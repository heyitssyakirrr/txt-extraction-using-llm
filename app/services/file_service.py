import re
from fastapi import HTTPException, UploadFile


NAME_KEYWORDS = [
    "name",
    "customer name",
    "account name",
    "account holder",
    "full name",
]

ACCOUNT_KEYWORDS = [
    "account number",
    "acc number",
    "acc no",
    "a/c no",
    "acct no",
    "account no",
]


async def read_txt_upload(upload_file: UploadFile) -> str:
    if not upload_file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename")

    if not upload_file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported")

    raw_bytes = await upload_file.read()

    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw_bytes.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail="Unable to decode uploaded text file",
            ) from exc


def preprocess_text(text: str, max_characters: int) -> str:
    cleaned = text.replace("\x00", " ")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    if len(cleaned) > max_characters:
        cleaned = cleaned[:max_characters]

    return cleaned


def extract_relevant_window(text: str, window_size: int = 8) -> str:
    """
    Keep nearby lines around keywords such as name/account.
    If nothing matches, return original text.
    """
    lines = [line.strip() for line in text.splitlines()]
    if not lines:
        return text

    matched_indexes: set[int] = set()
    all_keywords = NAME_KEYWORDS + ACCOUNT_KEYWORDS

    for idx, line in enumerate(lines):
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in all_keywords):
            start = max(0, idx - window_size)
            end = min(len(lines), idx + window_size + 1)
            matched_indexes.update(range(start, end))

    if not matched_indexes:
        return text

    selected_lines = [lines[i] for i in sorted(matched_indexes)]
    result = "\n".join(selected_lines).strip()

    return result if result else text


def regex_fallback_extract(text: str) -> dict[str, str | None]:
    """
    Very light fallback.
    Useful if later you want to compare regex result vs LLM result.
    """
    name_value = None
    account_value = None

    name_pattern = re.compile(
        r"(?i)\b(?:customer name|account name|account holder|full name|name)\b\s*[:\-]?\s*(.+)"
    )
    account_pattern = re.compile(
        r"(?i)\b(?:account number|acc number|acc no|a/c no|acct no|account no)\b\s*[:\-]?\s*([A-Za-z0-9\- ]+)"
    )

    for line in text.splitlines():
        stripped = line.strip()

        if name_value is None:
            name_match = name_pattern.search(stripped)
            if name_match:
                candidate = name_match.group(1).strip()
                if candidate:
                    name_value = candidate

        if account_value is None:
            account_match = account_pattern.search(stripped)
            if account_match:
                candidate = account_match.group(1).strip()
                if candidate:
                    account_value = candidate

        if name_value and account_value:
            break

    return {
        "name": name_value,
        "account_number": account_value,
    }