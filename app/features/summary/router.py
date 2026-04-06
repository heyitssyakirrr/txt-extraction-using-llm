from __future__ import annotations

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
settings = get_settings()
llm_client = LLMClient()


async def _run_summarisation(original_text: str, source: str) -> SummaryResponse:
    prompt = build_summary_prompt(original_text)
    llm_result = await llm_client.extract_fields(prompt)

    raw_daily = llm_result.get("daily_summaries") or []
    raw_monthly = llm_result.get("monthly_summaries") or []

    daily_summaries = [
        DailySummary(
            date=row.get("date"),
            total_debit=row.get("total_debit"),
            total_credit=row.get("total_credit"),
            closing_balance=row.get("closing_balance"),
        )
        for row in raw_daily
        if isinstance(row, dict)
    ]

    monthly_summaries = [
        MonthlySummary(
            month=row.get("month"),
            total_debit=row.get("total_debit"),
            total_credit=row.get("total_credit"),
            min_balance=row.get("min_balance"),
            max_balance=row.get("max_balance"),
        )
        for row in raw_monthly
        if isinstance(row, dict)
    ]

    return SummaryResponse(
        success=True,
        message="Summarisation completed successfully.",
        data=SummaryResult(
            daily_summaries=daily_summaries,
            monthly_summaries=monthly_summaries,
            overall_total_debit=llm_result.get("overall_total_debit"),
            overall_total_credit=llm_result.get("overall_total_credit"),
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


@router.post("/from-file", response_model=SummaryResponse)
async def summarise_from_file(file: UploadFile = File(...)) -> SummaryResponse:
    raw_bytes, ext = await validate_and_read_upload(file)
    filename = file.filename or "uploaded_file"
    original_text = decode_txt_bytes(raw_bytes)
    return await _run_summarisation(original_text=original_text, source=filename)