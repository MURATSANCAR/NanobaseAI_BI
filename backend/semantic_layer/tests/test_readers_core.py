"""H2 → M37 okur çekirdeği sözleşmesi (`readers_core.Provider`): M37'nin `ReadersCore.resolve` aradığı dört zorunlu
yöntem ve üç isteğe bağlı yöntem H2'nin kendi işlevlerinden sayı verir; «Okur çekirdeği bağlı değil» artık çıkmaz.

Sınanan: kayıt (`app.state.readers_core`) → resolve; envanter (kaynak başına, tekil toplam, birleşmiş okur sayılmaz);
izin çelişkisi (aynı kanalda izin + ret); segment sayımı H2 segment motoruyla aynı sayı (`readers_segments.preview`);
ilgi alanları; kural cümlesi ve alanları; hatalı kural düz cümleyle; kişi verisi dönmez.
Veriler yapaydır (tablolara doğrudan yazılır).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from semantic_bridge import okur_sources as OS
from semantic_bridge import readers as R
from semantic_bridge import readers_core as RC
from semantic_bridge import readers_segments as S
from semantic_layer.store.catalog_store import open_store

T = "t1"
NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("READERS_EXPORT_ENABLED", "READERS_REQUIRE_KVKK", "READERS_MINOR_EXPORT", "READERS_CONSENT_SOURCES"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    R._ready.discard(id(e))
    R.ensure(e)
    S.ensure_tables(e)
    with e.begin() as c:
        def reader(rid, sources, *, status="aktif", interests=(), minor=False, attrs=None, city=None):
            c.execute(R.READERS.insert().values(
                reader_id=rid, tenant_id=T, status=status, is_minor=minor, city=city, first_seen=NOW, last_touch=NOW,
                interests_json=json.dumps([{"ad": i} for i in interests]), attrs_json=json.dumps(attrs or {}),
                sources_json=json.dumps(sources), event_count=0, updated_at=NOW))

        def consent(rid, ch, st, src):
            c.execute(R.CONSENTS.insert().values(tenant_id=T, reader_id=rid, channel=ch, status=st, source=src, at=NOW))

        reader("r1", {"crm_contact": 1}, interests=["Tarih"], city="İstanbul")
        reader("r2", {"crm_contact": 1, "crm_lead": 2}, interests=["Tarih", "Roman"], minor=True)
        reader("r3", {"upload": 1}, attrs={"uyari": ["ortak_iletisim"]})
        reader("r9", {"crm_contact": 1}, status="birlesti", interests=["Tarih"])
        consent("r1", "email", "izinli", "iys")
        consent("r1", "kvkk", "izinli", "crm")
        consent("r2", "email", "izinli", "iys")
        consent("r2", "email", "ret", "crm")          # çelişki: ret kazanır
        consent("r2", "kvkk", "izinli", "crm")
        consent("r9", "email", "izinli", "iys")
        consent("r9", "email", "ret", "crm")          # birleşmiş okur sayılmaz
    return e


@pytest.fixture
def core(engine):
    app = SimpleNamespace(state=SimpleNamespace())
    RC.register(app, lambda: engine, lambda: T)
    c = OS.ReadersCore.resolve(app)
    assert c is not None and isinstance(c.provider, RC.Provider)
    return c


def test_inventory_counts_unique_readers_per_source(core):
    inv = core.inventory(T)
    assert inv["toplam"] == 3 and inv["tekil"] == 3
    rows = {r["kayitTipi"]: r for r in inv["satirlar"]}
    assert set(rows) == {"crm_contact", "crm_lead", "upload"}
    cc = rows["crm_contact"]
    assert cc["kaynak"] == "CRM kişi" and cc["toplam"] == 2
    assert cc["epostaIzinli"] == 1 and cc["iysOnayli"] == 2 and cc["kvkkOnayli"] == 2
    assert cc["ilgiAlaniDolu"] == 2 and cc["cocukOlasi"] == 1 and cc["silinebilir"] is None


def test_consent_health_lists_conflicts_and_shared_contacts(core):
    items = {x["tur"]: x["sayi"] for x in core.consent(T)}
    assert items["celiski_email"] == 1 and items["celiski_sms"] == 0 and items["celiski_kvkk"] == 0
    assert items["ortak_iletisim"] == 1


def test_segment_size_matches_h2_preview(core, engine):
    rule = {"match": "all", "rules": [{"field": "ilgi", "op": "in", "value": ["Tarih"]}]}
    got = core.size(T, rule)
    ref = S.preview(engine, T, rule)
    assert got["toplam"] == ref["total"] == 2
    assert got["eposta"] == ref["email"]["exportable"] == 1
    assert got["sms"] == ref["sms"]["exportable"] == 0 and got["izinli"] == 1
    assert core.size(T, {"match": "all", "rules": []})["toplam"] == 3


def test_interests_and_rule_helpers(core):
    assert core.interests(T) == [{"id": "Tarih", "ad": "Tarih", "okur": 2}, {"id": "Roman", "ad": "Roman", "okur": 1}]
    rule = {"match": "all", "rules": [{"field": "ilgi", "op": "in", "value": ["Tarih", "Roman"]},
                                      {"field": "il", "op": "in", "value": ["İstanbul"]}]}
    assert core.rule_interests(rule) == ["Tarih", "Roman"]
    assert "Tarih" in (core.rule_text(rule) or "") and "İstanbul" in (core.rule_text(rule) or "")
    assert "ilgi" in {f["field"] for f in core.rule_fields()}


def test_bad_rule_is_a_plain_sentence_and_no_personal_data(core):
    with pytest.raises(OS.SourceError):
        core.size(T, {"match": "all", "rules": [{"field": "eposta", "op": "in", "value": ["a@b.com"]}]})
    dump = json.dumps([core.inventory(T), core.consent(T), core.interests(T)], ensure_ascii=False)
    assert "r1" not in dump and "@" not in dump


def test_without_registration_m37_still_says_not_connected():
    assert OS.ReadersCore.resolve(SimpleNamespace(state=SimpleNamespace())) is None
