"""ローソク足データの取得"""
import logging
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# GMOコイン interval 名のマッピング
_INTERVAL_MAP = {
    60: "1min",
    300: "5min",
    600: "10min",
    900: "15min",
    1800: "30min",
    3600: "1hour",
    14400: "4hour",
    28800: "8hour",
    43200: "12hour",
    86400: "1day",
}


def fetch_ohlcv_from_gmo(period_sec: int = 3600, count: int = 100) -> pd.DataFrame:
    """GMOコイン公開APIからローソク足を取得する"""
    import config

    interval = _INTERVAL_MAP.get(period_sec)
    if interval is None:
        raise ValueError(f"未対応のローソク足期間: {period_sec}秒")

    now = datetime.now(timezone.utc)
    all_rows = []

    # 日中足は日付ごとに取得する必要がある
    # 1hour足の場合: 1日24本 × 5日 = 120本 (指標計算に十分)
    days_needed = max(2, (count // 24) + 2)
    for days_ago in range(days_needed):
        target = now - timedelta(days=days_ago)
        date_str = target.strftime("%Y%m%d")

        try:
            resp = requests.get(
                "https://api.coin.z.com/public/v1/klines",
                params={
                    "symbol": config.PRODUCT_CODE,
                    "interval": interval,
                    "date": date_str,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            if data["status"] != 0:
                logger.warning("GMO klines エラー (date=%s): %s", date_str, data)
                continue

            rows = data.get("data", [])
            all_rows.extend(rows)
        except Exception as e:
            logger.warning("GMO klines 取得失敗 (date=%s): %s", date_str, e)

    if not all_rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(all_rows)
    df["timestamp"] = pd.to_datetime(df["openTime"].astype(int), unit="ms", utc=True)
    df = df.set_index("timestamp")
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]  # 日付境界の重複を排除
    df = df[df["close"] > 0]

    return df.tail(count)


def fetch_ohlcv_from_cryptocompare(period_sec: int = 3600, count: int = 100) -> pd.DataFrame:
    """CryptoCompare API からローソク足を取得する（フォールバック用）"""
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
    df = df[df["close"] > 0]
    return df


def get_candles(period_sec: int = 3600, count: int = 100) -> pd.DataFrame:
    """ローソク足を取得する。GMOコイン → CryptoCompare の順にフォールバック。"""
    try:
        df = fetch_ohlcv_from_gmo(period_sec, count)
        if len(df) >= 30:
            logger.info("GMOコインから %d 本のローソク足を取得", len(df))
            return df
        logger.warning("GMOコインのデータが不足 (%d本)", len(df))
    except Exception as e:
        logger.warning("GMOコインからの取得に失敗: %s", e)

    # フォールバック
    try:
        df = fetch_ohlcv_from_cryptocompare(period_sec, count)
        if len(df) >= 30:
            logger.info("CryptoCompare から %d 本のローソク足を取得", len(df))
            return df
    except Exception as e:
        logger.warning("CryptoCompare からの取得にも失敗: %s", e)

    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
