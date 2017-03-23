# coding: utf-8
from __future__ import unicode_literals
from __future__ import absolute_import

import os

from fabric.decorators import task
from fabric.state import env

from . import over_ssh
from . import compose_tools as compose  # NOQA


@task
def run(image_name, *args, **kw):
    """run:<image_name> """
    with over_ssh.DockerProxy(
            env['host_string'],
            os.path.basename(os.getcwd())) as proxy:
        image = proxy.remote_client.images.get(image_name)
        proxy.remote_client.containers.run(image, *args, **kw)


@task
def push(image, tag):
    """push:<image_name>,<image_tag> """
    with over_ssh.DockerProxy(
            env['host_string'],
            os.path.basename(os.getcwd())) as proxy:
        proxy.push(image, tag)
