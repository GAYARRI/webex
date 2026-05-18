from __future__ import annotations

import re

from .text_utils import compact_text, normalize_key


DATE_HEADING_RE = re.compile(
    r"\b\d{1,2}\s+de\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+\s+de\s+\d{4}\b"
)


def relevant_text_for_entity(entity_name: str, text: str) -> str:
    text = compact_text(text)
    if not entity_name or not text:
        return text

    dated_chunk = _matching_dated_chunk(entity_name, text)
    if dated_chunk:
        return dated_chunk
    return text


def _matching_dated_chunk(entity_name: str, text: str) -> str:
    matches = list(DATE_HEADING_RE.finditer(text))
    if len(matches) < 2:
        return ""

    name_key = normalize_key(entity_name)
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chunk = compact_text(text[start:end])
        if name_key and name_key in normalize_key(chunk):
            return chunk
    return ""
