# This file is kept for backwards compatibility.
# The prompt logic has moved to app/features/summary/prompt.py
from app.features.extraction.prompt import build_extraction_prompt
from app.features.summary.prompt import build_summary_prompt

__all__ = ["build_extraction_prompt", "build_summary_prompt"]