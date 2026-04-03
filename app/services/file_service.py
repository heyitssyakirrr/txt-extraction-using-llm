from __future__ import annotations

import logging

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def read_txt_upload(file: UploadFile) -> str:
    ext = ""
    if file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower()
        if f".{ext}" not in settings.allowed_upload_extensions:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported file type '.{ext}'. Only .txt files are accepted.",
            )

    raw_bytes = await file.read()

    if len(raw_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the maximum allowed size of {settings.max_upload_bytes // (1024 * 1024)} MB.",
        )

    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return raw_bytes.decode("latin-1")