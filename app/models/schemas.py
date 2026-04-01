from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Inbound request models
# ---------------------------------------------------------------------------

class ExtractFromTextRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        description="Raw text to extract information from.",
    )


# ---------------------------------------------------------------------------
# Extraction result & response
# ---------------------------------------------------------------------------

class ExtractionResult(BaseModel):
    """The fields we want to extract from the source text."""
    name: str | None = Field(
        default=None,
        description="Extracted person / account-holder name.",
    )
    account_number: str | None = Field(
        default=None,
        description="Extracted account number, preserved exactly as found.",
    )

    # FUTURE FIELDS: add new fields here when the requirements grow.


class ExtractionMeta(BaseModel):
    """Metadata attached to every extraction response, useful for debugging."""
    input_characters: int = Field(
        description="Character count of the raw input."
    )
    preprocessed_characters: int = Field(
        description="Character count after preprocessing / windowing."
    )
    llm_called: bool = Field(
        description="Whether the LLM microservice was invoked."
    )
    llm_fallback_used: bool = Field(
        description="True when regex fallback filled a field the LLM left null."
    )
    source: str = Field(
        description="Origin of the input, 'raw_text' or a filename."
    )


class ExtractResponse(BaseModel):
    success: bool
    message: str
    data: ExtractionResult
    meta: ExtractionMeta


# ---------------------------------------------------------------------------
# LLM microservice contract
# ---------------------------------------------------------------------------

class LLMRequestPayload(BaseModel):
    """
    Payload sent TO the LLM microservice.
    Adjust field names here when have the API contract.
    """
    prompt: str
    model: str | None = None


class LLMRawResponse(BaseModel):
    """
    Payload received FROM the LLM microservice.
    _normalize_llm_output() in llm_client.py handles multiple possible shapes.
    """
    content: str


# ---------------------------------------------------------------------------
# Error response (used by global exception handler)
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    success: bool = False
    message: str