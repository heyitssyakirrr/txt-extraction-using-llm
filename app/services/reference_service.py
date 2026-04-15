from __future__ import annotations

"""
reference_service.py
--------------------
Loads the reference CSV (filename → expected bank details) once at startup,
then provides a compare() function used by the extraction router.

CSV expected columns (case-insensitive, extra columns are ignored):
    filename, bank, fi code, masteracc, subacc

The `filename` column stores values like "BBB-001227-24" (no extension).
Uploaded filenames like "JSB-000486-25_extracted.txt" are normalised to
"JSB-000486-25" before lookup.
"""

import csv
import logging
import re
from functools import lru_cache
from pathlib import Path

from app.models.schemas import ComparisonResult, FieldComparisonDetail

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path to the reference CSV.
# Place the file at  data/reference.csv  relative to the project root,
# or override by changing this constant.
# ---------------------------------------------------------------------------
REFERENCE_CSV_PATH = Path("data/reference.csv")


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def _normalise_key(raw: str) -> str:
    """
    Strip file extensions and known suffixes so that
    'JSB-000486-25_extracted.txt' → 'JSB-000486-25'
    'BBB-001227-24.txt'           → 'BBB-001227-24'
    'BBB-001227-24'               → 'BBB-001227-24'
    """
    # Drop any file extension first (.txt, .pdf, .md …)
    name = Path(raw).stem  # removes last suffix, e.g. .txt
    # Drop trailing _extracted (case-insensitive) and any other _<word> suffixes
    name = re.sub(r'_extracted$', '', name, flags=re.IGNORECASE).strip()
    return name


def _normalise_header(h: str) -> str:
    """Lower-case, strip spaces — makes column matching robust."""
    return h.strip().lower().replace(" ", "")


def _load_csv(path: Path) -> dict[str, dict]:
    """
    Returns a dict keyed by normalised filename string.
    Each value is a flat dict with keys: filename, bank, fi_code, masteracc, subacc
    """
    if not path.exists():
        logger.warning("Reference CSV not found at %s — comparisons will be skipped", path)
        return {}

    records: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            logger.warning("Reference CSV appears empty")
            return {}

        # Build a normalised-header → original-header map
        header_map = {_normalise_header(h): h for h in reader.fieldnames}

        # Resolve the columns we care about (tolerant of spacing/casing)
        col = {
            "filename":  header_map.get("filename"),
            "bank":      header_map.get("bank"),
            "fi_code":   header_map.get("ficode") or header_map.get("fi_code") or header_map.get("finum"),
            "masteracc": header_map.get("masteracc") or header_map.get("master_account_number"),
            "subacc":    header_map.get("subacc") or header_map.get("sub_account_number"),
        }

        missing = [k for k, v in col.items() if v is None]
        if missing:
            logger.warning("Reference CSV is missing expected columns: %s", missing)

        for row in reader:
            raw_filename = row.get(col["filename"] or "", "").strip()
            if not raw_filename:
                continue
            key = _normalise_key(raw_filename)
            records[key] = {
                "filename":  raw_filename,
                "bank":      row.get(col["bank"] or "", "").strip() if col["bank"] else None,
                "fi_code":   row.get(col["fi_code"] or "", "").strip() if col["fi_code"] else None,
                "masteracc": row.get(col["masteracc"] or "", "").strip() if col["masteracc"] else None,
                "subacc":    row.get(col["subacc"] or "", "").strip() if col["subacc"] else None,
            }

    logger.info("Loaded %d rows from reference CSV at %s", len(records), path)
    return records


@lru_cache(maxsize=1)
def get_reference_data() -> dict[str, dict]:
    """Cached loader — reads the CSV once per process lifetime."""
    return _load_csv(REFERENCE_CSV_PATH)


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def _normalise_value(v: str | None) -> str:
    """Strip, lower-case, and remove common separators for loose matching."""
    if v is None:
        return ""
    return re.sub(r'[\s\-_/]', '', v).lower()


def _field_match(extracted: str | None, expected: str | None) -> FieldComparisonDetail:
    """
    Compare two values with normalisation (ignore case, spaces, dashes).
    Both being None counts as a match (field not present in either source).
    """
    match = _normalise_value(extracted) == _normalise_value(expected)
    return FieldComparisonDetail(
        extracted=extracted,
        expected=expected,
        match=match,
    )


def compare_extraction(
    filename_raw: str,
    bank_name: str | None,
    fi_num: str | None,
    master_account_number: str | None,
    sub_account_number: str | None,
) -> ComparisonResult:
    """
    Look up the uploaded file's filename in the reference CSV and compare
    the four verifiable fields.

    Args:
        filename_raw: The original uploaded filename, e.g. "JSB-000486-25_extracted.txt"
        bank_name:    Bank name extracted by the LLM from the document body.
        fi_num:       FI number extracted by the LLM.
        master_account_number: Master acc extracted by the LLM.
        sub_account_number:    Sub acc extracted by the LLM.

    Returns:
        ComparisonResult with per-field verdicts and an overall all_match flag.
    """
    key = _normalise_key(filename_raw)
    reference = get_reference_data()
    row = reference.get(key)

    if row is None:
        logger.warning("Filename key '%s' not found in reference CSV", key)
        return ComparisonResult(
            filename_key=key,
            csv_row_found=False,
            bank_name=FieldComparisonDetail(extracted=bank_name, expected=None, match=False),
            fi_num=FieldComparisonDetail(extracted=fi_num, expected=None, match=False),
            master_account_number=FieldComparisonDetail(extracted=master_account_number, expected=None, match=False),
            sub_account_number=FieldComparisonDetail(extracted=sub_account_number, expected=None, match=False),
            all_match=False,
        )

    bank_cmp    = _field_match(bank_name,             row.get("bank"))
    fi_cmp      = _field_match(fi_num,                row.get("fi_code"))
    master_cmp  = _field_match(master_account_number, row.get("masteracc"))
    sub_cmp     = _field_match(sub_account_number,    row.get("subacc"))

    all_match = all([
        bank_cmp.match,
        fi_cmp.match,
        master_cmp.match,
        sub_cmp.match,
    ])

    return ComparisonResult(
        filename_key=key,
        csv_row_found=True,
        bank_name=bank_cmp,
        fi_num=fi_cmp,
        master_account_number=master_cmp,
        sub_account_number=sub_cmp,
        all_match=all_match,
    )