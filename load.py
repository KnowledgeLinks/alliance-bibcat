"""Loads all RDF Turtle files in custom/ and data/ directories"""
__author__ = "Jeremy Nelson"

import click
import datetime
import logging
import os
import requests
import rdflib
import re
import sys
import urllib.request

from types import SimpleNamespace
try:
    from lxml import etree
except ImportError:
    import xml.etree.ElementTree as etree

from bibcat import clean_uris, replace_iri, slugify
from bibcat.rml import processor
from bibcat.linkers.deduplicate import Deduplicator

PROJECT_BASE =  os.path.abspath(os.path.dirname(__file__))
sys.path.append(PROJECT_BASE)
try:
    import instance.config as config
except ImportError:
    config = SimpleNamespace()
    config.TRIPLESTORE_URL = "http://localhost:9999/blazegraph/sparql"

processor.NS_MGR.bf = rdflib.Namespace("http://id.loc.gov/ontologies/bibframe/")
processor.NS_MGR.rdf = rdflib.RDF
processor.NS_MGR.rdfs = rdflib.RDFS
processor.NS_MGR.schema = rdflib.Namespace("http://schema.org/")
processor.NS_MGR.owl = rdflib.OWL

# Alliance Preprocessor
PREFIX = """PREFIX bf: <http://id.loc.gov/ontologies/bibframe/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>"""

