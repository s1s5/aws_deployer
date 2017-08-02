# coding: utf-8
from __future__ import unicode_literals
from __future__ import absolute_import
from __future__ import print_function

try:
    input = raw_input
except NameError:
    pass

from fabric.decorators import task
from fabric.api import sudo, warn_only


@task
def clear_images(force=False):
    """clear all images"""
    force_flag = ''
    if force:
        sudo('docker stop `sudo docker ps -q`')
        force_flag = '-f '
    with warn_only():
        sudo('docker rm {}`sudo docker ps -aq`'.format(force_flag))
        sudo('docker rmi {}`sudo docker images -aq`'.format(force_flag))
