#!/bin/bash
# -*- mode: shell-script -*-

set -eu  # <= 0以外が返るものがあったら止まる, 未定義の変数を使おうとしたときに打ち止め

flag="false"
for i in `/bin/df | /usr/bin/tail -n +2 | /bin/sed 's/^.* \([0-9]*\)%.*$/\1/'`; do
    if [ ${i} -gt 80 ]; then
        flag="true"
    fi
done

if [ ${flag} = "true" ]; then
    df | /usr/local/bin/alert_to_slack.sh -m "Disk usage alert"
fi
