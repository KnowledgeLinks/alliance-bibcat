__author__ = "Jeremy Nelson, Jay Peterson"

import datetime
import json
import math
import os
import requests
import threading
import rdflib
import sys
import time
import re, pdb
from types import SimpleNamespace

from flask import Flask, render_template, request
from flask import abort, jsonify, flash, Response, url_for
from flask_cache import Cache
# from bibcat.rml.processor import SPARQLProcessor
from rdfframework.rml.processor import SPARQLProcessor
# from rdfframework.rml.processor2 import SPARQLProcessor
app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('config.py')

LIBRARIES = dict()

PROJECT_BASE =  os.path.abspath(os.path.dirname(__file__))
cache = Cache(app, config={"CACHE_TYPE": "filesystem",
                           "CACHE_DIR": os.path.join(PROJECT_BASE, "cache")})

BACKGROUND_THREAD = None

SCHEMA_PROCESSOR = SPARQLProcessor(
    rml_rules=["bf-to-schema_rdfw.ttl"],
    triplestore_url=app.config.get("TRIPLESTORE_URL"))

ISBN_RE = re.compile(r"^(\d+)\b")

def __run_query__(sparql):
    result = requests.post(app.config.get("TRIPLESTORE_URL"),
        data={"query": sparql,
              "format": "json"})
    if result.status_code > 399:
        return []
    bindings = result.json().get('results').get('bindings')
    return bindings

@app.template_filter('cover_art')
def retrieve_cover_art(instance):
    cover_template = "http://images.amazon.com/images/P/{}.jpg"
    if not hasattr(instance, 'isbn'):
        return ''
    for isbn in instance.isbn:
        isbn_result = ISBN_RE.match(isbn)
        if isbn_result is None:
            continue
        #print(isbn_result.groups()[0])
        isbn_formatted = isbn_result.groups()[0]
        cover_url = cover_template.format(isbn_formatted)
        #print(isbn)
        result = requests.get(cover_url)
        #print(cover_url, result.status_code)
        if len(result.content) > 100:
            return """<img src="{}" alt="{} Cover Art" align="right" />""".format(cover_url,
                instance.name)
    return ''

#@app.template_filter("get_itemjsonld")
#def item_jsonld(instance):


@app.template_filter('get_jsonld')
def output_jsonld(instance):
    #print(instance)
    def test_add_simple(name):
        if hasattr(instance, name):
            instance_ld[name] = getattr(instance, name)
    instance_ld = { "@context": "http://schema.org",
        "@type": "CreativeWork",
        "author": [],
        "contributor": [],
        "workExample": []
    }
    if hasattr(instance, 'name'):
        instance_ld['name'] = instance.name
    if hasattr(instance, 'description'):
        instance_ld['description'] = instance.description
    if hasattr(instance, 'datePublished'):
        if isinstance(instance.datePublished, list):
            instance_ld['datePublished'] = ",".join(instance.datePublished)
        else:
            instance_ld['datePublished'] = instance.datePublished
    test_add_simple('author')
    test_add_simple('contributor')
    if hasattr(instance, 'workExample'):
        for item in instance.workExample:
            item_example = {"@type": "CreativeWork",
                "url": item.iri,
                "name": "{} -- {}".format(item.provider.name, instance.name),
                "provider": {
                    "@type": "Organization",
                    "name": item.provider.name,
                    "logo": "{}{}".format(app.config.get("BASE_URL")[:-1],
                                          url_for('static',
                                              filename="img/{}".format(
                                                  item.provider.logo))),
                    "url": item.provider.iri,
                                        "address": {
                        "@type": "PostalAddress",
                        "streetAddress": item.provider.address.streetAddress,
                        "postalCode": item.provider.address.postalCode
                    }
                }
            }
            if hasattr(item.provider, "latitude"):
                item_example["geo"] = {
                        "@type": "GeoCoordinates",
                        "latitude": item.provider.latitude,
                        "longitude": item.provider.longitude
                }
            instance_ld['workExample'].append(item_example)
    return json.dumps(instance_ld, indent=2, sort_keys=True)

