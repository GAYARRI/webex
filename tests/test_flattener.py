from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.flattener import (
    _build_summary_no_ai,
    _collect_all_images,
    _collect_texts,
    _dedup_images,
    filter_broken_images,
    flatten_entity,
    flatten_entities,
)


def _ok_checker(url: str) -> bool:
    # "ok.com" is valid; "broken.com" and "error.com" are not
    # NOTE: cannot use "ok" in url because "broken" contains the substring "ok"
    return "ok.com" in url


def _all_ok(_url: str) -> bool:
    return True


# ---------------------------------------------------------------------------
# _collect_texts
# ---------------------------------------------------------------------------

def test_collect_texts_deduplicates_identical():
    entity = {
        "longDescription": "Texto largo.",
        "description": "Texto largo.",
        "shortDescription": "",
        "sourceText": "",
    }
    assert _collect_texts(entity) == ["Texto largo."]


def test_collect_texts_drops_subsets():
    entity = {
        "longDescription": "Texto largo con más detalle.",
        "description": "Texto largo",
        "shortDescription": "",
        "sourceText": "",
    }
    result = _collect_texts(entity)
    assert len(result) == 1
    assert "más detalle" in result[0]


def test_collect_texts_keeps_non_overlapping():
    entity = {
        "longDescription": "Descripción extensa del castillo.",
        "description": "Información sobre el horario de visitas.",
        "shortDescription": "",
        "sourceText": "",
    }
    result = _collect_texts(entity)
    assert len(result) == 2


def test_collect_texts_skips_empty():
    entity = {
        "longDescription": "",
        "description": "Solo esto.",
        "shortDescription": "",
        "sourceText": "",
    }
    assert _collect_texts(entity) == ["Solo esto."]


# ---------------------------------------------------------------------------
# _build_summary_no_ai
# ---------------------------------------------------------------------------

def test_build_summary_no_ai_returns_longest():
    entity = {
        "longDescription": "Este es el texto más largo y detallado sobre el lugar.",
        "description": "Texto corto.",
        "shortDescription": "",
        "sourceText": "",
    }
    summary = _build_summary_no_ai(entity)
    assert "más largo" in summary


def test_build_summary_no_ai_empty_entity():
    entity = {"longDescription": "", "description": "", "shortDescription": "", "sourceText": ""}
    assert _build_summary_no_ai(entity) == ""


# ---------------------------------------------------------------------------
# _dedup_images
# ---------------------------------------------------------------------------

def test_dedup_images_removes_duplicates():
    images = ["http://a.com/1.jpg", "http://a.com/2.jpg", "http://a.com/1.jpg"]
    assert _dedup_images(images) == ["http://a.com/1.jpg", "http://a.com/2.jpg"]


def test_dedup_images_filters_empty():
    assert _dedup_images(["", "http://a.com/1.jpg", ""]) == ["http://a.com/1.jpg"]


# ---------------------------------------------------------------------------
# filter_broken_images
# ---------------------------------------------------------------------------

def test_filter_broken_images_keeps_valid():
    with patch("src.flattener._check_image_url", side_effect=_ok_checker):
        result = filter_broken_images(
            ["http://ok.com/img.jpg", "http://broken.com/img.jpg"], quiet=True
        )
    assert result == ["http://ok.com/img.jpg"]


def test_filter_broken_images_removes_connection_errors():
    with patch("src.flattener._check_image_url", side_effect=_ok_checker):
        result = filter_broken_images(
            ["http://ok.com/img.jpg", "http://fail.com/img.jpg"], quiet=True
        )
    assert result == ["http://ok.com/img.jpg"]


def test_filter_broken_images_deduplicates():
    with patch("src.flattener._check_image_url", side_effect=_all_ok):
        result = filter_broken_images(
            ["http://ok.com/img.jpg", "http://ok.com/img.jpg"], quiet=True
        )
    assert result == ["http://ok.com/img.jpg"]


def test_filter_broken_images_empty_input():
    assert filter_broken_images([], quiet=True) == []


# ---------------------------------------------------------------------------
# flatten_entity
# ---------------------------------------------------------------------------

def _make_entity(**kwargs) -> dict:
    base = {
        "name": "Catedral de Burgos",
        "type": "Catedral",
        "types": ["Catedral"],
        "shortDescription": "Una catedral gótica.",
        "longDescription": "La Catedral de Burgos es una obra maestra del gótico español.",
        "description": "Patrimonio de la Humanidad desde 1984.",
        "sourceText": "Fuente original del texto.",
        "images": ["http://ok.com/cat.jpg", "http://broken.com/cat.jpg"],
        "coordinates": {"lat": 42.34, "lng": -3.70},
    }
    base.update(kwargs)
    return base


