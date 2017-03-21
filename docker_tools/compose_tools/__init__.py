# coding: utf-8
from __future__ import unicode_literals
from __future__ import absolute_import

import os

from fabric.decorators import task
from fabric.state import env
from compose.cli import command

from .. import over_ssh


@task
def up(target_dir, *files, **kw):
    with over_ssh.DockerProxy(
            env['host_string'],
            os.path.basename(os.getcwd())) as proxy:
        project = command.project_from_options(
            target_dir, {'--file': files, '--host': proxy.sock})
        project.up()
