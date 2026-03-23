"""Flask ウェブアプリケーション"""
import logging
import threading
import sys
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from trader import Trader
import config

# ---- ログをメモリに保持する仕組み ----
class LogBuffer(logging.Handler):
    def __init__(self, maxlen=200):
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("trader.log", encoding="utf-8"),
        log_buffer,
    ],
)
logger = logging.getLogger(__name__)

# ---- アプリ状態 ----
app = Flask(__name__)

state = {
    "running": False,
    "dry_run": True,
    "thread": None,
    "trader": None,
    "last_summary": None,
    "last_decision": None,
    "trade_history": [],
}


# ---- トレーダーを拡張してUI用データを記録 ----
class WebTrader(Trader):
    def run_once(self):
        super().run_once()
        # Trader が保持する最新データを UI 用の state に反映
        if self.last_summary:
            state["last_summary"] = self.last_summary
        if self.last_decision:
            state["last_decision"] = self.last_decision
        # 実際に取引が実行された場合のみ記録
        if self.last_trade:
            t = self.last_trade
            _record_trade(t["action"], t["size"], t["price"], t["reason"])


def _record_trade(action, size, price, reason):
    state["trade_history"].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "size": round(size, 6),
        "price": round(price),
        "reason": reason,
    })
    if len(state["trade_history"]) > 100:
        state["trade_history"] = state["trade_history"][-100:]


def _trading_loop():
    import time
    trader = WebTrader(dry_run=state["dry_run"])
    state["trader"] = trader
    logger.info("=== トレーディング開始 (dry_run=%s, order_type=%s) ===",
                state["dry_run"], config.ORDER_TYPE)
    while state["running"]:
        try:
            trader.run_once()
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
    return render_template("index.html", config=config)


@app.route("/api/status")
def api_status():
    return jsonify({
        "running": state["running"],
        "dry_run": state["dry_run"],
        "summary": state["last_summary"],
        "decision": state["last_decision"],
        "trade_history": state["trade_history"][-20:],
        "logs": log_buffer.logs[-50:],
    })


@app.route("/api/start", methods=["POST"])
def api_start():
    if state["running"]:
        return jsonify({"error": "既に実行中です"}), 400
    data = request.get_json(silent=True) or {}
    state["dry_run"] = data.get("dry_run", True)
    state["running"] = True
    t = threading.Thread(target=_trading_loop, daemon=True)
    t.start()
    state["thread"] = t
    return jsonify({"status": "started", "dry_run": state["dry_run"]})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    if not state["running"]:
        return jsonify({"error": "実行中ではありません"}), 400
    state["running"] = False
    return jsonify({"status": "stopped"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