class AlliancePreprocessor(object):
    MARC_NS = {'marc': 'http://www.loc.gov/MARC21/slim'}

    ALLIANCE_KEY_SPARQL = PREFIX + """
SELECT DISTINCT ?instance
WHERE {{
    ?instance rdf:type bf:Instance .
    ?instance bf:identifiedBy ?ident .
    ?ident rdf:value ?value .
    FILTER(CONTAINS(?value, "{0}"))
}}"""

    ORG_LABEL_SPARQL = PREFIX + """
SELECT DISTINCT ?label
WHERE {{
    <{0}> rdfs:label ?label .
}}"""

    MAX_WORK_TRIPLES_SPARQL = PREFIX + """
SELECT ?work ?count
WHERE {
    ?work rdf:type bf:Work .
    {
        SELECT ?work (count(*) as ?count)
        WHERE {
            ?work ?p ?o .
        }
    }
} ORDER BY DESC(?count) LIMIT 1"""

    MAX_INSTANCE_TRIPLES_SPARQL = PREFIX + """
SELECT ?instance ?count
WHERE {{
    <{work}> bf:hasInstance ?instance .
    {{
        SELECT ?instance (count(*) as ?count)
        WHERE {{
            ?instance ?p ?o .
        }}
    }}
}} ORDER BY DESC(?count) LIMIT 1"""

    WORKS_OF_INSTANCE_SPARQL = PREFIX + """
SELECT DISTINCT ?work
WHERE {{
     <{0}> bf:instanceOf ?work .
}}"""

    def __init__(self, 
        bibframe_graph, 
        marc_xml,
        institutional_iri,
        triplestore_url=config.TRIPLESTORE_URL):
        """Creates an instance of Alliance Preprocessor

        Args:
            bibframe_graph(rdflib.Graph): BIBFRAME RDF graph
            institutional_iri(rdflib.URIRef): Institutional IRI
            marc_xml (etree.XML): MARC XML
            triplestore_url (str): URL to Triplestore URL
        """
        self.graph = bibframe_graph
        self.institutional_iri = institutional_iri
        self.marc_xml = marc_xml
        self.triplestore_url = triplestore_url

    def __get_create_items__(self, instance_iri):
         
        # Create a stub item if none exists
        def item_stub():
            base_iri = str(instance_iri).split("#")[0]
            item_iri = rdflib.URIRef("{}#InstanceStub".format(base_iri))
            self.graph.add((item_iri, 
                            processor.NS_MGR.rdf.type, 
                            processor.NS_MGR.bf.Item))
            self.graph.add((item_iri, 
                            processor.NS_MGR.bf.itemOf, 
                            instance_iri))
            self.graph.add((instance_iri, 
                            processor.NS_MGR.bf.hasItem, 
                            item_iri))
            return item_iri
        item_iris = []
        for row in self.graph.objects(subject=instance_iri,
                                      predicate=processor.NS_MGR.bf.hasItem):
            item_iris.append(row)
        if len(item_iris) < 1:
            item_iris.append(item_stub())
        return item_iris
            

    def __get_canonical_instance__(self):
        """Selects the BF Work with the largest number of triples
        to use as the canonical entity for Instance"""
        result = self.graph.query(
            AlliancePreprocessor.MAX_WORK_TRIPLES_SPARQL)
        if len(result.bindings) < 1:
            raise ValueError("Could not extract max work triples")
        org_work_iri = result.bindings[0]['work']
        # Extract
        instance_result = self.graph.query(
            AlliancePreprocessor.MAX_INSTANCE_TRIPLES_SPARQL.format(
                work=org_work_iri))
        return rdflib.URIRef(instance_result.bindings[0]['instance'])


         

    def __get_works__(self, instance_iri):
        """Attempts to retrieve any existing works from triplestore
        that match Instance IRI

        Args:
            instance_iri(rdflib.URIRef): URI of instance
        """
        works = []
        result = requests.post(self.triplestore_url,
            data={"query": WORKS_OF_INSTANCE_SPARQL.format(instance_iri),
                  "format": "json"})
        if result.status_code > 399:
            return works
        bindings = result.json().get("results").get("bindings")
        if len(bindings) < 1:
            return works
        for row in bindings:
            work_uri = row.get("work").get("value")
            works.append(rdflib.URIRef(work_iri))
        return works
        

    def __match_key__(self):
        match_key = self.marc_xml.find(
            "marc:datafield[@tag='997']/marc:subfield[@code='a']",
            AlliancePreprocessor.MARC_NS)
        if match_key is None:
            return
        result = requests.post(self.triplestore_url,
            data={"query": AlliancePreprocessor.ALLIANCE_KEY_SPARQL.format(
                               match_key.text),
                  "format": "json"})
        if result.status_code > 399:
            return
        bindings = result.json().get("results").get("bindings")
        if len(bindings) < 1:
            return
        instance_url = bindings[0].get("instance").get("value")
        return rdflib.URIRef(instance_url)

    def __mint_instance_iri__(self, instance_iri):
        """Takes an existing BF Instance IRI, attempts to extract Work label 
        for minting a new Alliance IRI and replaces instance_iri for all
        references of in graph.

        Args:
            instance_iri(rdflib.URIRef): URI of Instance
        """
        work_iri = self.graph.value(subject=instance_iri,
                                    predicate=processor.NS_MGR.bf.instanceOf)
        work_label = self.graph.value(subject=work_iri,
                                      predicate=processor.NS_MGR.rdfs.label)
        if work_label is None:
            return
        new_instance_iri = rdflib.URIRef(
            urllib.parse.urljoin(config.BASE_URL,
                                 slugify(work_label)))
        replace_iri(self.graph, instance_iri, new_instance_iri)
        return new_instance_iri

    def __mint_item_iris__(self, item_iris, instance_iri):
        """Takes BF Instance
        and mints a new IRI based on the Instance IRI and the slugged
        Institutional RDFS label

        Args:
            item_iri(lists): List of Item IRIs
            instance_iri(rdflib.URIRef): New instance IRI
        """
        output = []
        sparql = AlliancePreprocessor.ORG_LABEL_SPARQL.format(
            self.institutional_iri)
        result = requests.post(self.triplestore_url,
            data={"query": sparql,
                  "format": "json"})
        if result.status_code > 399:
            return output
        bindings = result.json().get('results').get('bindings')
        if len(bindings) < 1:
            return output
        institution_label = bindings[0].get('label').get('value')
        for i, item_iri in enumerate(item_iris):
            new_url = "{0}/{1}".format(
                instance_iri,
                slugify(institution_label))
            if i > 0:
                new_url += "-{0}".format(i)
            new_item_iri = rdflib.URIRef(new_url)
            replace_iri(self.graph, item_iri, new_item_iri)
            output.append(new_item_iri)
        return output


    def run(self):
        """Runs Alliance Preprocessor"""
        clean_uris(self.graph)
        org_instance_iri = self.__get_canonical_instance__()
        org_item_iris = self.__get_create_items__(org_instance_iri)
        existing_instance_iri = self.__match_key__()
        if existing_instance_iri is not None:
            #for work in self.__get_works__(org_instance_iri):
                # Should replace existing Work IRI
            replace_iri(self.graph, org_instance_iri, existing_instance_iri)
            new_instance_iri = existing_instance_iri
        else:
            new_instance_iri = self.__mint_instance_iri__(org_instance_iri)
        new_item_iris = self.__mint_item_iris__(org_item_iris, new_instance_iri)
        return new_instance_iri, new_item_iris 


