__author__ = "Jeremy Nelson"

import click
import datetime
import gzip
import io
import logging
import multiprocessing
import copyreg
import os
import rdflib
import requests
import uuid
import sys 
import xml.etree.ElementTree as etree
import lxml.etree

from io import BytesIO

PROJECT_BASE =  os.path.abspath(os.path.dirname(__file__))
sys.path.append(PROJECT_BASE)
import instance.config as config
from bibcat import clean_uris
import bibcat.rml.processor as processor
import load

BF = rdflib.Namespace("http://id.loc.gov/ontologies/bibframe/")
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
        "http://buffalostate.summon.serialssolutions.com/search?id=FETCHMERGED-buffalostate_catalog_{0}2",
        marc_xml)

#@asyncio.coroutine
#def run_workflow(workflow, element, counter, master_graph, loc_graph):
#    lean, loc = workflow.run(element, counter)
#    master_graph += lean
#    loc_graph += loc

def lxml_elementtree_unpickler(data):
    return lxml.etree.parse(BytesIO(data))

def lxml_xslt_unpickler(data):
    return lxml.etree.XSLT(
        lxml.etree.parse(BytesIO(data)))

def lxml_elementtree_pickler(tree):
    return lxml_elementtree_unpickler, (lxml.etree.tostring(tree),)

def lxml_xslt_pickler(xslt):
    return lxml_xslt_unpickler, (lxml.etree.XSLT(
                                    lxml.etree.parse(BytesIO(xslt))), )



def run_workflow(**kwargs):
    workflow = kwargs.get('workflow')
    raw_xml = kwargs.get('raw')
    counter = kwargs.get('counter')
    logging.getLogger('rdflib').setLevel(logging.CRITICAL)
    record = etree.XML(raw_xml)
    workflow.run(record, counter)
    return workflow.lean_graph, workflow.output_graph
    
def pool_init(queue):
    run_workflow.queue = queue

#copyreg.pickle(lxml.etree._ElementTree,
#    lxml_elementtree_pickler,
#    lxml_elementtree_unpickler)
#copyreg.pickle(lxml.etree.XSLT,
#    lxml_xslt_pickler,
#    lxml_xslt_unpickler)
 
@click.command()
@click.argument('filepath')
@click.argument('institution_iri')
@click.option('--size', default=5000)
@click.option('--offset', default=0)
@click.option('--ils_minter')
@click.option('--marc2bibframe2')
@click.option('--output_file', default=None)
def process_xml(filepath,
    institution_iri,
    size,
    offset,
    ils_minter,
    marc2bibframe2,
    output_file):
    """Processes a MARC XML file using Python standard ElementTree iterparse to
    avoid memory issues with lxml etree iterparse, each MARC XML is converted 
    using LOC's <https://github.com/lcnetdev/marc2bibframe2> to BF 2.0 RDF XML
    which is then preprocessed to convert URLs of main Instance and Items into
    SEO friendly URLs along with additional triples that are added with the 
    BF Instance and BF Item RML processors."""
    logging.getLogger('rdflib').setLevel(logging.CRITICAL)
    counter, master_graph, loc_graph = 0, rdflib.Graph(), rdflib.Graph()
    start = datetime.datetime.utcnow()
    ils_minter = getattr(sys.modules[__name__], ils_minter)
    start_msg = 'Started at {} for {} size {}'.format(start, filepath, size)
    institutional_workflow = AllianceWorkflow(institution=institution_iri,
        ils_minter=ils_minter,
        marc2bibframe2=marc2bibframe2)
    try:
        click.echo(start_msg)
    except io.UnsupportedOperation:
        print(start_msg)
    #queue = multiprocessing.Queue()
    #pool = multiprocessing.Pool(processes=3,
    #    initializer=pool_init,
    #    initargs=(queue,))
        
    for action, element in etree.iterparse(filepath):
        if "record" in element.tag:
            if counter < offset:# and counter > 0:
                counter += 1
                continue
            if counter >= offset+size:
                break
            if not counter%5 and counter >0:
                tasks = []
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
            try:
                lean, loc = institutional_workflow.run(element, counter) 
                if not master_graph:
                    master_graph = lean
                    loc_graph = loc
                else:
                    master_graph += lean
                    loc_graph += loc
            except:
                err_msg = "E{}".format(counter)
                try:
                    click.echo(err_msg, nl=False)
                except io.UnsupportedOperation:
                    print(err_msg, end="")
                continue
            counter += 1
    if output_file is not None:
        with open(output_file, "wb+") as fo:
            fo.write(master_graph.serialize(format='turtle', encoding='utf-8'))
        with gzip.open("{}-loc.gz".format(output_file[:-4]), "wb") as loc_fo:
            loc_fo.write(loc_graph.serialize())



    end = datetime.datetime.utcnow()
    end_msg = "Finished at {}, total time={} mins".format(
        end, 
        (end-start).seconds / 60.0)
    try:
        click.echo(end_msg)
    except io.UnsupportedOperation:
        print(end_msg)

