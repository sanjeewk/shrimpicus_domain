from __future__ import annotations

import httpx

from shrimpicus.config import Settings

# Try to import Groq, but don't fail if not installed
try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False


class OllamaClient:
    """LLM client supporting both local Ollama and hosted Groq."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = settings.llm_provider.lower()

        if self.provider == "groq":
            if not HAS_GROQ:
                raise RuntimeError(
                    "Groq provider selected but groq package not installed. "
                    "Install with: pip install groq"
                )
            if not settings.groq_api_key:
                raise RuntimeError(
                    "Groq provider selected but GROQ_API_KEY not set in .env"
                )
            self.groq_client = Groq(api_key=settings.groq_api_key)
            self.groq_model = settings.groq_model
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

        if self.provider == "groq":
            return await self._groq_answer(user_text, system_prompt)
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

    async def _groq_answer(self, user_text: str, system_prompt: str) -> str:
        """Groq implementation of answer()."""
        try:
            response = self.groq_client.chat.completions.create(
                model=self.groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.7,
                max_tokens=512,
            )
            return response.choices[0].message.content.strip() or "I could not generate a response."
        except Exception as e:
            return f"Groq API error: {e}"

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
        if self.provider == "groq":
            return await self._groq_chat(messages, tools)
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

    async def _groq_chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        """Groq implementation of chat() with tool calling support."""
        try:
            # Convert shrimpicus tool format to Groq format
            groq_tools = None
            if tools:
                groq_tools = [
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

            response = self.groq_client.chat.completions.create(
                model=self.groq_model,
                messages=messages,
                tools=groq_tools,
                temperature=0.7,
                max_tokens=1024,
            )

            message = response.choices[0].message

            # Convert Groq response back to shrimpicus format (Ollama-like)
            result = {}

            if message.content:
                result["content"] = message.content

            if message.tool_calls:
                # Convert Groq tool_calls to Ollama format
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
            # Return error in content if Groq fails
            return {"content": f"Groq API error: {e}"}
