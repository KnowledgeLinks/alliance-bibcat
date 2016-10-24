import requests
from flask import Flask, jsonify, render_template

app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('config.py')

@app.route("/")
def home():
    return "Colorado Alliance of Research Libraries BIBCAT Sitemap"

@app.route("/<uuid>")
def instance(uuid):
    output = {"@context": "http://schema.org",
        "@type": "CreativeWork",
        "name": "",
        "datePublished": "",
        "author": "",
        "mainEntityOfPage": {
            "@type": "CreativeWork",
            "@id": None,
            "place": {}
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

TITLE = PREFIX + """
SELECT ?main ?subtitle
WHERE {{
   <{0}> bf:title ?title .
   ?title bf:mainTitle ?main .
   OPTIONAL {{ ?title bf:subtitle ?subtitle }}
}}"""


if __name__ == '__main__':
    app.run(debug=True)
