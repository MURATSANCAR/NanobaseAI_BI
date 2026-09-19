"""Toplantı odası rezervasyonu: çakışma, geçmiş, iptal yetkisi, İstanbul günü ve oturumdan gelen kimlik."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from semantic_bridge import board as B
from semantic_bridge import rooms as R
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_runtime import catalog  # noqa: F401

T = "t1"
# 2026-09-16 09:00 İstanbul = 06:00 UTC.
NOW = datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc)
CONF = {"ROOM_DAY_START": "08:00", "ROOM_DAY_END": "20:00", "ROOM_SLOT_MINUTES": "30"}.get


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    R._ready.discard(id(e))
    R.ensure(e)
    return e


@pytest.fixture
def room(engine):
    return R.add_room(engine, T, "timasai", {"name": "Büyük Divan", "location": "3. kat", "capacity": 12})


def _book(engine, room, start, end, user="ayse", display="Ayşe Kaya", day="2026-09-16", **kw):
    return R.book(engine, T, room["id"], user, display, {"date": day, "start": start, "end": end, **kw},
                  now=NOW, conf=CONF)


def test_overlap_is_refused_and_says_who_holds_it(engine, room):
    _book(engine, room, "14:00", "15:30", title="Yayın kurulu")
    with pytest.raises(R.Conflict) as e:
        _book(engine, room, "15:00", "16:00", user="mehmet", display="Mehmet Can")
    assert e.value.status == 409
    assert e.value.booking["displayName"] == "Ayşe Kaya"
    assert "Ayşe Kaya" in str(e.value)


def test_touching_ranges_and_other_rooms_are_free(engine, room):
    other = R.add_room(engine, T, "timasai", {"name": "Podcast Stüdyosu"})
    _book(engine, room, "14:00", "15:00")
    _book(engine, room, "15:00", "16:00", user="mehmet", display="Mehmet Can")
    _book(engine, room, "13:00", "14:00", user="zeynep", display="Zeynep Er")
    _book(engine, other, "14:00", "15:00", user="mehmet", display="Mehmet Can")
    view = R.day_view(engine, T, "2026-09-16", "mehmet", now=NOW, conf=CONF)
    assert len(view["bookings"]) == 4
    assert {b["startLocal"] for b in view["bookings"] if b["mine"]} == {"15:00", "14:00"}


@pytest.mark.parametrize("start,end,message", [
    ("15:00", "14:00", "sonra"),
    ("14:10", "15:00", "adım"),
    ("07:30", "09:00", "arasında"),
    ("19:30", "20:30", "arasında"),
    ("8:00", "09:00", "biçim"),
])
def test_bad_ranges_are_explained(engine, room, start, end, message):
    with pytest.raises(R.RoomError) as e:
        _book(engine, room, start, end)
    assert e.value.status == 422 and message in str(e.value)


def test_past_is_refused_but_the_current_slot_can_be_taken(engine, room):
    with pytest.raises(R.RoomError, match="Geçmiş"):
        _book(engine, room, "08:00", "08:30")
    with pytest.raises(R.RoomError, match="Geçmiş"):
        _book(engine, room, "14:00", "15:00", day="2026-09-15")
    # 09:00 tam şimdi; 09:00–09:30 alınabilir.
    assert _book(engine, room, "09:00", "09:30")["startLocal"] == "09:00"


def test_only_the_owner_or_an_admin_cancels_and_the_slot_frees(engine, room):
    b = _book(engine, room, "14:00", "15:00")
    with pytest.raises(R.Forbidden):
        R.cancel(engine, T, b["id"], "mehmet", admin=False, now=NOW)
    R.cancel(engine, T, b["id"], "AYSE", admin=False, now=NOW)
    with pytest.raises(R.NotFound):
        R.cancel(engine, T, b["id"], "ayse", admin=False, now=NOW)
    again = _book(engine, room, "14:00", "15:00", user="mehmet", display="Mehmet Can")
    R.cancel(engine, T, again["id"], "timasai", admin=True, now=NOW)
    assert R.day_view(engine, T, "2026-09-16", "x", now=NOW, conf=CONF)["bookings"] == []


def test_finished_booking_cannot_be_cancelled(engine, room):
    b = _book(engine, room, "10:00", "10:30")
    later = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)  # 11:00 İstanbul
    with pytest.raises(R.RoomError, match="Bitmiş"):
        R.cancel(engine, T, b["id"], "ayse", now=later)


def test_day_is_the_istanbul_day(engine, room):
    conf = {"ROOM_DAY_START": "00:00", "ROOM_DAY_END": "24:00", "ROOM_SLOT_MINUTES": "30"}.get
    b = R.book(engine, T, room["id"], "ayse", "Ayşe Kaya", {"date": "2026-09-17", "start": "01:30", "end": "02:00"},
               now=NOW, conf=conf)
    assert b["start"].startswith("2026-09-16T22:30")  # UTC'de hâlâ 16'sı
    assert [x["id"] for x in R.day_view(engine, T, "2026-09-17", "x", now=NOW, conf=conf)["bookings"]] == [b["id"]]
    assert R.day_view(engine, T, "2026-09-16", "x", now=NOW, conf=conf)["bookings"] == []
    late = R.book(engine, T, room["id"], "ayse", "Ayşe Kaya", {"date": "2026-09-16", "start": "23:30", "end": "24:00"},
                  now=NOW, conf=conf)
    assert late["endLocal"] == "24:00" and late["date"] == "2026-09-16"


def test_now_view_shows_current_holder_and_next(engine, room):
    _book(engine, room, "09:00", "10:00")
    _book(engine, room, "10:00", "11:00", user="mehmet", display="Mehmet Can")
    _book(engine, room, "13:00", "14:00", user="zeynep", display="Zeynep Er")
    at = datetime(2026, 9, 16, 6, 15, tzinfo=timezone.utc)  # 09:15
    r = R.now_view(engine, T, "x", now=at)["rooms"][0]
    assert r["current"]["displayName"] == "Ayşe Kaya"
    assert r["next"]["displayName"] == "Mehmet Can"


def test_removing_a_room_cancels_its_future_bookings(engine, room):
    _book(engine, room, "14:00", "15:00")
    out = R.remove_room(engine, T, "timasai", room["id"], now=NOW)
    assert out["cancelledBookings"] == 1
    assert R.list_rooms(engine, T) == []
    R.add_room(engine, T, "timasai", {"name": "Büyük Divan"})  # kaldırılan odanın adı yeniden kullanılabilir
    with pytest.raises(R.RoomError, match="zaten"):
        R.add_room(engine, T, "timasai", {"name": "büyük divan"})


def test_session_carries_the_display_name():
    assert B.session_of("s=1", fetch=lambda c: {"username": "ayse", "displayName": "Ayşe Kaya"}) == ("ayse", "Ayşe Kaya")
    assert B.session_of("s=1", fetch=lambda c: {"username": "ayse"}) == ("ayse", "ayse")
    with pytest.raises(B.NoUser):
        B.session_of("", fetch=lambda c: {"username": "ayse"})


def test_endpoints_take_identity_from_the_session(catalog, logo_connector, settings, monkeypatch):
    from semantic_bridge import admin as A
    from semantic_bridge.app import Runtime, create_app

    who = {"s=ayse": {"username": "ayse", "displayName": "Ayşe Kaya"},
           "s=mehmet": {"username": "mehmet", "displayName": "Mehmet Can"},
           "s=admin": {"username": "timasai", "displayName": "Timaş AI"}}
    monkeypatch.setattr(B, "_fetch_session", lambda cookie: who.get(cookie))
    monkeypatch.setenv("TIMAS_ADMIN_USERS", "timasai")
    monkeypatch.setenv("ROOM_DAY_START", "00:00")
    monkeypatch.setenv("ROOM_DAY_END", "24:00")
    A._cache.update(at=0.0, values={})
    runtime = Runtime(settings, store=catalog, connector=logo_connector, llm=None)
    client = TestClient(create_app(runtime))

    assert client.get("/api/v1/rooms").status_code == 401
    assert client.post("/api/v1/admin/rooms", json={"name": "Divan"}, headers={"cookie": "s=ayse"}).status_code == 403
    room = client.post("/api/v1/admin/rooms", json={"name": "Divan"}, headers={"cookie": "s=admin"}).json()

    day = "2099-01-05"
    made = client.post(f"/api/v1/rooms/{room['id']}/bookings", headers={"cookie": "s=ayse"},
                       json={"date": day, "start": "14:00", "end": "15:00", "title": "Kurul", "username": "mehmet"})
    assert made.status_code == 201, made.text
    assert made.json()["username"] == "ayse", "gövdedeki kullanıcı adı yok sayılmalı"

    clash = client.post(f"/api/v1/rooms/{room['id']}/bookings", headers={"cookie": "s=mehmet"},
                        json={"date": day, "start": "14:30", "end": "15:30"})
    assert clash.status_code == 409
    assert clash.json()["detail"]["booking"]["displayName"] == "Ayşe Kaya"

    seen = client.get(f"/api/v1/rooms?date={day}", headers={"cookie": "s=mehmet"}).json()
    b = seen["bookings"][0]
    assert (b["displayName"], b["title"], b["mine"], b["canCancel"]) == ("Ayşe Kaya", "Kurul", False, False)
    assert seen["me"] == {"username": "mehmet", "displayName": "Mehmet Can", "admin": False}

    assert client.delete(f"/api/v1/rooms/bookings/{b['id']}", headers={"cookie": "s=mehmet"}).status_code == 403
    assert client.delete(f"/api/v1/rooms/bookings/{b['id']}", headers={"cookie": "s=ayse"}).status_code == 200
    kinds = [x["kind"] for x in A.audit_list(runtime.store.engine)["items"]]
    assert kinds.count("booking") == 2 and "room" in kinds
