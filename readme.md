# deployer
# create virtualenv

``` shell
mkvirtualenv --no-site-packages deployer -p /usr/bin/python2.7
# 利用するパッケージのインストール
sudo apt-get install python-dev libssl-dev
```

# 初期設定
## bin/をPATHに入れておく
``` shell
# @~/.bashrc
# PATHを追加しておく
## e.g) export PATH="$PATH:${HOME}/work/deployer/bin"
export PATH="$PATH:<deployer install dir>/bin"


## 以下のコマンドが使えるように
$ rfab -H localhost ping
```

### bash_completeを使いたい場合

``` shell
_ssh_config ()
{
    COMPREPLY+=( $(compgen -W "$(grep "host " ~/.ssh/config  | egrep -v "^#" | awk '{print $2}')" ${COMP_WORDS[COMP_CWORD]} ) )
}
complete -F _ssh_config ransible rdocker docker-connect docker-disconnect
```

# パッケージのインストール等
- ネットワーク周りの設定、不要なサービスのアンインストール
- fluentd、dockerのインストール
- ※AIDE, PSADがまだちゃんと動いていなさそう。。
- ※clamdを入れると大概メモリが不足するので1GBのswapfileが自動生成される
```
$ ransible <host alias>

$ ransible -s <slack_url> <host alias>
# slack_urlを追加すると/usr/local/bin/alert_to_slack.shが追加される
```

## test login
```
rfab -i ~/.ssh/hogehgoe.pem  -H ubuntu@52.87.***.*** ping
```

# ユーザーの登録、デフォルトユーザーの削除
```
rfab -i ~/.ssh/hogehgoe.pem  -H ubuntu@52.87.***.*** setup_aws_ec2:`whoami`
```
上記コマンドで、AWSのインスタンスを初期化する。
1. ユーザーの追加を行う
2. id_rsaの生成
3. authorized_keysに追加
4. sudoersにそのユーザーを追加(adminグループに追加)


## 実行後
### ログででてきたものを~/.ssh/configに以下を追加
以下参考

```
host <host alias>
     User username
     Hostname 52.87.***.***
     Port 22
     IdentityFile ~/.ssh/ubuntu_52.87.***.***_id_rsa
     IdentitiesOnly yes
```

### sshしてみる
```
$ ssh <host alias>

sign_and_send_pubkey: signing failed: agent refused operation

# 上記のエラーが出た場合には以下のコマンド
$ ssh-add ~/.ssh/ubuntu_52.87.***.***_id_rsa # <= 作成されたid_rsa
```


## 最後にデフォルトで作成されるubuntuを削除する
```
$ rfab -H <host alias> user_del:ubuntu
```

## ユーザー作成
```
$ rfab -H <host alias> user_add:<user name>,<id_rsa path>
```

# rdocker
``` shell
# exec rdocker, connect to other host
$ rdocker <host alias>
export DOCKER_HOST=unix:///tmp/docker-sawai/cluster_001.sock

# set DOCKER_HOST environment variable
$ eval `rdocker <host alias>`
$ docker info  # remote hostのdockerサーバーに繋がる

# - ローカルにもどる
$ unset DOCKER_HOST
$ eval `rdocker`

# - docker groupに所属している必要があるので、所属していない場合、以下を実行しておく
$ sudo usermod -G `id -Gn | sed s'/ /,/'g`,docker `whoami`

# - set your own alias
$ alias docker-gateway='docker -H `rdocker -H cluster_gateway`'
```

## うまく動作しない場合
``` shell
$ docker-tunnel <host alias>

# 別のターミナルで
$ docker -H unix:///tmp/docker-<user>/<host alias>.sock ...
```

``` shell
$ ssh -f -N -L /tmp/<host alias>.sock:/var/run/docker.sock <host alias>

# 下記どちらかで接続できるようになる
$ docker -H unix:///tmp/<host alias>.sock ...

$ export DOCKER_HOST=unix:///tmp/<host alias>.sock
$ docker ...
```

# dc-deploy

``` yaml
project: "<myproject>"

hosts:
  <host alias>:         # ssh <host alias>
    ip: "192.168.3.12"  # ホスト間のIPアドレス
    services:           # このホストに立てるサービス一覧
      web:
      web_back:
      web_admin:
      redis:
  subuntu1:             # 別のホストで別のサービスを立てる
    services:
      web_front:
      db:
      log_proxy:
      web_backup:
      db_backup:

compose_context: .  # docker composeファイルの起動ディレクトリ
compose_files:      # docker composeファイル一覧
  - docker-compose.yml
  - docker-compose.prod.yml
  - docker-compose.prod.localvm.yml

override:  # docker compose設定を上書きする時はココになんか書く
  all:
    restart: "no"
    environment:
      - APPLICATION_URL_SP=hogehoge
      - ALLOWED_HOSTS=["*", ]
      - SEND_ERROR_EMAILS=False
    logging:
      driver: fluentd
      options:
        fluentd-address: "127.0.0.1:26226"
        tag: docker.{{.Name}}
  log_proxy:   # 特定のサービスの設定の上書き
    logging:
      driver: "json-file"
```

- 上のようなdeploy.ymlを用意する

``` shell
$ dc-deploy deploy.yml
```

# ディスク容量が10%切ったらslackへ報告するshを追加する
```$ rfab install_disk_usage_alert:[slack webhook url],[channel],[監視するディスク] -H [hostname]```

/etc/crontabに登録され、のこり30分おきにディスク容量をチェックし10%切ったら指定されたslack urlにメッセージを飛ばす。
- [slack webhook url] slackのwebhookのURL(省略不可)
- [channel] slack channel 省略時 #random
- [監視するディスク] 省略時 /
