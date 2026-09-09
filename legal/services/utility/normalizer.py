from hazm import Normalizer
from typing import Optional

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
ENGLISH_DIGITS = "0123456789"

DIGIT_TRANSLATION = str.maketrans(
    PERSIAN_DIGITS + ARABIC_DIGITS,
    ENGLISH_DIGITS + ENGLISH_DIGITS,
)

normalizer = Normalizer()


def normalise_digits(value: str) -> str:
    if not value:
        return value
    return value.translate(DIGIT_TRANSLATION)


INVISIBLE_CHARS = {
    "\u200c",  # نیم فاصله
    "\u200d",  # اتصال نامرئی
    "\u200e",  # LRM
    "\u200f",  # RLM
    "\ufeff",  # BOM
}


def normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    for char in INVISIBLE_CHARS:
        value = value.replace(char, " ")
    value = normalizer.normalize(value)
    value = value.translate(DIGIT_TRANSLATION)
    return value.strip()
