from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = f"sqlite:///{ROOT_DIR / 'xhs_workflow.db'}"
    export_dir: Path = ROOT_DIR / "exports"

    llm_provider: str = "mock"
    openai_compatible_api_key: str | None = None
    openai_compatible_base_url: str = "https://api.openai.com/v1"
    openai_compatible_model: str = "gpt-4o-mini"

    image_api_key: str | None = None
    image_base_url: str = "https://api.openai.com/v1"
    image_model: str = "gpt-image-1"

    cathoven_cover_reference_dir: Path = ROOT_DIR / "references" / "covers"
    cathoven_product_reference_dir: Path = ROOT_DIR / "references" / "product"

    api_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
