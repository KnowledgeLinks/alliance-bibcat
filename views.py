import markdown
import re
import smtplib
import json
import urllib

from elasticsearch import Elasticsearch
from flask import Flask, jsonify, render_template, request
from flask.ext.login import current_user
from . import app, login_manager

def cropHighlights(text):
    span = 75
    highlightx = re.compile(r"(\<em\>)(.+?)(\</em\>)")
    sentencex = re.compile(r"[\!\.\?]\s")
    hightlights = highlightx.finditer(text)
    returnText = ""
    
    for highlight in highlights:
        if hightlight.start()<span:
            trimStart = 0
        if len(text)-highlight.end()<span:
            trimEnd = 0
        
    bSentence = sentencex.finditer(text[:highlight.start()])
    #for s in bSentence:
        
def send_contact(form):
    FROM = request.form['email']
    TO = ["jermnelson@gmail.com"]
    SUBJECT = "COVER Feedback for Becoming a Lean Library"
    TEXT = "Comment from {} about Cover-{}:\n\n{}".format(
        request.form['email'],
        request.form['comment'],
        request.fomr['cover_id'])
    message = """\From: {}\nTo: {}\nSubject: {}\n\n{}""".format(
        FROM,
        ",".join(TO),
        SUBJECT,
        TEXT)
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.ehlo()
        server.starttls()
        server.login(app.config.get("GMAIL_USER"), app.config.get("GMAIL_PWD"))
        server.sendmail(FROM, TO, message)
        server.close()
    except:
        print("ERROR {}".format(sys.exc_info()))
        return False
    return True

@app.route("/badges$")
@app.route("/badges/<action>")
def badges(action="about"):
    return render_template("badges/{}.html".format(action))


@app.route("/book")
@app.route("/book/<chapter>")
@app.route("/book/<chapter>/<page>")
def book(chapter=None, page=None):
    if not chapter:
        return render_template("book/index.html")
    if not page:
        return render_template("book/{}/index.html".format(chapter))
    return "In Book chapter={} page={}".format(chapter, page)

@app.route('/searchbook.html', methods=['POST', 'GET'])
def search():
    """Renders to a search results page listing chapter 
    page and paragraph of the searched for words

    Search view for the application"""
    es = Elasticsearch("http://localhost:9200")
    phrase = request.args.get('q')
    doc_type, results = None, []
    es_dsl = {
        "query": {},
        "highlight": {}
    }
    es_dsl['query']['match'] =  {"content": phrase}
    es_dsl['highlight'] = {"fields" : {"content" : {}}}
    print("keys---",request.form.keys())
    result = es.search(
        body=es_dsl,
        size=50, 
        index='book')
    #print(json.dumps(result.get('hits').get('hits'),indent=2))
    return render_template(
        "search.html",
        searchList=result.get('hits').get('hits'),
        searchPhrase=phrase)
    
@app.route("/research")
def research():
    return render_template(
        "research.html")

@app.route("/")
def home():
    print("Current user is {}".format(current_user))
    return render_template(
        "index.html")