@app.template_filter("is_list")
def test_for_list(is_list):
    return isinstance(is_list, list)

@app.route("/")
def home():
    triples_store_stats = {}
    bf_counts = {}
    #if len(LIBRARIES) < 1:
        #set_libraries()
    for iri, info in LIBRARIES.items():
        bf_counts_bindings = __run_query__(BIBFRAME_COUNTS.format(iri))
        bf_counts[iri] = {"name": info.get('name'),
                          "counts": bf_counts_bindings}

    return render_template("simple.html",
        ts_stats=triples_store_stats,
        bf_counts=bf_counts)


def get_place(uri):
    output = {"@type": "Library", "priceRange" : "0"}
    sparql = LIBRARY.format(uri)
    bindings = __run_query__(sparql)
    for row in bindings:
        library_uri = row.get('library').get('value')
        if not library_uri in LIBRARIES:
            continue
        output["@id"] = library_uri
        output["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": LIBRARIES[library_uri]['latitude'],
            "longitude": LIBRARIES[library_uri]['longitude']
        }
        output["address"] = LIBRARIES[library_uri]["address"]
        output["image"] = LIBRARIES[library_uri]["image"]
        output["name"] = LIBRARIES[library_uri]["name"]
        output["telephone"] = LIBRARIES[library_uri]["telephone"]
    return output


def __construct_schema__(iri):
    """Constructs a simple Python object populated from rdflib.Graph
    schema.org triples and an bf:Instance IRI

    Args:
    -----
        iri: rdflib.URIRef of Instance

    Returns:
    --------
        SimpleNamespace
    """
    def build_entity(entity_dict):
        if not '@id' in entity_dict:
            return
        entity = SimpleNamespace()
        entity.iri = entity_dict['@id']
        for key, val in instance_vars[entity_dict['@id']].items():
            for row in val:
                if '@id' in row and not key.startswith("sameAs"):
                    setattr(entity, key, build_entity(row))
            if not hasattr(entity, key):
                setattr(entity, key, val)
        return entity
    SCHEMA_PROCESSOR.run(instance=iri, limit=1, offset=0, threading=False)
    instance_listing = json.loads(SCHEMA_PROCESSOR.output.serialize(format='json-ld').decode())
    instance_vars = dict()
    if not instance_listing:
        raise LookupError("IRI --- %s --- returned no data" % iri)
    for row in instance_listing:
        entity_url = row['@id']
        instance_vars[entity_url] = {}
        for key, val in row.items():
            if key.startswith('@id'):
                continue
            if key.startswith('@type'):
                instance_vars[entity_url]['class'] = val
            else:
                output = []
                if isinstance(val, list):
                    for list_item in val:
                        if '@value' in list_item:
                            output.append(list_item.get('@value'))
                        else:
                            output.append(list_item)
                if len(output) == 1 and not isinstance(output[0], dict):
                    output = ''.join(output)
                instance_vars[entity_url][key.split("/")[-1]] = output
    entity = SimpleNamespace()
    entity.iri = iri
    for key, val in instance_vars.get(str(iri)).items():
        output = []
        for row in val:
            if '@id' in row:
                output.append(build_entity(row))
        if len(output) < 1:
            output = val
        if not hasattr(entity , key):
            setattr(entity, key, output)
    return entity

