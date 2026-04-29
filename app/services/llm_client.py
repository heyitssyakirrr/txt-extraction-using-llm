from __future__ import annotations

"""
llm_client.py
-------------
HTTP client for the internal LLM microservice.

JSON parsing and recovery logic has been moved to app/services/json_parser.py.
This module is responsible only for building the request, sending it, and
returning the parsed field dict.
"""

import logging
import time

import httpx
from fastapi import HTTPException

from app.core.config import get_settings
from app.services.json_parser import normalize_llm_output

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
        return headers

    async def extract_fields(
        self,
        prompt: str,
        stop: list[str] | None = None,
        timeout: float | None = None,
    ) -> dict:
        payload = {
            "prompt": prompt,
            "model": self.settings.llm_model_name,
            "helper_id": self.settings.helper_id,
        }
        if stop:
            payload["stop"] = stop

        logger.debug("Prompt length: %d characters", len(prompt))
        logger.debug("Calling LLM microservice at %s", self.settings.llm_url)

        try:
            t0 = time.time()
            effective_timeout = timeout if timeout is not None else self.settings.llm_timeout_seconds
            async with httpx.AsyncClient(timeout=effective_timeout) as client:
                response = await client.post(
                    self.settings.llm_url,
                    headers=self._build_headers(),
                    json=payload,
                )
            response.raise_for_status()
            elapsed = time.time() - t0
            logger.debug(
                "LLM HTTP call took %.1fs, raw response length: %d chars",
                elapsed, len(response.text),
            )

            result = normalize_llm_output(response.json())
            logger.debug("Final extracted dict keys: %s", list(result.keys()))
            return result

        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=504,
                detail="LLM microservice timed out.",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"LLM microservice error: HTTP {exc.response.status_code}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail="Unable to connect to LLM microservice.",
            ) from exc