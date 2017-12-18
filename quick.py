import datetime
import urllib.request
import os
import sys

from rdfframework.configuration import RdfConfigManager
from rdfframework.datatypes import RdfNsManager
from rdfframework.utilities import list_files
PROJECT_BASE =  os.path.abspath(os.path.dirname(__file__))
sys.path.append(PROJECT_BASE)
try:
    import instance.config as config
except ImportError:
    try:
        from example_instance import config
    except ImportError:
        config = SimpleNamespace()
        config.TRIPLESTORE_URL = "http://localhost:9999/blazegraph/sparql"

CFG = RdfConfigManager(config=config)

def turtles():
    conn = CFG.data_tstore
    start = datetime.datetime.now()
    print("Loading RDF turtle files for Alliance BIBCAT at {}".format(
               start.isoformat()))

    conn.load_directory(file_directory=os.path.join(PROJECT_BASE, 'data'),
                        file_extensions=['ttl'],
                        include_subfolders=True,
                        reset=False,
                        use_threading=True,
                        method='local')

    conn.load_data(os.path.join(PROJECT_BASE, "custom", "alliance.ttl"),
                   is_file=True)
    end = datetime.datetime.now()
    print("Finished RDF turtle load at {}, total time {} minutes".format(
               end, (end-start).seconds / 60.0))

if __name__ == '__main__':
    turtles()
