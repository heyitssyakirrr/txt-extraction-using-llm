"""
File-level helpers: upload validation, text pre-processing, windowing, regex fallback.
"""

from __future__ import annotations

import re

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Keyword lists for the relevant-window extractor
# ---------------------------------------------------------------------------

NAME_KEYWORDS: list[str] = [
    "name",
    "customer name",
    "account name",
    "account holder",
    "full name",
]

ACCOUNT_KEYWORDS: list[str] = [
    "account number",
    "acc number",
    "acc no",
    "a/c no",
    "acct no",
    "account no",
]


# ---------------------------------------------------------------------------
# Upload reading
# ---------------------------------------------------------------------------

async def read_txt_upload(upload_file: UploadFile) -> str:
    """
    Read and decode a .txt upload.

    Raises HTTPException (400) for:
      - Missing filename
      - Unsupported extension
      - File exceeding max_upload_bytes
      - Empty file
      - Undecodable bytes
    """
    settings = get_settings()

    # no filename
    if not upload_file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename.")

    # .txt only 
    ext = "." + upload_file.filename.rsplit(".", 1)[-1].lower() if "." in upload_file.filename else ""
    if ext not in settings.allowed_upload_extensions:
        allowed = ", ".join(settings.allowed_upload_extensions)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {allowed}",
        )

    # read bytes and check size before decoding
    raw_bytes = await upload_file.read()

    if len(raw_bytes) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {limit_mb:.0f} MB upload limit.",
        )

    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Try UTF-8 first, fall back to latin-1 (covers most western encodings).
    for encoding in ("utf-8", "latin-1"):
        try:
            # bytes -> string
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise HTTPException(
        status_code=400,
        detail="Unable to decode the uploaded text file (tried utf-8 and latin-1).",
    )


# ---------------------------------------------------------------------------
# Text pre-processing
# ---------------------------------------------------------------------------

def preprocess_text(text: str, max_characters: int) -> str:
    """
    Normalise whitespace and enforce a character limit.

    Steps (in order):
      1. Strip null bytes (common in PDF-extracted text).
      2. Normalise line endings to \\n.
      3. Collapse runs of spaces/tabs to a single space.
      4. Collapse runs of 3+ blank lines to 2.
      5. Strip leading/trailing whitespace.
      6. Hard-truncate to max_characters.
    """
    cleaned = text.replace("\x00", " ")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    # cut the input down to size if it's too long
    if len(cleaned) > max_characters:
        cleaned = cleaned[:max_characters]

    return cleaned


# ---------------------------------------------------------------------------
# Relevant-window extraction
# ---------------------------------------------------------------------------

def extract_relevant_window(text: str, window_size: int = 8) -> str:
    """
    Return only the lines that surround name / account keywords.

    This reduces noise for the LLM and cuts token usage on very long documents.
    If no keywords match, the full text is returned unchanged.

    Args:
        text:        Pre-processed input text.
        window_size: Number of lines to include above and below each matched line.
    """
    lines = [line.strip() for line in text.splitlines()]
    if not lines:
        return text

    all_keywords = NAME_KEYWORDS + ACCOUNT_KEYWORDS
    matched_indexes: set[int] = set()

    for idx, line in enumerate(lines):
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in all_keywords):
            start = max(0, idx - window_size)
            end = min(len(lines), idx + window_size + 1)
            matched_indexes.update(range(start, end))

    if not matched_indexes:
        return text

    selected = [lines[i] for i in sorted(matched_indexes)]
    result = "\n".join(selected).strip()
    return result if result else text


# ---------------------------------------------------------------------------
# Regex fallback extractor
# ---------------------------------------------------------------------------

def regex_fallback_extract(text: str) -> dict[str, str | None]:
    """
    Light regex pass over the text.

    Used to fill any field that the LLM returned as null.
    Keeping this separate from the LLM call makes it easy to compare
    and measure accuracy of each approach independently.
    """
    name_value: str | None = None
    account_value: str | None = None

    name_pattern = re.compile(
        r"(?i)\b(?:customer\s+name|account\s+(?:name|holder)|full\s+name|name)\b"
        r"\s*[:\-]?\s*(.+)"
    )
    account_pattern = re.compile(
        r"(?i)\b(?:account\s+number|acc(?:ount)?\s+no\.?|a/c\s+no\.?|acct\s+no\.?)\b"
        r"\s*[:\-]?\s*([\w\-]+)"
    )

    for line in text.splitlines():
        stripped = line.strip()

        if name_value is None:
            m = name_pattern.search(stripped)
            if m:
                candidate = m.group(1).strip()
                if candidate:
                    name_value = candidate

        if account_value is None:
            m = account_pattern.search(stripped)
            if m:
                candidate = m.group(1).strip()
                if candidate:
                    account_value = candidate

        if name_value and account_value:
            break

    return {"name": name_value, "account_number": account_value}