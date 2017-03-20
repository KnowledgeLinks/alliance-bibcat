"""Loads all RDF Turtle files in custom/ and data/ directories"""
__author__ = "Jeremy Nelson"

import datetime
import os
import rdflib
import sys
import urllib.request
try:
    from lxml import etree
except ImportError:
    import xml.etree.ElementTree as etree

PROJECT_BASE =  os.path.abspath(os.path.dirname(__file__))
sys.path.append(PROJECT_BASE)
import instance.config as config
TRIPLESTORE_URL = "http://localhost:9999/blazegraph/sparql"

def load_turtles():
    """Loads all RDF Turtle files located in the custom and data 
    directories."""
    start = datetime.datetime.now()
    print("Loading RDF turtle files for Alliance BIBCAT at {}".format(
        start.isoformat()))
    # Load custom ttl files for institutional metadata for richer
    # context for ttl files in the data directory
    for directory in ["custom", "data"]: 
        turtle_path = os.path.join(PROJECT_BASE, directory)
        walker = next(os.walk(turtle_path))
        for filename in walker[2]:
            if not filename.endswith("ttl"):
                continue
            full_path = os.path.join(turtle_path, filename)
            with open(full_path, "rb") as fo:
                raw_turtle = fo.read()
            request = urllib.request.Request(
                          url=TRIPLESTORE_URL,
                          data=raw_turtle,
                          headers={"Content-type": "text/turtle"})
            with urllib.request.urlopen(request) as triplestore_response:
                print("\t{} ingest result {}".format(filename, 
                    triplestore_response.read().decode('utf-8')))
    end = datetime.datetime.now()
    print("Finished RDF turtle load at {}, total time {} minutes".format(
        end,
        (end-start).seconds / 60.0))

def load_marc_xml(marc_filepath, mrc2bf_xsl):
    marc_context = etree.iterparse(marc_filepath)
    xslt_tree = etree.parse(mrc2bf_xsl)
    xslt_transform = etree.XSLT(xslt_tree)
    match_keys, record = None, {}
    for action, elem in marc_context:
        if "record" in elem.tag:
            record = elem
            bf_rdf_xml = xslt_transform(
                record, 
                baseuri="'{0}'".format(config.get("BASE_URL"))
            bf_rdf = rdflib.parse(bf_rdf_xml)




if __name__ == '__main__':
    load_turtles()
