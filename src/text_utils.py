from __future__ import annotations

import re
import unicodedata

# Liferay/CMS navigation boilerplate patterns found in listing widgets and teasers
_BOILERPLATE_RE = re.compile(
    r"\d{1,5}\s+visitas?\b"   # "1487 visitas"
    r"|\bsaber\s+m[aá]s\b"    # "Saber más"
    r"|\bir\s+a\s+\w"         # "Ir a Catedral"
    r"|\bver\s+m[aá]s\b"      # "Ver más"
    r"|\bleer\s+m[aá]s\b"     # "Leer más"
    r"|\bqu[eé]\s+ver\b",     # "Qué ver" / "Que ver" (Liferay nav label)
    re.IGNORECASE,
)


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return compact_text(text)


def is_boilerplate_text(text: str) -> bool:
    """Return True if text contains CMS/navigation boilerplate patterns."""
    return bool(_BOILERPLATE_RE.search(text or ""))


_TEXT_PREFIX_RE = re.compile(
    r"^(?:"
    r"mas lugares de interes|"
    r"m[a\u00e1]s lugares de inter[e\u00e9]s|"
    r"lugares de interes|"
    r"lugares de inter[e\u00e9]s|"
    r"curiosidades|"
    r"ficha"
    r")\b[:\s-]*",
    re.IGNORECASE,
)

_INLINE_NOISE_RE = re.compile(
    r"\b(?:mas lugares de interes|m[a\u00e1]s lugares de inter[e\u00e9]s|lugares de interes|"
    r"lugares de inter[e\u00e9]s|ver mapa|saber mas|saber m[a\u00e1]s|leer mas|leer m[a\u00e1]s|"
    r"reserva ahora|qu[e\u00e9]\s+ver)\b",
    re.IGNORECASE,
)


def clean_content_text(text: str) -> str:
    """Remove repeated CMS labels and inline actions from extracted content text."""
    cleaned = compact_text(text)
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        cleaned = _TEXT_PREFIX_RE.sub("", cleaned).strip()
    cleaned = _INLINE_NOISE_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)
    cleaned = re.sub(r"(?:\.\s*){2,}", ". ", cleaned)
    return compact_text(cleaned)
