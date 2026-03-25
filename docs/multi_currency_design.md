# マルチ通貨対応 外部設計書

> **ステータス: 実装済み** (2026-03-25)
> 本設計書に基づき、BTC / ETH / XRP / SOL の4通貨同時運用を実装完了。
> 実装の詳細は [architecture.md](architecture.md) を参照。

## 1. 概要

現在 BTC/JPY 単一通貨で運用しているトレーディングボットを、複数の暗号資産で同時運用できるように拡張する。

### 対象通貨（有名銘柄を優先選定）

GMOコイン取引所（現物）で取扱いのある19銘柄のうち、時価総額・流動性の高い以下の銘柄を対象とする。

| 優先度 | シンボル | 銘柄 | 最小注文 | 選定理由 |
|--------|---------|------|---------|---------|
| ★★★ | BTC | ビットコイン | 0.00001 | 基軸通貨、流動性最大 |
| ★★★ | ETH | イーサリアム | 0.001 | 時価総額2位、DeFi基盤 |
| ★★★ | XRP | リップル | 1 | 国内人気高、流動性高 |
| ★★★ | SOL | ソラナ | 0.01 | 成長著しい、高速チェーン |
| ★★☆ | DOGE | ドージコイン | 10 | ミーム系代表、ボラティリティ高 |
| ★★☆ | ADA | カルダノ | 1 | 安定した時価総額 |
| ★★☆ | DOT | ポルカドット | 0.1 | マルチチェーン基盤 |
| ★★☆ | LINK | チェーンリンク | 0.1 | オラクル領域の代表格 |
| ★☆☆ | ATOM | コスモス | 0.01 | IBC エコシステム |
| ★☆☆ | LTC | ライトコイン | 0.1 | 老舗アルトコイン |

> ★★★ から段階的に対応する。FCR, NAC, WILD 等のマイナー銘柄は流動性リスクが高いため対象外とする。

---

## 2. 現状のアーキテクチャと課題

### 現状（単一通貨）

```
app.py → Trader (1インスタンス) → GMOClient
              ↓                       ↓
         RiskManager (1)         config.PRODUCT_CODE = "BTC"
```

### 課題

| # | 課題 | 影響 |
|---|------|------|
| 1 | `PRODUCT_CODE` がグローバル定数 | 通貨ごとに切り替えられない |
| 2 | Trader が1インスタンス | 複数通貨を同時に回せない |
| 3 | RiskManager のエントリー価格が1つ | 通貨ごとの損益管理ができない |
| 4 | risk_state.json が単一エントリー | 再起動時に1通貨分しか復元できない |
| 5 | ダッシュボードが1通貨前提 | 複数通貨の状態を表示できない |
| 6 | 全体のリスク管理がない | 通貨横断の投入額上限がない |

---

## 3. 拡張後のアーキテクチャ

### 全体構成

```
app.py (Flask)
  │
  ├── TradeManager (新規：全体管理)
  │     │
  │     ├── CurrencyTrader("BTC")  ← 通貨ごとのTrader
  │     │     ├── GMOClient (共有)
  │     │     ├── RiskManager("BTC")
  │     │     └── 個別設定 (最小注文量, etc.)
  │     │
  │     ├── CurrencyTrader("ETH")
  │     │     ├── GMOClient (共有)
  │     │     ├── RiskManager("ETH")
  │     │     └── 個別設定
  │     │
  │     ├── CurrencyTrader("SOL")
  │     │     └── ...
  │     │
  │     └── PortfolioRiskManager (新規：全体リスク管理)
  │
  └── Dashboard (通貨切り替え表示)
```

### コンポーネント説明

| コンポーネント | 役割 |
|---------------|------|
| **TradeManager** | 全通貨の Trader を管理し、ループを制御する |
| **CurrencyTrader** | 現在の Trader を通貨パラメータ化したもの |
| **PortfolioRiskManager** | 全体の投入額上限・通貨間のリスク分散を管理 |
| **GMOClient** | 全通貨で1インスタンスを共有（API レート制限対策） |