def __check_exists__(iri):
    """Internal function takes an iri and queries triplestore for
    it's existence, returns True if found, False otherwise

    Args:

    ----
        iri: A rdflib.URIRef
    """
    start = datetime.datetime.now()
    # sparql = PREFIX +"""
    # SELECT DISTINCT ?iri
    #                  WHERE {{ OPTIONAL {{ ?iri rdf:type bf:Instance . }}
    #                           OPTIONAL {{ ?iri rdf:type bf:Item . }}
    #                           FILTER (sameTerm(?iri, <{iri}>))
    #                 }}""".format(iri=iri)
    sparql = PREFIX +"""
    SELECT DISTINCT *
                     WHERE {{ <{iri}> rdf:type ?type .
                              FILTER (?type=bf:Instance||?type=bf:Item)
                    }}""".format(iri=iri)
    bindings = __run_query__(sparql)
    # print("check_exists ran in: ", (datetime.datetime.now() - start))
    if len(bindings) > 0:
        return True
    return False

@app.route("/agent/<path:name>")
def display_agent(name):
    """Displays bf:Agent view"""
    agent_iri = rdflib.URIRef("{}agent/{}".format(
        app.config.get('BASE_URL'),
        name))
    sparql = AGENT_DETAIL.format(agent=agent_iri)
    bindings = __run_query__(sparql)
    if len(bindings) < 1:
        abort(404)
    return render_template("collections.html",
        collection_type="BIBFRAME Agents",
        collection_name=bindings[0].get('name').get('value'),
        instances=bindings)

@app.route("/topic/<path:name>")
def display_topic(name):
    """bf:Topic view"""
    topic_iri = rdflib.URIRef("{}topic/{}".format(
        app.config.get('BASE_URL'),
        name))
    sparql = TOPIC_DETAIL.format(topic=topic_iri)
    bindings = __run_query__(sparql)
    if len(bindings) < 1:
        abort(404)
    return render_template('collections.html',
        collection_type='BIBFRAME Topic',
        collection_name=bindings[0].get('name').get('value'),
        instances=bindings)


@app.route("/<path:title>/<path:institution>")
def display_item(title, institution):
    """Displays different views of bf:Item

    Args:
    -----
        title: path, Slugified title of Instance
        institution: path, Slugified institution name
    """
    instance_iri = rdflib.URIRef("{0}{1}".format(
        app.config.get("BASE_URL"),
        str(title)))
    if institution.endswith("/"):
        institution = institution[:-1]
    item_iri = rdflib.URIRef("{0}/{1}".format(
        instance_iri,
        institution))

    item = None
    try:
        instance = __construct_schema__(instance_iri)
    except LookupError as err:
        print(err.args[0])
        abort(404)
    instance.workExample = instance.workExample
    for row in instance.workExample:
        if row.iri == str(item_iri):
            item = row
    if not item:
        abort(404)
    return render_template("item.html",
        item=item,
        instance=instance)

@app.route("/robots.txt")
def robots():
    robots_txt = render_template("robots.txt")
    return Response(robots_txt, mimetype="text/plain")

@app.route("/<path:title>.json")
@app.route("/<path:title>")
def display_instance(title):
    """Displays different views of bf:Instance

    Args:
        title(path): Slugified title of Instance
    """
    if title.startswith("google") or \
       title.startswith("BingSiteAuth"):
        return render_template(title)
    # Kludge ensures that IRI does not have trailing /
    if title.endswith("/"):
        title = title[:-1]
    instance_iri = rdflib.URIRef("{0}{1}".format(
        app.config.get("BASE_URL"),
        title))
    # if not __check_exists__(instance_iri):
    #     abort(404)
    start = datetime.datetime.now()
    try:
        instance = __construct_schema__(instance_iri)
    except LookupError:
        abort(404)
    # pdb.set_trace()
    # print("Schema generated in %s" % (datetime.datetime.now() - start))
    for item in instance.workExample:

        if not hasattr(item, "provider"):
            # Try to directly query for bf:heldBy for item iri
            # sparql = PREFIX + """
            # SELECT DISTINCT ?provider ?name ?logo ?street ?city ?state ?zip
            #       WHERE {{ <{item}>  bf:heldBy ?provider .
            #                ?provider schema:logo ?logo .
            #                ?library schema:parentOrganization ?provider ;
            #                         rdfs:label ?name ;
            #                         schema:address ?addr .
            #                ?addr    schema:streetAddress ?street ;
            #                         schema:addressLocality ?city ;
            #                         schema:addressRegion ?state ;
            #                         schema:postalCode ?zip .
            #                                         }}""".format(item=item.iri)
            # bindings = __run_query__(sparql)
            bindings = []
            provider = SimpleNamespace()
            address = SimpleNamespace()
            if len(bindings) > 0:
                provider.name = bindings[0].get('name').get('value')
                provider.iri =  bindings[0].get('provider').get('value')
                provider.logo = bindings[0].get('logo').get('value')
                address.streetAddress = bindings[0].get('street').get('value')
            else:
                # Default to the Alliance
                provider.logo = "alliance-logo.png"
                provider.name = "Unknown"
                provider.iri = app.config.get('BASE_URL')
                address.streetAddress = "E Florida Ave"
                address.city = "Denver"
                address.state = "Colorado"
                address.postalCode = "80210"
            setattr(provider, "address", address)
            setattr(item, "provider", provider)

    if request.path.endswith(".json"):
        raw_json = output_jsonld(instance)
        return jsonify(json.loads(raw_json))
    return render_template("instance.html",
        instance=instance)

