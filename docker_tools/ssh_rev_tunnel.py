# coding: utf-8
import random
import subprocess
# import os

from fabric.state import env


class ReverseTunnel(object):

    def __init__(self, local_port=-1, remote_port=-1):
        self.plist = []
        self.local_port = local_port
        self.remote_port = remote_port

    def __enter__(self):
        if self.plist:
            raise Exception()

        if self.remote_port <= 0:
            remote_port = random.randint(32768, 65535)
        else:
            remote_port = self.remote_port
        if self.local_port <= 0:
            local_port = random.randint(32768, 65535)
        else:
            local_port = self.local_port

        self.plist = []
        for i in env['all_hosts']:
            cmd = ['ssh', '-R',
                   '{}:localhost:{}'.format(
                       remote_port, local_port),
                   '-o', 'StrictHostKeyChecking=no',
                   '-o', 'UserKnownHostsFile=/dev/null']
            if 'key_filename' in env and env['key_filename']:
                cmd += ['-i', env['key_filename'][0]]
            cmd += [i]
            p = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            p.stdin.write("uptime")
            p.stdin.flush()
            p.stdout.readline()
            self.plist.append(p)
        return self

    def __exit__(self, type_, value, traceback):
        from signal import SIGINT
        for p in self.plist:
            p.send_signal(SIGINT)
            p.wait()
        self.plist = []


def reverse_tunnel_decorator(local_port, remote_port):
    def with_reverse_tunnel(func):
        def run(*args, **kw):
            with ReverseTunnel(local_port, remote_port):
                return func(*args, **kw)
        return run
    return with_reverse_tunnel
