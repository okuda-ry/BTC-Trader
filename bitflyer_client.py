"""bitFlyer REST API クライアント"""
import hashlib
import hmac
import time
import requests
import config


class BitFlyerClient:
    def __init__(self):
        self.base_url = config.BITFLYER_BASE_URL
        self.api_key = config.BITFLYER_API_KEY
        self.api_secret = config.BITFLYER_API_SECRET

    # ---- 認証ヘッダー生成 ----
    def _headers(self, method: str, path: str, body: str = "") -> dict:
        timestamp = str(int(time.time()))
        text = timestamp + method + path + body
        sign = hmac.new(
            self.api_secret.encode(), text.encode(), hashlib.sha256
        ).hexdigest()
        return {
            "ACCESS-KEY": self.api_key,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-SIGN": sign,
            "Content-Type": "application/json",
        }

    # ---- Public API ----
    def get_ticker(self) -> dict:
        """現在のティッカー情報を取得"""
        url = f"{self.base_url}/v1/ticker"
        resp = requests.get(url, params={"product_code": config.PRODUCT_CODE}, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_executions(self, count: int = 500) -> list:
        """約定履歴を取得（ローソク足生成用）"""
        url = f"{self.base_url}/v1/executions"
        resp = requests.get(
            url,
            params={"product_code": config.PRODUCT_CODE, "count": count},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # ---- Private API ----
    def get_balance(self) -> list:
        """残高一覧を取得"""
        path = "/v1/me/getbalance"
        resp = requests.get(
            self.base_url + path,
            headers=self._headers("GET", path),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_jpy_balance(self) -> float:
        """JPY 残高を返す"""
        for item in self.get_balance():
            if item["currency_code"] == "JPY":
                return float(item["available"])
        return 0.0

    def get_btc_balance(self) -> float:
        """BTC 残高を返す"""
        for item in self.get_balance():
            if item["currency_code"] == "BTC":
                return float(item["available"])
        return 0.0

    def send_order(
        self,
        side: str,
        size: float,
        order_type: str = "MARKET",
        price: int | None = None,
    ) -> dict:
        """注文を送信 (side: BUY or SELL)"""
        import json

        path = "/v1/me/sendchildorder"
        body_dict = {
            "product_code": config.PRODUCT_CODE,
            "child_order_type": order_type,
            "side": side,
            "size": round(size, 8),
        }
        if order_type == "LIMIT" and price is not None:
            body_dict["price"] = price

        body = json.dumps(body_dict)
        resp = requests.post(
            self.base_url + path,
            headers=self._headers("POST", path, body),
            data=body,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_positions(self) -> list:
        """建玉一覧（現物の場合は使わないが互換性のため）"""
        path = "/v1/me/getpositions"
        params = f"?product_code={config.PRODUCT_CODE}"
        resp = requests.get(
            self.base_url + path + params,
            headers=self._headers("GET", path + params),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