@app.route("/siteindex.xml")
@cache.cached(timeout=86400) # Cached for 1 day
def site_index():
    """Generates siteindex XML, each sitemap has a maximum of 50k links
    dynamically generates the necessary number of sitemaps in the
    template"""
    bindings = __run_query__(ITEM_COUNT)
    count = int(bindings[0].get('count').get('value'))
    shards = math.ceil(count/10000)
    mod_date = app.config.get('MOD_DATE')
    if mod_date is None:
        mod_date=datetime.datetime.utcnow().strftime("%Y-%m-%d")
    xml = render_template("siteindex.xml",
            count=range(1, shards+1),
            last_modified=mod_date)
    return Response(xml, mimetype="text/xml")

@app.route("/sitemap<offset>.xml", methods=["GET"])
#@cache.cached(timeout=86400)
def sitemap(offset=0):
    offset = (int(offset)*10000) - 10000
    sparql = ITEMS.format(10000, offset)
    result = requests.post(app.config.get("TRIPLESTORE_URL"),
        data={"query": sparql,
              "format": "json"})
    items = result.json().get('results').get('bindings')
    #print("Number of instances {}".format(len(instances)))
    xml = render_template("sitemap_template.xml", items=items)
    return Response(xml, mimetype="text/xml")


PREFIX = """PREFIX bf: <http://id.loc.gov/ontologies/bibframe/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX relators: <http://id.loc.gov/vocabulary/relators/>
PREFIX schema: <http://schema.org/>
"""

AGENT_DETAIL = PREFIX + """
SELECT ?name ?instance ?instance_name
WHERE {{
    <{agent}> rdfs:label ?name .
    ?work bf:contribution ?contrib .
    ?contrib bf:agent <{agent}> .
    ?instance bf:instanceOf ?work ;
        rdfs:label ?instance_name .
}} ORDER BY ?label
LIMIT 100
"""

BIBFRAME_COUNTS = PREFIX + """

SELECT DISTINCT (count(?work) as ?work_count) (count(?instance) as ?instance_count) (count(?item) as ?item_count)
WHERE {{
    ?item bf:heldBy <{0}> .
    ?item bf:itemOf ?instance .
    ?instance bf:instanceOf ?work .
}}
"""

CREATORS = PREFIX + """

SELECT DISTINCT ?name ?type_of
WHERE {{
    BIND(<{0}> as ?instance)
 {{
    ?instance relators:aut ?author
 }} UNION {{
    ?instance relators:cre ?author
 }} UNION {{
    ?instance relators:aus ?author
 }}
 ?author schema:name ?name .
 ?author rdf:type ?type_of .
}} ORDER BY ?name"""


