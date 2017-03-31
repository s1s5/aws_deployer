#!/bin/bash
# -*- mode: shell-script -*-

set -eu  # <= 0以外が返るものがあったら止まる, 未定義の変数を使おうとしたときに打ち止め
echo "${USER_NAME}:x:${GROUP_ID}:" > /etc/group
echo "${USER_NAME}:x:${USER_ID}:${GROUP_ID}::/home/${USER_NAME}:/bin/sh" > /etc/passwd

touch /tmp/startup_process_ended

su - $USER_NAME -c "$*"
