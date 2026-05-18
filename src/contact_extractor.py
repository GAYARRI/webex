from __future__ import annotations

import re

from .text_utils import compact_text


PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+34\s*)?(?:\d[\s.-]?){9}(?!\d)"
)

ADDRESS_MARKERS = [
    "avenida",
    "avda",
    "calle",
    "carretera",
    "c/",
    "paseo",
    "plaza",
]


def extract_contact_info(text: str) -> dict[str, str]:
    return {
        "address": extract_address(text),
        "phone": extract_phone(text),
    }


def extract_phone(text: str) -> str:
    for match in PHONE_PATTERN.finditer(text or ""):
        phone = compact_text(match.group(0)).strip(" .,:;")
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 9 or (len(digits) == 11 and digits.startswith("34")):
            return phone
    return ""


def extract_address(text: str) -> str:
    text = compact_text(text)
    if not text:
        return ""
    sentences = re.split(r"(?<=[.;])\s+|\s{2,}", text)
    for sentence in sentences:
        lowered = sentence.casefold()
        if any(marker in lowered for marker in ADDRESS_MARKERS):
            address = _trim_address(sentence)
            if address:
                return address
    return ""


def _trim_address(sentence: str) -> str:
    sentence = compact_text(sentence)
    match = re.search(
        r"((?:C/|calle|plaza|avenida|avda\.?|paseo|carretera)\s+[^.;]{3,120})",
        sentence,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return compact_text(match.group(1).strip(" ,.;"))
