"""
LLM microservice client.

HOW TO SWITCH FROM MOCK → REAL:
  1. Change the alias at the bottom of this file:
         LLMClient = RealLLMClient
  2. Set the correct URL/key in your .env file.
  3. Adjust _normalize_llm_output() if the response shape differs.

No other files need to change — the rest of the codebase only ever
calls `LLMClient().extract_fields(prompt)`.
"""

from __future__ import annotations

import json
import logging
import re

import httpx
from fastapi import HTTPException

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared response normaliser
# ---------------------------------------------------------------------------

def _normalize_llm_output(response_json: dict) -> dict[str, str | None]:
    """
    Accept several possible response shapes from the LLM microservice and
    always return {"name": ..., "account_number": ...}.

    Add new shape handlers here once you know the real API contract.
    """

    # Shape 1 — service returns the extracted fields directly.
    if "name" in response_json or "account_number" in response_json:
        return {
            "name": response_json.get("name"),
            "account_number": response_json.get("account_number"),
        }

    # Shape 2 — service returns {"content": "<json string>"}.
    if "content" in response_json and isinstance(response_json["content"], str):
        try:
            parsed = json.loads(response_json["content"])
            return {
                "name": parsed.get("name"),
                "account_number": parsed.get("account_number"),
            }
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=502,
                detail="LLM response 'content' field is not valid JSON.",
            ) from exc

    # Shape 3 — OpenAI-compatible chat-completion format.
    if "choices" in response_json and isinstance(response_json["choices"], list):
        try:
            content = response_json["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return {
                "name": parsed.get("name"),
                "account_number": parsed.get("account_number"),
            }
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=502,
                detail="Unsupported LLM response format inside 'choices'.",
            ) from exc

    raise HTTPException(
        status_code=502,
        detail=(
            "Unsupported LLM response format. "
            "Update _normalize_llm_output() in llm_client.py to handle it."
        ),
    )


# ---------------------------------------------------------------------------
# MOCK client — active while the real microservice URL is unknown
# ---------------------------------------------------------------------------

class MockLLMClient:
    """
    Simulates LLM extraction with regex so the rest of the app can be
    developed and tested without a running microservice.

    Replace with RealLLMClient once the endpoint details are confirmed.
    """

    async def extract_fields(self, prompt: str) -> dict[str, str | None]:
        logger.warning(
            "MockLLMClient is active — not calling any real LLM microservice."
        )

        # Pull the text block that build_extraction_prompt() wraps in triple-quotes.
        text_match = re.search(r'"""(.*?)"""', prompt, re.DOTALL)
        if not text_match:
            return {"name": None, "account_number": None}

        text = text_match.group(1)
        name: str | None = None
        account_number: str | None = None

        name_patterns = [
            r"Customer\s+Name\s*[:\-]\s*(.+)",
            r"Account\s+(?:Name|Holder)\s*[:\-]\s*(.+)",
            r"\bName\s*[:\-]\s*(.+)",
        ]
        account_patterns = [
            r"Account\s+Number\s*[:\-]\s*([\w\-]+)",
            r"Acc(?:ount)?\s+No\.?\s*[:\-]\s*([\w\-]+)",
            r"A/C\s+No\.?\s*[:\-]\s*([\w\-]+)",
        ]

        for pattern in name_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
                break

        for pattern in account_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                account_number = m.group(1).strip()
                break

        return {"name": name, "account_number": account_number}


# ---------------------------------------------------------------------------
# REAL client — uncomment alias at the bottom when ready
# ---------------------------------------------------------------------------

class RealLLMClient:
    """
    Calls your senior's LLM microservice over HTTP.

    Required .env keys:
        LLM_BASE_URL          e.g. http://10.0.0.5:8001
        LLM_EXTRACT_ENDPOINT  e.g. /extract  (default)

    Optional .env keys:
        LLM_API_KEY           Bearer token if the service requires auth
        LLM_MODEL_NAME        Model name forwarded to the service
        LLM_TIMEOUT_SECONDS   Request timeout in seconds (default 60)
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    # authorization header is only added if LLM API key is set
    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
        return headers

    # build the request body according to the microservice's expected API contract
    async def extract_fields(self, prompt: str) -> dict[str, str | None]:
        payload = {
            "prompt": prompt, # change if it expects a different field name (text/input)
            "model": self.settings.llm_model_name,
        }

        logger.debug("Calling LLM microservice at %s", self.settings.llm_url)

        try:
            # actual HTTP call to the microservice
            async with httpx.AsyncClient(
                timeout=self.settings.llm_timeout_seconds
            ) as client:
                response = await client.post(
                    self.settings.llm_url,
                    headers=self._build_headers(),
                    json=payload, # dict -> JSON
                )
            response.raise_for_status()
            return _normalize_llm_output(response.json())

        except httpx.TimeoutException as exc:
            logger.error("LLM microservice timed out")
            raise HTTPException(
                status_code=504, detail="LLM microservice timed out."
            ) from exc

        except httpx.HTTPStatusError as exc:
            logger.error("LLM microservice returned HTTP %s", exc.response.status_code)
            raise HTTPException(
                status_code=502,
                detail=f"LLM microservice error: HTTP {exc.response.status_code}",
            ) from exc

        except httpx.RequestError as exc:
            logger.error("Cannot reach LLM microservice: %s", exc)
            raise HTTPException(
                status_code=502,
                detail="Unable to connect to LLM microservice.",
            ) from exc

        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail="LLM microservice returned invalid JSON.",
            ) from exc


# ---------------------------------------------------------------------------
# Active client alias
# ---------------------------------------------------------------------------
# To switch to the real service, change the line below to:
#     LLMClient = RealLLMClient
#
LLMClient = MockLLMClient