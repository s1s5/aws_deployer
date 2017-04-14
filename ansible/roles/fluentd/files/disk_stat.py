# coding: utf-8
import time
import json
import subprocess


paths = ['/', '/data', '/var', '/home']
parsed = [[y for y in x.split(' ') if y]
          for x in subprocess.check_output(['df', '-k']).splitlines()[1:]]
result = {}
for i in subprocess.check_output(['df', '-k']).splitlines()[1:]:
    i = [x for x in i.split(' ') if x]
    try:
        if i[-1] in paths:
            result['{}:total'.format(i[-1])] = int(i[1])
            result['{}:used'.format(i[-1])] = int(i[2])
            result['{}:use%'.format(i[-1])] = float(i[2]) / int(i[1])
    except:
        pass
result['timestamp'] = time.time()
print(json.dumps(result))
