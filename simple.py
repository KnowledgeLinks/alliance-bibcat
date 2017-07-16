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
from types import SimpleNamespace

from flask import Flask, render_template, request
from flask import abort, jsonify, flash, Response
from flask_cache import Cache
from bibcat.rml.processor import SPARQLProcessor

app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('config.py')

LIBRARIES = dict()

PROJECT_BASE =  os.path.abspath(os.path.dirname(__file__))
cache = Cache(app, config={"CACHE_TYPE": "filesystem",
                           "CACHE_DIR": os.path.join(PROJECT_BASE, "cache")})

BACKGROUND_THREAD = None

SCHEMA_PROCESSOR = SPARQLProcessor(
    rml_rules=["bibcat-bf-to-schema.ttl"],
    triplestore_url=app.config.get("TRIPLESTORE_URL"))

def set_libraries():
    global LIBRARIES
    bindings = __run_query__(LIBRARY_GEO)
    for row in bindings:
        library_iri = row.get('library').get('value')
        LIBRARIES[library_iri] = {
            "name": row.get('name').get('value'),
            "address": get_address(library_iri),
            "image": row.get('image').get('value'),
            "latitude": row.get('lat').get('value'),
            "longitude": row.get('long').get('value'),
            "telephone": row.get('telephone').get('value')
        }
        


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
    cover_template = "http://covers.openlibrary.org/b/isbn/{}-M.jpg"
    if not hasattr(instance, 'isbn'):
        return ''
    for isbn in instance.isbn:
        cover_url = cover_template.format(isbn)
        result = requests.get(cover_url)
        #print(cover_url, result.status_code)
        if result.status_code < 400:
            return """<img src="{}" alt="{} Cover Art" />""".format(cover_url,
                instance.name)
    return ''

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
                "name": instance.name,
                "provider": {
                    "url": item.provider.iri,
                    "address": {
                        "@type": "PostalAddress",
                        "streetAddress": item.provider.address.streetAddress,
                        "postalCode": item.provider.address.postalCode
                    }
                }
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
    if len(LIBRARIES) < 1:
        set_libraries()
    for iri, info in LIBRARIES.items():
        bf_counts_bindings = __run_query__(BIBFRAME_COUNTS.format(iri))
        bf_counts[iri] = {"name": info.get('name'),
                          "counts": bf_counts_bindings}

    return render_template("simple.html", 
        ts_stats=triples_store_stats,
        bf_counts=bf_counts)

def get_address(uri):
    address = {"@type": "PostalAddress"}
    sparql = LIBRARY_ADDRESS.format(uri)
    bindings = __run_query__(sparql)
    for row in bindings:
        address["streetAddress"] = row.get('streetAddr').get('value')
        address["addressLocality"] = row.get('city').get('value')
        address["addressRegion"] = row.get('state').get('value')
        address["postalCode"] = row.get('zip').get('value')
        break
    return address 
        

def get_authors(uri):
    authors = []
    sparql = CREATORS.format(uri)
    bindings = __run_query__(sparql)
    for row in bindings:
        raw_type = row.get('type_of').get('value')
        if raw_type.endswith("Organization"):
            type_of = "Organization"
        else:
            type_of = "Person"
        authors.append({"@type": type_of,
                        "name": row.get('name').get('value')})
    return authors
  
def get_date_published(uri):
    sparql = WORK_DATE.format(uri)
    bindings = __run_query__(sparql)
    dates = []
    for row in bindings:
        dates.append(row.get('date').get('value'))
    return dates
 

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
                if '@id' in row:
                    setattr(entity, key, build_entity(row))
            if not hasattr(entity, key): 
                setattr(entity, key, val)
        return entity
    SCHEMA_PROCESSOR.run(instance=iri, limit=1, offset=0)
    instance_listing = json.loads(SCHEMA_PROCESSOR.output.serialize(format='json-ld'))
    instance_vars = dict()
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
        for row in val:
            if '@id' in row:
                setattr(entity, key, build_entity(row))
        if not hasattr(entity , key):
            setattr(entity, key, val)
    return entity 

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
    instance = __construct_schema__(instance_iri)
    instance.workExample = [instance.workExample,]
    for row in instance.workExample:
        print(row.iri, item_iri, row.iri == item_iri, type(row.iri), type(item_iri))
        if row.iri == str(item_iri):
            item = row
    if not item:
        abort(404)
    return render_template("item.html",
        item=item,
        instance=instance)


@app.route("/<path:title>")
def display_instance(title):
    """Displays different views of bf:Instance 

    Args:
        title(path): Slugified title of Instance
    """
    # Kludge ensures that IRI does not have trailing /
    if title.endswith("/"):
        title = title[:-1]
    instance_iri = rdflib.URIRef("{0}{1}".format(
        app.config.get("BASE_URL"),
        title))
    instance = __construct_schema__(instance_iri)
    instance.workExample = [instance.workExample,]
    return render_template("instance.html",
        instance=instance)
    
@app.route("/siteindex.xml")
@cache.cached(timeout=86400) # Cached for 1 day
def site_index():
    """Generates siteindex XML, each sitemap has a maximum of 50k links
    dynamically generates the necessary number of sitemaps in the 
    template"""
    bindings = __run_query__(INSTANCE_COUNT)
    count = int(bindings[0].get('count').get('value'))
    shards = math.ceil(count/50000)
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
    offset = (int(offset)*50000) - 50000
    sparql = INSTANCES.format(offset)
    result = requests.post(app.config.get("TRIPLESTORE_URL"), 
        data={"query": sparql,
              "format": "json"})
    instances = result.json().get('results').get('bindings')
    #print("Number of instances {}".format(len(instances)))
    xml = render_template("sitemap_template.xml", instances=instances) 
    return Response(xml, mimetype="text/xml")



