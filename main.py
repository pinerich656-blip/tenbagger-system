from __future__ import annotations

from fastapi import FastAPI

from .strategy import analyze_stocks

app = FastAPI(title="Tenbagger System API")

@app.get("/")
def root() -> dict:
    return {"message": "Tenbagger System API is running."}

@app.get("/analyze")
def analyze() -> list[dict]:
    results = analyze_stocks()
    return [item.model_dump() for item in results]
