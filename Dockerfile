# Dockerfile for BIBCAT 
FROM python:3.5.1
MAINTAINER Jeremy Nelson <jermnelson@gmail.com>

# Set environmental variables
ENV BIBCAT_GIT https://github.com/KnowledgeLink/alliance-bibcat.git
ENV BIBCAT_HOME /opt/alliance-bibcat/

# Update and install Python3 setuptool and pip
RUN apt-get update && apt-get install -y && \
   apt-get install -y git && \
#  apt-get install -y python3-setuptools &&\
#  apt-get install -y python3-pip && \
#  apt-get install -y supervisor && \
  apt-get install -y cron

# Clone master branch of BIBCAT repository,
# setup Python env, run 
RUN git clone  https://github.com/KnowledgeLinks/alliance-bibcat.git /opt/alliance-bibcat && \
    cd /opt && \
    ls -ltra && \
    cd $BIBCAT_HOME && \
    git submodule init && \
    git submodule update && \
    mkdir instance && \
    mkdir cache && \
    pip3 install -r requirements.txt
  #chmod +x $DIGCC_HOME/search/poll.py && \
  #crontab crontab.txt

COPY instance/config.py $BIBCAT_HOME/instance/config.py
EXPOSE 5000

WORKDIR $BIBCAT_HOME
CMD ["nohup", "uwsgi", "-s", "0.0.0.0:5000", "-w", "simple:app"]
#CMD ["/usr/bin/supervisord"]
