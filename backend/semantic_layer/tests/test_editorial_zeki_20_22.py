"""Müşteri kayıtları ZEKI-20/21/22 (2026-09-29) — sözleşme listesi ve çevirmenler.

- ZEKI-20: «Bitişi en yakın» önce süresi devam edenleri (bugüne en yakın bitiş başta), sonra bitmişleri (en son biten
  başta), en sonda süresiz / bitişi girilmemiş olanları getirir; süre süzgeci (devam | bitmis | suresiz) etkin
  sözleşmeleri örtüşmeden böler ve özet üç sayıyı verir.
- ZEKI-21: aynı kitap kartı bir sözleşmede bir kez girer; aynı adı taşıyan farklı kartlar stok koduyla ayrı kalır.
- ZEKI-22: çevirmen listesi sözleşmedeki kaynak dile (`new_orjinaldili`) göre süzülür; dili girilmemiş kişi
  «Belirtilmemiş» (`yok`) grubundadır; rakamların hepsi bir kaynağa bağlı.
"""
from __future__ import annotations

import pytest

from semantic_bridge import contracts_kaynak as CK
from semantic_bridge import contributors_kaynak as KK
from semantic_bridge import editorial as E
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_kaydi as SK
from semantic_layer.tests.test_royalty import G1, G2, P1, P2, TEN, engine  # noqa: F401
from semantic_layer.tests.test_sorgu_bilgisi_telif import SCHEMA, _check, _crm_run

LANG = "0b1c2d3e-aaaa-bbbb-cccc-ddddeeeeffff"
PERSON = "0a1b2c3d-1111-2222-3333-444455556666"


# ------------------------------------------------------------------ ZEKI-20


def test_term_filter_splits_contracts_without_overlap():
    running, ended, open_ended = (E._where("x.", term=t) for t in E.TERMS)
    assert "s.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date)" in running
    assert "s.new_SozlesmeBitisTarihi < CAST(GETDATE() AS date)" in ended
    assert "ISNULL(s.new_suresizsozlesme, 0) = 0" in running and "ISNULL(s.new_suresizsozlesme, 0) = 0" in ended
    assert "s.new_SozlesmeBitisTarihi IS NULL" in open_ended and "<> 0" in open_ended
    assert E._where("x.") == "s.statecode = 0"                      # süzgeç boşsa eskisi gibi
    with pytest.raises(E.EditorialError):
        E._where("x.", term="bitmis'; DROP")


def test_nearest_end_order_puts_running_contracts_first():
    sql = E.list_sql(SCHEMA, 0, order="bitis", q="", status=None, kind=None, expiring_days=None, term="")
    order = sql.split(" ORDER BY ", 1)[1]
    # Grup: devam 0, bitmiş 1, süresiz/girilmemiş 2; devam edenler bitişe artan, bitmişler azalan.
    assert order.startswith("CASE WHEN (ISNULL(s.new_suresizsozlesme, 0) = 0 AND s.new_SozlesmeBitisTarihi >= ")
    assert "THEN 0 WHEN" in order and "THEN 1 ELSE 2 END" in order
    assert "THEN s.new_SozlesmeBitisTarihi END DESC" in order
    assert "CASE WHEN s.new_SozlesmeBitisTarihi IS NULL THEN 1 ELSE 0 END" not in order   # eski sıra


def test_summary_counts_each_term_and_query_info_covers_them(engine):  # noqa: F811
    run = _crm_run([
        ("AS yururlukte", [{"toplam": 10, "yururlukte": 6, "yenilemede": 1, "yaklasan": 2, "ort_telif": 9, "telif_dolu": 5,
                            "sure_devam": 5, "sure_bitmis": 3, "sure_suresiz": 2}]),
        ("CAST(s.statuscode AS int)", []),
        ("CAST(s.new_SozlesmeTipi AS int)", []),
    ])
    out = E.summary(SCHEMA, run, 60)
    assert out["terms"] == {"devam": 5, "bitmis": 3, "suresiz": 2}
    assert "AS sure_suresiz" in E.summary_sql(SCHEMA, 60)
    k = _check(P.ekle(out, CK.for_summary(SCHEMA, out, engine)), CK.NOT_RAKAM)
    assert k["fields"]["terms"] == "hesap:ozet"


# ------------------------------------------------------------------ ZEKI-21


def _page_run(books):
    return _crm_run([
        ("SELECT COUNT(*) AS n", [{"n": 1}]),
        ("OFFSET", [{"new_sozlesmeId": G1, "new_name": "2026-1", "kalan_gun": 10}]),
        ("SELECT sk.new_sozlesmeid", books),
        ("SELECT t.new_sozlesmeid", []),
    ])


