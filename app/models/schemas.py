from typing import List
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Customer detail extraction schemas
# ---------------------------------------------------------------------------

class ExtractionResult(BaseModel):
    name: str | None = Field(default=None)
    master_account_number: str | None = Field(default=None)
    sub_account_number: str | None = Field(default=None)
    address: str | None = Field(default=None)
    fi_num: str | None = Field(default=None)
    # FUTURE FIELDS: add here


class ExtractionMeta(BaseModel):
    input_characters: int
    llm_called: bool
    source: str


class ExtractResponse(BaseModel):
    success: bool
    message: str
    data: ExtractionResult
    meta: ExtractionMeta


# ---------------------------------------------------------------------------
# Bank statement summary extraction schemas
# ---------------------------------------------------------------------------

class DailySummary(BaseModel):
    date: str | None = Field(default=None)
    total_debit: str | None = Field(default=None)
    total_credit: str | None = Field(default=None)
    closing_balance: str | None = Field(default=None)


class MonthlySummary(BaseModel):
    month: str | None = Field(default=None)
    total_debit: str | None = Field(default=None)
    total_credit: str | None = Field(default=None)
    min_balance: str | None = Field(default=None)
    max_balance: str | None = Field(default=None)


class SummaryResult(BaseModel):
    daily_summaries: List[DailySummary] = Field(default_factory=list)
    monthly_summaries: List[MonthlySummary] = Field(default_factory=list)
    overall_total_debit: str | None = Field(default=None)
    overall_total_credit: str | None = Field(default=None)


class SummaryResponse(BaseModel):
    success: bool
    message: str
    data: SummaryResult
    meta: ExtractionMeta  # reused — same shape


# ---------------------------------------------------------------------------
# Shared LLM communication schemas (used by both features)
# ---------------------------------------------------------------------------

class LLMRequestPayload(BaseModel):
    prompt: str
    model: str | None = None


class LLMRawResponse(BaseModel):
    content: str


class ErrorResponse(BaseModel):
    success: bool = False
    message: str