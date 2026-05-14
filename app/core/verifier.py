"""
Verification orchestrator.
Compares vision-extracted label fields against application data
and produces structured per-field verdicts.
"""
import hashlib
import logging
import re
import time
import unicodedata
from datetime import datetime

from app.core.constants import (
    EXACT_MATCH_FIELDS,
    FUZZY_MATCH_FIELDS,
    NUMERIC_FIELDS,
    TTB_REQUIRED_FIELDS,
    TTB_OPTIONAL_FIELDS,
    GOVERNMENT_WARNING_CANONICAL,
)
from app.core.prompts.registry import get_prompt
from app.core.response_cache import get_cached_extract, save_cached_extract
from app.core.vision import VisionClient
from app.models.audit import PredictionFieldResult, PredictionLog
from app.models.label import ApplicationData
from app.models.result import BatchVerificationResponse, FieldVerdict, VerificationResult
from app.services.audit_logger import log_prediction

logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "brand_name": "Brand Name",
    "class_type": "Class / Type",
    "abv": "Alcohol Content (ABV)",
    "net_contents": "Net Contents",
    "bottler_name": "Bottler / Producer Name",
    "bottler_address": "Bottler / Producer Address",
    "country_of_origin": "Country of Origin",
    "government_warning": "Government Warning Statement",
}


# ---------------------------------------------------------------------------
# Text normalisation helpers
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """Collapse whitespace and normalise unicode."""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalise_numeric(text: str) -> str:
    """Strip spaces around punctuation and normalise decimals for numeric fields."""
    text = _normalise(text)
    text = re.sub(r"\s*%\s*", "%", text)
    text = re.sub(r"\s*\.\s*", ".", text)
    return text.lower()


def _normalise_fuzzy(text: str) -> str:
    return _normalise(text).lower()


# ---------------------------------------------------------------------------
# Per-field comparison
# ---------------------------------------------------------------------------

def _compare_field(
    field: str,
    extracted: str | None,
    application: str | None,
) -> FieldVerdict:
    label = FIELD_LABELS.get(field, field.replace("_", " ").title())
    app_val = application or ""

    if extracted is None:
        status = "fail" if field in TTB_REQUIRED_FIELDS else "warning"
        return FieldVerdict(
            field=field,
            field_label=label,
            extracted_value=None,
            application_value=app_val,
            status=status,
            note="Field not detected on label." if field in TTB_REQUIRED_FIELDS else "Optional field not found.",
        )

    ext_val = extracted.strip()

    # --- Government warning: canonical + application exact match ---
    if field == "government_warning":
        ext_norm = _normalise(ext_val)
        app_norm = _normalise(app_val)
        canonical_norm = _normalise(GOVERNMENT_WARNING_CANONICAL)

        if ext_norm == app_norm == canonical_norm:
            return FieldVerdict(field=field, field_label=label, extracted_value=ext_val, application_value=app_val, status="pass")

        if ext_norm == app_norm:
            # Matches application but not canonical — warn that canonical text differs
            return FieldVerdict(
                field=field,
                field_label=label,
                extracted_value=ext_val,
                application_value=app_val,
                status="warning",
                note="Matches application but differs from TTB canonical warning text.",
            )

        if ext_norm == canonical_norm:
            # Matches canonical but not application — application may have a typo
            return FieldVerdict(
                field=field,
                field_label=label,
                extracted_value=ext_val,
                application_value=app_val,
                status="warning",
                note="Matches TTB canonical text but differs from application value.",
            )

        return FieldVerdict(
            field=field,
            field_label=label,
            extracted_value=ext_val,
            application_value=app_val,
            status="fail",
            note="Does not match application value or TTB canonical warning text.",
        )

    # --- Exact match fields ---
    if field in EXACT_MATCH_FIELDS:
        if _normalise(ext_val) == _normalise(app_val):
            return FieldVerdict(field=field, field_label=label, extracted_value=ext_val, application_value=app_val, status="pass")
        return FieldVerdict(
            field=field, field_label=label, extracted_value=ext_val, application_value=app_val,
            status="fail", note="Exact match required; values differ.",
        )

    # --- Numeric fields ---
    if field in NUMERIC_FIELDS:
        if _normalise_numeric(ext_val) == _normalise_numeric(app_val):
            return FieldVerdict(field=field, field_label=label, extracted_value=ext_val, application_value=app_val, status="pass")
        # Check if only formatting differs (e.g. "45 %" vs "45%")
        digits_ext = re.sub(r"[^\d.]", "", ext_val)
        digits_app = re.sub(r"[^\d.]", "", app_val)
        if digits_ext and digits_ext == digits_app:
            return FieldVerdict(
                field=field, field_label=label, extracted_value=ext_val, application_value=app_val,
                status="warning", note="Numeric values match but formatting differs.",
            )
        return FieldVerdict(
            field=field, field_label=label, extracted_value=ext_val, application_value=app_val,
            status="fail", note="Numeric values do not match.",
        )

    # --- Fuzzy match fields ---
    if _normalise(ext_val) == _normalise(app_val):
        return FieldVerdict(field=field, field_label=label, extracted_value=ext_val, application_value=app_val, status="pass")

    if _normalise_fuzzy(ext_val) == _normalise_fuzzy(app_val):
        return FieldVerdict(
            field=field, field_label=label, extracted_value=ext_val, application_value=app_val,
            status="warning", note="Values match when case is ignored — verify capitalisation.",
        )

    # Partial containment heuristic
    if _normalise_fuzzy(ext_val) in _normalise_fuzzy(app_val) or _normalise_fuzzy(app_val) in _normalise_fuzzy(ext_val):
        return FieldVerdict(
            field=field, field_label=label, extracted_value=ext_val, application_value=app_val,
            status="warning", note="Partial match — one value appears to contain the other.",
        )

    return FieldVerdict(
        field=field, field_label=label, extracted_value=ext_val, application_value=app_val,
        status="fail", note="Values do not match.",
    )


