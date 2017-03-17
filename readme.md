# deployer
## test login
- fab -i ~/.ssh/lifecard_akb.pem  -H ubuntu@52.87.169.26 ping

## set AWS EC2
AWSのインスタンスを初期化する。
1. ユーザーの追加を行う
2. id_rsaの生成
3. authorized_keysに追加
4. sudoersにそのユーザーを追加
5. ubuntuユーザーの削除

### 実行後
#### ~/.ssh/configに以下を追加
```
host <host alias>
     User sawai
     Hostname 52.87.169.26
     Port 22
     IdentityFile ~/.ssh/ubuntu_52.87.169.26_id_rsa
     IdentitiesOnly yes
```

#### sshしてみる
```
$ ssh <host alias>
sign_and_send_pubkey: signing failed: agent refused operation
# このエラーが出た場合には以下のコマンド
$ ssh-add ~/.ssh/ubuntu_52.87.169.26_id_rsa # <= 作成されたid_rsa
```


### 最後にデフォルトで作成されるubuntuを削除する
$ fab -H <host alias> user_del:ubuntu
