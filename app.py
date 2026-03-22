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
        from candle_builder import get_candles
        from indicators import build_summary
        from ai_analyzer import analyze

        logger.info("ローソク足データを取得中...")
        candles = get_candles(config.CANDLE_PERIOD_SEC, config.CANDLE_COUNT)

        if len(candles) < 30:
            logger.warning("ローソク足データが不足しています (%d本)", len(candles))
            return

        summary = build_summary(candles)
        state["last_summary"] = summary
        logger.info(
            "価格=¥%s  RSI=%.1f  MACD_H=%.1f  BB_pos=%.3f",
            f"{summary['price']:,.0f}",
            summary["rsi"],
            summary["macd_histogram"],
            summary["bb_position"],
        )

        btc_balance = self.client.get_btc_balance() if not self.dry_run else 0.0
        jpy_balance = self.client.get_jpy_balance() if not self.dry_run else 1_000_000.0
        current_price = summary["price"]

        if self.risk.entry_price is not None and btc_balance > 0.0001:
            if self.risk.should_stop_loss(current_price):
                logger.warning("損切り発動!")
                self._execute_sell(btc_balance, current_price)
                _record_trade("SELL", btc_balance, current_price, "損切り")
                return
            if self.risk.should_take_profit(current_price):
                logger.info("利確発動!")
                self._execute_sell(btc_balance, current_price)
                _record_trade("SELL", btc_balance, current_price, "利確")
                return

        logger.info("Claude に分析を依頼中...")
        decision = analyze(summary, btc_balance)
        state["last_decision"] = decision
        logger.info(
            "AI判断: %s (確信度: %.0f%%) — %s",
            decision["action"],
            decision["confidence"] * 100,
            decision["reason"],
        )

        if decision["confidence"] < 0.6:
            logger.info("確信度が低いためスキップ")
            return

        if decision["action"] == "BUY" and btc_balance < 0.0001:
            size = self.risk.calc_order_size(jpy_balance, current_price)
            if size > 0:
                self._execute_buy(size, current_price)
                _record_trade("BUY", size, current_price, decision["reason"])
        elif decision["action"] == "SELL" and btc_balance > 0.0001:
            self._execute_sell(btc_balance, current_price)
            _record_trade("SELL", btc_balance, current_price, decision["reason"])
        else:
            logger.info("HOLD — 待機")


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
    logger.info("=== トレーディング開始 (dry_run=%s) ===", state["dry_run"])
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
