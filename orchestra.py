# coding: utf-8
from __future__ import unicode_literals
from __future__ import absolute_import

import uuid
import copy
import os
import yaml
# import json
import six
from pprint import pprint
import threading
import subprocess

from fabric.api import hide  # execute
from fabric.state import env
# from fabric.utils import puts

from ansible.parsing.dataloader import DataLoader
from ansible.vars import VariableManager
from ansible.inventory import Inventory

from compose.cli import command
from compose.config import config as dc_config

# import docker_tools
from docker_tools import over_ssh


env.forward_agent = True
env.use_ssh_config = True
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_inventory(filename):
    variable_manager = VariableManager()
    loader = DataLoader()

    #  Ansible: Load inventory
    inventory = Inventory(
        loader=loader,
        variable_manager=variable_manager,
        host_list=filename
    )
    return inventory


def serialize_inventory(inventory):
    if not isinstance(inventory, Inventory):
        return dict()

    data = list()
    for group in inventory.get_groups():
        if group != 'all':
            group_data = inventory.get_group(group).serialize()

            #  Seed host data for group
            host_data = list()
            for host in inventory.get_group(group).hosts:
                host_data.append(host.serialize())

            group_data['hosts'] = host_data
            data.append(group_data)

    return data


def load_compose_settings(context, files, host=None):
    if host:
        return command.project_from_options(
            context, {'--file': files, '--host': host})
    return command.project_from_options(
        context, {'--file': files})


def debug_dump_inventory(inventory):
    pprint(serialize_inventory(inventory))


def debug_dump_compose_project(project):
    for service in project.services:
        if service.config_dict().get('options', {}).get('command') == 'true':
            continue
        print '-' * 20, service.name, service.image_name, '-' * 20
        pprint(service.config_dict())
        # print 'exposed ports:', service.image().get('ExposedPorts', [])
        # print(dir(service))
        # pprint(service.options)
        # number = None
        # one_off = False
        # override_options = {}
        # container_options = service._get_container_create_options(
        #     override_options,
        #     number or service._next_container_number(one_off=one_off),
        #     one_off=False,
        #     previous_container=None,
        # )
        # pprint(container_options)


def get_filename(base_dir, path):
    if os.path.isabs(path):
        return path
    return os.path.join(base_dir, path)


def extract_run_arguments(project_name, service_name, config_dict, host_aliases):
    d = {}
    options = config_dict.get('options', {})
    if 'command' in options:
        d['command'] = options['command']
    if 'environment' in options:
        d['environment'] = options['environment']
    if 'restart' in options:
        d['restart_policy'] = options['restart']
    if 'volumes' in options:
        volumes = {}
        for volume in options['volumes']:
            volumes[volume.external] = {'bind': volume.internal, 'mode': volume.mode}
        d['volumes'] = volumes
    if 'ports' in options:
        ports = {}
        for port in options['ports']:
            host, docker = port.split(':')
            ports[host] = docker
        d['ports'] = ports
    if host_aliases:
        d['extra_hosts'] = host_aliases
    if 'networks' in config_dict:
        d['networks'] = config_dict['networks'].keys()
    d['detach'] = True
    d['hostname'] = service_name
    d['name'] = '{}_{}_1'.format(project_name, service_name)
    return d


__RESOLVE_CACHE = {}


def resolveIp(src_hostname, dst_hostname):
    global __RESOLVE_CACHE
    from fabric.api import run
    key = (src_hostname, dst_hostname)
    if key in __RESOLVE_CACHE:
        return __RESOLVE_CACHE[key]
    env.host_string = src_hostname
    with hide('running'), hide('stdout'):
        s = run("getent hosts %s | awk '{ print $1 }'" % dst_hostname).strip()
        if not s:
            s = run("dig +short %s" % dst_hostname).strip()
    # print '"{}"'.format(s)
    __RESOLVE_CACHE[key] = s
    return s


