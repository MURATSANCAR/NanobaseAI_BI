"""M39 Pazar › Rakipler ve emsal — ikinci rakip kaynağı Başarı Dağıtım kataloğu: kaynak seçimi (varsayılan CRM akışı
değişmez), Başarı ham kategorilerinin eşleme hattına «basari:» anahtarıyla girmesi (TİMAŞ grubu ve katalogdan düşen
başlık sayılmaz, CRM anlık görüntüsü Başarı sayılarını sıfırlamaz, kategori listesi değişince onay geri döner), ad
eşleşmesi / Zeki AI önerisi / karar, matrisin yalnız onaylı eşlemeyi sayması, rakip listesi, emsal, tazelik ve sorgu
bilgisi (asıl okuma = Başarı kataloğu sorgusu, CRM rakip okuması yazılmaz).

Veriler yapaydır ve yalnız kuralları sınar; gerçek katalogla kabul test sunucusunda.
"""

from __future__ import annotations

from datetime import date

import pytest

from semantic_bridge import pazar as P
from semantic_bridge import pazar_dagitim as D
from semantic_bridge import pazar_kaynak as PK
from semantic_bridge import provenance as PV
from semantic_bridge import sorgu_izi as IZ
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_pazar import K_KG, K_ROMAN, KITAPLIK, _choice, _seed
from semantic_layer.tests.test_pazar_dagitim import _b

T = "t1"
ROMAN, BAHCE = "Edebiyat>Roman", "Hobi>Bahçe"
K_ROMAN_KEY, K_BAHCE_KEY = P.BASARI_PREFIX + ROMAN, P.BASARI_PREFIX + BAHCE


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("PAZAR_DIR", str(tmp_path / "raporlar"))
    monkeypatch.setenv("PAZAR_CATEGORY_SOURCE", "kitaplik")
    monkeypatch.setenv("PAZAR_DAGITIM_ARALIK_GUN", "35")
    monkeypatch.setattr(P, "today", lambda: date(2026, 9, 29))
    e = open_store("sqlite://").engine
    P._ready.discard(id(e))
    D._ready.discard(id(e))
    P.ensure(e)
    D.ensure(e)
    return e


def _basari(engine):
    """İki görüntü: 4. başlık TİMAŞ grubunda, 5. başlık ikinci görüntüde katalogdan düşer, 6. başlık yeni girer."""
    d1 = [_b("9780000000001", 10, 100.0, "Alfa", kategori=ROMAN), _b("9780000000002", 10, 200.0, "Alfa", kategori=ROMAN),
          _b("9780000000003", 10, 150.0, "Beta", kategori=BAHCE), _b("9780000000004", 10, 120.0, "Timaş", kategori=ROMAN),
          _b("9780000000005", 10, 90.0, "Gama", kategori=ROMAN)]
    D.apply(engine, T, "basari", date(2026, 9, 24), D.parse(d1, "basari"), yontem="elle")
    d2 = [r for r in d1 if r["barkod"] != "9780000000005"] + [_b("9780000000006", 5, 300.0, "Beta", kategori=ROMAN)]
    D.apply(engine, T, "basari", date(2026, 9, 25), D.parse(d2, "basari"), yontem="elle")
    with engine.begin() as c:
        c.execute(D.TITLES.update().where(D.TITLES.c.barkod == "9780000000004").values(timas=True))


def _both(engine):
    _seed(engine)
    _basari(engine)
    return P.sync_basari_categories(engine, T)


# ------------------------------------------------------------------ kaynak listesi ve tazelik


