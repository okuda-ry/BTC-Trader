"""暗号資産自動売買 エントリーポイント"""
import argparse
import logging
import sys
from trade_manager import TradeManager


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("trader.log", encoding="utf-8"),
        ],
    )


def main():
    parser = argparse.ArgumentParser(description="Crypto Auto Trader (GMOコイン + Claude AI)")
    parser.add_argument("--live", action="store_true", help="実際に注文を出す")
    parser.add_argument("--once", action="store_true", help="1回だけ実行して終了")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING"])
    args = parser.parse_args()

    setup_logging(args.log_level)
    manager = TradeManager(dry_run=not args.live)

    if args.once:
        manager.run_once()
    else:
        manager.run_loop()


if __name__ == "__main__":
    main()
