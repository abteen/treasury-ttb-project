"""
Pydantic models for audit log entries.

AgentCorrection / AuditSubmission — field-level human review events (verification mode).
PredictionLog                      — image-level prediction events (prediction-only mode).
"""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field
import uuid


class AgentCorrection(BaseModel):
    """A single field-level correction or verification by a compliance agent."""
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    image_filename: str
    field: str
    extracted_value: Optional[str]          # What the model extracted
    application_value: str                  # What the application claimed
    status_shown: str                       # The verdict shown to the agent
    agent_action: Literal["verified_correct", "corrected"]
    agent_provided_value: Optional[str]     # Only set when agent_action == "corrected"
    model_used: str
    prompt_version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AuditSubmission(BaseModel):
    """Payload sent from frontend when agent submits their review."""
    session_id: str
    image_filename: str
    model_used: str
    prompt_version: str
    corrections: list[dict]                 # Raw field correction entries from UI


class PredictionFieldResult(BaseModel):
    """Single-field outcome within a prediction log entry."""
    field: str
    field_label: str
    extracted_value: Optional[str]          # None when field was not detected
    detected: bool


class PredictionLog(BaseModel):
    """Image-level log entry written for every prediction-only extraction."""
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    image_filename: str
    image_hash: str                         # SHA-256 hex digest of raw image bytes
    model_used: str
    prompt_version: str
    raw_prompt: str                         # Full prompt text sent to the model
    raw_model_output: str                   # Raw text response before JSON parsing
    fields: list[PredictionFieldResult]     # All fields, detected and undetected
    cache_hit: bool = False                 # True when response came from the static cache
    timestamp: datetime = Field(default_factory=datetime.utcnow)
