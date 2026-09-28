"""Sorgu bilgisi — Grup 4: M37 okur topluluğu, okur sesi ve not sinyali panelleri, M20 basın, M21 reklam, M22 sosyal
medya, M23 işbirlikleri, M27 fuar ve etkinlik, M28 kurumsal ilişkiler.

Her uç için örnek çıktıda her rakam bir kaynağa bağlı (`uncovered_numbers` boş), kayıt tutarlı (`problems` boş), SQL
çalışan metin (yer tutucu yok). Kişisel veri (kişi kartı adı, e-postası) sorgu bilgisine hiçbir zaman yazılmaz. Veriler
yapaydır; gerçek CRM / Logo kabulü `scripts/acceptance/sorgu-bilgisi/pazarlama_*.py` ile test sunucusunda yapılır.
"""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from semantic_bridge import ads as A
from semantic_bridge import ads_kaynak as AK
from semantic_bridge import events as E
from semantic_bridge import events_kaynak as EK
from semantic_bridge import influencers as I
from semantic_bridge import influencers_kaynak as IK
from semantic_bridge import note_signal as N
from semantic_bridge import okur as O
from semantic_bridge import okur_kaynak as OK
from semantic_bridge import pr as PR
from semantic_bridge import pr_kaynak as PRK
from semantic_bridge import provenance as PV
from semantic_bridge import public_affairs as PA
from semantic_bridge import public_affairs_kaynak as PAK
from semantic_bridge import reader_voice as V
from semantic_bridge import readers as R
from semantic_bridge import signals_kaynak as SK
from semantic_bridge import social as S
from semantic_bridge import social_kaynak as SOK
from semantic_layer.store.catalog_store import open_store

T = "t1"
SCHEMA = "Timas_MSCRM.dbo"
GUID = "11111111-2222-3333-4444-555555555555"
MODS = (O, R, V, N, PR, S, I, A, E, PA)


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for m in MODS:
        m._ready.discard(id(e))
        m.ensure(e)
    yield e
    for m in MODS:
        m._ready.discard(id(e))


def _check(out: dict, ignore=()) -> dict:
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert PV.uncovered_numbers(out, ignore) == []
    assert PV.problems(out) == [], PV.problems(out)
    for s in k["sources"].values():
        assert s["sql"].strip() and PV.placeholders_left(s["sql"]) == [], (s["id"], s["sql"][:200])
        assert s["connection"] in ("logo", "crm", "portal")
    json.dumps(out, default=str)
    return k


def _crm_pr():
    return SimpleNamespace(archive_path=None, roles=lambda: ["basin"])


# ------------------------------------------------------------------ M37 okur topluluğu


def test_m37_kitle_ve_egilim(engine):
    out = {"envanter": {"bagli": True, "toplam": 10, "tekil": 10, "tazelik": [],
                        "satirlar": [{"kaynak": "CRM", "kayitTipi": "crm", "toplam": 10, "kvkkOnayli": 4, "iysOnayli": 3,
                                      "epostaIzinli": 5, "smsIzinli": 2, "ilgiAlaniDolu": 6, "silinebilir": None, "cocukOlasi": 1}]},
           "izin": {"bagli": True, "items": [{"tur": "celiski_email", "ad": "E-posta", "sayi": 2, "aciklama": None}], "toplam": 2},
           "segmentSayilari": {"taslak": 1, "onaylandi": 2}, "yaklasanProgramlar": [], "yorum": {"cevapsiz": 3, "toplam": 5},
           "egilim": O.trend(engine, T)}
    PV.ekle(out, OK.for_overview(engine, T, out, "2025-09-01"))
    _check(out, OK.NOT_RAKAM)
    cons = {"bagli": True, "items": [{"tur": "x", "ad": "x", "sayi": 1}], "toplam": 1, "onceki": 0}
    PV.ekle(cons, OK.for_consent(engine, T))
    _check(cons, OK.NOT_RAKAM)


def test_m37_segment_program_yorum_etkinlik(engine):
    segs = O.list_segments(engine, T)
    PV.ekle(segs, OK.for_segments(engine, T, ""))
    _check(segs, OK.NOT_RAKAM)
    progs = O.list_programs(engine, T)
    PV.ekle(progs, OK.for_programs(engine, T, progs, O.program_filters()))
    _check(progs, OK.NOT_RAKAM)
    rev = {"items": [{"id": "1", "puan": 4, "durum": "cevapsiz"}], "sayilar": O.review_counts([]), "seo": {"yorum": 3, "urun": 2}}
    PV.ekle(rev, OK.for_reviews(engine, T, ["55"]))
    _check(rev, OK.NOT_RAKAM)
    ev = {"yil": 2026, "toplam": 3, "durumlar": {"Tamamlandı": 2}, "tamamlanan": 2, "katilimci": 40, "satilan": 10,
          "katilimciBos": 0, "tipler": [{"ad": "İmza", "etkinlik": 2, "katilimci": 40, "satilan": 10}], "iller": [],
          "yazarlar": [], "etkinlikler": [], "yillar": [2026, 2025], "ziyaretHaric": True, "tipSuzgeci": []}
    PV.ekle(ev, OK.for_events([], SCHEMA, 2026, True, []))
    k = _check(ev, OK.NOT_RAKAM)
    assert k["sources"]["topluluk.etkinlik"]["connection"] == "crm"
    assert "2026-01-01" in k["sources"]["topluluk.etkinlik"]["sql"]


