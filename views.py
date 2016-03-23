import markdown
import re
import smtplib
import json
import urllib

from elasticsearch import Elasticsearch
from flask import Flask, jsonify, render_template, request
from flask.ext.login import current_user
from . import app
#from flask import current_app as app

'''ctx = app.test_request_context('/')
with ctx:'''
#app = Flask(__name__)
login_manager = app.login_manager

@app.route("/")
def home():
    print("Current user is {}".format(current_user))
    return render_template(
        "index.html")
