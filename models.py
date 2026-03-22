from __future__ import annotations

from pydantic import BaseModel, Field

class StockInput(BaseModel):
    name: str = Field(..., description="銘柄名")
    code: str = Field(..., description="Yahoo Finance 用コード")

class StockAnalysis(BaseModel):
    name: str
    code: str
    price: float
    fair_price: float
    danger_price: float
    status: str
