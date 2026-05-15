"""
Pydantic models for audit log entries.

AuditEntry / AuditFieldEntry — per-image human review events (verification & prediction modes).
PredictionLog               — image-level prediction events (prediction-only mode).
"""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field
import uuid


class AuditFieldEntry(BaseModel):
    """One field's outcome within a human-reviewed image."""
    field: str
    field_label: str
    extracted_value: Optional[str]
    application_value: str
    status_shown: str
    agent_action: Optional[Literal["verified_correct", "corrected", "found_on_label", "manual_override", "marked_fail"]] = None
    agent_provided_value: Optional[str] = None
    comparison_result: Optional[Literal["match", "mismatch"]] = None


class AuditEntry(BaseModel):
    """Per-image audit record written when an agent submits a review."""
    entry_id: str                            # Shared with PredictionLog.entry_id for the same image
    session_id: str
    image_filename: str
    model_used: str
    prompt_version: str
    fields: list[AuditFieldEntry]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AuditSubmission(BaseModel):
    """Payload sent from frontend when agent submits their review."""
    session_id: str
    image_filename: str
    model_used: str
    prompt_version: str
    log_id: Optional[str] = None            # Matches PredictionLog.entry_id when available
    fields: list[dict]                       # All result fields; non-pass ones carry agent action data


class PredictionFieldResult(BaseModel):
    """Single-field outcome within a prediction log entry."""
    field: str
    field_label: str
    extracted_value: Optional[str]           # None when field was not detected
    detected: bool


class PredictionLog(BaseModel):
    """Image-level log entry written for every prediction-only extraction."""
    entry_id: str                            # Shared with AuditEntry.entry_id for the same image
    image_filename: str
    image_hash: str                          # SHA-256 hex digest of raw image bytes
    model_used: str
    prompt_version: str
    raw_prompt: str                          # Full prompt text sent to the model
    raw_model_output: str                    # Raw text response before JSON parsing
    fields: list[PredictionFieldResult]      # All fields, detected and undetected
    cache_hit: bool = False                  # True when response came from the static cache
    timestamp: datetime = Field(default_factory=datetime.utcnow)
