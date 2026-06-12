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

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        """Low-level /api/chat call returning the raw ``message`` dict.

        The returned message may contain ``content`` (a plain reply) and/or
        ``tool_calls`` (the model asking to run a tool). Used by the agentic
        loop in AssistantService.
        """
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data.get("message", {}) or {}
