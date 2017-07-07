# deployer
## create virtualenv

``` shell
mkvirtualenv --no-site-packages deployer -p /usr/bin/python2.7
sudo apt-get install socat  # socatも使ってるので入れておく
```

## bin/をPATHに入れておく
以下のコマンドが使えるように
``` shell
rfab -H localhost ping
```

## test login
```
rfab -i ~/.ssh/hogehgoe.pem  -H ubuntu@52.87.***.*** ping
```

## set AWS EC2
```
rfab -i ~/.ssh/hogehgoe.pem  -H ubuntu@52.87.***.*** setup_aws_ec2:`whoami`
```
上記コマンドで、AWSのインスタンスを初期化する。
1. ユーザーの追加を行う
2. id_rsaの生成
3. authorized_keysに追加
4. sudoersにそのユーザーを追加(adminグループに追加)

※このあとcreate_swapでスワップファイルを作っておいたほうが良い。clamdを入れると大概メモリが不足する

### 実行後
#### ログででてきたものを~/.ssh/configに以下を追加
以下参考

```
host <host alias>
     User username
     Hostname 52.87.***.***
     Port 22
     IdentityFile ~/.ssh/ubuntu_52.87.***.***_id_rsa
     IdentitiesOnly yes
```

#### sshしてみる
```
$ ssh <host alias>

sign_and_send_pubkey: signing failed: agent refused operation

# 上記のエラーが出た場合には以下のコマンド
$ ssh-add ~/.ssh/ubuntu_52.87.***.***_id_rsa # <= 作成されたid_rsa
```


### 最後にデフォルトで作成されるubuntuを削除する
```
$ wfab -H <host alias> user_del:ubuntu
```

## OSのいろいろな設定を行っておく
- ネットワーク周りの設定、不要なサービスのアンインストール
- fluentd、dockerのインストール
- ※AIDE, PSADがまだちゃんと動いていなさそう。。

```
$ ransible <host alias>
```

# rdocker

## single host
``` shell
$ python rdocker <host alias>
# /var/run/docker.sockをトンネルしてローカルに持ってくる
(-> <host>) $ docker ps # <= リモートのdockerに接続!
```

## multiple host

``` shell
$ python rdocker <host alias0> <host alias1> <host alias2>
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

# deperecated
$ orche deploy.yml
```
