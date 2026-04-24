from __future__ import annotations

"""
batch_router.py
---------------
POST /extract/batch
GET  /extract/batch/download/{date}/{filename}

Accepts multiple PDF or TXT files in a single multipart/form-data request.
Processes each file sequentially through the existing _run_extraction() pipeline
and streams progress comment lines (prefixed with #) back to the caller.

When all files are processed the server saves the CSV under:
    batch_outputs/YYYY-MM-DD/extraction_HHMMSS.csv

and streams a final comment line with the download URL. The caller then hits
GET /extract/batch/download/YYYY-MM-DD/extraction_HHMMSS.csv to retrieve it.

CSV columns: filename, bank_name, fi_num, master_account_number, sub_account_number
(comparison data is retained internally for future use but not written to CSV)
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import get_settings
from app.features.extraction.router import _run_extraction
from app.services.file_service import decode_txt_bytes, validate_and_read_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extract", tags=["Batch Extraction"])
settings = get_settings()

# ---------------------------------------------------------------------------
# Output directory — created on first use
# ---------------------------------------------------------------------------
_OUTPUT_ROOT = Path("batch_outputs")

# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

_CSV_HEADER = "filename,bank_name,fi_num,master_account_number,sub_account_number\r\n"


def _escape_csv_field(value: str | None) -> str:
    if value is None:
        return ""
    s = str(value)
    if "," in s or '"' in s or "\n" in s or "\r" in s:
        s = '"' + s.replace('"', '""') + '"'
    return s


def _make_data_row(filename: str, result) -> str:
    """Build one CSV data row — 5 fields only."""
    d = result.data
    fields = [
        filename,
        d.bank_name,
        d.fi_num,
        d.master_account_number,
        d.sub_account_number,
    ]
    return ",".join(_escape_csv_field(f) for f in fields) + "\r\n"


def _make_error_row(filename: str) -> str:
    """Build one CSV error row — empty fields except filename."""
    fields = [filename, "", "", "", ""]
    return ",".join(_escape_csv_field(f) for f in fields) + "\r\n"


def _comment(message: str) -> str:
    return f"# {message}\r\n"


# ---------------------------------------------------------------------------
# Core streaming generator
# ---------------------------------------------------------------------------

async def _stream_batch(files: list[UploadFile]) -> AsyncGenerator[str, None]:
    """
    Processes all files sequentially.
    Streams only # progress comment lines to the caller.
    Writes CSV rows to batch_outputs/extraction_YYYY-MM-DD.csv on the server.
    Yields a final # line with the download URL when done.
    """
    total = len(files)
    ok_count = 0
    error_count = 0
    batch_start = time.monotonic()

    # Build output path: batch_outputs/extraction_2026-04-24.csv
    now = datetime.now()
    _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    csv_filename = now.strftime("extraction_%Y-%m-%d.csv")
    csv_path = _OUTPUT_ROOT / csv_filename
    download_url = f"/extract/batch/download/{csv_filename}"

    try:
        with csv_path.open("w", encoding="utf-8", newline="") as csv_fh:
            csv_fh.write(_CSV_HEADER)
            csv_fh.flush()

            for index, upload in enumerate(files, start=1):
                filename = upload.filename or f"file_{index}"
                yield _comment(f"[{index}/{total}] processing: {filename}")

                file_start = time.monotonic()

                try:
                    raw_bytes, ext = await validate_and_read_upload(upload)

                    if ext == ".pdf":
                        from app.services.docling_client import DoclingClient
                        docling = DoclingClient()
                        original_text = await docling.pdf_to_text(raw_bytes, filename)
                    else:
                        original_text = decode_txt_bytes(raw_bytes)

                    del raw_bytes

                    result = await _run_extraction(
                        original_text=original_text,
                        source=filename,
                    )

                    elapsed = time.monotonic() - file_start
                    ok_count += 1

                    csv_fh.write(_make_data_row(filename, result))
                    csv_fh.flush()

                    yield _comment(f"[{index}/{total}] done: {filename} — {elapsed:.1f}s")

                    logger.info("Batch [%d/%d] %s — %.1fs", index, total, filename, elapsed)

                except Exception as exc:
                    elapsed = time.monotonic() - file_start
                    error_count += 1

                    csv_fh.write(_make_error_row(filename))
                    csv_fh.flush()

                    yield _comment(
                        f"[{index}/{total}] error: {filename} — {elapsed:.1f}s — {exc}"
                    )

                    logger.warning(
                        "Batch [%d/%d] %s failed in %.1fs: %s",
                        index, total, filename, elapsed, exc,
                    )

                await asyncio.sleep(0)

        total_elapsed = time.monotonic() - batch_start
        yield _comment(f"done. {ok_count} ok / {error_count} error — total: {total_elapsed:.1f}s")
        yield _comment(f"download: {download_url}")

        logger.info(
            "Batch complete — %d ok / %d error — %.1fs — saved: %s",
            ok_count, error_count, total_elapsed, csv_path,
        )

    except Exception as exc:
        logger.exception("Batch stream failed: %s", exc)
        yield _comment(f"fatal error: {exc}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/batch",
    response_class=StreamingResponse,
    summary="Batch extract fields from multiple files",
    description=(
        "Upload PDF or TXT files. Progress streams back as # comment lines. "
        "When complete, a # download: /extract/batch/download/YYYY-MM-DD/extraction_HHMMSS.csv "
        "line is yielded. Hit that URL to download the CSV."
    ),
)
async def extract_batch(
    files: list[UploadFile] = File(..., description="PDF or TXT files to process"),
) -> StreamingResponse:
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

    logger.info("Batch request received — %d file(s)", len(files))

    return StreamingResponse(
        _stream_batch(files),
        media_type="text/plain",
        headers={
            "X-Batch-File-Count": str(len(files)),
            "Cache-Control": "no-cache",
        },
    )


@router.get(
    "/batch/download/{filename}",
    summary="Download the CSV result for a completed batch run",
)
async def download_batch_result(filename: str) -> FileResponse:
    from fastapi import HTTPException

    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    csv_path = _OUTPUT_ROOT / filename

    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    return FileResponse(
        path=csv_path,
        media_type="text/csv",
        filename=filename,
    )