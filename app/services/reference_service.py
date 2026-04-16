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

REFERENCE_CSV_PATH = Path("data/reference.csv")

# ---------------------------------------------------------------------------
# Canonical bank name map
# Keys   : normalised variants the LLM might produce  (lower, no spaces/punct)
# Values : exact canonical name as it appears in the reference CSV
#
# Add rows here whenever a new mismatch pattern is discovered.
# ---------------------------------------------------------------------------
_BANK_CANONICAL: dict[str, str] = {
    # BSN variants
    "bsn":                          "BSN",
    "banksimpanannasional":         "BSN",
    "banksimpanannasionalberhad":   "BSN",

    # Maybank
    "maybank":                      "Maybank",
    "maybankberhad":                "Maybank",
    "malayanbankingberhad":         "Maybank",
    "maybankislamic":               "Maybank Islamic",
    "maybankislamicberhad":         "Maybank Islamic",

    # CIMB
    "cimbbank":                     "CIMB Bank",
    "cimbbankberhad":               "CIMB Bank",
    "cimbislamic":                  "CIMB Islamic",
    "cimbislamicberhad":            "CIMB Islamic",

    # Alliance
    "alliancebank":                 "Alliance Bank",
    "alliancebankberhad":           "Alliance Bank",
    "allianceislamicbank":          "Alliance Islamic Bank",
    "allianceislamicbankberhad":    "Alliance Islamic Bank",
    "alliancefinanceberhad":        "Alliance Bank",

    # Hong Leong
    "hongleongbank":                "Hong Leong Bank",
    "hongleongbankberhad":          "Hong Leong Bank",
    "hongleongislamicbank":         "Hong Leong Islamic Bank",
    "hongleongislamicbankberhad":   "Hong Leong Islamic Bank",

    # RHB
    "rhbbank":                      "RHB Bank",
    "rhbbankberhad":                "RHB Bank",
    "rhbislamicbank":               "RHB Islamic Bank",
    "rhbislamicbankberhad":         "RHB Islamic Bank",

    # AmBank
    "ambank":                       "AmBank",
    "ambankberhad":                 "AmBank",
    "ambankislamic":                "AmBank Islamic",
    "ambankislamicberhad":          "AmBank Islamic",
    "ammbankberhad":                "AmBank",

    # HSBC
    "hsbcbank":                     "HSBC Bank",
    "hsbcbankberhad":               "HSBC Bank",
    "hsbcbankmalaysiaberhad":       "HSBC Bank",
    "hsbcamanah":                   "HSBC Amanah",
    "hsbcamanahmalaysiaberhad":     "HSBC Amanah",

    # OCBC
    "ocbc":                         "OCBC Bank",
    "ocbcbank":                     "OCBC Bank",
    "ocbcbankberhad":               "OCBC Bank",
    "ocbcbankmalaysiaberhad":       "OCBC Bank",
    "ocbcalamin":                   "OCBC Al-Amin",
    "ocbcalaminbankberhad":         "OCBC Al-Amin",

    # Public Bank (sender — should not normally appear but kept for completeness)
    "publicbankberhad":             "Public Bank Berhad",
    "publicbank":                   "Public Bank Berhad",
    "publicislamicbank":            "Public Islamic Bank",
    "publicislamicbankberhad":      "Public Islamic Bank",

    # Kuwait Finance House
    "kuwaitfinancehouse":           "Kuwait Finance House",
    "kuwaitfinancehouseberhad":     "Kuwait Finance House",
    "kfh":                          "Kuwait Finance House",

    # Standard Chartered
    "standardcharteredbank":        "Standard Chartered Bank",
    "standardchartered":            "Standard Chartered Bank",
    "standardchartereredsaadiq":    "Standard Chartered Saadiq",
    "standardchartteredsaadiq":     "Standard Chartered Saadiq",
    "standardchartteredsaadiqberhad": "Standard Chartered Saadiq",

    # Bank Islam / Muamalat
    "bankislam":                    "Bank Islam",
    "bankislammalaysiaberhad":      "Bank Islam",
    "bankmuamalat":                 "Bank Muamalat",
    "bankmuamalatmalaysiaberhad":   "Bank Muamalat",

    # Affin
    "affinbank":                    "Affin Bank",
    "affinbankberhad":              "Affin Bank",
    "affinislamicbank":             "Affin Islamic Bank",
    "affinislamicbankberhad":       "Affin Islamic Bank",

    # Agro / Rakyat
    "agrobank":                     "Agro Bank",
    "bankpertanianberhad":          "Agro Bank",
    "bankrakyat":                   "Bank Rakyat",
    "bankrakyatberhad":             "Bank Rakyat",
    "bankkeperjaanrakyat":          "Bank Rakyat",

    # UOB
    "uob":                          "UOB Bank",
    "uobbank":                      "UOB Bank",
    "unitedoberseabank":            "UOB Bank",
    "unitedoberseabankberhad":      "UOB Bank",

    # Citibank
    "citibank":                     "Citibank",
    "citibankberhad":               "Citibank",
    "citibankmalaysiaberhad":       "Citibank",
}


