"""ローソク足データの取得"""
import logging
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_INTERVAL_MAP = {
    60: "1min", 300: "5min", 600: "10min", 900: "15min", 1800: "30min",
    3600: "1hour", 14400: "4hour", 28800: "8hour", 43200: "12hour", 86400: "1day",
}


def fetch_ohlcv_from_gmo(symbol: str, period_sec: int = 3600, count: int = 100) -> pd.DataFrame:
    """GMOコイン公開APIからローソク足を取得する"""
    interval = _INTERVAL_MAP.get(period_sec)
    if interval is None:
        raise ValueError(f"未対応のローソク足期間: {period_sec}秒")

    now = datetime.now(timezone.utc)
    all_rows = []
    days_needed = max(2, (count // 24) + 2)

    for days_ago in range(days_needed):
        target = now - timedelta(days=days_ago)
        date_str = target.strftime("%Y%m%d")
        try:
            resp = requests.get(
                "https://api.coin.z.com/public/v1/klines",
                params={"symbol": symbol, "interval": interval, "date": date_str},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data["status"] != 0:
                continue
            all_rows.extend(data.get("data", []))
        except Exception as e:
            logger.warning("[%s] GMO klines 取得失敗 (date=%s): %s", symbol, date_str, e)

    if not all_rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(all_rows)
    df["timestamp"] = pd.to_datetime(df["openTime"].astype(int), unit="ms", utc=True)
    df = df.set_index("timestamp")
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df[df["close"] > 0]
    return df.tail(count)


def fetch_ohlcv_from_cryptocompare(symbol: str, period_sec: int = 3600, count: int = 100) -> pd.DataFrame:
    """CryptoCompare API からローソク足を取得する（フォールバック用）"""
    if period_sec <= 60:
        endpoint = "histominute"
    elif period_sec <= 3600:
        endpoint = "histohour"
    else:
        endpoint = "histoday"

    resp = requests.get(
        f"https://min-api.cryptocompare.com/data/v2/{endpoint}",
        params={"fsym": symbol, "tsym": "JPY", "limit": count},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("Response") != "Success":
        raise RuntimeError(f"CryptoCompare エラー: {data.get('Message', 'unknown')}")

    df = pd.DataFrame(data["Data"]["Data"])
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("timestamp")
    df = df.rename(columns={"volumefrom": "volume"})
    df = df[["open", "high", "low", "close", "volume"]]
    df = df.sort_index()
    df = df[df["close"] > 0]
    return df


def get_candles(symbol: str, period_sec: int = 3600, count: int = 100) -> pd.DataFrame:
    """ローソク足を取得する。GMOコイン → CryptoCompare の順にフォールバック。"""
    try:
        df = fetch_ohlcv_from_gmo(symbol, period_sec, count)
        if len(df) >= 30:
            logger.info("[%s] GMOコインから %d 本のローソク足を取得", symbol, len(df))
            return df
    except Exception as e:
        logger.warning("[%s] GMOコインからの取得に失敗: %s", symbol, e)

    try:
        df = fetch_ohlcv_from_cryptocompare(symbol, period_sec, count)
        if len(df) >= 30:
            logger.info("[%s] CryptoCompare から %d 本のローソク足を取得", symbol, len(df))
            return df
    except Exception as e:
        logger.warning("[%s] CryptoCompare からの取得にも失敗: %s", symbol, e)

    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
