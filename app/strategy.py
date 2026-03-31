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
from bs4 import BeautifulSoup
import time


def fetch_price_data(code: str) -> dict | None:
    try:
        time.sleep(1)

        code_clean = code.replace(".T", "")
        url = f"https://finance.yahoo.co.jp/quote/{code_clean}"

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        # ① メイン
        price_tag = soup.select_one("span[class*='_3rXWJKZF']")

        # ② フォールバック
        if not price_tag:
            price_tag = soup.select_one("span[class*='Price']")

        if not price_tag:
            return None

        price = float(price_tag.text.replace(",", "").replace("円", ""))

        return {
            "current_price": price,
            "month_low": price * 0.95,
            "month_high": price * 1.05,
        }

    except Exception as e:
        print(f"[fetch_price_data] failed: {e}")
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
