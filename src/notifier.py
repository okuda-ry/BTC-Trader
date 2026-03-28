"""LINE Messaging API による通知モジュール"""
import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_config() -> tuple[str, str]:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    user_id = os.environ.get("LINE_USER_ID", "")
    if not token or not user_id:
        raise ValueError("LINE_CHANNEL_ACCESS_TOKEN と LINE_USER_ID が未設定")
    return token, user_id


def send_line_message(text: str) -> bool:
    """LINE にテキストメッセージを送信する。"""
    try:
        token, user_id = _get_config()
    except ValueError as e:
        logger.debug("LINE通知スキップ: %s", e)
        return False

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    body = json.dumps({
        "to": user_id,
        "messages": [{"type": "text", "text": text}],
    }).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                logger.info("LINE通知送信成功")
                return True
            logger.warning("LINE HTTP %s", resp.status)
            return False
    except urllib.error.HTTPError as e:
        logger.warning("LINE HTTPError %s: %s", e.code, e.read().decode())
        return False
    except Exception as e:
        logger.warning("LINE送信エラー: %s", e)
        return False


def notify_trade(symbol: str, action: str, size: float, price: float,
                 reason: str = "", pnl_jpy: float | None = None):
    """約定通知"""
    emoji = {"BUY": "🟢", "SELL": "🔴"}.get(action, "⚪")
    lines = [
        f"{emoji} {symbol} {action}",
        f"数量: {size}",
        f"価格: ¥{price:,.0f}",
    ]
    if pnl_jpy is not None:
        sign = "+" if pnl_jpy >= 0 else ""
        lines.append(f"損益: {sign}¥{pnl_jpy:,.0f}")
    if reason:
        lines.append(f"理由: {reason}")
    lines.append(datetime.now().strftime("%H:%M"))
    send_line_message("\n".join(lines))


def notify_stop_loss(symbol: str, entry_price: float, current_price: float,
                     size: float):
    """損切り通知"""
    pnl_pct = (current_price - entry_price) / entry_price * 100
    msg = (
        f"🚨 {symbol} 損切り発動\n"
        f"エントリー: ¥{entry_price:,.0f}\n"
        f"現在価格: ¥{current_price:,.0f}\n"
        f"損失: {pnl_pct:.2f}%\n"
        f"数量: {size}\n"
        f"{datetime.now().strftime('%H:%M')}"
    )
    send_line_message(msg)


def notify_take_profit(symbol: str, entry_price: float, current_price: float,
                       size: float):
    """利確通知"""
    pnl_pct = (current_price - entry_price) / entry_price * 100
    msg = (
        f"🎯 {symbol} 利確発動\n"
        f"エントリー: ¥{entry_price:,.0f}\n"
        f"現在価格: ¥{current_price:,.0f}\n"
        f"利益: +{pnl_pct:.2f}%\n"
        f"数量: {size}\n"
        f"{datetime.now().strftime('%H:%M')}"
    )
    send_line_message(msg)


def notify_error(message: str):
    """エラー通知"""
    msg = f"⚠️ エラー\n{message}\n{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    send_line_message(msg)
