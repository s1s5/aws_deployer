#!/bin/sh
# -*- mode: shell-script -*-

set -eu

SLACK_URL={{ SLACK_URL }}
#メッセージを保存する一時ファイル
MESSAGEFILE=$(mktemp -t webhooks.XXXXXXXXXXXXXXXXXXXXX)
trap "
rm -f ${MESSAGEFILE}
" 0

usage_exit() {
    echo "Usage: $0 [-m message] [-c channel] [-i icon] [-n botname]" 1>&2
    exit 0
}

while getopts c:i:n:m: opts
do
    case $opts in
        c)
            CHANNEL=$OPTARG
            ;;
        i)
            FACEICON=$OPTARG
            ;;
        n)
            BOTNAME=$OPTARG
            ;;
        m)
            MESSAGE=$OPTARG"\n"
            ;;
        \?)
            usage_exit
            ;;
    esac
done
#slack 送信チャンネル
CHANNEL=${CHANNEL:-"#alert"}
#slack 送信名
BOTNAME=${BOTNAME:-"$(hostname)[$(cat /etc/machine-id)]"}
#slack アイコン
FACEICON=${FACEICON:-":rotating_light:"}
#見出しとなるようなメッセージ
MESSAGE=${MESSAGE:-""}

if [ -p /dev/stdin ] ; then
    #改行コードをslack用に変換
    cat - | tr '\n' '\\' | sed 's/\\/\\n/g'  > ${MESSAGEFILE}
else
    echo "nothing stdin"
    exit 1
fi

# WEBMESSAGE='```'`cat ${MESSAGEFILE}`'```'
WEBMESSAGE='>>>'`cat ${MESSAGEFILE}`

curl -X POST -H 'Content-Type:application/json' -d "{\"text\":\"${MESSAGE}${WEBMESSAGE}\",\"username\":\"${BOTNAME}\", \"channel\": \"${CHANNEL}\"}" ${SLACK_URL}

rm ${MESSAGEFILE}