def test_flatten_entity_adds_summary_no_ai():
    with patch("src.flattener._check_image_url", side_effect=_ok_checker):
        entity = _make_entity()
        result = flatten_entity(entity, use_ai=False, quiet=True)
    assert "summary" in result
    assert result["summary"]
    # Original fields preserved
    assert "shortDescription" in result
    assert "longDescription" in result


def test_flatten_entity_filters_images():
    with patch("src.flattener._check_image_url", side_effect=_ok_checker):
        entity = _make_entity()
        result = flatten_entity(entity, use_ai=False, quiet=True)
    assert result["images"] == ["http://ok.com/cat.jpg"]


def test_flatten_entity_with_ai_calls_openai():
    fake_response = MagicMock()
    fake_response.output_text = "Resumen generado por IA."
    with patch("src.flattener._check_image_url", side_effect=_ok_checker), \
         patch("src.flattener.os.getenv", return_value="fake-key"), \
         patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.responses.create.return_value = fake_response
        mock_openai.return_value = mock_client
        entity = _make_entity()
        result = flatten_entity(entity, use_ai=True, model="gpt-test", quiet=True)
    assert result["summary"] == "Resumen generado por IA."


# ---------------------------------------------------------------------------
# flatten_entities
# ---------------------------------------------------------------------------

def test_flatten_entities_processes_all():
    with patch("src.flattener._check_image_url", side_effect=_ok_checker):
        entities = [_make_entity(), _make_entity(name="Museo de Burgos")]
        result = flatten_entities(entities, use_ai=False, quiet=True)
    assert len(result) == 2
    assert all("summary" in e for e in result)


def test_flatten_entities_empty():
    assert flatten_entities([], use_ai=False, quiet=True) == []


# ---------------------------------------------------------------------------
# _collect_all_images
# ---------------------------------------------------------------------------

def test_collect_all_images_includes_sources():
    entity = {
        "images": ["http://ok.com/main.jpg"],
        "sources": [
            {"images": ["http://ok.com/src1.jpg", "http://ok.com/src2.jpg"]},
            {"images": ["http://ok.com/src3.jpg"]},
        ],
    }
    result = _collect_all_images(entity)
    assert result == [
        "http://ok.com/main.jpg",
        "http://ok.com/src1.jpg",
        "http://ok.com/src2.jpg",
        "http://ok.com/src3.jpg",
    ]


def test_collect_all_images_no_sources():
    entity = {"images": ["http://ok.com/a.jpg"], "sources": []}
    assert _collect_all_images(entity) == ["http://ok.com/a.jpg"]


def test_flatten_entity_collects_source_images():
    entity = _make_entity(
        images=["http://ok.com/main.jpg"],
        sources=[{"images": ["http://ok.com/extra.jpg", "http://fail.com/bad.jpg"]}],
    )
    with patch("src.flattener._check_image_url", side_effect=_ok_checker):
        result = flatten_entity(entity, use_ai=False, quiet=True)
    assert "http://ok.com/main.jpg" in result["images"]
    assert "http://ok.com/extra.jpg" in result["images"]
    assert "http://fail.com/bad.jpg" not in result["images"]


def test_flatten_entity_caps_images_after_collecting_sources():
    images = [f"http://ok.com/{i}.jpg" for i in range(12)]
    entity = _make_entity(images=images[:2], sources=[{"images": images[2:]}])
    with patch("src.flattener._check_image_url", side_effect=_all_ok):
        result = flatten_entity(entity, use_ai=False, quiet=True)
    assert len(result["images"]) == 10


def test_flatten_entity_summary_strips_common_content_prefixes():
    entity = _make_entity(
        longDescription="Mas lugares de interes Convento del Santo Angel. Ver mapa.",
        description="",
        shortDescription="",
        sourceText="",
        images=[],
    )
    result = flatten_entity(entity, use_ai=False, quiet=True)
    assert result["summary"] == "Convento del Santo Angel."


# ---------------------------------------------------------------------------
# summary field ordering
# ---------------------------------------------------------------------------

def test_flatten_entity_summary_is_first_field():
    with patch("src.flattener._check_image_url", side_effect=_all_ok):
        entity = _make_entity()
        result = flatten_entity(entity, use_ai=False, quiet=True)
    assert list(result.keys())[0] == "summary"
