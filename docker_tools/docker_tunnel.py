# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import argparse
import os
import subprocess
import random
import time
import signal
from multiprocessing import Process

from fabric.state import env
from fabric.api import sudo, run, hide

from . import daemon
from . import over_ssh

env.forward_agent = True
env.use_ssh_config = True


class DockerTunnelDaemon(daemon.Daemon):

    def __init__(self, *args, **kwargs):
        self.hostname = kwargs.pop('hostname')
        self.tmp_dir = os.path.join('/tmp', 'docker-{}'.format(os.environ['USER']))
        if not kwargs.get('pidfile'):
            kwargs['pidfile'] = os.path.join(self.tmp_dir, '{}.pid'.format(self.hostname))
        if not kwargs.get('stdout'):
            kwargs['stdout'] = os.path.join(self.tmp_dir, 'log')
        if not kwargs.get('stderr'):
            kwargs['stderr'] = os.path.join(self.tmp_dir, 'log')
        self.sock_name = os.path.join(self.tmp_dir, '{}.sock'.format(self.hostname))
        self.cert_file = os.path.join(self.tmp_dir, '{}.crt'.format(self.hostname))

        super(DockerTunnelDaemon, self).__init__(*args, **kwargs)
        self.__started = False

    def startup(self):
        if self.__started:
            return

        env.host_string = self.hostname
        if not os.path.exists(self.tmp_dir):
            os.mkdir(self.tmp_dir)
        with hide('running', 'stdout'):
            run("socat -h")
            sudo("true")
            run("mkdir -p {}".format(self.tmp_dir))
            run("chmod 700 {}".format(self.tmp_dir))
        subprocess.call(['chmod', '700', self.tmp_dir])

        self.local_basename = over_ssh.get_base_filename(True)
        self.remote_basename = over_ssh.get_base_filename(False)

        self.port = random.randint(10000, 65535)
        over_ssh.exchange_certs(self.cert_file)

        self.__started = True

    def daemonize(self):
        self.startup()
        super(DockerTunnelDaemon, self).daemonize()

    def run(self):
        self.startup()

        try:
            os.remove(self.sock_name)
        except:
            pass

        kw = {
            'sock': self.sock_name,
            'port': self.port,
            'lpem': '{}.pem'.format(self.local_basename),
            'rpem': '{}.pem'.format(self.remote_basename),
            'remote_host': self.hostname,
            'crt': self.cert_file,
        }
        if True:
            cmd0 = ["socat", "-t3600", "TCP-LISTEN:{},forever,reuseaddr,fork".format(self.port),
                    "EXEC:'ssh {} socat STDIO \"TCP:localhost:{}\"'".format(self.hostname, self.port)]
            cmd1 = ["socat", "-t3600", "unix-listen:{sock},fork,mode=600".format(**kw),
                    "openssl-connect:localhost:{port},cert={lpem},cafile={crt}".format(**kw)]
            # cmd2 = (["ssh", "-kTax", self.hostname, "sudo"] +
            cmd2 = (["ssh", "-t", "-t", "-kax", self.hostname, "sudo"] +
                    (["-S", ] if env['password'] else []) +
                    [("socat -t3600 openssl-listen:{port},fork,forever,reuseaddr,cert={rpem},cafile={crt} "
                      "UNIX-CONNECT:/var/run/docker.sock").format(**kw)])
        else:
            cmd0 = ["socat", "-t3600", "TCP-LISTEN:{},forever,reuseaddr,fork".format(self.port),
                    "EXEC:'ssh {} socat STDIO \"TCP:localhost:{}\"'".format(self.hostname, self.port)]
            cmd1 = ["socat", "-t3600", "unix-listen:{sock},fork,mode=600".format(**kw),
                    "tcp-connect:localhost:{port}".format(**kw)]
            # cmd2 = (["ssh", "-kTax", self.hostname, "sudo"] +
            cmd2 = (["ssh", "-t", "-t", "-kax", self.hostname, "sudo"] +
                    (["-S", ] if env['password'] else []) +
                    [("socat -t3600 tcp-listen:{port},fork,forever,reuseaddr "
                      "UNIX-CONNECT:/var/run/docker.sock").format(**kw)])

        p0 = subprocess.Popen(cmd0)
        p2 = subprocess.Popen(cmd2, stdin=subprocess.PIPE)
        p1 = subprocess.Popen(cmd1)

        if env['password']:
            p2.stdin.write(env['password'] + '\n')
            p2.stdin.flush()

        try:
            while True:
                time.sleep(0.1)
        except:
            pass
        p2.send_signal(signal.SIGINT)

        p0.terminate()
        p1.terminate()
        p2.terminate()

    def connect(self):
        if self.get_pid():
            try:
                subprocess.check_call(['docker', '-H', 'unix://{}'.format(self.sock_name), 'info'],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, )
            except:
                self.stop()
                try:
                    self.delpid()
                except:
                    pass

        if not self.get_pid():
            p = Process(target=self.execute, args=('start', ))
            p.start()
            p.join()
            if not p.exitcode:
                for i in range(50):
                    if os.path.exists(self.sock_name):
                        time.sleep(0.1)
                        break
                    time.sleep(0.1)
                subprocess.check_call(['docker', '-H', 'unix://{}'.format(self.sock_name), 'info'],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, )
            return p.exitcode


def connect(hostname):
    return DockerTunnelDaemon(hostname=hostname).connect()


def close(hostname):
    tunnel = DockerTunnelDaemon(hostname=hostname)
    tunnel.stop()
    try:
        tunnel.delpid()
    except:
        pass


def main():
    """
    The application entry point
    python -m docker_tools.docker_tunnel restart -H subuntu0
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
    daemon = DockerTunnelDaemon(hostname=args.hostname)

    daemon.execute(operation)


if __name__ == '__main__':
    main()

