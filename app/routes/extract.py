from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from app.core.config import get_settings
from app.models.schemas import (
    ExtractResponse,
    ExtractionMeta,
    ExtractionResult,
)
from app.services.file_service import read_txt_upload
from app.services.llm_client import LLMClient
from app.services.prompt_service import build_extraction_prompt

router = APIRouter(prefix="/extract", tags=["Extraction"])
settings = get_settings()
llm_client = LLMClient()


async def _run_extraction(original_text: str, source: str) -> ExtractResponse:
    prompt = build_extraction_prompt(original_text)
    llm_result = await llm_client.extract_fields(prompt)

    return ExtractResponse(
        success=True,
        message="Extraction completed successfully.",
        data=ExtractionResult(
            name=llm_result.get("name"),
            master_account_number=llm_result.get("master_account_number"),
            sub_account_number=llm_result.get("sub_account_number"),
            address=llm_result.get("address"),
            fi_num=llm_result.get("fi_num"),
        ),
        meta=ExtractionMeta(
            input_characters=len(original_text),
            llm_called=True,
            source=source,
        ),
    )


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/from-file", response_model=ExtractResponse)
async def extract_from_file(file: UploadFile = File(...)) -> ExtractResponse:
    original_text = await read_txt_upload(file)
    return await _run_extraction(
        original_text=original_text,
        source=file.filename or "uploaded_file",
    )