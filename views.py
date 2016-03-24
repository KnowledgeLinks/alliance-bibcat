"""Flask Blueprint for rdfw core views"""
__author__ = "Jeremy Nelson, Mike Stabile"

import time
import base64
import re
import io
import json
import requests
from urllib.request import urlopen
from werkzeug import wsgi
from flask import Flask, abort, Blueprint, jsonify, render_template, Response, request
from flask import redirect, url_for, send_file, current_app
from flask.ext.login import login_required, login_user, current_user
from flask_wtf import CsrfProtect
from rdfframework import RdfProperty, get_framework as rdfw
from rdfframework.utilities import render_without_request, code_timer, \
        remove_null, pp, clean_iri, uid_to_repo_uri, cbool, make_list
from rdfframework.forms import rdf_framework_form_factory 
from rdfframework.api import rdf_framework_api_factory, Api
from rdfframework.security import User

base_site = Blueprint("base_site", __name__,
                       template_folder="templates")
base_site.config = {}

#from flask import current_app as app

'''ctx = app.test_request_context('/')
with ctx:'''
#app = Flask(__name__)
#login_manager = app.login_manager

@base_site.route("/")
def home():
    print("Current user is {}".format(current_user))
    return render_template(
        "index.html")

@base_site.route("/tester.html")
def home2():
    print("Current user is {}".format(current_user))
    return current_app.login_manager.unauthorized() 
        
from run import login_manager
