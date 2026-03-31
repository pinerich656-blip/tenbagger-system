from __future__ import annotations

from typing import Iterable
import requests

from .config import settings
from .models import StockAnalysis, StockInput

DEFAULT_STOCKS: list[StockInput] = [
    StockInput(name="ランディックス", code="2981"),
    StockInput(name="リアルゲイト", code="5532"),
    StockInput(name="ブロードエンタープライズ", code="4415"),
    StockInput(name="ガーデン", code="274A"),
]

BASE_URL = "https://api.twelvedata.com"


def td_symbol(code: str) -> str:
    return code


def classify_price(price: float, buy_line: float, danger_line: float) -> str:
    if price <= buy_line:
        return "買い候補"
    if price >= danger_line:
        return "危険"
    return "様子見"


def fetch_price_data(code: str) -> dict | None:
    if not settings.twelve_data_api_key:
        print("[fetch_price_data] TWELVE_DATA_API_KEY missing")
        return None

    symbol = td_symbol(code)
    print(f"[fetch_price_data] symbol={symbol}")

    try:
        ts_resp = requests.get(
            f"{BASE_URL}/time_series",
            params={
                "symbol": symbol,
                "interval": "1day",
                "outputsize": 30,
                "apikey": settings.twelve_data_api_key,
            },
            timeout=20,
        )
        ts_data = ts_resp.json()
        print(f"[fetch_price_data] time_series response for {symbol}: {ts_data}")

        values = ts_data.get("values", [])
        closes: list[float] = []

        for row in values:
            close_val = row.get("close")
            if close_val is None:
                continue
            try:
                closes.append(float(close_val))
            except (TypeError, ValueError):
                continue

        if closes:
            current_price = closes[0]
            month_low = min(closes)
            month_high = max(closes)

            return {
                "current_price": current_price,
                "month_low": month_low,
                "month_high": month_high,
            }

        price_resp = requests.get(
            f"{BASE_URL}/price",
            params={
                "symbol": symbol,
                "apikey": settings.twelve_data_api_key,
            },
            timeout=20,
        )
        price_data = price_resp.json()
        print(f"[fetch_price_data] price response for {symbol}: {price_data}")

        price_str = price_data.get("price")
        if price_str is not None:
            current_price = float(price_str)
            return {
                "current_price": current_price,
                "month_low": current_price * 0.97,
                "month_high": current_price * 1.08,
            }

        return None

    except Exception as e:
        print(f"[fetch_price_data] failed for {code}: {e}")
        return None
    


def analyze_stocks(stocks: Iterable[StockInput] | None = None) -> list[StockAnalysis]:
    targets = list(stocks) if stocks is not None else DEFAULT_STOCKS
    results: list[StockAnalysis] = []

    for stock in targets:
        price_data = fetch_price_data(stock.code)

        if price_data is None:
            results.append(
                StockAnalysis(
                    name=stock.name,
                    code=stock.code,
                    price=0.0,
                    fair_price=0.0,
                    danger_price=0.0,
                    status="取得失敗",
                )
            )
            continue

        price = price_data["current_price"]
        month_low = price_data["month_low"]
        month_high = price_data["month_high"]

        buy_line = round(month_low * 1.04, 2)
        danger_line = round(max(month_high * 0.95, price * 1.10), 2)

        status = classify_price(price, buy_line, danger_line)

        results.append(
            StockAnalysis(
                name=stock.name,
                code=stock.code,
                price=round(price, 2),
                fair_price=buy_line,
                danger_price=round(danger_line, 2),
                status=status,
            )
        )

    return results
