"""Hız (2026-09-29) — M7 yazar ilişkileri ısı haritası: eski hesap = yeni hesap.

- Görüşmesiz satırın ısısı bir kez hesaplanıp kopyalanır: her satırda `heat([], now)` (ve izi varsa `with_trace`) ile
  aynı değer, satırlar ortak nesne paylaşmaz.
- Sadakat sözlüğü hazır parça ve gün başına bir kez kurulur: `author_growth.loyalty_map(crm["loyalty"])` ile aynı; parça
  değişince yeniden kurulur. Isı haritasının bütün cevabı eski yolla (her istekte `loyalty_map`) birebir aynı.
- Hazır parça dosyası değişince istek beklemez: bir önceki hazırlık döner, yeni dosya arkada ayrıştırılır; kapsam
  değişince (başka klasör) eski klasörün verisi sunulmaz. Tur önceki satış kaydını bellekten okur (disk ile aynı).
- Hazırlık yokken canlı CRM okuması aynı metin için bellekte; «Verileri yenile» kaynağı bekler.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

from semantic_bridge import author_growth as G
from semantic_bridge import author_relations as R
from semantic_bridge import author_snapshots as S
from semantic_bridge.editorial_home import EditorialHomeSnapshots
from semantic_layer.tests.test_author_growth import _snaps
from semantic_layer.tests.test_author_relations import GUID, T, _day, engine  # noqa: F401

SCHEMA = "Timas_MSCRM.dbo"
OTHER = "0a1b2c3d-1111-2222-3333-444455556699"


def _crm(now: datetime) -> dict:
    loc = now.astimezone(R.TZ)
    return {
        "authors": [{"ContactId": GUID, "FullName": "Sözleşmeli Yazar", "sozlesme": 2, "en_yakin_bitis": _day(20)},
                    {"ContactId": OTHER, "FullName": "Sessiz Yazar", "sozlesme": 1, "en_yakin_bitis": None}],
        "events": [{"kisi": GUID, "tur": "eser", "yil": loc.year, "ay": loc.month, "adet": 3,
                    "son": (now - timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%S")}],
        "loyalty": [{"kisi": GUID, "ilk": "2015-01-01", "son": "2026-01-01", "eser": 4, "sozlesme": 2, "aktif": 1},
                    {"kisi": OTHER.upper(), "ilk": "2024-03-01", "son": "2024-03-01", "eser": 1, "sozlesme": 1, "aktif": 1}],
        "books": [], "pool": [],
    }


def _wait(cond, seconds=3.0):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_blank_rows_heat_equals_old_computation(engine):  # noqa: F811
    now = datetime.now(timezone.utc)
    c = R.create_card(engine, T, "ayse", {"name": "Portal Adayı", "owner": "ayse"})
    R.create_meeting(engine, T, "ayse", "Ayşe", False, {"cardId": c["id"], "status": "yapildi", "date": _day(-2),
                                                        "time": "10:00", "topic": "t", "tone": "olumlu"})
    crm = _crm(now)
    out = R.heatmap(SCHEMA, lambda sql: [], engine, T, "ayse", crm=crm, now=now, order="ad")
    rows = {r["key"]: r for r in out["items"]}
    # Eski hesap: her satır için ayrı `heat([], now)`; izi olan CRM satırında `with_trace`.
    day, kind = R.latest_trace([("eser", crm["events"][0]["son"])], now)
    assert rows[GUID.lower()]["heat"] == R.with_trace(R.heat([], now), day, kind, now)
    assert rows[OTHER]["heat"] == R.heat([], now)
    # Kartı olan satırın ısısı görüşmelerinden (değişmedi).
    assert rows[c["id"]]["heat"]["score"] > 0 and rows[c["id"]]["heat"]["contactsYear"] == 1
    # Satırlar ortak nesne paylaşmaz.
    a, b = rows[GUID.lower()]["heat"], rows[OTHER]["heat"]
    assert a["parts"] is not b["parts"] and a["months"] is not b["months"]
    b["months"][0] = 99
    b["parts"]["tone"] = 99
    assert a["months"][0] == 0 and a["parts"]["tone"] == 0


def test_loyalty_memo_equals_loyalty_map_and_follows_the_part(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    crm = _crm(now)
    snaps, _ = _snaps(tmp_path, monkeypatch, crm, {})
    first = snaps.loyalty_map(crm)
    assert first == G.loyalty_map(crm["loyalty"])
    assert snaps.loyalty_map(crm) is first                     # parça ve gün aynı: yeniden kurulmaz
    other = dict(crm, loyalty=crm["loyalty"][:1])
    assert snaps.loyalty_map(other) == G.loyalty_map(other["loyalty"]) and snaps.loyalty_map(other) is not first


def test_heatmap_answer_is_the_same_as_the_old_path(engine, tmp_path, monkeypatch):  # noqa: F811
    now = datetime.now(timezone.utc)
    c = R.create_card(engine, T, "ayse", {"name": "Portal Adayı", "owner": "ayse"})
    R.create_meeting(engine, T, "ayse", "Ayşe", False, {"cardId": c["id"], "status": "planlandi", "date": _day(3),
                                                        "time": "11:00", "topic": "Randevu"})
    R.card_for_crm(engine, T, "ayse", GUID, "Sözleşmeli Yazar", "yazar")
    snaps, _ = _snaps(tmp_path, monkeypatch, _crm(now), {now.year: []})
    snaps.snap.refresh(force=True)
    crm = snaps.crm_for_heatmap()
    assert crm is not None
    for scope, order in (("hepsi", "soguk"), ("hepsi", "sadik"), ("hepsi", "zayif"), ("ilgi", "sicak"), ("benim", "ad"),
                         ("sozlesmeli", "soguk")):
        old = R.heatmap(SCHEMA, lambda sql: [], engine, T, "ayse", scope=scope, order=order, now=now, crm=crm,
                        loyalty=lambda: G.loyalty_map(crm["loyalty"]))
        new = R.heatmap(SCHEMA, lambda sql: [], engine, T, "ayse", scope=scope, order=order, now=now, crm=crm,
                        loyalty=lambda: snaps.loyalty_map(crm))
        assert new == old, (scope, order)


def test_new_part_is_parsed_in_the_background_and_scope_is_respected(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    crm = _crm(now)
    scope = ["t"]
    snaps, _ = _snaps(tmp_path, monkeypatch, crm, {now.year: []})
    snaps.snap.scope = lambda: ["author-snapshots", *scope]
    snaps.snap.refresh(force=True)
    first = snaps.part("crm")
    assert first is not None and first["data"]["authors"] == crm["authors"]
    assert snaps.part("crm") is first                          # dosya değişmedi: bellekten

    crm["authors"] = crm["authors"][:1]
    snaps.snap.refresh(force=True)
    path = snaps.snap.directory() / "crm.json"
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))   # aynı saat diliminde yazılsa da yeni dosya
    got = snaps.part("crm")
    assert got is first or got["data"]["authors"] == crm["authors"]  # beklemez: önceki ya da (bitmişse) yeni
    assert _wait(lambda: snaps.part("crm")["data"]["authors"] == crm["authors"])
    assert snaps.part("crm") == EditorialHomeSnapshots.load(path)     # diskteki kayıtla aynı

    # Tur önceki satış kaydını bellekten okur; bellekteki disktekiyle aynıdır.
    sales = snaps.part("sales")
    assert snaps._previous("sales") is sales
    assert snaps._previous("sales") == EditorialHomeSnapshots.load(snaps.snap.directory() / "sales.json")

    # Kapsam değişti (başka klasör): eski klasörün verisi sunulmaz.
    scope[0] = "baska"
    assert snaps.part("crm") is None and snaps.crm_for_heatmap() is None


def test_warm_loads_parts_without_a_request(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    snaps, _ = _snaps(tmp_path, monkeypatch, _crm(now), {now.year: []})
    snaps.snap.refresh(force=True)
    assert snaps._memo == {}
    snaps.warm()
    assert set(snaps._memo) == {"crm", "sales"}
    assert snaps.part("crm") is snaps._memo["crm"][1]


def test_live_reader_keeps_the_same_sql_and_refresh_waits_for_the_source():
    S.CANLI.dusur()
    calls: list[str] = []

    def fetch(sql):
        calls.append(sql)
        return [{"n": len(calls)}]

    live = S.AuthorSnapshots.live_reader(fetch, "t-hiz")
    assert live("SELECT 1") == [{"n": 1}] and live("SELECT 1") == [{"n": 1}] and calls == ["SELECT 1"]
    assert live("SELECT 2") == [{"n": 2}]
    assert S.AuthorSnapshots.live_reader(fetch, "t-hiz", fresh=True)("SELECT 1") == [{"n": 3}]
    assert S.AuthorSnapshots.live_reader(fetch, "baska")("SELECT 1") == [{"n": 4}]   # kiracı anahtarda
    S.CANLI.dusur()
