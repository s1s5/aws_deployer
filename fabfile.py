# coding: utf-8
from __future__ import unicode_literals
from __future__ import absolute_import

# import uuid
import re
import getpass
import os
import paramiko

from fabric.decorators import task
from fabric.state import env
from fabric.api import settings, run, sudo, local, put, hide, warn_only, runs_once  # prompt
from fabric.utils import puts
from fabric.context_managers import shell_env
from fabric.contrib.files import append, exists

import docker_tools as docker  # NOQA

env.forward_agent = True
env.use_ssh_config = True


@task
def ping():
    """接続テスト"""
    run("echo `hostname` {}".format(env['host_string']))


@task
@runs_once
def reboot():
    # """リブート"""
    config_file = os.path.join(os.getenv('HOME'), '.ssh/config')
    ssh_config = paramiko.SSHConfig()
    ssh_config.parse(open(config_file, 'r'))

    depends = []
    for i in env['hosts']:
        d = ssh_config.lookup(i)
        l = []
        for j in env['hosts']:
            if j in d.get('proxycommand', ''):
                l.append(j)
        depends.append((i, l))

    root = [x[0] for x in depends if len(x[1]) == 0]
    depends = [x for x in depends if len(x[1])]
    while depends:
        for idx, i in enumerate(depends):
            if not set(i[1]).difference(set(root)):
                root.append(i[0])
                break
        depends.pop(idx)
    with settings(hide('warnings'),
                  warn_only=True, ):
        for node in reversed(root):
            env['host_string'] = node
            sudo("shutdown -r now")


@task
def install_default_packages():
    with hide('stdout'), shell_env(DEBIAN_FRONTEND='noninteractive'):
        sudo('apt update')
        sudo('apt upgrade -y')
        sudo('apt install socat python2.7 -y', pty=False)


@task
def setup_aws_ec2(username, id_rsa_pub=None):
    """setup_aws_ec2:<username>でユーザー作成＋devグループの作成、id_rsa.pubの作成を行う。"""
    with warn_only():
        res = sudo("grep -c '^dev:' /etc/group")
    if res.return_code:
        sudo('groupadd dev')
    if username != '-':
        user_add(username, id_rsa_pub)
    install_default_packages()


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
            if os.path.exists(id_rsa_pub):
                for i in range(100000):
                    id_rsa_pub = '~/.ssh/{}id_rsa.{}.pub'.format(hoststring, i)
                    if not os.path.exists(id_rsa_pub):
                        break
            if os.path.exists(id_rsa):
                for i in range(100000):
                    id_rsa = '~/.ssh/{}id_rsa.{}'.format(hoststring, i)
                    if not os.path.exists(id_rsa):
                        break
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
            puts('#    ProxyCommand  ssh -W %h:%p <gateway>')
        except:
            sudo('deluser {}'.format(username))
            raise


@task
def user_del(username):
    """user_del:<username> ユーザーの削除"""
    sudo('userdel {}'.format(username))


@task
def update_id_rsa_pub(username, id_rsa_pub):
    put(id_rsa_pub,
        '/home/{}/.ssh/authorized_keys'.format(username),
        use_sudo=True)
    sudo('chmod 600 /home/{}/.ssh/authorized_keys'.format(username))
    sudo('chown -R {username}:dev /home/{username}/.ssh/authorized_keys'.format(username=username))


@task
def setup_nat_instance():
    """AWSのnat instanceの設定をする"""
    sudo('sysctl -w net.ipv4.ip_forward=1')
    sudo('sysctl -p')
    # TODO: あるかどうかチェックして追加しないと・・・
    sudo('/sbin/iptables -t nat -A POSTROUTING -o eth0 -s 0.0.0.0/0 -j MASQUERADE')
    sudo('netfilter-persistent save')


@task
def create_swap(size='1G', filename='/swapfile'):
    """swapファイルの作成"""
    if exists(filename):
        puts('Resizing swapsize {}'.format(filename))
        res = run('free | grep Swap')
        work = res.split()
        if work[2] == '0':
            # swap未使用に付き続行
            sudo('swapoff -a')
            sudo('rm {}'.format(filename))
            # もしここで終わる場合は次も必要だけど、リサイズなので
            # sudo("cat /etc/fstab | grep -v 'none swap sw 0 0' > /etc/fstab")
            # TODO:もし既に別の方法で作ったSwapfileがある場合は未対応
        else:
            puts("Swap file is being used.Processing stop.")
            return

    sudo('fallocate -l {} {}'.format(size, filename))
    sudo('chmod 600 {}'.format(filename))
    sudo('mkswap {}'.format(filename))
    sudo('swapon {}'.format(filename))
    # add "{} none swap sw 0 0"
    append('/etc/fstab', "{} none swap sw 0 0".format(filename), use_sudo=True)

@task
def install_warn_to_slack(slack_url="https://hooks.slack.com/services/DUMMY", slack_chanel="#random", watch_disk="/"):
    put("bin/warn_to_slack.sh", "/usr/local/bin", use_sudo=True)
    sudo('chmod +x /usr/local/bin/warn_to_slack.sh')
    # edit crontab
    append('/etc/crontab', '*/30 * * * * root /usr/local/bin/warn_to_slack.sh {} {} {}'.format(slack_url, slack_chanel, watch_disk), use_sudo=True)
