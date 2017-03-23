FROM ubuntu:16.04
ENV LANG ja_JP.UTF-8
RUN apt-get update && \
    apt-get install -y python2.7 libffi-dev libssl-dev && \
    apt-get install -y git python-pip locales language-pack-ja && \
    apt-get install -y docker.io socat && \
    dpkg-reconfigure -f noninteractive locales && \
    update-locale LANG=${LANG} && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/*
RUN pip install --upgrade pip
RUN pip install setuptools virtualenvwrapper

ADD ./docker_startup.sh /opt
ADD requirements.txt /opt/
RUN pip install -U -r /opt/requirements.txt
RUN mkdir -p /app/
ADD ./ /app/
RUN mkdir -p /opt/
CMD ["/bin/bash", "/opt/docker_startup.sh"]
