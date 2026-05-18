from __future__ import annotations

import re
import unicodedata

# Liferay/CMS navigation boilerplate patterns found in listing widgets and teasers
_BOILERPLATE_RE = re.compile(
    r"\d{1,5}\s+visitas?\b"   # "1487 visitas"
    r"|\bsaber\s+m[aá]s\b"    # "Saber más"
    r"|\bir\s+a\s+\w"         # "Ir a Catedral"
    r"|\bver\s+m[aá]s\b"      # "Ver más"
    r"|\bleer\s+m[aá]s\b",    # "Leer más"
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
