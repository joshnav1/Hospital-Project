from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # Gemini
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"

    # Generation defaults
    DEFAULT_MAX_TOKENS: int = 2048
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_TOP_P: float = 0.95

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
