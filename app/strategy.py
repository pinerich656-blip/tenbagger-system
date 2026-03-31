from __future__ import annotations

from typing import Iterable
import time
import yfinance as yf

from .models import StockAnalysis, StockInput

DEFAULT_STOCKS: list[StockInput] = [
    StockInput(name="ランディックス", code="2981.T"),
    StockInput(name="リアルゲイト", code="5532.T"),
    StockInput(name="ブロードエンタープライズ", code="4415.T"),
    StockInput(name="ガーデン", code="274A.T"),
]


def classify_price(price: float, buy_line: float, danger_line: float) -> str:
    if price <= buy_line:
        return "買い候補"
    if price >= danger_line:
        return "危険"
    return "様子見"


import requests
import yfinance as yf


def fetch_price_data(code: str) -> dict | None:
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0"
        })

        ticker = yf.Ticker(code, session=session)

        hist = ticker.history(period="1mo", interval="1d")

        if hist is None or hist.empty:
            return None

        closes = hist["Close"].dropna()
        if closes.empty:
            return None

        return {
            "current_price": float(closes.iloc[-1]),
            "month_low": float(closes.min()),
            "month_high": float(closes.max()),
        }

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
