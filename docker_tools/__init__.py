# coding: utf-8
from __future__ import unicode_literals
from __future__ import absolute_import
from __future__ import print_function

try:
    input = raw_input
except NameError:
    pass

from fabric.decorators import task
from fabric.state import env
from fabric.utils import puts
from fabric.api import local, sudo, warn_only

from . import over_ssh


@task
def sock(sock_name=None):
    """リモート接続用のdocker socketの作成, ソケット名を指定する場合は引数にPATHを入れる
    sock:<sock_name>"""
    if sock_name is None:
        sock_name = '{}.sock'.format(env['host_string'])
    with over_ssh.DockerProxy(
            env['host_string'],
            'deployer', sock_name=sock_name) as proxy:
        puts('created socket={}, registry={}'.format(proxy.sock, proxy.local_registry))
        puts(' - remoteのdockerサーバでコマンド実行')
        puts('docker -H {} images'.format(proxy.sock))
        puts(' - localにあるイメージをremoteにpush')
        puts('docker tag <image> {}/<image_tag>'.format(proxy.local_registry))
        puts('docker push {}/<image_tag>'.format(proxy.local_registry))
        puts('docker -H {} pull {}/<image_tag>'.format(proxy.sock, proxy.remote_registry))
        puts('Please quit or Ctrl+C when exit, waiting for commands on remote docker')
        puts('send <image tag or hash> # <= でimageを送る')
        try:
            while True:
                l = input().strip()
                if l == 'quit':
                    break
                elif l.startswith('send'):
                    image_tag = [x for x in l.split(' ') if x][1]
                    local('docker tag {} {}/tmp'.format(image_tag, proxy.local_registry))
                    local('docker push {}/tmp'.format(proxy.local_registry))
                    local('docker -H {} pull {}/tmp'.format(proxy.sock, proxy.remote_registry))
                    local('docker -H {} tag {}/tmp {}'.format(proxy.sock, proxy.remote_registry, image_tag))
                else:
                    local('docker -H {} {}'.format(proxy.sock, l))
                puts('command "{}" finished!'.format(l))
        except KeyboardInterrupt:
            pass


@task
def ps(*args, **kw):
    """ps """
    with over_ssh.DockerProxy(
            env['host_string'],
            'deployer') as proxy:
        for container in proxy.remote_client.containers.list():
            print(container)


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


@task
def images(*args, **kw):
    """images """
    with over_ssh.DockerProxy(
            env['host_string'],
            'deployer') as proxy:
        for image in proxy.remote_client.images.list():
            print(image)


@task
def run(image_name, *args, **kw):
    """run:<image_name> """
    with over_ssh.DockerProxy(
            env['host_string'],
            'deployer') as proxy:
        image = proxy.remote_client.images.get(image_name)
        proxy.remote_client.containers.run(image, *args, **kw)


@task
def push(image, tag):
    """push:<image_name>,<image_tag> """
    with over_ssh.DockerProxy(
            env['host_string'],
            'deployer') as proxy:
        proxy.push(image, tag)


@task
def execute(*functions):
    with over_ssh.DockerProxy(
            env['host_string'],
            'deployer') as proxy:
        for func in functions:
            func(proxy)


@task
def get_proxy():
    return over_ssh.DockerProxy(
        env['host_string'],
        'deployer')