class Orchestra(object):
    timezone = 'Japan'

    def __init__(self, filename):
        self.conf_dict = yaml.load(open(filename))

        filedir = os.path.abspath(os.path.dirname(filename))
        if self.conf_dict.get('compose_context'):
            if os.path.isabs(self.conf_dict['compose_context']):
                context = self.conf_dict['compose_context']
            else:
                context = os.path.join(filedir, self.conf_dict['compose_context'])
        else:
            context = filedir
        self.filedir = filedir
        self.compose_context = context
        self.hosts = self.conf_dict['hosts']
        project = load_compose_settings(
            self.compose_context, [get_filename(self.filedir, x) for x in self.conf_dict['compose_files']])

        self.service_hosts_map = {
            x.name: [y for y in self.hosts if x.name in self.hosts[y].get('services', {})]
            for x in project.services}

        config_details = dc_config.find(self.filedir, [self.conf_dict['compose_files'][0]], None)
        config_data = dc_config.load(config_details)

        all_override = self.conf_dict.get('override', {}).get('all', {})
        l = all_override.get('environment', [])

        l.append('PROJECT_NAME={}'.format(self.conf_dict['project']))
        l.append('TZ={}'.format(self.timezone))

        all_override['environment'] = l
        all_services = {}
        for service in project.services:
            all_services[service.name] = copy.deepcopy(all_override)
        self.addConfig(config_data, all_services)
        project = load_compose_settings(
            self.compose_context, [get_filename(self.filedir, x) for x in self.conf_dict['compose_files']])

        services = {}
        for service in project.services:
            extra_hosts = []
            for service2 in project.services:
                if service == service2:
                    continue
                lb = self.service_hosts_map[service.name]
                l = list(set(self.service_hosts_map[service2.name]).difference(
                    set(self.service_hosts_map[service.name])))
                if lb and l:
                    extra_hosts.append('{}:{}'.format(service2.name, resolveIp(lb[0], l[0])))
            extra_hosts = list(set(extra_hosts))
            services[service.name] = self.conf_dict.get('override', {}).get(service.name, {})
            base_hosts = ['{}:{}'.format(x[0], x[1]) for x in service.options.get('extra_hosts', {}).items()]
            services[service.name]['extra_hosts'] = services[service.name].get(
                'extra_hosts', base_hosts) + extra_hosts

        self.addConfig(config_data, services)
        # print config_data.version
        # print dir(config_data)
        self.default_project = self.getProject()

        env.forward_agent = True
        env.use_ssh_config = True

    def addConfig(self, config_data, services):
        d = {
            'version': config_data.version,
            'services': services
        }
        # pprint(d)
        tmp_filename = os.path.join('/tmp/', '{}.yml'.format(uuid.uuid4().hex))
        yaml.safe_dump(d, open(tmp_filename, 'wb'), encoding='utf-8', allow_unicode=True)
        self.conf_dict['compose_files'].append(tmp_filename)

    def getProject(self, host=None):
        project = load_compose_settings(
            self.compose_context, [get_filename(self.filedir, x)
                                   for x in self.conf_dict['compose_files']], host=host)
        # for service in project.services:
        #     d = self.conf_dict.get('override', {}).get('all', {})
        #     d = self.updateDict(d, self.conf_dict.get('override', {}).get(service.name, {}))
        #     d_org = copy.deepcopy(d)
        #     extra_hosts = []
        #     for service2 in project.services:
        #         if service == service2:
        #             continue
        #         l = list(set(self.service_hosts_map[service2.name]).difference(
        #             set(self.service_hosts_map[service.name])))
        #         if l:
        #             extra_hosts.append(l[0])
        #     d['extra_hosts'] = list(set(extra_hosts))
        #     d.pop('environment')
        #     d['environment'] = dc_config.resolve_environment(d_org)
        #     print "=" * 100
        #     print service.name
        #     print service.options, d
        #     service.options = self.updateDict(service.options, d)
        #     print '>>>', service.options, d
        return project

    def debugDump(self):
        print("---- input file ----")
        pprint(self.conf_dict)
        # debug_dump_inventory(self.inventory)
        debug_dump_compose_project(self.default_project)

    def updateDict(self, base, d):
        for key in d:
            if key in base:
                if isinstance(d[key], dict):
                    base[key] = self.updateDict(base.get(key, {}), d[key])
                # elif isinstance(d[key], list):
                #     print base.get(key, []), d[key]
                #     base[key] = base.get(key, []) + d[key]
                else:
                    base[key] = copy.deepcopy(d[key])
        return base

    def start(self, build=False):
        if build:
            t = threading.Thread(target=self.build)
            t.start()
        self.proxy = over_ssh.DockerMultipleProxy(
            [str(x) for x in self.hosts],
            self.default_project.name, sleep_time=1)
        self.proxy.start()
        self.projects = {host: self.getProject(self.proxy.getSock(host))
                         for host in self.hosts}
        if build:
            t.join()

    def end(self):
        self.proxy.end()

    def build(self, service_names=None, **kw):
        tl = []
        for service in self.default_project.get_services(service_names):
            if service.can_be_built():
                t = threading.Thread(target=service.build, kwargs=kw)
                t.start()
                tl.append(t)
        [x.join() for x in tl]

    def push(self):
        image_map = {}
        for host in self.hosts:
            service_names = self.hosts[host].get('services', {})
            services = self.default_project.get_services(service_names)
            image_map[host] = [(x.build() if x.can_be_built() else x.image_name, x.image_name)
                               for x in services]
        self.proxy.push(image_map)

    def up(self):
        tl = []
        for host in self.hosts:
            service_names = self.hosts[host].get('services', {})
            project = self.projects[host]
            t = threading.Thread(
                target=project.up,
                kwargs={
                    'service_names': service_names,
                    'start_deps': False,
                    'detached': True,
                    'remove_orphans': True,
                })
            t.start()
            tl.append(t)
        [x.join() for x in tl]

    def __extractPort(self, port):
        return {'port': port.split(':')[0], 'proto': 'tcp'}

    def ansible(self, args):
        tmp_filename = os.path.join('/tmp/', '{}.yml'.format(uuid.uuid4().hex))
        var_tmp_filename = os.path.join('/tmp/', '{}.yml'.format(uuid.uuid4().hex))
        set_vars = []
        with open(tmp_filename, 'w') as fp:
            six.print_('[node]', file=fp)
            log_proxy_node = None
            for host, host_dict in self.hosts.items():
                open_ports = []
                for service_name in host_dict.get('services', {}):
                    service = self.default_project.get_service(service_name)
                    open_ports.extend([self.__extractPort(x) for x in service.options.get('ports', [])])
                # six.print_('{} allowed_port_list=\'{}\''.format(host, json.dumps(open_ports)), file=fp)
                six.print_(host, file=fp)
                set_vars.append({'hosts': host,
                                 'tasks': [
                                     {'set_fact': {'allowed_port_list': open_ports}},
                                 ] + [{'set_fact': x} for x in host_dict.get('vars', [])], })
                if 'log_proxy' in host_dict.get('services', {}):
                    log_proxy_node = host
            six.print_('[all:vars]', file=fp)
            six.print_('ansible_python_interpreter=/usr/bin/python2.7', file=fp)
            if log_proxy_node:
                six.print_('FLUENTD_LOG_AGGREGATOR_NAME=proxy', file=fp)
                six.print_('FLUENTD_LOG_AGGREGATOR_HOST={}'.format(log_proxy_node), file=fp)
                six.print_('FLUENTD_LOG_AGGREGATOR_PORT=33815', file=fp)

        yaml.safe_dump(set_vars, open(var_tmp_filename, 'wb'), encoding='utf-8', allow_unicode=True)
        print "-" * 10, "inventory file", "-" * 10
        print open(tmp_filename).read()
        print "-" * 10, "set varialbe file", "-" * 10
        print open(var_tmp_filename).read()
        subprocess.call(['ansible-playbook', '-i', tmp_filename,
                         var_tmp_filename, 'ansible/site.yml'] + args, cwd=SCRIPT_DIR)


