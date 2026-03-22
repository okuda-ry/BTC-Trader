"""ローソク足データの取得"""
import logging
import requests
import pandas as pd
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def fetch_ohlcv(period_sec: int = 3600, count: int = 100) -> pd.DataFrame:
    """CryptoCompare API から BTC/JPY のローソク足を取得する（無料・登録不要）"""
    if period_sec <= 60:
        endpoint = "histominute"
    elif period_sec <= 3600:
        endpoint = "histohour"
    else:
        endpoint = "histoday"

    url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
    params = {
        "fsym": "BTC",
        "tsym": "JPY",
        "limit": count,
        "e": "bitflyer",
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("Response") != "Success":
        raise RuntimeError(f"CryptoCompare エラー: {data.get('Message', 'unknown')}")

    rows = data["Data"]["Data"]
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("timestamp")
    df = df.rename(columns={"volumefrom": "volume"})
    df = df[["open", "high", "low", "close", "volume"]]
    df = df.sort_index()

    # 値が0のデータは除外
    df = df[df["close"] > 0]
    return df


def _fetch_from_executions(period_sec: int = 3600) -> pd.DataFrame:
    """bitFlyer 約定履歴からローソク足を生成（フォールバック用）。
    before パラメータで複数ページ取得し、十分な本数を確保する。
    """
    from bitflyer_client import BitFlyerClient
    client = BitFlyerClient()

    all_executions = []
    before_id = None
    max_pages = 10

    for _ in range(max_pages):
        params = {"product_code": "BTC_JPY", "count": 500}
        if before_id is not None:
            params["before"] = before_id

        resp = requests.get(
            f"{client.base_url}/v1/executions",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        page = resp.json()

        if not page:
            break

        all_executions.extend(page)
        before_id = page[-1]["id"]
        logger.info("約定履歴 %d 件取得済み...", len(all_executions))

        # 十分なデータがあればループ終了（概算チェック）
        if len(all_executions) >= 3000:
            break

    if not all_executions:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    records = []
    for ex in all_executions:
        dt = datetime.fromisoformat(ex["exec_date"].replace("Z", "+00:00"))
        records.append({
            "timestamp": dt,
            "price": float(ex["price"]),
            "size": float(ex["size"]),
        })

    df = pd.DataFrame(records)
    df = df.sort_values("timestamp")
    df = df.set_index("timestamp")

    ohlcv = df["price"].resample(f"{period_sec}s").ohlc()
    ohlcv["volume"] = df["size"].resample(f"{period_sec}s").sum()
    ohlcv = ohlcv.dropna()
    return ohlcv


def get_candles(period_sec: int = 3600, count: int = 100) -> pd.DataFrame:
    """ローソク足を取得する。CryptoCompare → 約定履歴ページングの順にフォールバック。"""
    try:
        df = fetch_ohlcv(period_sec, count)
        if len(df) >= 30:
            logger.info("CryptoCompare から %d 本のローソク足を取得", len(df))
            return df
        logger.warning("CryptoCompare のデータが不足 (%d本)", len(df))
    except Exception as e:
        logger.warning("CryptoCompare からの取得に失敗: %s", e)

    # フォールバック: bitFlyer 約定履歴をページングで取得
    logger.info("約定履歴からローソク足を生成します（複数ページ取得）")
    return _fetch_from_executions(period_sec)
