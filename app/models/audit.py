"""
Pydantic models for agent correction audit log entries.
These are appended to audit.jsonl for future benchmark/eval work.
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
