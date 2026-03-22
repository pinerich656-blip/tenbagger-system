from __future__ import annotations

import requests

from .config import settings

def send_line_notify(message: str) -> bool:
    if not settings.line_notify_token:
        return False

    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {settings.line_notify_token}"}
    data = {"message": message}
    response = requests.post(url, headers=headers, data=data, timeout=15)
    return response.ok
