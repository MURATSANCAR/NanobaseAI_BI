"""Üretim hız (2026-09-29): kartlar ve özet süreç belleğinde; rakamlar eski hesapla birebir aynı.

Sözleşme: ekranın uçları (özet, liste, gecikmeler, matbaalar, kart, takvim) aynı okuma + aynı portal kayıtları + aynı
ayarlar + aynı günde kartları bir kez kurar; kayıt yazılınca, ayar ya da gün değişince, yeni okuma gelince yeniden
kurar. Yeni okuma gelip kartları henüz kurulmadıysa önceki okumanın kartları (ve sorgu bilgisinde o okumanın SQL'i)
döner, yenisi arkada kurulur. «Verileri yenile» kaynağı bekler. Diğer modüllerin okuduğu `Service.cards` her seferinde
yeniden kurar (eski davranış).

Veriler yapaydır; gerçek CRM/Logo kabulü test sunucusunda.
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timedelta
from typing import Any

import pytest

from semantic_bridge import production as PR
from semantic_bridge import production_kaynak as PK
from semantic_bridge import production_plan as PL
from semantic_bridge import production_store as PS
from semantic_bridge import provenance as P
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_production import CARD
from semantic_layer.tests.test_sorgu_bilgisi_kisiler import _check, _production

T = "t1"
NOW = date(2026, 9, 28)


def _eski_overview(svc: PR.Service, engine: Any, tenant: str, now: date) -> dict[str, Any]:
    """2026-09-29 öncesi `Service.overview` (aynen; kartlar her seferinde kurulur)."""
    cards, snap = svc.cards(engine, tenant, False, now)
    leads = PL.measure_leads(cards)
    open_ = [c for c in cards if c["stage"] not in ("tamam", "iptal", "eski")]
    late = [c for c in open_ if c["delays"]]
    soon = [c for c in open_ if not c["delays"] and PR._due_within(c, now, 14)]
    done = [c for c in cards if (PL.parse_day((c["actual"].get("depo") or {}).get("day")) or date.min)
            >= now - timedelta(days=30)]
    matched = sum(1 for c in cards if c["logoMatch"])
    by_stage = {k: 0 for k in PL.STAGES}
    for c in cards:
        by_stage[c["stage"]] += 1
    rec = [d for d in (PR._dayiso(r.get("tarih")) for r in snap["receipts"] if int(r.get("ps") or 0) == 0) if d]
    ords = [d for d in (PR._dayiso(r.get("tarih")) for r in snap["orders"]) if d]
    warnings = list(snap["warnings"])
    last_rec = max(rec) if rec else None
    last_day = PL.parse_day(last_rec)
    if last_day and (now - last_day).days > 10:
        warnings.append(f"Logo'daki son gerçek depo girişi {last_day.day:02d}.{last_day.month:02d}.{last_day.year}: bu tarihten "
                        "sonra gerçekleşen baskı ve depo girişleri Logo kopyasına henüz gelmedi; CRM aşaması ve portal "
                        "kaydından gösterilir.")
    return {
        "asOf": datetime.fromtimestamp(snap["at"], PR.TZ).isoformat(timespec="seconds"), "historyFrom": snap["since"],
        "total": len(cards), "open": len(open_), "late": len(late),
        "escalated": sum(1 for c in late if any(d["level"] == "yonetici" for d in c["delays"])),
        "dueSoon": len(soon), "doneRecent": len(done), "byStage": by_stage, "leads": leads,
        "template": PL.measure_template(cards), "logoMatched": matched,
        "logo": ({"firms": snap["firms"], "lastReceipt": last_rec, "lastOrder": max(ords) if ords else None}
                 if snap["firms"] else None),
        "warnings": warnings, "db": {"crmMs": snap["crmMs"], "logoMs": snap["logoMs"]},
    }


def _eski_list(svc: PR.Service, engine: Any, tenant: str, now: date, page: int = 0, **kw: str) -> dict[str, Any]:
    cards, _ = svc.cards(engine, tenant, False, now)
    items = PR.filter_cards(cards, **kw)
    return {"items": [PR.summary(c) for c in items[page * PR.PAGE_SIZE:(page + 1) * PR.PAGE_SIZE]], "total": len(items),
            "page": page, "pageSize": PR.PAGE_SIZE}


def _eski_delays(svc: PR.Service, engine: Any, tenant: str, now: date) -> dict[str, Any]:
    cards, _ = svc.cards(engine, tenant, False, now)
    late = [c for c in cards if c["delays"]]
    late.sort(key=lambda c: (-max(d["days"] for d in c["delays"]), c["bookTitle"] or ""))
    return {"items": [PR.summary(c) for c in late], "escalateDays": svc.settings()["escalateDays"]}


def _eski_printers(svc: PR.Service, engine: Any, tenant: str, now: date) -> dict[str, Any]:
    cards, snap = svc.cards(engine, tenant, False, now)
    stats = PL.printer_stats(cards, now)
    ref, prior = PR._price_ref(stats), PL.overall_on_time(stats)
    for s in stats:
        sc = PL.score(s, ref, prior)
        s.update(score=sc["score"], scoreParts=sc["parts"], scoreNotes=sc["notes"])
    return {"items": stats, "priceRef": ref, "historyFrom": snap["since"]}


@pytest.fixture
def pr_engine():
    e = open_store("sqlite://").engine
    PS._ready.discard(id(e))
    PS.ensure(e)
    return e


@pytest.fixture
def sayac(monkeypatch):
    """Kartların kaç kez kurulduğu; gün sabit (arkadaki ısıtma da aynı günü kullansın)."""
    n = {"build": 0}
    orig = PR.build_cards

    def sayan(*a, **kw):
        n["build"] += 1
        return orig(*a, **kw)

    monkeypatch.setattr(PR, "build_cards", sayan)
    monkeypatch.setattr(PR, "today", lambda: NOW)
    return n


def _bekle() -> None:
    for t in threading.enumerate():
        if t.name.startswith("bellek:") and t is not threading.current_thread():
            t.join(10)


def _entry(engine, kind="yayin", **body):
    return PS.add_entry(engine, T, "ayse", "Ayşe", CARD, {"kind": kind, **body}, NOW)


def test_cached_screens_equal_old_computation(pr_engine, tmp_path, sayac):
    svc, source, _ = _production(tmp_path)
    _entry(pr_engine, day="2026-10-01")
    _entry(pr_engine, "kalite", value="sorunsuz")
    assert svc.overview(pr_engine, T) == _eski_overview(svc, pr_engine, T, NOW)
    for kw in ({}, {"durum": "hepsi"}, {"durum": "gecikme"}, {"durum": "tamam"}, {"q": "deneme"}, {"tur": "tekrar"},
               {"urun": "kitap"}, {"matbaa": "Örnek Matbaa"}):
        assert svc.list(pr_engine, T, **kw) == _eski_list(svc, pr_engine, T, NOW, **kw), kw
    assert svc.delays(pr_engine, T) == _eski_delays(svc, pr_engine, T, NOW)
    assert svc.printers(pr_engine, T) == _eski_printers(svc, pr_engine, T, NOW)

    # Kart ayrıntısı ve takvim: aynı kodun kartları her seferinde kurduğu hâliyle karşılaştırılır.
    eski, _, _ = _production(tmp_path)
    eski._kart_al = lambda e, t, fresh=False, now=None: (*eski.cards(e, t, fresh, now), None)
    assert svc.detail(pr_engine, T, CARD) == eski.detail(pr_engine, T, CARD)
    assert svc.calendar(pr_engine, T, "2026-12-01") == eski.calendar(pr_engine, T, "2026-12-01")

    # Kampüs «matbaadan yeni çıkanlar»: eski hesap (son okuma + kayıtlar → kartlar, her seferinde).
    snap = source.last()
    entries, _ = PS.load(pr_engine, T)
    days = svc.settings()["newPrintsDays"]
    cards = PR.build_cards(snap, entries, settings=svc.settings(), now=NOW)
    assert svc.new_prints(pr_engine, T) == {
        "items": [{**{k: v for k, v in i.items() if k != "titleFromBook"}, "cover": None} for i in PR.new_prints(cards, NOW, days)],
        "days": days, "ready": True,
        "asOf": datetime.fromtimestamp(snap["at"], PR.TZ).isoformat(timespec="seconds")}

    # Sorgu bilgisi: kartların dayandığı okumanın SQL'i, kaynaksız rakam yok.
    ov = svc.overview(pr_engine, T)
    k = _check(P.ekle(ov, PK.for_overview(pr_engine, T, ov, svc.okunan())), PK.NOT_RAKAM)
    assert k["sources"]["uretim.okuma.crm.kartlar"]["sql"].startswith("USE [CRMDB];")
    lst = svc.list(pr_engine, T, durum="hepsi")
    _check(P.ekle(lst, PK.for_list(pr_engine, T, lst, svc.okunan())), PK.NOT_RAKAM)


def test_memory_rebuilds_only_when_inputs_change(pr_engine, tmp_path, sayac):
    svc, source, settings = _production(tmp_path)
    svc.overview(pr_engine, T)
    assert sayac["build"] == 1
    svc.list(pr_engine, T, durum="hepsi")
    svc.delays(pr_engine, T)
    svc.printers(pr_engine, T)
    svc.overview(pr_engine, T)
    assert sayac["build"] == 1                                              # aynı girdiler: bellekten

    # Portal kaydı yazıldı: yazma ucu arkada kurar, sonraki okuma yeni kaydı gösterir.
    _entry(pr_engine, day="2026-10-01")
    svc.yazildi(pr_engine, T)
    _bekle()
    assert sayac["build"] == 2
    assert svc.list(pr_engine, T, durum="hepsi") == _eski_list(svc, pr_engine, T, NOW, durum="hepsi")
    got = next(x for x in svc.list(pr_engine, T, durum="hepsi")["items"] if x["id"] == CARD)
    assert got["publication"] == "2026-10-01"

    # Ayar değişti: yeniden kurulur.
    n = sayac["build"]
    settings["escalateDays"] = 3
    svc.delays(pr_engine, T)
    assert sayac["build"] == n + 1

    # Başka gün: yeniden kurulur.
    n = sayac["build"]
    svc.overview(pr_engine, T, now=NOW + timedelta(days=1))
    assert sayac["build"] == n + 1

    # «Verileri yenile»: kaynak yeniden okunur, kartlar o okumayla kurulur (okuma bitince başlayan ısıtmayla tek iş).
    before = source.last()["at"]
    n = sayac["build"]
    ov = svc.overview(pr_engine, T, fresh=True)
    _bekle()
    assert source.last()["at"] > before and sayac["build"] == n + 1
    assert ov == _eski_overview(svc, pr_engine, T, NOW)


def test_new_read_serves_previous_cards_until_built(pr_engine, tmp_path, sayac):
    svc, source, _ = _production(tmp_path)
    first = svc.list(pr_engine, T, durum="hepsi")
    s1 = svc.okunan()
    n = sayac["build"]
    # Arkadaki okuma bitti ama (ısıtma kancası olmadan) kartları kurulmadı.
    with source._lock:
        source._snap = dict(s1, at=s1["at"] + 60)
        source._at = s1["at"] + 60
    again = svc.list(pr_engine, T, durum="hepsi")
    assert again == first and svc.okunan() is s1                            # önceki okuma, onun SQL'iyle
    _bekle()
    assert sayac["build"] == n + 1
    svc.list(pr_engine, T, durum="hepsi")
    assert svc.okunan()["at"] == s1["at"] + 60 and sayac["build"] == n + 1  # yenisi bellekten


def test_new_read_warms_cards_behind(pr_engine, tmp_path, sayac):
    svc, source, _ = _production(tmp_path)
    svc.overview(pr_engine, T)
    n = sayac["build"]
    source._refresh(0.0 + 10 ** 10)   # arkadaki okuma (zamanlayıcı) bitti → ısıtma kancası
    _bekle()
    assert sayac["build"] == n + 1
    svc.overview(pr_engine, T)
    assert sayac["build"] == n + 1 and svc.okunan() is source.last()


def test_other_modules_get_their_own_cards(pr_engine, tmp_path, sayac):
    svc, _, _ = _production(tmp_path)
    a, _ = svc.cards(pr_engine, T)
    b, _ = svc.cards(pr_engine, T)
    assert a == b and a is not b                                            # çağıranın kopyası
    a[0]["stage"] = "degisti"
    assert svc.list(pr_engine, T, durum="hepsi") == _eski_list(svc, pr_engine, T, NOW, durum="hepsi")