# ---------------------------------------------------------------------------
# Overall status rollup
# ---------------------------------------------------------------------------

def _rollup_status(verdicts: list[FieldVerdict]) -> str:
    statuses = {v.status for v in verdicts}
    if "fail" in statuses:
        return "fail"
    if "warning" in statuses:
        return "warning"
    return "pass"


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def verify_label(
    image_bytes: bytes,
    application: ApplicationData,
    client: VisionClient,
    media_type: str = "image/jpeg",
    prompt_version: str = "latest",
) -> VerificationResult:
    """
    Run extraction + verification for a single label image.
    """
    t_start = time.perf_counter()
    prompt_text, resolved_version = get_prompt("extract", prompt_version)

    cached = get_cached_extract(application.filename, client.model_name, resolved_version)
    if cached is not None:
        extracted, _raw = cached
        cache_hit = True
    else:
        try:
            extracted, _raw = client.extract_fields(image_bytes, prompt_text, media_type)
        except Exception as exc:
            logger.exception("Vision extraction failed for %s", application.filename)
            return VerificationResult(
                image_filename=application.filename,
                overall_status="fail",
                fields=[],
                model_used=client.model_name,
                prompt_version=resolved_version,
                timestamp=datetime.utcnow(),
                error=f"Extraction failed: {exc}",
                processing_time_ms=(time.perf_counter() - t_start) * 1000,
            )
        cache_hit = False
        save_cached_extract(application.filename, client.model_name, resolved_version, _raw)

    all_fields = TTB_REQUIRED_FIELDS + [f for f in TTB_OPTIONAL_FIELDS if getattr(application, f, None)]
    app_dict = application.model_dump()

    verdicts = [
        _compare_field(field, extracted.get(field), app_dict.get(field))
        for field in all_fields
    ]

    return VerificationResult(
        image_filename=application.filename,
        overall_status=_rollup_status(verdicts),
        fields=verdicts,
        model_used=client.model_name,
        prompt_version=resolved_version,
        timestamp=datetime.utcnow(),
        cache_hit=cache_hit,
        processing_time_ms=(time.perf_counter() - t_start) * 1000,
    )


