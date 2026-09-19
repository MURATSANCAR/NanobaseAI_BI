"""Kampüs kutlaması: kutlanan kişinin gelen kutusu, günde bir kez, ad eşleştirme ve başkasının bildirimi."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from semantic_bridge import greetings as G
from semantic_layer.store.catalog_store import open_store

T = "t1"
NOW = datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    G._ready.discard(id(e))
    G.ensure(e)
    return e


def test_greeting_reaches_recipient_by_display_name_once(engine):
    first = G.send(engine, T, "deniz", "Deniz Kaya", {"to": "Ahmet Yıldız", "occasion": "Doğum Günü"}, now=NOW)
    again = G.send(engine, T, "deniz", "Deniz Kaya", {"to": "Ahmet  Yıldız"}, now=NOW)
    assert first["created"] and not again["created"] and first["id"] == again["id"]
    assert G.sent_today(engine, T, "deniz", now=NOW) == ["Ahmet Yıldız"]

    # AD büyük harfle yazsa da aynı kişi.
    box = G.inbox(engine, T, "ahmety", "AHMET YILDIZ")
    assert [(b["from"], b["occasion"]) for b in box] == [("Deniz Kaya", "Doğum Günü")]
    assert G.inbox(engine, T, "busra", "Büşra Aksoy") == []


def test_seen_is_only_marked_by_the_recipient(engine):
    g = G.send(engine, T, "deniz", "Deniz Kaya", {"to": "Ahmet Yıldız"}, now=NOW)
    assert G.mark_seen(engine, T, "busra", "Büşra Aksoy", [g["id"]]) == 0
    assert G.mark_seen(engine, T, "ahmety", "Ahmet Yıldız", [g["id"]]) == 1
    assert G.inbox(engine, T, "ahmety", "Ahmet Yıldız") == []


def test_cannot_greet_yourself_or_nobody(engine):
    with pytest.raises(G.GreetingError):
        G.send(engine, T, "deniz", "Deniz Kaya", {"to": "deniz kaya"}, now=NOW)
    with pytest.raises(G.GreetingError):
        G.send(engine, T, "deniz", "Deniz Kaya", {"to": "  "}, now=NOW)


def test_received_and_wall_keep_seen_rows_newest_first(engine):
    from datetime import timedelta

    a = G.send(engine, T, "deniz", "Deniz Kaya", {"to": "Ahmet Yıldız", "occasion": "Alkış: kapak"}, now=NOW)
    b = G.send(engine, T, "busra", "Büşra Aksoy", {"to": "Ahmet Yıldız"}, now=NOW + timedelta(minutes=5))
    G.send(engine, T, "deniz", "Deniz Kaya", {"to": "Büşra Aksoy"}, now=NOW + timedelta(minutes=9))
    assert G.mark_seen(engine, T, "ahmety", "Ahmet Yıldız", [a["id"]], now=NOW + timedelta(minutes=10)) == 1

    got = G.received(engine, T, "ahmety", "Ahmet Yıldız", now=NOW + timedelta(minutes=11))
    assert [g["id"] for g in got] == [b["id"], a["id"]]
    assert [g["seen"] for g in got] == [False, True]
    assert G.received(engine, T, "ahmety", "Ahmet Yıldız", days=0, now=NOW + timedelta(days=2)) == []

    wall = G.wall(engine, T, now=NOW + timedelta(minutes=11))
    assert [(g["from"], g["to"]) for g in wall] == [("Deniz Kaya", "Büşra Aksoy"), ("Büşra Aksoy", "Ahmet Yıldız"), ("Deniz Kaya", "Ahmet Yıldız")]
    assert wall[2]["occasion"] == "Alkış: kapak"
