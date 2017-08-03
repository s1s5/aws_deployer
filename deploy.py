# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import logging
import time
import uuid
import copy
import os
import yaml
from pprint import pprint
import threading
import operator
import subprocess

from fabric.api import hide
from fabric.state import env

# import docker
from compose.cli import command
from compose.config import config as dc_config
from compose.service import BuildAction
from compose.service import ConvergenceStrategy
from compose.project import ProjectError

from docker_tools import docker_tunnel

logger = logging.getLogger(__name__)


env.forward_agent = True
env.use_ssh_config = True


def load_compose_settings(context, files, host=None):
    if host:
        return command.project_from_options(
            context, {'--file': files, '--host': host})
    return command.project_from_options(
        context, {'--file': files})


def debug_dump_compose_project(project):
    for service in project.services:
        if service.config_dict().get('options', {}).get('command') == 'true':
            continue
        print('-' * 20, service.name, service.image_name, '-' * 20)
        pprint(service.config_dict())


def get_filename(base_dir, path):
    if os.path.isabs(path):
        return path
    return os.path.join(base_dir, path)


__RESOLVE_CACHE = {}


def resolveIp(src_hostname, dst_hostname):
    global __RESOLVE_CACHE
    from fabric.api import run
    key = (src_hostname, dst_hostname)
    if key in __RESOLVE_CACHE and __RESOLVE_CACHE.get(key):
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
        self.temp_files = []
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
        needs_expose = set()
        for service in project.services:
            extra_hosts = []
            try:
                depends_on = set(service.config_dict()['options'].get('depends_on', {}).keys())
            except:
                logger.exception("depends_on failed")
                project.build()
                depends_on = set(service.config_dict()['options'].get('depends_on', {}).keys())

            if depends_on:
                for service2 in project.get_services(depends_on):
                    if service == service2:
                        continue
                    lb = self.service_hosts_map[service.name]
                    l = list(set(self.service_hosts_map[service2.name]).difference(
                        set(self.service_hosts_map[service.name])))
                    if lb and l:
                        extra_hosts.append('{}:{}'.format(service2.name, self.conf_dict['hosts'][l[0]]['ip']))
            extra_hosts = list(set(extra_hosts))
            needs_expose.update([x.split(':')[0] for x in extra_hosts])

            # print(service.name, 'depends =>', depends_on, extra_hosts)
            services[service.name] = self.conf_dict.get('override', {}).get(service.name, {})
            base_hosts = ['{}:{}'.format(x[0], x[1]) for x in service.options.get('extra_hosts', {}).items()]
            services[service.name]['extra_hosts'] = services[service.name].get(
                'extra_hosts', base_hosts) + extra_hosts
        self.needs_expose = needs_expose

        self.addConfig(config_data, services)
        self.config_data = config_data
        # print config_data.version
        # print dir(config_data)
        self.default_project = self.getProject()
        self.git_revision = self.get_git_revision()

        env.forward_agent = True
        env.use_ssh_config = True

    def get_git_revision(self, length=10):
        try:
            revision = subprocess.check_output(
                ['git', '-C', self.compose_context, 'rev-parse', 'HEAD']).strip()[:length]
            result = subprocess.check_output(['git', '-C', self.compose_context, 'status', '--porcelain'])
            for line in result.splitlines():
                if line.startswith('?'):
                    continue
                revision = '{}[*]'.format(revision)
                break
        except:
            return '?' * length
        return revision

    def addConfig(self, config_data, services):
        d = {
            'version': config_data.version,
            'services': services
        }
        # pprint(d)
        tmp_filename = os.path.join('/tmp/', '{}.yml'.format(uuid.uuid4().hex))
        yaml.safe_dump(d, open(tmp_filename, 'wb'), encoding='utf-8', allow_unicode=True)
        self.temp_files.append(tmp_filename)
        self.conf_dict['compose_files'].append(tmp_filename)

    def getSock(self, hostname):
        base = os.path.join('/tmp', 'docker-{}'.format(os.environ['USER']))
        return 'unix://{}'.format(os.path.join(base, '{}.sock'.format(hostname)))

    def getProject(self, host=None):
        project = load_compose_settings(
            self.compose_context, [get_filename(self.filedir, x)
                                   for x in self.conf_dict['compose_files']], host=host)
        project._host = host
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
                else:
                    base[key] = copy.deepcopy(d[key])
        return base

    def start(self):
        for hostname in self.hosts:
            docker_tunnel.connect(hostname)

        # services = {}
        # for service in self.default_project.services:
        #     release_id = service.build() if service.can_be_built() else service.image_name
        #     services[service.name] = {
        #         'environment': [
        #             'RELEASE_ID={}/{}/{}'.format(
        #                 self.conf_dict['project'], service.name, release_id)
        #         ],
        #     }
        # self.addConfig(self.config_data, services)

        self.projects = {host: self.getProject(self.getSock(host))
                         for host in self.hosts}

    def end(self):
        [os.remove(x) for x in self.temp_files]
        self.temp_files = []

    def _project_up(self, project, service_names):
        from compose import parallel

        project.initialize()
        project.find_orphan_containers(True)

        # services = project.get_services_without_duplicate(
        #     service_names,
        #     include_deps=start_deps)
        services = project.get_services(service_names, False)

        def check(service):
            for try_cnt in range(3):
                try:
                    service.remove_duplicate_containers()
                    break
                except:
                    if try_cnt >= 2:
                        raise
                    time.sleep(5)

            service.ensure_image_exists(do_build=BuildAction.none)
        if False:
            tl = []
            for service in services:
                t = threading.Thread(target=check, args=(service, ))
                t.start()
                tl.append(t)
            [x.join() for x in tl]
        else:
            for service in services:
                check(service)

        # plans = project._get_convergence_plans(services, ConvergenceStrategy.changed)
        plans = project._get_convergence_plans(services, ConvergenceStrategy.always)

        def do(service):
            return service.execute_convergence_plan(
                plans[service.name],
                timeout=None,
                detached=True
            )

        def get_deps(service):
            return {
                (project.get_service(dep), config)
                for dep, config in service.get_dependency_configs().items()
            }

        results, errors = parallel.parallel_execute(
            services,
            do,
            operator.attrgetter('name'),
            None,
            get_deps
        )

        if errors:
            raise ProjectError(
                'Encountered errors while bringing up the project. {}'.format(errors)
            )

        return [
            container
            for svc_containers in results
            if svc_containers is not None
            for container in svc_containers
        ]

    def build_and_up(self, project=None, service_names=None):
        if project is None:
            tl = []
            for host in self.hosts:
                service_names = self.hosts[host].get('services', {})
                project = self.projects[host]
                t = threading.Thread(
                    target=self.build_and_up, args=(project, service_names))
                t.start()
                tl.append(t)
            [x.join() for x in tl]
        else:
            # caution !! project.client == docker.APIClient()
            service_release_ids = {}
            disabled_service_names = set(x.name for x in project.services).difference(service_names)
            project.stop(disabled_service_names)
            for service_name in service_names:
                service = project.get_service(service_name)
                if service.can_be_built():
                    image_id = service.build(pull=True)
                else:
                    project.client.pull(service.image_name)
                    image_id = service.image_name

                service_release_ids[service.name] = {
                    'environment': [
                        'RELEASE_ID={}:{}/{}/{}'.format(
                            self.conf_dict['project'], self.git_revision, service.name, image_id),
                        'SERVICE_NAME={}'.format(service_name),
                        'IMAGE_NAME={}'.format(service.image_name),
                    ],
                }
                # print(image_id, service_name, service.image_name, dir(service))
                # print(project.client.images())
                config = project.client.inspect_image(service.image_name)['Config']
                ports = [x.split('/')[0]
                         for x in config.get('ExposedPorts', {}).keys()]
                exposed_ports = [x.split(':')[-1] for x in service.config_dict()['options'].get('ports', [])]
                ports = set(ports).difference(exposed_ports)
                # print(service_name, ports, exposed_ports, service.config_dict())
                if service_name in self.needs_expose:
                    service_release_ids[service.name]['ports'] = ['{}:{}'.format(x, x) for x in ports]

            self.addConfig(self.config_data, service_release_ids)
            project = self.getProject(project._host)
            # pprint(service_release_ids)
            self._project_up(project, service_names)


def main(options, unknown_options):
    orchestra = Orchestra(options.deploy_filename)
    orchestra.start()
    try:
        orchestra.build_and_up()
    finally:
        orchestra.end()


def __entry_point():
    import argparse
    parser = argparse.ArgumentParser(
        description=u'',  # プログラムの説明
    )
    parser.add_argument('deploy_filename')
    main(*parser.parse_known_args())


if __name__ == '__main__':
    __entry_point()
