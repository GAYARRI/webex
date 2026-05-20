from __future__ import annotations

from urllib.parse import urljoin

import requests
import urllib3
from requests.exceptions import RequestException, SSLError
from bs4 import BeautifulSoup

from .block_extractor import extract_blocks
from .geo import extract_geo_candidates, extract_structured_data
from .image_filters import is_noise_image
from .models import PageExtraction
from .text_utils import compact_text


DEFAULT_TIMEOUT = 20


def ensure_url(url: str) -> str:
    if url.startswith(("http://", "https://")):
        return url
    return f"https://{url}"


def fetch_html(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str, list[str]]:
    resolved_url = ensure_url(url)
    headers = {"User-Agent": "ExtraccionWebSemantica/0.1"}
    warnings: list[str] = []

    # HEAD probe: detect broken links and non-HTML content without downloading the body.
    # 405/501 means the server does not support HEAD — fall through to GET.
    # SSL or network errors on HEAD are also ignored so the GET path can handle them.
    try:
        probe = requests.head(resolved_url, timeout=timeout, headers=headers, allow_redirects=True)
        if probe.status_code not in (405, 501):
            probe.raise_for_status()
            content_type = probe.headers.get("Content-Type", "")
            if content_type and not content_type.lower().startswith("text/html"):
                raise ValueError(
                    f"Contenido no-HTML omitido: {content_type.split(';')[0].strip()}"
                )
    except (ValueError, requests.HTTPError):
        raise
    except Exception:
        pass  # HEAD no disponible o error de red — intentar GET

    try:
        response = requests.get(resolved_url, timeout=timeout, headers=headers)
    except SSLError:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(
            resolved_url,
            timeout=timeout,
            headers=headers,
            verify=False,
        )
        warnings.append("Descarga realizada sin verificacion SSL tras fallo de certificado.")
    response.raise_for_status()
    return response.url, response.text, warnings


def parse_html(url: str, html: str, errors: list[str] | None = None) -> PageExtraction:
    soup = BeautifulSoup(html, "lxml")
    structured_data = extract_structured_data(soup)
    geo_candidates = extract_geo_candidates(soup, structured_data)

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = compact_text(soup.title.get_text(" ")) if soup.title else None
    description = _meta_content(soup, "description")
    language = soup.html.get("lang") if soup.html else None
    raw_text = compact_text(soup.get_text(" "))
    main_text = _main_text(soup) or raw_text
    images = _images(url, soup)
    blocks = extract_blocks(url, soup)

    return PageExtraction(
        url=url,
        title=title or None,
        description=description or None,
        language=language or None,
        main_text=main_text,
        raw_text=raw_text,
        images=images,
        status="ok",
        structured_data=structured_data,
        geo_candidates=geo_candidates,
        blocks=blocks,
        errors=errors or [],
    )


def extract_page(url: str) -> PageExtraction:
    try:
        final_url, html, warnings = fetch_html(url)
        return parse_html(final_url, html, errors=warnings)
    except RequestException as exc:
        message = "No se pudo descargar la pagina."
        response = getattr(exc, "response", None)
        if response is not None:
            message = f"No se pudo descargar la pagina. HTTP {response.status_code}."
        return PageExtraction(
            url=ensure_url(url),
            title=None,
            description=None,
            language=None,
            main_text="",
            raw_text="",
            images=[],
            status="error",
            errors=[message],
        )
    except Exception as exc:
        return PageExtraction(
            url=ensure_url(url),
            title=None,
            description=None,
            language=None,
            main_text="",
            raw_text="",
            images=[],
            status="error",
            errors=[f"No se pudo procesar la pagina: {exc}"],
        )


def _meta_content(soup: BeautifulSoup, name: str) -> str | None:
    selectors = [
        {"name": name},
        {"property": f"og:{name}"},
        {"name": f"twitter:{name}"},
    ]
    for selector in selectors:
        tag = soup.find("meta", attrs=selector)
        if tag and tag.get("content"):
            return compact_text(tag["content"])
    return None


def _main_text(soup: BeautifulSoup) -> str:
    candidates = soup.find_all(["main", "article"])
    if not candidates:
        return ""
    best = max(candidates, key=lambda tag: len(tag.get_text(" ")))
    return compact_text(best.get_text(" "))


def _images(url: str, soup: BeautifulSoup) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, img in enumerate(soup.find_all("img")):
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
                "source": "page",
                "index": str(index),
                "context": _image_context(img),
            }
        )
    return images[:80]


def _image_context(img) -> str:
    parts: list[str] = []
    for attr in ["title", "aria-label"]:
        if img.get(attr):
            parts.append(str(img[attr]))

    parent = img.parent
    for _ in range(4):
        if parent is None or getattr(parent, "name", None) in {"body", "html"}:
            break
        text = compact_text(parent.get_text(" "))
        if text:
            parts.append(text[:600])
            break
        parent = parent.parent

    previous_heading = img.find_previous(["h1", "h2", "h3", "h4"])
    if previous_heading:
        parts.append(compact_text(previous_heading.get_text(" ")))

    next_heading = img.find_next(["h1", "h2", "h3", "h4"])
    if next_heading:
        parts.append(compact_text(next_heading.get_text(" ")))

    return compact_text(" ".join(parts))[:1000]


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
