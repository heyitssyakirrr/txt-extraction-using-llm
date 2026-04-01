"""
Prompt construction for the LLM extraction call.

Keeping prompts here (rather than inline in routes) means:
  - Easy to iterate on prompt wording without touching business logic.
  - Simple to add prompt versioning or A/B testing later.
"""

from __future__ import annotations

import json


# ---------------------------------------------------------------------------
# Schema sent to the LLM — extend this when ExtractionResult grows
# ---------------------------------------------------------------------------

_EXPECTED_SCHEMA: dict[str, str] = {
    "name": "string or null",
    "account_number": "string or null",
    # Add new fields here when requirements change.
    # Example:
    #   "branch": "string or null",
    #   "document_date": "string or null",
}


def build_extraction_prompt(text: str) -> str:
    """
    Build the extraction prompt that is sent to the LLM microservice.

    The triple-quoted block is intentional — MockLLMClient uses it as a
    boundary to locate the text section inside the prompt.
    """
    instructions = f"""\
You are an information extraction assistant.

Your task:
Extract the following fields from the provided text:
{chr(10).join(f"- {k}" for k in _EXPECTED_SCHEMA)}

Rules:
- Return JSON only. No explanation, no markdown, no code fences.
- If a field cannot be found, return null for that field.
- Prefer the primary customer / account-holder name if multiple names appear.
- Copy the account number exactly as it appears in the text.
- Only return these keys: {", ".join(_EXPECTED_SCHEMA.keys())}

Expected JSON schema:
{json.dumps(_EXPECTED_SCHEMA, indent=2)}

Text to analyse:
\"\"\"
{text}
\"\"\"
"""
    return instructions.strip()