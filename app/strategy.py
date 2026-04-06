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

# 価格変動ベースの判定閾値
BUY_DROP_PCT = float(os.getenv("BUY_DROP_PCT", "0.03"))          # 前回比 -3% で買い候補
STRONG_BUY_DROP_PCT = float(os.getenv("STRONG_BUY_DROP_PCT", "0.05"))  # 前回比 -5% で強い買い候補メモ用
DANGER_RISE_PCT = float(os.getenv("DANGER_RISE_PCT", "0.08"))    # 前回比 +8% で高値警戒


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


def _extract_price_from_text(text: str, code: str) -> float | None:
    code_clean = code.replace(".T", "")

    patterns = [
        rf"{re.escape(code_clean)}.*?\n([0-9,]+)\n前日比",
        rf"{re.escape(code_clean)}.*?([0-9,]+)\s*円",
        r"([0-9,]+)\n前日比",
        r"([0-9,]+)\s*円",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return round(float(m.group(1).replace(",", "")), 2)
            except ValueError:
                continue

    return None


def _fetch_from_yahoo_jp(code: str) -> float | None:
    code_clean = code.replace(".T", "")
    url = f"https://finance.yahoo.co.jp/quote/{code_clean}"

    res = _request_with_retry(url, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")
    text = soup.get_text("\n", strip=True)

    price = _extract_price_from_text(text, code)
    if price is None:
        logger.warning("[_fetch_from_yahoo_jp] price regex miss for %s", code)
    return price


def _fetch_from_yahoo_com(code: str) -> float | None:
    url = f"https://finance.yahoo.com/quote/{code}"

    res = _request_with_retry(url, timeout=10)
    text = BeautifulSoup(res.text, "html.parser").get_text("\n", strip=True)

    patterns = [
        r"current price is\s*([0-9,]+\.[0-9]+)",
        r"Previous Close\s*([0-9,]+\.[0-9]+)",
        r"Open\s*([0-9,]+\.[0-9]+)",
        r"([0-9,]+\.[0-9]+)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if m:
            try:
                return round(float(m.group(1).replace(",", "")), 2)
            except ValueError:
                continue

    logger.warning("[_fetch_from_yahoo_com] price regex miss for %s", code)
    return None


def fetch_current_price(code: str) -> float | None:
    """
    1. Yahooファイナンス日本の個別ページ
    2. ダメなら Yahoo.com の個別ページ
    """
    try:
        time.sleep(REQUEST_SLEEP_SEC)

        try:
            price = _fetch_from_yahoo_jp(code)
            if price is not None:
                return price
        except Exception as e:
            logger.warning("[fetch_current_price] yahoo_jp failed for %s: %s", code, e)

        time.sleep(REQUEST_SLEEP_SEC)

        try:
            price = _fetch_from_yahoo_com(code)
            if price is not None:
                return price
        except Exception as e:
            logger.warning("[fetch_current_price] yahoo_com failed for %s: %s", code, e)

        return None

    except Exception as e:
        logger.warning("[fetch_current_price] failed for %s: %s", code, e)
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

def _save_current_state(results: list[StockAnalysis], change_map: dict[str, dict]) -> None:
    try:
        payload: dict[str, dict] = {}

        for r in results:
            extra = change_map.get(r.code, {})
            payload[r.code] = {
                "name": r.name,
                "price": r.price,
                "fair_price": r.fair_price,
                "danger_price": r.danger_price,
                "status": r.status,
                "prev_price": extra.get("prev_price"),
                "change_pct": extra.get("change_pct"),
            }

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.warning("[state] save failed: %s", e)

        


def _calc_price_change_pct(current_price: float, prev_price: float | None) -> float | None:
    if prev_price is None or prev_price <= 0:
        return None
    return (current_price - prev_price) / prev_price


def _build_lines_from_prev_price(current_price: float, prev_price: float | None) -> tuple[float, float]:
    """
    StockAnalysisの fair_price / danger_price を維持するための値。
    fair_price: 買い候補ライン（前回価格ベース）
    danger_price: 高値警戒ライン（前回価格ベース）
    """
    base = prev_price if prev_price and prev_price > 0 else current_price
    buy_line = round(base * (1 - BUY_DROP_PCT), 2)
    danger_line = round(base * (1 + DANGER_RISE_PCT), 2)
    return buy_line, danger_line


def classify_price_change(current_price: float, prev_price: float | None) -> str:
    """
    前回価格比で判定する。
    初回は様子見。
    """
    change_pct = _calc_price_change_pct(current_price, prev_price)

    if change_pct is None:
        return "様子見"

    if change_pct <= -BUY_DROP_PCT:
        return "買い候補"

    if change_pct >= DANGER_RISE_PCT:
        return "高値警戒"

    return "様子見"


def _format_pct(change_pct: float | None) -> str:
    if change_pct is None:
        return "N/A"
    return f"{change_pct * 100:+.2f}%"


def build_notifications(
    results: list[StockAnalysis],
    previous_state: dict[str, dict] | None = None,
    change_map: dict[str, dict] | None = None,
) -> list[str]:
    prev = previous_state or {}
    meta = change_map or {}
    messages: list[str] = []

    for r in results:
        old = prev.get(r.code, {})
        old_status = old.get("status")
        old_price = old.get("price")
        change_pct = meta.get(r.code, {}).get("change_pct")

        # 初回は通知しない
        if old_price is None:
            continue

        if r.status != old_status:
            msg = (
                f"{r.name}（{r.code}）: {old_status} → {r.status} "
                f"/ 株価 {old_price} → {r.price} "
                f"/ 変動率 {_format_pct(change_pct)} "
                f"/ 買いライン {r.fair_price}"
            )
            if change_pct is not None and change_pct <= -STRONG_BUY_DROP_PCT:
                msg += " / 急落"
            messages.append(msg)
            continue

        if r.status == "買い候補" and old_price != r.price:
            msg = (
                f"{r.name}（{r.code}）: 買い候補継続 "
                f"/ 株価 {old_price} → {r.price} "
                f"/ 変動率 {_format_pct(change_pct)} "
                f"/ 買いライン {r.fair_price}"
            )
            if change_pct is not None and change_pct <= -STRONG_BUY_DROP_PCT:
                msg += " / 急落"
            messages.append(msg)

    return messages


def analyze_stocks(stocks: Iterable[StockInput] | None = None) -> list[StockAnalysis]:
    previous_state = _load_previous_state()
    targets = list(stocks) if stocks is not None else DEFAULT_STOCKS
    results: list[StockAnalysis] = []

    for stock in targets:
        current_price = fetch_current_price(stock.code)

        if current_price is None:
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

        prev_price_raw = previous_state.get(stock.code, {}).get("price")
        prev_price = float(prev_price_raw) if prev_price_raw not in (None, 0, 0.0) else None

        buy_line, danger_line = _build_lines_from_prev_price(current_price, prev_price)
        status = classify_price_change(current_price, prev_price)

        results.append(
            StockAnalysis(
                name=stock.name,
                code=stock.code,
                price=round(current_price, 2),
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
    targets = list(stocks) if stocks is not None else DEFAULT_STOCKS

    results: list[StockAnalysis] = []
    change_map: dict[str, dict] = {}

    for stock in targets:
        current_price = fetch_current_price(stock.code)

        if current_price is None:
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

        prev_price_raw = previous_state.get(stock.code, {}).get("price")
        prev_price = float(prev_price_raw) if prev_price_raw not in (None, 0, 0.0) else None

        change_pct = _calc_price_change_pct(current_price, prev_price)
        buy_line, danger_line = _build_lines_from_prev_price(current_price, prev_price)
        status = classify_price_change(current_price, prev_price)

        results.append(
            StockAnalysis(
                name=stock.name,
                code=stock.code,
                price=round(current_price, 2),
                fair_price=buy_line,
                danger_price=danger_line,
                status=status,
            )
        )

        change_map[stock.code] = {
            "prev_price": prev_price,
            "change_pct": change_pct,
        }

    notifications = build_notifications(results, previous_state, change_map)
    _save_current_state(results, change_map)
    return results, notifications
