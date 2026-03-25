#!/bin/bash
# ============================================
# Crypto Auto Trader - EC2 初期セットアップ
# Ubuntu 24.04 LTS 用
# ============================================
set -e

echo "========================================="
echo "  Crypto Auto Trader セットアップ開始"
echo "========================================="

# --- システムパッケージ ---
echo "[1/5] システムパッケージをインストール中..."
sudo apt update -y
sudo apt install -y python3-pip python3-venv git

# --- Node.js (Claude Code CLI 用) ---
echo "[2/5] Node.js をインストール中..."
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
    sudo apt install -y nodejs
fi
echo "  Node.js $(node -v)"

# --- Claude Code CLI ---
echo "[3/5] Claude Code CLI をインストール中..."
if ! command -v claude &> /dev/null; then
    sudo npm install -g @anthropic-ai/claude-code
fi
echo "  Claude Code インストール完了"

# --- アプリケーション ---
echo "[4/5] アプリケーションをセットアップ中..."
cd /home/ubuntu

if [ ! -d "BTC-Trader" ]; then
    git clone https://github.com/okuda-ry/BTC-Trader.git
fi

cd BTC-Trader
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# --- .env ファイル ---
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "========================================="
    echo "  .env ファイルを編集してください:"
    echo "  nano /home/ubuntu/BTC-Trader/.env"
    echo "========================================="
fi

# --- systemd サービス ---
echo "[5/5] systemd サービスを登録中..."
sudo cp /home/ubuntu/BTC-Trader/deploy/crypto-trader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable crypto-trader

echo ""
echo "========================================="
echo "  セットアップ完了!"
echo ""
echo "  次のステップ:"
echo "  1. .env を編集:  nano /home/ubuntu/BTC-Trader/.env"
echo "  2. Claude 認証:  claude auth login"
echo "  3. サービス起動:  sudo systemctl start crypto-trader"
echo "  4. ログ確認:      sudo journalctl -u crypto-trader -f"
echo "========================================="
