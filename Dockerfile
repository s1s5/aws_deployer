# FROM ubuntu:16.04
# ENV LANG ja_JP.UTF-8
# RUN apt-get update && \
#     apt-get install -y python2.7 libffi-dev libssl-dev && \
#     apt-get install -y git python-pip locales language-pack-ja && \
#     dpkg-reconfigure -f noninteractive locales && \
#     update-locale LANG=${LANG} && \
#     apt-get upgrade -y && \
#     apt-get clean && \
#     rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/*
# RUN ln -s /usr/lib/python2.7/lib-dynload/datetime.x86_64-linux-gnu.so /usr/lib/python2.7/lib-dynload/datetime.so
FROM python:2.7-alpine
RUN apk add --update alpine-sdk libffi-dev openssl-dev bash
# FROM ubuntu:16.04
# ENV LANG ja_JP.UTF-8
# RUN apt-get update && \
#     apt-get install -y python2.7 libffi-dev libssl-dev && \
#     apt-get install -y git python-pip locales language-pack-ja && \
#     apt-get install -y docker.io socat && \
#     dpkg-reconfigure -f noninteractive locales && \
#     update-locale LANG=${LANG} && \
#     apt-get upgrade -y && \
#     apt-get clean && \
#     rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/*
RUN pip install --upgrade pip
RUN pip install setuptools virtualenvwrapper

RUN mkdir -p /opt/
ADD ./docker_startup.sh /opt
ADD requirements.txt /opt/
RUN pip install -U -r /opt/requirements.txt
RUN mkdir -p /app/
ADD ./ /app/
RUN mkdir -p /opt/
CMD ["/bin/bash", "/opt/docker_startup.sh"]
