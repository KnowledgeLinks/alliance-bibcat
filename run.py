import os
import re
import sys
import argparse
import requests
from flask import abort, Flask, g, jsonify, redirect, render_template, \
        request, url_for, Response, send_file, json
from flask.ext.login import LoginManager, login_user, login_required, \
    logout_user, make_secure_token, current_user
#! Insert path to RdfFramework package
sys.path.append(os.path.realpath('./rdfw/'))
from rdfframework.security import User 
from rdfframework import get_framework as rdfw
from rdfframework.utilities import cbool, slugify, separate_props
from core.rdfwcoreviews import rdfw_core 
from views import base_site

RDFW_RESET = True

__version_info__ = ('0', '0', '1')
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
    
# register the main site views    
app.register_blueprint(base_site, url_prefix='') 
# register the rdfw core application views 
app.register_blueprint(rdfw_core, url_prefix='') 
# register any additional rdfw modules
   
#Intialize Flask Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "/login"

@login_manager.user_loader
def load_user(user_id):
    ''' This will reload a users details '''    
    loaded_user_obj = User().get_user_obj(user_id)
    if loaded_user_obj:
        return User(loaded_user_obj)
    else:
        return None



def main(args):
    ''' Launches application with passed in Args '''
    global RDFW_RESET
    if cbool(args.get("rdfw_reset",True)):
        RDFW_RESET = True
    else:
        RDFW_RESET = False   
    print("post init in main ", RDFW_RESET) 
    
    # initialize the rdfframework
    rdfw(config=app.config,
         reset=RDFW_RESET,
         root_file_path=os.path.realpath('./'))
    # load default data into the server core
    ctx = app.test_request_context('/')
    with ctx:
        rdfw().load_default_data()
    host = '0.0.0.0'
    port = 8081 # Debug
    app.run(host=host,
            port=port,
            debug=True)
            
if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument(
        '--rdfw-reset',
        default=False,
        help="reset the the application RDF definitions")
    args=vars(parser.parse_args())
    main(args)
   
