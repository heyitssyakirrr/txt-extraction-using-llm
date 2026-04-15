from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, File, UploadFile

from app.core.config import get_settings
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
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuneable constants — adjust based on LLM thread/batch capacity.
#
# Effective rows in flight at once = ROWS_PER_CHUNK × PARALLEL_WINDOW.
# Example: 5 rows/chunk × 2 parallel = 10 rows processed per window.
# Raise ROWS_PER_CHUNK if the LLM handles larger inputs reliably.
# Raise PARALLEL_WINDOW if the LLM server has spare thread capacity.
# Lower either if you see 503 / 504 errors under shared-resource conditions.
# ---------------------------------------------------------------------------
ROWS_PER_CHUNK = 5   # rows sent to LLM per chunk
PARALLEL_WINDOW = 2  # chunks sent in parallel before awaiting and moving on
MAX_WINDOW_RETRIES = 3


# ---------------------------------------------------------------------------
# Pre-processing — strip everything except date + balance before LLM sees it
# ---------------------------------------------------------------------------

def _preprocess_statement(text: str) -> list[str]:
    """
    Parse the markdown table in Python and return only the meaningful lines.
    Each output line: "DDMMYY | 1,234.56DR"

    Returns a list of clean row strings (not a single joined string) so the
    caller can chunk them freely without re-splitting.
    """
    rows = []
    for line in text.splitlines():
        if not (line.startswith("|") and line.endswith("|")):
            continue
        if re.match(r'^\|[-| :]+\|$', line):
            continue

        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 2:
            continue

        date_col = cols[0]
        if not re.match(r'^\d{6}$|^\d{4}-\d{2}-\d{2}$', date_col):
            continue

        balance_col = cols[-1]
        if not re.search(r'\d', balance_col):
            continue

        rows.append(f"{date_col} | {balance_col}")

    return rows


def _chunk_rows(rows: list[str], chunk_size: int) -> list[str]:
    """
    Split list of preprocessed row strings into chunks.
    Each chunk is a single joined string ready to embed in a prompt.
    """
    chunks = []
    for i in range(0, len(rows), chunk_size):
        chunk_text = "\n".join(rows[i:i + chunk_size])
        chunks.append(chunk_text)
    return chunks


# ---------------------------------------------------------------------------
# Pure-Python arithmetic
# ---------------------------------------------------------------------------

def _to_decimal(value: str) -> Decimal | None:
    try:
        cleaned = value.strip().lstrip("RMrm $").replace(",", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, AttributeError):
        return None


def _fmt(d: Decimal) -> str:
    return f"{d:.2f}"


def _compute_summaries(raw_rows: list[dict]) -> SummaryResult:
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

    daily_summaries: list[DailySummary] = []
    for date in sorted(date_balances.keys()):
        balances = date_balances[date]
        daily_summaries.append(
            DailySummary(
                date=date,
                min_balance=_fmt(min(balances)),
                max_balance=_fmt(max(balances)),
                closing_balance=_fmt(balances[-1]),
            )
        )

    month_dailies: dict[str, list[DailySummary]] = defaultdict(list)
    for ds in daily_summaries:
        month = ds.date[:7]
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
                closing_balance=days[-1].closing_balance,
            )
        )

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
# LLM chunk calls
# ---------------------------------------------------------------------------

async def _call_llm_chunk(chunk_text: str, chunk_index: int, total: int) -> list[dict] | None:
    """
    Send one chunk to the LLM and return its rows.
    Retries once with a 3-second back-off on any failure.
    Returns None after all retries fail — one bad chunk never kills the whole
    request, and None is distinguishable from [] (LLM returned no rows).
    """
    logger.debug(
        "Chunk %d/%d — sending %d lines",
        chunk_index + 1, total, chunk_text.count("\n") + 1,
    )

    last_exc: Exception | None = None
    for attempt in range(2):  # attempt 0 = first try, attempt 1 = retry
        if attempt > 0:
            logger.warning(
                "Chunk %d/%d — attempt %d failed: %s — retrying in 3s",
                chunk_index + 1, total, attempt, last_exc,
            )
            await asyncio.sleep(3)
        try:
            prompt = build_summary_prompt(chunk_text)
            llm_result = await llm_client.extract_fields(
                prompt,
                stop=["} {", "\n} {", "\n}{"],
            )
            rows = llm_result.get("rows") or []
            logger.debug(
                "Chunk %d/%d — received %d rows",
                chunk_index + 1, total, len(rows),
            )
            return rows
        except Exception as exc:
            last_exc = exc

    logger.error(
        "Chunk %d/%d — all 2 attempts failed: %s",
        chunk_index + 1, total, last_exc,
    )
    return None  # None = failed; [] = succeeded but LLM returned no rows


