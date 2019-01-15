FROM ubuntu:18.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends python python-pip python-dev libssl-dev gcc gosu && \
    apt-get clean && \
    rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python python /usr/bin/python2 10
RUN update-alternatives --install /usr/bin/pip pip /usr/bin/pip2 10
RUN pip install setuptools wheel

RUN mkdir -p /opt/aws_deployer
ADD requirements.txt /opt/aws_deployer/requirements.txt
WORKDIR /opt/aws_deployer
RUN pip install -r requirements.txt

ADD . /opt/aws_deployer
RUN ln -s /opt/aws_deployer/bin/ransible_ /usr/local/bin/ransible
RUN ln -s /opt/aws_deployer/bin/rfab_ /usr/local/bin/rfab

ENTRYPOINT ["/opt/aws_deployer/entrypoint.sh"]
