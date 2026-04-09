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
# Bank statement summary schemas
# ---------------------------------------------------------------------------

class RawBalanceRow(BaseModel):
    """Single row returned by the LLM: just date + running balance."""
    date: str
    balance: str


class DailySummary(BaseModel):
    """Computed by Python from raw LLM rows — one entry per unique date."""
    date: str
    min_balance: str
    max_balance: str
    closing_balance: str   # last balance recorded on that date


class MonthlySummary(BaseModel):
    """Computed by Python — aggregated from DailySummary entries."""
    month: str             # YYYY-MM
    min_balance: str
    max_balance: str
    closing_balance: str   # last daily closing balance of the month


class SummaryResult(BaseModel):
    daily_summaries: List[DailySummary] = Field(default_factory=list)
    monthly_summaries: List[MonthlySummary] = Field(default_factory=list)
    overall_min_balance: str | None = Field(default=None)
    overall_max_balance: str | None = Field(default=None)
    overall_closing_balance: str | None = Field(default=None)


class SummaryResponse(BaseModel):
    success: bool
    message: str
    data: SummaryResult
    meta: ExtractionMeta


# ---------------------------------------------------------------------------
# Shared LLM communication schemas
# ---------------------------------------------------------------------------

class LLMRequestPayload(BaseModel):
    prompt: str
    model: str | None = None


class LLMRawResponse(BaseModel):
    content: str


class ErrorResponse(BaseModel):
    success: bool = False
    message: str