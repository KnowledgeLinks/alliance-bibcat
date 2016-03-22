import os
import re
import sys
import requests
from flask import abort, Flask, g, jsonify, redirect, render_template, request
from flask import url_for, Response, send_file
from flask.ext.login import LoginManager, login_user, login_required, logout_user
from flask.ext.login import make_secure_token, UserMixin, current_user
#! Insert path to RdfFramework package
sys.path.append(os.path.realpath('./rdfw/'))
from rdfframework.security import User 
from rdfframework import get_framework as rdfw

__version_info__ = ('0', '0', '1')
__version__ = '.'.join(__version_info__)
__author__ = "Jeremy Nelson, Mike Stabile"
__license__ = 'MIT'
__copyright__ = '(c) 2016 by Jeremy Nelson and Mike Stabile'

app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('config.py')
app.jinja_env.filters['quote_plus'] = lambda u: quote_plus(u)
    
# initialize the rdfframework
rdfw(config=app.config)
# load default data into the server core
ctx = app.test_request_context('/')
with ctx:
    rdfw().load_default_data()

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

if __name__ == '__main__':
    host = '0.0.0.0'
    port = 8081 # Debug
    app.run(host=host,
            port=port,
            debug=True)
