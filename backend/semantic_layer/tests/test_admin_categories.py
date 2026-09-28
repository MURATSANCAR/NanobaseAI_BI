"""Yönetim › Ayarlar kategorileri (2026-09-28).

Sözleşme: her ayar grubu `CATEGORIES`teki tam bir kategoridedir; SPEC'teki her ayarın grubu `GROUPS`ta tanımlıdır;
`settings_view()` kategorileri sırasıyla döndürür (ön yüz kategorisiz grubu «Diğer» altında gösterir).
"""

from __future__ import annotations

from semantic_bridge import admin as AD

APPROVED = {
    "baglanti": {"database", "crm", "directory", "people", "access"},
    "zeki": {"llm", "chat", "model_quality", "studio", "zeki_ortak", "voice"},
    "eposta": {"email", "delivery", "mailbox"},
    "pazarlama": {"marketing", "creative", "ads", "social", "influencer", "catalog", "relations", "sets"},
    "seo": {"seo", "geo"},
    "satis": {"corporate", "eticaret", "kampanya", "commerce", "readers", "dijital", "channels", "pazar"},
    "lojistik": {"stock", "shipping"},
    "finans": {"royalty", "kurul"},
    "ik": {"hr", "rooms"},
    "sistem": {"itops", "security", "support", "performance"},
}


def test_every_group_in_exactly_one_known_category():
    cat_ids = [c["id"] for c in AD.CATEGORIES]
    assert cat_ids == list(APPROVED)
    assert len(set(cat_ids)) == len(cat_ids)
    ids = [g["id"] for g in AD.GROUPS]
    assert len(set(ids)) == len(ids)
    assert all(g.get("category") in cat_ids for g in AD.GROUPS)
    by_cat: dict[str, set[str]] = {}
    for g in AD.GROUPS:
        by_cat.setdefault(g["category"], set()).add(g["id"])
    assert by_cat == APPROVED


def test_every_setting_has_a_defined_group():
    groups = {g["id"] for g in AD.GROUPS}
    assert {s["group"] for s in AD.SPEC} <= groups


def test_settings_view_carries_categories(monkeypatch):
    monkeypatch.setattr(AD, "_engine", None, raising=False)
    monkeypatch.setattr(AD, "_stored", lambda: {})
    view = AD.settings_view()
    assert [c["id"] for c in view["categories"]] == list(APPROVED)
    assert all("category" in g for g in view["groups"])
