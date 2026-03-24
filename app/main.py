from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from .strategy import analyze_stocks

app = FastAPI(title="Tenbagger System API")

@app.get("/")
def root() -> dict:
    return {"message": "Tenbagger System API is running."}

@app.head("/")
def root_head() -> Response:
    return Response(status_code=200)

@app.get("/analyze")
def analyze():
    results = analyze_stocks()
    data = [item.model_dump() for item in results]
    return JSONResponse(content=data, media_type="application/json; charset=utf-8")

@app.get("/buy")
def buy_candidates():
    results = analyze_stocks()

    buys = [
        item.model_dump()
        for item in results
        if item.status == "買い候補"
    ]

    return JSONResponse(content=buys, media_type="application/json; charset=utf-8")
