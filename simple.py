__author__ = "Jeremy Nelson, Jay Peterson"

import datetime
import json
import math
import os
import requests
import threading
import sys
import time
from flask import Flask, render_template, request
from flask import abort, jsonify, flash, Response
from flask_cache import Cache

app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('config.py')

LIBRARIES = dict()
PROJECT_BASE =  os.path.abspath(os.path.dirname(__file__))

cache = Cache(app, config={"CACHE_TYPE": "filesystem",
                           "CACHE_DIR": os.path.join(PROJECT_BASE, "cache")})

BACKGROUND_THREAD = None

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
 
def get_isbns(uri):
    isbns = []
    bindings = __run_query__(ISBNS.format(uri))
    for row in bindings:
        isbns.append(row.get('isbn').get('value'))
    return isbns

def get_item(uri):
    item = None
    sparql = ITEM.format(uri)
    bindings = __run_query__(sparql)
    if len(bindings) == 1:
        item = bindings[0].get('item').get('value')    
    return item

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
        

def get_title(uri):
    sparql = TITLE.format(uri)
    bindings = __run_query__(sparql)
    title = ''
    for row in bindings:
        title += row.get('main').get('value')
        if 'subtitle' in row:
            title += row.get('subtitle').get('value')
    return title 

def get_types(uuid):
    return "CreativeWork"
                            

@app.route("/<uuid>")
def instance(uuid):
    # Hack for Google verification
    if uuid.startswith("google"):
        return render_template(uuid)
    uri = "http://bibcat.coalliance.org/{}".format(uuid)
    bindings = __run_query__(GET_CLASS.format(uri))
    if len(bindings) < 1:
        abort(404)
    if request.args.get("vocab") == "bibframe":
        return jsonify({"@context": "http://id.loc.gov/ontologies/bibframe/",
            "@id": uri,
            "title": {"@type": "InstanceTitle",
                      "mainTitle": get_title(uri)}
        })
    output = {"@context": "http://schema.org",
        "@type": get_types(uuid),
        "name": get_title(uri),
        "datePublished": get_date_published(uri),
        "author": get_authors(uri),
        "isbn": get_isbns(uri),
        "mainEntityOfPage": {
            "@type": "CreativeWork", 
            "@id": get_item(uri),
            "contentLocation": get_place(uri)
        },
        "publisher": {
            "@type": "Organization",
            "name": "Colorado Alliance of Research Libraries",
            "logo": {
                  "@type": "ImageObject",
                  "url": "https://www.coalliance.org/sites/all/themes/minim/logo.png",
                  "height": "90px",
                  "width": "257px"
             }
        },
        "version": "0.7.0"
    }
    if len(output['isbn']) > 0:
        output.pop("@type")
        output['@type'] = 'Book' 
    return render_template('detail.html', info=output)
    
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
@cache.cached(timeout=86400)
def sitemap(offset=0):
    offset = (int(offset)*50000) - 50000
    sparql = INSTANCES.format(offset)
    result = requests.post(app.config.get("TRIPLESTORE_URL"),
        data={"query": sparql,
              "format": "json"})
    instances = result.json().get('results').get('bindings')
    xml = render_template("sitemap_template.xml", instances=instances)
    return Response(xml, mimetype="text/xml")

    
@app.route("/instance")


def bf_instance():
    return render_template("instance.html", site_title = "Welcome!", instance_title = "Environment Sustainibility for Boring People", authors = ["Jerome Nielsen", "Jaye Pietrson", "Felix Colgrave"], pubdate = "2016", blurb = LOREM, subjects = ["Maths", "Sciences", "Underwater basketweaving for the narcoleptic"], item_list = ["We've got a copy down at Joe's Pizza.", "There's one duct-taped to my chair.", "Cambridge library, 5012 N Avenue."])

LOREM = """
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Ut hendrerit tortor quis elit ullamcorper, in congue odio placerat. Pellentesque quis gravida odio. Fusce tempor ex quam. Fusce et vestibulum velit. Maecenas magna diam, eleifend in feugiat vitae, eleifend quis neque. Vivamus egestas sapien vitae velit facilisis, et aliquam erat ultrices. Quisque purus nunc, gravida eget blandit eu, sollicitudin sit amet erat. Nullam blandit urna ut convallis placerat. Phasellus lectus neque, efficitur quis volutpat nec, laoreet nec velit. In interdum ipsum eget turpis tincidunt posuere. Nam pretium, eros quis aliquet egestas, nisl neque aliquet risus, ut cursus tellus sapien ac leo. Ut gravida diam et odio porttitor, vel vehicula massa malesuada. Fusce ornare commodo elit tincidunt venenatis.
"""
    
PREFIX = """PREFIX bf: <http://id.loc.gov/ontologies/bibframe/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX relators: <http://id.loc.gov/vocabulary/relators/>
PREFIX schema: <http://schema.org/>
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
    ?instance bf:generationProcess ?process .
    ?process bf:generationDate ?date .
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
