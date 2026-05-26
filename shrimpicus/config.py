from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    discord_bot_token: str
    discord_command_prefix: str = "!"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b-instruct-q4_K_M"

    tz: str = "UTC"
    db_path: str = "./data/shrimpicus.db"
    check_interval_seconds: int = 30
    default_snooze_minutes: int = 30

    notion_token: str = ""
    notion_database_id: str = ""
    notion_title_property: str = "Name"

    obsidian_vault_path: str = ""
    obsidian_journal_relative: str = "Journal/inbox.md"

    model_config = SettingsConfigDict(env_file=str(DEFAULT_ENV_FILE), env_file_encoding="utf-8")

    @property
    def db_file(self) -> Path:
        return Path(self.db_path).expanduser().resolve()

    @property
    def obsidian_journal_file(self) -> Path | None:
        if not self.obsidian_vault_path:
            return None
        root = Path(self.obsidian_vault_path).expanduser().resolve()
        return root / self.obsidian_journal_relative
