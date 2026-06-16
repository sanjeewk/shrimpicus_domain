from __future__ import annotations

import httpx
import json

from shrimpicus.config import Settings

# Try to import OpenAI SDK (used for OpenRouter), but don't fail if not installed
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class OllamaClient:
    """LLM client supporting both local Ollama and hosted OpenRouter."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = settings.llm_provider.lower()

        if self.provider == "openrouter":
            if not HAS_OPENAI:
                raise RuntimeError(
                    "OpenRouter provider selected but openai package not installed. "
                    "Install with: pip install openai"
                )
            if not settings.openrouter_api_key:
                raise RuntimeError(
                    "OpenRouter provider selected but OPENROUTER_API_KEY not set in .env"
                )
            # OpenRouter uses OpenAI SDK with custom base URL
            self.openrouter_client = OpenAI(
                api_key=settings.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1"
            )
            self.openrouter_model = settings.openrouter_model
        else:
            # Local Ollama
            self.base_url = settings.ollama_base_url.rstrip("/")
            self.model = settings.ollama_model

    async def answer(self, user_text: str) -> str:
        """Simple question answering (used for !ask command)."""
        system_prompt = (
            "You are Shrimpicus, a concise personal assistant. "
            "Give short, practical replies. "
            "If the user is asking about reminders/todos/birthdays/journal and the bot has "
            "slash commands, mention the command format."
        )

        if self.provider == "openrouter":
            return await self._openrouter_answer(user_text, system_prompt)
        else:
            return await self._ollama_answer(user_text, system_prompt)

    async def _ollama_answer(self, user_text: str, system_prompt: str) -> str:
        """Ollama implementation of answer()."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data.get("message", {}).get("content", "").strip() or "I could not generate a response."

    async def _openrouter_answer(self, user_text: str, system_prompt: str) -> str:
        """OpenRouter implementation of answer()."""
        try:
            response = self.openrouter_client.chat.completions.create(
                model=self.openrouter_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.7,
                max_tokens=512,
            )
            return response.choices[0].message.content.strip() or "I could not generate a response."
        except Exception as e:
            return f"OpenRouter API error: {e}"

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        """Low-level chat call returning the raw message dict.

        The returned message may contain ``content`` (a plain reply) and/or
        ``tool_calls`` (the model asking to run a tool). Used by the agentic
        loop in AssistantService.
        """
        if self.provider == "openrouter":
            return await self._openrouter_chat(messages, tools)
        else:
            return await self._ollama_chat(messages, tools)

    async def _ollama_chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        """Ollama implementation of chat()."""
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

    async def _openrouter_chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        """OpenRouter implementation of chat() with tool calling support."""
        try:
            # Convert shrimpicus tool format to OpenAI/OpenRouter format
            openrouter_tools = None
            if tools:
                openrouter_tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": tool["function"]["name"],
                            "description": tool["function"].get("description", ""),
                            "parameters": tool["function"].get("parameters", {}),
                        }
                    }
                    for tool in tools
                ]

            response = self.openrouter_client.chat.completions.create(
                model=self.openrouter_model,
                messages=messages,
                tools=openrouter_tools,
                temperature=0.7,
                max_tokens=1024,
            )

            message = response.choices[0].message

            # Convert OpenRouter response back to shrimpicus format (Ollama-like)
            result = {}

            if message.content:
                result["content"] = message.content

            if message.tool_calls:
                # Convert OpenAI-style tool_calls to Ollama format
                result["tool_calls"] = []
                for tc in message.tool_calls:
                    result["tool_calls"].append({
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    })

            return result

        except Exception as e:
            # Return error in content if OpenRouter fails
            return {"content": f"OpenRouter API error: {e}"}
