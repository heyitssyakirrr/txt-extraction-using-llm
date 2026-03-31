from pydantic import BaseModel, Field

class ExtractFromTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="The input text to extract information from")


class ExtractionResult(BaseModel):
    name: str | None = Field(default=None, description="Extracted person/customer name")
    account_numer: str | None = Field(default=None, description="Extracted account number")

class ExtractionMeta(BaseModel):
    input_characters: int
    preprocessed_characters: int
    llm_called: bool
    source: str


class ExtractResponse(BaseModel):
    success: bool
    message: str
    data: ExtractionResult
    meta: ExtractionMeta


class LLMRequestPayload(BaseModel):
    prompt: str
    model: str | None = None


class LLMRawResponse(BaseModel):
    content: str


class ErrorResponse(BaseModel):
    success: bool = False
    message: str