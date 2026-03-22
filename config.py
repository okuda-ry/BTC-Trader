"""トレーディング設定"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- bitFlyer API ---
BITFLYER_API_KEY = os.getenv("BITFLYER_API_KEY", "")
BITFLYER_API_SECRET = os.getenv("BITFLYER_API_SECRET", "")
BITFLYER_BASE_URL = "https://api.bitflyer.com"
PRODUCT_CODE = "BTC_JPY"

# --- Claude 分析設定 ---
# "cli" = Claude Code CLI (サブスク内、APIキー不要)
# "api" = Anthropic API (従量課金、APIキー必要)
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
TRADE_INTERVAL_SEC = 900        # 15分間隔でチェック
CANDLE_PERIOD_SEC = 3600        # 1時間足
CANDLE_COUNT = 100              # 分析に使うローソク足の本数

# --- リスク管理 ---
MAX_POSITION_RATIO = 0.10       # 残高の最大10%をリスクにさらす
STOP_LOSS_PCT = 0.02            # 2% 損切り
TAKE_PROFIT_PCT = 0.04          # 4% 利確
MIN_TRADE_JPY = 1000            # 最小取引額(JPY)
