#!/bin/sh
DVAL=`/bin/df / | /usr/bin/tail -1 | /bin/sed 's/^.* \([0-9]*\)%.*$/\1/'`
if [ $DVAL -gt 10 ]; then
  msg=`hostname`': Disk usage alert: '$DVAL'%'
  curl -X POST --data-urlencode "payload={\"channel\": \"${2}\", \"username\": \"dev.sizebook.jp\", \"text\": \"${msg}  \"}" $1
fi
