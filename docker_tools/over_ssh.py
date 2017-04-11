# coding: utf-8
from __future__ import unicode_literals
from __future__ import absolute_import

import uuid
import random
import subprocess
import os
import requests
import threading
# import multiprocessing

from fabric.state import env
from fabric.api import local, get, put, run, sudo, warn_only, hide  # , remote_tunnel
from fabric.decorators import task
from fabric.contrib.console import confirm as fab_confirm
from fabric.contrib.files import exists
from fabric.utils import puts

import docker
from .ssh_rev_tunnel import ReverseTunnel
# from ..utility import create_tls_cert


def get_base_filename(run_on_localhost):
    if run_on_localhost:
        filename = os.path.join(os.path.expanduser("~"), '.ssh', 'localhost')
    else:
        with hide('running'), hide('stdout'):
            username = run('id -un')
        filename = os.path.join('/home', username, '.ssh', 'localhost')
    return filename


@task
def create_tls_cert(filename=None, confirm_overwrite=True, run_on_localhost=False):
    '''create_tls_cert:<filename> tls証明書の作成'''
    if filename is None:
        filename = get_base_filename(run_on_localhost)
    if run_on_localhost:
        _run = local
        _exists = os.path.exists
    else:
        _run = run
        _exists = exists
    if _exists(filename + '.pem'):
        if not confirm_overwrite:
            return
        if not fab_confirm("overwrite {} ?".format(filename), default=False):
            return
    onetime_pass = uuid.uuid4().hex
    kw = {
        'filename': filename,
        'password': onetime_pass,
    }
    _run('openssl genrsa -des3 -out {filename}.key '
         '-passout pass:{password} 2048'.format(**kw))
    _run('openssl req -passin pass:{password} -new -key {filename}.key '
         '-out {filename}.csr  -subj "/CN=localhost"'.format(**kw))
    _run('cp {filename}.key {filename}.key.org'.format(**kw))
    _run('openssl rsa -passin pass:{password} -in {filename}.key.org '
         '-out {filename}.key'.format(**kw))
    _run('openssl x509 -req -days 365 -in {filename}.csr '
         '-signkey {filename}.key -out {filename}.crt'.format(**kw))
    _run('cat {filename}.crt {filename}.key > {filename}.pem'.format(**kw))
    _run('chmod 600 {filename}.key'.format(**kw))
    _run('chmod 600 {filename}.pem'.format(**kw))


class DockerRegistry(object):
    def __init__(self, project_name, port=55124):
        self.plist = []
        self.project_name = project_name
        self.port = port

    def __enter__(self):
        if self.port <= 0:
            port = random.randint(32768, 65535)
        else:
            port = self.port
        self.local_client = docker.from_env()
        environment = {
        }
        volumes = {
            '{}_docker_registry'.format(self.project_name): {'type': 'bind', 'bind': '/var/lib/registry', 'mode': 'rw'},
        }
        for volume in volumes:
            try:
                self.local_client.volumes.get(volume)
            except docker.errors.NotFound:
                self.local_client.volumes.create(volume)

        ports = {
            '5000': port,
        }
        # print self.local_client.containers.run.__doc__
        self.__container = self.local_client.containers.run(
            'registry:2.3.0', environment=environment, ports=ports,
            volumes=volumes,
            detach=True)
        # cmd = ['docker', 'run', '-p', '{}:5000'.format(port), '-v',
        #        '{}_docker_registry:/var/lib/registry'.format(self.project_name),
        #        'registry:2.3.0']
        # print ' '.join(cmd)
        # self.plist.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        # self.plist.append(subprocess.Popen(cmd))
        # import time
        # time.sleep(10)
        return port

    def __exit__(self, type_, value, traceback):
        # from signal import SIGINT
        # for p in self.plist:
        #     p.send_signal(SIGINT)
        #     p.wait()
        # self.plist = []
        # print dir(self.__container)
        try:
            self.__container.stop(timeout=1)
        except requests.exceptions.Timeout:
            print "Timeout occurred skipped"


def _socat_remote(hostname, port):
    from fabric.api import sudo
    sudo(' '.join(["socat", "TCP-LISTEN:{},fork,reuseaddr".format(port),
                   "UNIX-CONNECT\:/var/run/docker.sock"]))


