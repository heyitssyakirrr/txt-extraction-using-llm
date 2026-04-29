from __future__ import annotations

"""
pipeline.py
-----------
Two-stage streaming pipeline for batch extraction.

Stage 1 (_stage_ocr)    — sends each file to Docling OCR concurrently with Stage 2.
Stage 2 (_stream_batch) — reads OCR results from the queue, calls the LLM, writes CSV.

Both stages retry individually via _with_retry up to _MAX_ATTEMPTS times, with
each retry increasing the timeout by _RETRY_TIMEOUT_INCREMENT seconds.
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings
from app.features.extraction.router import _run_extraction
from app.features.extraction.batch.csv_writer import (
    _CSV_HEADER,
    _comment,
    _make_data_row,
    _make_error_row,
)
from app.services.file_service import decode_txt_bytes, validate_and_read_upload

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Output directory root — subfolders created per run
# ---------------------------------------------------------------------------
_OUTPUT_ROOT = Path("batch_outputs")

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------
# Total attempts = 1 first try + 2 retries
_MAX_ATTEMPTS = 3
# Each retry increases the timeout by this many seconds (3 minutes)
_RETRY_TIMEOUT_INCREMENT = 180.0

# ---------------------------------------------------------------------------
# Pipeline sentinel — signals Stage 2 that Stage 1 is done
# ---------------------------------------------------------------------------
_DONE = object()


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------

async def _with_retry(label: str, base_timeout: float, coro_fn, *args, **kwargs):
    """
    Call an async function up to _MAX_ATTEMPTS times.
    Each retry increases the timeout by _RETRY_TIMEOUT_INCREMENT seconds.

    Attempt 1: base_timeout
    Attempt 2: base_timeout + 1 x _RETRY_TIMEOUT_INCREMENT
    Attempt 3: base_timeout + 2 x _RETRY_TIMEOUT_INCREMENT

    The increased timeout is passed as a keyword argument 'timeout' to coro_fn.
    Raises the last exception if all attempts fail.

    label        — human-readable name for logging e.g. "OCR file1.pdf"
    base_timeout — the normal timeout for attempt 1 (seconds)
    coro_fn      — the async function to call
    *args / **kwargs — forwarded to coro_fn
    """
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        current_timeout = base_timeout + (attempt - 1) * _RETRY_TIMEOUT_INCREMENT
        try:
            logger.debug(
                "%s — attempt %d/%d timeout=%.0fs",
                label, attempt, _MAX_ATTEMPTS, current_timeout,
            )
            return await coro_fn(*args, timeout=current_timeout, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS:
                logger.warning(
                    "%s — attempt %d/%d failed (timeout=%.0fs): %s — retrying with %.0fs",
                    label, attempt, _MAX_ATTEMPTS, current_timeout, exc,
                    current_timeout + _RETRY_TIMEOUT_INCREMENT,
                )
            else:
                logger.error(
                    "%s — all %d attempts failed: %s",
                    label, _MAX_ATTEMPTS, exc,
                )
    raise last_exc


# ---------------------------------------------------------------------------
# Pipeline Stage 1 — Docling OCR with retry
# ---------------------------------------------------------------------------

async def _stage_ocr(files: list[UploadFile], queue: asyncio.Queue) -> None:
    """
    Reads each file, sends to Docling with retry, puts result into queue.
    On permanent failure puts the exception so Stage 2 writes an error row.
    Puts _DONE sentinel when all files are done.
    """
    for index, upload in enumerate(files, start=1):
        filename = upload.filename or f"file_{index}"
        file_start = time.monotonic()
        try:
            raw_bytes, ext = await validate_and_read_upload(upload)

            if ext == ".pdf":
                from app.services.docling_client import DoclingClient
                docling = DoclingClient()
                text = await _with_retry(
                    f"OCR {filename}",
                    settings.docling_timeout_seconds,
                    docling.pdf_to_text, raw_bytes, filename,
                )
            else:
                # TXT — instant decode, no network call, no retry needed
                text = decode_txt_bytes(raw_bytes)

            del raw_bytes
            await queue.put((index, filename, text, file_start, None))
            logger.debug("OCR done [%d] %s — queued for LLM", index, filename)

        except Exception as exc:
            # All retries exhausted — pass error to Stage 2
            await queue.put((index, filename, None, file_start, exc))
            logger.warning("OCR permanently failed [%d] %s: %s", index, filename, exc)

    await queue.put(_DONE)


# ---------------------------------------------------------------------------
# Core streaming generator — pipelined with retry
# ---------------------------------------------------------------------------

async def stream_batch(files: list[UploadFile]) -> AsyncGenerator[str, None]:
    """
    Two-stage pipeline:
      Stage 1 (OCR)  — background task, sends files to Docling
      Stage 2 (LLM)  — main loop, reads from queue, calls LLM

    Both stages retry individually up to _MAX_ATTEMPTS times.
    The client read timeout is set to cover worst case per file:
        Docling timeout (300s) + LLM timeout (600s) +
        retry waits (2 × 180s) + buffer = ~1440s per file.
    """
    total = len(files)
    ok_count = 0
    error_count = 0
    batch_start = time.monotonic()

    now = datetime.now()
    date_folder = _OUTPUT_ROOT / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    date_folder.mkdir(parents=True, exist_ok=True)
    csv_filename = now.strftime("extraction_%Y-%m-%d.csv")
    csv_path = date_folder / csv_filename
    download_url = (
        f"/extract/batch/download"
        f"/{now.strftime('%Y')}/{now.strftime('%m')}/{now.strftime('%d')}"
        f"/{csv_filename}"
    )

    # maxsize=1: Stage 1 can be at most 1 file ahead of Stage 2
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)

    try:
        with csv_path.open("w", encoding="utf-8", newline="") as csv_fh:
            csv_fh.write(_CSV_HEADER)
            csv_fh.flush()

            ocr_task = asyncio.create_task(_stage_ocr(files, queue))

            while True:
                item = await queue.get()

                if item is _DONE:
                    break

                index, filename, text, file_start, ocr_error = item

                yield _comment(f"[{index}/{total}] processing LLM: {filename}")

                try:
                    if ocr_error is not None:
                        raise ocr_error

                    # LLM with retry
                    result = await _with_retry(
                        f"LLM {filename}",
                        settings.llm_timeout_seconds,
                        _run_extraction,
                        original_text=text,
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

            await ocr_task

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