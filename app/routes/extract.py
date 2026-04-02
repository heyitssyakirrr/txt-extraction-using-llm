"""
Extraction routes — file upload only.

/extract/from-file accepts a .txt file upload
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from app.core.config import get_settings
from app.models.schemas import (
    ExtractResponse,
    ExtractionMeta,
    ExtractionResult,
)
from app.services.file_service import (
    extract_relevant_window,
    preprocess_text,
    read_txt_upload,
    regex_fallback_extract,
)
from app.services.llm_client import LLMClient
from app.services.prompt_service import build_extraction_prompt

router = APIRouter(prefix="/extract", tags=["Extraction"])
settings = get_settings()
llm_client = LLMClient()


async def _run_extraction(original_text: str, source: str) -> ExtractResponse:
    preprocessed_text = preprocess_text(
        text=original_text,
        max_characters=settings.max_input_characters,
    )
    focused_text = extract_relevant_window(preprocessed_text)

    prompt = build_extraction_prompt(focused_text)
    llm_result = await llm_client.extract_fields(prompt)
    fallback_result = regex_fallback_extract(focused_text)

    final_name = llm_result.get("name") or fallback_result.get("name")
    final_account_number = (
        llm_result.get("account_number") or fallback_result.get("account_number")
    )

    fallback_used = (
        (final_name is not None and llm_result.get("name") is None)
        or (final_account_number is not None and llm_result.get("account_number") is None)
    )

    return ExtractResponse(
        success=True,
        message="Extraction completed successfully.",
        data=ExtractionResult(
            name=final_name,
            account_number=final_account_number,
        ),
        meta=ExtractionMeta(
            input_characters=len(original_text),
            preprocessed_characters=len(focused_text),
            llm_called=True,
            llm_fallback_used=fallback_used,
            source=source,
        ),
    )


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/from-file", response_model=ExtractResponse)
async def extract_from_file(file: UploadFile = File(...)) -> ExtractResponse:
    """Extract name and account number from an uploaded .txt file."""
    original_text = await read_txt_upload(file)
    return await _run_extraction(
        original_text=original_text,
        source=file.filename or "uploaded_file",
    )