from __future__ import annotations

from typing import Iterable
import traceback

import yfinance as yf

from .models import StockAnalysis, StockInput

DEFAULT_STOCKS: list[StockInput] = [
    StockInput(name="ランディックス", code="2981.T"),
    StockInput(name="リアルゲイト", code="5532.T"),
]

def fetch_latest_price(code: str) -> float | None:
    try:
        ticker = yf.Ticker(code)
        hist = ticker.history(period="5d", auto_adjust=False)

        if hist is None or hist.empty:
            return None

        closes = hist["Close"].dropna()
        if closes.empty:
            return None

        return float(closes.iloc[-1])
    except Exception:
        print(f"[fetch_latest_price] failed for {code}")
        print(traceback.format_exc())
        return None

def classify_price(price: float, fair_price: float, danger_price: float) -> str:
    if price <= fair_price:
        return "買い候補"
    if price >= danger_price:
        return "危険"
    return "様子見"

def analyze_stocks(stocks: Iterable[StockInput] | None = None) -> list[StockAnalysis]:
    targets = list(stocks) if stocks is not None else DEFAULT_STOCKS
    results: list[StockAnalysis] = []

    for stock in targets:
        price = fetch_latest_price(stock.code)
        if price is None:
            continue

        fair_price = round(price * 0.80, 2)
        danger_price = round(price * 1.30, 2)
        status = classify_price(price, fair_price, danger_price)

        results.append(
            StockAnalysis(
                name=stock.name,
                code=stock.code,
                price=round(price, 2),
                fair_price=fair_price,
                danger_price=danger_price,
                status=status,
            )
        )

    return results
