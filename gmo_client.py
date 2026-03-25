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
    def get_ticker(self, symbol: str) -> dict:
        resp = requests.get(
            f"{PUBLIC_URL}/v1/ticker",
            params={"symbol": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] != 0:
            raise RuntimeError(f"GMO ticker エラー: {data}")
        return data["data"][0]

    def get_klines(self, symbol: str, interval: str = "1hour", date: str = "") -> list:
        if not date:
            from datetime import datetime, timezone
            date = datetime.now(timezone.utc).strftime("%Y%m%d")

        resp = requests.get(
            f"{PUBLIC_URL}/v1/klines",
            params={"symbol": symbol, "interval": interval, "date": date},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] != 0:
            raise RuntimeError(f"GMO klines エラー: {data}")
        return data.get("data", [])

    # ---- Private API ----
    def get_assets(self) -> list:
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

    def get_balance(self, symbol: str) -> float:
        """指定シンボルの利用可能残高を返す"""
        for item in self.get_assets():
            if item["symbol"] == symbol:
                return float(item["available"])
        return 0.0

    def get_jpy_balance(self) -> float:
        return self.get_balance("JPY")

    def send_order(
        self,
        symbol: str,
        side: str,
        size: float,
        order_type: str = "LIMIT",
        price: int | None = None,
        size_decimals: int = 5,
    ) -> dict:
        path = "/v1/order"
        body_dict = {
            "symbol": symbol,
            "side": side,
            "executionType": order_type,
            "size": str(round(size, size_decimals)),
        }
        if order_type == "LIMIT" and price is not None:
            body_dict["price"] = str(int(price))
            # FAS (Fill And Store): 板に残り続ける。Makerになりやすい
            # SOKは即キャンセルされるリスクがあるため使わない

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
        logger.info("[%s] 注文送信成功: orderId=%s", symbol, data.get("data"))
        return data

    def get_order_status(self, order_id: str) -> dict:
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
        if data["status"] != 0:
            logger.warning("キャンセルエラー: orderId=%s, response=%s", order_id, data)
        else:
            logger.info("注文キャンセル成功: orderId=%s", order_id)
        return data
