"""
Audit logger.
Appends agent correction events to an append-only JSONL file.
Each line is a self-contained JSON object — easy to load into pandas for eval work.

Trade-off documented: local file storage is fine for a prototype.
Production deployment should replace this with a proper datastore.
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from app.models.audit import AgentCorrection, AuditSubmission, PredictionLog

logger = logging.getLogger(__name__)

AUDIT_LOG_PATH      = Path(os.getenv("AUDIT_LOG_PATH",      "logs/audit.jsonl"))
PREDICTION_LOG_PATH = Path(os.getenv("PREDICTION_LOG_PATH", "logs/predictions.jsonl"))


def _ensure_log_dir() -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREDICTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_corrections(submission: AuditSubmission) -> int:
    """
    Write agent correction entries to the audit log.
    Returns the number of entries written.
    """
    _ensure_log_dir()
    written = 0

    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        for correction in submission.corrections:
            try:
                entry = AgentCorrection(
                    session_id=submission.session_id,
                    image_filename=submission.image_filename,
                    field=correction["field"],
                    extracted_value=correction.get("extracted_value"),
                    application_value=correction.get("application_value", ""),
                    status_shown=correction["status_shown"],
                    agent_action=correction["agent_action"],
                    agent_provided_value=correction.get("agent_provided_value"),
                    model_used=submission.model_used,
                    prompt_version=submission.prompt_version,
                    timestamp=datetime.utcnow(),
                )
                f.write(entry.model_dump_json() + "\n")
                written += 1
            except Exception as exc:
                logger.error("Failed to write audit entry for field %s: %s", correction.get("field"), exc)

    logger.info("Wrote %d audit entries for session %s / %s", written, submission.session_id, submission.image_filename)
    return written


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
