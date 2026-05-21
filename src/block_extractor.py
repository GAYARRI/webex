from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .image_filters import is_noise_image
from .models import ContentBlock
from .text_utils import clean_content_text, compact_text


BLOCK_TAGS = ["article", "section", "main"]
CARD_SELECTORS = [
    "[class*=card]",
    "[class*=item]",
    "[class*=noticia]",
    "[class*=evento]",
    "[class*=resource]",
    "[class*=contenido]",
]


def extract_blocks(url: str, soup: BeautifulSoup, max_blocks: int = 80) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    seen_texts: set[str] = set()
    candidates = []
    for tag_name in BLOCK_TAGS:
        candidates.extend(soup.find_all(tag_name))
    for selector in CARD_SELECTORS:
        candidates.extend(soup.select(selector))

    for position, tag in enumerate(candidates):
        text = clean_content_text(tag.get_text(" "))
        if not _is_useful_block_text(text):
            continue
        text_key = text[:300]
        if text_key in seen_texts:
            continue
        seen_texts.add(text_key)
        title = _block_title(tag)
        images = _block_images(url, tag)
        block = ContentBlock(
            block_id=f"block-{len(blocks) + 1}",
            url=url,
            title=title,
            text=text[:3000],
            images=images,
            kind=getattr(tag, "name", "block") or "block",
            position=position,
        )
        blocks.append(block)
        if len(blocks) >= max_blocks:
            break

    if not blocks:
        body_text = clean_content_text(soup.get_text(" "))
        if body_text:
            blocks.append(
                ContentBlock(
                    block_id="block-1",
                    url=url,
                    title="",
                    text=body_text[:3000],
                    images=_block_images(url, soup),
                    kind="page",
                    position=0,
                )
            )
    blocks.sort(key=lambda block: (0 if block.title else 1, -len(block.images), block.position))
    for index, block in enumerate(blocks, start=1):
        block.block_id = f"block-{index}"
    return blocks


def _is_useful_block_text(text: str) -> bool:
    if len(text) < 50:
        return False
    lowered = text.casefold()
    noise_markers = ["cookies", "politica de privacidad", "aviso legal"]
    if any(marker in lowered for marker in noise_markers) and len(text) < 500:
        return False
    return True


def _block_title(tag) -> str:
    heading = tag.find(["h1", "h2", "h3", "h4"]) if hasattr(tag, "find") else None
    if heading:
        return clean_content_text(heading.get_text(" "))
    return ""


def _block_images(url: str, tag) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, img in enumerate(tag.find_all("img") if hasattr(tag, "find_all") else []):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        absolute = urljoin(url, src)
        alt = compact_text(img.get("alt", ""))
        metadata = _image_metadata(img)
        if is_noise_image(absolute, alt, metadata) or _is_small_interface_image(img):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        images.append(
            {
                "url": absolute,
                "alt": alt,
                "source": "block",
                "index": str(index),
                "context": clean_content_text(tag.get_text(" "))[:1000],
            }
        )
    return images[:20]


def _image_metadata(img) -> str:
    classes = " ".join(img.get("class", []) or [])
    attrs = [
        classes,
        str(img.get("id", "") or ""),
        str(img.get("role", "") or ""),
        str(img.get("aria-label", "") or ""),
        str(img.get("title", "") or ""),
    ]
    return compact_text(" ".join(attrs))


def _is_small_interface_image(img) -> bool:
    width = _dimension(img.get("width"))
    height = _dimension(img.get("height"))
    if width is None or height is None:
        return False
    return width <= 80 and height <= 80


def _dimension(value) -> int | None:
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    return int(digits)