# ------------------------------------------------------------------ okur sesi ve not sinyali


def test_okur_sesi_ozeti(engine):
    st = V.settings(lambda k: "")
    out = V.summary(engine, T, st)
    assert "kaynakKonu" in out and "kaynaklar" not in out       # sorgu bilgisi anahtarıyla çakışmaz
    out["uyarilar"] = V.alerts(engine, T)
    out["ayarlar"] = {k: st[k] for k in ("minProb", "minMargin", "defectDays", "defectMin", "windowDays")}
    out["sonKosu"] = None
    PV.ekle(out, SK.for_voice_summary(engine, T, st, out))
    k = _check(out, SK.NOT_RAKAM)
    assert any(s["id"].startswith("trendyol.") for s in k["sources"].values())
    lab = {"items": {"k1": {"konu": "kargo", "olasilik": 0.8}}, "konular": V.TOPICS}
    PV.ekle(lab, SK.for_voice_labels(engine, T, "site-yorum"))
    _check(lab, SK.NOT_RAKAM)


def test_not_sinyali_karti(engine):
    st = N.settings(lambda k: "")
    out = N.view(engine, T, "120.01", N.portal_notes(engine, T, {"120.01"}), st)
    PV.ekle(out, SK.for_note_view(engine, T, "120.01", st))
    _check(out, SK.NOT_RAKAM)


# ------------------------------------------------------------------ M20 basın


def test_m20_bugun_ve_rapor(engine):
    crm = _crm_pr()
    home = {"month": "2026-09", "from": "2026-09-01", "to": "2026-09-30", "books": [], "booksError": None,
            "kpi": {"books": 0, "noKit": 0, "pending": 0, "overdue": 0, "recent": 0, "candidates": 0},
            "pending": [], "overdue": [], "recentCoverage": [], "webWatch": False}
    PV.ekle(home, PRK.for_home(engine, T, crm, date(2026, 9, 1), date(2026, 9, 30), []))
    k = _check(home, PRK.NOT_RAKAM)
    assert k["sources"]["pr.ay"]["connection"] == "crm"
    rep = PR.report(engine, T, "2026-09-01", "2026-09-30", [])
    PV.ekle(rep, PRK.for_report(engine, T, crm))
    _check(rep, PRK.NOT_RAKAM)
    kits = {"items": PR.list_kits(engine, T), "total": 0}
    PV.ekle(kits, PRK.for_kits(engine, T, ""))
    _check(kits, PRK.NOT_RAKAM)


def test_m20_medya_kisisi_kisisel_veri_kayda_girmez(engine):
    PR.create_contact(engine, T, "ayse", {"name": "Mehmet Muhabir", "email": "mehmet@gazete.example"})
    k = PRK.for_contacts(engine, T, _crm_pr()).to_dict()
    text = json.dumps(k, ensure_ascii=False)
    assert "Mehmet Muhabir" not in text and "mehmet@gazete.example" not in text
    assert PV.problems({"kaynaklar": k}) == []


# ------------------------------------------------------------------ M21 reklam


def test_m21_ozet_her_rakam_kaynakli(engine):
    st = A.settings(lambda k: "")
    f, t = date(2026, 9, 1), date(2026, 9, 30)
    out = A.overview(engine, T, f, t, "", None, {}, {}, st)
    out["oneriler"] = A.list_suggestions(engine, T, "acik")
    out["uyarilar"] = []
    PV.ekle(out, AK.for_overview(engine, T, out, f, t, "", [], None, "TIGER", [], set()))
    _check(out, AK.NOT_RAKAM)
    b = A.budget(engine, T, 2026, st, None)
    PV.ekle(b, AK.for_budget(engine, T, 2026, [], False))
    _check(b, AK.NOT_RAKAM + ("yil",))


def test_m21_yenileme_logo_sorgusu_origin(engine):
    A.meta_set(engine, T, AK.LOGO_SQL_KEY, {"runs": [{"conn": "logo", "sql": "SELECT 1 AS gun FROM dbo.LG_411_01_INVOICE",
                                                       "rows": 3, "dbMs": 5, "at": "2026-09-28T04:00:00"}]})
    k = AK.for_status(engine, T, "TIGER").to_dict()
    logo = [s for s in k["sources"].values() if s["connection"] == "logo"]
    assert logo and logo[0]["sql"].startswith("USE [TIGER]")
    assert logo[0]["id"] in k["sources"]["reklam.verisonu"]["origin"]


