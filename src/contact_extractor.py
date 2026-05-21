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

ADDRESS_STOP_RE = re.compile(
    r"\b(?:ver mapa|horarios?|fecha|hora|precio|idiomas?|de lunes|lunes|martes|"
    r"miercoles|mi\u00e9rcoles|jueves|viernes|sabado|s\u00e1bado|domingo|actividad|"
    r"informacion|informaci\u00f3n|reserva|entrada|gratuito)\b",
    re.IGNORECASE,
)

NARRATIVE_ADDRESS_RE = re.compile(
    r"\b(?:se llena|se encuentran?|sirven?|disfrutar|recorrido|actividad|"
    r"concierto|casetas?|escenario|temporada|prevision|previsi\u00f3n)\b",
    re.IGNORECASE,
)

MAX_ADDRESS_WORDS = 14
MAX_ADDRESS_LENGTH = 90


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
    address = compact_text(match.group(1).strip(" ,.;"))
    address = ADDRESS_STOP_RE.split(address, maxsplit=1)[0]
    address = compact_text(address.strip(" ,.;:-"))
    if not _is_plausible_address(address):
        return ""
    return address


def _is_plausible_address(address: str) -> bool:
    if not address:
        return False
    if len(address) > MAX_ADDRESS_LENGTH:
        return False
    if len(address.split()) > MAX_ADDRESS_WORDS:
        return False
    if NARRATIVE_ADDRESS_RE.search(address):
        return False
    lowered = address.casefold()
    if lowered in {"calle", "plaza", "paseo", "avenida", "carretera", "c/"}:
        return False
    return True
