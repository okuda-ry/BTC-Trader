"""全通貨を管理するオーケストレーター"""
import logging
import time
from .gmo_client import GMOClient
from .trader import CurrencyTrader
from .candle_builder import get_candles
from .indicators import build_summary
from . import config

logger = logging.getLogger(__name__)


class TradeManager:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.client = GMOClient()
        self.traders: dict[str, CurrencyTrader] = {}
        self._init_traders()

    def _init_traders(self):
        currencies = config.load_currencies()
        for symbol, cfg in currencies.items():
            if cfg.get("enabled"):
                self.traders[symbol] = CurrencyTrader(
                    symbol, cfg, self.client, self.dry_run)
                logger.info("[%s] トレーダー初期化完了 (%s)", symbol, cfg["name"])

    def run_once(self):
        """全通貨の分析・売買を1サイクル実行"""
        # まず全通貨のサマリを収集（他通貨の参考情報として使う）
        all_summaries: dict[str, dict] = {}
        for symbol, trader in self.traders.items():
            try:
                candles = get_candles(symbol, config.CANDLE_PERIOD_SEC, config.CANDLE_COUNT)
                if len(candles) >= 30:
                    all_summaries[symbol] = build_summary(candles)
            except Exception as e:
                logger.warning("[%s] サマリ取得失敗: %s", symbol, e)

        # 各通貨で売買判断（事前取得のサマリを渡して二重取得を防止）
        for symbol, trader in self.traders.items():
            try:
                other = {s: v for s, v in all_summaries.items() if s != symbol}
                own_summary = all_summaries.get(symbol)
                trader.run_once(
                    other_summaries=other if other else None,
                    prefetched_summary=own_summary,
                )
            except Exception:
                logger.exception("[%s] エラーが発生しました", symbol)

    def run_loop(self):
        logger.info("=== TradeManager 開始 (dry_run=%s, 通貨=%s) ===",
                    self.dry_run, list(self.traders.keys()))
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("TradeManager エラー")
            logger.info("次のチェックまで %d 秒待機...", config.TRADE_INTERVAL_SEC)
            time.sleep(config.TRADE_INTERVAL_SEC)
