# BTC Auto Trader

GMOコイン API と Claude AI を組み合わせた BTC/JPY 自動売買ウェブアプリケーション。

テクニカル指標（RSI・MACD・ボリンジャーバンド）を計算し、Claude AI に売買判断を委ねる。
指値注文（Post-only）をデフォルトとし、Maker 手数料リベート（-0.01%）を活用する。
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
GMO_API_KEY=あなたのGMOコインAPIキー
GMO_API_SECRET=あなたのGMOコインシークレット
ANALYZER_MODE=cli
```

- **GMOコイン**: [会員ページ](https://coin.z.com/jp/) → API でキーを発行
- **ANALYZER_MODE**: `cli`（Claude Code、サブスク内無料）/ `api`（Anthropic API、従量課金）

## 使い方

### Webアプリケーション（メイン）

```bash
python app.py
```

ブラウザで http://localhost:5000 にアクセスし、ダッシュボードから操作する。

- **Dry Run / LIVE** トグルでモードを切り替え
- **開始 / 停止** ボタンでトレーディングを制御
- テクニカル指標・AI判断・取引履歴・ログがリアルタイムで表示される

### CLI

```bash
# ドライラン（注文は出さない）
python main.py

# 1回だけ分析して終了
python main.py --once

# 本番モード（実際に注文を出す）
python main.py --live
```

## 動作の流れ

1. GMOコインから1時間足ローソクを取得（5日分）
2. テクニカル指標（RSI / MACD / ボリンジャーバンド）を計算
3. ポジション保有中なら損切り・利確をチェック（損切りは成行で即約定）
4. Claude AI にテクニカル指標を渡して BUY / SELL / HOLD を判断
5. 確信度 60% 以上なら指値注文を実行（Post-only で Maker 確定）
6. 15分間隔でループ（未約定の指値は次サイクルでキャンセル → 再判断）

## 設定値

[config.py](config.py) で変更可能。

| 項目 | デフォルト | 説明 |
|------|-----------|------|
| `TRADE_INTERVAL_SEC` | 900（15分） | チェック間隔 |
| `CANDLE_PERIOD_SEC` | 3600（1時間） | ローソク足の期間 |
| `ORDER_TYPE` | LIMIT | 注文方式（LIMIT / MARKET） |
| `LIMIT_OFFSET_PCT` | 0.05% | 指値のオフセット幅 |
| `MAX_POSITION_RATIO` | 10% | 1回の注文で使う残高割合 |
| `STOP_LOSS_PCT` | 2% | 損切りライン |
| `TAKE_PROFIT_PCT` | 4% | 利確ライン |
| `MIN_TRADE_JPY` | 1,000円 | 最小取引額 |

## プロジェクト構成

```
├── app.py               # Flask ウェブアプリケーション
├── main.py              # CLI エントリーポイント
├── config.py            # 設定・環境変数
├── trader.py            # メインのトレードロジック（指値注文対応）
├── gmo_client.py        # GMOコイン REST API クライアント
├── ai_analyzer.py       # Claude による売買判断（CLI / API 切り替え）
├── candle_builder.py    # GMOコイン klines からローソク足取得
├── indicators.py        # テクニカル指標計算
├── risk_manager.py      # リスク管理（損切り/利確/ポジションサイズ/状態永続化）
├── templates/
│   └── index.html       # ダッシュボード画面
└── static/
    └── style.css        # スタイルシート
```

## 注意事項

- 本ボットの利用による損失について、一切の責任を負いません
- まずは Dry Run モードで動作を確認してから使用してください
- LIVE モードは自己責任で使用してください
- PCがスリープすると損切りが発動しないため、稼働中はスリープを無効にしてください
