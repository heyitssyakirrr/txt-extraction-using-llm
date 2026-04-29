from __future__ import annotations

"""
router.py
---------
POST /extract/batch
GET  /extract/batch/download/{year}/{month}/{day}/{filename}

Accepts multiple PDF or TXT files in a single multipart/form-data request.
All processing logic lives in pipeline.py; this module only handles HTTP concerns.
"""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import get_settings
from app.features.extraction.batch.pipeline import stream_batch, _OUTPUT_ROOT

router = APIRouter(prefix="/extract", tags=["Batch Extraction"])
settings = get_settings()


@router.post(
    "/batch",
    response_class=StreamingResponse,
    summary="Batch extract fields from multiple files",
)
async def extract_batch(
    files: list[UploadFile] = File(..., description="PDF or TXT files to process"),
) -> StreamingResponse:
    if not files:
        raise HTTPException(status_code=422, detail="No files provided.")

    max_files = settings.max_files_per_batch
    if len(files) > max_files:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Too many files. Received {len(files)}, "
                f"maximum allowed per request is {max_files}."
            ),
        )

    import logging
    logging.getLogger(__name__).info("Batch request received — %d file(s)", len(files))

    return StreamingResponse(
        stream_batch(files),
        media_type="text/plain",
        headers={
            "X-Batch-File-Count": str(len(files)),
            "Cache-Control": "no-cache",
        },
    )


@router.get(
    "/batch/download/{year}/{month}/{day}/{filename}",
    summary="Download the CSV result for a completed batch run",
)
async def download_batch_result(
    year: str, month: str, day: str, filename: str
) -> FileResponse:
    for segment in (year, month, day, filename):
        if ".." in segment or "/" in segment or "\\" in segment:
            raise HTTPException(status_code=400, detail="Invalid path.")

    csv_path = _OUTPUT_ROOT / year / month / day / filename

    if not csv_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {year}/{month}/{day}/{filename}",
        )

    return FileResponse(
        path=csv_path,
        media_type="text/csv",
        filename=filename,
    )