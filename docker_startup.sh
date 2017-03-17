#!/bin/bash
# -*- mode: shell-script -*-

set -eu  # <= 0以外が返るものがあったら止まる, 未定義の変数を使おうとしたときに打ち止め
groupadd -g $GROUP_ID $USER_NAME
useradd -u $USER_ID -g $GROUP_ID $USER_NAME

touch /tmp/startup_process_ended

su - $USER_NAME -c "$*"
