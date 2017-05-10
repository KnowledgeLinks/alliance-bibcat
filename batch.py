__author__ = "Jeremy Nelson"

import click
import datetime
import io
import logging
import os
import rdflib
import requests
import uuid
import sys 
import xml.etree.ElementTree as etree
import lxml.etree

PROJECT_BASE =  os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(PROJECT_BASE, "bibcat/VERSION")) as fo:
    BIBCAT_VERSION = fo.read()
sys.path.append(PROJECT_BASE)
import instance.config as config
import bibcat.rml.processor as processor
from load import AlliancePreprocessor

MARC_NS = {'marc': 'http://www.loc.gov/MARC21/slim'}
etree.register_namespace("marc", MARC_NS.get("marc"))

def check_init_triplestore():
    """Checks size of triplestore, loads Alliance ttl if empty"""
    result = requests.post(config.TRIPLESTORE_URL,
        data={"query": "SELECT (count(*) as ?count) WHERE {   ?s ?p ?o . }",
              "format": "json"})
    bindings = result.json().get("results").get('bindings')
    count = int(bindings[0].get("count").get("value"))
    if count < 1:
        with open(os.path.join(PROJECT_BASE, "custom/alliance.ttl")) as fo:
            requests.post(config.TRIPLESTORE_URL,
                data=fo.read(),
                headers={"Content-Type": "text/turtle"}) 

def iii_minter(opac_url, marc_xml):
    field907a = marc_xml.find("marc:datafield[@tag='907']/marc:subfield[@code='a']", 
        MARC_NS)
    bib_id = field907a.text[1:-1]
    return rdflib.URIRef(opac_url.format(bib_id))

def summon_minter(discovery_url, marc_xml):
    field001 = marc_xml.find("marc:controlfield[@tag='001']", MARC_NS)
    if field001 is None:
        return discovery_url.format("invalid_{0}".format(uuid.uuid1()))
    return rdflib.URIRef(discovery_url.format(field001.text))

    
def cc_minter(marc_xml):
    return iii_minter("https://tiger.coloradocollege.edu/record={0}", marc_xml)

def cu_minter(marc_xml):
    return iii_minter("http://libraries.colorado.edu/record={0}", marc_xml)

def suny_buff_minter(marc_xml):
    return summon_minter(
        "http://buffalostate.summon.serialssolutions.com/search?id=FETCHMERGED-buffalostate_catalog_{0}",
        marc_xml)
    
@click.command()
@click.argument('filepath')
@click.argument('institution_iri')
@click.option('--size', default=5000)
@click.option('--offset', default=0)
@click.option('--ils_minter')
@click.option('--output_file', default=None)
def process_xml(filepath,
    institution_iri,
    size,
    offset,
    ils_minter,
    output_file):
    """Processes a MARC XML file using Python standard ElementTree iterparse to
    avoid memory issues with lxml etree iterparse, each MARC XML is converted 
    using LOC's <https://github.com/lcnetdev/marc2bibframe2> to BF 2.0 RDF XML
    which is then preprocessed to convert URLs of main Instance and Items into
    SEO friendly URLs along with additional triples that are added with the 
    BF Instance and BF Item RML processors."""
    logging.getLogger('rdflib').setLevel(logging.CRITICAL)
    transform = lxml.etree.XSLT(lxml.etree.parse(config.MARC2BIBFRAME_XSL))
    institution_iri = rdflib.URIRef(institution_iri)
    ils_minter = getattr(sys.modules[__name__], ils_minter)

    instance_processor = processor.XMLProcessor(
        rml_rules=[os.path.join(PROJECT_BASE, 
                       "custom/rml-alliance-instance.ttl"),
                   os.path.join(PROJECT_BASE, 
                       "bibcat/rdfw-definitions/rml-bibcat-base.ttl")],
        version=BIBCAT_VERSION,
        namespaces=MARC_NS)
    item_processor = processor.XMLProcessor(
        rml_rules=os.path.join(PROJECT_BASE, "custom/rml-alliance-item.ttl"),
        institution_iri=institution_iri,
        namespaces=MARC_NS)
    counter, master_graph = 0, None
    start = datetime.datetime.utcnow()
    start_msg = 'Started at {} for {} size {}'.format(start, filepath, size)
    try:
        click.echo(start_msg)
    except io.UnsupportedOperation:
        print(start_msg)
    for action, element in etree.iterparse(filepath):
        if "record" in element.tag:
            if counter < offset:# and counter > 0:
                counter += 1
                continue
            if counter >= offset+size:
                break
            if not counter%10 and counter > 0:
                try:
                    click.echo(".", nl=False)
                except io.UnsupportedOperation:
                    print(".", end="")
            if not counter%100:
                try:
                    click.echo(counter, nl=False)
                except io.UnsupportedOperation:
                    print(counter, end="")
            raw_marc = etree.tostring(element)
            lxml_mrc = lxml.etree.XML(raw_marc)
            bf_xml = transform(lxml_mrc, baseuri="'https://bibcat.coalliance.org/'")
            bf_rdf = rdflib.Graph().parse(data=lxml.etree.tostring(bf_xml))
            preprocessor = AlliancePreprocessor(
                bf_rdf,
                element,
                institution_iri)
            instance_iri, item_iris = preprocessor.run()
            ils_url = ils_minter(element)
            instance_processor.run(element,
                instance_iri=instance_iri)
            bf_rdf += instance_processor.output
            for item in item_iris:
                item_processor.run(element,
                    item_iri=item,
                    institution_iri=institution_iri,
                    ils_url=ils_url)
                bf_rdf += item_processor.output
        
            try:
                raw_turtle = bf_rdf.serialize(format='turtle')
            except:
                msg = "Error with {}".format(counter)
                try:
                    click.echo(msg)
                except io.UnsupportedOperation:
                    print(msg)
                date_stamp = datetime.datetime.utcnow()
                error_filepath = os.path.join(PROJECT_BASE, 
                    "errors/bf-{}-{}.xml".format(
                        date_stamp.toordinal(),
                        counter))
                with open(error_filepath, "wb+") as fo: 
                    fo.write(bf_rdf.serialize())
                continue 
            result = requests.post(config.TRIPLESTORE_URL,
                data=raw_turtle,
                headers={"Content-Type": "text/turtle"})
            if output_file is not None:
                if master_graph is None:
                    master_graph = bf_rdf
                else:
                    master_graph += bf_rdf
            counter += 1
    if output_file is not None:
        with open(output_file, "wb+") as fo:
            fo.write(master_graph.serialize(format='turtle', encoding='utf-8'))
    end = datetime.datetime.utcnow()
    end_msg = "Finished at {}, total time={} mins".format(
        end, 
        (end-start).seconds / 60.0)
    try:
        click.echo(end_msg)
    except io.UnsupportedOperation:
        print(end_msg)

if __name__ == "__main__":
    check_init_triplestore()
    process_xml()
