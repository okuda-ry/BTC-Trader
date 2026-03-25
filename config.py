"""トレーディング設定"""
import json
import os
from dotenv import load_dotenv

load_dotenv()

# --- GMOコイン API ---
GMO_API_KEY = os.getenv("GMO_API_KEY", "")
GMO_API_SECRET = os.getenv("GMO_API_SECRET", "")

# --- Claude 分析設定 ---
ANALYZER_MODE = os.getenv("ANALYZER_MODE", "cli")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

# --- テクニカル指標パラメータ ---
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2

# --- 取引ルール ---
TRADE_INTERVAL_SEC = 900
CANDLE_PERIOD_SEC = 3600
CANDLE_COUNT = 100
ORDER_TYPE = "LIMIT"
LIMIT_OFFSET_PCT = 0.05
MIN_TRADE_JPY = 1000

# --- 通貨設定の読み込み ---
_CURRENCIES_FILE = os.path.join(os.path.dirname(__file__), "currencies.json")

def load_currencies() -> dict:
    with open(_CURRENCIES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def get_enabled_symbols() -> list[str]:
    currencies = load_currencies()
    return [sym for sym, cfg in currencies.items() if cfg.get("enabled")]