class AlliancePostProcessor(Deduplicator):
    """Class de-duplicates and generates IRIs for common BF classes"""

    def __init__(self, **kwargs):
        self.triplestore_url = kwargs.get(
            'triplestore_url', 

           'http://localhost:9999/blazegraph/sparql/')
        kwargs["classes"] = [
            processor.NS_MGR.bf.Topic, 
            processor.NS_MGR.bf.Person, 
            processor.NS_MGR.bf.Organization 
        ]
        super(AlliancePostProcessor, self).__init__(**kwargs) 

  

@click.command()
def turtles():
    """Loads all RDF Turtle files located in the custom and data 
    directories."""
    start = datetime.datetime.now()
    click.echo("Loading RDF turtle files for Alliance BIBCAT at {}".format(
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
                click.echo("\t{} ingest result {}".format(filename, 
                          triplestore_response.read().decode('utf-8')))
    end = datetime.datetime.now()
    click.echo("Finished RDF turtle load at {}, total time {} minutes".format(
               end,
               (end-start).seconds / 60.0))

@click.command()
@click.argument('marc_filepath')
@click.argument('mrc2bf_xsl')
@click.option('--shard_size', default=None, help="Sharded output graphs") 
def marc_xml(marc_filepath, mrc2bf_xsl, shard_size):
    """Takes a MARC XML file and path to LOC's xslt file and transforms 
    to BIBFRAME 2.0 entities. If shard_size is set, shards records and
    saves to output RDF ttl file.

    \b
    Args:
        marc_filepath(str): File path to MARC XML
        mrc2bf_xsl(str): File path to LOC's marc2bibframe.xsl XSLT file
    """
    logging.getLogger('rdflib').setLevel(logging.CRITICAL)
    marc_context = etree.iterparse(marc_filepath)
    xslt_tree = etree.parse(mrc2bf_xsl)
    xslt_transform = etree.XSLT(xslt_tree)
    match_keys, record, total = None, {}, 0
    output_graph = None
    if shard_size is not None:
        shard_size = int(shard_size)
        output_graph = rdflib.Graph()
    start = datetime.datetime.utcnow()
    click.echo("Started transforming MARC to BF at {} for {}".format(
        start.isoformat(),
        marc_filepath))
    for action, elem in marc_context:
        if "record" in elem.tag:
            record = elem
            bf_rdf_xml = xslt_transform(
                record, 
                baseuri="'{0}'".format(config.BASE_URL))
            bf_rdf = rdflib.Graph()
            bf_rdf.parse(data=etree.tostring(bf_rdf_xml))
            clean_uris(bf_rdf)
            if output_graph is not None:
                output_graph += bf_rdf
            total += 1
            if not total%100:
                click.echo(".", nl=False)
            if not total%1000:
                click.echo(record, nl=False)
            if shard_size is not None and not total%shard_size:
                output_file = os.path.join(
                    PROJECT_BASE, 
                    os.path.join("data", "marc-output-{}-{}-{}k.ttl".format(
                       start.strftime("%Y%m%d%H%M%S"),
                        total-shard_size,
                        total)))
                with open(output_file, "wb") as fo:
                    fo.write(output_graph.serialize(format='turtle'))
                output_graph = rdflib.Graph()
                 
            
    end = dateime.datetime.utcnow()
    click.echo("Finished at {} total time {} minutes for {} records".format(
        end.isoformat(),
        (end-start).seconds / 60.0,
        total))



@click.group()
def cli():
    pass

cli.add_command(marc_xml)
cli.add_command(turtles)




if __name__ == '__main__':
    cli()
    #load_turtles()