class AllianceWorkflow(object):
    """This class encapsulates a multi-step work-flow"""

    def __init__(self, **kwargs):
        self.institution_iri = rdflib.URIRef(kwargs.get('institution'))
        self.ils_minter = kwargs.get("ils_minter")
        self.base_url = kwargs.get("base_url",
                                   config.BASE_URL)
        self.triplestore_url = kwargs.get("triplestore_url",
                                          config.TRIPLESTORE_URL)
        marc2bibframe2_xslt = kwargs.get("marc2bibframe2")
        if not os.path.exists(marc2bibframe2_xslt):
            raise FileNotFoundError("{} not found".format(marc2bibframe2_xslt))
        self.loc_bf_xslt = lxml.etree.XSLT(
            lxml.etree.parse(marc2bibframe2_xslt))
        self.marc_ns = {'marc': 'http://www.loc.gov/MARC21/slim'}
        self.instance_processor = kwargs.get("instance_processor",
            processor.XMLProcessor(
                rml_rules=['bibcat-base.ttl',
                    os.path.abspath(
                        os.path.join(PROJECT_BASE, "custom/rml-alliance-instance.ttl"))],
                namespaces=self.marc_ns))
        self.item_processor = kwargs.get("item_processor",
            processor.XMLProcessor(
                rml_rules=[os.path.abspath(
                    os.path.join(PROJECT_BASE, "custom/rml-alliance-item.ttl"))]))
        self.lean_processor = processor.SPARQLProcessor(
            rml_rules="bibcat-loc-bf-to-lean-bf.ttl")
        self.record, self.output_graph, self.lean_graph = None, None, None

    def __ils_link__(self):
        ils_url = self.ils_minter(self.record)
        check_exists = requests.get(str(ils_url))
        if check_exists.status_code > 399:
            raise ValueError("{} not found".format(ils_url))
        return ils_url

    def __alliance_dedup__(self):
        processor = load.AlliancePostProcessor(triplestore_url=self.triplestore_url)
        processor.run(self.lean_graph, rdf_classes=[BF.Agent])
        self.lean_graph = processor.output

    def __alliance_updates__(self):
        processor = load.AlliancePreprocessor(
            self.output_graph,
            self.record,
            self.institution_iri,
            self.triplestore_url)
        return processor.run()

    def __ingest_to_triplestore__(self, counter=None):
        if not counter:
            counter = -1
        try:
            raw_turtle = self.lean_graph.serialize(
                    format='turtle')
        except:
            msg = "Error with {}".format(counter)
            try:
                click.echo(msg, nl=False)
            except io.UnsupportedOperation:
                print(msg, end="")
            date_stamp = datetime.datetime.utcnow()
            error_filepath = os.path.join(PROJECT_BASE, 
                "errors/bf-{}-{}.xml".format(
                    date_stamp.toordinal(),
                    counter))
            with open(error_filepath, "wb+") as fo: 
                fo.write(self.lean_graph.serialize())
            raise ValueError("Error with serializing lean_graph to turtle")
        result = requests.post(self.triplestore_url,
            data=raw_turtle,
            headers={"Content-Type": "text/turtle"})
        if result.status_code < 399:
            return True
        else:
            raise ValueError("Ingestion failed")

    def marc2loc_bf(self, record):
        try:
            self.record = lxml.etree.XML(record)
        except ValueError:
            self.record = lxml.etree.XML(etree.tostring(record))
        bf_xml = self.loc_bf_xslt(self.record,
            baseuri="'{}'".format(self.base_url))
        self.output_graph = rdflib.Graph().parse(data=lxml.etree.tostring(bf_xml))

    def __produce_lean__(self):
        self.lean_processor.triplestore = self.output_graph
        self.lean_processor.run()
        self.lean_graph = self.lean_processor.output
        # Register OWL namespace
        self.lean_graph.namespace_manager.bind("owl", rdflib.OWL)
        # Clean any URIs
        clean_uris(self.lean_graph)
       
    def run(self, record, counter):
        """Takes a record and runs workflow to ingest into a RDF 
        triplestore
        
        Args:
            record: String, lxml.etree.Element, etree.Element
        """
        
        # Step one -- run marc2bibframe2 XSLT transform on record
        self.marc2loc_bf(record)

        # Step two -- create Alliance updates including replacing bf:Instance
        # and bf:Item iris with SEO friendly URLs
        instance_iri, item_iris = self.__alliance_updates__()
        
        # Step three: run instance processor with Alliance Instance Processor
        self.instance_processor.run(self.record, instance_iri=instance_iri)
        self.output_graph += self.instance_processor.output

        # Step four: generates link to ILS or Discovery layer
        ils_url = self.__ils_link__()

        # Step five: run Alliance Item processor on each  bf:item
        for item in item_iris:
            self.item_processor.run(
                self.record,
                item_iri=item,
                institution_iri=self.institution_iri,
                ils_url=ils_url)
            self.output_graph += self.item_processor.output

        # Step six: run LOC BIBFRAME to BIBFRAME Lean for ingestion into
        # production triplestore
        self.__produce_lean__()

        # Step seven: run Alliance Deduplication on Lean Graph 
        self.__alliance_dedup__()

        # Step eight: Ingest Lean Graph into triplstore
        self.__ingest_to_triplestore__(counter)
        
        return self.lean_graph, self.output_graph
        

def asynco_approach():
    tasks = []
    loop = asyncio.get_event_loop()
    for action, element in etree.iterparse(filepath):
        if "record" in element.tag:
            if counter < offset:# and counter > 0:
                counter += 1
                continue
            if counter >= offset+size:
                break
            if not counter%5 and counter >0:
                loop.run_until_complete(asyncio.gather(*tasks))
                tasks = []
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
            try:
                tasks.append(
                    asyncio.ensure_future(
                        run_workflow(institutional_workflow,
                            element,
                            counter,
                            master_graph,
                            loc_graph)))
                
               # institutional_workflow.run(element, counter)
            except ValueError:
                continue

                            
            counter += 1
    loop.close()


if __name__ == "__main__":
    check_init_triplestore()
    process_xml()
