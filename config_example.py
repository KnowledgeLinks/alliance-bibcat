"""OMNIBUS CONFIG file for KnowlegeLinks.io applications"""
# enter a secret key for the flask application instance
import os

SECRET_KEY = "enter_a_secret_key_here"

# Enter the root file path for where the RDF defintioins are stored. The
# application will search this path for all folders titled 'rdfw-definitions'
# and load those files into the RDF_DEFINITIONS triplestore.
#! If left blank the application will use the file path that originally called
#! RdfConfigManager
RDF_DEFINITION_FILE_PATH = os.path.join(os.path.expanduser("~"),
                                        "git", "rdfframework")

# Path to where local data files are stored, as python sees the file path.
# This variable is paired with the 'container_dir' in a TRIPLESTORE declaration.
# Without this linkage the only way to send a file through to the triplestore
# is via a REST call that does not work well for large and large numbers of
# files
#! The docker container should be volume mapped to this location.
#! Example: -v {python_dir}:{docker_container_dir}
#!          -v /home/username/local_data:/local_data
LOCAL_DATA_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                               'data')
CACHE_DATA_PATH = os.path.join(os.path.expanduser("~"), 'cache_data')
RML_DATA_PATH = os.path.join(os.path.expanduser("~"),
                             'git',
                             'bibcat',
                             'bibcat',
                             'maps')
# URL used in generating IRIs
BASE_URL = "http://bibcat.org/"

# url to elasticsearch
ES_URL = "http://localhost:9200"

# Declaration for the triplestore that stores data for the application
DATA_TRIPLESTORE = {
    "vendor": "blazegraph",
    "url": "http://localhost:9999/blazegraph",
    # The 'container_dir' is linked with the LOCAL_DATA_PATH declaration
    # This is how the triplestore sees the file path.
    "container_dir": "alliance_data",
    "local_directory": LOCAL_DATA_PATH,
    "namespace": 'kb', #"alliance", # "kb",
    "graph": "bf:nullGraph",
    "namespace_params": {"quads": True}
}

# Declaration for the triplestore storing the rdf vocab and rdfframework files
# that define the applications classes, forms, and APIs
DEFINITION_TRIPLESTORE = {
    "vendor": "blazegraph",
    "url": "http://localhost:9999/blazegraph",
    "container_dir": "local_data",
    "graph": "<http://knowledgelinks.io/ns/application-framework/>",
    "namespace": "rdf_defs",
    "namespace_params": {"quads": True}
}

# Declaration for the triplestore storing the rdf vocab and rdfframework files
# that define the applications classes, forms, and APIs
RML_MAPS_TRIPLESTORE = {
    "vendor": "blazegraph",
    "url": "http://localhost:9999/blazegraph",
    "container_dir": "local_data",
    "namespace": "rml_maps",
    "namespace_params": {"quads": True}
}

REPOSITORY_URL = "http://localhost:8080/rest"

# Dictionary of web accessibale datasets
DATASET_URLS = {
    "loc_subjects_skos.nt.gz": "http://id.loc.gov/static/data/authoritiessubjects.nt.skos.gz",
    "marc_relators_nt": "http://id.loc.gov/static/data/vocabularyrelators.nt.zip",
    "bibframe_vocab_rdf": "http://id.loc.gov/ontologies/bibframe.rdf"
}

DEFAULT_RDF_NS = {
    "kds": "http://knowledgelinks.io/ns/data-structures/",
    "kdr": "http://knowledgelinks.io/ns/data-resources/",
    "bf": "http://id.loc.gov/ontologies/bibframe/",
    "dpla": "http://dp.la/about/map/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "loc": "http://id.loc.gov/authorities/",
    "mods": "http://www.loc.gov/mods/v3",
    "es": "http://knowledgelinks.io/ns/elasticsearch/",
    "edm": "http://www.europeana.eu/schemas/edm/",
    "schema": "http://schema.org/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "ore": "http://www.openarchives.org/ore/terms/",
    "owl": "http://www.w3.org/2002/07/owl#",
    "void": "http://rdfs.org/ns/void#",
    "dcterm": "http://purl.org/dc/terms/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dbo": "http://dbpedia.org/ontology/",
    "dbp": "http://dbpedia.org/property/",
    "dbr": "http://dbpedia.org/resource/",
    "m21": "<http://knowledgelinks.io/ns/marc21/>",
    "acl": "<http://www.w3.org/ns/auth/acl#>",
    "bd": "<http://www.bigdata.com/rdf#>",
    "relator": "http://id.loc.gov/vocabulary/relators/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "mads": "<http://www.loc.gov/mads/rdf/v1#>"
}

# The name used the site
SITE_NAME = "DPLA-SERVICE-HUB"

# Organzation information for the hosting org.
ORGANIZATION = {
    "name": "knowledgeLinks.io",
    "url": "http://knowledgelinks.io/",
    "description": ""
}

# Default data to load at initial application creation
FRAMEWORK_DEFAULT = []

DATE_FORMAT = {
    "python": "",
    "json": ""
}
