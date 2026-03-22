from __future__ import annotations

from openai import OpenAI

from .config import settings

def score_company_text(text: str) -> str:
    if not settings.openai_api_key:
        return "OPENAI_API_KEY 未設定のため AI 評価はスキップしました。"

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = f"""以下の企業説明を見て、成長性を100点満点で簡潔に評価してください。\n\n{text}"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content or ""