# ------------------------------------------------------------------ M22 sosyal medya


def test_m22_rapor_ve_takvim(engine):
    rep = S.report(engine, T, "2026-09")
    rep["yorum"] = None
    PV.ekle(rep, SOK.for_report(engine, T, "2026-09"))
    _check(rep, SOK.NOT_RAKAM)
    st = S.settings(lambda k: "")
    cal = S.calendar(engine, T, st, date(2026, 9, 21), date(2026, 9, 27))
    cal["onayBekleyen"] = S.pending(engine, T, st)
    PV.ekle(cal, SOK.for_calendar(engine, T, date(2026, 9, 21), date(2026, 9, 27), ""))
    _check(cal, SOK.NOT_RAKAM)


# ------------------------------------------------------------------ M23 işbirlikleri


def test_m23_pano_ve_rapor(engine):
    out = I.board(engine, T, "ayse", True)
    PV.ekle(out, IK.for_board(engine, T))
    _check(out, IK.NOT_RAKAM)
    rep = I.report(engine, T, date(2026, 9, 1), date(2026, 9, 30), True)
    rep["crm"] = None
    PV.ekle(rep, IK.for_report(engine, T, date(2026, 9, 1), date(2026, 9, 30), False))
    _check(rep, IK.NOT_RAKAM)
    pays = I.list_payouts(engine, T, "2026-09")
    PV.ekle(pays, IK.for_payouts(engine, T, "2026-09"))
    _check(pays, IK.NOT_RAKAM)


# ------------------------------------------------------------------ M27 fuar ve etkinlik


def test_m27_takvim_yaklasan_sonuc(engine):
    cal = E.calendar([], [], 2026, list(E.CLASSES), False)
    cal.update(unmappedTypes=0, warnings=[], crmMs=0)
    PV.ekle(cal, EK.for_calendar(engine, T, 2026))
    _check(cal, EK.NOT_RAKAM)
    up = E.upcoming(engine, T)
    PV.ekle(up, EK.for_upcoming(engine, T))
    _check(up, EK.NOT_RAKAM)
    fair = {"id": "F1", "starts_on": "2026-09-10", "ends_on": "2026-09-14", "crm_event_ids_json": json.dumps([GUID])}
    r = {"sql": ["SELECT 1 AS adet FROM dbo.LG_411_01_STLINE"], "sqlOnceki": ["SELECT 2 AS adet FROM dbo.LG_211_01_STLINE"],
         "dataEnd": "2026-09-20", "computedAt": "2026-09-21T07:45:00"}
    k = EK.for_result(engine, T, "F1", SimpleNamespace(firms=lambda: {2026: "411"}), r, fair).to_dict()
    assert PV.problems({"kaynaklar": k}) == []
    conns = {s["id"]: s["connection"] for s in k["sources"].values()}
    assert conns["etk.logo.sonuc.1"] == "logo" and conns["etk.logo.temel.1"] == "logo" and conns["etk.crm.siparis"] == "crm"
    assert any(i.startswith("etk.crm.etkinlik.") for i in conns)


# ------------------------------------------------------------------ M28 kurumsal ilişkiler


def _pa_st():
    return PA.settings_from(lambda k, d="": d)


def test_m28_ana_ekran_ve_rapor(engine):
    st = _pa_st()
    home = PA.home(engine, T, "ayse", st)
    PV.ekle(home, PAK.for_home(engine, T))
    _check(home, PAK.NOT_RAKAM)
    rep = PA.report(engine, T, "ayse", st, 2026)
    rep["crm"] = {"types": [{"type": 12, "label": "Tanıtım", "orders": 3, "books": 40}], "excludedStatus": [], "error": None}
    PV.ekle(rep, PAK.for_report(engine, T, 2026, [12], []))
    _check(rep, PAK.NOT_RAKAM + ("crm.excludedStatus",))
    gifts = PA.list_gifts(engine, T, month="2026-09")
    PV.ekle(gifts, PAK.for_gifts(engine, T, "2026-09", "", ""))
    _check(gifts, PAK.NOT_RAKAM)


def test_m28_kisi_karti_kisisel_veri_kayda_girmez(engine):
    p = PA.create_person(engine, T, "ayse", {"name": "Ayşe Gizli", "email": "ayse.gizli@ornek.example", "phone": "05320000000"})
    for k in (PAK.for_people(engine, T, False), PAK.for_person(engine, T, p["id"], None)):
        text = json.dumps(k.to_dict(), ensure_ascii=False)
        assert "Ayşe Gizli" not in text and "ayse.gizli@ornek.example" not in text and "05320000000" not in text
        assert PV.problems({"kaynaklar": k.to_dict()}) == []
