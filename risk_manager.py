"""リスク管理"""
import json
import logging
import os
import config

logger = logging.getLogger(__name__)

STATE_FILE = "risk_state.json"


class RiskManager:
    def __init__(self):
        self.entry_price: float | None = None
        self._load_state()

    def _load_state(self):
        """前回のエントリー価格をファイルから復元"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                self.entry_price = data.get("entry_price")
                if self.entry_price is not None:
                    logger.info("前回のエントリー価格を復元: ¥%s", f"{self.entry_price:,.0f}")
            except Exception as e:
                logger.warning("リスク状態の読み込みに失敗: %s", e)

    def _save_state(self):
        """エントリー価格をファイルに保存"""
        try:
            with open(STATE_FILE, "w") as f:
                json.dump({"entry_price": self.entry_price}, f)
        except Exception as e:
            logger.warning("リスク状態の保存に失敗: %s", e)

    def calc_order_size(self, jpy_balance: float, btc_price: float) -> float:
        """注文サイズ(BTC)を計算"""
        risk_jpy = jpy_balance * config.MAX_POSITION_RATIO
        size = risk_jpy / btc_price
        # GMOコイン最小注文単位: 0.00001 BTC (5桁)
        size = round(size, 5)
        if size < 0.00001:
            return 0.0
        if risk_jpy < config.MIN_TRADE_JPY:
            return 0.0
        return size

    def set_entry(self, price: float):
        """エントリー価格を記録"""
        self.entry_price = price
        self._save_state()
        logger.info("エントリー価格を記録: ¥%s", f"{price:,.0f}")

    def clear_entry(self):
        """ポジションクリア"""
        self.entry_price = None
        self._save_state()
        logger.info("エントリー価格をクリア")

    def should_stop_loss(self, current_price: float) -> bool:
        """損切り判定"""
        if self.entry_price is None:
            return False
        loss_pct = (current_price - self.entry_price) / self.entry_price
        return loss_pct <= -config.STOP_LOSS_PCT

    def should_take_profit(self, current_price: float) -> bool:
        """利確判定"""
        if self.entry_price is None:
            return False
        gain_pct = (current_price - self.entry_price) / self.entry_price
        return gain_pct >= config.TAKE_PROFIT_PCT
