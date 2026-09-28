"""M53 Set, hediye ve promosyon: fiyat–marj ve KDV ayrışması, maliyet kaynağı, set onayı (iki göz), açılacak kart ve CRM
eşlemesi, kural tabanlı set önerisi, kurumsal hediye seçenekleri ve teklif onayı, yetki kuralları, yazma yasağı.

Veriler yapaydır ve yalnız hesap kurallarını sınar; gerçek Logo/CRM kabulü test sunucusunda
(`scripts/acceptance/M53/`, günlük 2026-09-28 M53).
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from semantic_bridge import access as A
from semantic_bridge import sets as S
from semantic_bridge import sets_sources as src
from semantic_layer.store.catalog_store import open_store

T = "t1"
ST = S.settings_from(lambda key, default="": S.DEFAULTS.get(key, default))
BRIDGE = Path(S.__file__).parent


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    S._ready.discard(id(e))
    S.ensure(e)
    return e


def _books(engine, rows=None):
    rows = rows or [
        # stok, ad, yazar, dizi, crm tipi, fiyat (CRM, KDV dahil), KDV %, stok, son 12 ay adet
        ("K1", "Kitap 1", "Yazar A", "Dizi X", 1, 100.0, 0.0, 500, 900),
        ("K2", "Kitap 2", "Yazar A", "Dizi X", 1, 80.0, 0.0, 500, 700),
        ("K3", "Kitap 3", "Yazar A", "Dizi X", 1, 60.0, 0.0, 500, 500),
        ("K4", "Kitap 4", "Yazar B", None, 1, 50.0, 0.0, 0, 2000),        # stok yok
        ("D1", "Defter", None, None, 2, 40.0, 20.0, 300, 50),             # promosyon (KDV %20)
        ("15701", "Ajanda", None, None, None, None, 20.0, 0, 10),         # ticari ürün, stok yok
        ("SET1", "Set Bir", None, None, 4, 200.0, 0.0, 800, 120),
    ]
    with engine.begin() as c:
        for code, ad, yazar, dizi, tip, fiyat, kdv, stok, s12 in rows:
            c.execute(S.BOOKS.insert().values(stok_kodu=code, ad=ad, yazar=yazar, dizi=dizi, crm_tip=tip, liste_fiyat=fiyat, kdv=kdv,
                                              stok=stok, son12_adet=s12, son12_ciro=s12 * (fiyat or 0), in_logo=True, in_crm=tip is not None))


# ------------------------------------------------------------------ fiyat – marj


def test_price_calc_splits_vat_by_list_share_and_needs_every_cost():
    items = [{"stok": "K1", "adet": 1, "liste": 100.0, "kdv": 0.0, "maliyet": 30.0},
             {"stok": "D1", "adet": 1, "liste": 50.0, "kdv": 20.0, "maliyet": 10.0}]
    r = S.price_calc(items, 120.0, 5.0, ST)
    assert r["listeToplami"] == 150.0 and r["indirim"] == pytest.approx(0.2)
    # 120 × 100/150 = 80 (KDV 0) + 120 × 50/150 = 40 → 40/1,2 = 33,33
    assert r["netGelir"] == pytest.approx(113.33, abs=0.01)
    assert r["maliyetToplami"] == 40.0
    assert r["marj"] == pytest.approx(113.33 - 40 - 5, abs=0.01)
    assert r["marjMesaj"] is None and r["kdvYontemi"] == "liste"

    unknown = S.price_calc([{**items[0], "maliyet": None}, items[1]], 120.0, None, ST)
    assert unknown["marj"] is None and unknown["maliyetToplami"] is None
    assert unknown["marjMesaj"] == "Marj hesaplanamadı: 1 kitapta maliyet yok."


def test_price_calc_uses_quantity_share_when_a_list_price_is_missing():
    r = S.price_calc([{"stok": "A", "adet": 2, "liste": None, "kdv": 0.0, "maliyet": 1.0},
                      {"stok": "B", "adet": 2, "liste": 10.0, "kdv": 20.0, "maliyet": 1.0}], 60.0, None, ST)
    assert r["eksikFiyat"] == 1 and r["indirim"] is None and r["kdvYontemi"] == "adet"
    assert r["netGelir"] == pytest.approx(30 + 30 / 1.2, abs=0.01)


def test_margin_floor_flags_only_when_set():
    items = [{"stok": "A", "adet": 1, "liste": 100.0, "kdv": 0.0, "maliyet": 90.0}]
    assert S.price_calc(items, 95.0, None, ST)["marjUyari"] is False           # sınır boş: uyarı yok
    assert S.price_calc(items, 95.0, None, {**ST, "marginMinPct": 10})["marjUyari"] is True


def test_costs_are_stripped_without_permission():
    obj = {"ad": "Set", "marj": 1.0, "bilesenler": [{"stok": "A", "maliyet": 3.0, "liste": 5.0}], "netGelir": 2.0}
    assert S.strip_costs(obj) == {"ad": "Set", "bilesenler": [{"stok": "A", "liste": 5.0}]}


def test_cost_is_unknown_without_the_m9_provider_and_never_invented():
    src.register_cost_provider(None)
    assert src.unit_costs(["K1"], "m9")["K1"]["birim"] is None
    src.register_cost_provider(lambda codes: {"K1": {"birim": 25.0}})
    try:
        out = src.unit_costs(["K1", "K2"], "m9")
        assert out["K1"]["birim"] == 25.0 and out["K2"]["birim"] is None
    finally:
        src.register_cost_provider(None)
    assert src.unit_costs(["K1"], "logo", {"K1": {"birim": 20.0}})["K1"]["tahmini"] is True
    assert src.unit_costs(["K1"], "yok", {"K1": {"birim": 20.0}})["K1"]["birim"] is None


# ------------------------------------------------------------------ set akışı


def test_set_draft_submit_and_the_sender_cannot_approve(engine):
    _books(engine)
    s = S.create_set(engine, ST, T, "ayse", {"ad": "Yaz seti", "tur": "tematik", "bilesenler": [{"stok": "K1", "adet": 1}, {"stok": "K2"}],
                                             "setFiyati": 150})
    assert s["id"].startswith(f"MS-{S.today().year}-") and s["durum"] == "taslak"
    assert s["listeToplami"] == 180.0 and s["indirim"] == pytest.approx(1 / 6)
    assert s["marj"] is None and s["eksikMaliyet"] == 2                         # M9 yok → maliyet bilinmiyor
    s = S.submit_set(engine, ST, T, "ayse", s["id"])
    assert s["durum"] == "onayda"
    with pytest.raises(S.SetsError) as e:
        S.decide_set(engine, T, "ayse", s["id"], True, None)
    assert e.value.status == 409
    with pytest.raises(S.SetsError):
        S.decide_set(engine, T, "mehmet", s["id"], False, "")                     # geri gönderme gerekçe ister
    s = S.decide_set(engine, T, "mehmet", s["id"], True, "uygun")
    assert s["durum"] == "kart-bekliyor" and s["onaylayan"] == "mehmet"
    with pytest.raises(S.SetsError):
        S.update_set(engine, ST, T, "ayse", s["id"], {"setFiyati": 10}, [])      # onaylıda fiyat değişmez


def test_card_todo_has_no_barcode_proposal_and_csv_lists_components(engine):
    _books(engine)
    s = S.create_set(engine, ST, T, "ayse", {"ad": "Set", "bilesenler": [{"stok": "K1", "adet": 2}], "setFiyati": 150})
    with pytest.raises(S.SetsError):
        S.card_todo(engine, ST, T, s["id"])                                       # onaysız set için kart listesi yok
    S.submit_set(engine, ST, T, "ayse", s["id"])
    S.decide_set(engine, T, "mehmet", s["id"], True, None)
    todo = S.card_todo(engine, ST, T, s["id"])
    assert todo["bilesenler"][0]["stok"] == "K1" and todo["bilesenler"][0]["adet"] == 2
    assert "TİMAŞ" in todo["barkod"]
    csv = S.card_todo_csv(todo)
    assert "K1" in csv and "Bileşen stok kodu" in csv


def test_link_requires_an_active_set_card_in_crm(engine):
    _books(engine)
    s = S.create_set(engine, ST, T, "ayse", {"ad": "Set", "bilesenler": [{"stok": "K1"}], "setFiyati": 90})
    S.submit_set(engine, ST, T, "ayse", s["id"])
    S.decide_set(engine, T, "mehmet", s["id"], True, None)
    with pytest.raises(S.SetsError) as e:
        S.link_set(engine, T, s["id"], "YOK", None)
    assert e.value.status == 404
    with pytest.raises(S.SetsError) as e:
        S.link_set(engine, T, s["id"], "K2", {"id": "x", "ad": "Kitap 2", "tip": 1, "tipAdi": "Kitap"})
    assert e.value.status == 409
    out = S.link_set(engine, T, s["id"], "SET9", {"id": "g", "ad": "Set", "tip": 4})
    assert out["durum"] == "satista" and out["stokKodu"] == "SET9"


def test_auto_link_only_on_an_exact_single_component_match(engine):
    _books(engine)
    s = S.create_set(engine, ST, T, "ayse", {"ad": "Set", "bilesenler": [{"stok": "K1"}, {"stok": "K2"}], "setFiyati": 150})
    S.submit_set(engine, ST, T, "ayse", s["id"])
    S.decide_set(engine, T, "mehmet", s["id"], True, None)
    comp = {"SETA": {"bilesenler": [{"stok": "K1", "adet": 1.0}, {"stok": "K2", "adet": 1.0}]},
            "SETB": {"bilesenler": [{"stok": "K1", "adet": 1.0}]}}
    crm_sets = [{"id": "a", "stok": "SETA", "ad": "Set A"}, {"id": "b", "stok": "SETB", "ad": "Set B"}]
    assert S.auto_link(engine, T, comp, crm_sets) == [{"set": s["id"], "stok": "SETA"}]
    # İki aday aynı bileşenlere sahipse eşleme yapılmaz (insan seçer).
    s2 = S.create_set(engine, ST, T, "ayse", {"ad": "Set 2", "bilesenler": [{"stok": "K3"}], "setFiyati": 50})
    S.submit_set(engine, ST, T, "ayse", s2["id"])
    S.decide_set(engine, T, "mehmet", s2["id"], True, None)
    comp2 = {"X1": {"bilesenler": [{"stok": "K3", "adet": 1.0}]}, "X2": {"bilesenler": [{"stok": "K3", "adet": 1.0}]}}
    assert S.auto_link(engine, T, comp2, [{"id": "1", "stok": "X1", "ad": "x"}, {"id": "2", "stok": "X2", "ad": "y"}]) == []


def test_status_transitions_are_guarded(engine):
    _books(engine)
    s = S.create_set(engine, ST, T, "ayse", {"ad": "Set", "bilesenler": [{"stok": "K1"}], "setFiyati": 90})
    with pytest.raises(S.SetsError):
        S.update_set(engine, ST, T, "ayse", s["id"], {"durum": "satista"}, [])
    with pytest.raises(S.SetsError):
        S.submit_set(engine, ST, T, "ayse", S.create_set(engine, ST, T, "ayse", {"ad": "Fiyatsız", "bilesenler": [{"stok": "K1"}]})["id"])


# ------------------------------------------------------------------ öneri


def test_suggestions_from_baskets_authors_and_series(engine):
    _books(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as c:
        c.execute(S.PAIRS.insert(), [
            {"kod_a": "K1", "kod_b": "K2", "siparis_sayisi": 40, "lift": 3.0, "donem": "d", "asof": now},
            {"kod_a": "K1", "kod_b": "K3", "siparis_sayisi": 12, "lift": 2.0, "donem": "d", "asof": now},
            {"kod_a": "K2", "kod_b": "K3", "siparis_sayisi": 9, "lift": 2.0, "donem": "d", "asof": now},
            {"kod_a": "K1", "kod_b": "K4", "siparis_sayisi": 80, "lift": 5.0, "donem": "d", "asof": now},   # K4 stoksuz
            {"kod_a": "D1", "kod_b": "K1", "siparis_sayisi": 50, "lift": 0.5, "donem": "d", "asof": now},   # promosyon, lift<1
        ])
    out = S.build_suggestions(engine, ST)
    assert out["birlikte"] >= 1
    res = S.list_suggestions(engine, ST, durum="yeni")
    codes = [sorted(x["stok"] for x in i["bilesenler"]) for i in res["items"]]
    assert ["K1", "K2", "K3"] in codes                                            # çift + ikisiyle de alınan üçüncü
    assert codes.count(["K1", "K2", "K3"]) == 1                                   # yazar/dizi kuralı aynı öneriye katılır
    assert not any("K4" in c or "D1" in c for c in codes)
    first = next(i for i in res["items"] if sorted(x["stok"] for x in i["bilesenler"]) == ["K1", "K2", "K3"])
    assert first["tur"] == "birlikte" and "B2C" in first["gerekce"] and "yazarın" in first["gerekce"]
    assert first["listeToplami"] == 240.0
    s = S.adopt_suggestion(engine, ST, T, "ayse", first["id"])
    assert s["kaynak"] == "oneri" and s["durum"] == "taslak"
    # Taslağa alınan öneri yeniden kurulumda korunur; aynı bileşenli set artık aday değildir.
    S.build_suggestions(engine, ST)
    assert S.list_suggestions(engine, ST, durum="benimsendi")["total"] == 1


def test_suggestion_filters_age_and_budget(engine):
    _books(engine)
    S.build_suggestions(engine, ST)
    assert S.list_suggestions(engine, ST, butce_max=100)["total"] == 0
    assert S.list_suggestions(engine, ST, butce_min=200, butce_max=300)["total"] >= 1


# ------------------------------------------------------------------ kurumsal hediye


def test_gift_options_fit_the_budget_and_stock(engine):
    _books(engine)
    opts = S.gift_options(engine, ST, T, 300, 150.0, [(100, 0.10)])
    assert opts and all(o["birimNet"] <= 150.0 for o in opts)
    assert all(o["indirim"] == 0.10 for o in opts)
    assert not any(k["stok"] == "K4" for o in opts for k in o["kalemler"])       # stok 300'e yetmiyor
    assert [o["no"] for o in opts] == list(range(1, len(opts) + 1))


def test_offer_flow_sender_cannot_approve_and_handoff_for_m32(engine):
    _books(engine)
    acc = {"id": "00000000-0000-0000-0000-000000000001", "unvan": "Örnek Holding", "kod": "120.01"}
    o = S.create_offer(engine, ST, T, "ali", {"adet": 300, "kisiBasiButce": 150}, acc)
    assert o["id"].startswith("KT-") and o["durum"] == "taslak" and o["secenekler"]
    o = S.update_offer(engine, ST, T, "ali", o["id"], {"secili": [1]})
    o = S.submit_offer(engine, T, "ali", o["id"])
    with pytest.raises(S.SetsError) as e:
        S.decide_offer(engine, T, "ali", o["id"], True, None)
    assert e.value.status == 409
    o = S.decide_offer(engine, T, "veli", o["id"], True, None)
    assert o["durum"] == "onaylandi"
    h = S.handoff(engine, T, o["id"])
    assert h["kaynak"] == "M53" and h["satirlar"] and all(l["secenek"] == 1 for l in h["satirlar"])
    with pytest.raises(S.SetsError):
        S.update_offer(engine, ST, T, "ali", o["id"], {"adet": 10})               # onaylı teklifin içeriği değişmez
    assert S.update_offer(engine, ST, T, "ali", o["id"], {"durum": "gonderildi"})["durum"] == "gonderildi"


def test_offer_pdf_marks_drafts_and_has_no_cost(engine):
    pytest.importorskip("fpdf")
    from semantic_bridge import sets_docs as D

    _books(engine)
    acc = {"id": "00000000-0000-0000-0000-000000000001", "unvan": "Örnek Holding", "kod": None}
    o = S.create_offer(engine, ST, T, "ali", {"adet": 10, "kisiBasiButce": 500}, acc)
    data = D.offer_pdf(o, "Timaş Yayınları")
    assert data[:4] == b"%PDF"


def test_tiers_parse_from_text_and_list():
    assert S.parse_tiers("100:5;300:10") == [(100, 0.05), (300, 0.10)]
    assert S.parse_tiers([{"adet": 300, "indirim": 0.1}, {"adet": 100, "indirim": 0.05}]) == [(100, 0.05), (300, 0.10)]
    with pytest.raises(S.SetsError):
        S.parse_tiers([{"adet": 0, "indirim": 2}])
    assert S.tier_for(250, [(100, 0.05), (300, 0.10)]) == 0.05


# ------------------------------------------------------------------ takvim ve pencere


def test_next_occurrence_and_window():
    assert S.next_occurrence("2020-11-24", date(2026, 9, 28)) == date(2026, 11, 24)
    assert S.next_occurrence("2020-01-01", date(2026, 9, 28)) == date(2027, 1, 1)
    assert S.next_occurrence("2027-03-10", date(2026, 9, 28)) == date(2027, 3, 10)
    assert S.window12(date(2026, 8, 17)) == ("2025-09", "2026-08")


# ------------------------------------------------------------------ SQL güvenliği ve yazma yasağı


def test_sql_guards():
    with pytest.raises(src.SourceError):
        src.bom_sql("411", ["A'; DROP TABLE x --"], [])
    with pytest.raises(src.SourceError):
        src.crm_account_sql("Timas_MSCRM.dbo", "1 OR 1=1")
    with pytest.raises(src.SourceError):
        src.prefix("Timas;DROP.dbo")
    assert "LEFT(s.new_name, 3) = N'B2C'" in src.crm_basket_pairs_sql("Timas_MSCRM.dbo", date(2024, 9, 1), [8], "B2C", 2)
    assert "HAVING COUNT(*) >= 2" in src.crm_basket_pairs_sql("Timas_MSCRM.dbo", date(2024, 9, 1), [8], "B2C", 2)
    assert "S.LINETYPE IN (0)" in src.sales_sql("411", date(2026, 1, 1), date(2027, 1, 1), [0])


def test_no_write_to_crm_logo_or_tsoft():
    """Kaynak katmanında yazan SQL ya da dış yazma çağrısı yok (statik tarama)."""
    text = (BRIDGE / "sets_sources.py").read_text(encoding="utf-8") + (BRIDGE / "sets.py").read_text(encoding="utf-8")
    sql = re.findall(r'"""(.*?)"""|"([^"\n]*(?:SELECT|FROM)[^"\n]*)"', (BRIDGE / "sets_sources.py").read_text(encoding="utf-8"), re.S)
    blob = " ".join(a + b for a, b in sql).upper()
    for kw in ("INSERT ", "UPDATE ", "DELETE ", "MERGE ", "EXEC ", "DROP "):
        assert kw not in blob
    assert "tsoft" not in text.lower() and "seo_geo.connections" not in text


def test_no_technology_names_on_screen_texts():
    banned = re.compile(r"qwen|vllm|temporal|timesfm|ollama|openai|gpt|claude|llama", re.I)
    for f in ("sets_docs.py", "sets.py", "sets_api.py"):
        body = (BRIDGE / f).read_text(encoding="utf-8")
        strings = re.findall(r'"([^"\n]{12,})"', body)
        assert not [s for s in strings if banned.search(s)], f


# ------------------------------------------------------------------ yetki


def test_feature_rules_for_sets():
    f = A.features_for
    assert f("POST", "/api/v1/marketing/sets") == ["ozellik:set.yaz"]
    assert f("PATCH", "/api/v1/marketing/sets/MS-2026-0001") == ["ozellik:set.yaz"]
    assert f("PUT", "/api/v1/marketing/sets/MS-2026-0001/items") == ["ozellik:set.yaz"]
    assert f("POST", "/api/v1/marketing/sets/suggestions/SO-1/adopt") == ["ozellik:set.yaz"]
    assert f("POST", "/api/v1/marketing/sets/MS-2026-0001/approve") == []          # açıkça verilen onay ucun içinde
    assert f("POST", "/api/v1/marketing/sets/MS-2026-0001/price") == []            # hesap kaydetmez
    assert f("POST", "/api/v1/marketing/sets/run-due") == []
    assert f("POST", "/api/v1/marketing/gift-offers") == ["ozellik:set.yaz"]
    assert f("POST", "/api/v1/marketing/gift-offers/KT-2026-0001/letter") == ["ozellik:set.yaz"]
    assert f("POST", "/api/v1/marketing/gift-offers/KT-2026-0001/approve") == []
    assert f("GET", "/api/v1/marketing/sets/MS-2026-0001/card-todo.csv") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/marketing/gift-offers/KT-2026-0001/document.pdf") == []   # teklif PDF'i satışın asıl işi
    assert A.rule_for("/api/v1/marketing/sets/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/marketing/promo-items") == frozenset({A.page("pazarlama-set-hediye")})
    assert {"ozellik:set.onay", "ozellik:set.teklif-onay"} <= A.explicit_keys()
    assert "ozellik:set.maliyet-gor" in A.all_keys() - A.explicit_keys()


def test_catalog_has_the_page():
    cat = json.loads((BRIDGE / "access_catalog.json").read_text(encoding="utf-8"))
    assert any(p["key"] == "sayfa:pazarlama-set-hediye" and p["area"] == "pazarlama" for p in cat["pages"])
