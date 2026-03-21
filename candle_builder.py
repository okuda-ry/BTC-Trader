"""約定履歴から1時間足ローソクを生成"""
import pandas as pd
from datetime import datetime, timezone


def build_candles_from_executions(executions: list, period_sec: int = 3600) -> pd.DataFrame:
    """bitFlyer約定履歴リストから OHLCV DataFrame を作成"""
    if not executions:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    records = []
    for ex in executions:
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
