# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import glob
import subprocess
import hashlib
import os
import json

tmp_dir = '/tmp/check_docker'
if not os.path.exists(tmp_dir):
    os.mkdir(tmp_dir)

containers = str(subprocess.check_output(['docker', 'ps', '--no-trunc', '-aq'])).splitlines()
whole = glob.glob(os.path.join(tmp_dir, '*'))

for container_id in containers:
    js = str(subprocess.check_output(['docker', 'inspect', container_id]))
    tmp = json.loads(js)
    tmp[0]["Mounts"] = sorted(tmp[0]["Mounts"], key=lambda x: (x["Type"], x["Source"], x["Destination"]))
    js = json.dumps(tmp[0], sort_keys=True)
    hashvalue = '{}-{}'.format(container_id, hashlib.sha1(js).hexdigest())
    dst = os.path.join(tmp_dir, hashvalue)
    if not os.path.exists(dst):
        print(js)
        for other in glob.glob(os.path.join(tmp_dir, '{}-*'.format(container_id))):
            os.remove(other)
        open(dst, 'w').write(js)
    else:
        whole.remove(dst)

for container_info in whole:
    bn = os.path.basename(container_info)
    container_id, hashvalue = bn.split('-')
    result = {
        "Id": container_id,
        "Deleted": True,
    }
    print(json.dumps(result))
    os.remove(container_info)
