"""Loads all RDF Turtle files in custom/ and data/ directories"""
__author__ = "Jeremy Nelson"

import click
import datetime
import logging
import os
import rdflib
import re
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

def clean_subjects(graph):
    """Iterates through all URIRef subjects and attempts to fix any
    issues with URL.

    Args:
        graph(rdflib.Graph): BIBFRAME RDF Graph
    """
    for subject in set([s for s in graph.subjects()]):
        if isinstance(subject, rdflib.URIRef):
            try:
                rdflib.util.check_subject(str(subject))
            except rdflib.exceptions.SubjectTypeError:
                url_sections = urllib.parse.urlparse(str(subject))
                new_url = (url_sections.scheme,
                           url_sections.netloc,
                           urllib.parse.quote(url_sections.path),
                           urllib.parse.quote(url_sections.params),
                           urllib.parse.quote(url_sections.query),
                           urllib.parse.quote(url_sections.fragment))
                new_subject = rdflib.URIRef(
                    str(urllib.parse.urlunparse(new_url)))
                for pred, obj in graph.predicate_objects(subject=subject):
                    graph.remove((subject, pred, obj))
                    graph.add((new_subject, pred, obj)) 
                for subj, pred in graph.subject_predicates(object=subject):
                    graph.remove((subj, pred, subject))
                    graph.add((subj, pred, new_subject))

                    
                    
                
                
def slugify(value):
    """
    Converts to lowercase, removes non-word characters (alphanumerics and
    underscores) and converts spaces to hyphens. Also strips leading and
    trailing whitespace.
    """
    value = re.sub('[^\w\s-]', '', value).strip().lower()
    return re.sub('[-\s]+', '-', value)

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
            clean_subjects(bf_rdf)
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