---

## 4. 設定の設計

### currencies.json（新規）

通貨ごとの設定を外部ファイルで管理する。

```json
{
  "currencies": [
    {
      "symbol": "BTC",
      "enabled": true,
      "min_order_size": 0.00001,
      "size_decimals": 5,
      "max_position_ratio": 0.10,
      "stop_loss_pct": 0.02,
      "take_profit_pct": 0.04
    },
    {
      "symbol": "ETH",
      "enabled": true,
      "min_order_size": 0.001,
      "size_decimals": 4,
      "max_position_ratio": 0.08,
      "stop_loss_pct": 0.03,
      "take_profit_pct": 0.05
    },
    {
      "symbol": "XRP",
      "enabled": false,
      "min_order_size": 1,
      "size_decimals": 0,
      "max_position_ratio": 0.05,
      "stop_loss_pct": 0.03,
      "take_profit_pct": 0.06
    }
  ],
  "global": {
    "max_total_position_ratio": 0.40,
    "max_concurrent_positions": 3,
    "trade_interval_sec": 900,
    "order_type": "LIMIT",
    "analyzer_mode": "cli"
  }
}
```

### 設定項目の説明

| 項目 | 説明 |
|------|------|
| `enabled` | この通貨の自動売買を有効にするか |
| `min_order_size` | GMOコインの最小注文単位 |
| `size_decimals` | 注文数量の小数桁数 |
| `max_position_ratio` | この通貨に使う残高の最大割合 |
| `stop_loss_pct` / `take_profit_pct` | 通貨ごとの損切り/利確ライン |
| `max_total_position_ratio` | 全通貨合計のリスク上限（残高の40%まで） |
| `max_concurrent_positions` | 同時にポジションを持てる通貨数 |

---

## 5. 処理フローの設計

### 5.1 メインループ

```
毎サイクル（15分ごと）:
  1. 全通貨の未約定注文をチェック
  2. for 通貨 in 有効な通貨リスト:
       a. ローソク足を取得
       b. テクニカル指標を計算
       c. 損切り/利確チェック
       d. ポートフォリオリスクチェック ← 新規
       e. Claude AI に分析を依頼
       f. 注文を実行
  3. 一定間隔で待機
```

### 5.2 ポートフォリオリスク判定（新規）

```
新規ポジションを取る前に:
  1. 現在の全ポジション数 >= max_concurrent_positions → スキップ
  2. 現在の全投入額 / JPY残高 >= max_total_position_ratio → スキップ
  3. 同一通貨のポジションが既にある → スキップ（現行どおり）
```

### 5.3 AI 分析の変更点

AI に渡す情報に「他通貨の状況」を追加し、相関を考慮した判断を可能にする。

```
現在のプロンプト:
  "BTC/JPY RSI=35, MACD=..."

拡張後のプロンプト:
  "対象通貨: ETH/JPY RSI=42, MACD=..."
  "参考情報: BTC/JPY RSI=35 (ポジションあり), SOL/JPY RSI=28"
```

> BTC が下落局面のときにアルトも連動して下がる傾向があるため、
> 他通貨の状況を参考情報として渡すことで判断精度の向上を期待する。

---

## 6. データ永続化の設計

### risk_state.json の拡張

```json
{
  "positions": {
    "BTC": {
      "entry_price": 11500000,
      "entry_time": "2026-03-24T10:30:00Z",
      "size": 0.00091
    },
    "ETH": {
      "entry_price": 280000,
      "entry_time": "2026-03-24T11:00:00Z",
      "size": 0.035
    }
  },
  "pending_orders": {
    "SOL": {
      "order_id": "123456",
      "side": "BUY",
      "placed_at": "2026-03-24T11:15:00Z"
    }
  }
}
```

---

## 7. ダッシュボードの設計

### レイアウト変更

