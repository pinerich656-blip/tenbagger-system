from __future__ import annotations

from typing import Iterable
import json
import logging
import os
import time

import requests
from bs4 import BeautifulSoup

from .models import StockAnalysis, StockInput

DEFAULT_STOCKS: list[StockInput] = [
    StockInput(name="ランディックス", code="2981.T"),
    StockInput(name="リアルゲイト", code="5532.T"),
    StockInput(name="ブロードエンタープライズ", code="4415.T"),
    StockInput(name="ガーデン", code="274A.T"),
    StockInput(name="マイクロアド", code="9553.T"),
    StockInput(name="ログリー", code="6579.T"),
    StockInput(name="グッドパッチ", code="7351.T"),
    StockInput(name="AI inside", code="4488.T"),
    StockInput(name="パワーエックス", code="4890.T"),
]

logger = logging.getLogger(__name__)

session = requests.Session()
session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }
)

STATE_FILE = os.getenv("STOCK_STATE_FILE", "stock_state.json")
REQUEST_SLEEP_SEC = float(os.getenv("REQUEST_SLEEP_SEC", "3.0"))
MAX_RETRY = int(os.getenv("FETCH_MAX_RETRY", "2"))


def classify_price(price: float, buy_line: float, overheat_line: float) -> str:
    if price <= buy_line:
        return "買い候補"
    if price >= overheat_line:
        return "高値警戒"
    return "様子見"


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _request_with_retry(
    url: str,
    *,
    timeout: int = 10,
    params: dict | None = None,
) -> requests.Response:
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRY + 2):
        try:
            res = session.get(url, params=params, timeout=timeout)

            if res.status_code == 429:
                wait_sec = 8 * attempt
                logger.warning(
                    "[request] rate limited attempt=%s url=%s wait=%ss",
                    attempt,
                    url,
                    wait_sec,
                )
                time.sleep(wait_sec)
                continue

            res.raise_for_status()
            return res

        except Exception as e:
            last_error = e
            logger.warning(
                "[request] failed attempt=%s url=%s params=%s error=%s",
                attempt,
                url,
                params,
                e,
            )
            time.sleep(3 * attempt)

    raise last_error if last_error else RuntimeError("request failed")

def _fetch_from_chart_api(code: str) -> dict | None:
    """
    Yahoo FinanceのチャートAPIから1ヶ月分の日足を取得する。
    """
    try:
        time.sleep(REQUEST_SLEEP_SEC)

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{code}"
        params = {
            "interval": "1d",
            "range": "1mo",
            "includePrePost": "false",
            "events": "div,splits",
        }

        res = _request_with_retry(url, timeout=12, params=params)
        data = res.json()

        result = data.get("chart", {}).get("result", [])
        if not result:
            logger.warning("[chart_api] no result for %s", code)
            return None

        item = result[0]
        quotes = item.get("indicators", {}).get("quote", [])
        if not quotes:
            logger.warning("[chart_api] no quotes for %s", code)
            return None

        quote = quotes[0]
        closes = quote.get("close", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])

        close_vals = [_safe_float(x) for x in closes]
        high_vals = [_safe_float(x) for x in highs]
        low_vals = [_safe_float(x) for x in lows]

        close_vals = [x for x in close_vals if x is not None]
        high_vals = [x for x in high_vals if x is not None]
        low_vals = [x for x in low_vals if x is not None]

        if not close_vals or not high_vals or not low_vals:
            logger.warning("[chart_api] insufficient OHLC for %s", code)
            return None

        current_price = close_vals[-1]
        month_low = min(low_vals)
        month_high = max(high_vals)

        return {
            "current_price": round(current_price, 2),
            "month_low": round(month_low, 2),
            "month_high": round(month_high, 2),
            "source": "chart_api",
        }

    except Exception as e:
        logger.warning("[chart_api] failed for %s: %s", code, e)
        return None


def _fetch_current_price_from_quote_page(code: str) -> float | None:
    """
    最終フォールバック。現在値だけ取得する。
    """
    try:
        code_clean = code.replace(".T", "")
        url = f"https://finance.yahoo.co.jp/quote/{code_clean}"

        time.sleep(REQUEST_SLEEP_SEC)
        res = _request_with_retry(url, timeout=10)

        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text("\n", strip=True)

        import re

        idx = text.find(code_clean)
        if idx == -1:
            logger.warning("[quote_page] code not found in page text: %s", code)
            return None

        window = text[idx:idx + 1200]

        m = re.search(r"([0-9,]+)\n前日比", window)
        if not m:
            m = re.search(r"([0-9,]+)\s*円", window)

        if not m:
            logger.warning("[quote_page] price regex miss: %s", code)
            return None

        return float(m.group(1).replace(",", ""))

    except Exception as e:
        logger.warning("[quote_page] failed for %s: %s", code, e)
        return None


def fetch_price_data(code: str) -> dict | None:
    """
    優先順位:
    1. chart APIから現在値・1ヶ月安値・1ヶ月高値を取得
    2. ダメなら現在値だけ取得
       ただし month_low / month_high が無いと誤判定しやすいので None 扱い
    """
    chart_data = _fetch_from_chart_api(code)
    if chart_data is not None:
        return chart_data

    fallback_price = _fetch_current_price_from_quote_page(code)
    if fallback_price is None:
        return None

    logger.warning("[fetch_price_data] fallback current price only for %s", code)
    return None


def _load_previous_state() -> dict[str, dict]:
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except Exception as e:
        logger.warning("[state] load failed: %s", e)
        return {}


def _save_current_state(results: list[StockAnalysis]) -> None:
    try:
        payload: dict[str, dict] = {}
        for r in results:
            payload[r.code] = {
                "name": r.name,
                "price": r.price,
                "fair_price": r.fair_price,
                "danger_price": r.danger_price,
                "status": r.status,
            }

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("[state] save failed: %s", e)


def build_notifications(
    results: list[StockAnalysis],
    previous_state: dict[str, dict] | None = None,
) -> list[str]:
    prev = previous_state or {}
    messages: list[str] = []

    for r in results:
        old = prev.get(r.code, {})
        old_status = old.get("status")
        old_price = old.get("price")

        # 初回は通知しない
        if old_status is None:
            continue

        if r.status != old_status:
            messages.append(
                f"{r.name}（{r.code}）: {old_status} → {r.status} "
                f"/ 株価 {old_price} → {r.price} / 買いライン {r.fair_price}"
            )
            continue

        if r.status == "買い候補" and old_price != r.price:
            messages.append(
                f"{r.name}（{r.code}）: 買い候補継続 / 株価 {old_price} → {r.price} "
                f"/ 買いライン {r.fair_price}"
            )

    return messages


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

        price = float(price_data["current_price"])
        month_low = float(price_data["month_low"])
        month_high = float(price_data["month_high"])

        buy_line = round(month_low * 1.04, 2)
        overheat_line = round(month_high * 0.97, 2)

        if overheat_line <= buy_line:
            overheat_line = round(buy_line * 1.03, 2)

        status = classify_price(price, buy_line, overheat_line)

        results.append(
            StockAnalysis(
                name=stock.name,
                code=stock.code,
                price=round(price, 2),
                fair_price=buy_line,
                danger_price=overheat_line,
                status=status,
            )
        )

    return results


def analyze_and_collect_notifications(
    stocks: Iterable[StockInput] | None = None,
) -> tuple[list[StockAnalysis], list[str]]:
    previous_state = _load_previous_state()
    results = analyze_stocks(stocks)
    notifications = build_notifications(results, previous_state)
    _save_current_state(results)
    return results, notifications
