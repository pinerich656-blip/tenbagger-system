# Tenbagger System

小型成長株の簡易スクリーニングを行うための、GitHub公開向けの最小構成リポジトリです。

## できること
- FastAPI で分析APIを公開
- yfinance で株価を取得
- 買いライン / 危険ラインを計算
- スケジューラで定期実行
- 任意で OpenAI API / LINE Notify を利用

## ディレクトリ構成
```text
tenbagger_github_ready/
├── app/
│   ├── __init__.py
│   ├── ai.py
│   ├── config.py
│   ├── main.py
│   ├── models.py
│   ├── notifications.py
│   ├── scheduler.py
│   ├── strategy.py
│   └── storage.py
├── data/
│   └── .gitkeep
├── tests/
│   └── test_strategy.py
├── .env.example
├── .gitignore
├── LICENSE
├── Dockerfile
├── README.md
├── requirements.txt
└── run.py
```

## セットアップ
```bash
python -m venv .venv
source .venv/bin/activate   # Windows は .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

## 起動
```bash
uvicorn app.main:app --reload
```

ブラウザで以下を開く:
- API: http://127.0.0.1:8000/analyze
- Docs: http://127.0.0.1:8000/docs

## 定期実行
```bash
python run.py
```

## GitHub に上げる手順
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-name>/<repo-name>.git
git push -u origin main
```

## 注意
- `LINE Notify` は新規利用に制約があるため、必要に応じて別の通知手段へ置き換えてください。
- `yfinance` は非公式データソースです。実運用前に必ず検証してください。
- これは投資助言ではなく、研究・検証用の雛形です。
