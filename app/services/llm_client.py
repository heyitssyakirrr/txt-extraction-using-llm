from __future__ import annotations

import json
import logging

import httpx
from fastapi import HTTPException

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _normalize_llm_output(response_json: dict) -> dict:
    """
    Parse the LLM response envelope and return the full parsed dict.
    Both extraction and summary features call this — each picks the keys it needs.
    """
    logger.debug("Raw LLM response: %s", response_json)

    try:
        parsed = json.loads(response_json["text"].strip())
        return parsed
    except (KeyError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Failed to parse LLM response. Check the 'text' field in the response.",
        ) from exc


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
        return headers

    async def extract_fields(self, prompt: str) -> dict:
        payload = {
            "prompt": prompt,
            "model": self.settings.llm_model_name,
            "helper_id": self.settings.helper_id,
        }
        logger.debug("Calling LLM microservice at %s", self.settings.llm_url)

        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(
                    self.settings.llm_url,
                    headers=self._build_headers(),
                    json=payload,
                )
            response.raise_for_status()
            return _normalize_llm_output(response.json())

        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="LLM microservice timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=502, detail=f"LLM microservice error: HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail="Unable to connect to LLM microservice.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="LLM microservice returned invalid JSON.") from exc