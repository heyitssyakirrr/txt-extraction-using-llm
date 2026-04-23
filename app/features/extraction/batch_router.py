from __future__ import annotations

"""
batch_router.py
---------------
POST /extract/batch

Accepts multiple PDF or TXT files in a single multipart/form-data request.
Processes each file sequentially through the existing _run_extraction() pipeline
and streams results back as CSV rows, one row per file, as each file completes.

Progress comment lines (prefixed with #) are interleaved in the stream so the
caller can print them to the terminal while writing data rows to a .csv file.

Design decisions
----------------
- Sequential processing: one file at a time so memory stays flat.
  Each file's bytes are released after Docling returns text.
- Per-file isolation: a failed file writes an error row and the loop continues.
- StreamingResponse: the HTTP connection stays alive and rows arrive immediately,
  so the caller never has to wait for the full batch before seeing any output.
- File count cap: controlled by settings.max_files_per_batch.
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.features.extraction.router import _run_extraction
from app.services.file_service import decode_txt_bytes, validate_and_read_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extract", tags=["Batch Extraction"])
settings = get_settings()

# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

_CSV_HEADER = (
    "filename,status,bank_name,fi_num,"
    "master_account_number,sub_account_number,"
    "name,address,"
    "reference_found,all_match,error_reason\r\n"
)


def _escape_csv_field(value: str | None) -> str:
    """
    Wrap a field value in quotes if it contains a comma, quote, or newline.
    Always returns a string — None becomes empty string.
    """
    if value is None:
        return ""
    s = str(value)
    if "," in s or '"' in s or "\n" in s or "\r" in s:
        s = '"' + s.replace('"', '""') + '"'
    return s


def _make_data_row(filename: str, result) -> str:
    """Build one CSV data row from a successful ExtractResponse."""
    d = result.data
    cmp = result.comparison

    reference_found = ""
    all_match = ""
    if cmp is not None:
        reference_found = "yes" if cmp.csv_row_found else "no"
        all_match = "yes" if cmp.all_match else "no"

    fields = [
        filename,
        "ok",
        d.bank_name,
        d.fi_num,
        d.master_account_number,
        d.sub_account_number,
        d.name,
        d.address,
        reference_found,
        all_match,
        "",
    ]
    return ",".join(_escape_csv_field(f) for f in fields) + "\r\n"


def _make_error_row(filename: str, reason: str) -> str:
    """Build one CSV error row for a file that could not be processed."""
    fields = [filename, "error", "", "", "", "", "", "", "", "", reason]
    return ",".join(_escape_csv_field(f) for f in fields) + "\r\n"


def _comment(message: str) -> str:
    """
    A CSV comment line. Standard CSV has no comment syntax, but lines starting
    with # are ignored by pandas (read_csv comment='#') and most parsers when
    configured to do so. The caller can also filter them out trivially.
    """
    return f"# {message}\r\n"


# ---------------------------------------------------------------------------
# Core streaming generator
# ---------------------------------------------------------------------------

async def _stream_batch(files: list[UploadFile]) -> AsyncGenerator[str, None]:
    """
    Async generator that drives the full batch and yields CSV lines one by one.

    Yield order per file:
      1. # [n/total] processing: <filename>
      2. data row OR error row
      3. # [n/total] done: <filename> — <duration>s — <match status>

    Final line:
      # done. X ok / Y mismatch / Z error. total: Xs
    """
    total = len(files)
    ok_count = 0
    mismatch_count = 0
    error_count = 0
    batch_start = time.monotonic()

    yield _CSV_HEADER

    for index, upload in enumerate(files, start=1):
        filename = upload.filename or f"file_{index}"
        yield _comment(f"[{index}/{total}] processing: {filename}")

        file_start = time.monotonic()

        try:
            # --- read and validate ---
            # validate_and_read_upload reads all bytes into memory here.
            # After we pass them to Docling, we del raw_bytes so Python can
            # GC them before the next file is read.
            raw_bytes, ext = await validate_and_read_upload(upload)

            # --- run extraction (Docling + LLM) ---
            if ext == ".pdf":
                from app.services.docling_client import DoclingClient
                docling = DoclingClient()
                original_text = await docling.pdf_to_text(raw_bytes, filename)
            else:
                original_text = decode_txt_bytes(raw_bytes)

            # Release PDF bytes — no longer needed
            del raw_bytes

            result = await _run_extraction(
                original_text=original_text,
                source=filename,
            )

            elapsed = time.monotonic() - file_start
            cmp = result.comparison

            if cmp and cmp.csv_row_found and cmp.all_match:
                match_label = "all match"
                ok_count += 1
            elif cmp and cmp.csv_row_found and not cmp.all_match:
                match_label = "mismatch"
                mismatch_count += 1
            else:
                match_label = "no reference"
                ok_count += 1

            yield _make_data_row(filename, result)
            yield _comment(
                f"[{index}/{total}] done: {filename} — "
                f"{elapsed:.1f}s — {match_label}"
            )

            logger.info(
                "Batch [%d/%d] %s — %.1fs — %s",
                index, total, filename, elapsed, match_label,
            )

        except Exception as exc:
            elapsed = time.monotonic() - file_start
            reason = str(exc)
            error_count += 1

            yield _make_error_row(filename, reason)
            yield _comment(
                f"[{index}/{total}] error: {filename} — "
                f"{elapsed:.1f}s — {reason}"
            )

            logger.warning(
                "Batch [%d/%d] %s failed in %.1fs: %s",
                index, total, filename, elapsed, reason,
            )

        # Small yield point between files so the event loop stays responsive
        # and the StreamingResponse can flush the buffer to the client.
        await asyncio.sleep(0)

    total_elapsed = time.monotonic() - batch_start
    yield _comment(
        f"done. {ok_count} ok / {mismatch_count} mismatch / "
        f"{error_count} error. total: {total_elapsed:.1f}s"
    )

    logger.info(
        "Batch complete — %d ok / %d mismatch / %d error — %.1fs",
        ok_count, mismatch_count, error_count, total_elapsed,
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/batch",
    response_class=StreamingResponse,
    summary="Batch extract fields from multiple files",
    description=(
        "Upload up to `max_files_per_batch` PDF or TXT files. "
        "Results stream back as CSV rows as each file completes. "
        "Lines starting with # are progress comments — filter or print them "
        "to stderr while writing data rows to a .csv file. "
    ),
)
async def extract_batch(
    files: list[UploadFile] = File(..., description="PDF or TXT files to process"),
) -> StreamingResponse:
    # --- validate file count up front before touching any file ---
    if not files:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="No files provided.")

    max_files = settings.max_files_per_batch
    if len(files) > max_files:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=(
                f"Too many files. Received {len(files)}, "
                f"maximum allowed per request is {max_files}."
            ),
        )

    logger.info(
        "Batch request received — %d file(s) — max allowed: %d",
        len(files), max_files,
    )

    return StreamingResponse(
        _stream_batch(files),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=extraction_results.csv",
            "X-Batch-File-Count": str(len(files)),
            "Cache-Control": "no-cache",
        },
    )