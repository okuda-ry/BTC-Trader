# GMOコイン API リファレンス

本システムで使用しているGMOコイン REST API のエンドポイントと注意点。

公式ドキュメント: https://api.coin.z.com/docs/

---

## 認証方式

Private API には HMAC-SHA256 認証が必要。

### ヘッダー構成

| ヘッダー | 値 |
|---------|-----|
| `API-KEY` | 発行されたAPIキー |
| `API-TIMESTAMP` | リクエスト時刻（ミリ秒） |
| `API-SIGN` | HMAC-SHA256 署名 |
| `Content-Type` | `application/json` |

### 署名の生成

```
text = timestamp + method + path + body
sign = HMAC-SHA256(secret, text)
```

- `timestamp`: ミリ秒単位の Unix タイムスタンプ（文字列）
- `method`: `GET` or `POST`
- `path`: `/v1/order` 等（ホスト部分を含まない）
- `body`: POST時のリクエストボディ（JSON文字列）。GETの場合は空文字

---

## 使用エンドポイント

### Public API

Base URL: `https://api.coin.z.com/public`

#### GET /v1/ticker

最新のティッカー情報を取得。

```
パラメータ: symbol=BTC
レスポンス:
{
  "status": 0,
  "data": [{
    "ask": "15000000",
    "bid": "14999000",
    "high": "15100000",
    "low": "14800000",
    "last": "14999500",
    "symbol": "BTC",
    "volume": "123.456"
  }]
}
```

#### GET /v1/klines

ローソク足データを取得。

```
パラメータ:
  symbol   = BTC
  interval = 1hour (1min, 5min, 10min, 15min, 30min, 1hour, 4hour, 8hour, 12hour, 1day)
  date     = 20260325 (YYYYMMDD, UTC基準)

レスポンス:
{
  "status": 0,
  "data": [{
    "openTime": "1711324800000",
    "open": "14900000",
    "high": "15000000",
    "low": "14850000",
    "close": "14980000",
    "volume": "12.345"
  }, ...]
}
```

**注意点:**
- `date` パラメータは必須。1日分のデータのみ返す
- 100本以上のデータが必要な場合は複数日分をリクエストする必要がある
- `openTime` はミリ秒単位のUnixタイムスタンプ
- 日付はUTC基準（JST-9時間）

### Private API

Base URL: `https://api.coin.z.com/private`

#### GET /v1/account/assets

全資産の残高を取得。

```
レスポンス:
{
  "status": 0,
  "data": [
    {"symbol": "JPY", "amount": "100000", "available": "85000"},
    {"symbol": "BTC", "amount": "0.00066", "available": "0.00066"},
    ...
  ]
}
```

- `amount`: 総残高
- `available`: 利用可能残高（注文中の分を除く）

#### POST /v1/order

新規注文を送信。

```
ボディ:
{
  "symbol": "BTC",
  "side": "BUY",
  "executionType": "LIMIT",
  "size": "0.00066",
  "price": "14990000"
}

レスポンス:
{
  "status": 0,
  "data": "123456789"  ← orderId
}
```

**パラメータ詳細:**

| パラメータ | 値 | 説明 |
|-----------|-----|------|
| `symbol` | `BTC`, `ETH`, `XRP`, `SOL` | 現物のシンボル（`BTC_JPY` はレバレッジ） |
| `side` | `BUY`, `SELL` | 売買方向 |
| `executionType` | `MARKET`, `LIMIT` | 注文タイプ |
| `size` | 文字列 | 注文数量 |
| `price` | 文字列 | 指値価格（LIMIT時のみ） |
| `timeInForce` | `FAS`, `FAK`, `FOK`, `SOK` | 執行条件（省略時はFAS） |

**timeInForce の種類:**

| 値 | 名称 | 動作 | 本システムでの使用 |
|----|------|------|------------------|
| `FAS` | Fill And Store | 約定しなかった分は板に残る | **使用中（デフォルト）** |
| `FAK` | Fill And Kill | 約定しなかった分は即キャンセル | 未使用 |
| `FOK` | Fill Or Kill | 全量約定しなければ全キャンセル | 未使用 |
| `SOK` | Store Or Kill (Post-only) | Takerになる場合は即キャンセル | **使用しない**（※） |

> ※ SOK は Maker 確定だが、スプレッドが狭い時に即キャンセルされるリスクが高く、連続注文の原因となるため FAS を採用。

#### GET /v1/orders

注文の状態を確認。

```
パラメータ: orderId=123456789

レスポンス:
{
  "status": 0,
  "data": {
    "list": [{
      "orderId": 123456789,
      "symbol": "BTC",
      "side": "BUY",
      "executionType": "LIMIT",
      "status": "EXECUTED",
      "price": "14990000",
      "size": "0.00066",
      "executedSize": "0.00066",
      "timestamp": "2026-03-25T10:30:00.000Z"
    }]
  }
}
```

**ステータス:**

| status | 意味 | 本システムの対応 |
|--------|------|---------------|
| `WAITING` | 注文受付済み（未約定） | キャンセル |
| `ORDERED` | 板に乗った（未約定） | キャンセル |
| `EXECUTED` | 全量約定 | ポジション更新 |
| `CANCELED` | キャンセル済み | 部分約定があれば反映 |
| `EXPIRED` | 期限切れ | 部分約定があれば反映 |

#### POST /v1/cancelOrder

注文をキャンセル。

```
ボディ:
{
  "orderId": 123456789
}
```

---

## 手数料

| 種類 | Maker | Taker |
|------|-------|-------|
| 現物取引 | **-0.01%（リベート）** | 0.05% |
| 入出金 | 無料 | - |

本システムは指値注文（Maker）をデフォルトとし、手数料リベートを活用する。

---

## レート制限

- Private API: **1秒あたり10回**
- Public API: **1秒あたり10回**

本システムは4通貨を順次処理するため、通常運用ではレート制限に抵触しない。

---

## 注意点

1. **シンボル名**: 現物は `BTC`, `ETH` 等。`BTC_JPY` はレバレッジ取引のシンボルなので注意
2. **数値は文字列**: 注文のsize, priceは文字列で送信する必要がある
3. **タイムスタンプ**: 認証のタイムスタンプはミリ秒単位
4. **klines の日付**: UTC基準のYYYYMMDD形式。日本時間との差に注意
5. **部分約定**: LIMIT注文は部分約定する可能性がある。`executedSize` で確認
