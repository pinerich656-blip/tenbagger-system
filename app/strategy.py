from __future__ import annotations

from typing import Iterable
import traceback

import yfinance as yf

from .models import StockAnalysis, StockInput

DEFAULT_STOCKS: list[StockInput] = [
    StockInput(name="ランディックス", code="2981.T"),
    StockInput(name="リアルゲイト", code="5532.T"),

    StockInput(name="ブロードエンタープライズ", code="4415.T"),
    StockInput(name="パワーエックス", code="485A.T"),

    # ←ここ追加
    StockInput(name="ガーデン", code="274A.T"),

    StockInput(name="マイクロアド", code="9553.T"),
    StockInput(name="エッジテクノロジー", code="4268.T"),
    StockInput(name="データX", code="3905.T"),
    StockInput(name="ログリー", code="6579.T"),
    StockInput(name="グッドパッチ", code="7351.T"),
    StockInput(name="AI inside", code="4488.T"),
]

def fetch_price_data(code: str):
    try:
        ticker = yf.Ticker(code)
        hist = ticker.history(period="1mo", interval="1d", auto_adjust=False)

        if hist is not None and not hist.empty and "Close" in hist.columns:
            closes = hist["Close"].dropna()
            if not closes.empty:
                current_price = float(closes.iloc[-1])
                month_low = float(closes.min())
                month_high = float(closes.max())

                return {
                    "current_price": current_price,
                    "month_low": month_low,
                    "month_high": month_high,
                }

        # 履歴が取れないときの予備ルート
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info:
            last_price = fast_info.get("lastPrice") or fast_info.get("last_price")
            day_low = fast_info.get("dayLow") or fast_info.get("day_low")
            day_high = fast_info.get("dayHigh") or fast_info.get("day_high")

            if last_price:
                current_price = float(last_price)
                month_low = float(day_low) if day_low else current_price * 0.95
                month_high = float(day_high) if day_high else current_price * 1.05

                return {
                    "current_price": current_price,
                    "month_low": month_low,
                    "month_high": month_high,
                }

        return None

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

        # 買いライン: 1か月安値から8%上まで
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
