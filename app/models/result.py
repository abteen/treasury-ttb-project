"""
Pydantic models for verification results returned to the frontend.
"""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel


class FieldVerdict(BaseModel):
    field: str
    field_label: str                        # Human-readable label for UI
    extracted_value: Optional[str]          # What the vision model saw on the label
    application_value: str                  # What the application form claimed
    status: Literal["pass", "warning", "fail"]
    note: Optional[str] = None              # Explanation for warning/fail


class VerificationResult(BaseModel):
    image_filename: str
    overall_status: Literal["pass", "warning", "fail"]
    fields: list[FieldVerdict]
    model_used: str
    prompt_version: str
    timestamp: datetime
    error: Optional[str] = None             # Set if extraction itself failed
    prediction_only: bool = False           # True when no application data is compared
    cache_hit: bool = False                 # True when response came from the static cache
    processing_time_ms: Optional[float] = None  # Wall-clock time for this image


class BatchVerificationResponse(BaseModel):
    results: list[VerificationResult]
    total: int
    passed: int
    warnings: int
    failed: int
    errors: int
    total_time_ms: Optional[float] = None   # Wall-clock time for the whole batch
