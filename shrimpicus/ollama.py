from __future__ import annotations

import httpx

from shrimpicus.config import Settings


class OllamaClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model

    async def answer(self, user_text: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Shrimpicus, a concise personal assistant. "
                        "Give short, practical replies. "
                        "If the user is asking about reminders/todos/birthdays/journal and the bot has "
                        "slash commands, mention the command format."
                    ),
                },
                {"role": "user", "content": user_text},
            ],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data.get("message", {}).get("content", "").strip() or "I could not generate a response."
