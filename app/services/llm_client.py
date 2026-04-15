from __future__ import annotations

import json
import logging
import re
import time
from tracemalloc import stop

import httpx
from fastapi import HTTPException

from app.core.config import get_settings

logger = logging.getLogger(__name__)

def _strip_trailing_commas(text: str) -> str:
    """
    Remove trailing commas before closing brackets/braces.
    Handles: [..., ] and {..., }
    """
    text = re.sub(r',\s*(\])', r'\1', text)
    text = re.sub(r',\s*(\})', r'\1', text)
    return text


def _extract_last_json_object(text: str) -> str | None:
    """
    Walk through the text character by character tracking brace depth.
    Every time depth returns to 0 we've found a complete top-level {...} block.
    We keep overwriting last_candidate so we always end up with the LAST one.
    """
    depth = 0
    start = None
    last_candidate = None

    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                last_candidate = text[start:i + 1]

    return last_candidate

def _extract_json_objects(text: str) -> list[str]:
    """
    Return all complete top-level JSON object blocks in order.
    """
    depth = 0
    start = None
    candidates: list[str] = []

    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start:i + 1])

    return candidates


def _merge_non_empty_dicts(dicts: list[dict]) -> dict:
    """
    Merge dicts from left to right, only overriding when the new value is non-empty.
    Helps when the LLM emits multiple JSON objects and some fields are null/missing
    in later duplicates.
    """
    merged: dict = {}
    for item in dicts:
        for key, value in item.items():
            if value is None:
                continue
            if isinstance(value, str) and value.strip() == "":
                continue
            merged[key] = value
    return merged


def _normalize_llm_output(response_json: dict) -> dict:
    """
    Parse the LLM response envelope and return the full parsed dict.
    Both extraction and summary features call this, each picks the keys it needs.

    Qwen2.5 often returns explanation text alongside the JSON, so we extract
    the JSON block explicitly rather than parsing the entire text value.
    Priority:
      1. Last ```json ... ``` code block  — most complete, LLM's final answer
      2. Last complete {...} block found by brace-depth tracking — handles nested JSON
    """
    logger.debug("Raw LLM response: %s", response_json)

    try:
        raw = response_json["text"].strip()

        # Strategy 1: grab the LAST ```json ... ``` block
        code_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if code_blocks:
            logger.debug("Parsing from code block (last of %d found)", len(code_blocks))
            return json.loads(_strip_trailing_commas(code_blocks[-1]))

        # Strategy 2: brace-depth tracking over all objects
        # Qwen sometimes returns two adjacent JSON objects; we merge non-empty fields
        # so we don't accidentally lose values like bank_name.
        json_blocks = _extract_json_objects(raw)
        if json_blocks:
            logger.debug("Parsing from brace-depth extraction (%d object(s))", len(json_blocks))
            parsed_dicts = []
            for block in json_blocks:
                try:
                    parsed = json.loads(_strip_trailing_commas(block))
                    if isinstance(parsed, dict):
                        parsed_dicts.append(parsed)
                except json.JSONDecodeError:
                    continue

            if parsed_dicts:
                return _merge_non_empty_dicts(parsed_dicts)
        
        # Strategy 3 (NEW): Qwen stop-token truncation repair
        # Happens when stop token fires before the final closing brace is written.
        # The text ends with a valid array but missing the outer '}'
        logger.debug("Attempting truncation repair")
        repaired = raw
        if not repaired.endswith("}"):
            repaired = repaired.rstrip() + "\n}"
        last_json = _extract_last_json_object(repaired)
        if last_json:
            logger.debug("Parsing from repaired truncated JSON")
            return json.loads(_strip_trailing_commas(last_json))

        raise ValueError("No JSON object found in LLM response text.")

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

    async def extract_fields(self, prompt: str, stop: list[str] | None = None) -> dict:
        payload = {
            "prompt": prompt,
            "model": self.settings.llm_model_name,
            "helper_id": self.settings.helper_id,
            #"max_tokens": self.settings.max_tokens, 
        }
        if stop:
            payload["stop"] = stop

        logger.debug("Prompt length: %d characters", len(prompt))
        logger.debug("Calling LLM microservice at %s", self.settings.llm_url)

        try:
            t0 = time.time()
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(
                    self.settings.llm_url,
                    headers=self._build_headers(),
                    json=payload,
                )
            response.raise_for_status()
            logger.debug("LLM response time: finished. Raw length: %d chars", len(response.text))
            logger.debug("LLM HTTP call took %.1fs", time.time() - t0)
            return _normalize_llm_output(response.json())

        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="LLM microservice timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=502, detail=f"LLM microservice error: HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail="Unable to connect to LLM microservice.") from exc