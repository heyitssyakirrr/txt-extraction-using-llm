from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, File, UploadFile

from app.features.summary.prompt import build_summary_prompt
from app.models.schemas import (
    DailySummary,
    ExtractionMeta,
    MonthlySummary,
    SummaryResponse,
    SummaryResult,
)
from app.services.file_service import decode_txt_bytes, validate_and_read_upload
from app.services.llm_client import LLMClient

router = APIRouter(prefix="/summarise", tags=["Summarisation"])
llm_client = LLMClient()


# ---------------------------------------------------------------------------
# Pure-Python arithmetic — no LLM involvement
# ---------------------------------------------------------------------------

def _to_decimal(value: str) -> Decimal | None:
    """Safely parse a balance string to Decimal; return None on failure."""
    try:
        # strip currency symbols, spaces, commas  e.g. "RM 1,234.56" → "1234.56"
        cleaned = value.strip().lstrip("RMrm $").replace(",", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, AttributeError):
        return None


def _fmt(d: Decimal) -> str:
    return f"{d:.2f}"


def _compute_summaries(raw_rows: list[dict]) -> SummaryResult:
    """
    Given a list of {"date": "YYYY-MM-DD", "balance": "..."} dicts from the LLM,
    compute daily and monthly summaries entirely in Python.

    Per day  : min / max / closing (last) balance
    Per month: min / max / closing (last daily closing) balance
    Overall  : min / max / closing across the whole statement
    """

    # ── 1. Group balances by date (preserving insertion order for "last") ──
    # date_balances[date] = list of Decimal balances in order seen
    date_balances: dict[str, list[Decimal]] = defaultdict(list)

    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        date = (row.get("date") or "").strip()
        raw_bal = row.get("balance") or ""
        bal = _to_decimal(raw_bal)
        if date and bal is not None:
            date_balances[date].append(bal)

    if not date_balances:
        return SummaryResult()

    # ── 2. Build daily summaries ──
    daily_summaries: list[DailySummary] = []
    for date in sorted(date_balances.keys()):
        balances = date_balances[date]
        daily_summaries.append(
            DailySummary(
                date=date,
                min_balance=_fmt(min(balances)),
                max_balance=_fmt(max(balances)),
                closing_balance=_fmt(balances[-1]),   # last transaction of the day
            )
        )

    # ── 3. Build monthly summaries from daily data ──
    # month_dailies[YYYY-MM] = list of DailySummary in order
    month_dailies: dict[str, list[DailySummary]] = defaultdict(list)
    for ds in daily_summaries:
        month = ds.date[:7]   # "YYYY-MM"
        month_dailies[month].append(ds)

    monthly_summaries: list[MonthlySummary] = []
    for month in sorted(month_dailies.keys()):
        days = month_dailies[month]
        all_mins = [Decimal(d.min_balance) for d in days]
        all_maxs = [Decimal(d.max_balance) for d in days]
        monthly_summaries.append(
            MonthlySummary(
                month=month,
                min_balance=_fmt(min(all_mins)),
                max_balance=_fmt(max(all_maxs)),
                closing_balance=days[-1].closing_balance,  # last day of month
            )
        )

    # ── 4. Overall stats ──
    all_bal_decimals = [
        bal for balances in date_balances.values() for bal in balances
    ]
    last_daily = daily_summaries[-1]

    return SummaryResult(
        daily_summaries=daily_summaries,
        monthly_summaries=monthly_summaries,
        overall_min_balance=_fmt(min(all_bal_decimals)),
        overall_max_balance=_fmt(max(all_bal_decimals)),
        overall_closing_balance=last_daily.closing_balance,
    )


# ---------------------------------------------------------------------------
# Route logic
# ---------------------------------------------------------------------------

async def _run_summarisation(original_text: str, source: str) -> SummaryResponse:
    prompt = build_summary_prompt(original_text)
    llm_result = await llm_client.extract_fields(
        prompt,
        stop=["} {", "\n} {", "\n}{"]
    )

    # LLM returns {"rows": [{"date": ..., "balance": ...}, ...]}
    raw_rows = llm_result.get("rows") or []

    summary_result = _compute_summaries(raw_rows)

    return SummaryResponse(
        success=True,
        message="Summarisation completed successfully.",
        data=summary_result,
        meta=ExtractionMeta(
            input_characters=len(original_text),
            llm_called=True,
            source=source,
        ),
    )


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/from-file", response_model=SummaryResponse)
async def summarise_from_file(file: UploadFile = File(...)) -> SummaryResponse:
    raw_bytes, ext = await validate_and_read_upload(file)
    filename = file.filename or "uploaded_file"
    original_text = decode_txt_bytes(raw_bytes)
    return await _run_summarisation(original_text=original_text, source=filename)