# BTC Auto Trader

bitFlyer API と Claude AI を組み合わせた BTC/JPY 自動売買ウェブアプリケーション。

テクニカル指標（RSI・MACD・ボリンジャーバンド）を計算し、Claude AI に売買判断を委ねる。
ブラウザ上のダッシュボードからトレーディングの開始・停止、リアルタイムモニタリングが可能。

## セットアップ

```bash
# 仮想環境の作成・有効化
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# パッケージインストール
pip install -r requirements.txt
```

## APIキーの設定

`.env.example` をコピーして `.env` を作成し、キーを設定する。

```bash
cp .env.example .env
```

```
BITFLYER_API_KEY=あなたのbitFlyerキー
BITFLYER_API_SECRET=あなたのbitFlyerシークレット
ANTHROPIC_API_KEY=あなたのAnthropicキー
```

- **bitFlyer**: [bitFlyer Lightning](https://lightning.bitflyer.com/developer) でAPIキーを発行
- **Anthropic**: [Anthropic Console](https://console.anthropic.com/) でAPIキーを取得

## 使い方

### Webアプリケーション（メイン）

```bash
python app.py
```

ブラウザで http://localhost:5000 にアクセスし、ダッシュボードから操作する。

- **Dry Run / LIVE** トグルでモードを切り替え
- **開始 / 停止** ボタンでトレーディングを制御
- テクニカル指標・AI判断・取引履歴・ログがリアルタイムで表示される

### CLI（従来方式）

```bash
# ドライラン（注文は出さない）
python main.py

# 1回だけ分析して終了
python main.py --once

# 本番モード（実際に注文を出す）
python main.py --live
```

## 動作の流れ

1. bitFlyer から約定履歴を取得し、1時間足ローソクを生成
2. テクニカル指標（RSI / MACD / ボリンジャーバンド）を計算
3. ポジション保有中なら損切り・利確をチェック
4. Claude AI にテクニカル指標を渡して BUY / SELL / HOLD を判断
5. 確信度 60% 以上なら注文を実行
6. 15分間隔でループ

## 設定値

[config.py](config.py) で変更可能。

| 項目 | デフォルト | 説明 |
|------|-----------|------|
| `TRADE_INTERVAL_SEC` | 900（15分） | チェック間隔 |
| `CANDLE_PERIOD_SEC` | 3600（1時間） | ローソク足の期間 |
| `MAX_POSITION_RATIO` | 10% | 1回の注文で使う残高割合 |
| `STOP_LOSS_PCT` | 2% | 損切りライン |
| `TAKE_PROFIT_PCT` | 4% | 利確ライン |
| `MIN_TRADE_JPY` | ¥1,000 | 最小取引額 |

## プロジェクト構成

```
├── app.py               # Flask ウェブアプリケーション
├── main.py              # CLI エントリーポイント
├── config.py            # 設定・環境変数
├── trader.py            # メインのトレードロジック
├── ai_analyzer.py       # Claude API による売買判断
├── bitflyer_client.py   # bitFlyer REST API クライアント
├── candle_builder.py    # 約定履歴 → ローソク足変換
├── indicators.py        # テクニカル指標計算
├── risk_manager.py      # リスク管理（損切り/利確/ポジションサイズ）
├── templates/
│   └── index.html       # ダッシュボード画面
└── static/
    └── style.css        # スタイルシート
```

## 注意事項

- 本ボットの利用による損失について、一切の責任を負いません
- まずは Dry Run モードで動作を確認してから使用してください
- LIVE モードは自己責任で使用してください
