"""
Static response cache for test images.

Images whose filenames start with TEST_PREFIX bypass the live API entirely.
The cache is keyed on (base_filename, model, prompt_version) and backed by
plain-text .txt files stored in cached_responses/ and committed to the repo.

File naming convention (all three parts joined by double underscores):
    cached_responses/{base_filename}__{model}__{prompt_version}.txt

where base_filename is the image filename with TEST_PREFIX stripped.

Example:
    Image uploaded as:  [TESTIMAGE]-bourbon_label.jpg
    Model:              claude-opus-4-5
    Prompt version:     v1
    Cache file:         cached_responses/bourbon_label.jpg__claude-opus-4-5__v1.txt
"""
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

TEST_PREFIX = "[TESTIMAGE]-"
CACHE_DIR = Path(__file__).parent / "cached_responses"


def _safe(s: str) -> str:
    """Replace filesystem path separators so parts cannot escape the cache dir."""
    return re.sub(r"[/\\]", "_", s)


def get_cached_extract(
    filename: str,
    model: str,
    prompt_version: str,
) -> tuple[dict, str] | None:
    """
    Return (parsed_fields, raw_text) if a cache entry exists for this
    (filename, model, prompt_version) triple, otherwise return None.

    The raw_text is the file contents as-is — equivalent to what the model
    would have returned — and is recorded verbatim in prediction logs.
    """
    if not filename.startswith(TEST_PREFIX):
        return None

    base = filename[len(TEST_PREFIX):]
    cache_file = CACHE_DIR / f"{_safe(base)}__{_safe(model)}__{_safe(prompt_version)}.txt"

    if not cache_file.exists():
        logger.warning(
            "Cache miss for test image '%s' (model=%s, version=%s) — expected %s",
            filename, model, prompt_version, cache_file.name,
        )
        return None

    raw = cache_file.read_text(encoding="utf-8").strip()
    text = raw
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    logger.info(
        "Cache hit for '%s' (model=%s, version=%s)",
        filename, model, prompt_version,
    )
    return json.loads(text), raw


def save_cached_extract(
    filename: str,
    model: str,
    prompt_version: str,
    raw_output: str,
) -> None:
    """
    Persist a live API response to the cache directory for future reuse.
    No-ops silently for filenames that don't start with TEST_PREFIX.
    """
    if not filename.startswith(TEST_PREFIX):
        return

    base = filename[len(TEST_PREFIX):]
    cache_file = CACHE_DIR / f"{_safe(base)}__{_safe(model)}__{_safe(prompt_version)}.txt"

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(raw_output, encoding="utf-8")
        logger.info(
            "Wrote cache entry for '%s' → %s",
            filename, cache_file.name,
        )
    except Exception as exc:
        logger.error("Failed to write cache file %s: %s", cache_file.name, exc)