DETAIL = PREFIX + """

SELECT DISTINCT ?instance ?date
WHERE {
    ?instance rdf:type bf:Instance .
    ?instance bf:generationProcess ?process .
    ?process bf:generationDate ?date .
} LIMIT 100"""

GET_CLASS = PREFIX + """

SELECT DISTINCT ?type_of
WHERE {{
    <{0}> rdf:type ?type_of .
}}"""

INSTANCES = PREFIX + """

SELECT DISTINCT ?instance ?date
WHERE {{
    ?instance rdf:type bf:Instance .
    OPTIONAL {{ ?instance bf:generationProcess ?process .
                ?process bf:generationDate ?date }}
    FILTER(isIRI(?instance))
}} ORDER BY ?instance
LIMIT 50000
OFFSET {0}"""

ITEMS = PREFIX + """
SELECT DISTINCT ?item ?date
WHERE {{
    ?item rdf:type bf:Item ;
          bf:itemOf ?instance .
    OPTIONAL {{
        ?instance bf:generationProcess ?process .
        ?process bf:generationDate ?date
    }}
}} ORDER BY ?item
LIMIT {0}
OFFSET {1}"""

INSTANCE_COUNT = PREFIX + """
SELECT (count(*) as ?count) WHERE {
   ?s rdf:type bf:Instance .
}"""

ITEM_COUNT = PREFIX + """
SELECT (count(?s) as ?count) WHERE {
    ?s rdf:type bf:Item .
}"""

ISBNS = PREFIX + """SELECT DISTINCT ?isbn
WHERE {{
    <{0}> bf:identifiedBy ?isbn_node .
    ?isbn_node rdf:type bf:Isbn .
    ?isbn_node rdf:value ?isbn .
}}"""

ITEM = PREFIX + """

SELECT DISTINCT ?item
WHERE {{
    ?item bf:itemOf <{0}> .
}}"""


LIBRARY = PREFIX + """

SELECT DISTINCT ?library
WHERE {{
    ?item bf:itemOf <{0}> .
    ?item bf:heldBy ?library .
}}
"""

LIBRARY_ADDRESS = PREFIX + """

SELECT DISTINCT ?streetAddr ?city ?state ?zip
WHERE {{
    <{0}> schema:address ?addr .
    ?addr schema:streetAddress ?streetAddr .
    ?addr schema:addressLocality ?city .
    ?addr schema:addressRegion ?state .
    ?addr schema:postalCode ?zip .
}}
"""

LIBRARY_GEO = PREFIX + """

SELECT DISTINCT ?library ?name ?image ?telephone ?lat ?long
WHERE {
    ?library rdf:type schema:Library .
    ?library rdfs:label ?name .
    ?library schema:telephone ?telephone .
    ?library schema:image ?image .
    ?library schema:geo ?coor .
    ?coor schema:latitude ?lat .
    ?coor schema:longitude ?long .
}"""

TITLE = PREFIX + """
SELECT ?main ?subtitle
WHERE {{
   <{0}> bf:title ?title .
   ?title bf:mainTitle ?main .
   OPTIONAL {{ ?title bf:subtitle ?subtitle }}
}}"""

TOPIC_DETAIL = PREFIX + """
SELECT ?name ?instance ?instance_name
WHERE {{
    <{topic}> rdfs:label ?name .
    ?work bf:subject <{topic}> .
    ?instance bf:instanceOf ?work ;
        rdfs:label ?instance_name .
}} ORDER BY ?label
LIMIT 100
"""

TRIPLESTORE_COUNT = """SELECT (count(*) as ?count) WHERE {
   ?s ?p ?o .
}"""

WORK_DATE = PREFIX + """
SELECT ?date
WHERE {{
    <{0}> bf:instanceOf ?work .
    ?work bf:originDate ?date .
}}"""

if __name__ == '__main__':
    #set_libraries()
    app.run(host='0.0.0.0', debug=True)
