# coding: utf-8
from __future__ import unicode_literals
from __future__ import absolute_import

import uuid
import subprocess
import os

from docker_tools import over_ssh
from fabric.state import env
from six import print_

env.forward_agent = True
env.use_ssh_config = True


def search_commons(hosts):
    common = hosts[0]
    for i in range(1, len(hosts)):
        host = hosts[i]
        for j in range(min(len(common), len(host))):
            if common[j] != host[j]:
                break
        common = common[:j]
    return common


def create_rc_file(proxy, hosts, fp):
    print_('if [ -e ~/.bash_profile ]; then . ~/.bash_profile; fi', file=fp)
    print_('if [ -e ~/.bashrc ]; then . ~/.bashrc; fi', file=fp)

    print_("alias docker_localhost='docker -H unix:///var/run/docker.sock'", file=fp)
    print_("alias dl='docker -H unix:///var/run/docker.sock'", file=fp)
    print_('docker_localhost(dl) -> [localhost]')
    print_(r'export ORG_PS1="$PS1"', file=fp)
    if len(hosts) == 1:
        print_(r'export PS1="(->{}) $PS1"'.format(hosts[0]), file=fp)
        print_('export DOCKER_HOST={}'.format(proxy.getSock(hosts[0])), file=fp)
        print_('docker -> [{}]'.format(hosts[0]))
    else:
        common = search_commons(hosts)
        print_(r'export PS1="(rdocker) $PS1"', file=fp)
        for index, host in enumerate(hosts):
            print_("alias docker_{}='docker -H {}'".format(host[len(common):], proxy.getSock(host)), file=fp)
            print_("alias d{}='docker -H {}'".format(host[len(common):], proxy.getSock(host)), file=fp)
            print_('[{}] docker_{}(d{}) -> [{}]'.format(index, host[len(common):], host[len(common):], host))
        print_('function sw () {', file=fp)
        print_('    case $1 in', file=fp)
        for index, host in enumerate(hosts):
            sock = proxy.getSock(host)
            ps1 = 'export PS1="(->{})$ORG_PS1"'.format(host)
            print_('        {}) export DOCKER_HOST="{}"'.format(index, sock), file=fp)
            print_('            {} ;;'.format(ps1), file=fp)
            print_('        {}) export DOCKER_HOST="{}"'.format(host[len(common):], sock), file=fp)
            print_('            {} ;;'.format(ps1), file=fp)
            print_('        {}) export DOCKER_HOST="{}"'.format(host, sock), file=fp)
            print_('            {} ;;'.format(ps1), file=fp)
        print_('            esac', file=fp)
        print_('}', file=fp)


def main(args):
    hosts = args
    proxy = over_ssh.DockerMultipleProxy(
        [str(x) for x in hosts],
        "registry_default", sleep_time=1)
    proxy.start()
    tmp_filename = '/tmp/{}.sh'.format(uuid.uuid4().hex)

    with open(tmp_filename, 'w') as fp:
        create_rc_file(proxy, hosts, fp)
    # print tmp_filename
    # print open(tmp_filename, 'r').read()
    try:
        subprocess.call('/bin/bash --rcfile {}'.format(tmp_filename), shell=True)
    finally:
        proxy.end()
        os.remove(tmp_filename)


def __entry_point():
    import argparse
    parser = argparse.ArgumentParser(
        description=u'',  # プログラムの説明
    )
    parser.add_argument("args", nargs="*")

    main(parser.parse_args().args)


if __name__ == '__main__':
    __entry_point()
