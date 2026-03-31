from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "LLM Extraction Service"
    app_version: str = "1.0.0"
    debug: bool = True

    # LLM microservice configuration
    llm_base_url: str = "http://127.0.0.1:8001" # change the url later
    llm_extract_endpoint: str = "/extract"
    llm_timeout_seconds: float = 60.0

    # Optional auth if the LLM microservice requires it
    llm_api_key: str | None = None

    # If the LLm microservice expects a model name
    llm_model_name: str = "default model"

    # Input text safety
    max_input_characters: int = 50000

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    @property
    def llm_url(self) -> str:
        return f"{self.llm_base_url.rstrip('/')}{self.llm_extract_endpoint}"
    
@lru_cache
def get_settings() -> Settings:
    return Settings()