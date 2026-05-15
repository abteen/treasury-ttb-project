"""
API routes.
"""
import io
import logging
import mimetypes
import uuid
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from app.core.constants import GOVERNMENT_WARNING_CANONICAL
from app.core.verifier import predict_batch, predict_label, verify_batch, verify_label
from app.core.vision import get_vision_client
from app.core.prompts.registry import list_prompts
from app.models.audit import AuditSubmission
from app.models.label import ApplicationData
from app.services.audit_logger import log_corrections
from app.services.csv_parser import parse_csv, validate_image_csv_pairing

logger = logging.getLogger(__name__)
router = APIRouter()


def _guess_media_type(filename: str) -> str:
    mt, _ = mimetypes.guess_type(filename)
    if mt and mt.startswith("image/"):
        return mt
    return "image/jpeg"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Prompts (debug / admin)
# ---------------------------------------------------------------------------

@router.get("/prompts")
async def get_prompts():
    return list_prompts()


# ---------------------------------------------------------------------------
# Constants exposed to frontend
# ---------------------------------------------------------------------------

@router.get("/constants")
async def get_constants():
    return {"government_warning_canonical": GOVERNMENT_WARNING_CANONICAL}


# ---------------------------------------------------------------------------
# Single label verification
# ---------------------------------------------------------------------------

@router.post("/verify/single")
async def verify_single(
    image: Annotated[UploadFile, File(description="Label image")],
    brand_name: Annotated[str, Form()],
    class_type: Annotated[str, Form()],
    abv: Annotated[str, Form()],
    net_contents: Annotated[str, Form()],
    bottler_name: Annotated[str, Form()],
    bottler_address: Annotated[str, Form()],
    country_of_origin: Annotated[str | None, Form()] = None,
    government_warning: Annotated[str, Form()] = GOVERNMENT_WARNING_CANONICAL,
    prompt_version: Annotated[str, Form()] = "latest",
    model: Annotated[str | None, Form()] = None,
):
    image_bytes = await image.read()
    media_type = _guess_media_type(image.filename or "label.jpg")

    application = ApplicationData(
        filename=image.filename or "label.jpg",
        brand_name=brand_name,
        class_type=class_type,
        abv=abv,
        net_contents=net_contents,
        bottler_name=bottler_name,
        bottler_address=bottler_address,
        country_of_origin=country_of_origin or None,
        government_warning=government_warning,
    )

    client = get_vision_client(model=model or None)
    result = verify_label(image_bytes, application, client, media_type, prompt_version)
    return result


# ---------------------------------------------------------------------------
# Batch label verification
# ---------------------------------------------------------------------------

@router.post("/verify/batch")
async def verify_batch_endpoint(
    images: Annotated[list[UploadFile], File(description="Label images")],
    csv_file: Annotated[UploadFile, File(description="Application data CSV")],
    prompt_version: Annotated[str, Form()] = "latest",
    model: Annotated[str | None, Form()] = None,
):
    csv_bytes = await csv_file.read()
    parse_result = parse_csv(csv_bytes)

    if not parse_result.applications and parse_result.errors:
        raise HTTPException(status_code=422, detail={"csv_errors": parse_result.errors})

    image_filenames = [img.filename or f"image_{i}" for i, img in enumerate(images)]
    pairing_errors = validate_image_csv_pairing(image_filenames, parse_result.applications)

    if pairing_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "pairing_errors": pairing_errors,
                "csv_errors": parse_result.errors,
            },
        )

    # Build lookup: filename -> ApplicationData
    app_lookup = {app.filename: app for app in parse_result.applications}

    items = []
    for upload in images:
        fname = upload.filename or "unknown.jpg"
        app = app_lookup[fname]
        image_bytes = await upload.read()
        media_type = _guess_media_type(fname)
        items.append((image_bytes, app, media_type))

    client = get_vision_client(model=model or None)
    batch_response = await verify_batch(items, client, prompt_version)

    # Include any CSV parse warnings in the response
    response_data = batch_response.model_dump(mode="json")
    if parse_result.errors:
        response_data["csv_warnings"] = parse_result.errors

    return JSONResponse(content=response_data)


# ---------------------------------------------------------------------------
# Prediction-only endpoints (extract fields, no application data required)
# ---------------------------------------------------------------------------

@router.post("/predict/single")
async def predict_single(
    image: Annotated[UploadFile, File(description="Label image")],
    prompt_version: Annotated[str, Form()] = "latest",
    model: Annotated[str | None, Form()] = None,
):
    image_bytes = await image.read()
    media_type = _guess_media_type(image.filename or "label.jpg")
    filename = image.filename or "label.jpg"
    client = get_vision_client(model=model or None)
    result = predict_label(image_bytes, filename, client, media_type, prompt_version)
    return result


@router.post("/predict/batch")
async def predict_batch_endpoint(
    images: Annotated[list[UploadFile], File(description="Label images")],
    prompt_version: Annotated[str, Form()] = "latest",
    model: Annotated[str | None, Form()] = None,
):
    client = get_vision_client(model=model or None)
    items = []
    for upload in images:
        fname = upload.filename or "unknown.jpg"
        image_bytes = await upload.read()
        media_type = _guess_media_type(fname)
        items.append((image_bytes, fname, media_type))
    batch_response = await predict_batch(items, client, prompt_version)
    return JSONResponse(content=batch_response.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Examples download
# ---------------------------------------------------------------------------

_EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"

@router.get("/examples/download")
async def download_examples():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(_EXAMPLES_DIR.iterdir()):
            if path.is_file():
                zf.write(path, path.name)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="examples.zip"'},
    )


# ---------------------------------------------------------------------------
# Audit log submission
# ---------------------------------------------------------------------------

@router.post("/audit")
async def submit_audit(submission: AuditSubmission):
    written = log_corrections(submission)
    return {"written": written, "session_id": submission.session_id}
