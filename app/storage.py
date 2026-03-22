from __future__ import annotations

from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
TRADES_FILE = DATA_DIR / "trades.csv"

def append_trade_log(log: dict) -> None:
    df = pd.DataFrame([log])
    if TRADES_FILE.exists():
        old = pd.read_csv(TRADES_FILE)
        df = pd.concat([old, df], ignore_index=True)
    df.to_csv(TRADES_FILE, index=False)
