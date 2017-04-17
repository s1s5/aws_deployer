# deployer
## create virtualenv

``` shell
mkvirtualenv --no-site-packages deployer -p /usr/bin/python2.7
```

## bin/をPATHに入れておく
以下のコマンドが使えるように
``` shell
wfab -H localhost ping
```

## test login
```
wfab -i ~/.ssh/hogehgoe.pem  -H ubuntu@52.87.***.*** ping
```

## set AWS EC2
```
wfab -i ~/.ssh/hogehgoe.pem  -H ubuntu@52.87.***.*** setup_aws_ec2:`whoami`
```
上記コマンドで、AWSのインスタンスを初期化する。
1. ユーザーの追加を行う
2. id_rsaの生成
3. authorized_keysに追加
4. sudoersにそのユーザーを追加
5. ubuntuユーザーの削除

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
# このエラーが出た場合には以下のコマンド
$ ssh-add ~/.ssh/ubuntu_52.87.***.***_id_rsa # <= 作成されたid_rsa
```


### 最後にデフォルトで作成されるubuntuを削除する
```
$ wfab -H <host alias> user_del:ubuntu
```

## OSのいろいろな設定を行っておく

```
$ 
```
