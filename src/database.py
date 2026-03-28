"""SQLite 取引履歴データベース"""
import sqlite3
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(_PROJECT_ROOT, "trades.db")


def _connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """テーブルを作成（存在しなければ）"""
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            size REAL NOT NULL,
            price REAL NOT NULL,
            reason TEXT,
            entry_price REAL,
            pnl_pct REAL,
            pnl_jpy REAL
        )
    """)
    conn.commit()
    conn.close()
    logger.info("データベース初期化完了: %s", DB_FILE)
    cleanup_old_trades()


def cleanup_old_trades(days: int = 90):
    """指定日数より古い取引履歴を削除する。"""
    conn = _connect()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    result = conn.execute("DELETE FROM trades WHERE timestamp < ?", (cutoff,))
    deleted = result.rowcount
    conn.commit()
    conn.close()
    if deleted > 0:
        logger.info("古い取引履歴を %d 件削除しました（%s 以前）", deleted, cutoff)


def record_trade(symbol: str, action: str, size: float, price: float,
                 reason: str = "", entry_price: float | None = None):
    """取引を記録する。SELLの場合はエントリー価格から損益を計算。"""
    pnl_pct = None
    pnl_jpy = None
    if action == "SELL" and entry_price is not None and entry_price > 0:
        pnl_pct = round((price - entry_price) / entry_price * 100, 2)
        pnl_jpy = round((price - entry_price) * size, 0)

    conn = _connect()
    conn.execute(
        """INSERT INTO trades (timestamp, symbol, action, size, price, reason, entry_price, pnl_pct, pnl_jpy)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         symbol, action, size, price, reason, entry_price, pnl_pct, pnl_jpy)
    )
    conn.commit()
    conn.close()


def get_trades(symbol: str | None = None, limit: int = 50) -> list[dict]:
    """取引履歴を取得。symbolがNoneなら全通貨。"""
    conn = _connect()
    if symbol:
        rows = conn.execute(
            "SELECT * FROM trades WHERE symbol = ? ORDER BY id DESC LIMIT ?",
            (symbol, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats(symbol: str | None = None) -> dict:
    """通貨別または全体の統計を計算。"""
    conn = _connect()

    where = "WHERE symbol = ?" if symbol else ""
    params = (symbol,) if symbol else ()

    # 総取引数
    total = conn.execute(
        f"SELECT COUNT(*) FROM trades {where}", params
    ).fetchone()[0]

    buy_count = conn.execute(
        f"SELECT COUNT(*) FROM trades {where + ' AND ' if where else 'WHERE '}action = 'BUY'",
        params
    ).fetchone()[0]

    sell_count = conn.execute(
        f"SELECT COUNT(*) FROM trades {where + ' AND ' if where else 'WHERE '}action = 'SELL'",
        params
    ).fetchone()[0]

    # SELL取引の勝敗
    wins = conn.execute(
        f"SELECT COUNT(*) FROM trades {where + ' AND ' if where else 'WHERE '}action = 'SELL' AND pnl_pct > 0",
        params
    ).fetchone()[0]

    losses = conn.execute(
        f"SELECT COUNT(*) FROM trades {where + ' AND ' if where else 'WHERE '}action = 'SELL' AND pnl_pct <= 0",
        params
    ).fetchone()[0]

    # 累計損益
    total_pnl = conn.execute(
        f"SELECT COALESCE(SUM(pnl_jpy), 0) FROM trades {where + ' AND ' if where else 'WHERE '}action = 'SELL'",
        params
    ).fetchone()[0]

    # 平均損益%
    avg_pnl_pct = conn.execute(
        f"SELECT COALESCE(AVG(pnl_pct), 0) FROM trades {where + ' AND ' if where else 'WHERE '}action = 'SELL' AND pnl_pct IS NOT NULL",
        params
    ).fetchone()[0]

    # 最大利益・最大損失
    best = conn.execute(
        f"SELECT COALESCE(MAX(pnl_jpy), 0) FROM trades {where + ' AND ' if where else 'WHERE '}action = 'SELL'",
        params
    ).fetchone()[0]

    worst = conn.execute(
        f"SELECT COALESCE(MIN(pnl_jpy), 0) FROM trades {where + ' AND ' if where else 'WHERE '}action = 'SELL'",
        params
    ).fetchone()[0]

    conn.close()

    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

    return {
        "total_trades": total,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "total_pnl_jpy": round(total_pnl),
        "avg_pnl_pct": round(avg_pnl_pct, 2),
        "best_trade_jpy": round(best),
        "worst_trade_jpy": round(worst),
    }


def get_daily_pnl(days: int = 30, symbol: str | None = None) -> list[dict]:
    """日次損益を取得（グラフ用）"""
    conn = _connect()
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    where = "WHERE timestamp >= ?" if not symbol else "WHERE timestamp >= ? AND symbol = ?"
    params = (start,) if not symbol else (start, symbol)

    rows = conn.execute(
        f"""SELECT DATE(timestamp) as date,
                   SUM(CASE WHEN pnl_jpy IS NOT NULL THEN pnl_jpy ELSE 0 END) as pnl
            FROM trades
            {where}
            GROUP BY DATE(timestamp)
            ORDER BY date""",
        params
    ).fetchall()
    conn.close()

    result = []
    cumulative = 0
    for r in rows:
        cumulative += r["pnl"]
        result.append({
            "date": r["date"],
            "daily_pnl": round(r["pnl"]),
            "cumulative_pnl": round(cumulative),
        })
    return result
