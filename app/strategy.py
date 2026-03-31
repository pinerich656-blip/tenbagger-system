from __future__ import annotations

from typing import Iterable
import traceback

import yfinance as yf

from .models import StockAnalysis, StockInput


def test_yfinance():
    data = yf.download("2981.T", period="5d")
    print(data)
    return data


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


def fetch_prices_batch(codes: list[str]) -> dict[str, dict]:
    try:
        data = yf.download(
            tickers=" ".join(codes),
            period="1mo",
            interval="1d",
            auto_adjust=False,
            group_by="ticker",
            progress=False,
            threads=False,
        )

        results: dict[str, dict] = {}

        for code in codes:
            try:
                if len(codes) == 1:
                    closes = data["Close"].dropna()
                else:
                    if code not in data.columns.get_level_values(0):
                        continue
                    closes = data[code]["Close"].dropna()

                if closes.empty:
                    continue

                current_price = float(closes.iloc[-1])
                month_low = float(closes.min())
                month_high = float(closes.max())

                results[code] = {
                    "current_price": current_price,
                    "month_low": month_low,
                    "month_high": month_high,
                }
            except Exception:
                print(f"[fetch_prices_batch] failed parsing {code}")
                print(traceback.format_exc())
                continue

        return results

    except Exception:
        print("[fetch_prices_batch] batch download failed")
        print(traceback.format_exc())
        return {}


def analyze_stocks(stocks: Iterable[StockInput] | None = None) -> list[StockAnalysis]:
    targets = list(stocks) if stocks is not None else DEFAULT_STOCKS
    codes = [s.code for s in targets]

    price_map = fetch_prices_batch(codes)
    results: list[StockAnalysis] = []

    for stock in targets:
        price_data = price_map.get(stock.code)
        if price_data is None:
            print(f"[analyze_stocks] skipped {stock.code} because price_data is None")
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
                danger_price=danger_line,
                status=status,
            )
        )

    return results