def main(options, unknown_options):
    if options.command == 'ansible':
        orchestra = Orchestra(options.deploy_filename)
        orchestra.ansible(unknown_options)
    elif options.command == 'fabric':
        conf_dict = yaml.load(open(options.deploy_filename))
        subprocess.call(
            ['fab', '-H', ','.join(conf_dict['hosts'].keys())] + unknown_options, cwd=SCRIPT_DIR)
    elif options.command == 'compose':
        import logging
        logging.basicConfig(level=logging.WARN)

        orchestra = Orchestra(options.deploy_filename)
        # orchestra.default_project.build()
        orchestra.start()
        try:
            orchestra.push()
            orchestra.up()
        finally:
            orchestra.end()
    elif options.command == 'debug':
        orchestra = Orchestra(options.deploy_filename)
        orchestra.debugDump()
    else:
        raise Exception('unknown command: "{}"'.format(options.command))


def __entry_point():
    import argparse
    parser = argparse.ArgumentParser(
        description=u'',  # プログラムの説明
    )
    parser.add_argument('deploy_filename')
    subparsers = parser.add_subparsers(help='sub-command help', title='subcommands')

    debug_parser = subparsers.add_parser('debug', help='debug')
    debug_parser.set_defaults(command='debug')

    ansible_parser = subparsers.add_parser('ansible', help='exec ansible')
    ansible_parser.set_defaults(command='ansible')

    fab_parser = subparsers.add_parser('fab', help='exec fabric')
    fab_parser.set_defaults(command='fabric')

    compose_parser = subparsers.add_parser('compose', help='exec docker-compose')
    compose_parser.set_defaults(command='compose')

    main(*parser.parse_known_args())


if __name__ == '__main__':
    __entry_point()
