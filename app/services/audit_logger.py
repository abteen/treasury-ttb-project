"""
Audit logger.
Appends human review events to an append-only JSONL file.
Each line is a self-contained JSON object — easy to load into pandas for eval work.

Trade-off documented: local file storage is fine for a prototype.
Production deployment should replace this with a proper datastore.
"""
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.models.audit import AuditEntry, AuditFieldEntry, AuditSubmission, PredictionLog

logger = logging.getLogger(__name__)

AUDIT_LOG_PATH      = Path(os.getenv("AUDIT_LOG_PATH",      "logs/audit.jsonl"))
PREDICTION_LOG_PATH = Path(os.getenv("PREDICTION_LOG_PATH", "logs/predictions.jsonl"))


def _ensure_log_dir() -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREDICTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _lookup_prediction_entry_id(image_filename: str, model_used: str, prompt_version: str) -> Optional[str]:
    """Scan predictions.jsonl in reverse to find the entry_id for the most recent matching run."""
    if not PREDICTION_LOG_PATH.exists():
        return None
    with PREDICTION_LOG_PATH.open(encoding="utf-8") as f:
        lines = f.readlines()
    for line in reversed(lines):
        try:
            entry = json.loads(line)
            if (entry.get("image_filename") == image_filename
                    and entry.get("model_used") == model_used
                    and entry.get("prompt_version") == prompt_version):
                return entry.get("entry_id")
        except json.JSONDecodeError:
            continue
    return None


def log_corrections(submission: AuditSubmission) -> int:
    """
    Write a single per-image audit entry to audit.jsonl.
    Returns the number of fields that had an explicit agent action.
    """
    _ensure_log_dir()

    entry_id = (
        submission.log_id
        or _lookup_prediction_entry_id(submission.image_filename, submission.model_used, submission.prompt_version)
        or str(uuid.uuid4())
    )

    fields = []
    for f in submission.fields:
        try:
            fields.append(AuditFieldEntry(
                field=f["field"],
                field_label=f.get("field_label", f["field"]),
                extracted_value=f.get("extracted_value"),
                application_value=f.get("application_value", ""),
                status_shown=f["status_shown"],
                agent_action=f.get("agent_action"),
                agent_provided_value=f.get("agent_provided_value"),
                comparison_result=f.get("comparison_result"),
            ))
        except Exception as exc:
            logger.error("Failed to parse audit field entry for %s: %s", f.get("field"), exc)

    entry = AuditEntry(
        entry_id=entry_id,
        session_id=submission.session_id,
        image_filename=submission.image_filename,
        model_used=submission.model_used,
        prompt_version=submission.prompt_version,
        fields=fields,
        timestamp=datetime.utcnow(),
    )

    try:
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")
        actioned = sum(1 for f in fields if f.agent_action is not None)
        logger.info(
            "Wrote audit entry for %s / %s (%d total fields, %d actioned)",
            submission.session_id, submission.image_filename, len(fields), actioned,
        )
        return actioned
    except Exception as exc:
        logger.error("Failed to write audit entry for %s: %s", submission.image_filename, exc)
        return 0


def log_prediction(entry: PredictionLog) -> None:
    """
    Append one image-level prediction log entry to predictions.jsonl.
    Each line is a self-contained JSON object suitable for offline eval.
    """
    _ensure_log_dir()
    try:
        with PREDICTION_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")
        logger.info(
            "Logged prediction for %s (%d fields, hash=%s…)",
            entry.image_filename, len(entry.fields), entry.image_hash[:12],
        )
    except Exception as exc:
        logger.error("Failed to write prediction log for %s: %s", entry.image_filename, exc)