def predict_label(
    image_bytes: bytes,
    filename: str,
    client: VisionClient,
    media_type: str = "image/jpeg",
    prompt_version: str = "latest",
) -> VerificationResult:
    """Extract fields from a label image without comparing against application data."""
    t_start = time.perf_counter()
    prompt_text, resolved_version = get_prompt("extract", prompt_version)

    image_hash = hashlib.sha256(image_bytes).hexdigest()

    cached = get_cached_extract(filename, client.model_name, resolved_version)
    if cached is not None:
        extracted, raw_output = cached
        cache_hit = True
    else:
        try:
            extracted, raw_output = client.extract_fields(image_bytes, prompt_text, media_type)
        except Exception as exc:
            logger.exception("Vision extraction failed for %s", filename)
            elapsed_ms = (time.perf_counter() - t_start) * 1000
            log_prediction(PredictionLog(
                image_filename=filename,
                image_hash=image_hash,
                model_used=client.model_name,
                prompt_version=resolved_version,
                raw_prompt=prompt_text,
                raw_model_output=str(exc),
                fields=[],
                cache_hit=False,
            ))
            return VerificationResult(
                image_filename=filename,
                overall_status="fail",
                fields=[],
                model_used=client.model_name,
                prompt_version=resolved_version,
                timestamp=datetime.utcnow(),
                error=f"Extraction failed: {exc}",
                prediction_only=True,
                cache_hit=False,
                processing_time_ms=elapsed_ms,
            )
        cache_hit = False
        save_cached_extract(filename, client.model_name, resolved_version, raw_output)

    verdicts = []
    for field in TTB_REQUIRED_FIELDS:
        label = FIELD_LABELS.get(field, field.replace("_", " ").title())
        val = extracted.get(field)
        if val is not None:
            verdicts.append(FieldVerdict(field=field, field_label=label,
                                         extracted_value=val.strip(), application_value="",
                                         status="pass"))
        else:
            verdicts.append(FieldVerdict(field=field, field_label=label,
                                         extracted_value=None, application_value="",
                                         status="warning", note="Field not detected on label."))

    for field in TTB_OPTIONAL_FIELDS:
        label = FIELD_LABELS.get(field, field.replace("_", " ").title())
        val = extracted.get(field)
        if val is not None:
            verdicts.append(FieldVerdict(field=field, field_label=label,
                                         extracted_value=val.strip(), application_value="",
                                         status="pass"))

    overall = "warning" if any(v.status == "warning" for v in verdicts) else "pass"

    log_prediction(PredictionLog(
        image_filename=filename,
        image_hash=image_hash,
        model_used=client.model_name,
        prompt_version=resolved_version,
        raw_prompt=prompt_text,
        raw_model_output=raw_output,
        fields=[
            PredictionFieldResult(
                field=v.field,
                field_label=v.field_label,
                extracted_value=v.extracted_value,
                detected=v.extracted_value is not None,
            )
            for v in verdicts
        ],
        cache_hit=cache_hit,
    ))

    return VerificationResult(
        image_filename=filename,
        overall_status=overall,
        fields=verdicts,
        model_used=client.model_name,
        prompt_version=resolved_version,
        timestamp=datetime.utcnow(),
        prediction_only=True,
        cache_hit=cache_hit,
        processing_time_ms=(time.perf_counter() - t_start) * 1000,
    )


async def predict_batch(
    items: list[tuple[bytes, str, str]],  # (image_bytes, filename, media_type)
    client: VisionClient,
    prompt_version: str = "latest",
) -> BatchVerificationResponse:
    """Extract fields for a batch of label images without comparison."""
    t_start = time.perf_counter()
    results = []
    for image_bytes, filename, media_type in items:
        result = predict_label(image_bytes, filename, client, media_type, prompt_version)
        results.append(result)

    passed   = sum(1 for r in results if r.overall_status == "pass")
    warnings = sum(1 for r in results if r.overall_status == "warning")
    failed   = sum(1 for r in results if r.overall_status == "fail")
    errors   = sum(1 for r in results if r.error is not None)

    return BatchVerificationResponse(
        results=results, total=len(results),
        passed=passed, warnings=warnings, failed=failed, errors=errors,
        total_time_ms=(time.perf_counter() - t_start) * 1000,
    )


async def verify_batch(
    items: list[tuple[bytes, ApplicationData, str]],  # (image_bytes, application, media_type)
    client: VisionClient,
    prompt_version: str = "latest",
) -> BatchVerificationResponse:
    """
    Verify a batch of labels. Runs sequentially to respect API rate limits
    while keeping the interface async-compatible for FastAPI.
    """
    t_start = time.perf_counter()
    results = []
    for image_bytes, application, media_type in items:
        result = verify_label(image_bytes, application, client, media_type, prompt_version)
        results.append(result)

    passed = sum(1 for r in results if r.overall_status == "pass")
    warnings = sum(1 for r in results if r.overall_status == "warning")
    failed = sum(1 for r in results if r.overall_status == "fail")
    errors = sum(1 for r in results if r.error is not None)

    return BatchVerificationResponse(
        results=results,
        total=len(results),
        passed=passed,
        warnings=warnings,
        failed=failed,
        errors=errors,
        total_time_ms=(time.perf_counter() - t_start) * 1000,
    )
