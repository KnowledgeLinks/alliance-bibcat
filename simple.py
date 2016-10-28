__author__ = "Jeremy Nelson"

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
from flask_negotiate import consumes, produces

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
        LIBRARIES[row.get('library').get('value')] = {
            "name": row.get('name').get('value'),
            "latitude": row.get('lat').get('value'),
            "longitude": row.get('long').get('value')
    }


class SetupThread(threading.Thread):

    def __init__(self, **kwargs):
        threading.Thread.__init__(self)
        self.messages = []
    
    def run(self):
        set_libraries()
        while 1:
            time.sleep(10)
            try:
                bindings = __run_query__(TRIPLESTORE_COUNT)
                count = int(bindings[0].get("count").get("value"))
                # Check for Empty triplestore, load data and alliance graphs
                # if empty
                if count < 1:
                    # Alliance RDF
                    msg = "...Loading Alliance RDF Graph"
                    self.messages.append(msg)
                    print(msg)
                    with open(os.path.join(PROJECT_BASE,
                        "custom",
                        "alliance.ttl")) as fo:
                        result = requests.post(
                            app.config.get("TRIPLESTORE_URL"),
                            data=fo.read(),
                            headers={"Content-Type": "text/turtle"})
                    # Now loads all TTL files in data directory
                    data_dir = os.path.join(PROJECT_BASE, "data")
                    data_walker = next(os.walk(data_dir))
                    for ttl_filename in data_walker[2]:
                        if not ttl_filename.endswith("ttl"):
                            continue
                        msg = "...Loading {}".format(ttl_filename)
                        self.messages.append(msg)
                        print(msg)
                        with open(os.path.join(
                            PROJECT_BASE,
                            "data",
                            ttl_filename), "rb+") as fo:
                                result = requests.post(
                                    app.config.get("TRIPLESTORE_URL"),
                                    data=fo,
                                headers={"Content-Type": "text/turtle"})
                break
            except:
                pass
        cache.clear()

def __run_query__(sparql):
    result = requests.post(app.config.get("TRIPLESTORE_URL"),
        data={"query": sparql,
              "format": "json"})
    if result.status_code > 399:
        print(result.text)
        return []
    bindings = result.json().get('results').get('bindings')
    return bindings



@app.route("/")
def home():
    triples_store_stats = {}
    bf_counts = {}
    for iri, info in LIBRARIES.items():
        bf_counts_bindings = __run_query__(BIBFRAME_COUNTS.format(iri))
        print("\t{}".format(iri))
        bf_counts[iri] = {"name": info.get('name'),
                          "counts": bf_counts_bindings}

    return render_template("simple.html", 
        ts_stats=triples_store_stats,
        bf_counts=bf_counts)


@app.route("/init")
def initialize():
    global BACKGROUND_THREAD
    BACKGROUND_THREAD = SetupThread()
    BACKGROUND_THREAD.start()
    time.sleep(15)
    set_libraries()
    return "Initializing Triplestore"

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
    output = {"@type": "Library"}
    sparql = LIBRARY.format(uri)
    bindings = __run_query__(sparql)
    for row in bindings:
        library_uri = row.get('library').get('value')
        output["@id"] = library_uri
        output["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": LIBRARIES[library_uri]['latitude'],
            "longitude": LIBRARIES[library_uri]['longitude']
        },
        output["name"] = LIBRARIES[library_uri]["name"]
        
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
#@produces("application/json", "application/ld-json")
def instance(uuid):
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
    output = {"@context": {"name":"http://schema.org",
                           "bf": "http://id.loc.gov/ontologies/bibframe/"},
        "@type": get_types(uuid),
        "name": get_title(uri),
        "datePublished": "",
        "author": get_authors(uri),
        "isbn": get_isbns(uri),
        "mainEntityOfPage": {
            "@type": "CreativeWork", 
            "@id": get_item(uri),
            "additionalType": "bf:Item",
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
        "version": "0.5.0"
    }
    return jsonify(output)
    return Response(json.dumps(output), mimetype="application/ld+json")
    

@app.route("/siteindex.xml")
@cache.cached(timeout=86400) # Cached for 1 day
def site_index():
    """Generates siteindex XML, each sitemap has a maximum of 50k links
    dynamically generates the necessary number of sitemaps in the 
    template"""
    bindings = __run_query__(INSTANCE_COUNT)
    count = int(bindings[0].get('count').get('value'))
    shards = math.ceil(count/50000)
    xml = render_template("siteindex.xml", 
            count=range(1, shards+1), 
            last_modified=datetime.datetime.utcnow().isoformat())
    return Response(xml, mimetype="text/xml")

@app.route("/sitemap<offset>.xml", methods=["GET"])
@cache.cached(timeout=86400)
#@produces("text/xml")
def sitemap(offset=0):
    offset = (int(offset)*50000) - 50000
    sparql = INSTANCES.format(offset)
    result = requests.post(app.config.get("TRIPLESTORE_URL"),
        data={"query": sparql,
              "format": "json"})
    instances = result.json().get('results').get('bindings')
    xml = render_template("sitemap_template.xml", instances=instances)
    return Response(xml, mimetype="text/xml")


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

LIBRARY_GEO = PREFIX + """

SELECT DISTINCT ?library ?name ?lat ?long
WHERE {
    ?library rdf:type schema:Library .
    ?library rdfs:label ?name .
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

if __name__ == '__main__':
    app.run(debug=True)
