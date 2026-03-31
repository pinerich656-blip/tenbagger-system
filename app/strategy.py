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


def classify_price(price: float, buy_line: float, danger_line: float) -> str:
    if price <= buy_line:
        return "買い候補"
    if price >= danger_line:
        return "危険"
    return "様子見"


def resolve_symbol(code: str) -> tuple[str | None, str]:
    if not settings.twelve_data_api_key:
        return None, "APIキー未設定"

    try:
        resp = requests.get(
            f"{BASE_URL}/symbol_search",
            params={
                "symbol": code,
                "apikey": settings.twelve_data_api_key,
            },
            timeout=20,
        )
        data = resp.json()

        items = data.get("data")
        if not items:
            return None, f"symbol_search失敗: {data}"

        for item in items:
            symbol = str(item.get("symbol", ""))
            exchange = str(item.get("exchange", ""))
            mic_code = str(item.get("mic_code", ""))

            if code in symbol and (
                "Tokyo" in exchange
                or "Japan" in exchange
                or mic_code == "XJPX"
            ):
                return symbol, "OK"

        return str(items[0].get("symbol")), "候補先頭を採用"

    except Exception as e:
        return None, f"symbol_search例外: {e}"


def fetch_price_data(code: str) -> tuple[dict | None, str]:
    symbol, reason = resolve_symbol(code)
    if not symbol:
        return None, reason

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
            }, f"OK symbol={symbol}"

        price_resp = requests.get(
            f"{BASE_URL}/price",
            params={
                "symbol": symbol,
                "apikey": settings.twelve_data_api_key,
            },
            timeout=20,
        )
        price_data = price_resp.json()

        price_str = price_data.get("price")
        if price_str is not None:
            current_price = float(price_str)
            return {
                "current_price": current_price,
                "month_low": current_price * 0.97,
                "month_high": current_price * 1.08,
            }, f"price fallback OK symbol={symbol}"

        return None, f"time_series/price失敗 symbol={symbol} ts={ts_data} price={price_data}"

    except Exception as e:
        return None, f"price取得例外 symbol={symbol}: {e}"


def analyze_stocks(stocks: Iterable[StockInput] | None = None) -> list[StockAnalysis]:
    targets = list(stocks) if stocks is not None else DEFAULT_STOCKS
    results: list[StockAnalysis] = []

    for stock in targets:
        price_data, reason = fetch_price_data(stock.code)

        if price_data is None:
            results.append(
                StockAnalysis(
                    name=stock.name,
                    code=stock.code,
                    price=0.0,
                    fair_price=0.0,
                    danger_price=0.0,
                    status=reason[:120],
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
