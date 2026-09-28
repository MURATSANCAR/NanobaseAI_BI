"""Sorgu bilgisi — Grup 4: M16 lansman, M17 backlist, M19 içerik ve tasarım, M53 set / hediye, M24 katalog ve bülten,
H2 okur veri tabanı.

Her kaynak kurucusu için: kayıt tutarlı (`problems` boş), her SQL çalışan metin (yer tutucu yok), bağlantı Logo / CRM /
portal; Logo / CRM veritabanı adı verildiyse metin «USE [..]» ile başlar (kopyala-çalıştır). Önbellekten gelen rakamda
okuma işinin kaydettiği asıl sorgu `origin` olarak görünür. Örnek bir uç çıktısında her rakam bir kaynağa bağlıdır
(`uncovered_numbers` boş). Veriler yapaydır; gerçek CRM / Logo kabulü `scripts/acceptance/sorgu-bilgisi/pazarlama_*.py`.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from semantic_bridge import budget as B
from semantic_bridge import catalogs as CAT
from semantic_bridge import catalogs_kaynak as KCAT
from semantic_bridge import marketing_creative as MC
from semantic_bridge import marketing_creative_kaynak as KC
from semantic_bridge import newsletters as NL
from semantic_bridge import provenance as PV
from semantic_bridge import readers as R
from semantic_bridge import readers_kaynak as KR
from semantic_bridge import sets as SETS
from semantic_bridge import sets_kaynak as KS
from semantic_bridge.marketing import backlist as BL
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import kaynak_backlist as KB
from semantic_bridge.marketing import kaynak_lansman as KL
from semantic_bridge.marketing import launch as L
from semantic_layer.store.catalog_store import open_store

T = "t1"
SCHEMA = "Timas_MSCRM.dbo"
LOGO_DB = "TIGER"
GUID = "11111111-2222-3333-4444-555555555555"
MODS = (C, B, L, BL, MC, SETS, CAT, NL, R)


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for m in MODS:
        m._ready.discard(id(e))
        m.ensure(e)
    yield e
    for m in MODS:
        m._ready.discard(id(e))


def _ok(k: PV.Kaynaklar) -> dict:
    d = {"kaynaklar": k.to_dict()}
    assert PV.problems(d) == [], PV.problems(d)
    src = d["kaynaklar"]["sources"]
    assert src, "kaynak yok"
    for s in src.values():
        assert s["sql"].strip(), s["id"]
        assert PV.placeholders_left(s["sql"]) == [], (s["id"], s["sql"][:200])
        assert s["connection"] in ("logo", "crm", "portal")
        if s["connection"] in ("logo", "crm") and s["database"]:
            assert s["sql"].lstrip().upper().startswith(f"USE [{s['database'].upper()}]"), s["sql"][:80]
    json.dumps(d, default=str)
    return d["kaynaklar"]


# ------------------------------------------------------------------ M16 lansman


def _launch():
    return {"id": "L1", "planId": "P1", "stokKodu": "S1", "yayinGunu": "2026-09-01", "okuma": "2026-09-20T10:00:00",
            "crmKitapId": GUID,
            "ozet": {"veriSonuLogo": "2026-09-19", "hedef": {"2026": {}},
                     "sql": {"siparis": "SELECT s.new_name FROM new_siparisBase s WHERE s.statecode = 0",
                             "fatura": ["SELECT 1 AS a FROM LG_411_01_STLINE", "SELECT 2 AS b FROM LG_211_01_STLINE"]}}}


def test_m16_lansman_kaynaklari(engine):
    full = _launch()
    k = _ok(KL.for_launch(engine, T, full, LOGO_DB))
    # okuma işinin çalıştırdığı Logo metinleri origin; veritabanı adıyla
    assert k["sources"]["lansman.fatura.2"]["database"] == LOGO_DB
    assert "lansman.fatura.1" in k["sources"]["lansman.gunluk"]["origin"]
    assert k["fields"]["sinyal"].startswith("hesap:")
    _ok(KL.for_tracking(engine, T, full, LOGO_DB))
    ev = _ok(KL.for_events(engine, full, SCHEMA))
    assert ev["sources"]["lansman.etkinlik.crm"]["connection"] == "crm"
    _ok(KL.for_media(engine, full))
    _ok(KL.for_crm_todo(engine, full, SCHEMA))
    _ok(KL.for_reviews(engine, T, full, LOGO_DB))
    _ok(KL.for_list(engine, T, {"items": [{"id": "L1"}]}))
    _ok(KL.for_today(engine, T))


# ------------------------------------------------------------------ M17 backlist


def test_m17_backlist_kaynaklari(engine):
    _ok(KB.for_list(engine, T, {"items": []}, LOGO_DB))
    _ok(KB.for_detail(engine, T, "S1", LOGO_DB))
    _ok(KB.for_agenda(engine, T, {"items": []}, LOGO_DB))
    _ok(KB.for_effects(engine, T, 2026, True, LOGO_DB))
    _ok(KB.for_activations(engine, T, {"items": []}))
    _ok(KB.for_plan_books(engine, "P1"))


# ------------------------------------------------------------------ M19 içerik ve tasarım


def test_m19_icerik_ozet_her_rakam_kaynakli(engine):
    trace: dict = {}
    out = MC.summary(engine, T, "ayse", True, True, date(2026, 9, 28), trace=trace)
    PV.ekle(out, KC.for_summary(engine, T, "ayse", trace))
    _ok_payload(out)
    _ok(KC.for_requests(engine, T, {"items": [{"id": "R1"}]}, 0))
    _ok(KC.for_pending(engine, T))
    _ok(KC.for_request(engine, T, "R1", False))
    _ok(KC.for_archive(engine, T, 0))
    b = _ok(KC.for_books(SCHEMA, "deniz", 0))
    assert b["sources"]["icerik.crm.ara"]["connection"] == "crm"


def _ok_payload(out: dict, ignore=()) -> None:
    assert out["kaynaklar"] and not out["kaynaklar"].get("error"), out["kaynaklar"]
    assert PV.uncovered_numbers(out, ignore) == []
    assert PV.problems(out) == []


# ------------------------------------------------------------------ M53 set / hediye


def test_m53_set_hediye_kaynaklari(engine):
    _ok(KS.for_list(engine, T, {"items": []}, LOGO_DB))
    _ok(KS.for_set(engine, T, "SET1", {"stokKodu": "S1", "bilesenler": [{"stok": "A1"}, {"stok": "A2"}]}, LOGO_DB))
    _ok(KS.for_effect(engine, T, {}, ["S1"], LOGO_DB))
    _ok(KS.for_suggestions(engine, {"items": [{"bilesenler": [{"stok": "A1"}]}]}, LOGO_DB))
    _ok(KS.for_meta(engine, LOGO_DB))
    _ok(KS.for_status(engine, LOGO_DB))
    _ok(KS.for_books(engine, LOGO_DB))
    _ok(KS.for_pairs(engine, {}, LOGO_DB))
    _ok(KS.for_offers(engine, T))
    _ok(KS.for_offer(engine, T, {"id": "O1", "adet": 25}, LOGO_DB))
    acc = _ok(KS.for_accounts(SCHEMA, "kitap", 0))
    assert all(s["connection"] == "crm" for s in acc["sources"].values())
    _ok(KS.for_history(SCHEMA, GUID))
    _ok(KS.for_promo(engine, LOGO_DB))


def test_m53_yenileme_isinin_logo_sorgusu_origin(engine):
    """Set yenilemesinin kaydettiği çalışmış Logo metni kaynak listesinde, veritabanı adıyla."""
    SETS.meta_set(engine, "sql", {"items": [{"conn": "logo", "sql": "SELECT I.CODE FROM LG_411_ITEMS I", "rows": 3, "dbMs": 12,
                                             "at": "2026-09-28T02:00:00"}]})
    k = _ok(KS.for_list(engine, T, {"items": []}, LOGO_DB))
    logo = [s for s in k["sources"].values() if s["connection"] == "logo"]
    assert logo and logo[0]["sql"].startswith(f"USE [{LOGO_DB}]")


# ------------------------------------------------------------------ M24 katalog ve bülten


def test_m24_katalog_bulten_kaynaklari(engine):
    _ok(KCAT.for_meta(engine, T, LOGO_DB))
    _ok(KCAT.for_catalogs(engine, T, {"items": [{"id": "C1"}]}, ""))
    _ok(KCAT.for_catalog(engine, T, "C1", LOGO_DB))
    _ok(KCAT.for_candidates(engine, T, LOGO_DB))
    _ok(KCAT.for_newsletters(engine, T, {"items": [{"id": "N1"}]}, ""))
    nl = _ok(KCAT.for_newsletter(engine, T, "N1", {"segment": {}}, SCHEMA, LOGO_DB))
    seg = nl["sources"]["bulten.segment"]
    assert seg["connection"] == "crm" and "FullName" not in seg["sql"] and "EMailAddress1" not in seg["sql"]
    _ok(KCAT.for_segment(SCHEMA, NL.normalize_segment({})))
    _ok(KCAT.for_report(engine, T, {"items": [], "crm": {}}, SCHEMA))


# ------------------------------------------------------------------ H2 okur veri tabanı


def test_h2_okur_kaynaklari_ve_origin(engine):
    R.sql_runs_set(engine, T, [{"conn": "crm", "sql": "SELECT c.ContactId FROM Timas_MSCRM.dbo.ContactBase c WHERE c.statecode = 0",
                                "rows": 5, "dbMs": 10, "at": "2026-09-28T03:20:00"}])
    k = _ok(KR.for_overview(engine, T))
    org = [s for s in k["sources"].values() if s["connection"] == "crm"]
    assert org, "okuma turunun CRM sorgusu origin olmalı"
    assert any(org[0]["id"] in s["origin"] for s in k["sources"].values())
    _ok(KR.for_sources(engine, T))
    _ok(KR.for_card(engine, T, "R1"))
    _ok(KR.for_search(engine, T))
    _ok(KR.for_subject(engine, T))
    _ok(KR.for_candidates(engine, T, "bekliyor", 0))
    _ok(KR.for_preview(engine, T))
    _ok(KR.for_segments(engine, T, "", ""))
    _ok(KR.for_segment(engine, T, "SG1"))
    _ok(KR.for_imports(engine, T))
    _ok(KR.for_import(engine, T, "I1", "", 0))
    _ok(KR.for_exports(engine, T, 0))
    _ok(KR.for_status(engine, T))
    _ok(KR.for_mine(engine, T))


def test_h2_kisisel_veri_kayda_girmez(engine):
    """Arama ve KVKK başvurusunda aranan değer (e-posta) sorgu bilgisine yazılmaz; kayıtta sonuç satırı yok."""
    for k in (KR.for_search(engine, T), KR.for_subject(engine, T)):
        text = json.dumps(k.to_dict(), ensure_ascii=False)
        assert "ayse.okur@ornek.com" not in text
        for s in k.to_dict()["sources"].values():
            assert set(s) >= {"sql", "stats"} and "rows" not in s


def test_h2_tur_kaydi_durum_cevabina_karismaz(engine):
    """Kaydedilen çalışmış SQL listesi ayrı meta anahtarında: durum cevabındaki son tur raporunda sql alanı yok
    (yoksa satır sayısı ve süre sayıları kaynaksız rakam olurdu)."""
    R.sql_runs_set(engine, T, [{"conn": "crm", "sql": "SELECT 1", "rows": 1, "dbMs": 1, "at": datetime.now(timezone.utc).isoformat()}])
    assert "SELECT 1" not in json.dumps(R.last_run(engine, T))
    assert R.sql_runs(engine, T)[0]["sql"] == "SELECT 1"
