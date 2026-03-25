from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from .strategy import analyze_stocks
from .notifications import send_line_push

app = FastAPI(title="Tenbagger System API")

SECRET_KEY = "buycheck_2026_yutaka_9x7pL2"


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

    if buys:
        msg = "【買い候補】\n"
        for b in buys:
            msg += f"{b['name']} ({b['code']}) {b['price']}円\n"

        send_line_push(msg)

    return JSONResponse(content=buys, media_type="application/json; charset=utf-8")


@app.get("/test-line")
def test_line(key: str):
    if key != SECRET_KEY:
        return {"error": "unauthorized"}

    send_line_push("LINE通知テストです")
    return {"message": "test sent"}


@app.get("/run-buy-check")
def run_buy_check(key: str):
    if key != SECRET_KEY:
        return {"error": "unauthorized"}

    results = analyze_stocks()

    buys = [
        item.model_dump()
        for item in results
        if item.status == "買い候補"
    ]

    if buys:
        msg = "【買い候補】\n"
        for b in buys:
            msg += f"{b['name']} ({b['code']}) {b['price']}円\n"

        send_line_push(msg)

    return {"count": len(buys), "items": buys}
