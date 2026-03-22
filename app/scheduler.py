from __future__ import annotations

import time
import schedule

from .notifications import send_line_notify
from .strategy import analyze_stocks

def screening_job() -> None:
    results = analyze_stocks()
    buy_candidates = [r for r in results if r.status == "買い候補"]
    if buy_candidates:
        lines = ["買い候補があります:"]
        for item in buy_candidates:
            lines.append(f"- {item.name} ({item.code}) 現在値 {item.price} 円")
        send_line_notify("\n".join(lines))

def run_scheduler() -> None:
    schedule.every().day.at("07:00").do(screening_job)
    print("scheduler started")
    while True:
        schedule.run_pending()
        time.sleep(30)
