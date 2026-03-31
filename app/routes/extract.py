from fastapi import APIRouter, File, UploadFile

from app.core.config import get_settings
from app.models.schemas import (
    ExtractFromTextRequest,
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


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/from-text", response_model=ExtractResponse)
async def extract_from_text(payload: ExtractFromTextRequest) -> ExtractResponse:
    original_text = payload.text
    preprocessed_text = preprocess_text(
        text=original_text,
        max_characters=settings.max_input_characters,
    )
    focused_text = extract_relevant_window(preprocessed_text)

    prompt = build_extraction_prompt(focused_text)
    llm_result = await llm_client.extract_fields(prompt)

    # optional light fallback
    fallback_result = regex_fallback_extract(focused_text)

    final_name = llm_result.get("name") or fallback_result.get("name")
    final_account_number = llm_result.get("account_number") or fallback_result.get("account_number")

    return ExtractResponse(
        success=True,
        message="Extraction completed successfully",
        data=ExtractionResult(
            name=final_name,
            account_number=final_account_number,
        ),
        meta=ExtractionMeta(
            input_characters=len(original_text),
            preprocessed_characters=len(focused_text),
            llm_called=True,
            source="raw_text",
        ),
    )


@router.post("/from-file", response_model=ExtractResponse)
async def extract_from_file(file: UploadFile = File(...)) -> ExtractResponse:
    original_text = await read_txt_upload(file)

    preprocessed_text = preprocess_text(
        text=original_text,
        max_characters=settings.max_input_characters,
    )
    focused_text = extract_relevant_window(preprocessed_text)

    prompt = build_extraction_prompt(focused_text)
    llm_result = await llm_client.extract_fields(prompt)

    # optional light fallback
    fallback_result = regex_fallback_extract(focused_text)

    final_name = llm_result.get("name") or fallback_result.get("name")
    final_account_number = llm_result.get("account_number") or fallback_result.get("account_number")

    return ExtractResponse(
        success=True,
        message="Extraction completed successfully",
        data=ExtractionResult(
            name=final_name,
            account_number=final_account_number,
        ),
        meta=ExtractionMeta(
            input_characters=len(original_text),
            preprocessed_characters=len(focused_text),
            llm_called=True,
            source=file.filename or "uploaded_file",
        ),
    )