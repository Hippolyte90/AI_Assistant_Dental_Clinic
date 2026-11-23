"""Application settings, read from the environment and the repo-root .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
PRICE_LIST_PATH = DATA_DIR / "price_list" / "Dental_Price_List_EUR.xlsx"
CATALOG_PATH = DATA_DIR / "catalog.json"
RULES_DIR = APP_DIR / "rules"
PROMPTS_DIR = APP_DIR / "prompts"


class Settings(BaseSettings):
    """Runtime configuration. No API keys: every model runs locally."""

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    ollama_host: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen3:4b"
    llm_think: bool = False
    llm_num_ctx: int = 8192
    llm_temperature: float = 0
    llm_timeout_s: int = 300
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    storage_dir: Path = Path("storage")
    clinic_name: str = "Dental Clinic"
    clinic_address: str = ""
    dentist_name: str = ""
    auth_required: bool = True
    max_accounts: int = 100

    @property
    def storage_path(self) -> Path:
        """Absolute storage directory."""
        path = self.storage_dir
        return path if path.is_absolute() else ROOT_DIR / path


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings."""
    return Settings()
