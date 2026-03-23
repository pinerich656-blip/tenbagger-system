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

        # まず通常の履歴取得
        hist = ticker.history(period="1mo", interval="1d", auto_adjust=False)

        if hist is not None and not hist.empty and "Close" in hist.columns:
            closes = hist["Close"].dropna()
            if not closes.empty:
                return float(closes.iloc[-1])

        # 履歴がダメなら fast_info を試す
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info:
            last_price = fast_info.get("lastPrice") or fast_info.get("last_price")
            if last_price:
                return float(last_price)

        return None

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
            print(f"[analyze_stocks] skipped {stock.code} because price is None")
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
