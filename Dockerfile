# Dockerfile for BIBCAT
FROM python:3.5.1
MAINTAINER Jeremy Nelson <jermnelson@gmail.com>

# Set environmental variables
ENV BIBCAT_GIT https://github.com/KnowledgeLinks/alliance-bibcat.git
ENV BIBCAT_HOME /opt/alliance-bibcat/

# Update and install Python3 setuptool and pip
RUN apt-get update && apt-get install -y && \
  apt-get install -y cron

RUN mkdir $BIBCAT_HOME && cd $BIBCAT_HOME && \
  mkdir instance && mkdir cache


COPY simple.py $BIBCAT_HOME/simple.py
COPY templates/ $BIBCAT_HOME/templates/
COPY requirements.txt $BIBCAT_HOME/requirements.txt
RUN  cd $BIBCAT_HOME && ls -ltra && pip3 install -r requirements.txt
COPY static/ $BIBCAT_HOME/static/
COPY instance/config.py $BIBCAT_HOME/instance/config.py
COPY instance/google*.html $BIBCAT_HOME/templates/
COPY instance/BingSiteAuth* $BIBCAT_HOME/templates/

EXPOSE 5000

WORKDIR $BIBCAT_HOME
CMD ["nohup", "uwsgi", "-s", "0.0.0.0:5000", "-w", "simple:app"]