def _canonical_bank(raw: str | None) -> str | None:
    """
    Normalise a raw bank name string to its canonical form.

    Steps:
      1. Strip punctuation, spaces, "berhad", "(m)", common suffixes
      2. Look up in the canonical map
      3. If not found, return the original (trimmed) string so the
         comparison still runs — just won't match if truly different
    """
    if not raw:
        return raw
    # Remove punctuation except letters and digits, lowercase
    key = re.sub(r'[^a-z0-9]', '', raw.lower())
    return _BANK_CANONICAL.get(key, raw.strip())


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def _normalise_key(raw: str) -> str:
    name = Path(raw).stem
    name = re.sub(r'_extracted$', '', name, flags=re.IGNORECASE).strip()
    return name


def _normalise_header(h: str) -> str:
    return h.strip().lower().replace(" ", "")


def _load_csv(path: Path) -> dict[str, dict]:
    if not path.exists():
        logger.warning("Reference CSV not found at %s — comparisons will be skipped", path)
        return {}

    records: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            logger.warning("Reference CSV appears empty")
            return {}

        header_map = {_normalise_header(h): h for h in reader.fieldnames}

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
    match = _normalise_value(extracted) == _normalise_value(expected)
    return FieldComparisonDetail(
        extracted=extracted,
        expected=expected,
        match=match,
    )


def _bank_field_match(extracted: str | None, expected: str | None) -> FieldComparisonDetail:
    """
    Like _field_match but first canonicalises the extracted bank name.
    The canonicalised form is what we store as `extracted` so the UI
    shows the clean name, not the raw LLM output.
    """
    canonical_extracted = _canonical_bank(extracted)
    match = _normalise_value(canonical_extracted) == _normalise_value(expected)
    return FieldComparisonDetail(
        extracted=canonical_extracted,
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
    key = _normalise_key(filename_raw)
    reference = get_reference_data()
    row = reference.get(key)

    if row is None:
        logger.warning("Filename key '%s' not found in reference CSV", key)
        return ComparisonResult(
            filename_key=key,
            csv_row_found=False,
            bank_name=FieldComparisonDetail(extracted=_canonical_bank(bank_name), expected=None, match=False),
            fi_num=FieldComparisonDetail(extracted=fi_num, expected=None, match=False),
            master_account_number=FieldComparisonDetail(extracted=master_account_number, expected=None, match=False),
            sub_account_number=FieldComparisonDetail(extracted=sub_account_number, expected=None, match=False),
            all_match=False,
        )

    bank_cmp   = _bank_field_match(bank_name,             row.get("bank"))
    fi_cmp     = _field_match(fi_num,                     row.get("fi_code"))
    master_cmp = _field_match(master_account_number,      row.get("masteracc"))
    sub_cmp    = _field_match(sub_account_number,         row.get("subacc"))

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