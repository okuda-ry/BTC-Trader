"""リスク管理"""
import config


class RiskManager:
    def __init__(self):
        self.entry_price: float | None = None

    def calc_order_size(self, jpy_balance: float, btc_price: float) -> float:
        """注文サイズ(BTC)を計算"""
        risk_jpy = jpy_balance * config.MAX_POSITION_RATIO
        size = risk_jpy / btc_price
        # bitFlyer 最小注文単位: 0.001 BTC
        size = max(round(size, 4), 0.001)
        if risk_jpy < config.MIN_TRADE_JPY:
            return 0.0
        return size

    def set_entry(self, price: float):
        """エントリー価格を記録"""
        self.entry_price = price

    def clear_entry(self):
        """ポジションクリア"""
        self.entry_price = None

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
