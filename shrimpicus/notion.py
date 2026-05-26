from __future__ import annotations

import httpx

from shrimpicus.config import Settings


class NotionService:
    def __init__(self, settings: Settings):
        self.enabled = bool(settings.notion_token and settings.notion_database_id)
        self._token = settings.notion_token
        self._database_id = settings.notion_database_id
        self._title_prop = settings.notion_title_property
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    async def create_todo_page(self, task: str) -> str | None:
        if not self.enabled:
            return None

        body = {
            "parent": {"database_id": self._database_id},
            "properties": {
                self._title_prop: {
                    "title": [
                        {
                            "type": "text",
                            "text": {"content": task},
                        }
                    ]
                }
            },
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post("https://api.notion.com/v1/pages", headers=self._headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            return data.get("id")