class DockerTunnel(object):

    def __init__(self, hostname, port=-1, sock_name=None):
        self.hostname = hostname
        self.plist = []
        self.port = port
        self.tmp_file = None
        self.sock_name = sock_name

    def __enter__(self):
        if self.plist:
            raise Exception()
        self.plist = []
        if self.port <= 0:
            port = random.randint(32768, 65535)
        else:
            port = self.port

        if self.sock_name:
            sock_name = self.sock_name
        else:
            sock_name = '/tmp/{}.sock'.format(uuid.uuid4().hex)

        # sock_name = '~/.docker_tunnel_{}'.format(uuid.uuid4().hex)
        # proc = multiprocessing.Process(target=_socat_remote, args=(self.hostname, port))
        # proc.start()
        # self.proc = proc

        local_basename = get_base_filename(True)
        remote_basename = get_base_filename(False)
        tmp_file = '/tmp/{}.crt'.format(uuid.uuid4().hex)
        create_tls_cert(confirm_overwrite=False, run_on_localhost=True)
        create_tls_cert(confirm_overwrite=False, run_on_localhost=False)
        put(local_path='{}.crt'.format(local_basename), remote_path=tmp_file)
        get(local_path=tmp_file, remote_path='{}.crt'.format(remote_basename))

        kw = {
            'sock': sock_name,
            'port': port,
            'lpem': '{}.pem'.format(local_basename),
            'rpem': '{}.pem'.format(remote_basename),
            'remote_host': self.hostname,
            'crt': tmp_file,
        }
        sudo("true")
        # print env

        def _local_listen(**kw):
            local("socat unix-listen:{sock},fork,mode=600 "
                  "openssl-connect:localhost:{port},cert={lpem},cafile={crt}".format(**kw))

        def _local_forward(**kw):
            local("socat TCP-LISTEN:{port},reuseaddr,fork "
                  "EXEC:'ssh {remote_host} socat STDIO \"TCP:127.0.0.1:{port}\"'".format(**kw))

        def _remote_forward(**kw):
            sudo("socat openssl-listen:{port},fork,reuseaddr,cert={rpem},cafile={crt} "
                 "UNIX-CONNECT:/var/run/docker.sock".format(**kw))

        # self.plist.append(multiprocessing.Process(target=_local_listen, kwargs=kw))
        # self.plist.append(multiprocessing.Process(target=_local_forward, kwargs=kw))
        # self.plist.append(multiprocessing.Process(target=_remote_forward, kwargs=kw))
        # for i in self.plist:
        #     i.start()
        # import time
        # time.sleep(60)
        # self.tunnel = remote_tunnel(port)
        # self.tunnel.__enter__()

        cmd0 = ["socat", "TCP-LISTEN:{},forever,reuseaddr,fork".format(port),
                "EXEC:'ssh {} socat STDIO \"TCP:127.0.0.1:{}\"'".format(self.hostname, port)]
        cmd1 = ["socat", "unix-listen:{sock},fork,mode=600".format(**kw),
                "openssl-connect:localhost:{port},cert={lpem},cafile={crt}".format(**kw)]
        cmd2 = (["ssh", "-kTax", self.hostname, "sudo"] +
                (["-S", ] if env['password'] else []) +
                [("socat openssl-listen:{port},fork,forever,reuseaddr,cert={rpem},cafile={crt} "
                  "UNIX-CONNECT:/var/run/docker.sock").format(**kw)])
        self.cmd_id = ("socat openssl-listen:{port},fork,forever,"
                       "reuseaddr,cert={rpem},cafile={crt}".format(**kw))

        # print 'cmd0:', ' '.join(cmd0)
        # print 'cmd1:', ' '.join(cmd1)
        # print 'cmd2:', ' '.join(cmd2)
        # cmd1 = (["ssh", "-kTax", self.hostname, "sudo", ] +
        #         (["-S", ] if self.sudo_password else []) +
        #      ["socat", "TCP-LISTEN:{},fork,reuseaddr".format(port), "UNIX-CONNECT\:/var/run/docker.sock"])
        # cmd0 = ["socat", "TCP-LISTEN:{},reuseaddr,fork".format(port),
        #         "EXEC:'ssh {} socat STDIO UNIX-CONNECT:{}'".format(self.hostname, sock_name)]
        # cmd1 = (["ssh", "-kTax", self.hostname, "sudo", ] +
        #         (["-S", ] if self.sudo_password else []) +
        # ["socat", "UNIX-LISTEN:{},fork,reuseaddr".format(sock_name), "UNIX-CONNECT\:/var/run/docker.sock"])

        self.plist.append(subprocess.Popen(cmd0, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        self.plist.append(subprocess.Popen(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        p2 = subprocess.Popen(cmd2, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # self.plist.append(subprocess.Popen(cmd0))
        # self.plist.append(subprocess.Popen(cmd1))
        # p2 = subprocess.Popen(cmd2, stdin=subprocess.PIPE)
        self.plist.append(p2)
        # self.plist.append(subprocess.Popen(cmd0))
        # p = subprocess.Popen(cmd1, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if env['password']:
            p2.stdin.write(env['password'] + '\n')
            p2.stdin.flush()
        # self.p = p
        # self.plist.append(p)
        # import time
        # time.sleep(10)
        self.tmp_file = tmp_file
        self.sock = kw['sock']
        return self.sock

    def __exit__(self, type_, value, traceback):
        # from signal import SIGINT
        # # self.p.stdin.close()
        # self.proc.terminate()
        # # import time
        # # time.sleep(10)
        # for p in self.plist:
        #     p.send_signal(SIGINT)
        #     p.wait()
        [x.terminate() for x in self.plist]
        self.plist = []
        if os.path.exists(self.tmp_file):
            os.remove(self.tmp_file)
        if exists(self.tmp_file):
            run('rm {}'.format(self.tmp_file))
        if os.path.exists(self.sock):
            os.remove(self.sock)

        ret = subprocess.check_output(['ssh', self.hostname, 'ps', 'aux'])
        # print type(ret)
        ret = ret.decode('UTF-8')
        for line in ret.splitlines():
            line = line.strip()
            line = filter(lambda x: x, line.split(' '))
            pid = line[1]
            cmd = line[10:]
            # print self.cmd_id in ' '.join(cmd), self.cmd_id, ' '.join(cmd)
            if self.cmd_id in ' '.join(cmd):
                with hide('stdout', 'warnings', 'running'), warn_only():
                    sudo('kill {}'.format(pid))
        # self.tunnel.__exit__(type_, value, traceback)
        # self.tunnel = None


class DockerProxy(object):
    def __init__(self, hostname, project_name, registry_port=55124, sock_name=None, sleep_time=10):
        self.hostname = hostname
        self.project_name = project_name
        self.registry_port = registry_port
        self.__local_client = None
        self.__remote_client = None
        self.reg = None
        self.sock_name = sock_name
        self.sleep_time = sleep_time

    def __enter__(self):
        if self.reg is not None:
            raise Exception()
        self.reg = DockerRegistry(self.project_name, -1)
        self.dt = DockerTunnel(self.hostname, sock_name=self.sock_name)
        self.local_registry_port = self.reg.__enter__()
        self.st = ReverseTunnel(self.local_registry_port, self.registry_port)
        self.dt_sock = self.dt.__enter__()
        self.st.__enter__()

        # waiting for service
        if self.sleep_time > 0:
            import time
            time.sleep(10)
        return self

    def __exit__(self, type_, value, traceback):
        self.st.__exit__(type_, value, traceback)
        self.reg.__exit__(type_, value, traceback)
        self.dt.__exit__(type_, value, traceback)
        self.reg = None
        self.dt = None
        self.st = None
        self.__local_client = None
        self.__remote_client = None

    def start(self):
        self.__enter__()

    def end(self):
        self.__exit__(None, None, None)

    def __append_tag(self, remote_image, tag):
        if len(tag.split(':')) > 1:
            remote_image.tag(*tag.split(':'))
        else:
            remote_image.tag(tag)

    def push(self, image, tag):
        if isinstance(image, (str, unicode)):
            image = self.local_client.images.get(image)
        try:
            remote_image = self.remote_client.images.get(tag)
            if image.id == remote_image.id:
                # self.__append_tag(remote_image, tag)
                puts('image ids are same skipped {} -> {}'.format(tag, image.id))
                return
            self.remote_client.images.remove(tag.split(':')[0])
        except docker.errors.APIError:
            pass
        except docker.errors.ImageNotFound:
            pass
        iid = image.id.split(':')[1]
        local_name = '{}/{}'.format(self.local_registry, iid)
        remote_name = '{}/{}'.format(self.remote_registry, iid)
        image.tag(local_name)
        self.local_client.images.push(local_name)
        # ここで失敗するとno space left on deviceの可能性大
        self.remote_client.images.pull(remote_name)
        remote_image = self.remote_client.images.get(remote_name)
        self.__append_tag(remote_image, tag)
        self.local_client.images.remove(local_name)
        self.remote_client.images.remove(remote_name)
        return remote_image

    def getLocalRegistry(self):
        return '127.0.0.1:{}'.format(self.local_registry_port)

    def getRemoteRegistry(self):
        return '127.0.0.1:{}'.format(self.registry_port)

    def getSock(self):
        return 'unix://{}'.format(self.dt_sock)

    def getLocalClient(self):
        if self.__local_client is None:
            self.__local_client = docker.from_env()
        return self.__local_client

    def getRemoteClient(self):
        if self.__remote_client is None:
            # print 'socket -> ', self.sock
            self.__remote_client = docker.from_env(environment=dict(DOCKER_HOST=self.sock))
        return self.__remote_client

    local_registry = property(getLocalRegistry)
    remote_registry = property(getRemoteRegistry)
    sock = property(getSock)
    local_client = property(getLocalClient)
    remote_client = property(getRemoteClient)


class DockerMultipleProxy(object):
    def __init__(self, hostnames, project_name, registry_port=55124, sleep_time=10):
        self.hostnames = hostnames
        self.project_name = project_name
        self.registry_port = registry_port
        self.__local_client = None
        self.__remote_clients = None
        self.reg = None
        self.sleep_time = sleep_time

    def __enter__(self):
        if self.reg is not None:
            raise Exception()
        self.reg = DockerRegistry(self.project_name, -1)
        self.local_registry_port = self.reg.__enter__()
        docker_tunnels = []
        rev_tunnels = []
        socks_map = {}
        for host in self.hostnames:
            env.host_string = host
            dt = DockerTunnel(host)
            rt = ReverseTunnel(self.local_registry_port, self.registry_port)
            # print 'reverse tunnel local:{}, remote:{}'.format(self.local_registry_port, self.registry_port)
            socks_map[host] = dt.__enter__()
            rt.__enter__()
            docker_tunnels.append(dt)
            rev_tunnels.append(rt)

        self.socks_map = socks_map
        self.docker_tunnels = docker_tunnels
        self.rev_tunnels = rev_tunnels
        # waiting for service
        if self.sleep_time > 0:
            import time
            time.sleep(self.sleep_time)
        self.getRemoteClients()
        return self

    def __exit__(self, type_, value, traceback):
        [x.__exit__(type_, value, traceback) for x in self.rev_tunnels]
        [x.__exit__(type_, value, traceback) for x in self.docker_tunnels]
        self.reg.__exit__(type_, value, traceback)
        self.reg = None
        self.dt = None
        self.st = None
        self.__local_client = None
        self.__remote_clients = None

    def start(self):
        self.__enter__()

    def end(self):
        self.__exit__(None, None, None)

    def __append_tag(self, remote_image, tag):
        if len(tag.split(':')) > 1:
            remote_image.tag(*tag.split(':'))
        else:
            remote_image.tag(tag)

    def __push(self, remote_client, image, tag):
        if isinstance(image, (str, unicode)):
            image = self.local_client.images.get(image)
        try:
            remote_image = remote_client.images.get(tag)
            if image.id == remote_image.id:
                # self.__append_tag(remote_image, tag)
                puts('image ids are same skipped {} {}'.format(tag, image.id))
                return
            remote_client.images.remove(tag.split(':')[0])
        except docker.errors.APIError:
            pass
        except docker.errors.ImageNotFound:
            pass
        iid = image.id.split(':')[1]
        local_name = '{}/{}'.format(self.local_registry, iid)
        remote_name = '{}/{}'.format(self.remote_registry, iid)
        image.tag(local_name)
        self.local_client.images.push(local_name)
        # ここで失敗するとno space left on deviceの可能性大
        remote_client.images.pull(remote_name)
        remote_image = remote_client.images.get(remote_name)
        self.__append_tag(remote_image, tag)
        try:
            self.local_client.images.remove(local_name)
        except docker.errors.ImageNotFound:
            pass
        try:
            remote_client.images.remove(remote_name)
        except docker.errors.ImageNotFound:
            pass

        puts('push finished {} {}'.format(tag, image.id))
        return remote_image

    def __push_list(self, hostname, image_tag_list):
        # print hostname, type(hostname), self.remote_clients
        rcl = self.remote_clients[hostname]
        [self.__push(rcl, x[0], x[1]) for x in image_tag_list]

    def push(self, image_map):
        tl = []
        for host, image_tag_list in image_map.items():
            t = threading.Thread(
                target=self.__push_list, args=(host, image_tag_list,))
            t.start()
            tl.append(t)
        [x.join() for x in tl]

    def getLocalRegistry(self):
        return '127.0.0.1:{}'.format(self.local_registry_port)

    def getRemoteRegistry(self):
        return '127.0.0.1:{}'.format(self.registry_port)

    def getSock(self, hostname):
        return 'unix://{}'.format(self.socks_map[hostname])

    def getLocalClient(self):
        if self.__local_client is None:
            self.__local_client = docker.from_env()
        return self.__local_client

    def getRemoteClients(self):
        if self.__remote_clients is None:
            # print 'socket -> ', self.sock
            self.__remote_clients = {}
            # print self.socks_map
            for host in self.socks_map:
                # print host, self.getSock(host)
                self.__remote_clients[host] = docker.from_env(
                    environment=dict(DOCKER_HOST=self.getSock(host)))
        # print self.__remote_clients
        return self.__remote_clients

    local_registry = property(getLocalRegistry)
    remote_registry = property(getRemoteRegistry)
    sock = property(getSock)
    local_client = property(getLocalClient)
    remote_clients = property(getRemoteClients)


class DockerImage(object):
    def __init__(self, image_tag, build_param, run_param):
        '''
        =========== build_param ===========
        Args:
            path (str): Path to the directory containing the Dockerfile
            fileobj: A file object to use as the Dockerfile. (Or a file-like
                object)
            tag (str): A tag to add to the final image
            quiet (bool): Whether to return the status
            nocache (bool): Don't use the cache when set to ``True``
            rm (bool): Remove intermediate containers. The ``docker build``
                command now defaults to ``--rm=true``, but we have kept the old
                default of `False` to preserve backward compatibility
            stream (bool): *Deprecated for API version > 1.8 (always True)*.
                Return a blocking generator you can iterate over to retrieve
                build output as it happens
            timeout (int): HTTP timeout
            custom_context (bool): Optional if using ``fileobj``
            encoding (str): The encoding for a stream. Set to ``gzip`` for
                compressing
            pull (bool): Downloads any updates to the FROM image in Dockerfiles
            forcerm (bool): Always remove intermediate containers, even after
                unsuccessful builds
            dockerfile (str): path within the build context to the Dockerfile
            buildargs (dict): A dictionary of build arguments
            container_limits (dict): A dictionary of limits applied to each
                container created by the build process. Valid keys:

                - memory (int): set memory limit for build
                - memswap (int): Total memory (memory + swap), -1 to disable
                    swap
                - cpushares (int): CPU shares (relative weight)
                - cpusetcpus (str): CPUs in which to allow execution, e.g.,
                    ``"0-3"``, ``"0,1"``
            decode (bool): If set to ``True``, the returned stream will be
                decoded into dicts on the fly. Default ``False``.

        =========== run_param ===========
        Args:
            image (str): The image to run.
            command (str or list): The command to run in the container.
            blkio_weight_device: Block IO weight (relative device weight) in
                the form of: ``[{"Path": "device_path", "Weight": weight}]``.
            blkio_weight: Block IO weight (relative weight), accepts a weight
                value between 10 and 1000.
            cap_add (list of str): Add kernel capabilities. For example,
                ``["SYS_ADMIN", "MKNOD"]``.
            cap_drop (list of str): Drop kernel capabilities.
            cpu_group (int): The length of a CPU period in microseconds.
            cpu_period (int): Microseconds of CPU time that the container can
                get in a CPU period.
            cpu_shares (int): CPU shares (relative weight).
            cpuset_cpus (str): CPUs in which to allow execution (``0-3``,
                ``0,1``).
            detach (bool): Run container in the background and return a
                :py:class:`Container` object.
            device_read_bps: Limit read rate (bytes per second) from a device
                in the form of: `[{"Path": "device_path", "Rate": rate}]`
            device_read_iops: Limit read rate (IO per second) from a device.
            device_write_bps: Limit write rate (bytes per second) from a
                device.
            device_write_iops: Limit write rate (IO per second) from a device.
            devices (:py:class:`list`): Expose host devices to the container,
                as a list of strings in the form
                ``<path_on_host>:<path_in_container>:<cgroup_permissions>``.

                For example, ``/dev/sda:/dev/xvda:rwm`` allows the container
                to have read-write access to the host's ``/dev/sda`` via a
                node named ``/dev/xvda`` inside the container.
            dns (:py:class:`list`): Set custom DNS servers.
            dns_opt (:py:class:`list`): Additional options to be added to the
                container's ``resolv.conf`` file.
            dns_search (:py:class:`list`): DNS search domains.
            domainname (str or list): Set custom DNS search domains.
            entrypoint (str or list): The entrypoint for the container.
            environment (dict or list): Environment variables to set inside
                the container, as a dictionary or a list of strings in the
                format ``["SOMEVARIABLE=xxx"]``.
            extra_hosts (dict): Addtional hostnames to resolve inside the
                container, as a mapping of hostname to IP address.
            group_add (:py:class:`list`): List of additional group names and/or
                IDs that the container process will run as.
            hostname (str): Optional hostname for the container.
            ipc_mode (str): Set the IPC mode for the container.
            isolation (str): Isolation technology to use. Default: `None`.
            labels (dict or list): A dictionary of name-value labels (e.g.
                ``{"label1": "value1", "label2": "value2"}``) or a list of
                names of labels to set with empty values (e.g.
                ``["label1", "label2"]``)
            links (dict or list of tuples): Either a dictionary mapping name
                to alias or as a list of ``(name, alias)`` tuples.
            log_config (dict): Logging configuration, as a dictionary with
                keys:

                - ``type`` The logging driver name.
                - ``config`` A dictionary of configuration for the logging
                  driver.

            mac_address (str): MAC address to assign to the container.
            mem_limit (float or str): Memory limit. Accepts float values
                (which represent the memory limit of the created container in
                bytes) or a string with a units identification char
                (``100000b``, ``1000k``, ``128m``, ``1g``). If a string is
                specified without a units character, bytes are assumed as an
                intended unit.
            mem_limit (str or int): Maximum amount of memory container is
                allowed to consume. (e.g. ``1G``).
            mem_swappiness (int): Tune a container's memory swappiness
                behavior. Accepts number between 0 and 100.
            memswap_limit (str or int): Maximum amount of memory + swap a
                container is allowed to consume.
            networks (:py:class:`list`): A list of network names to connect
                this container to.
            name (str): The name for this container.
            network_disabled (bool): Disable networking.
            network_mode (str): One of:

                - ``bridge`` Create a new network stack for the container on
                  on the bridge network.
                - ``none`` No networking for this container.
                - ``container:<name|id>`` Reuse another container's network
                  stack.
                - ``host`` Use the host network stack.
            oom_kill_disable (bool): Whether to disable OOM killer.
            oom_score_adj (int): An integer value containing the score given
                to the container in order to tune OOM killer preferences.
            pid_mode (str): If set to ``host``, use the host PID namespace
                inside the container.
            pids_limit (int): Tune a container's pids limit. Set ``-1`` for
                unlimited.
            ports (dict): Ports to bind inside the container.

                The keys of the dictionary are the ports to bind inside the
                container, either as an integer or a string in the form
                ``port/protocol``, where the protocol is either ``tcp`` or
                ``udp``.

                The values of the dictionary are the corresponding ports to
                open on the host, which can be either:

                - The port number, as an integer. For example,
                  ``{'2222/tcp': 3333}`` will expose port 2222 inside the
                  container as port 3333 on the host.
                - ``None``, to assign a random host port. For example,
                  ``{'2222/tcp': None}``.
                - A tuple of ``(address, port)`` if you want to specify the
                  host interface. For example,
                  ``{'1111/tcp': ('127.0.0.1', 1111)}``.
                - A list of integers, if you want to bind multiple host ports
                  to a single container port. For example,
                  ``{'1111/tcp': [1234, 4567]}``.

            privileged (bool): Give extended privileges to this container.
            publish_all_ports (bool): Publish all ports to the host.
            read_only (bool): Mount the container's root filesystem as read
                only.
            remove (bool): Remove the container when it has finished running.
                Default: ``False``.
            restart_policy (dict): Restart the container when it exits.
                Configured as a dictionary with keys:

                - ``Name`` One of ``on-failure``, or ``always``.
                - ``MaximumRetryCount`` Number of times to restart the
                  container on failure.

                For example:
                ``{"Name": "on-failure", "MaximumRetryCount": 5}``

            security_opt (:py:class:`list`): A list of string values to
                customize labels for MLS systems, such as SELinux.
            shm_size (str or int): Size of /dev/shm (e.g. ``1G``).
            stdin_open (bool): Keep ``STDIN`` open even if not attached.
            stdout (bool): Return logs from ``STDOUT`` when ``detach=False``.
                Default: ``True``.
            stdout (bool): Return logs from ``STDERR`` when ``detach=False``.
                Default: ``False``.
            stop_signal (str): The stop signal to use to stop the container
                (e.g. ``SIGINT``).
            sysctls (dict): Kernel parameters to set in the container.
            tmpfs (dict): Temporary filesystems to mount, as a dictionary
                mapping a path inside the container to options for that path.

                For example:

                .. code-block:: python

                    {
                        '/mnt/vol2': '',
                        '/mnt/vol1': 'size=3G,uid=1000'
                    }

            tty (bool): Allocate a pseudo-TTY.
            ulimits (:py:class:`list`): Ulimits to set inside the container, as
                a list of dicts.
            user (str or int): Username or UID to run commands as inside the
                container.
            userns_mode (str): Sets the user namespace mode for the container
                when user namespace remapping option is enabled. Supported
                values are: ``host``
            volume_driver (str): The name of a volume driver/plugin.
            volumes (dict or list): A dictionary to configure volumes mounted
                inside the container. The key is either the host path or a
                volume name, and the value is a dictionary with the keys:

                - ``bind`` The path to mount the volume inside the container
                - ``mode`` Either ``rw`` to mount the volume read/write, or
                  ``ro`` to mount it read-only.

                For example:

                .. code-block:: python

                    {'/home/user1/': {'bind': '/mnt/vol2', 'mode': 'rw'},
                     '/var/www': {'bind': '/mnt/vol1', 'mode': 'ro'}}

            volumes_from (:py:class:`list`): List of container names or IDs to
                get volumes from.
            working_dir (str): Path to the working directory.

        Returns:
            The container logs, either ``STDOUT``, ``STDERR``, or both,
            depending on the value of the ``stdout`` and ``stderr`` arguments.

            If ``detach`` is ``True``, a :py:class:`Container` object is
            returned instead.
        '''
        self.image_tag = image_tag
        self.build_param = build_param
        self.run_param = run_param

    def run(self, proxy, build_image=True, run_image=True):
        if build_image:
            image_name = '{}/{}'.format(proxy.registry, self.image_tag)
            image = proxy.local_client.images.build(**self.build_param)
            image.tag(image_name)
            proxy.local_client.images.push(image_name)
        else:
            image = None

        if run_image:
            proxy.remote_client.images.pull(image_name)
            container = proxy.remote_client.containers.run(
                proxy.remote_client.images.get(image_name), **self.run_param)
        else:
            container = None

        return image, container

