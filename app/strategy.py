from __future__ import annotations

from typing import Iterable
import traceback

import yfinance as yf

from .models import StockAnalysis, StockInput

DEFAULT_STOCKS: list[StockInput] = [
    StockInput(name="ランディックス", code="2981.T"),
    StockInput(name="リアルゲイト", code="5532.T"),
]


def fetch_price_data(code: str):
    try:
        ticker = yf.Ticker(code)
        hist = ticker.history(period="1mo", interval="1d", auto_adjust=False)

        if hist is None or hist.empty:
            return None

        closes = hist["Close"].dropna()
        if closes.empty:
            return None

        current_price = float(closes.iloc[-1])
        month_low = float(closes.min())
        month_high = float(closes.max())

        return {
            "current_price": current_price,
            "month_low": month_low,
            "month_high": month_high,
        }

    except Exception:
        print(f"[fetch_price_data] failed for {code}")
        print(traceback.format_exc())
        return None


def classify_price(price: float, buy_line: float, danger_line: float) -> str:
    if price <= buy_line:
        return "買い候補"
    if price >= danger_line:
        return "危険"
    return "様子見"


def analyze_stocks(stocks: Iterable[StockInput] | None = None) -> list[StockAnalysis]:
    targets = list(stocks) if stocks is not None else DEFAULT_STOCKS
    results: list[StockAnalysis] = []

    for stock in targets:
        price_data = fetch_price_data(stock.code)
        if price_data is None:
            print(f"[analyze_stocks] skipped {stock.code} because price_data is None")
            continue

        price = price_data["current_price"]
        month_low = price_data["month_low"]
        month_high = price_data["month_high"]

        # 買いライン: 1か月安値から5%上まで
        buy_line = round(month_low * 1.08, 2)

        # 危険ライン: 1か月高値の95%以上
        danger_line = round(month_high * 0.95, 2)

        status = classify_price(price, buy_line, danger_line)

        results.append(
            StockAnalysis(
                name=stock.name,
                code=stock.code,
                price=round(price, 2),
                fair_price=buy_line,
                danger_price=danger_line,
                status=status,
            )
        )

    return results
