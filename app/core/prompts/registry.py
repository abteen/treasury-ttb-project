"""
Prompt version registry.
Adding a new prompt version = add a new file and register it here.
The version string is recorded in every VerificationResult and AuditLog entry
so results are always reproducible and comparable across versions.
"""
import os
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

PROMPT_REGISTRY: dict[str, dict[str, Path]] = {
    "extract": {
        "v1": PROMPTS_DIR / "v1_extract.txt",
    },
}

# "latest" resolves to the highest version key (lexicographic, assumes vN naming)
def _resolve_version(name: str, version: str) -> str:
    available = PROMPT_REGISTRY.get(name, {})
    if not available:
        raise ValueError(f"No prompts registered for '{name}'")
    if version == "latest":
        return sorted(available.keys())[-1]
    if version not in available:
        raise ValueError(f"Prompt '{name}' version '{version}' not found. Available: {list(available.keys())}")
    return version


def get_prompt(name: str, version: str = "latest") -> tuple[str, str]:
    """
    Load a prompt by name and version.
    Returns (prompt_text, resolved_version) so callers can record the exact version used.
    """
    resolved = _resolve_version(name, version)
    path = PROMPT_REGISTRY[name][resolved]
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip(), resolved


def list_prompts() -> dict[str, list[str]]:
    """Return all registered prompt names and their available versions."""
    return {name: list(versions.keys()) for name, versions in PROMPT_REGISTRY.items()}
