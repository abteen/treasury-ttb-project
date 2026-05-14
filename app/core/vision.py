"""
Abstracted vision client.
Adding a new backend = implement VisionClient ABC and register in get_vision_client().
"""
import base64
import json
import logging
import os
from abc import ABC, abstractmethod

import anthropic

logger = logging.getLogger(__name__)


class VisionClient(ABC):
    """Abstract interface for vision-based label extraction."""

    @abstractmethod
    def extract_fields(self, image_bytes: bytes, prompt: str, media_type: str = "image/jpeg") -> dict:
        """
        Extract structured fields from a label image.

        Args:
            image_bytes: Raw image bytes
            prompt:      The extraction prompt to use
            media_type:  MIME type of the image

        Returns:
            dict of extracted field names to values (or None if not found)
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifier string recorded in results and audit logs."""
        ...


class AnthropicVisionClient(VisionClient):
    """Vision extraction via Anthropic Claude."""

    DEFAULT_MODEL = "claude-opus-4-5"
    MAX_TOKENS = 1024

    def __init__(self, model: str | None = None):
        self._model = model or os.getenv("ANTHROPIC_MODEL", self.DEFAULT_MODEL)
        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    @property
    def model_name(self) -> str:
        return self._model

    def extract_fields(self, image_bytes: bytes, prompt: str, media_type: str = "image/jpeg") -> dict:
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        message = self._client.messages.create(
            model=self._model,
            max_tokens=self.MAX_TOKENS,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        raw = message.content[0].text.strip()
        # Strip markdown fences if model wraps output despite instructions
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        return json.loads(raw)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_BACKENDS: dict[str, type[VisionClient]] = {
    "anthropic": AnthropicVisionClient,
}


def get_vision_client(backend: str | None = None, model: str | None = None) -> VisionClient:
    """
    Return a VisionClient for the configured backend.
    Reads VISION_BACKEND env var if backend not supplied explicitly.
    """
    key = (backend or os.getenv("VISION_BACKEND", "anthropic")).lower()
    cls = _BACKENDS.get(key)
    if cls is None:
        raise ValueError(f"Unknown vision backend '{key}'. Available: {list(_BACKENDS.keys())}")
    return cls(model=model)