def test_sources_and_freshness(engine):
    _seed(engine)
    assert P.rakip_sources(engine, T)[0] == {"kaynak": "basari", "ad": "Başarı Dağıtım kataloğu", "tarih": None, "kayit": 0,
                                             "hazir": False}
    with pytest.raises(P.PazarError) as e:
        P.matrix(engine, T, kaynak="basari")
    assert e.value.status == 409
    _basari(engine)
    src = {s["kaynak"]: s for s in P.rakip_sources(engine, T)}
    assert src["basari"]["tarih"] == "2026-09-25" and src["basari"]["kayit"] == 4 and src["crm"]["kayit"] == 5
    fr = P.freshness(engine, T, "basari")
    assert (fr["kaynak"], fr["records"], fr["katalogTarihi"], fr["firstCreated"], fr["ageDays"]) == ("basari", 4, "2026-09-25", "2026-09-24", 4)
    assert fr["stale"] is False and fr["goruntu"] == 2
    assert P.freshness(engine, T)["kaynak"] == "crm" and P.freshness(engine, T)["records"] == 5   # varsayılan değişmedi
    with pytest.raises(P.PazarError):
        P.freshness(engine, T, "dr")


# ------------------------------------------------------------------ kategori eşlemesi


def test_basari_categories_enter_the_mapping_table(engine):
    info = _both(engine)
    assert info["kategori"] == 2 and info["kayit"] == 4 and info["yeni"] == 2
    assert P.sync_basari_categories(engine, T)["imza"] == info["imza"]          # aynı görüntü: ikinci kez yazılmaz
    b = P.category_map(engine, T, kaynak="basari")
    rows = {x["ham"]: x for x in b["items"]}
    assert rows[K_ROMAN_KEY]["kayit"] == 3            # TİMAŞ grubu ve katalogdan düşen başlık sayılmaz
    assert rows[K_ROMAN_KEY]["ad"] == ROMAN and rows[K_ROMAN_KEY]["kaynak"] == "basari"
    assert set(rows[K_ROMAN_KEY]["ornekler"]) <= {"Kitap 9780000000001", "Kitap 9780000000002", "Kitap 9780000000006"}
    assert b["counts"] == {"yeni": 2} and b["coverage"]["records"] == 4
    c = P.category_map(engine, T, kaynak="crm")
    assert c["total"] == 3 and all(x["kaynak"] == "crm" for x in c["items"])
    assert P.category_map(engine, T)["total"] == 5                             # kaynak boş: ikisi birlikte
    assert P.category_map(engine, T, kaynak="basari", q="bahçe")["items"][0]["ham"] == K_BAHCE_KEY
    # CRM anlık görüntüsü Başarı sayılarını sıfırlamaz.
    _seed(engine)
    assert {x["ham"]: x["kayit"] for x in P.category_map(engine, T, kaynak="basari")["items"]} == {K_ROMAN_KEY: 3, K_BAHCE_KEY: 1}
    assert P.to_suggest(engine, T, kaynak="basari") == [K_ROMAN_KEY, K_BAHCE_KEY]
    assert set(P.to_suggest(engine, T)) >= {K_ROMAN_KEY, K_BAHCE_KEY, "Kişisel Gelişim"}


def test_basari_suggestion_name_match_model_prompt_and_decision(engine):
    _both(engine)
    asked = []

    def choose(prompt, options):
        asked.append(prompt)
        return _choice(options, "Kişisel Gelişim", p=0.9, margin=0.8)

    out = P.suggest_mapping(engine, T, P.to_suggest(engine, T, kaynak="basari"), choose, "Zeki AI", 60)
    assert out["done"] == {"oneri": 2}
    rows = {x["ham"]: x for x in P.category_map(engine, T, kaynak="basari")["items"]}
    assert rows[K_ROMAN_KEY]["yontem"] == "ad" and rows[K_ROMAN_KEY]["oneriId"] == K_ROMAN   # «Roman» ad eşleşmesi
    assert rows[K_BAHCE_KEY]["yontem"] == "zeki" and rows[K_BAHCE_KEY]["oneriId"] == K_KG
    assert len(asked) == 1 and "«Hobi>Bahçe»" in asked[0] and "basari:" not in asked[0] and "Kitap 9780000000003" in asked[0]
    # Matris onay bekleyen öneriyi saymaz; «önerileri de say» sayar.
    assert P.matrix(engine, T, kaynak="basari", kategori=K_ROMAN)["rakipOzet"]["kitap"] == 0
    assert P.matrix(engine, T, kaynak="basari", kategori=K_ROMAN, include_suggested=True)["rakipOzet"]["kitap"] == 3
    res = P.decide_mapping(engine, T, "ayse", [{"ham": K_ROMAN_KEY, "karar": "onayla"}])
    assert res["decided"][0]["kategoriId"] == K_ROMAN
    # CRM rakip kayıtlarına dokunulmaz.
    assert P.competitors(engine, T, durum="eslenmemis")["total"] == 5


