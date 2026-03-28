"""リスク管理（マルチ通貨対応）"""
import json
import logging
import os

logger = logging.getLogger(__name__)

STATE_FILE = "risk_state.json"


def _load_all_state() -> dict | None:
    """全通貨のリスク状態を読み込む。ファイルなしは空dict、読み込みエラーはNone。"""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("risk_state.json 読み込みエラー: %s", e)
        return None


def _save_all_state(data: dict):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning("リスク状態の保存に失敗: %s", e)


class RiskManager:
    def __init__(self, symbol: str, currency_config: dict):
        self.symbol = symbol
        self.min_order_size = currency_config["min_order_size"]
        self.size_decimals = currency_config["size_decimals"]
        self.max_position_ratio = currency_config["max_position_ratio"]
        self.stop_loss_pct = currency_config["stop_loss_pct"]
        self.take_profit_pct = currency_config["take_profit_pct"]
        self.entry_price: float | None = None
        self.entry_size: float = 0.0
        self._load_state()

    def _load_state(self):
        data = _load_all_state() or {}
        pos = data.get(self.symbol, {})
        self.entry_price = pos.get("entry_price")
        self.entry_size = pos.get("entry_size", 0.0)
        if self.entry_price is not None:
            logger.info("[%s] エントリー復元: ¥%s (%.6f)",
                        self.symbol, f"{self.entry_price:,.0f}", self.entry_size)

    def _save_state(self):
        data = _load_all_state()
        if data is None:
            logger.warning("[%s] risk_state.json の読み込み失敗のため保存スキップ", self.symbol)
            return
        if self.entry_price is not None:
            data[self.symbol] = {
                "entry_price": self.entry_price,
                "entry_size": self.entry_size,
            }
        else:
            data.pop(self.symbol, None)
        _save_all_state(data)

    def calc_order_size(self, jpy_balance: float, price: float,
                        current_balance: float = 0.0) -> float:
        """目標ポジション（総資産の max_position_ratio）に対する不足分を計算。

        current_balance が 0 なら新規購入、>0 なら差分の追加購入量を返す。
        """
        # 総資産の概算: JPY + 現在の当通貨ポジション評価額
        position_value = current_balance * price
        total_assets = jpy_balance + position_value
        target_jpy = total_assets * self.max_position_ratio
        gap_jpy = target_jpy - position_value

        from .config import MIN_TRADE_JPY
        if gap_jpy < MIN_TRADE_JPY:
            return 0.0

        size = gap_jpy / price
        size = round(size, self.size_decimals)
        if size < self.min_order_size:
            return 0.0
        return size

    def set_entry(self, price: float, size: float = 0.0):
        """エントリーを記録。既存ポジションがあれば加重平均で更新。"""
        if self.entry_price is not None and self.entry_size > 0 and size > 0:
            # 加重平均取得単価
            total_cost = self.entry_price * self.entry_size + price * size
            total_size = self.entry_size + size
            self.entry_price = total_cost / total_size
            self.entry_size = total_size
            logger.info("[%s] 追加購入 → 平均取得単価: ¥%s (合計: %.6f)",
                        self.symbol, f"{self.entry_price:,.0f}", self.entry_size)
        else:
            self.entry_price = price
            self.entry_size = size
            logger.info("[%s] エントリー記録: ¥%s (%.6f)",
                        self.symbol, f"{price:,.0f}", size)
        self._save_state()

    def clear_entry(self):
        self.entry_price = None
        self.entry_size = 0.0
        self._save_state()
        logger.info("[%s] エントリークリア", self.symbol)

    def should_stop_loss(self, current_price: float) -> bool:
        if self.entry_price is None:
            return False
        return (current_price - self.entry_price) / self.entry_price <= -self.stop_loss_pct

    def should_take_profit(self, current_price: float) -> bool:
        if self.entry_price is None:
            return False
        return (current_price - self.entry_price) / self.entry_price >= self.take_profit_pct
