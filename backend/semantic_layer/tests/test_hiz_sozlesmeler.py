"""Hız (2026-09-29) — M6 sözleşme listesi ve özeti (`contracts_hizli`): eski hesap = yeni hesap.

- Liste: `sayfa` cevabı `editorial.page` ile aynı; aynı süzgeç ikinci kez CRM'e gitmez; süzgeç/sayfa/kiracı anahtarda;
  «Verileri yenile» kaynağı bekler; uç satıra portal rozetini koyunca bellekteki kayıt değişmez.
- Özet: editoryal masam hazırlığındaki `contracts` parçası `editorial.summary` ile aynı; uyarı günü farklıysa, hazırlık
  eskiyse ya da «Verileri yenile»de CRM okunur (bellek penceresiyle).
- Sorgu bilgisi: kaynaksız rakam yok, SQL aynı (`test_sorgu_bilgisi_telif` denetimi).
"""
from __future__ import annotations

import time

from semantic_bridge import contracts_hizli as H
from semantic_bridge import contracts_kaynak as CK
from semantic_bridge import editorial as E
from semantic_bridge import provenance as P
from semantic_bridge.editorial_home import EditorialHomeSnapshots
from semantic_layer.tests.test_royalty import G1, G2, P1, engine  # noqa: F401
from semantic_layer.tests.test_sorgu_bilgisi_telif import SCHEMA, _check, _crm_run

SUMMARY = [
    ("AS yururlukte", [{"toplam": 120, "yururlukte": 90, "yenilemede": 4, "yaklasan": 6, "ort_telif": 9.4, "telif_dolu": 70}]),
    ("CAST(s.statuscode AS int)", [{"statuscode": "Aktif - Sözleşme", "kod": 100000000, "n": 80}]),
    ("CAST(s.new_SozlesmeTipi AS int)", [{"new_SozlesmeTipi": "Telif Alış", "kod": 5, "n": 110}]),
]
PAGE = [
    ("SELECT COUNT(*) AS n", [{"n": 2}]),
    ("OFFSET", [{"new_sozlesmeId": G1, "new_name": "2026-1", "new_Telif": 10, "new_sozlesmeavanstutari": 5000,
                 "kalan_gun": 40, "new_SozlesmeSuresiYil": 5, "r_cogaltma": 1, "tip_kod": 5, "durum_kod": 100000000},
                {"new_sozlesmeId": G2, "new_name": "2026-2", "new_Telif": 12, "kalan_gun": -3}]),
    ("SELECT sk.new_sozlesmeid", [{"new_sozlesmeid": G1, "new_kitapId": P1, "new_name": "Kitap"}]),
    ("SELECT t.new_sozlesmeid", [{"new_sozlesmeid": G1, "kisi": "Ayşe Yazar", "new_Odeme": 100}]),
]


def _counting(markers):
    run = _crm_run(markers)
    calls: list[str] = []

    def wrapped(sql):
        calls.append(sql)
        return run(sql)
    return wrapped, calls


class _Home:
    """Editoryal masam hazırlığının yerine: yalnız `directory()`."""

    def __init__(self, root):
        self.root = root

    def directory(self):
        return self.root


def test_page_is_the_same_and_the_crm_part_is_kept():
    H.LISTE.dusur()
    run, calls = _counting(PAGE)
    flt = {"q": "", "status": 100000000, "kind": None, "expiring_days": 60}
    old = E.page(SCHEMA, run, 0, order="bitis", **flt)
    n = len(calls)
    new = H.sayfa("t-hiz", SCHEMA, run, 0, order="bitis", **flt)
    assert new == old and len(calls) == 2 * n                   # ilk okuma: aynı dört sorgu, aynı cevap
    new["items"][0]["portal"] = {"id": "x"}                      # uç rozeti koyar
    again = H.sayfa("t-hiz", SCHEMA, run, 0, order="bitis", **flt)
    assert len(calls) == 2 * n and again == old                  # bellekten; rozet belleğe sızmadı
    assert "portal" not in again["items"][0]
    H.sayfa("t-hiz", SCHEMA, run, 1, order="bitis", **flt)       # başka sayfa: başka anahtar
    H.sayfa("t-hiz", SCHEMA, run, 0, order="bitis", **dict(flt, q="ayşe"))
    H.sayfa("t-baska", SCHEMA, run, 0, order="bitis", **flt)
    assert len(calls) == 5 * n
    fresh = H.sayfa("t-hiz", SCHEMA, run, 0, order="bitis", fresh=True, **flt)   # Verileri yenile: kaynağı bekler
    assert fresh == old and len(calls) == 6 * n
    H.LISTE.dusur()


