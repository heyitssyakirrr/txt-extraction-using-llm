from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LLM Extraction Service"
    app_version: str = "1.0.0"
    debug: bool = True

    # ---------------------------------------------------------------------------
    # LLM microservice configuration
    # ---------------------------------------------------------------------------
    llm_base_url: str = "http://127.0.0.1:8001"
    llm_extract_endpoint: str = "/extract"
    llm_timeout_seconds: float = 60.0
    llm_api_key: str | None = None
    llm_model_name: str = "default"
    helper_id: str = "file_reader"

    # ---------------------------------------------------------------------------
    # Input safety
    # ---------------------------------------------------------------------------
    max_input_characters: int = 50_000

    # ---------------------------------------------------------------------------
    # File upload
    # ---------------------------------------------------------------------------
    allowed_upload_extensions: list[str] = [".txt"]
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("llm_base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("llm_timeout_seconds")
    @classmethod
    def _positive_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("llm_timeout_seconds must be positive")
        return v

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
    @property
    def llm_url(self) -> str:
        """Full URL used by LLMClient when calling the microservice."""
        return f"{self.llm_base_url}{self.llm_extract_endpoint}"


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.
    The cache is module-level, so the .env file is read only once per process.
    """
    return Settings()