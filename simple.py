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
    sparql = AUTHOR.format(uri)
    bindings = __run_query__(sparql)
    for row in bindings:
        authors.append({"@type": "Person",
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
    sparql = LIBRARY_GEO.format(uri)
    bindings = __run_query__(sparql)
    if len(bindings) != 1:
        return
    return {
        "@type": "Library",
        "@id": bindings.get('library').get('value'),
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": bindings.get('latitude').get('value'),
            "longitude": bindings.get('longitude').get('value')
        }
    }
        

def get_title(uri):
    sparql = TITLE.format(uri)
    bindings = __run_query__(sparql)
    title = ''
    for row in bindings:
        title += row.get('main').get('value')
        if 'subtitle' in row:
            title += row.get('subtitle').get('value')
    return title 
                            

@app.route("/<uuid>")
def instance(uuid):
    uri = "http://bibcat.coalliance.org/{}".format(uuid)
    output = {"@context": "http://schema.org",
        "@type": "CreativeWork",
        "name": get_title(uri),
        "datePublished": "",
        "author": get_authors(uri),
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
        }
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


AUTHOR = PREFIX + """

SELECT DISTINCT ?name
WHERE {{
    <{0}> relators:aut ?author .
    ?author schema:name ?name .
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

SELECT DISTINCT ?library ?lat ?long
WHERE {{
    ?item bf:itemOf <{0}> .
    ?item bf:heldBy ?library .
    ?library schema:geo ?coor .
    ?coor schema:latitude ?lat .
    ?coor schema:longitude ?long .
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
