# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

import time
import json
import subprocess


result = {}
df = str(subprocess.check_output(['df'])).splitlines()

header = [x for x in df[0].split(' ') if x]
if header[-2] == 'Mounted' and header[-1] == 'on':
    header.pop(-1)
    header[-1] += ' on'

l = []
for i in df[1:]:
    i = dict(zip(header, [x for x in i.split(' ') if x]))
    l.append(i)
result['timestamp'] = time.time()
result['disks'] = l
print(json.dumps(result))
