"""
TTB regulatory constants and canonical field values.
"""

GOVERNMENT_WARNING_CANONICAL = (
    """GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."""
)

# Fields that must match exactly (case-sensitive, whitespace-normalized)
EXACT_MATCH_FIELDS = {"government_warning"}

# Fields where case-insensitive fuzzy matching produces a warning rather than fail
FUZZY_MATCH_FIELDS = {"brand_name", "class_type", "bottler_name", "bottler_address", "country_of_origin"}

# Fields where numeric normalization is applied
NUMERIC_FIELDS = {"abv", "net_contents"}

TTB_REQUIRED_FIELDS = [
    "brand_name",
    "class_type",
    "abv",
    "net_contents",
    "bottler_name",
    "bottler_address",
    "government_warning",
]

TTB_OPTIONAL_FIELDS = ["country_of_origin"]
