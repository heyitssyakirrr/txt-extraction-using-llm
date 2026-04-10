from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LLM Extraction Service"
    app_version: str = "1.0.0"
    debug: bool = False

    # ---------------------------------------------------------------------------
    # LLM microservice configuration
    # ---------------------------------------------------------------------------
    llm_base_url: str = ""
    llm_extract_endpoint: str = ""
    llm_timeout_seconds: float = 600.0
    llm_api_key: str | None = None
    llm_model_name: str = ""
    helper_id: str = ""
    max_tokens: int = 2048

    # ---------------------------------------------------------------------------
    # Docling OCR microservice configuration
    # ---------------------------------------------------------------------------
    docling_base_url: str = ""
    docling_ocr_endpoint: str = ""
    docling_timeout_seconds: float = 300.0

    # ---------------------------------------------------------------------------
    # Input safety
    # ---------------------------------------------------------------------------
    max_input_characters: int = 50_000

    # ---------------------------------------------------------------------------
    # File upload
    # ---------------------------------------------------------------------------
    allowed_upload_extensions: list[str] = [".txt", ".pdf"]
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("llm_base_url", "docling_base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("llm_timeout_seconds")
    @classmethod
    def _positive_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("llm_timeout_seconds must be positive")
        return v

    @field_validator("docling_timeout_seconds")
    @classmethod
    def _positive_docling_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("docling_timeout_seconds must be positive")
        return v

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------
    @property
    def llm_url(self) -> str:
        return f"{self.llm_base_url}{self.llm_extract_endpoint}"

    @property
    def docling_ocr_url(self) -> str:
        return f"{self.docling_base_url}{self.docling_ocr_endpoint}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