def test_same_book_card_is_listed_once_and_same_title_cards_keep_stock_code(engine):  # noqa: F811
    books = [
        {"new_sozlesmeid": G1, "new_kitapId": P1, "new_name": "Binbir Gece Masalları", "new_StokKodu": "K-1"},
        {"new_sozlesmeid": G1, "new_kitapId": P1.upper(), "new_name": "Binbir Gece Masalları", "new_StokKodu": "K-1"},
        {"new_sozlesmeid": G1, "new_kitapId": P2, "new_name": "Binbir Gece Masalları", "new_StokKodu": "K-2",
         "new_isbn13": "9780000000002"},
    ]
    out = E.page(SCHEMA, _page_run(books), 0, order="bitis", term="devam")
    got = out["items"][0]["books"]
    assert [b["stockCode"] for b in got] == ["K-1", "K-2"]          # aynı kart bir kez; farklı kart ayrı
    assert got[1]["isbn"] == "9780000000002"
    assert "k.new_StokKodu" in E.books_sql(SCHEMA, [G1])
    k = _check(P.ekle(out, CK.for_page(engine, TEN, SCHEMA, out, 0, term="devam")), CK.NOT_RAKAM)
    assert "s.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date)" in k["sources"]["sozlesme.crm.sayim"]["sql"]


# ------------------------------------------------------------------ ZEKI-22


def test_language_filter_sql():
    sql = E.contributors_count_sql(SCHEMA, ["Tercüme"], "", LANG)
    assert "EXISTS (SELECT 1 FROM Timas_MSCRM.dbo.new_sozlesmetarafiBase ct" in sql
    assert "cs.new_orjinaldili" in sql and f"cd.new_dilId = '{LANG}'" in sql
    none = E.contributors_list_sql(SCHEMA, ["Tercüme"], 0, "", "son", E.LANG_NONE)
    assert "NOT EXISTS (SELECT 1 FROM" in none
    assert "new_new_sozlesme_new_dilBase" not in sql + none         # dil kapsamı kaynak dil değildir
    assert E.contributors_count_sql(SCHEMA, ["Tercüme"]) == E.contributors_count_sql(SCHEMA, ["Tercüme"], "", "")
    with pytest.raises(E.EditorialError):
        E.contributors_count_sql(SCHEMA, ["Tercüme"], "", "İngilizce' OR 1=1 --")


def _lang_run():
    return _crm_run([
        ("AS kisi", [{"new_dilId": LANG, "dil": "Arapça", "kisi": 4}]),
        ("COUNT(*) AS n", [{"n": 7, "son12_kisi": 1, "katki": 9}]),
        ("OFFSET", [{"ContactId": PERSON, "FullName": "Ayşe Çevirmen", "eser": 3, "son": "2026-01-01", "son12": 1}]),
        ("new_Katilimsaglayan IN", [{"new_Katilimsaglayan": PERSON, "rol": "Tercüme", "eser": 3}]),
        ("SELECT DISTINCT ct.new_kisi", [{"new_kisi": PERSON.upper(), "new_dilId": LANG, "dil": "Arapça"},
                                         {"new_kisi": PERSON, "new_dilId": LANG, "dil": "Arapça"}]),
    ])


def test_translator_list_with_languages_and_facets_have_sources():
    roles = ["Tercüme"]
    run = _lang_run()
    out = SK.bagla_run(run, lambda r: E.contributors_page(SCHEMA, r, roles, 0, lang=LANG, langs=True),
                       lambda o, log: KK.for_contributors(o, log, SCHEMA, roles, 0, "", "son", LANG, True))
    assert out["items"][0]["languages"] == ["Arapça"]
    k = _check(out, KK.NOT_RAKAM)
    assert LANG in k["sources"]["kisiler.sayim"]["sql"] and "kisiler.diller" in k["sources"]
    assert "Ayşe Çevirmen" not in str(k)                             # kişisel veri kayda girmez

    plain = SK.bagla_run(run, lambda r: E.contributors_page(SCHEMA, r, roles, 0),
                         lambda o, log: KK.for_contributors(o, log, SCHEMA, roles, 0))
    assert "languages" not in plain["items"][0]                      # yazar ve serbest sekmesi eskisi gibi

    fac = SK.bagla_run(run, lambda r: E.language_facets(SCHEMA, r, roles), lambda o, log: KK.for_languages(o, log, SCHEMA, roles))
    assert fac["items"] == [{"id": LANG, "name": "Arapça", "people": 4}] and fac["unspecified"] == 7
    k = _check(fac, KK.NOT_RAKAM)
    assert "NOT EXISTS" in k["sources"]["kisiler.dilYok"]["sql"]
