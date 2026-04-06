from __future__ import annotations

from typing import Iterable
import csv
import io
import json
import logging
import os
import time
from datetime import datetime

import requests

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
REQUEST_SLEEP_SEC = float(os.getenv("REQUEST_SLEEP_SEC", "1.0"))
MAX_RETRY = int(os.getenv("FETCH_MAX_RETRY", "2"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "22"))  # 営業日ベースで約1か月


def classify_price(price: float, buy_line: float, overheat_line: float) -> str:
    if price <= buy_line:
        return "買い候補"
    if price >= overheat_line:
        return "高値警戒"
    return "様子見"


def _to_stooq_symbol(code: str) -> str:
    # 2981.T -> 2981.jp
    return code.replace(".T", "").lower() + ".jp"


def _safe_float(value: str | None) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _request_with_retry(
    url: str,
    *,
    timeout: int = 15,
    params: dict | None = None,
) -> requests.Response:
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRY + 2):
        try:
            res = session.get(url, params=params, timeout=timeout)

            if res.status_code == 429:
                wait_sec = 5 * attempt
                last_error = RuntimeError(f"429 Too Many Requests: {url}")
                logger.warning(
                    "[request] rate limited attempt=%s url=%s wait=%ss",
                    attempt,
                    url,
                    wait_sec,
                )
                time.sleep(wait_sec)
                continue

            if res.status_code >= 500:
                wait_sec = 4 * attempt
                last_error = RuntimeError(f"{res.status_code} Server Error: {url}")
                logger.warning(
                    "[request] server error attempt=%s url=%s status=%s wait=%ss",
                    attempt,
                    url,
                    res.status_code,
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
            time.sleep(2 * attempt)

    raise last_error if last_error else RuntimeError("request failed")


def fetch_price_data(code: str) -> dict | None:
    """
    Stooq のCSV日足から現在値・1か月安値・1か月高値を取得する。
    """
    try:
        time.sleep(REQUEST_SLEEP_SEC)

        symbol = _to_stooq_symbol(code)
        url = "https://stooq.com/q/d/l/"
        params = {
            "s": symbol,
            "i": "d",  # daily
        }

        res = _request_with_retry(url, timeout=15, params=params)
        text = res.text.strip()

        if not text or "No data" in text:
            logger.warning("[fetch_price_data] no csv data for %s (%s)", code, symbol)
            return None

        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)

        if not rows:
            logger.warning("[fetch_price_data] empty csv rows for %s (%s)", code, symbol)
            return None

        parsed_rows: list[dict] = []
        for row in rows:
            date_str = row.get("Date")
            close_v = _safe_float(row.get("Close"))
            high_v = _safe_float(row.get("High"))
            low_v = _safe_float(row.get("Low"))

            if not date_str or close_v is None or high_v is None or low_v is None:
                continue

            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue

            parsed_rows.append(
                {
                    "date": dt,
                    "close": close_v,
                    "high": high_v,
                    "low": low_v,
                }
            )

        if not parsed_rows:
            logger.warning("[fetch_price_data] no valid rows for %s (%s)", code, symbol)
            return None

        parsed_rows.sort(key=lambda x: x["date"])
        recent = parsed_rows[-LOOKBACK_DAYS:]

        if len(recent) < 5:
            logger.warning(
                "[fetch_price_data] insufficient recent rows for %s (%s): %s",
                code,
                symbol,
                len(recent),
            )
            return None

        current_price = recent[-1]["close"]
        month_low = min(r["low"] for r in recent)
        month_high = max(r["high"] for r in recent)

        return {
            "current_price": round(current_price, 2),
            "month_low": round(month_low, 2),
            "month_high": round(month_high, 2),
            "source": "stooq_csv",
        }

    except Exception as e:
        logger.warning("[fetch_price_data] failed for %s: %s", code, e)
        return None


def _load_previous_state() -> dict[str, dict]:
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
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
