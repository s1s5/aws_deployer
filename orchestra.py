# coding: utf-8
from __future__ import unicode_literals
from __future__ import absolute_import

import os
import yaml


from fabric.api import execute
from fabric.state import env

from ansible.parsing.dataloader import DataLoader
from ansible.vars import VariableManager
from ansible.inventory import Inventory

from compose.cli import command
import docker_tools


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


def load_compose_settings(context, files):
    return command.project_from_options(
        context, {'--file': files})


def debug_dump_inventory(inventory):
    from pprint import pprint
    pprint(serialize_inventory(inventory))


def debug_dump_compose_project(project):
    from pprint import pprint
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


def load_settings(filename):
    d = yaml.load(open(filename))
    filedir = os.path.abspath(os.path.dirname(filename))
    if d.get('compose_context'):
        if os.path.isabs(d['compose_context']):
            context = d['compose_context']
        else:
            context = os.path.join(filedir, d['compose_context'])
    else:
        context = filedir
    inventory = load_inventory(get_filename(filedir, d['ansible_inventory']))
    project = load_compose_settings(context, [get_filename(filedir, x) for x in d['compose_files']])
    project.build()

    # debug_dump_inventory(inventory)
    # debug_dump_compose_project(project)

    # print dir(inventory)
    # for i in inventory.get_groups():
    #     print i, inventory.get_hosts(i)

    if True:
        for service in project.services:
            hosts = inventory.get_hosts(service.name)
            print service.name, service.image_name, '=>', hosts
            if not hosts:
                continue
            for host in hosts:
                name = service.image_name.split(':')[0]
                execute(docker_tools.push, service.image_name, name, hosts=[str(host)])

    print dir(project)
    links = []
    for service in project.services:
        hosts = inventory.get_hosts(service.name)
        print service.name, service.image_name, '=>', hosts
        from pprint import pprint
        run_kwargs = extract_run_arguments(
            project.name, service.name, service.config_dict(), d.get('host_aliases', dict()))
        pprint(service.config_dict())
        pprint(run_kwargs)
        if not hosts:
            continue
        for host in hosts:
            name = service.image_name.split(':')[0]
            execute(docker_tools.run, service.image_name.split(':')[0],
                    hosts=[str(host)], links=links, **run_kwargs)
        links.append((run_kwargs['name'], run_kwargs['hostname']))


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