# ------------------------------------------------------------------ matris, rakip listesi, emsal


def test_matrix_counts_only_approved_basari_mapping(engine):
    _both(engine)
    crm_before = P.matrix(engine, T)
    m = P.matrix(engine, T, kaynak="basari")
    assert m["kaynak"] == "basari" and m["katalogTarihi"] == "2026-09-25" and "Başarı" in m["note"]
    rows = {r["yayinevi"]: r for r in m["rows"]}
    assert set(rows) == {"Alfa", "Beta"} and m["rakipOzet"]["kitap"] == 4        # TİMAŞ ve düşen başlık yok
    assert rows["Alfa"]["medyan"] == 150.0 and rows["Beta"]["kitap"] == 2
    assert rows["Beta"]["yeni"] == 1 and rows["Alfa"]["yeni"] == 0                # ilk görüntüden sonra giren
    assert m["timas"][0]["yayinevi"] == "TİMAŞ (tümü)" and m["timas"][0]["kitap"] == 2
    P.decide_mapping(engine, T, "ayse", [{"ham": K_ROMAN_KEY, "karar": "duzelt", "kategoriId": K_ROMAN}])
    k = P.matrix(engine, T, kaynak="basari", kategori=K_ROMAN)
    assert {r["yayinevi"]: r["kitap"] for r in k["rows"]} == {"Alfa": 2, "Beta": 1} and k["eslenmemis"] == 1
    # CRM matrisi Başarı kararından etkilenmez.
    assert P.matrix(engine, T)["rakipOzet"] == crm_before["rakipOzet"]
    assert P.matrix(engine, T, kategori=K_ROMAN)["rakipOzet"]["kitap"] == 0


def test_single_snapshot_new_count_is_unknown(engine):
    _seed(engine)
    D.apply(engine, T, "basari", date(2026, 9, 25), D.parse([_b("9780000000001", 1, 100.0, "Alfa")], "basari"), yontem="elle")
    m = P.matrix(engine, T, kaynak="basari")
    assert m["rows"][0]["yeni"] is None and "bilinmiyor" in m["yeniNot"]


def test_competitor_list_and_publishers_from_basari(engine):
    _both(engine)
    P.decide_mapping(engine, T, "ayse", [{"ham": K_ROMAN_KEY, "karar": "duzelt", "kategoriId": K_ROMAN}])
    a = P.competitors(engine, T, yayinevi="Alfa", kaynak="basari")
    assert a["total"] == 2 and a["kaynak"] == "basari"
    it = a["items"][0]
    assert it["kategoriId"] == K_ROMAN and it["kategoriYol"] == "Roman" and it["stok"] == 10 and it["emsalBagi"] is False
    assert P.competitors(engine, T, kategori=K_ROMAN, kaynak="basari")["total"] == 3
    assert [x["crmId"] for x in P.competitors(engine, T, durum="eslenmemis", kaynak="basari")["items"]] == ["9780000000003"]
    assert P.competitors(engine, T, q="0000000006", kaynak="basari")["total"] == 1
    assert P.publishers(engine, T, "basari") == [{"ad": "Alfa", "kitap": 2}, {"ad": "Beta", "kitap": 2}]
    assert P.competitors(engine, T, yayinevi="Alfa")["kaynak"] == "crm"              # varsayılan CRM


