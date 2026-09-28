"""Ortak yapı taşı 5 + öneri 9 — kitap benzerliği dizini (`semantic_bridge.book_similarity`) ve bağlandığı yerler:
M15 emsal adayı (satış sütunları ilk baskı veri kümesinden), M39 emsal bulda aday genişletme (sözcük + anlam sırası),
M1 başvuru (maske), artımlı dizin (değişmeyen kitap yeniden gömülmez, çıkan kitap pasif).

Gömme servisi sahte: kelimelerden deterministik vektör (aynı kelimeyi paylaşan metinler yakın). Gerçek gömme ve CRM
kabulü test sunucusunda (scripts/acceptance/zeki-ortak-belge-benzerlik).
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from semantic_bridge import book_similarity as BS
from semantic_layer.store.catalog_store import open_store

T = "t1"
DIM = 64


def fake_embed(calls=None):
    def emb(texts):
        if calls is not None:
            calls.append(list(texts))
        out = []
        for t in texts:
            v = [0.0] * DIM
            for w in BS._fold(BS.clean(t)).replace(".", " ").replace(":", " ").split():
                if len(w) < 4:
                    continue
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                v[h % DIM] += 1.0
            v[0] += 0.01
            out.append(v)
        return out
    return emb


def _book(kid, ad, stok, ozet, kitaplik="Kişisel Gelişim", tema=None, kategori=None):
    return {"kitap_id": kid, "stok_kodu": stok, "ad": ad, "yazar": "Yazar", "kitaplik": kitaplik, "kategori": kategori,
            "turler": None, "temalar": tema, "ozet": ozet, "spot": None, "crm_degisme": "2026-09-01T00:00:00"}


BOOKS = [
    _book("K1", "Zihin Haritası", "S1", "<p>Alışkanlık zihin dikkat odak üzerine</p>", tema="Alışkanlık"),
    _book("K2", "Küçük Adımlar", "S2", "alışkanlık zihin dikkat değişim rehberi", tema="Alışkanlık"),
    _book("K3", "Denizin Altı", "S3", "balık deniz mercan çocuk masalı", kitaplik="Çocuk"),
    _book("K4", "Odak Sanatı", None, "dikkat odak zihin çalışma", tema="Verimlilik"),
    _book("K5", "Mercan Adası", "S5", "deniz mercan balık macera", kitaplik="Çocuk"),
]


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    BS._ready.discard(id(e))
    BS._indexes.clear()
    BS.ensure(e)
    return e


CFG = {"textChars": 3000, "batch": 2}


def test_book_text_cleans_html_skips_author_and_cuts_at_sentence():
    t = BS.book_text({**BOOKS[0], "yazar": "Gizli Yazar"}, 3000)
    assert "<p>" not in t and "Gizli Yazar" not in t and "Tema: Alışkanlık" in t and t.startswith("Zihin Haritası")
    long = BS.book_text({"ad": "A", "ozet": "Cümle bir. " * 200}, 300)
    assert len(long) <= 300 and long.endswith(".")


def test_vector_roundtrip_is_unit_float32():
    v = BS.unit([3.0, 4.0])
    assert abs(v[0] - 0.6) < 1e-6 and BS.decode(BS.encode(v)).tolist() == v.tolist()
    with pytest.raises(BS.SimilarityError):
        BS.unit([0.0, 0.0])


def test_incremental_index(engine):
    calls = []
    out = BS.build_index(engine, T, BOOKS, fake_embed(calls), CFG)
    assert out["gomulen"] == 5 and out["degismeyen"] == 0 and sum(len(c) for c in calls) == 5 and len(calls) == 3
    calls.clear()
    changed = [dict(b) for b in BOOKS[:4]]
    changed[1]["ozet"] = "tamamen yeni özet"
    out = BS.build_index(engine, T, changed, fake_embed(calls), CFG)
    assert out["gomulen"] == 1 and out["degismeyen"] == 3 and out["pasif"] == 1      # K5 CRM'de yok → pasif
    assert BS.status(engine, T)["kitap"] == 4 and BS.status(engine, T)["toplam"] == 5
    calls.clear()
    out = BS.build_index(engine, T, BOOKS, fake_embed(calls), CFG)                    # K5 döndü: gömülmeden etkin
    assert BS.status(engine, T)["kitap"] == 5 and out["gomulen"] == 1                  # yalnız K2 (özet geri değişti)


def test_similar_by_book_and_text_with_filters(engine):
    BS.build_index(engine, T, BOOKS, fake_embed(), CFG)
    r = BS.similar_books(engine, T, stok_kodu="S1", n=3)
    assert r["hazir"] and r["items"][0]["kitapId"] in ("K2", "K4") and "K1" not in [x["kitapId"] for x in r["items"]]
    k2 = next(x for x in r["items"] if x["kitapId"] == "K2")
    assert any("aynı kitaplık" in g for g in k2["gerekce"]) and any("ortak tema: Alışkanlık" in g for g in k2["gerekce"])
    assert [x["sira"] for x in r["items"]] == [1, 2, 3]
    r = BS.similar_books(engine, T, stok_kodu="S1", n=5, suzgec={"stokluOlsun": True, "haric": ["S2"]})
    assert {x["kitapId"] for x in r["items"]} == {"K3", "K5"}                         # K4 stoksuz, K2 hariç
    r = BS.similar_books(engine, T, metin="deniz mercan balık", n=2, embed=fake_embed())
    assert {x["kitapId"] for x in r["items"]} == {"K3", "K5"} and r["items"][0]["gerekce"] == ["özet benzerliği"]
    missing = BS.similar_books(engine, T, stok_kodu="YOK", n=3)
    assert missing["hazir"] is False and "dizininde yok" in missing["not"]
    with pytest.raises(BS.SimilarityError):
        BS.similar_books(engine, T, stok_kodu="S1", n=0)


def test_empty_index_is_explicit(engine):
    r = BS.similar_books(engine, T, stok_kodu="S1", n=3)
    assert r["hazir"] is False and "kurulmadı" in r["not"]


def test_reasons_are_rule_based():
    g = BS.reasons({"kitaplik": "Roman", "temalar": "Aşk, Savaş", "kategori": "Edebiyat > Roman"},
                   {"kitaplik": "roman", "temalar": "Savaş; Tarih", "kategori": "Edebiyat > Roman"})
    assert g[0].startswith("aynı kitaplık") and "ortak tema: Savaş" in g and any("ortak kategori" in x for x in g)


# ------------------------------------------------------------------ M15 emsal adayı


def test_marketing_emsal_candidates_use_m10_sales(engine):
    from semantic_bridge.marketing import plans as P

    BS.build_index(engine, T, BOOKS, fake_embed(), CFG)
    ds = SimpleNamespace(outcomes={"S2": SimpleNamespace(months=[10, 20, 30, 40, 50, 60])}, books={})
    card = {"kitap": {"stokKodu": "S1", "ad": "Zihin Haritası"}, "emsal": {"hazir": True, "crmEmsalSayisi": 0, "items": []},
            "metinler": []}
    out = P.emsal_candidates(engine, T, SimpleNamespace(ds=ds), card, 3)
    assert out["gerekli"] and out["hazir"]
    s2 = next(x for x in out["items"] if x["stokKodu"] == "S2")
    assert s2["ilk3"] == 60 and s2["ilk6"] == 210 and s2["ilk12"] is None            # SQL kaynaklı veri kümesi
    assert all(x["stokKodu"] for x in out["items"])                                     # stoksuz kitap aday olmaz
    card["emsal"]["crmEmsalSayisi"] = 2
    assert P.emsal_candidates(engine, T, None, card, 3)["gerekli"] is False


def test_marketing_emsal_candidates_fall_back_to_card_text(engine):
    from semantic_bridge.marketing import plans as P

    BS.build_index(engine, T, BOOKS, fake_embed(), CFG)
    seen = {}

    def similar(engine_, tenant, **kw):
        seen.setdefault("calls", []).append(kw)
        if kw.get("stok_kodu"):
            return {"hazir": False, "items": [], "not": "dizinde yok"}
        return BS.similar_books(engine_, tenant, embed=fake_embed(), **kw)

    card = {"kitap": {"stokKodu": "YENI", "ad": "Mercan"}, "emsal": {"hazir": False, "items": []},
            "metinler": [{"alan": "new_ozet", "metin": "deniz mercan balık"}]}
    out = P.emsal_candidates(engine, T, None, card, 2, similar=similar)
    assert [c.get("metin") is not None for c in seen["calls"]] == [False, True]
    assert {x["stokKodu"] for x in out["items"]} == {"S3", "S5"} and "hazır değil" in out["not"]


# ------------------------------------------------------------------ M39 emsal bul


def test_pazar_comparables_add_meaning_candidates_without_changing_rules(tmp_path, monkeypatch):
    from semantic_bridge import pazar as PZ
    from semantic_layer.tests import test_pazar as TP

    monkeypatch.setenv("PAZAR_DIR", str(tmp_path / "raporlar"))
    monkeypatch.setenv("PAZAR_CATEGORY_SOURCE", "kitaplik")
    e = open_store("sqlite://").engine
    PZ._ready.discard(id(e))
    PZ.ensure(e)
    TP._seed(e)
    base = PZ.comparables(e, TP.T, {"q": "masal"}, None)
    assert [x["id"] for x in base["timas"]] == []                                     # ortak sözcük yok
    out = PZ.comparables(e, TP.T, {"q": "masal"}, None,
                         lambda bid, q, n: {"hazir": True, "items": [{"kitapId": "B2", "sira": 1}]})
    assert [x["id"] for x in out["timas"]] == ["B2"] and out["counts"]["anlamEklenen"] == 1
    assert any("anlamca yakın" in g for g in out["timas"][0]["gerekce"])
    same = PZ.comparables(e, TP.T, {"q": "alışkanlık zihin"}, None, lambda bid, q, n: {"hazir": False, "items": [], "not": "yok"})
    assert [x["id"] for x in same["timas"]] == [x["id"] for x in PZ.comparables(e, TP.T, {"q": "alışkanlık zihin"}, None)["timas"]]
    assert same["anlamNot"] == "yok"
