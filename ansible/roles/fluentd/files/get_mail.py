# coding: utf-8
import json
import mailbox

path = '/var/mail/td-agent'
mbox = mailbox.mbox(path)
if mbox.keys():
    for key in mbox.keys():
        message = mbox.pop(key)
        d = dict(message.items())
        p = message.get_payload()
        if isinstance(p, list):
            d['message'] = ('-' * 80).join(str(x).decode('utf-8') for x in p)
        else:
            d['message'] = p.decode('utf-8')
        print json.dumps(d)
    open(path, 'w')
