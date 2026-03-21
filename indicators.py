"""テクニカル指標の計算"""
import numpy as np
import pandas as pd
import config


def calc_rsi(closes: pd.Series, period: int = config.RSI_PERIOD) -> pd.Series:
    """RSI を計算"""
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def calc_macd(
    closes: pd.Series,
    fast: int = config.MACD_FAST,
    slow: int = config.MACD_SLOW,
    signal: int = config.MACD_SIGNAL,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD, シグナル線, ヒストグラムを返す"""
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_bollinger(
    closes: pd.Series,
    period: int = config.BB_PERIOD,
    std_mult: float = config.BB_STD,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """ボリンジャーバンド（upper, middle, lower）を返す"""
    middle = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    return upper, middle, lower


def build_summary(df: pd.DataFrame) -> dict:
    """DataFrameの最新行からテクニカルサマリを生成"""
    closes = df["close"]
    rsi = calc_rsi(closes)
    macd_line, signal_line, histogram = calc_macd(closes)
    bb_upper, bb_middle, bb_lower = calc_bollinger(closes)

    last = len(df) - 1
    price = closes.iloc[last]

    return {
        "price": float(price),
        "rsi": round(float(rsi.iloc[last]), 2),
        "macd": round(float(macd_line.iloc[last]), 2),
        "macd_signal": round(float(signal_line.iloc[last]), 2),
        "macd_histogram": round(float(histogram.iloc[last]), 2),
        "bb_upper": round(float(bb_upper.iloc[last]), 2),
        "bb_middle": round(float(bb_middle.iloc[last]), 2),
        "bb_lower": round(float(bb_lower.iloc[last]), 2),
        "bb_position": round(
            (price - bb_lower.iloc[last])
            / (bb_upper.iloc[last] - bb_lower.iloc[last] + 1e-9),
            3,
        ),
        "price_change_1h": round(
            float((price - closes.iloc[last - 1]) / closes.iloc[last - 1] * 100), 3
        ),
        "price_change_4h": round(
            float((price - closes.iloc[max(0, last - 4)]) / closes.iloc[max(0, last - 4)] * 100), 3
        ),
    }
