# coding: utf-8
from __future__ import unicode_literals
from __future__ import absolute_import

import os
import time

from fabric.decorators import task
from fabric.state import env
from fabric.utils import puts

from . import over_ssh
from .over_ssh import create_tls_cert  # NOQA
from . import compose_tools as compose  # NOQA


@task
def sock(sock_name=None):
    if sock_name is None:
        sock_name = '{}.sock'.format(env['host_string'])
    with over_ssh.DockerProxy(
            env['host_string'],
            os.path.basename(os.getcwd()), sock_name=sock_name) as proxy:
        puts('created socket={}, registry={}'.format(proxy.sock, proxy.local_registry))
        puts('check following command')
        puts(' - remote docker command')
        puts('docker -H {} images'.format(proxy.sock))
        puts(' - to push image')
        puts('docker tag <image> {}/<image_tag>'.format(proxy.local_registry))
        puts('docker push {}/<image_tag>'.format(proxy.local_registry))
        puts('docker -H {} pull {}/<image_tag>'.format(proxy.sock, proxy.remote_registry))
        puts('Please Ctrl+C when exit')
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            pass


@task
def ps(*args, **kw):
    """ps """
    with over_ssh.DockerProxy(
            env['host_string'],
            os.path.basename(os.getcwd())) as proxy:
        for container in proxy.remote_client.containers.list():
            print container


@task
def images(*args, **kw):
    """images """
    with over_ssh.DockerProxy(
            env['host_string'],
            os.path.basename(os.getcwd())) as proxy:
        for image in proxy.remote_client.images.list():
            print image


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


@task
def execute(*functions):
    with over_ssh.DockerProxy(
            env['host_string'],
            os.path.basename(os.getcwd())) as proxy:
        for func in functions:
            func(proxy)
