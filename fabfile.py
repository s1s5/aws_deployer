# coding: utf-8
from __future__ import unicode_literals
from __future__ import absolute_import

import re
import getpass

from fabric.decorators import task
from fabric.state import env
from fabric.api import run, sudo, local, put, warn_only  # prompt
from fabric.utils import puts
from fabric.context_managers import shell_env

env.forward_agent = True
env.use_ssh_config = True


@task
def ping():
    """接続テスト"""
    run("echo `hostname` {}".format(env['host_string']))


@task
def setup_aws_ec2(username, id_rsa_pub=None):
    """setup_aws_ec2:<username>でユーザー作成＋devグループの作成、id_rsa.pubの作成を行う。"""
    with warn_only():
        res = sudo("grep -c '^dev:' /etc/group")
    if res.return_code:
        sudo('groupadd dev')
    user_add(username, id_rsa_pub)
    with shell_env(DEBIAN_FRONTEND='noninteractive'):
        sudo('apt update')
        sudo('apt upgrade -y')
        sudo('apt install python2.7 -y', pty=False)


@task
def user_add(username, id_rsa_pub, sudoer=True):
    """user_add:<username>,<id_rsa_pub>でユーザーの作成を行う"""
    with warn_only():
        res = sudo("grep -c '^{}:' /etc/passwd".format(username))
    if res.return_code:
        if id_rsa_pub is None:
            hoststring = re.sub('[^\w\-_\. ]', '_', env['host_string']) + '_'
            local('ssh-keygen -t rsa  -f ~/.ssh/{}id_rsa'.format(hoststring))
            id_rsa_pub = '~/.ssh/{}id_rsa.pub'.format(hoststring)
            id_rsa = '~/.ssh/{}id_rsa'.format(hoststring)
        else:
            id_rsa = '<set your id_rsa path for {}>'.format(id_rsa_pub)

        password = getpass.getpass('Input new password: ')
        sudo('useradd -d /home/{username} -g dev -G admin -s '
             '/bin/bash -p `openssl passwd -1 {password}` {username}'.format(
                 username=username, password=password))
        try:
            sudo('mkdir -p /home/{}'.format(username))
            sudo('mkdir -p /home/{}/.ssh'.format(username))
            put(id_rsa_pub,
                '/home/{}/.ssh/authorized_keys'.format(username),
                use_sudo=True)
            sudo('chmod 700 /home/{}/.ssh'.format(username))
            sudo('chmod 600 /home/{}/.ssh/authorized_keys'.format(username))
            sudo('chown -R {username}:dev /home/{username}'.format(username=username))
            puts('#### add following lines to ~/.ssh/config ####')
            puts('host <host alias>')
            puts('    User {}'.format(username))
            puts('    Hostname {}'.format(env['host_string'].split('@')[-1]))
            puts('    Port 22')
            puts('    IdentityFile {}'.format(id_rsa))
            puts('    IdentitiesOnly yes')
        except:
            sudo('deluser {}'.format(username))
            raise


@task
def user_del(username):
    """user_del:<username> ユーザーの削除"""
    sudo('userdel {}'.format(username))


@task
def setup_nat_instance():
    """AWSのnat instanceの設定をする"""
    sudo('sysctl -w net.ipv4.ip_forward=1')
    sudo('sysctl -p')
    # TODO: あるかどうかチェックして追加しないと・・・
    sudo('/sbin/iptables -t nat -A POSTROUTING -o eth0 -s 0.0.0.0/0 -j MASQUERADE')
    sudo('netfilter-persistent save')
