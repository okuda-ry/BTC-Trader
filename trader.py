"""メインのトレーディングロジック"""
import logging
import time
from gmo_client import GMOClient
from candle_builder import get_candles
from indicators import build_summary
from ai_analyzer import analyze
from risk_manager import RiskManager
import config

logger = logging.getLogger(__name__)


class Trader:
    def __init__(self, dry_run: bool = True):
        self.client = GMOClient()
        self.risk = RiskManager()
        self.dry_run = dry_run
        self._pending_order_id: str | None = None
        # UI等から参照できるように最新データを保持
        self.last_summary: dict | None = None
        self.last_decision: dict | None = None
        self.last_trade: dict | None = None  # 直近の取引 {"action", "size", "price", "reason"}

    def run_once(self):
        """1回の分析・売買サイクルを実行"""
        self.last_trade = None  # 毎サイクルリセット

        # 0. 未約定の指値注文があればチェック
        self._check_pending_order()

        # 1. ローソク足を取得
        logger.info("ローソク足データを取得中...")
        candles = get_candles(config.CANDLE_PERIOD_SEC, config.CANDLE_COUNT)

        if len(candles) < 30:
            logger.warning("ローソク足データが不足しています (%d本)", len(candles))
            return

        # 2. テクニカル指標を計算
        summary = build_summary(candles)
        self.last_summary = summary
        logger.info(
            "価格=¥%s  RSI=%.1f  MACD_H=%.1f  BB_pos=%.3f",
            f"{summary['price']:,.0f}",
            summary["rsi"],
            summary["macd_histogram"],
            summary["bb_position"],
        )

        # 3. 現在の残高を確認
        btc_balance = self.client.get_btc_balance() if not self.dry_run else 0.0
        jpy_balance = self.client.get_jpy_balance() if not self.dry_run else 1_000_000.0
        current_price = summary["price"]

        # 4. 損切り・利確チェック（ポジション保有時）
        if self.risk.entry_price is not None and btc_balance > 0.00001:
            if self.risk.should_stop_loss(current_price):
                logger.warning("損切り発動! entry=¥%s → now=¥%s",
                               f"{self.risk.entry_price:,.0f}", f"{current_price:,.0f}")
                self._execute_sell(btc_balance, current_price, force_market=True)
                self.last_trade = {"action": "SELL", "size": btc_balance, "price": current_price, "reason": "損切り"}
                return
            if self.risk.should_take_profit(current_price):
                logger.info("利確発動! entry=¥%s → now=¥%s",
                            f"{self.risk.entry_price:,.0f}", f"{current_price:,.0f}")
                self._execute_sell(btc_balance, current_price)
                self.last_trade = {"action": "SELL", "size": btc_balance, "price": current_price, "reason": "利確"}
                return

        # 5. AI に売買判断を聞く
        logger.info("Claude に分析を依頼中...")
        decision = analyze(summary, btc_balance)
        self.last_decision = decision
        logger.info(
            "AI判断: %s (確信度: %.0f%%) — %s",
            decision["action"],
            decision["confidence"] * 100,
            decision["reason"],
        )

        # 6. 判断に基づいて売買実行
        if decision["confidence"] < 0.6:
            logger.info("確信度が低いためスキップ")
            return

        if decision["action"] == "BUY" and btc_balance < 0.00001:
            size = self.risk.calc_order_size(jpy_balance, current_price)
            if size > 0:
                self._execute_buy(size, current_price)
                self.last_trade = {"action": "BUY", "size": size, "price": current_price, "reason": decision["reason"]}

        elif decision["action"] == "SELL" and btc_balance > 0.00001:
            self._execute_sell(btc_balance, current_price)
            self.last_trade = {"action": "SELL", "size": btc_balance, "price": current_price, "reason": decision["reason"]}

        else:
            logger.info("HOLD — 待機")

    def _calc_limit_price(self, side: str, market_price: float) -> int:
        """指値価格を計算する。Maker になるようにオフセットを付ける。"""
        offset = market_price * config.LIMIT_OFFSET_PCT / 100
        if side == "BUY":
            # 現在価格より少し下に買い指値
            return int(market_price - offset)
        else:
            # 現在価格より少し上に売り指値
            return int(market_price + offset)

    def _execute_buy(self, size: float, price: float):
        order_type = config.ORDER_TYPE
        limit_price = self._calc_limit_price("BUY", price) if order_type == "LIMIT" else None

        if order_type == "LIMIT":
            logger.info("BUY %.5f BTC @ 指値 ¥%s (市場: ¥%s)",
                        size, f"{limit_price:,}", f"{price:,.0f}")
        else:
            logger.info("BUY %.5f BTC @ 成行 ¥%s", size, f"{price:,.0f}")

        if not self.dry_run:
            result = self.client.send_order("BUY", size, order_type, limit_price)
            order_id = result.get("data")
            if order_type == "LIMIT" and order_id:
                self._pending_order_id = str(order_id)
                logger.info("指値注文送信: orderId=%s", order_id)
            else:
                # 成行なら即約定
                self.risk.set_entry(price)
        else:
            logger.info("[DRY RUN] 注文はスキップ")
            self.risk.set_entry(price)

    def _execute_sell(self, size: float, price: float, force_market: bool = False):
        order_type = "MARKET" if force_market else config.ORDER_TYPE
        limit_price = self._calc_limit_price("SELL", price) if order_type == "LIMIT" else None

        if order_type == "LIMIT":
            logger.info("SELL %.5f BTC @ 指値 ¥%s (市場: ¥%s)",
                        size, f"{limit_price:,}", f"{price:,.0f}")
        else:
            logger.info("SELL %.5f BTC @ 成行 ¥%s", size, f"{price:,.0f}")

        if not self.dry_run:
            result = self.client.send_order("SELL", size, order_type, limit_price)
            order_id = result.get("data")
            if order_type == "LIMIT" and order_id:
                self._pending_order_id = str(order_id)
                logger.info("指値注文送信: orderId=%s", order_id)
            else:
                self.risk.clear_entry()
        else:
            logger.info("[DRY RUN] 注文はスキップ")
            self.risk.clear_entry()

    def _check_pending_order(self):
        """未約定の指値注文があれば状態を確認し、必要ならキャンセル"""
        if self._pending_order_id is None:
            return
        if self.dry_run:
            self._pending_order_id = None
            return

        try:
            order = self.client.get_order_status(self._pending_order_id)
            if not order:
                logger.warning("注文情報が取得できません: %s", self._pending_order_id)
                self._pending_order_id = None
                return

            status = order.get("status", "")
            side = order.get("side", "")
            logger.info("注文 %s 状態: %s", self._pending_order_id, status)

            if status == "EXECUTED":
                logger.info("指値注文が約定しました: %s %s", side, self._pending_order_id)
                exec_price = float(order.get("price", 0))
                if side == "BUY":
                    self.risk.set_entry(exec_price)
                else:
                    self.risk.clear_entry()
                self._pending_order_id = None

            elif status in ("CANCELED", "EXPIRED"):
                logger.info("指値注文がキャンセル/期限切れ: %s", self._pending_order_id)
                self._pending_order_id = None

            elif status in ("WAITING", "ORDERED"):
                # まだ約定していない → キャンセルして次のサイクルに進む
                logger.info("指値注文が未約定のためキャンセルします: %s", self._pending_order_id)
                self.client.cancel_order(int(self._pending_order_id))
                self._pending_order_id = None

        except Exception as e:
            logger.warning("注文状態の確認でエラー: %s", e)
            self._pending_order_id = None

    def run_loop(self):
        """定期的にrun_onceを実行するループ"""
        logger.info("=== BTC Trader 開始 (dry_run=%s) ===", self.dry_run)
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("エラーが発生しました")
            logger.info("次のチェックまで %d 秒待機...", config.TRADE_INTERVAL_SEC)
            time.sleep(config.TRADE_INTERVAL_SEC)
