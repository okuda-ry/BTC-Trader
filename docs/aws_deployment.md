# AWS デプロイ手順

EC2 無料枠（t3.micro）を使ったデプロイ手順。

---

## 1. EC2 インスタンスの作成

AWS Management Console → EC2 → 「インスタンスを起動」

### 設定値

| 項目 | 値 |
|------|-----|
| 名前 | `crypto-trader` |
| AMI | **Ubuntu Server 24.04 LTS** (64-bit, x86) |
| インスタンスタイプ | **t3.micro** (無料枠対象) |
| キーペア | 新しいキーペアを作成 → `crypto-trader-key` → RSA → .pem |
| ストレージ | 8 GiB gp3（デフォルト、無料枠内） |

### セキュリティグループの設定

「セキュリティグループを作成」を選択し、以下のルールを追加:

| タイプ | ポート | ソース | 用途 |
|--------|--------|--------|------|
| SSH | 22 | マイIP | SSH接続 |
| カスタムTCP | 5000 | マイIP | ダッシュボード |

> **「マイIP」を選ぶこと。** 「0.0.0.0/0（全開放）」にするとダッシュボードが誰でもアクセスできてしまう。

「インスタンスを起動」をクリック。

---

## 2. キーペアの準備（ローカルPC）

ダウンロードした `.pem` ファイルをホームディレクトリの `.ssh` フォルダに移動:

```bash
# Windows (Git Bash / WSL)
mkdir -p ~/.ssh
mv ~/Downloads/crypto-trader-key.pem ~/.ssh/
chmod 400 ~/.ssh/crypto-trader-key.pem
```

---

## 3. EC2 に接続

EC2 コンソールでインスタンスの「パブリック IPv4 アドレス」を確認。

```bash
ssh -i ~/.ssh/crypto-trader-key.pem ubuntu@<パブリックIP>
```

> 接続できない場合: セキュリティグループで SSH (22番ポート) が自分のIPに開いているか確認。

---

## 4. セットアップスクリプトの実行

```bash
# リポジトリをクローン
git clone https://github.com/okuda-ry/BTC-Trader.git
cd BTC-Trader

# セットアップスクリプトを実行
chmod +x deploy/setup.sh
./deploy/setup.sh
```

これで Python, Node.js, Claude Code CLI, 依存パッケージ, systemd サービスが自動でセットアップされる。

---

## 5. 環境変数の設定

```bash
nano /home/ubuntu/BTC-Trader/.env
```

以下を入力:

```env
GMO_API_KEY=あなたのGMOコインAPIキー
GMO_API_SECRET=あなたのGMOコインシークレット
ANALYZER_MODE=cli
```

`Ctrl+O` → Enter → `Ctrl+X` で保存して閉じる。

---

## 6. Claude Code の認証

```bash
claude auth login
```

ヘッドレス環境の場合、表示されるURLをローカルPCのブラウザで開いて認証する。

> **注意**: t3.micro (1GB RAM) では Claude Code CLI のメモリが不足する場合がある。
> その場合は `ANALYZER_MODE=api` に切り替え、`ANTHROPIC_API_KEY` を設定する。

### スワップファイルの追加（メモリ不足対策）

```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

これで実質2GBのメモリが使える。

---

## 7. 動作確認

```bash
cd /home/ubuntu/BTC-Trader
source venv/bin/activate
python app.py
```

ローカルPCのブラウザで `http://<パブリックIP>:5000` にアクセスし、ダッシュボードが表示されることを確認。

確認できたら `Ctrl+C` で停止。

---

## 8. サービスとして起動

```bash
# 起動
sudo systemctl start crypto-trader

# 状態確認
sudo systemctl status crypto-trader

# ログをリアルタイムで確認
sudo journalctl -u crypto-trader -f
```

**これでSSH接続を切ってもボットが動き続ける。**

---

## 運用コマンド集

```bash
# サービス停止
sudo systemctl stop crypto-trader

# サービス再起動
sudo systemctl restart crypto-trader

# ログの確認（直近100行）
sudo journalctl -u crypto-trader -n 100

# アプリの更新
cd /home/ubuntu/BTC-Trader
git pull
sudo systemctl restart crypto-trader

# トレードログの確認
cat /home/ubuntu/BTC-Trader/trader.log
tail -f /home/ubuntu/BTC-Trader/trader.log
```

---

## IPアドレスが変わる問題

EC2 を再起動するとパブリックIPが変わる。対策:

### Elastic IP（無料枠内）

1. EC2 コンソール → Elastic IP → 「Elastic IP アドレスを割り当てる」
2. 割り当てたIPを選択 → 「アクション」→「Elastic IP アドレスの関連付け」
3. 作成したインスタンスを選択

> Elastic IP は **インスタンスに関連付けている間は無料**。
> 関連付けを外したまま放置すると課金されるので注意。

---

## コストまとめ（無料枠）

| リソース | 無料枠 | 超過時の月額 |
|---------|--------|------------|
| EC2 t3.micro | 12ヶ月 750時間/月 | 約 ¥1,200/月 |
| EBS 8GB gp3 | 12ヶ月 30GB | 数十円/月 |
| Elastic IP | インスタンス稼働中は無料 | ¥500/月 |
| データ転送 | 100GB/月 | 微量 |

**12ヶ月間は実質無料で運用可能。**

---

## トラブルシューティング

### ダッシュボードにアクセスできない

1. セキュリティグループで 5000 番ポートが開いているか確認
2. ソースが「マイIP」になっている場合、IPが変わっていないか確認
3. `sudo systemctl status crypto-trader` でサービスが動いているか確認

### Claude Code CLI がメモリ不足で落ちる

```bash
# スワップが有効か確認
free -h

# スワップがなければ追加（上記の手順を参照）
```

それでもダメなら `ANALYZER_MODE=api` に切り替える。

### サービスが起動しない

```bash
# 詳細ログを確認
sudo journalctl -u crypto-trader -n 50 --no-pager

# 手動で実行してエラーを確認
cd /home/ubuntu/BTC-Trader
source venv/bin/activate
python app.py
```

### Git pull で競合が起きる

```bash
cd /home/ubuntu/BTC-Trader
git stash        # ローカル変更を退避
git pull
git stash pop    # 退避した変更を戻す
sudo systemctl restart crypto-trader
```
