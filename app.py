"""Flask ウェブアプリケーション（マルチ通貨対応）"""
import logging
import logging.handlers
import threading
import sys
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from src.trade_manager import TradeManager
from src.database import init_db, get_trades, get_stats, get_daily_pnl
from src import config

# ---- ログ ----
class LogBuffer(logging.Handler):
    def __init__(self, maxlen=300):
        super().__init__()
        self.logs: list[dict] = []
        self.maxlen = maxlen

    def emit(self, record):
        entry = {
            "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
            "level": record.levelname,
            "message": self.format(record),
        }
        self.logs.append(entry)
        if len(self.logs) > self.maxlen:
            self.logs = self.logs[-self.maxlen:]


log_buffer = LogBuffer()
log_buffer.setFormatter(logging.Formatter("%(name)s: %(message)s"))

file_handler = logging.handlers.RotatingFileHandler(
    "trader.log", encoding="utf-8", maxBytes=5 * 1024 * 1024, backupCount=3
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        file_handler,
        log_buffer,
    ],
)
logger = logging.getLogger(__name__)

# ---- アプリ状態 ----
app = Flask(__name__)
init_db()

state = {
    "running": False,
    "dry_run": True,
    "manager": None,
    "trade_history": {},  # symbol -> list
}


def _record_trade(symbol, action, size, price, reason):
    if symbol not in state["trade_history"]:
        state["trade_history"][symbol] = []
    state["trade_history"][symbol].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "size": round(size, 6),
        "price": round(price),
        "reason": reason,
    })
    if len(state["trade_history"][symbol]) > 50:
        state["trade_history"][symbol] = state["trade_history"][symbol][-50:]


def _trading_loop():
    import time
    manager = TradeManager(dry_run=state["dry_run"])
    state["manager"] = manager
    symbols = list(manager.traders.keys())
    logger.info("=== トレーディング開始 (dry_run=%s, 通貨=%s) ===",
                state["dry_run"], symbols)

    while state["running"]:
        try:
            manager.run_once()
            # 取引記録をUI用stateに反映
            for symbol, trader in manager.traders.items():
                if trader.last_trade:
                    t = trader.last_trade
                    _record_trade(symbol, t["action"], t["size"], t["price"], t["reason"])
        except Exception:
            logger.exception("エラーが発生しました")

        for _ in range(config.TRADE_INTERVAL_SEC):
            if not state["running"]:
                break
            time.sleep(1)

    logger.info("=== トレーディング停止 ===")


# ---- ルート ----
@app.route("/")
def index():
    currencies = config.load_currencies()
    enabled = {s: c for s, c in currencies.items() if c.get("enabled")}
    return render_template("index.html", currencies=enabled)


@app.route("/api/status")
def api_status():
    manager = state.get("manager")
    currencies_status = {}

    if manager:
        for symbol, trader in manager.traders.items():
            currencies_status[symbol] = {
                "summary": trader.last_summary,
                "decision": trader.last_decision,
                "entry_price": trader.risk.entry_price,
                "entry_size": trader.risk.entry_size,
                "trade_history": get_trades(symbol, limit=10),
            }

    return jsonify({
        "running": state["running"],
        "dry_run": state["dry_run"],
        "currencies": currencies_status,
        "logs": log_buffer.logs[-80:],
    })


@app.route("/api/stats")
def api_stats():
    symbol = request.args.get("symbol")
    return jsonify({
        "overall": get_stats(),
        "by_symbol": get_stats(symbol) if symbol else None,
    })


@app.route("/api/trades")
def api_trades():
    symbol = request.args.get("symbol")
    limit = request.args.get("limit", 100, type=int)
    return jsonify(get_trades(symbol, limit))


@app.route("/api/daily_pnl")
def api_daily_pnl():
    symbol = request.args.get("symbol")
    days = request.args.get("days", 30, type=int)
    return jsonify(get_daily_pnl(days, symbol))


@app.route("/api/start", methods=["POST"])
def api_start():
    if state["running"]:
        return jsonify({"error": "既に実行中です"}), 400
    data = request.get_json(silent=True) or {}
    state["dry_run"] = data.get("dry_run", True)
    state["running"] = True
    t = threading.Thread(target=_trading_loop, daemon=True)
    t.start()
    return jsonify({"status": "started", "dry_run": state["dry_run"]})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    if not state["running"]:
        return jsonify({"error": "実行中ではありません"}), 400
    state["running"] = False
    return jsonify({"status": "stopped"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
