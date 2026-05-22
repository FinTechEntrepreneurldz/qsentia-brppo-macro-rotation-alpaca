from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
import requests

from .data import assert_http_ok


@dataclass(frozen=True)
class AlpacaSettings:
    api_key_id: str
    api_secret_key: str
    trading_base_url: str = "https://paper-api.alpaca.markets"
    data_base_url: str = "https://data.alpaca.markets"
    data_feed: str = "iex"

    @classmethod
    def from_env(cls) -> "AlpacaSettings":
        key = os.getenv("APCA_API_KEY_ID") or os.getenv("ALPACA_API_KEY_ID")
        secret = os.getenv("APCA_API_SECRET_KEY") or os.getenv("ALPACA_API_SECRET_KEY")
        if not key or not secret:
            raise RuntimeError("Missing APCA_API_KEY_ID/APCA_API_SECRET_KEY for Alpaca.")
        return cls(
            api_key_id=key,
            api_secret_key=secret,
            trading_base_url=os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/"),
            data_base_url=os.getenv("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets").rstrip("/"),
            data_feed=os.getenv("ALPACA_DATA_FEED", "iex"),
        )


class AlpacaClient:
    def __init__(self, settings: AlpacaSettings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update(
            {
                "APCA-API-KEY-ID": settings.api_key_id,
                "APCA-API-SECRET-KEY": settings.api_secret_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _trading(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.session.request(method, f"{self.settings.trading_base_url}{path}", timeout=30, **kwargs)
        assert_http_ok(response)
        return response.json() if response.text else None

    def _data(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.session.request(method, f"{self.settings.data_base_url}{path}", timeout=45, **kwargs)
        assert_http_ok(response)
        return response.json() if response.text else None

    def get_account(self) -> dict[str, Any]:
        return dict(self._trading("GET", "/v2/account"))

    def get_clock(self) -> dict[str, Any]:
        return dict(self._trading("GET", "/v2/clock"))

    def get_positions(self) -> list[dict[str, Any]]:
        return list(self._trading("GET", "/v2/positions"))

    def cancel_open_orders(self) -> Any:
        return self._trading("DELETE", "/v2/orders")

    def submit_market_order(
        self,
        symbol: str,
        side: str,
        notional: float | None = None,
        qty: float | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        if notional is None and qty is None:
            raise ValueError("Either notional or qty is required.")
        payload: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }
        if notional is not None:
            payload["notional"] = f"{notional:.2f}"
        else:
            payload["qty"] = f"{qty:.6f}"
        if client_order_id:
            payload["client_order_id"] = client_order_id[:48]
        return dict(self._trading("POST", "/v2/orders", json=payload))

    def get_stock_bars(
        self,
        symbols: list[str],
        start: date | str,
        end: date | str,
        timeframe: str = "1Day",
        adjustment: str = "all",
        limit: int = 10000,
    ) -> pd.DataFrame:
        params = {
            "symbols": ",".join(symbols),
            "timeframe": timeframe,
            "start": str(start),
            "end": str(end),
            "limit": limit,
            "adjustment": adjustment,
            "feed": self.settings.data_feed,
        }
        all_bars: dict[str, list[dict[str, Any]]] = {}
        while True:
            payload = self._data("GET", "/v2/stocks/bars", params=params)
            for symbol, bars in dict(payload.get("bars", {})).items():
                all_bars.setdefault(symbol, []).extend(bars)
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token

        rows = []
        for symbol, bars in all_bars.items():
            for bar in bars:
                rows.append({"date": pd.to_datetime(bar["t"], utc=True).tz_convert(None).normalize(), "symbol": symbol, "close": bar["c"]})
        if not rows:
            raise RuntimeError("Alpaca returned no historical bars.")
        frame = pd.DataFrame(rows)
        prices = frame.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index().ffill()
        prices.index = pd.DatetimeIndex(prices.index).tz_localize(None)
        return prices
