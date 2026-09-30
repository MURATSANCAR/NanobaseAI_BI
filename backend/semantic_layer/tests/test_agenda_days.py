"""Kampüs ajandasının «Önemli günler» kısmı (`agenda_days`): CRM özel gününün tarihi Sezon takviminin kuralıyla,
pencere dışı ve tarihi bilinmeyen gün dışarıda, aynı adlı resmî tatil tek satır ve kesin gün, doğum günü yalnız gün/ay.

Veriler yapaydır; gerçek CRM okuması test sunucusunda (`semantic_seo_seasons_days`, gece Sezon takvimi yenilemesi)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from semantic_bridge import agenda_days as AD
from semantic_bridge.seo_geo import seasons as S
from semantic_layer.store.catalog_store import open_store

T = "t1"
NOW = date(2026, 9, 30)  # ISO 40. hafta


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    S.ensure_tables(e)
    at = datetime(2026, 9, 29, tzinfo=timezone.utc)

    def day(key, name, w1=None, w2=None, fixed=None, books=0, source="crm"):
        return dict(tenant_id=T, day_key=key, name=name, source=source, crm_ids=json.dumps([key]), week_from=w1,
                    week_to=w2, fixed_date=fixed, web=False, crm_books=books, keywords_json="[]", synced_at=at)

    with e.begin() as c:
        c.execute(S.DAYS.insert(), [
            day("hayvan", "Dünya Hayvanları Koruma Günü", 41, 41, books=16),
            day("cumhuriyet", "Cumhuriyet Bayramı", 44, 44, books=15),
            day("ogretmen", "Öğretmenler Günü", 48, 48, books=8),            # kural: 24 Kasım → 55 gün
            day("akif", "Mehmet Akif Ersoy'un Doğum Günü", 52, 52, books=9),  # pencere dışı
            day("lgs", "LGS (Liselere Geçiş Sınavı)", source="kural"),        # tarih bilinmiyor
        ])
    return e


def test_special_days_use_season_rules_and_window(engine):
    got = {d["id"]: d for d in AD.special_days(engine, T, NOW, 60)}
    assert set(got) == {"hayvan", "cumhuriyet", "ogretmen"}
    assert got["hayvan"]["startsOn"] == "2026-10-05" and got["hayvan"]["endsOn"] == "2026-10-11"
    assert got["hayvan"]["precision"] == "hafta" and got["hayvan"]["books"] == 16
    assert got["ogretmen"]["startsOn"] == "2026-11-24" and got["ogretmen"]["precision"] == "kesin"


def test_same_named_holiday_merges_into_special_day(engine, monkeypatch):
    monkeypatch.setattr(AD, "holidays", lambda *_a: [
        {"kind": "tatil", "id": "2026-10-29", "title": "Cumhuriyet Bayramı", "day": "2026-10-29", "startsOn": "2026-10-29",
         "endsOn": "2026-10-29", "daysLeft": 29, "half": False},
        {"kind": "tatil", "id": "2026-10-28", "title": "Cumhuriyet Bayramı Arifesi", "day": "2026-10-28",
         "startsOn": "2026-10-28", "endsOn": "2026-10-28", "daysLeft": 28, "half": True}])
    monkeypatch.setattr(AD, "birthdays", lambda *_a: [])
    out = AD.important_days(engine, T, NOW, 60)
    cum = [d for d in out["importantDays"] if d["title"] == "Cumhuriyet Bayramı"]
    assert len(cum) == 1 and cum[0]["holiday"] and cum[0]["day"] == "2026-10-29" and cum[0]["precision"] == "kesin"
    assert [d["day"] for d in out["importantDays"]] == sorted(d["day"] for d in out["importantDays"])
    assert any(d["kind"] == "tatil" and d["half"] for d in out["importantDays"])


def test_a_failing_source_leaves_the_rest(engine, monkeypatch):
    def boom(*_a):
        raise RuntimeError("İK tablosu yok")
    monkeypatch.setattr(AD, "holidays", boom)
    monkeypatch.setattr(AD, "birthdays", boom)
    out = AD.important_days(engine, T, NOW, 60)
    assert len(out["importantDays"]) == 3 and out["birthdays"] == []
