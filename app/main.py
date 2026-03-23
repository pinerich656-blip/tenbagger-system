from __future__ import annotations

from fastapi import FastAPI, Response

from .strategy import analyze_stocks

app = FastAPI(title="Tenbagger System API")

@app.get("/")
def root() -> dict:
    return {"message": "Tenbagger System API is running."}

@app.head("/")
def root_head() -> Response:
    return Response(status_code=200)

@app.get("/analyze")
def analyze() -> list[dict]:
    results = analyze_stocks()
    return [item.model_dump() for item in results]
