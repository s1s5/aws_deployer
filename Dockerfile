FROM python:2.7
RUN pip install --upgrade pip
ADD ./docker_startup.sh /opt
ADD requirements.txt /opt/
RUN pip install -U -r /opt/requirements.txt
RUN mkdir -p /app/
ADD ./ /app/
RUN mkdir -p /opt/
CMD ["/bin/bash", "/opt/docker_startup.sh"]
