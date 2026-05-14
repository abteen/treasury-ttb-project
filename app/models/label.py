"""
Pydantic models for label application data submitted by importers/producers.
"""
from typing import Optional
from pydantic import BaseModel

from app.core.constants import GOVERNMENT_WARNING_CANONICAL


class ApplicationData(BaseModel):
    filename: str
    brand_name: str
    class_type: str
    abv: str
    net_contents: str
    bottler_name: str
    bottler_address: str
    country_of_origin: Optional[str] = None
    government_warning: str = GOVERNMENT_WARNING_CANONICAL

    class Config:
        json_schema_extra = {
            "example": {
                "filename": "label_001.jpg",
                "brand_name": "OLD TOM DISTILLERY",
                "class_type": "Kentucky Straight Bourbon Whiskey",
                "abv": "45% Alc./Vol. (90 Proof)",
                "net_contents": "750 mL",
                "bottler_name": "Old Tom Distillery LLC",
                "bottler_address": "123 Barrel Lane, Louisville, KY 40201",
                "country_of_origin": None,
                "government_warning": GOVERNMENT_WARNING_CANONICAL,
            }
        }
