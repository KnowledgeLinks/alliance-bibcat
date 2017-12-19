import datetime
import urllib.request
import os
import sys

PROJECT_BASE =  os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_BASE, 'data')

sys.path.append(PROJECT_BASE)
try:
    import instance.config as config
except ImportError:
    try:
        from example_instance import config
    except ImportError:
        config = SimpleNamespace()
        config.TRIPLESTORE_URL = "http://localhost:9999/blazegraph/sparql"

try:
    from rdfframework.connections import Blazegraph
    CONN = Blazegraph(config.TRIPLESTORE_URL)
except ImportError:
    print("INFO: 'rdfframework' not installed")
    CONN = None


def turtles():
    start = datetime.datetime.now()
    print("Loading RDF turtle files for Alliance BIBCAT at {}".format(
                start.isoformat()))
    if CONN:
        CONN.load_directory(file_directory=DATA_DIR,
                            file_extensions=['ttl'],
                            include_subfolders=False,
                            reset=False,
                            use_threading=True)
        CONN.load_data(os.path.join(PROJECT_BASE, "custom", "alliance.ttl"),
                       is_file=True)
    else:
        print("INFO: 'rdfframework' connection not available. Loading with alternate method")
        # Load custom ttl files for institutional metadata for richer
        # context for ttl files in the data directory
        headers = {"Content-type": "text/turtle"}
        with open(os.path.join(PROJECT_BASE, "custom", "alliance.ttl"), "rb") as fo:
            request = urllib.request.Request(url=config.TRIPLESTORE_URL,
                                             data=fo.read(),
                                             headers=headers)
            urllib.request.urlopen(request)
            print("Loaded alliance")
        for directory in ["data"]:
            turtle_path = os.path.join(PROJECT_BASE, directory)
            walker = next(os.walk(turtle_path))
            for filename in walker[2]:
                if not filename.endswith("ttl"):
                    continue
                full_path = os.path.join(turtle_path, filename)
                with open(full_path, "rb") as fo:
                    raw_turtle = fo.read()
                request = urllib.request.Request(
                              url=config.TRIPLESTORE_URL,
                              data=raw_turtle,
                              headers=headers)
                with urllib.request.urlopen(request) as triplestore_response:
                    print("\t{} ingest result {}".format(filename,
                              triplestore_response.read().decode('utf-8')))
    end = datetime.datetime.now()
    print("Finished RDF turtle load at {}, total time {} minutes".format(
               end, (end-start).seconds / 60.0))

if __name__ == '__main__':
    turtles()
