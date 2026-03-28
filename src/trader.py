"""通貨ごとのトレーディングロジック"""
import logging
from .gmo_client import GMOClient
from .candle_builder import get_candles
from .indicators import build_summary
from .ai_analyzer import analyze
from .risk_manager import RiskManager
from .database import record_trade
from .notifier import notify_trade, notify_stop_loss, notify_take_profit, notify_error
from . import config

logger = logging.getLogger(__name__)


class CurrencyTrader:
    """1つの通貨ペアを担当するトレーダー"""

    def __init__(self, symbol: str, currency_config: dict, client: GMOClient, dry_run: bool = True):
        self.symbol = symbol
        self.currency_config = currency_config
        self.client = client
        self.risk = RiskManager(symbol, currency_config)
        self.dry_run = dry_run
        self._pending_order_id: str | None = None
        self._pending_side: str | None = None
        self._pending_check_failures: int = 0

        # UI 用
        self.last_summary: dict | None = None
        self.last_decision: dict | None = None
        self.last_trade: dict | None = None  # 約定確認済みの取引のみ

    def run_once(self, other_summaries: dict | None = None, prefetched_summary: dict | None = None):
        """1回の分析・売買サイクル"""
        self.last_trade = None

        # 0. 未約定の指値注文があれば処理して、このサイクルはスキップ
        if self._pending_order_id is not None:
            self._check_pending_order()
            return  # 注文処理後は次のサイクルまで待つ

        # 1-2. テクニカル指標（事前取得済みならスキップ）
        if prefetched_summary is not None:
            summary = prefetched_summary
        else:
            logger.info("[%s] ローソク足データを取得中...", self.symbol)
            candles = get_candles(self.symbol, config.CANDLE_PERIOD_SEC, config.CANDLE_COUNT)
            if len(candles) < 30:
                logger.warning("[%s] ローソク足データが不足 (%d本)", self.symbol, len(candles))
                return
            summary = build_summary(candles)
        self.last_summary = summary
        logger.info("[%s] 価格=¥%s RSI=%.1f MACD_H=%.1f BB=%.3f",
                    self.symbol, f"{summary['price']:,.0f}",
                    summary["rsi"], summary["macd_histogram"], summary["bb_position"])

        # 3. 残高確認（Dry Runでも実際の残高を表示に使う）
        try:
            balance = self.client.get_balance(self.symbol)
            jpy_balance = self.client.get_jpy_balance()
        except Exception as e:
            logger.warning("[%s] 残高取得失敗: %s", self.symbol, e)
            balance = 0.0
            jpy_balance = 1_000_000.0 if self.dry_run else 0.0
        current_price = summary["price"]
        min_size = self.currency_config["min_order_size"]
        has_position = balance >= min_size

        # 4. 損切り・トレーリングストップチェック（ポジション保有時）
        if has_position and self.risk.entry_price is not None:
            self.risk.update_trailing(current_price)
            if self.risk.should_stop_loss(current_price):
                logger.warning("[%s] 損切り発動! entry=¥%s → now=¥%s",
                               self.symbol, f"{self.risk.entry_price:,.0f}", f"{current_price:,.0f}")
                notify_stop_loss(self.symbol, self.risk.entry_price, current_price, balance)
                self._execute_sell(balance, current_price, force_market=True)
                return
            if self.risk.should_trailing_stop(current_price):
                logger.info("[%s] トレーリングストップ発動! 最高値=¥%s → now=¥%s",
                            self.symbol, f"{self.risk.highest_price:,.0f}", f"{current_price:,.0f}")
                notify_take_profit(self.symbol, self.risk.entry_price, current_price, balance)
                self._execute_sell(balance, current_price)
                return

        # 4b. エントリー価格が不明だが残高がある場合（再起動後や部分約定後）
        if has_position and self.risk.entry_price is None:
            avg_price = self.client.calc_average_buy_price(self.symbol)
            if avg_price:
                logger.info("[%s] 約定履歴から平均取得単価を算出: ¥%s (保有: %.6f)",
                            self.symbol, f"{avg_price:,.0f}", balance)
                self.risk.set_entry(avg_price, balance)
            else:
                logger.warning("[%s] 約定履歴なし。現在価格 ¥%s で記録します (保有: %.6f)",
                               self.symbol, f"{current_price:,.0f}", balance)
                self.risk.set_entry(current_price, balance)

        # 5. AI 分析
        logger.info("[%s] Claude に分析を依頼中...", self.symbol)
        decision = analyze(self.symbol, summary, balance, other_summaries)
        self.last_decision = decision
        logger.info("[%s] AI判断: %s (確信度: %.0f%%) — %s",
                    self.symbol, decision["action"],
                    decision["confidence"] * 100, decision["reason"])

        # 6. 売買実行
        if decision["confidence"] < 0.6:
            logger.info("[%s] 確信度が低いためスキップ", self.symbol)
            return

        if decision["action"] == "BUY":
            size = self.risk.calc_order_size(jpy_balance, current_price, balance)
            if size > 0:
                if has_position:
                    logger.info("[%s] 目標比率未達のため追加購入 (現保有: %.6f)", self.symbol, balance)
                self._execute_buy(size, current_price)
                # 注意: last_trade は約定確認時に設定（_check_pending_order 内）
            else:
                logger.info("[%s] 目標比率到達済み — 追加購入不要", self.symbol)

        elif decision["action"] == "SELL" and has_position:
            self._execute_sell(balance, current_price)

        else:
            logger.info("[%s] HOLD — 待機", self.symbol)

    def _calc_limit_price(self, side: str, market_price: float) -> int:
        offset = market_price * config.LIMIT_OFFSET_PCT / 100
        if side == "BUY":
            return int(market_price - offset)
        else:
            return int(market_price + offset)

    def _execute_buy(self, size: float, price: float):
        order_type = config.ORDER_TYPE
        limit_price = self._calc_limit_price("BUY", price) if order_type == "LIMIT" else None
        decimals = self.currency_config["size_decimals"]

        logger.info("[%s] BUY %s @ %s ¥%s",
                    self.symbol, f"{size:.{decimals}f}",
                    "指値" if order_type == "LIMIT" else "成行",
                    f"{(limit_price or price):,}")

        if not self.dry_run:
            result = self.client.send_order(
                self.symbol, "BUY", size, order_type, limit_price, decimals)
            order_id = result.get("data")
            if order_type == "LIMIT":
                if order_id:
                    self._pending_order_id = str(order_id)
                    self._pending_side = "BUY"
                    logger.info("[%s] 指値注文送信: orderId=%s (次のサイクルで確認)", self.symbol, order_id)
                else:
                    logger.warning("[%s] 指値注文のorder_idが取得できませんでした", self.symbol)
            else:
                # 成行なら即約定とみなす
                self.risk.set_entry(price, size)
                self.last_trade = {"action": "BUY", "size": size, "price": price, "reason": "成行約定"}
                record_trade(self.symbol, "BUY", size, price, "成行約定")
        else:
            logger.info("[%s] [DRY RUN] 注文スキップ", self.symbol)
            self.risk.set_entry(price, size)
            self.last_trade = {"action": "BUY", "size": size, "price": price, "reason": "DRY RUN"}
            record_trade(self.symbol, "BUY", size, price, "DRY RUN")

    def _execute_sell(self, size: float, price: float, force_market: bool = False):
        order_type = "MARKET" if force_market else config.ORDER_TYPE
        limit_price = self._calc_limit_price("SELL", price) if order_type == "LIMIT" else None
        decimals = self.currency_config["size_decimals"]

        logger.info("[%s] SELL %s @ %s ¥%s",
                    self.symbol, f"{size:.{decimals}f}",
                    "指値" if order_type == "LIMIT" else "成行",
                    f"{(limit_price or price):,}")

        if not self.dry_run:
            result = self.client.send_order(
                self.symbol, "SELL", size, order_type, limit_price, decimals)
            order_id = result.get("data")
            if order_type == "LIMIT":
                if order_id:
                    self._pending_order_id = str(order_id)
                    self._pending_side = "SELL"
                    logger.info("[%s] 指値注文送信: orderId=%s (次のサイクルで確認)", self.symbol, order_id)
                else:
                    logger.warning("[%s] 指値注文のorder_idが取得できませんでした", self.symbol)
            else:
                # 成行なら即約定
                entry_px = self.risk.entry_price
                self.risk.clear_entry()
                self.last_trade = {"action": "SELL", "size": size, "price": price, "reason": "成行約定"}
                record_trade(self.symbol, "SELL", size, price, "成行約定", entry_price=entry_px)
        else:
            logger.info("[%s] [DRY RUN] 注文スキップ", self.symbol)
            entry_px = self.risk.entry_price
            self.risk.clear_entry()
            self.last_trade = {"action": "SELL", "size": size, "price": price, "reason": "DRY RUN"}
            record_trade(self.symbol, "SELL", size, price, "DRY RUN", entry_price=entry_px)

    def _check_pending_order(self):
        """未約定注文の状態確認。約定時のみ取引を記録。"""
        if self._pending_order_id is None:
            return

        if self.dry_run:
            self._pending_order_id = None
            self._pending_side = None
            return

        try:
            order = self.client.get_order_status(self._pending_order_id)
            if not order:
                logger.warning("[%s] 注文情報取得不可: %s", self.symbol, self._pending_order_id)
                self._pending_order_id = None
                self._pending_side = None
                return

            status = order.get("status", "")
            side = order.get("side", self._pending_side or "")
            executed_size = float(order.get("executedSize", "0"))
            order_price = float(order.get("price", "0"))

            logger.info("[%s] 注文 %s: status=%s, side=%s, 約定=%s",
                        self.symbol, self._pending_order_id, status, side, executed_size)

            if status == "EXECUTED":
                # 全量約定 — 取引を記録
                logger.info("[%s] 指値注文が全量約定! %s %.6f @ ¥%s",
                            self.symbol, side, executed_size, f"{order_price:,.0f}")
                if side == "BUY":
                    self.risk.set_entry(order_price, executed_size)
                    self.last_trade = {"action": "BUY", "size": executed_size,
                                       "price": order_price, "reason": "指値約定"}
                    record_trade(self.symbol, "BUY", executed_size, order_price, "指値約定")
                    notify_trade(self.symbol, "BUY", executed_size, order_price, "指値約定")
                else:
                    entry_px = self.risk.entry_price
                    pnl = (order_price - entry_px) * executed_size if entry_px else None
                    self.risk.clear_entry()
                    self.last_trade = {"action": "SELL", "size": executed_size,
                                       "price": order_price, "reason": "指値約定"}
                    record_trade(self.symbol, "SELL", executed_size, order_price, "指値約定", entry_price=entry_px)
                    notify_trade(self.symbol, "SELL", executed_size, order_price, "指値約定", pnl_jpy=pnl)

            elif status in ("CANCELED", "EXPIRED"):
                if executed_size > 0:
                    # 部分約定あり
                    logger.info("[%s] 部分約定: %s %.6f @ ¥%s",
                                self.symbol, side, executed_size, f"{order_price:,.0f}")
                    if side == "BUY":
                        self.risk.set_entry(order_price, executed_size)
                        self.last_trade = {"action": "BUY", "size": executed_size,
                                           "price": order_price, "reason": "部分約定"}
                        record_trade(self.symbol, "BUY", executed_size, order_price, "部分約定")
                    else:
                        # SELL部分約定: 残りのポジションを更新
                        entry_px = self.risk.entry_price
                        remaining = self.risk.entry_size - executed_size
                        if remaining >= self.currency_config["min_order_size"]:
                            self.risk.entry_size = remaining
                            self.risk._save_state()
                            logger.info("[%s] SELL部分約定: 残ポジション %.6f", self.symbol, remaining)
                        else:
                            self.risk.clear_entry()
                        self.last_trade = {"action": "SELL", "size": executed_size,
                                           "price": order_price, "reason": "部分約定"}
                        record_trade(self.symbol, "SELL", executed_size, order_price, "部分約定", entry_price=entry_px)
                else:
                    logger.info("[%s] 注文キャンセル/期限切れ（約定なし）", self.symbol)

            elif status in ("WAITING", "ORDERED"):
                # 未約定 → キャンセル
                logger.info("[%s] 未約定のためキャンセル: %s", self.symbol, self._pending_order_id)
                self.client.cancel_order(int(self._pending_order_id))
                if executed_size > 0:
                    logger.info("[%s] キャンセル前に部分約定: %s %.6f",
                                self.symbol, side, executed_size)
                    if side == "BUY":
                        self.risk.set_entry(order_price, executed_size)
                        self.last_trade = {"action": "BUY", "size": executed_size,
                                           "price": order_price, "reason": "部分約定(残キャンセル)"}
                        record_trade(self.symbol, "BUY", executed_size, order_price, "部分約定(残キャンセル)")

            self._pending_order_id = None
            self._pending_side = None
            self._pending_check_failures = 0

        except Exception as e:
            self._pending_check_failures += 1
            logger.warning("[%s] 注文状態確認エラー (%d回目): %s",
                           self.symbol, self._pending_check_failures, e)
            if self._pending_check_failures >= 3:
                logger.error("[%s] 3回連続失敗。注文 %s をキャンセル試行後クリア",
                             self.symbol, self._pending_order_id)
                try:
                    self.client.cancel_order(int(self._pending_order_id))
                except Exception:
                    pass
                self._pending_order_id = None
                self._pending_side = None
                self._pending_check_failures = 0