async def _run_summarisation(original_text: str, source: str) -> SummaryResponse:
    # Step 1 — preprocess: strip everything except date + balance
    preprocessed_rows = _preprocess_statement(original_text)
    logger.debug(
        "Preprocessed %d rows from %d input chars",
        len(preprocessed_rows), len(original_text),
    )

    if not preprocessed_rows:
        logger.warning("No transaction rows found after preprocessing")
        return SummaryResponse(
            success=False,
            message="No transaction rows found in the uploaded statement.",
            data=SummaryResult(),
            meta=ExtractionMeta(
                input_characters=len(original_text),
                llm_called=False,
                source=source,
            ),
        )

    # Step 2 — chunk the preprocessed rows
    chunks = _chunk_rows(preprocessed_rows, ROWS_PER_CHUNK)
    logger.debug(
        "%d rows split into %d chunks of up to %d rows each",
        len(preprocessed_rows), len(chunks), ROWS_PER_CHUNK,
    )

    # Step 3 — fire chunks in parallel windows, with retry rounds for failures
    total_chunks = len(chunks)
    results: list[list[dict] | None] = [None] * total_chunks  # index-aligned
    failed_indices = list(range(total_chunks))                 # all pending initially

    for retry_round in range(MAX_WINDOW_RETRIES):
        if not failed_indices:
            break

        if retry_round > 0:
            wait = 30 * retry_round  # round 1: 30s, round 2: 60s
            logger.warning(
                "Retry round %d/%d — %d chunks still failed, waiting %ds before retrying: chunks %s",
                retry_round, MAX_WINDOW_RETRIES - 1,
                len(failed_indices), wait,
                [i + 1 for i in failed_indices],
            )
            await asyncio.sleep(wait)

        still_failed: list[int] = []
        pending = list(failed_indices)

        for window_start in range(0, len(pending), PARALLEL_WINDOW):
            window_indices = pending[window_start: window_start + PARALLEL_WINDOW]

            logger.debug(
                "Round %d — window: running chunks %s of %d in parallel",
                retry_round + 1,
                [i + 1 for i in window_indices],
                total_chunks,
            )

            window_tasks = [
                _call_llm_chunk(chunks[i], i, total_chunks)
                for i in window_indices
            ]
            window_results = await asyncio.gather(*window_tasks)

            for i, result in zip(window_indices, window_results):
                if result is None:
                    still_failed.append(i)
                else:
                    results[i] = result  # slot back in original order

            # Breathing room between windows (skip after the last one)
            if window_start + PARALLEL_WINDOW < len(pending):
                await asyncio.sleep(3)

        failed_indices = still_failed

    # Report permanently failed chunks
    if failed_indices:
        logger.error(
            "Permanently failed chunks after %d rounds: %s — rows will be missing from summary",
            MAX_WINDOW_RETRIES,
            [i + 1 for i in failed_indices],
        )

    # Step 4 — flatten results, skipping permanently failed chunks (None)
    all_rows: list[dict] = [
        row
        for chunk_rows in results
        if chunk_rows is not None   # skip permanently failed chunks
        for row in chunk_rows
    ]
    logger.debug("Total rows collected across all chunks: %d", len(all_rows))

    # Step 5 — return partial success with warning if any chunks failed
    if failed_indices:
        failed_row_ranges = [
            f"rows {i * ROWS_PER_CHUNK + 1}–{min((i + 1) * ROWS_PER_CHUNK, len(preprocessed_rows))}"
            for i in failed_indices
        ]
        logger.error("Missing from summary: %s", ", ".join(failed_row_ranges))
        return SummaryResponse(
            success=True,  # partial result is still usable
            message=(
                "Summarisation completed with warnings. "
                f"Some transactions could not be processed: {', '.join(failed_row_ranges)}. "
                "The summary may be incomplete."
            ),
            data=_compute_summaries(all_rows),
            meta=ExtractionMeta(
                input_characters=len(original_text),
                llm_called=True,
                source=source,
            ),
        )

    # Step 6 — full success
    return SummaryResponse(
        success=True,
        message="Summarisation completed successfully.",
        data=_compute_summaries(all_rows),
        meta=ExtractionMeta(
            input_characters=len(original_text),
            llm_called=True,
            source=source,
        ),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/from-file", response_model=SummaryResponse)
async def summarise_from_file(file: UploadFile = File(...)) -> SummaryResponse:
    raw_bytes, ext = await validate_and_read_upload(file)
    filename = file.filename or "uploaded_file"
    original_text = decode_txt_bytes(raw_bytes)
    return await _run_summarisation(original_text=original_text, source=filename)