# coding: utf-8
from __future__ import unicode_literals
from __future__ import absolute_import

import os

from fabric.decorators import task
from fabric.state import env
from compose.cli import command
from compose.service import BuildAction

from .. import over_ssh


@task
def push(target_dir, *files, **kw):
    """push:<dir>,files.."""
    project = command.project_from_options(
        target_dir, {'--file': files})
    # print dir(project)
    # print project.name
    # for i in project.services:
    #     print i.image_name, i.name
    #     print i
    #     print dir(i)
    # return

    with over_ssh.DockerProxy(
            env['host_string'],
            os.path.basename(os.getcwd())) as proxy:
        for service in project.services:
            print service.image_name
            proxy.push(service.image_name, service.image_name)


@task
def up(target_dir, *files, **kw):
    """up:<dir>,files.."""
    with over_ssh.DockerProxy(
            env['host_string'],
            os.path.basename(os.getcwd())) as proxy:
        project = command.project_from_options(
            target_dir, {'--file': files, '--host': proxy.sock})
        project.up(do_build=BuildAction.skip)
