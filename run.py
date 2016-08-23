import os
import logging
import inspect
import sys
import argparse
from urllib.parse import quote_plus
from flask import  Flask, json, url_for
from flask.ext.login import LoginManager
from flask.ext.mail import Mail, Message
#! Insert path to RdfFramework package
sys.path.append(os.path.realpath('./rdfw/'))
from rdfframework.security import User
from rdfframework import get_framework as rdfw
from rdfframework.utilities import cbool, slugify, separate_props
from core.rdfwcoreviews import rdfw_core
from bibcat.rdfwbibcatviews import bibcat
from views import base_site
from werkzeug.wsgi import DispatcherMiddleware

RDFW_RESET = True
SERVER_CHECK = True

__version_info__ = ('0', '1', '0')
__version__ = '.'.join(__version_info__)
__author__ = "Jeremy Nelson, Mike Stabile"
__license__ = 'MIT'
__copyright__ = '(c) 2016 by Jeremy Nelson and Mike Stabile'

app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('config.py')
app.jinja_env.filters['quote_plus'] = lambda u: quote_plus(u)
app.jinja_env.filters['slugify'] = lambda u: slugify(u)
app.jinja_env.filters['pjson'] = lambda u: json.dumps(u, indent=4)
app.jinja_env.filters['is_list'] = lambda u: isinstance(u, list)
app.jinja_env.filters['separate_props'] = lambda u: separate_props(u)
app.jinja_env.filters['app_item'] = lambda u: rdfw().app.get(u,str(u))
app.jinja_env.filters['app_url'] = \
        lambda u: (url_for('rdfw_core.base_path') + rdfw().app.get(u,str(u))).replace("//","/")

# register the main site views
app.register_blueprint(base_site, url_prefix='')
# register the rdfw core application views
app.register_blueprint(rdfw_core, url_prefix='')
# register any additional rdfw modules
app.register_blueprint(bibcat, url_prefix='')
# register any additional rdfw modules
mail=Mail(app)
#Intialize Flask Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "/login"

logging.basicConfig(level=logging.DEBUG)
logging_off = logging.getLogger("requests")
logging_off.setLevel(logging.WARN)

parent_app = DispatcherMiddleware(
    app,
    {"/two": app})

@app.route("/emailtest")
def index():
	msg = Message(
              'Test of emailer',
	       sender='emailer.knowledgelinks.io@gmail.com',
	       recipients=
               ['Jeremy.Nelson@coloradocollege.edu','jermnelson@gmail.com'])
	msg.body = "Testing emailer"
	mail.send(msg)
	return "Sent"


@login_manager.user_loader
def load_user(user_id):
    ''' This will reload a users details '''
    loaded_user_obj = User().get_user_obj(user_id)
    if loaded_user_obj:
        return User(loaded_user_obj)
    else:
        return None

def setup(args={}):
    "Setup environment"
    ''' Launches application with passed in Args '''
    global RDFW_RESET
    global SERVER_CHECK
    # test to see if a forced definition reset is required
    if cbool(args.get("rdfw_reset",True)):
        RDFW_RESET = True
    else:
        RDFW_RESET = False
    # test to see if the server status check should be skipped
    if cbool(args.get("server_check",True)):
        SERVER_CHECK = True
    else:
        SERVER_CHECK = False
    # initialize the rdfframework
    rdfw(config=app.config,
         reset=RDFW_RESET,
         server_check = SERVER_CHECK,
         root_file_path=os.path.realpath('./'))
    # load default data into the server core
    ctx = app.test_request_context('/')
    with ctx:
        rdfw().load_default_data()

def main(args):
    if cbool(args.get("setup_only")):
        setup(args)
    else:
        print("Running standalone")
        setup(args)
        host = '0.0.0.0'
        port = 8081 # Debug
        ssl_context = 'adhoc'
        app.run(host=host,
                port=port,
            #ssl_context=ssl_context,
                debug=True)

if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        '--setup-only',
        default=False,
        help='Run RDF framework setup only')
    arg_parser.add_argument(
        '--rdfw-reset',
        default=False,
        help="reset the the application RDF definitions")
    arg_parser.add_argument(
        '--server-check',
        default=True,
        help="test to see it semanitc server is running")
    app_args = vars(arg_parser.parse_args())
    main(app_args)

#! Trying to force loading for Docker container
setup()
