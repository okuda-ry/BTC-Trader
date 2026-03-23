"""GMOコイン REST API クライアント"""
import hashlib
import hmac
import json
import logging
import time
import requests
import config

logger = logging.getLogger(__name__)

PUBLIC_URL = "https://api.coin.z.com/public"
PRIVATE_URL = "https://api.coin.z.com/private"


class GMOClient:
    def __init__(self):
        self.api_key = config.GMO_API_KEY
        self.api_secret = config.GMO_API_SECRET

    # ---- 認証ヘッダー生成 ----
    def _headers(self, method: str, path: str, body: str = "") -> dict:
        timestamp = str(int(time.time() * 1000))
        text = timestamp + method + path + body
        sign = hmac.new(
            self.api_secret.encode("ascii"),
            text.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "API-KEY": self.api_key,
            "API-TIMESTAMP": timestamp,
            "API-SIGN": sign,
            "Content-Type": "application/json",
        }

    # ---- Public API ----
    def get_ticker(self) -> dict:
        """現在のティッカー情報を取得"""
        resp = requests.get(
            f"{PUBLIC_URL}/v1/ticker",
            params={"symbol": config.PRODUCT_CODE},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] != 0:
            raise RuntimeError(f"GMO API エラー: {data}")
        # 単一シンボル指定でもリストで返る
        return data["data"][0]

    def get_klines(self, interval: str = "1hour", date: str = "") -> list:
        """ローソク足データを取得
        interval: 1min, 5min, 10min, 15min, 30min, 1hour, 4hour, 8hour, 12hour, 1day
        date: YYYYMMDD (日中足) or YYYY (日足以上)
        """
        if not date:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            date = now.strftime("%Y%m%d")

        resp = requests.get(
            f"{PUBLIC_URL}/v1/klines",
            params={
                "symbol": config.PRODUCT_CODE,
                "interval": interval,
                "date": date,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] != 0:
            raise RuntimeError(f"GMO klines エラー: {data}")
        return data.get("data", [])

    def get_orderbooks(self) -> dict:
        """板情報を取得"""
        resp = requests.get(
            f"{PUBLIC_URL}/v1/orderbooks",
            params={"symbol": config.PRODUCT_CODE},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] != 0:
            raise RuntimeError(f"GMO orderbooks エラー: {data}")
        return data["data"]

    # ---- Private API ----
    def get_assets(self) -> list:
        """残高一覧を取得"""
        path = "/v1/account/assets"
        resp = requests.get(
            PRIVATE_URL + path,
            headers=self._headers("GET", path),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] != 0:
            raise RuntimeError(f"GMO assets エラー: {data}")
        return data["data"]

    def get_jpy_balance(self) -> float:
        """JPY の利用可能残高を返す"""
        for item in self.get_assets():
            if item["symbol"] == "JPY":
                return float(item["available"])
        return 0.0

    def get_btc_balance(self) -> float:
        """BTC の利用可能残高を返す"""
        for item in self.get_assets():
            if item["symbol"] == "BTC":
                return float(item["available"])
        return 0.0

    def send_order(
        self,
        side: str,
        size: float,
        order_type: str = "LIMIT",
        price: int | None = None,
    ) -> dict:
        """注文を送信
        side: BUY or SELL
        order_type: LIMIT or MARKET
        price: 指値価格（LIMIT時は必須）
        """
        path = "/v1/order"
        body_dict = {
            "symbol": config.PRODUCT_CODE,
            "side": side,
            "executionType": order_type,
            "size": str(round(size, 5)),
        }
        if order_type == "LIMIT" and price is not None:
            body_dict["price"] = str(int(price))
            # Post-only (SOK) で確実に Maker になる
            body_dict["timeInForce"] = "SOK"

        body = json.dumps(body_dict)
        resp = requests.post(
            PRIVATE_URL + path,
            headers=self._headers("POST", path, body),
            data=body,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] != 0:
            raise RuntimeError(f"GMO order エラー: {data}")
        logger.info("注文送信成功: orderId=%s", data.get("data"))
        return data

    def get_order_status(self, order_id: str) -> dict:
        """注文ステータスを取得"""
        path = "/v1/orders"
        resp = requests.get(
            PRIVATE_URL + path,
            headers=self._headers("GET", path),
            params={"orderId": order_id},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] != 0:
            raise RuntimeError(f"GMO orders エラー: {data}")
        if data["data"]["list"]:
            return data["data"]["list"][0]
        return {}

    def cancel_order(self, order_id: int) -> dict:
        """注文をキャンセル"""
        path = "/v1/cancelOrder"
        body = json.dumps({"orderId": order_id})
        resp = requests.post(
            PRIVATE_URL + path,
            headers=self._headers("POST", path, body),
            data=body,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info("注文キャンセル: orderId=%s, status=%s", order_id, data["status"])
        return data

    def get_active_orders(self) -> list:
        """未約定の注文一覧を取得"""
        path = "/v1/activeOrders"
        resp = requests.get(
            PRIVATE_URL + path,
            headers=self._headers("GET", path),
            params={"symbol": config.PRODUCT_CODE, "count": 100},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] != 0:
            raise RuntimeError(f"GMO activeOrders エラー: {data}")
        return data["data"].get("list", [])
