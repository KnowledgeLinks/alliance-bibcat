# BIBCAT Base Image
FROM python:3.5.1
MAINTAINER Jeremy Nelson <jermnelson@gmail.com>

# Set environmental variables
ENV BIBCAT_HOME /opt/bibcat
ENV NGINX_HOME /etc/nginx

# Update Ubuntu and install Python 3 setuptools, git and other
# packages
RUN apt-get update && apt-get install -y && \
    apt-get install -y python3-setuptools &&\
    apt-get install -y git &&\
    apt-get install -y  nginx &&\
    apt-get install -y python3-pip &&\
    git clone https://github.com/KnowledgeLinks/BIBCAT2.git $BIBCAT_HOME &&\
    cd $BIBCAT_HOME &&\
    pip3 install -r requirements.txt

RUN cd $BIBCAT_HOME    

