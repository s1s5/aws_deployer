# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import argparse
import os
import subprocess
import random
import time

from fabric.state import env
from fabric.api import sudo, run, hide

from . import daemon
from . import over_ssh

env.forward_agent = True
env.use_ssh_config = True


class DockerTunnelDaemon(daemon.Daemon):

    def __init__(self, *args, **kwargs):
        self.hostname = kwargs.pop('hostname')
        super(DockerTunnelDaemon, self).__init__(*args, **kwargs)
        self.__started = False

    def startup(self):
        print(self.__started)
        if self.__started:
            return

        env.host_string = self.hostname
        self.tmp_dir = os.path.join('/tmp', 'docker-{}'.format(os.environ['USER']))
        if not os.path.exists(self.tmp_dir):
            os.mkdir(self.tmp_dir)
        with hide('running', 'stdout'):
            sudo("true")
            run("mkdir -p {}".format(self.tmp_dir))
            run("chmod 700 {}".format(self.tmp_dir))
        subprocess.call(['chmod', '700', self.tmp_dir])

        self.local_basename = over_ssh.get_base_filename(True)
        self.remote_basename = over_ssh.get_base_filename(False)

        self.port = random.randint(10000, 65535)
        self.sock_name = os.path.join(self.tmp_dir, '{}.sock'.format(self.hostname))
        self.cert_file = os.path.join(self.tmp_dir, '{}.crt'.format(self.hostname))
        over_ssh.exchange_certs(self.cert_file)

        self.__started = True
        print("started")

    def daemonize(self):
        self.startup()
        super(DockerTunnelDaemon, self).daemonize()

    def run(self):
        print("run start")
        self.startup()
        print(self.hostname, self.port, self.sock_name, self.cert_file, env['password'])

        kw = {
            'sock': self.sock_name,
            'port': self.port,
            'lpem': '{}.pem'.format(self.local_basename),
            'rpem': '{}.pem'.format(self.remote_basename),
            'remote_host': self.hostname,
            'crt': self.cert_file,
        }
        cmd0 = ["socat", "-t3600", "TCP-LISTEN:{},forever,reuseaddr,fork".format(self.port),
                "EXEC:'ssh {} socat STDIO \"TCP:127.0.0.1:{}\"'".format(self.hostname, self.port)]
        cmd1 = ["socat", "-t3600", "unix-listen:{sock},fork,mode=600".format(**kw),
                "openssl-connect:localhost:{port},cert={lpem},cafile={crt}".format(**kw)]
        cmd2 = (["ssh", "-kTax", self.hostname, "sudo"] +
                (["-S", ] if env['password'] else []) +
                [("socat -t3600 openssl-listen:{port},fork,forever,reuseaddr,cert={rpem},cafile={crt} "
                  "UNIX-CONNECT:/var/run/docker.sock").format(**kw)])

        p0 = subprocess.Popen(cmd0)
        p1 = subprocess.Popen(cmd1)
        p2 = subprocess.Popen(cmd2, stdin=subprocess.PIPE)

        if env['password']:
            p2.stdin.write(env['password'] + '\n')
            p2.stdin.flush()

        print("entering loop")
        try:
            while True:
                time.sleep(0.1)
        except:
            pass
        p0.terminate()
        p1.terminate()
        p2.terminate()


def main():
    """
    The application entry point
    """
    parser = argparse.ArgumentParser(
        # prog='PROG',
        description='Daemon runner',
        epilog="That's all folks"
    )

    parser.add_argument(
        '-H', '--hostname')
    parser.add_argument(
        'operation',
        metavar='OPERATION',
        type=str,
        help='Operation with daemon. Accepts any of these values: start, stop, restart, status',
        choices=['start', 'stop', 'restart', 'status', 'test'])

    args = parser.parse_args()
    operation = args.operation

    # Daemon
    daemon = DockerTunnelDaemon(pidfile='/tmp/tunnel.pid', stdout="/tmp/tunnel.stdout",
                                stderr="/tmp/tunnel.stdout",
                                hostname=args.hostname)
    daemon.execute(operation)


if __name__ == '__main__':
    main()

