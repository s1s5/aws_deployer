# coding: utf-8
from __future__ import unicode_literals
from __future__ import absolute_import

import uuid
import copy
import os
import yaml
from pprint import pprint
import threading

from fabric.api import execute
from fabric.state import env
from fabric.utils import puts

from ansible.parsing.dataloader import DataLoader
from ansible.vars import VariableManager
from ansible.inventory import Inventory

from compose.cli import command
from compose.config import config as dc_config

import docker_tools
from docker_tools import over_ssh


env.forward_agent = True
env.use_ssh_config = True


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
        print ' - ', service.name, service.image_name
        pprint(service.config_dict())


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
    s = run("getent hosts %s | awk '{ print $1 }'" % dst_hostname).strip()
    if not s:
        s = run("dig +short %s" % dst_hostname).strip()
    print '"{}"'.format(s)
    __RESOLVE_CACHE[key] = s
    return s


class Orchestra(object):
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
        self.inventory = self.getInventory()
        project = load_compose_settings(
            self.compose_context, [get_filename(self.filedir, x) for x in self.conf_dict['compose_files']])
        hs_map = {}
        sh_map = {}
        for service in project.services:
            hosts = self.inventory.get_hosts(service.name)
            sh_map[service.name] = [str(x) for x in hosts]
            for h in hosts:
                h = str(h)
                l = hs_map.get(h, [])
                l.append(service.name)
                hs_map[h] = l
        self.host_services_map, self.service_hosts_map = hs_map, sh_map

        config_details = dc_config.find(self.filedir, [self.conf_dict['compose_files'][0]], None)
        config_data = dc_config.load(config_details)

        all_override = self.conf_dict.get('override', {}).get('all', {})
        all_services = {}
        for service in project.services:
            all_services[service.name] = all_override
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
            services[service.name]['extra_hosts'] = services[service.name].get('extra_hosts', base_hosts) + extra_hosts

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

    def getInventory(self):
        return load_inventory(get_filename(self.filedir, self.conf_dict['ansible_inventory']))

    def getProject(self, host=None):
        project = load_compose_settings(
            self.compose_context, [get_filename(self.filedir, x) for x in self.conf_dict['compose_files']], host=host)
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
        debug_dump_inventory(self.inventory)
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

    def start(self, build=True):
        # t = threading.Thread(target=self.build)
        # t.start()
        self.proxy = over_ssh.DockerMultipleProxy(
            [str(x) for x in self.host_services_map.keys()],
            self.default_project.name, sleep_time=1)
        self.proxy.start()
        self.projects = {host: self.getProject(self.proxy.getSock(host)) for host in self.host_services_map.keys()}
        # t.join()

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
        for host, service_names in self.host_services_map.items():
            services = self.default_project.get_services(service_names)
            image_map[host] = [(x.image_name, x.image_name) for x in services]
        self.proxy.push(image_map)

    def up(self):
        tl = []
        for host, service_names in self.host_services_map.items():
            project = self.projects[host]
            t = threading.Thread(
                target=project.up,
                kwargs={
                    'service_names': service_names,
                    'start_deps': False,
                    'detached': True,
                })
            t.start()
            tl.append(t)
        [x.join() for x in tl]


def load_settings(filename):
    # resolveIp('subuntu0', 'subuntu1')
    # return
    orchestra = Orchestra(filename)

    # def get_deps(proj, service):
    #     return {
    #         (proj.get_service(dep), config)
    #         for dep, config in service.get_dependency_configs().items()
    #     }
    # for s in orchestra.default_project.get_services():
    #     print '-' * 20, s
    #     ss = get_deps(orchestra.default_project, s)
    #     for d, c in ss:
    #         print d, c(so)
    # return
    orchestra.debugDump()
    orchestra.start()
    try:
        print "start finished!"
        orchestra.push()
        orchestra.up()
    finally:
        orchestra.end()
    return

    d = yaml.load(open(filename))
    print("---- input file ----")
    pprint(d)
    filedir = os.path.abspath(os.path.dirname(filename))
    if d.get('compose_context'):
        if os.path.isabs(d['compose_context']):
            context = d['compose_context']
        else:
            context = os.path.join(filedir, d['compose_context'])
    else:
        context = filedir
    inventory = load_inventory(get_filename(filedir, d['ansible_inventory']))

    def _load_compose_settings(host=None):
        return load_compose_settings(
            context, [get_filename(filedir, x) for x in d['compose_files']], host=host)
    project = _load_compose_settings()
    project.build()

    debug_dump_inventory(inventory)
    debug_dump_compose_project(project)
    # print dir(inventory)
    # for i in inventory.get_groups():
    #     print i, inventory.get_hosts(i)

    services = project.get_services_without_duplicate(
        None,
        include_deps=True)
    print [x.name for x in services]

    # for service in project.services:
    #     print "=" * 80
    #     print service.name
    #     print "-" * 40
    #     pprint(service.options)
    #     print "-" * 20
    #     number = None
    #     one_off = False
    #     override_options = {}
    #     container_options = service._get_container_create_options(
    #         override_options,
    #         number or service._next_container_number(one_off=one_off),
    #         one_off=False,
    #         previous_container=None,
    #     )
    #     pprint(container_options)
    # return

    host_task_map = {}
    for group in inventory.get_groups():
        for host in inventory.get_hosts(group):
            host_task_map[host] = []

    for service in project.services:
        hosts = inventory.get_hosts(service.name)
        print service.name, service.image_name, '=>', hosts
        if not hosts:
            continue
        for host in hosts:
            name = service.image_name  # .split(':')[0]
            host_task_map[host].append(('push', [service.image_name, name], {}))
            host_task_map[host].append(('compose_up', [], {
                'service_names': [service.name],
                'start_deps': False,
                'detached': True}))

    for host, commands in host_task_map.items():
        if not commands:
            continue

        puts('{} {}'.format(host, commands))

        def _run(proxy):
            project = _load_compose_settings(proxy.sock)
            for cmd, args, kwargs in commands:
                puts('{} {} {}'.format(cmd, args, kwargs))
                if cmd == 'push':
                    proxy.push(*args)
                elif cmd == 'compose_up':
                    project.up(*args, **kwargs)
                else:
                    raise Exception('unknown cmd={}, args={}, kwargs={}'.format(cmd, args, kwargs))
            import time
            time.sleep(10)

        execute(docker_tools.execute, _run,
                hosts=[str(host)])

    # print dir(project)
    # links = []
    # for service in project.services:
    #     hosts = inventory.get_hosts(service.name)
    #     print service.name, service.image_name, '=>', hosts
    #     from pprint import pprint
    #     run_kwargs = extract_run_arguments(
    #         project.name, service.name, service.config_dict(), d.get('host_aliases', dict()))
    #     pprint(service.config_dict())
    #     pprint(run_kwargs)
    #     if not hosts:
    #         continue
    #     for host in hosts:
    #         name = service.image_name.split(':')[0]
    #         execute(docker_tools.run, service.image_name.split(':')[0],
    #                 hosts=[str(host)], links=links, **run_kwargs)
    #     links.append((run_kwargs['name'], run_kwargs['hostname']))


def main(args):
    load_settings(args[0])


def __entry_point():
    import argparse
    parser = argparse.ArgumentParser(
        description=u'',  # プログラムの説明
    )
    parser.add_argument("args", nargs="*")
    main(parser.parse_args().args)


if __name__ == '__main__':
    __entry_point()
