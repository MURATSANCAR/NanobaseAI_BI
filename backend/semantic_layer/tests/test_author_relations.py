"""M7 Yazar ilişkileri: kart, CRM kişisine tek kart, randevu → görüşme notu, gizli not, oda rezervasyonu,
ısı puanı ve CRM sorgularının biçimi.

Sözleşme: bir CRM kişisine en çok bir kart; görüşmeyi yalnız yazan (ya da yönetici) değiştirir; gizli notun metni
yalnız yazana ve katılımcılara gider; randevu tarihi değişince oda yeni saate taşınır, iptal edilince bırakılır;
ısı puanı yalnız yapılmış görüşmelerden çıkar.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from semantic_bridge import author_relations as R
from semantic_bridge import rooms
from semantic_layer.store.catalog_store import open_store

T = "t1"
GUID = "0A1B2C3D-1111-2222-3333-444455556666"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    R._ready.discard(id(e))
    rooms._ready.discard(id(e))
    R.ensure(e)
    rooms.ensure(e)
    return e


def _day(days: int) -> str:
    return (datetime.now(R.TZ) + timedelta(days=days)).date().isoformat()


def test_card_validation_and_one_card_per_crm_person(engine):
    with pytest.raises(R.RelationError, match="Ad soyad"):
        R.create_card(engine, T, "ayse", {"name": "  "})
    with pytest.raises(R.RelationError, match="E-posta"):
        R.create_card(engine, T, "ayse", {"name": "Deniz Yazar", "email": "yok"})
    with pytest.raises(R.RelationError, match="https"):
        R.create_card(engine, T, "ayse", {"name": "Deniz Yazar", "links": ["ftp://x"]})
    c = R.create_card(engine, T, "ayse", {"name": "Deniz  Yazar", "crmContactId": GUID, "tags": "tarih, tarih, ilk kitap",
                                          "links": ["https://ornek.org"], "source": "etkinlik"})
    assert c["name"] == "Deniz Yazar" and c["crmContactId"] == GUID.lower() and c["tags"] == ["tarih", "ilk kitap"]
    assert c["stage"] == "aday" and c["sourceLabel"] == "Fuar / etkinlik"
    with pytest.raises(R.RelationError) as e:
        R.create_card(engine, T, "mehmet", {"name": "Deniz Yazar", "crmContactId": GUID})
    assert e.value.status == 409 and e.value.extra["cardId"] == c["id"]
    row, created = R.card_for_crm(engine, T, "mehmet", GUID, "Deniz Yazar")
    assert row.id == c["id"] and created is False


def test_archive_only_by_opener_owner_or_admin(engine):
    c = R.create_card(engine, T, "ayse", {"name": "Aday Bir", "owner": "Mehmet"})
    out, diff = R.update_card(engine, T, "zeynep", False, c["id"], {"stage": "temas"})
    assert out["stage"] == "temas" and diff["stage"] == {"before": "aday", "after": "temas"}
    with pytest.raises(R.RelationError) as e:
        R.update_card(engine, T, "zeynep", False, c["id"], {"archived": True})
    assert e.value.status == 403
    out, _ = R.update_card(engine, T, "mehmet", False, c["id"], {"archived": True})
    assert out["archived"] is True
    assert R.list_cards(engine, T, "ayse")["total"] == 0
    assert R.list_cards(engine, T, "ayse", archived=True)["total"] == 1


def test_first_note_for_a_crm_author_opens_the_card(engine):
    m = R.create_meeting(engine, T, "ayse", "Ayşe", False, {
        "crmContactId": GUID, "name": "Deniz Yazar", "status": "yapildi", "date": _day(-3), "time": "11:00",
        "channel": "telefon", "topic": "Yeni dosya", "notes": "Kasımda bitiriyor", "tone": "olumlu",
        "nextStep": "İlk bölümleri iste", "nextDue": _day(-1)})
    got = R.by_crm(engine, T, "mehmet", False, GUID.lower())
    assert got["card"]["stage"] == "yazar" and got["card"]["name"] == "Deniz Yazar"
    assert got["timeline"][0]["id"] == m["id"] and got["timeline"][0]["notes"] == "Kasımda bitiriyor"
    assert got["heat"]["contactsYear"] == 1 and got["heat"]["band"] in ("ilik", "sicak")
    ag = R.agenda(engine, T, "ayse", False, scope="benim")
    assert [x["id"] for x in ag["openSteps"]] == [m["id"]] and ag["openSteps"][0]["stepLate"] is True
    assert R.agenda(engine, T, "zeynep", False, scope="benim")["openSteps"] == []


def test_meeting_rules_and_private_notes(engine):
    c = R.create_card(engine, T, "ayse", {"name": "Aday İki"})
    with pytest.raises(R.RelationError, match="İleri tarihli"):
        R.create_meeting(engine, T, "ayse", "Ayşe", False, {"cardId": c["id"], "status": "yapildi", "date": _day(3),
                                                            "time": "10:00", "topic": "x"})
    with pytest.raises(R.RelationError, match="Geçmiş"):
        R.create_meeting(engine, T, "ayse", "Ayşe", False, {"cardId": c["id"], "status": "planlandi", "date": _day(-5),
                                                            "time": "10:00", "topic": "x"})
    m = R.create_meeting(engine, T, "ayse", "Ayşe", False, {
        "cardId": c["id"], "status": "yapildi", "date": _day(-1), "time": "10:00", "topic": "Ücret konuşuldu",
        "notes": "gizli ayrıntı", "private": True, "participants": [{"username": "Mehmet", "display": "Mehmet"}],
        "nextStep": "Teklif gönder"})
    other = R.card_detail(engine, T, "zeynep", False, c["id"])["timeline"][0]
    assert other["hidden"] is True and other["notes"] is None and other["topic"] == "Gizli görüşme"
    assert R.card_detail(engine, T, "mehmet", False, c["id"])["timeline"][0]["notes"] == "gizli ayrıntı"
    with pytest.raises(R.RelationError) as e:
        R.update_meeting(engine, T, "mehmet", "Mehmet", False, m["id"], {"topic": "değişti"})
    assert e.value.status == 403
    done, _ = R.update_meeting(engine, T, "mehmet", "Mehmet", False, m["id"], {"nextDone": True})
    assert done["nextDone"] is True
    with pytest.raises(R.RelationError):
        R.delete_meeting(engine, T, "zeynep", False, m["id"])
    assert R.delete_meeting(engine, T, "ayse", False, m["id"])["id"] == m["id"]


def test_room_follows_the_appointment(engine, monkeypatch):
    from semantic_bridge import admin as admin_mod
    monkeypatch.setattr(admin_mod, "conf", lambda k, d="": {"ROOM_DAY_START": "08:00", "ROOM_DAY_END": "20:00",
                                                            "ROOM_SLOT_MINUTES": "30"}.get(k, d))
    room = rooms.add_room(engine, T, "timasai", {"name": "Divan"})
    c = R.create_card(engine, T, "ayse", {"name": "Aday Üç"})
    day = _day(5)
    m = R.create_meeting(engine, T, "ayse", "Ayşe", False, {"cardId": c["id"], "status": "planlandi", "date": day,
                                                            "time": "10:00", "minutes": 60, "topic": "Tanışma",
                                                            "roomId": room["id"]}, rooms)
    assert m["roomName"] == "Divan"
    with pytest.raises(R.RelationError) as e:   # aynı saate başka randevu: oda dolu, kayıt yazılmaz
        R.create_meeting(engine, T, "mehmet", "Mehmet", False, {"cardId": c["id"], "status": "planlandi", "date": day,
                                                                "time": "10:30", "minutes": 30, "topic": "Çakışan",
                                                                "roomId": room["id"]}, rooms)
    assert e.value.status == 409
    assert len(R.card_detail(engine, T, "ayse", False, c["id"])["timeline"]) == 1
    moved, _ = R.update_meeting(engine, T, "ayse", "Ayşe", False, m["id"], {"time": "14:00"}, rooms)
    assert moved["roomName"] == "Divan" and moved["roomBookingId"] != m["roomBookingId"]
    view = rooms.day_view(engine, T, day, "ayse")
    assert [b["startLocal"] for b in view["bookings"]] == ["14:00"]
    R.update_meeting(engine, T, "ayse", "Ayşe", False, m["id"], {"status": "iptal"}, rooms)
    assert rooms.day_view(engine, T, day, "ayse")["bookings"] == []


def test_heat_score():
    now = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)

    def m(days, tone=None, status="yapildi"):
        return SimpleNamespace(status=status, starts_at=now - timedelta(days=days), tone=tone)

    assert R.heat([], now)["score"] == 0 and R.heat([], now)["band"] == "yok"
    one = R.heat([m(0, "olumlu")], now)
    assert one["parts"] == {"recency": 50, "frequency": 10, "tone": 20} and one["band"] == "sicak"
    old = R.heat([m(400, "olumsuz")], now)
    assert old["score"] == 0 and old["band"] == "soguk" and old["daysSince"] == 400
    many = R.heat([m(90), m(100), m(120), m(130, "olumsuz"), m(-10, status="planlandi")], now)
    assert many["parts"]["frequency"] == 30 and many["parts"]["recency"] == 25 and many["parts"]["tone"] == 10
    assert many["next"] is not None and sum(many["months"]) == 4 and len(many["months"]) == 12
    assert R.month_keys(now)[-1] == "2026-09" and R.month_keys(now)[0] == "2025-10"


def test_crm_sql_is_read_only_and_escaped():
    s = "Timas_MSCRM.dbo"
    sql = R.pool_list_sql(s, "2024-01-01", 2, "O'Neil%")
    assert sql.startswith("SELECT") and "N'%O''Neil[%]%'" in sql and "OFFSET 100 ROWS" in sql
    assert "new_OlasYazarYazar" in sql and "NOT EXISTS" in sql and "100000012" in sql
    assert "100000012" not in R.pool_list_sql(s, "2024-01-01", 0, closed=True)
    assert "GETDATE()" in R.contracted_authors_sql(s) and "100000007" in R.contracted_authors_sql(s)
    assert "UNION ALL" in R.crm_events_sql(s, "2025-10-01")
    # «yazar mı» alt sorgusu dış sorgunun takma adlarını gölgelemez (t.new_kisi dıştaki sözleşme tarafıdır)
    for q in (R.contracted_authors_sql(s), R.crm_events_sql(s, "2025-10-01"), R.pool_list_sql(s, "2024-01-01", 0)):
        inner = q[q.index("EXISTS (SELECT 1"):]
        inner = inner[:inner.index(")") + 1]
        assert not re.search(r"Base (t|e|k|j|r|s)\b", inner), inner
    with pytest.raises(R.RelationError):
        R.pool_count_sql("bad;name", "2024-01-01")
    with pytest.raises(R.RelationError):
        R.crm_events_sql(s, "2025-10-01'; DROP")
    with pytest.raises(R.RelationError):
        R.pool_projects_sql(s, "2024-01-01", ["not-a-guid"])


def test_heatmap_merges_crm_authors_and_cards(engine):
    c = R.create_card(engine, T, "ayse", {"name": "Portal Adayı", "owner": "ayse"})
    R.create_meeting(engine, T, "ayse", "Ayşe", False, {"cardId": c["id"], "status": "yapildi", "date": _day(-2),
                                                        "time": "10:00", "topic": "t", "tone": "olumlu"})
    month = datetime.now(R.TZ)

    def fetch_all(sql):
        if "UNION ALL" in sql:
            return [{"kisi": GUID, "tur": "eser", "yil": month.year, "ay": month.month, "adet": 2}]
        return [{"ContactId": GUID, "FullName": "Sözleşmeli Yazar", "sozlesme": 1, "en_yakin_bitis": "2026-12-01"}]

    out = R.heatmap("Timas_MSCRM.dbo", fetch_all, engine, T, "ayse")
    assert out["total"] == 2 and out["crmOk"] is True
    first, second = out["items"]
    assert first["name"] == "Sözleşmeli Yazar" and first["heat"]["band"] == "yok" and first["crm"][-1] == 2
    assert second["cardId"] == c["id"] and second["heat"]["score"] > 0
    assert R.heatmap("Timas_MSCRM.dbo", fetch_all, engine, T, "ayse", scope="benim")["total"] == 1
    assert R.heatmap("Timas_MSCRM.dbo", fetch_all, engine, T, "ayse", scope="sozlesmeli")["total"] == 1

    def down(sql):
        raise RuntimeError("CRM kapalı")

    broken = R.heatmap("Timas_MSCRM.dbo", down, engine, T, "ayse")
    assert broken["crmOk"] is False and broken["total"] == 1
