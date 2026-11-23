from datetime import date
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# The backend folder (one level above config/): the code and data/ are in it, and the Python commands run from it
BACKEND_DIR = Path(__file__).resolve().parent.parent

# The project folder (one level above backend/): .env is there, next to .env.example, so it is found from any folder
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """All settings and secrets in one place, read once from .env."""

    # How .env is read: unknown lines are ignored, and error messages never show values
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # OpenAI: the key is required (no default), so the app fails fast without it
    OPENAI_API_KEY: SecretStr = Field(min_length=1)
    OPENAI_MODEL: str = "gpt-6-luna"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    # How much the chat model reasons before it answers. "none" is the fastest and the cheapest
    OPENAI_REASONING_EFFORT: Literal["none", "low", "medium", "high", "xhigh", "max"] = "none"

    # LangSmith tracing (optional): without a key, the app runs normally with no tracing
    LANGSMITH_API_KEY: Optional[SecretStr] = None
    # The name the runs are filed under in LangSmith
    LANGSMITH_PROJECT: str = "who-to-ask"
    # Only for a LangSmith account outside the US region, for example https://eu.api.smith.langchain.com
    LANGSMITH_ENDPOINT: Optional[str] = None

    # MongoDB: the main database of the fake company data. The default is a MongoDB installed on this computer.
    # The address is kept like a secret, because it can hold a password
    MONGODB_URI: SecretStr = SecretStr("mongodb://localhost:27017")
    MONGODB_DATABASE: str = "who_to_ask"

    # Postgres: the memory of the conversations (optional). The address holds a password, so it is kept like a secret.
    # It names its database: postgresql://user:password@localhost:5432/who_to_ask
    # Without it, the app runs normally, and a conversation is forgotten when the program stops
    POSTGRES_URI: Optional[SecretStr] = None

    # Data: the folder with the fake company files. Since M4 they are the seed source of MongoDB
    DATA_DIR: Path = Path("data")

    # A fixed fake "today", so date logic and tests give the same result every day
    TODAY: date = date(2026, 11, 1)


# The one shared settings object: every other file imports this
settings = Settings()
