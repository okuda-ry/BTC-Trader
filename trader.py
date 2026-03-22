"""メインのトレーディングロジック"""
import logging
import time
from bitflyer_client import BitFlyerClient
from candle_builder import get_candles
from indicators import build_summary
from ai_analyzer import analyze
from risk_manager import RiskManager
import config

logger = logging.getLogger(__name__)


class Trader:
    def __init__(self, dry_run: bool = True):
        self.client = BitFlyerClient()
        self.risk = RiskManager()
        self.dry_run = dry_run

    def run_once(self):
        """1回の分析・売買サイクルを実行"""
        # 1. ローソク足を取得
        logger.info("ローソク足データを取得中...")
        candles = get_candles(config.CANDLE_PERIOD_SEC, config.CANDLE_COUNT)

        if len(candles) < 30:
            logger.warning("ローソク足データが不足しています (%d本)", len(candles))
            return

        # 2. テクニカル指標を計算
        summary = build_summary(candles)
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
        if self.risk.entry_price is not None and btc_balance > 0.0001:
            if self.risk.should_stop_loss(current_price):
                logger.warning("損切り発動! entry=¥%s → now=¥%s",
                               f"{self.risk.entry_price:,.0f}", f"{current_price:,.0f}")
                self._execute_sell(btc_balance, current_price)
                return
            if self.risk.should_take_profit(current_price):
                logger.info("利確発動! entry=¥%s → now=¥%s",
                            f"{self.risk.entry_price:,.0f}", f"{current_price:,.0f}")
                self._execute_sell(btc_balance, current_price)
                return

        # 5. AI に売買判断を聞く
        logger.info("Claude に分析を依頼中...")
        decision = analyze(summary, btc_balance)
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

        if decision["action"] == "BUY" and btc_balance < 0.0001:
            size = self.risk.calc_order_size(jpy_balance, current_price)
            if size > 0:
                self._execute_buy(size, current_price)

        elif decision["action"] == "SELL" and btc_balance > 0.0001:
            self._execute_sell(btc_balance, current_price)

        else:
            logger.info("HOLD — 待機")

    def _execute_buy(self, size: float, price: float):
        logger.info("BUY %.4f BTC @ ¥%s", size, f"{price:,.0f}")
        if not self.dry_run:
            result = self.client.send_order("BUY", size)
            logger.info("注文結果: %s", result)
        else:
            logger.info("[DRY RUN] 注文はスキップ")
        self.risk.set_entry(price)

    def _execute_sell(self, size: float, price: float):
        logger.info("SELL %.4f BTC @ ¥%s", size, f"{price:,.0f}")
        if not self.dry_run:
            result = self.client.send_order("SELL", size)
            logger.info("注文結果: %s", result)
        else:
            logger.info("[DRY RUN] 注文はスキップ")
        self.risk.clear_entry()

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
