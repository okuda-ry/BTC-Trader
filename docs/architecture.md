# アーキテクチャ詳細

## 全体構成図

```
                         ┌──────────────┐
                         │   ブラウザ     │
                         │  Dashboard    │
                         └──────┬───────┘
                                │ HTTP (port 5000)
                         ┌──────▼───────┐
                         │   Flask App   │
                         │   (app.py)    │
                         └──────┬───────┘
                                │ バックグラウンドスレッド
                         ┌──────▼───────┐
                         │ TradeManager  │  ← 全通貨オーケストレーター
                         └──────┬───────┘
              ┌─────────────────┼─────────────────┐
              │                 │                 │
     ┌────────▼──────┐ ┌───────▼───────┐ ┌───────▼───────┐
     │CurrencyTrader │ │CurrencyTrader │ │CurrencyTrader │ ...
     │   ("BTC")     │ │   ("ETH")     │ │   ("XRP")     │
     └───┬───┬───┬───┘ └───────────────┘ └───────────────┘
         │   │   │
         │   │   └── RiskManager("BTC")
         │   │         ├── 損切り/利確判定
         │   │         ├── ポジションサイズ計算
         │   │         └── risk_state.json 永続化
         │   │
         │   └── ai_analyzer
         │         ├── Claude Code CLI (サブスク内無料)
         │         └── Anthropic API (従量課金)
         │
         └── GMOClient (全通貨で共有)
               ├── Public API  (ティッカー, klines)
               └── Private API (残高, 注文, キャンセル)
```

## コンポーネント間のデータフロー

### 1サイクルの実行順序

```
TradeManager.run_once()
│
├── Step 1: 全通貨のローソク足を一括取得
│   for symbol in traders:
│     candles[symbol] = get_candles(symbol)
│     summaries[symbol] = build_summary(candles[symbol])
│
├── Step 2: 各通貨のトレード実行
│   for symbol, trader in traders:
│     other_summaries = {他通貨のサマリ}
│     trader.run_once(
│       other_summaries=other_summaries,
│       prefetched_summary=summaries[symbol]  ← 二重取得防止
│     )
│
└── Step 3: 待機 (TRADE_INTERVAL_SEC)
```

### CurrencyTrader.run_once() の内部フロー

```
run_once()
│
├── 未約定注文あり？ → _check_pending_order() → return
│
├── テクニカル指標の取得（prefetched or 新規取得）
│
├── 残高確認 (GMO API)
│   ├── balance = 当通貨の保有量
│   ├── jpy_balance = JPY残高
│   └── has_position = balance >= min_order_size
│
├── 損切り/利確チェック（AI判断より優先）
│   ├── 損切り → _execute_sell(force_market=True)
│   └── 利確 → _execute_sell()
│
├── AI 分析
│   └── analyze(symbol, summary, balance, other_summaries)
│       → {action, confidence, reason}
│
└── 売買実行（confidence >= 0.6）
    ├── BUY: calc_order_size(jpy, price, balance) → 差分を購入
    └── SELL: _execute_sell(balance, price)
```

## スレッドモデル

```
メインスレッド (Flask)
│
├── HTTP リクエスト処理
│   ├── GET  /           → index.html を返す
│   ├── GET  /api/status → 全通貨の最新状態を JSON で返す
│   ├── POST /api/start  → トレードスレッドを起動
│   └── POST /api/stop   → state["running"] = False
│
└── トレードスレッド (daemon)
    └── _trading_loop()
        └── while state["running"]:
              manager.run_once()
              sleep(TRADE_INTERVAL_SEC)  ← 1秒刻みで running チェック
```

`state["running"]` フラグで停止を制御。sleep は1秒刻みでチェックするため、最大1秒以内に停止する。

## データ永続化

### risk_state.json

```json
{
  "BTC": {
    "entry_price": 15000000,
    "entry_size": 0.00066
  },
  "ETH": {
    "entry_price": 280000,
    "entry_size": 0.035
  }
}
```

- 各 `RiskManager` が `set_entry()` / `clear_entry()` 時に読み書き
- Read-Modify-Write パターン（読み取り失敗時は保存をスキップし、他通貨のデータを保護）

### trader.log

- 全通貨の操作ログを時系列で記録
- `[BTC]`, `[ETH]` 等のプレフィックスで通貨を識別

## エラーハンドリング方針

| レイヤー | 方針 |
|---------|------|
| `TradeManager` | 個別通貨のエラーを catch し、他通貨の処理は継続 |
| `CurrencyTrader` | 未約定注文の確認エラーは3回リトライ後にキャンセル試行 |
| `ai_analyzer` | AI応答のパースエラー/不正値はHOLDにフォールバック |
| `gmo_client` | HTTPエラーは `raise_for_status()` で上位に伝播 |
| `candle_builder` | GMOコイン失敗時は CryptoCompare にフォールバック |
| `risk_manager` | `risk_state.json` 読み取り失敗時は保存スキップ（データ保護） |
