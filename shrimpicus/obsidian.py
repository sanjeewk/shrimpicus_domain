from __future__ import annotations

from datetime import datetime
from pathlib import Path


class ObsidianJournal:
    def __init__(self, journal_file: Path | None):
        self.journal_file = journal_file

    def append(self, content: str) -> str | None:
        if not self.journal_file:
            return None
        self.journal_file.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.journal_file.open("a", encoding="utf-8") as f:
            f.write(f"\n- [{now}] {content.strip()}\n")
        return str(self.journal_file)
