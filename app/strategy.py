from __future__ import annotations

from typing import Iterable
import json
import logging
import os
import re
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
REQUEST_SLEEP_SEC = float(os.getenv("REQUEST_SLEEP_SEC", "1.5"))
MAX_RETRY = int(os.getenv("FETCH_MAX_RETRY", "2"))


def classify_price(price: float, buy_line: float, danger_line: float) -> str:
    if price <= buy_line:
        return "買い候補"
    if price >= danger_line:
        return "危険"
    return "様子見"


def _request_with_retry(url: str, *, timeout: int = 10) -> requests.Response:
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRY + 2):
        try:
            res = session.get(url, timeout=timeout)

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
                "[request] failed attempt=%s url=%s error=%s",
                attempt,
                url,
                e,
            )
            time.sleep(2 * attempt)

    raise last_error if last_error else RuntimeError("request failed")


def fetch_price_data(code: str) -> dict | None:
    """
    Yahooファイナンス日本の個別ページから現在値を取得する。
    ※ month_low / month_high は擬似計算
    """
    try:
        time.sleep(REQUEST_SLEEP_SEC)

        code_clean = code.replace(".T", "")
        url = f"https://finance.yahoo.co.jp/quote/{code_clean}"

        res = _request_with_retry(url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text("\n", strip=True)

        idx = text.find(code_clean)
        if idx == -1:
            logger.warning("[fetch_price_data] code not found in page text: %s", code)
            return None

        window = text[idx:idx + 1500]

        m = re.search(r"([0-9,]+)\n前日比", window)
        if not m:
            m = re.search(r"([0-9,]+)\s*円", window)
        if not m:
            logger.warning("[fetch_price_data] price regex miss for %s", code)
            return None

        price = float(m.group(1).replace(",", ""))

        # 仮の1ヶ月レンジ
        # 完全な実測値ではないが、現行Render運用では止まりにくさを優先
        month_low = round(price * 0.95, 2)
        month_high = round(price * 1.05, 2)

        return {
            "current_price": round(price, 2),
            "month_low": month_low,
            "month_high": month_high,
            "source": "yahoo_quote_page",
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


def analyze_and_collect_notifications(
    stocks: Iterable[StockInput] | None = None,
) -> tuple[list[StockAnalysis], list[str]]:
    previous_state = _load_previous_state()
    results = analyze_stocks(stocks)
    notifications = build_notifications(results, previous_state)
    _save_current_state(results)
    return results, notifications