def test_summary_from_the_editorial_home_part(tmp_path):
    H.OZET.dusur()
    run, calls = _counting(SUMMARY)
    old = E.summary(SCHEMA, run, 60)
    calls.clear()
    EditorialHomeSnapshots.save(tmp_path / "contracts.json", {"data": old, "updatedAt": time.time(), "error": None, "sql": []})
    home = _Home(tmp_path)
    out, at = H.ozet("t-hiz", SCHEMA, run, 60, home)
    assert out == old and at and calls == []                    # hazırlıktan: CRM'e gidilmedi, rakam aynı
    out, at = H.ozet("t-hiz", SCHEMA, run, 30, home)            # uyarı günü farklı: hazırlık kullanılmaz
    assert at is None and out["warnDays"] == 30 and len(calls) == 3
    out, at = H.ozet("t-hiz", SCHEMA, run, 60, home, fresh=True)   # Verileri yenile
    assert at is None and out == E.summary(SCHEMA, _crm_run(SUMMARY), 60) and len(calls) == 6
    EditorialHomeSnapshots.save(tmp_path / "contracts.json",
                                {"data": old, "updatedAt": time.time() - 3 * H.HAZIR_EN_ESKI, "error": None, "sql": []})
    H.OZET.dusur()
    out, at = H.ozet("t-hiz", SCHEMA, run, 60, home)            # tur durmuş: eski hazırlık yerine CRM
    assert at is None and out == old and len(calls) == 9
    out, at = H.ozet("t-hiz", SCHEMA, run, 60, None)            # bellekten (hazırlık yok)
    assert out == old and len(calls) == 9
    H.OZET.dusur()


def test_query_info_still_covers_every_number(tmp_path, engine):  # noqa: F811
    H.OZET.dusur()
    H.LISTE.dusur()
    run = _crm_run(SUMMARY)
    old = E.summary(SCHEMA, run, 60)
    EditorialHomeSnapshots.save(tmp_path / "contracts.json", {"data": old, "updatedAt": time.time(), "error": None, "sql": []})
    out, at = H.ozet("t-hiz", SCHEMA, run, 60, _Home(tmp_path))
    k = _check(P.ekle(out, CK.for_summary(SCHEMA, out, engine, at)), CK.NOT_RAKAM)
    ozet = k["sources"]["sozlesme.crm.ozet"]
    assert ozet["sql"].endswith(E.summary_sql(SCHEMA, 60)) and "hazırlığında" in ozet["description"]
    assert ozet["stats"]["dbMs"] == 7

    page = H.sayfa("t-hiz", SCHEMA, _crm_run(PAGE), 0, order="bitis", q="", status=100000000, kind=None, expiring_days=60)
    for c in page["items"]:
        c["portal"] = None
    k = _check(P.ekle(page, CK.for_page(engine, "t-hiz", SCHEMA, page, 0, status=100000000, expiring_days=60)), CK.NOT_RAKAM)
    assert k["sources"]["sozlesme.crm.liste"]["sql"].endswith(E.list_sql(SCHEMA, 0, order="bitis", q="", status=100000000,
                                                                          kind=None, expiring_days=60))
    H.OZET.dusur()
    H.LISTE.dusur()
