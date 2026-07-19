"""Unit tests for datasource-scoped chat suggestions."""

from __future__ import annotations

from nanobase_api.suggestions import build_suggestions, defaults_for


class _FakeRepo:
    def __init__(self, rows=None):
        self._rows = rows or []

    def top_user_questions(self, **_kwargs):
        return list(self._rows)


def test_defaults_per_datasource():
    assert any("hasar" in q.lower() for q in defaults_for("sigorta"))
    assert any("müşteri" in q.lower() or "musteri" in q.lower() for q in defaults_for("erp"))
    assert defaults_for("unknown-db")


def test_build_suggestions_defaults_without_history():
    out = build_suggestions(
        tenant_id="default",
        datasource_id="sigorta",
        limit=3,
        question_repo=_FakeRepo([]),
    )
    assert out["datasource_id"] == "sigorta"
    assert len(out["suggestions"]) == 3
    assert out["learned_count"] == 0
    assert all(s["source"] == "default" for s in out["suggestions"])


def test_build_suggestions_prefers_learned():
    out = build_suggestions(
        tenant_id="default",
        datasource_id="sigorta",
        limit=4,
        question_repo=_FakeRepo(
            [
                {"question": "Kaç poliçe var?", "count": 12},
                {"question": "Hasar durumu nedir?", "count": 5},
            ]
        ),
    )
    assert out["suggestions"][0]["text"] == "Kaç poliçe var?"
    assert out["suggestions"][0]["source"] == "learned"
    assert out["learned_count"] == 2
    assert out["default_count"] == 2
