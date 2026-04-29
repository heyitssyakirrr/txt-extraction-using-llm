from __future__ import annotations

"""
json_parser.py
--------------
JSON extraction and recovery helpers for LLM responses.

LLM outputs are often imperfect — they may wrap JSON in markdown code fences,
emit multiple JSON objects, truncate mid-object, or vary key casing.
The functions here handle all of those cases robustly.

Public entry point: normalize_llm_output(response_json) -> dict
"""

import json
import logging
import re

from fastapi import HTTPException

logger = logging.getLogger(__name__)

_EXPECTED_KEYS = {
    "name",
    "master_account_number",
    "sub_account_number",
    "address",
    "fi_num",
    "bank_name",
}


# ---------------------------------------------------------------------------
# Low-level string helpers
# ---------------------------------------------------------------------------

def strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before closing brackets/braces."""
    text = re.sub(r',\s*(\])', r'\1', text)
    text = re.sub(r',\s*(\})', r'\1', text)
    return text


def extract_last_json_object(text: str) -> str | None:
    """
    Walk through the text tracking brace depth, ignoring braces inside strings.
    Returns the last complete top-level {...} block found.
    """
    depth = 0
    start = None
    last_candidate = None
    in_string = False
    escape_next = False

    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                last_candidate = text[start:i + 1]

    return last_candidate


def extract_json_objects(text: str) -> list[str]:
    """
    Return all complete top-level JSON object blocks in order.
    Correctly ignores braces that appear inside string values.
    """
    depth = 0
    start = None
    candidates: list[str] = []
    in_string = False
    escape_next = False

    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start:i + 1])

    return candidates


# ---------------------------------------------------------------------------
# Dict helpers
# ---------------------------------------------------------------------------

def merge_non_empty_dicts(dicts: list[dict]) -> dict:
    """
    Merge dicts left to right, only overriding when the new value is non-empty.
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


def normalise_keys(d: dict) -> dict:
    """
    Normalise all keys to lowercase with underscores so that keys like
    'Bank_Name', 'BANK_NAME', or 'bankname' all resolve to 'bank_name'.
    """
    normalised: dict = {}
    for key, value in d.items():
        clean_key = re.sub(r'[\s\-]+', '_', key.strip()).lower()
        normalised[clean_key] = value
    return normalised


def filter_expected_keys(d: dict) -> dict:
    """Remove any keys the LLM hallucinated that aren't part of the schema."""
    return {k: v for k, v in d.items() if k in _EXPECTED_KEYS}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def normalize_llm_output(response_json: dict) -> dict:
    """
    Parse the LLM HTTP response dict into a clean field dict.

    Tries three strategies in order:
      1. Extract from a markdown ```json ... ``` code block
      2. Extract all brace-delimited JSON objects and merge them
      3. Repair a truncated response by appending a closing brace
    """
    try:
        raw = response_json["text"].strip()

        # Strategy 1 — markdown code block
        code_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if code_blocks:
            logger.debug("Parsing from code block (last of %d found)", len(code_blocks))
            parsed = json.loads(strip_trailing_commas(code_blocks[-1]))
            result = filter_expected_keys(normalise_keys(parsed))
            logger.debug("Parsed keys: %s", list(result.keys()))
            return result

        # Strategy 2 — brace-depth extraction
        json_blocks = extract_json_objects(raw)
        if json_blocks:
            logger.debug("Parsing from brace-depth extraction (%d object(s))", len(json_blocks))
            parsed_dicts: list[dict] = []
            for block in json_blocks:
                try:
                    parsed = json.loads(strip_trailing_commas(block))
                    if isinstance(parsed, dict):
                        parsed_dicts.append(filter_expected_keys(normalise_keys(parsed)))
                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse JSON block: %s | block: %.200s", e, block)
                    continue

            if parsed_dicts:
                merged = merge_non_empty_dicts(parsed_dicts)
                logger.debug("Merged keys from %d object(s): %s", len(parsed_dicts), list(merged.keys()))
                return merged

        # Strategy 3 — truncation repair
        logger.debug("Attempting truncation repair")
        repaired = raw
        if not repaired.endswith("}"):
            repaired = repaired.rstrip() + "\n}"
        last_json = extract_last_json_object(repaired)
        if last_json:
            logger.debug("Parsing from repaired truncated JSON")
            parsed = json.loads(strip_trailing_commas(last_json))
            result = filter_expected_keys(normalise_keys(parsed))
            logger.debug("Repaired parsed keys: %s", list(result.keys()))
            return result

        raise ValueError("No JSON object found in LLM response text.")

    except (KeyError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Failed to parse LLM response. Check the 'text' field in the response.",
        ) from exc