TEST_INSTANCE = SimpleNamespace()
TEST_INSTANCE.name="Environment Sustainibility for Boring People"
TEST_INSTANCE.authors=["Jerome Nielsen", "Jaye Pietrson", "Felix Colgrave"]
TEST_INSTANCE.editors=["Qwert Yuiop", "As Def", "Ghy Jikl"]
TEST_INSTANCE.datePublished="Apr. 1, 3000" 
TEST_INSTANCE.description="A book about environments, sustainability, more environments, and oh whatever lorem ipsum dolor sit amet, consectetur adipiscing elit. Ut hendrerit tortor quis elit ullamcorper, in congue odio placerat. Pellentesque quis gravida odio. Fusce tempor ex quam. Fusce et vestibulum velit. Maecenas magna diam, eleifend in feugiat vitae, eleifend quis neque. Vivamus egestas sapien vitae velit facilisis, et aliquam erat ultrices. Quisque purus nunc, gravida eget blandit eu, sollicitudin sit amet erat. Nullam blandit urna ut convallis placerat. Phasellus lectus neque, efficitur quis volutpat nec, laoreet nec velit. In interdum ipsum eget turpis tincidunt posuere. Nam pretium, eros quis aliquet egestas, nisl neque aliquet risus, ut cursus tellus sapien ac leo. Ut gravida diam et odio porttitor, vel vehicula massa malesuada. Fusce ornare commodo elit tincidunt venenatis."
TEST_INSTANCE.keywords = ["Maths", "Sciences", "Underwater basketweaving for the narcoleptic"]
TEST_INSTANCE.about=["Science", "Environment", "Sustenence"]
wex1 = SimpleNamespace() #No way am I putting these into the array first. Declare and flesh them out, THEN put them in there!
wex1.identifier = SimpleNamespace() 
wex1.identifier.propertyID = "1a2b3c-4d5e9z"
wex1.identifier.value = True
wex1.provider = SimpleNamespace()
wex1.provider.name = "Majestic Theatre"
wex1.fileFormat = "pdf"

wex2 = SimpleNamespace()
wex2.identifier = SimpleNamespace() 
wex2.identifier.propertyID = "aabbccddee"
wex2.identifier.value = False
wex2.provider = SimpleNamespace()
wex2.provider.name = "Ruby Cinema"
wex2.fileFormat = "print"

wex3 = SimpleNamespace()
wex3.identifier = SimpleNamespace() 
wex3.identifier.propertyID = "aabbccddee"
wex3.identifier.value = False
wex3.provider = SimpleNamespace()
wex3.provider.name = "Ruby Cinema"
wex3.fileFormat = "audio"

TEST_INSTANCE.workExample = [wex1, wex2, wex3] #I think that's how it works?
@app.route("/instance")
@app.route("/instance_test")
def bf_instance():
    return render_template("instance.html", instance=TEST_INSTANCE)
    
    
    
TEST_ITEM = SimpleNamespace()
TEST_ITEM.name="Environment Sustainibility for Boring People"
TEST_ITEM.authors=["Jerome Nielsen", "Jaye Pietrson", "Felix Colgrave"]
TEST_ITEM.editors=["Qwert Yuiop", "As Def", "Ghy Jikl"]
TEST_ITEM.datePublished="Apr. 1, 3000" 
TEST_ITEM.description="A book about environments, sustainability, more environments, and oh whatever lorem ipsum dolor sit amet, consectetur adipiscing elit. Ut hendrerit tortor quis elit ullamcorper, in congue odio placerat. Pellentesque quis gravida odio. Fusce tempor ex quam. Fusce et vestibulum velit. Maecenas magna diam, eleifend in feugiat vitae, eleifend quis neque. Vivamus egestas sapien vitae velit facilisis, et aliquam erat ultrices. Quisque purus nunc, gravida eget blandit eu, sollicitudin sit amet erat. Nullam blandit urna ut convallis placerat. Phasellus lectus neque, efficitur quis volutpat nec, laoreet nec velit. In interdum ipsum eget turpis tincidunt posuere. Nam pretium, eros quis aliquet egestas, nisl neque aliquet risus, ut cursus tellus sapien ac leo. Ut gravida diam et odio porttitor, vel vehicula massa malesuada. Fusce ornare commodo elit tincidunt venenatis."
TEST_ITEM.about=["Science", "Environment", "Sustenence"]
TEST_ITEM.location="Western State Coloradu Univarsetet" 
TEST_ITEM.refnumber="1A2B3C" 
TEST_ITEM.availability="Available" 
TEST_ITEM.url="http://google.com"
TEST_ITEM.genre=["Textbook", "Science", "Sustainability", "Nonbiodegradable"]
TEST_ITEM.publisher="Obadiah Books"
TEST_ITEM.fileFormat="pdf"

@app.route("/item")
def bf_item():
    return render_template("item.html", instance=TEST_ITEM)
    
    
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

INSTANCE_COUNT = PREFIX + """
SELECT (count(*) as ?count) WHERE {
   ?s rdf:type bf:Instance .
}"""

ISBNS = PREFIX + """

SELECT DISTINCT ?isbn
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
    set_libraries()
    app.run(host='0.0.0.0', debug=True)