def test_comparables_from_basari(engine):
    _both(engine)
    out = P.comparables(engine, T, {"q": "roman", "kaynak": "basari"}, None)
    assert out["kaynak"] == "basari" and out["katalogTarihi"] == "2026-09-25"
    assert {x["id"] for x in out["rakip"]} == {"9780000000001", "9780000000002", "9780000000006"}
    assert all(x["kaynak"] == "basari" and not x["crmEmsal"] for x in out["rakip"])
    # TİMAŞ kitabından başlanınca CRM emsal bağı yalnız CRM kaynağında gelir.
    b = P.comparables(engine, T, {"crmKitapId": "B1", "kaynak": "basari"}, None)
    assert b["counts"]["crmEmsal"] == 0
    assert P.comparables(engine, T, {"crmKitapId": "B1"}, None)["counts"]["crmEmsal"] == 1


# ------------------------------------------------------------------ kategori listesi değişince


def test_category_list_change_resets_basari_approval(engine):
    _both(engine)
    P.decide_mapping(engine, T, "ayse", [{"ham": K_ROMAN_KEY, "karar": "duzelt", "kategoriId": K_ROMAN}])
    info = P.apply_snapshot(engine, T, competitors=[], own_books=[], links=[],
                            kitaplik=[k for k in KITAPLIK if k["id"] != K_ROMAN], own_sales=None, actor="t")
    assert info["mappingReset"] == 1
    row = {x["ham"]: x for x in P.category_map(engine, T, kaynak="basari")["items"]}[K_ROMAN_KEY]
    assert row["durum"] == "yeni" and row["kategoriId"] is None and row["kayit"] == 3


# ------------------------------------------------------------------ sorgu bilgisi


def test_origin_uses_basari_query_instead_of_crm_competitors(engine):
    _seed(engine)
    P.meta_set(engine, T, "snapshot", {**P.meta_get(engine, T, "snapshot", {}),
                                       "okuma": {"crmSchema": "Timas_MSCRM.dbo", "blurbChars": 200, "crmRows": {}}})
    k = PV.Kaynaklar()
    assert PK.origin(k, engine, T, None, None, logo=False, basari=True) == [
        "hesap:basari-bekliyor", "crm.pazar.ownBooks", "crm.pazar.kitaplik"]
    _basari(engine)
    k = PV.Kaynaklar()
    ids = PK.origin(k, engine, T, "TIGERDB", "CRMDB", logo=False, basari=True)
    assert ids[0] == "pazar.dagitim.basari" and "crm.pazar.competitors" not in ids and "crm.pazar.links" not in ids
    assert "API_URUN_DB.dbo.basari_list" in k.sources["pazar.dagitim.basari"]["sql"]
    assert "crm.pazar.competitors" in PK.origin(PV.Kaynaklar(), engine, T, None, None, logo=False)


def test_matrix_and_freshness_are_bound_with_basari_origin(engine):
    _both(engine)
    for fn, text in ((lambda: P.matrix(engine, T, kaynak="basari"), PK.texts("basari")["matris"]),
                     (lambda: P.freshness(engine, T, "basari"), PK.texts("basari")["tazelik"])):
        with IZ.izle(engine) as ran:
            out = fn()
        kk = IZ.kaynak(engine, ran, out, prefix="portal.pazar.test", title="Test", text=text,
                       origin=lambda k: PK.origin(k, engine, T, None, None, logo=False, basari=True))
        out = PV.ekle(out, kk)
        assert not out["kaynaklar"].get("error")
        assert PV.uncovered_numbers(out, ["staleDays"]) == []
        assert PV.problems(out) == []
        portal = [s for s in out["kaynaklar"]["sources"].values() if s["connection"] == "portal"]
        assert portal and all("pazar.dagitim.basari" in s["origin"] for s in portal)
        assert any("semantic_pazar_dagitim_" in s["sql"] for s in portal)   # Başarı tabloları portal okumasında