```
┌─────────────────────────────────────────────────┐
│ BTC Auto Trader            [Dry Run] [開始][停止] │
├─────────────────────────────────────────────────┤
│ ポートフォリオ概要                                  │
│  JPY残高: ¥85,200  投入中: ¥14,800 (14.8%)        │
│  ポジション: 2/3                                   │
├──────────┬──────────┬───────────────────────────┤
│ [BTC]    │ [ETH]    │ [SOL]  [XRP]  [DOGE]      │
│ (選択中)  │          │ (無効はグレーアウト)          │
├──────────┴──────────┴───────────────────────────┤
│ ← 選択中の通貨の詳細（現行と同じ） →                  │
│  価格 / RSI / MACD / BB / AI判断 / 取引履歴         │
├─────────────────────────────────────────────────┤
│ ログ（全通貨共通、通貨名がプレフィックスに付く）         │
└─────────────────────────────────────────────────┘
```

### API 変更

| エンドポイント | 変更内容 |
|---------------|---------|
| `GET /api/status` | 全通貨の状態を返す |
| `GET /api/status/<symbol>` | 新規：特定通貨の詳細 |
| `POST /api/start` | 全有効通貨のトレーディングを開始 |
| `POST /api/currency/<symbol>/enable` | 新規：通貨の有効/無効切り替え |
| `GET /api/portfolio` | 新規：ポートフォリオ全体の状態 |

---

## 8. ファイル構成（変更後）

```
├── app.py                  # Flask アプリ（ポートフォリオ対応）
├── main.py                 # CLI エントリーポイント
├── config.py               # グローバル設定
├── currencies.json         # 通貨ごとの設定（新規）
├── trade_manager.py        # 全通貨を管理するオーケストレーター（新規）
├── currency_trader.py      # 通貨ごとのトレードロジック（trader.py を改名・拡張）
├── portfolio_risk.py       # ポートフォリオ全体のリスク管理（新規）
├── gmo_client.py           # GMOコイン API クライアント（変更なし）
├── ai_analyzer.py          # Claude 分析（マルチ通貨プロンプト対応）
├── candle_builder.py       # ローソク足取得（シンボルをパラメータ化）
├── indicators.py           # テクニカル指標計算（変更なし）
├── risk_manager.py         # 通貨単位のリスク管理（設定を外部から受け取る）
├── risk_state.json         # 全通貨のポジション永続化
├── templates/
│   └── index.html          # ダッシュボード（タブ切り替え対応）
├── static/
│   └── style.css
└── docs/
    └── multi_currency_design.md  # この設計書
```

---

## 9. 段階的な実装計画

### Phase 1: 基盤リファクタリング

- `PRODUCT_CODE` のハードコード排除（関数引数化）
- `currencies.json` の読み込み機構
- `RiskManager` に通貨シンボルを渡せるようにする
- `candle_builder` にシンボルを渡せるようにする

### Phase 2: マルチ通貨エンジン

- `CurrencyTrader` の実装（Trader をパラメータ化）
- `TradeManager` の実装（ループ制御）
- `PortfolioRiskManager` の実装
- `risk_state.json` のマルチ通貨対応

### Phase 3: AI 分析の強化

- プロンプトに他通貨の状況を追加
- 通貨間の相関を考慮した判断

### Phase 4: ダッシュボード対応

- 通貨タブの追加
- ポートフォリオ概要セクション
- 通貨ごとの有効/無効トグル
- API エンドポイントの拡張

---

## 10. リスクと注意点

| リスク | 対策 |
|--------|------|
| API レート制限（20 req/sec） | GMOClient を共有し、通貨間でリクエストを時間分散 |
| Claude Code のレート制限 | 通貨数 × 15分間隔 → 4通貨で1時間16回。間隔の調整が必要になる可能性 |
| アルトの流動性不足 | 最小取引額チェックに加え、板の厚さ確認を検討 |
| 通貨間の相関リスク | BTC 急落時に全通貨が連動下落 → `max_concurrent_positions` で制限 |
| 設定ミス | `currencies.json` のバリデーションを起動時に実行 |
