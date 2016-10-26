import requests
from flask import Flask, jsonify, render_template

app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('config.py')

@app.route("/")
def home():
    return "Colorado Alliance of Research Libraries BIBCAT Sitemap"

def __run_query__(sparql):
    result = requests.post(app.config.get("TRIPLESTORE_URL"),
        data={"query": sparql,
              "format": "json"})
    bindings = result.json().get('results').get('bindings')
    return bindings

    

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
    
def get_item(uri):
    item = None
    sparql = ITEM.format(uri)
    bindings = __run_query__(sparql)
    if len(bindings) == 1:
        item = bindings[0].get('item').get('value')    
    return item

def get_place(uri):
    output = {"@type": "Library"}
    sparql = LIBRARY_GEO.format(uri)
    bindings = __run_query__(sparql)
    for row in bindings:
        output["@id"] = row.get('library').get('value')
        output["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": row.get('latitude', {}).get('value'),
            "longitude": row.get('longitude', {}).get('value')
        }
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
    uri = "http://bibcat.coalliance.org/{}".format(uuid)
    output = {"@context": {"name":"http://schema.org",
                           "bf": "http://id.loc.gov/ontologies/bibframe/"},
        "@type": get_types(uuid),
        "name": get_title(uri),
        "datePublished": "",
        "author": get_authors(uri),
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
    # add_isbns(uri)
    return jsonify(output)
    

@app.route("/sitemap<offset>.xml", methods=["GET"])
def sitemap(offset=0):
    # This should be cached
    result = requests.post(app.config.get("TRIPLESTORE_URL"),
        data={"query": INSTANCES,
              "format": "json"})
    instances = result.json().get('results').get('bindings')
    return render_template("sitemap_template.xml", instances=instances)


PREFIX = """PREFIX bf: <http://id.loc.gov/ontologies/bibframe/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX relators: <http://id.loc.gov/vocabulary/relators/>
PREFIX schema: <http://schema.org/>
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




INSTANCES = PREFIX + """

SELECT DISTINCT ?instance ?date
WHERE {
    ?instance rdf:type bf:Instance .
    ?instance bf:generationProcess ?process .
    ?process bf:generationDate ?date .
} LIMIT 100"""

ITEM = PREFIX + """

SELECT DISTINCT ?item
WHERE {{
    ?item bf:itemOf <{0}> .
}}""" 

LIBRARY_GEO = PREFIX + """

SELECT DISTINCT ?library 
WHERE {{
    ?item bf:itemOf <{0}> .
    ?item bf:heldBy ?library .
}}"""

TITLE = PREFIX + """
SELECT ?main ?subtitle
WHERE {{
   <{0}> bf:title ?title .
   ?title bf:mainTitle ?main .
   OPTIONAL {{ ?title bf:subtitle ?subtitle }}
}}"""


if __name__ == '__main__':
    app.run(debug=True)
