"""
CSV parser for bulk application data uploads.
The 'filename' column is the join key between CSV rows and uploaded images.
"""
import csv
import io
import logging
from typing import NamedTuple

from app.core.constants import GOVERNMENT_WARNING_CANONICAL
from app.models.label import ApplicationData

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {
    "filename",
    "brand_name",
    "class_type",
    "abv",
    "net_contents",
    "bottler_name",
    "bottler_address",
}

OPTIONAL_COLUMNS = {"country_of_origin", "government_warning"}


class ParseResult(NamedTuple):
    applications: list[ApplicationData]
    errors: list[str]


def parse_csv(csv_bytes: bytes) -> ParseResult:
    """
    Parse a CSV file of application data.
    Returns (list of valid ApplicationData, list of error messages).
    """
    errors: list[str] = []
    applications: list[ApplicationData] = []

    try:
        text = csv_bytes.decode("utf-8-sig")  # handle BOM from Excel exports
    except UnicodeDecodeError:
        text = csv_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        return ParseResult([], ["CSV file appears to be empty."])

    actual_columns = {c.strip().lower() for c in reader.fieldnames}
    missing = REQUIRED_COLUMNS - actual_columns
    if missing:
        return ParseResult([], [f"CSV is missing required columns: {sorted(missing)}"])

    for i, row in enumerate(reader, start=2):  # row 1 = header
        # Normalise keys
        row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items()}

        filename = row.get("filename", "")
        if not filename:
            errors.append(f"Row {i}: missing filename, skipping.")
            continue

        # Validate required fields
        row_errors = []
        for col in REQUIRED_COLUMNS - {"filename"}:
            if not row.get(col):
                row_errors.append(col)

        if row_errors:
            errors.append(f"Row {i} ({filename}): missing required fields: {row_errors}")
            continue

        # Use canonical government warning if not supplied
        gov_warning = row.get("government_warning") or GOVERNMENT_WARNING_CANONICAL

        try:
            app = ApplicationData(
                filename=filename,
                brand_name=row["brand_name"],
                class_type=row["class_type"],
                abv=row["abv"],
                net_contents=row["net_contents"],
                bottler_name=row["bottler_name"],
                bottler_address=row["bottler_address"],
                country_of_origin=row.get("country_of_origin") or None,
                government_warning=gov_warning,
            )
            applications.append(app)
        except Exception as exc:
            errors.append(f"Row {i} ({filename}): validation error — {exc}")

    return ParseResult(applications, errors)


def validate_image_csv_pairing(
    image_filenames: list[str],
    applications: list[ApplicationData],
) -> list[str]:
    """
    Check that every uploaded image has a matching CSV row and vice versa.
    Returns list of mismatch error messages (empty = all good).
    """
    image_set = set(image_filenames)
    csv_set = {app.filename for app in applications}

    errors = []
    for img in sorted(image_set - csv_set):
        errors.append(f"Image '{img}' has no matching row in CSV.")
    for row in sorted(csv_set - image_set):
        errors.append(f"CSV row for '{row}' has no matching uploaded image.")

    return errors
