"""M39 Pazar araştırması ve rekabet: anlık görüntü ve tazelik, kategori eşlemesi (ad eşleşmesi, Zeki AI, emin değil,
karar), fiyat/format matrisi (PERCENTILE_CONT ile aynı medyan), emsal (kurallı süzgeç, CRM bağı, «benzemiyor» elenir),
iç göstergeler (aynı dönem büyümesi, TİMAŞ içi pay), rapor yükleme ve rakam çıkarımı (sayfada olmayan rakam atılır),
yönetim özeti (kaynaksız ya da kaynakta olmayan sayılı cümle reddi, iki göz onayı, onaylı kaynağın korunması),
yetki kuralları.

Veriler yapaydır ve yalnız kuralları sınar; gerçek CRM/Logo kabulü test sunucusunda (`scripts/acceptance/M39/`).
"""

from __future__ import annotations

import pytest

from semantic_bridge import access as A
from semantic_bridge import pazar as P
from semantic_layer.runtime.llm_choose import Choice
from semantic_layer.store.catalog_store import open_store

T = "t1"
K_KG, K_COCUK, K_ROMAN = "K-KG", "K-COCUK", "K-ROMAN"


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("PAZAR_DIR", str(tmp_path / "raporlar"))
    monkeypatch.setenv("PAZAR_CATEGORY_SOURCE", "kitaplik")
    e = open_store("sqlite://").engine
    P._ready.discard(id(e))
    P.ensure(e)
    return e


def _comp(cid, ad, yayinevi, fiyat, sayfa, kategori, created="2026-03-01T00:00:00", tanitim=None, cilt="Karton Kapak"):
    return {"crm_id": cid, "ad": ad, "yayinevi": yayinevi, "yazarlar": "Yazar", "isbn": None, "liste_fiyat": fiyat,
            "sayfa": sayfa, "cilt": cilt, "kagit": None, "baski_sayisi": 1, "kategori_ham": kategori, "dil": "Türkçe",
            "satis_adedi_ham": 5, "satis_adedi2_ham": None, "satis_durumu": "Satışta", "tanitim_kisa": tanitim,
            "crm_created": created, "crm_modified": None}


def _own(bid, ad, stok, fiyat, sayfa, kitaplik, marka="Timaş Yayınları", ozet=None):
    return {"crm_id": bid, "stok_kodu": stok, "ad": ad, "yazar": "Timaş Yazarı", "isbn": None, "marka_id": "M1", "marka": marka,
            "kitaplik_id": kitaplik, "kitaplik": {K_KG: "Kişisel Gelişim", K_COCUK: "Çocuk", K_ROMAN: "Roman"}[kitaplik],
            "fiyat": fiyat, "sayfa": sayfa, "cilt": "Amerikan Cilt", "ebat": "13,5x21", "web": None, "ilk_yayin": "2025-02-01",
            "ozet_kisa": ozet}


KITAPLIK = [{"id": K_KG, "ad": "Kişisel Gelişim"}, {"id": K_COCUK, "ad": "Çocuk"}, {"id": K_ROMAN, "ad": "Roman"}]


def _sales():
    rows = []
    for y, (a, b) in {2025: (100.0, 1000.0), 2026: (150.0, 1300.0)}.items():
        rows.append({"yil": y, "boyut": "stok", "anahtar": "S1", "yayinevi": "TIMAS", "ytd_adet": a, "ytd_ciro": b,
                     "adet": a * 2, "ciro": b * 2})
        rows.append({"yil": y, "boyut": "stok", "anahtar": "S2", "yayinevi": "TIMAS COCUK", "ytd_adet": a / 2, "ytd_ciro": b / 2,
                     "adet": a, "ciro": b})
        rows.append({"yil": y, "boyut": "kanal", "anahtar": "KITAPCI", "yayinevi": None, "ytd_adet": a, "ytd_ciro": b,
                     "adet": a, "ciro": b})
    return {"rows": rows, "dataEnd": "2026-08-17", "missingYears": [], "firms": {"2025": "211", "2026": "411"}}


def _seed(engine, comps=None):
    comps = comps or [
        _comp("R1", "Zihnin Gücü", "Alfa", 200.0, 240, "Kişisel Gelişim", tanitim="Alışkanlık ve zihin üzerine."),
        _comp("R2", "Alışkanlıklar", "Alfa", 300.0, 280, "Kişisel Gelişim", tanitim="Küçük alışkanlıkların gücü."),
        _comp("R3", "Mutlu Olmak", "Beta", 150.0, 200, "Psikoloji > Kişisel Gelişim"),
        _comp("R4", "Masal Adası", "Beta", 90.0, 48, "Çocuk Kitapları", created="2019-01-01T00:00:00"),
        _comp("R5", "Fiyatsız", "Gama", None, 250, "Kişisel Gelişim"),
    ]
    own = [_own("B1", "Zihin Haritası", "S1", 250.0, 260, K_KG, ozet="Zihin ve alışkanlık üzerine."),
           _own("B2", "Küçük Ayı", "S2", 120.0, 32, K_COCUK, marka="Timaş Çocuk")]
    return P.apply_snapshot(engine, T, competitors=comps, own_books=own, links=[("B1", "R2")], kitaplik=KITAPLIK,
                            own_sales=_sales(), actor="test")


def _choice(options, pick, p=0.9, margin=0.8):
    probs = {o: (p if o == pick else (1 - p) / max(1, len(options) - 1)) for o in options}
    return Choice(pick, options.index(pick), probs, "logprobs", margin=margin, coverage=1.0)


# ------------------------------------------------------------------ anlık görüntü ve tazelik


def test_snapshot_and_freshness(engine):
    info = _seed(engine)
    assert info["competitors"] == 5 and info["ownBooks"] == 2 and info["links"] == 1
    assert info["categorySource"] == "kitaplik" and info["categories"] == 3
    fr = P.freshness(engine, T)
    assert fr["records"] == 5 and fr["firstCreated"].startswith("2019") and fr["crmLinks"] == 1
    assert {"yil": "2019", "kayit": 1} in fr["byYear"]
    assert fr["ageDays"] is not None and fr["stale"] == (fr["ageDays"] > fr["staleDays"])
    cm = P.category_map(engine, T)
    assert cm["total"] == 3 and cm["counts"] == {"yeni": 3}
    assert cm["items"][0]["ham"] == "Kişisel Gelişim" and cm["items"][0]["kayit"] == 3


def test_resnapshot_keeps_approved_mapping_and_resets_missing_category(engine):
    _seed(engine)
    P.decide_mapping(engine, T, "ayse", [{"ham": "Kişisel Gelişim", "karar": "duzelt", "kategoriId": K_KG}])
    _seed(engine)
    assert P.competitors(engine, T, kategori=K_KG)["total"] == 3
    # Kategori listesinden düşen karşılık yeniden öneriye döner.
    P.apply_snapshot(engine, T, competitors=[_comp("R1", "Zihnin Gücü", "Alfa", 200.0, 240, "Kişisel Gelişim")],
                     own_books=[], links=[], kitaplik=[k for k in KITAPLIK if k["id"] != K_KG], own_sales=None, actor="t")
    row = P.category_map(engine, T, q="kişisel")["items"][0]
    assert row["durum"] == "yeni" and row["kategoriId"] is None and "listede yok" in row["not"]


# ------------------------------------------------------------------ eşleme


def test_suggest_mapping_name_model_and_unsure(engine):
    _seed(engine)
    asked = []

    def choose(prompt, options):
        asked.append(prompt)
        if "Psikoloji" in prompt:
            return _choice(options, "Kişisel Gelişim", p=0.93, margin=0.9)
        return _choice(options, "Çocuk", p=0.5, margin=0.1)

    out = P.suggest_mapping(engine, T, P.to_suggest(engine, T), choose, "Zeki AI", 60)
    assert out["done"] == {"oneri": 2, "belirsiz": 1}
    items = {x["ham"]: x for x in P.category_map(engine, T)["items"]}
    assert items["Kişisel Gelişim"]["yontem"] == "ad" and items["Kişisel Gelişim"]["oneriId"] == K_KG   # modele gitmez
    assert items["Psikoloji > Kişisel Gelişim"]["yontem"] == "ad"                                      # son parça adı
    assert items["Çocuk Kitapları"]["durum"] == "belirsiz"
    assert len(asked) == 1 and "Masal Adası" in asked[0]


def test_suggest_stops_when_model_fails(engine):
    _seed(engine)

    def boom(prompt, options):
        raise TimeoutError("kapı")

    out = P.suggest_mapping(engine, T, ["Çocuk Kitapları"], boom, "Zeki AI", 60)
    assert out["stopped"].startswith("Zeki AI cevap vermedi") and out["remaining"] == 1


def test_decide_mapping_updates_competitors_and_refuses_unknown(engine):
    _seed(engine)
    P.suggest_mapping(engine, T, ["Kişisel Gelişim"], None, "Zeki AI", 60)
    out = P.decide_mapping(engine, T, "ayse", [{"ham": "Kişisel Gelişim", "karar": "onayla"},
                                               {"ham": "Çocuk Kitapları", "karar": "reddet"}])
    assert [d["durum"] for d in out["decided"]] == ["onaylandi", "reddedildi"]
    assert P.competitors(engine, T, kategori=K_KG)["total"] == 3
    with pytest.raises(P.PazarError, match="Geçerli bir TİMAŞ kategorisi"):
        P.decide_mapping(engine, T, "ayse", [{"ham": "Çocuk Kitapları", "karar": "duzelt", "kategoriId": "UYDURMA"}])


# ------------------------------------------------------------------ matris


def test_percentile_is_percentile_cont():
    assert P.percentile([100, 200, 300, 400], 0.5) == 250
    assert P.percentile([1, 3, 5], 0.25) == 2
    assert P.percentile([], 0.5) is None


def test_matrix_counts_only_approved_mapping_and_has_timas_rows(engine):
    _seed(engine)
    m = P.matrix(engine, T, kategori=K_KG)
    assert m["rows"] == [] and m["eslenmemis"] == 5
    P.decide_mapping(engine, T, "ayse", [{"ham": "Kişisel Gelişim", "karar": "duzelt", "kategoriId": K_KG}])
    m = P.matrix(engine, T, kategori=K_KG)
    alfa = next(r for r in m["rows"] if r["yayinevi"] == "Alfa")
    assert alfa["kitap"] == 2 and alfa["medyan"] == 250 and alfa["sayfaMedyan"] == 260
    gama = next(r for r in m["rows"] if r["yayinevi"] == "Gama")
    assert gama["kitap"] == 1 and gama["fiyatli"] == 0 and gama["medyan"] is None      # fiyatsız kayıt fiyata girmez
    assert m["timas"][0]["yayinevi"] == "TİMAŞ (tümü)" and m["timas"][0]["medyan"] == 250
    assert m["timasKonum"] == 0.5                                                        # rakip fiyatlarının yarısı altında
    # Önerileri de say: öneri durumundaki eşleme matrise girer.
    P.suggest_mapping(engine, T, ["Psikoloji > Kişisel Gelişim"], None, "Zeki AI", 60)
    assert len(P.matrix(engine, T, kategori=K_KG, include_suggested=True)["rows"]) == 3
    # Sayfa bandı
    m = P.matrix(engine, T, kategori=K_KG, sayfa_min=250, sayfa_max=300)
    assert {r["yayinevi"]: r["kitap"] for r in m["rows"]} == {"Alfa": 1, "Gama": 1}
    assert P.matrix_csv(m).startswith("﻿Yayınevi".encode("utf-8"))


def test_watchlist_marks_rows(engine):
    _seed(engine)
    P.add_watch(engine, T, "ayse", {"yayinevi": "Beta"})
    with pytest.raises(P.PazarError, match="zaten"):
        P.add_watch(engine, T, "ayse", {"yayinevi": "Beta"})
    m = P.matrix(engine, T, watch_only=True)
    assert [r["yayinevi"] for r in m["rows"]] == ["Beta"] and m["rows"][0]["watched"]


# ------------------------------------------------------------------ emsal


def test_comparables_rules_link_and_model(engine):
    _seed(engine)
    P.decide_mapping(engine, T, "ayse", [{"ham": "Kişisel Gelişim", "karar": "duzelt", "kategoriId": K_KG}])

    def choose(prompt, options):
        return _choice(options, "benzemiyor" if "Fiyatsız" in prompt else "çok benzer", p=0.8)

    out = P.comparables(engine, T, {"crmKitapId": "B1"}, choose)
    ids = [x["id"] for x in out["rakip"]]
    assert ids[0] == "R2" and out["rakip"][0]["crmEmsal"]                           # CRM emsal bağı başta
    assert "R4" not in ids                                                           # başka kategori
    assert out["counts"]["crmEmsal"] == 1 and out["query"]["kategoriId"] == K_KG
    assert any("Zeki AI: çok benzer" in g for g in out["rakip"][0]["gerekce"])
    with pytest.raises(P.PazarError, match="girin"):
        P.comparables(engine, T, {}, None)


def test_comparables_without_model_is_explicit(engine):
    _seed(engine)
    out = P.comparables(engine, T, {"q": "alışkanlık zihin"}, None)
    assert out["counts"]["zekiOkudu"] == 0 and "tanımlı değil" in out["note"]
    assert {x["id"] for x in out["rakip"]} >= {"R1", "R2"}
    assert out["timas"][0]["id"] == "B1" and out["timas"][0]["satis"] == {"adet": 150.0, "ciro": 1300.0}


# ------------------------------------------------------------------ iç göstergeler


def test_own_market_growth_share_and_dimensions(engine):
    _seed(engine)
    k = P.own_market(engine, T, "kategori")
    assert k["yil"] == 2026 and k["total"]["ytdCiro"] == 1950 and round(k["total"]["ciroBuyume"], 4) == 0.3
    kg = next(r for r in k["rows"] if r["anahtar"] == K_KG)
    assert kg["ytdCiro"] == 1300 and round(kg["pay"], 4) == round(1300 / 1950, 4)
    y = P.own_market(engine, T, "yayinevi", 2026)
    assert {r["ad"] for r in y["rows"]} == {"TIMAS", "TIMAS COCUK"}
    ch = P.own_market(engine, T, "kanal")
    assert ch["rows"][0]["ad"] == "KITAPCI" and ch["period"]["bitis"] == "2026-08-17"
    assert "pazar payı değildir" in ch["note"]
    with pytest.raises(P.PazarError):
        P.own_market(engine, T, "il")


# ------------------------------------------------------------------ raporlar


def _pages(name, data):
    return [{"sayfa": "1", "metin": "2025 yılında toplam 400.123.456 adet kitap basıldı."},
            {"sayfa": "2", "metin": ""}]


def test_report_upload_checks_and_duplicate(engine):
    with pytest.raises(P.PazarError, match="PDF, Excel"):
        P.add_report(engine, T, "ayse", "rapor.exe", b"x", {"kaynak": "Birlik"}, _pages)
    with pytest.raises(P.PazarError, match="uzantısıyla"):
        P.add_report(engine, T, "ayse", "rapor.pdf", b"NOTPDF", {"kaynak": "Birlik"}, _pages)
    with pytest.raises(P.PazarError, match="kaynağı"):
        P.add_report(engine, T, "ayse", "rapor.pdf", b"%PDF-1.4", {}, _pages)
    r = P.add_report(engine, T, "ayse", "rapor.pdf", b"%PDF-1.4 a", {"kaynak": "Yayıncılar Birliği", "yil": "2025"}, _pages)
    assert r["sayfaSayisi"] == 2 and r["ilerleme"]["metinsizSayfa"] == 1 and r["yil"] == 2025
    with pytest.raises(P.PazarError, match="zaten yüklü"):
        P.add_report(engine, T, "ayse", "kopya.pdf", b"%PDF-1.4 a", {"kaynak": "X"}, _pages)


def test_extract_drops_numbers_not_on_page():
    page = {"sayfa": "3", "metin": "Toplam bandrol 400.123.456 adet. Çocuk kitaplarının payı %22,5 oldu."}

    def chat(messages):
        return ('[{"gosterge": "Toplam bandrol", "deger": "400.123.456", "birim": "adet", "donem": "2025", '
                '"alinti": "uydurma alıntı", "olcu": "pazar_adet"},'
                ' {"gosterge": "Çocuk payı", "deger": "22,5", "birim": "%", "olcu": "kategori_pay"},'
                ' {"gosterge": "Uydurma büyüme", "deger": "7,3", "birim": "%", "olcu": "pazar_buyume"}]')

    res = P.extract_page(page, chat, 12000)
    assert [f["gosterge"] for f in res["figures"]] == ["Toplam bandrol", "Çocuk payı"] and res["dropped"] == 1
    assert res["figures"][0]["deger"] == 400123456 and "400.123.456" in res["figures"][0]["alinti_kisa"]
    assert res["figures"][1]["deger"] == 22.5
    assert P.extract_page({"sayfa": "4", "metin": " "}, chat, 12000)["empty"]


def test_figure_decisions_and_manual_entry(engine):
    _seed(engine)
    r = P.add_report(engine, T, "ayse", "rapor.pdf", b"%PDF-1.4 b", {"kaynak": "Birlik", "yil": 2025}, _pages)
    n = P.store_figures(engine, T, r["id"], "1", [{"gosterge": "Toplam basılan", "deger": 400123456.0, "deger_metin": "400.123.456",
                                                   "birim": "adet", "donem": "2025", "alinti_kisa": None, "olcu": "pazar_adet"}])
    assert n == 1
    fid = P.figures(engine, T, r["id"])["items"][0]["id"]
    out = P.decide_figure(engine, T, "mehmet", fid, {"karar": "duzeltildi", "deger": "400.000.000"})
    assert out["deger"] == 400000000 and out["degerOneri"] == 400123456 and out["durum"] == "duzeltildi"
    with pytest.raises(P.PazarError, match="sayfa"):
        P.add_figure(engine, T, "mehmet", r["id"], {"gosterge": "Elle", "deger": 5})
    m = P.add_figure(engine, T, "mehmet", r["id"], {"gosterge": "E-kitap payı", "deger": "3,4", "birim": "%", "sayfa": "12",
                                                    "olcu": "kategori_pay"})
    assert m["durum"] == "onaylandi" and m["deger"] == 3.4 and m["yontem"] == "elle"
    assert len(P.approved_figures(engine, T)) == 2


# ------------------------------------------------------------------ yönetim özeti


def test_sentence_numbers_must_match_cited_sources():
    by_id = {"K1": {"deger": 848123456.12, "donem": "1 Ocak – 17.08 2026"}, "K2": {"deger": 42.71, "donem": "2026"}}
    assert P.check_sentence("Net ciro 848,1 milyon ₺ oldu [K1]", ["K1"], by_id) is None
    assert P.check_sentence("Ciro %42,7 büyüdü, 1 Ocak – 17 Ağustos 2026", ["K2", "K1"], by_id) is None
    assert "kaynakta olmayan" in P.check_sentence("Ciro %55 büyüdü", ["K2"], by_id)
    assert P.check_sentence("Pazar büyüyor", [], by_id) == "kaynağa bağlı değil"
    assert P.check_sentence("Pazar büyüyor", ["K9"], by_id) == "kaynağa bağlı değil"


def test_brief_draft_rejects_unsourced_and_two_eyes(engine):
    _seed(engine)

    def chat(messages):
        src = messages[-1]["content"]
        assert "K1: TİMAŞ net ciro = 1.950 ₺" in src
        return ('{"firsatlar": [{"metin": "TİMAŞ net cirosu 1.950 ₺ oldu.", "kaynaklar": ["K1"]},'
                ' {"metin": "Pazar %20 büyüdü.", "kaynaklar": ["K1"]}],'
                ' "tehditler": [{"metin": "Rakipler güçleniyor.", "kaynaklar": []}], "aksiyonlar": []}')

    b = P.draft_brief(engine, T, "ayse", "2026-08", chat)
    assert b["durum"] == "taslak" and b["sorunlar"] == []
    assert "TİMAŞ net cirosu 1.950 ₺ oldu. [K1]" in b["taslak"]
    assert {x["neden"][:12] for x in b["reddedilen"]} == {"kaynakta ola", "kaynağa bağl"}
    assert "Pazar büyüklüğü: kaynak yok" in b["taslak"]
    bad = b["taslak"].replace("oldu. [K1]", "oldu, pazar 99 milyon.")
    edited = P.update_brief(engine, T, "ayse", b["id"], bad)
    assert edited["sorunlar"] and edited["sorunlar"][0]["neden"] == "kaynağa bağlı değil"
    with pytest.raises(P.PazarError, match="düzeltin"):
        P.submit_brief(engine, T, "ayse", b["id"])
    P.update_brief(engine, T, "ayse", b["id"], b["taslak"])
    P.submit_brief(engine, T, "ayse", b["id"])
    with pytest.raises(P.PazarError, match="onaylayamaz"):
        P.decide_brief(engine, T, "AYSE", b["id"], True, None)
    with pytest.raises(P.PazarError, match="gerekçe"):
        P.decide_brief(engine, T, "mehmet", b["id"], False, "")
    ok = P.decide_brief(engine, T, "mehmet", b["id"], True, None)
    assert ok["durum"] == "onaylandi" and ok["dykGonderildiAt"]
    assert P.approved_brief(engine, T)["id"] == b["id"]
    with pytest.raises(P.PazarError, match="onaylı"):
        P.draft_brief(engine, T, "ayse", "2026-08", chat)


def test_report_cited_in_approved_brief_cannot_be_deleted(engine):
    _seed(engine)
    r = P.add_report(engine, T, "ayse", "rapor.pdf", b"%PDF-1.4 c", {"kaynak": "Birlik", "yil": 2025}, _pages)
    P.add_figure(engine, T, "mehmet", r["id"], {"gosterge": "Toplam basılan", "deger": 400, "birim": "milyon adet",
                                                "sayfa": "1", "olcu": "pazar_adet"})

    def chat(messages):
        k = next(line.split(":")[0] for line in messages[-1]["content"].splitlines() if "Toplam basılan" in line)
        return '{"firsatlar": [{"metin": "Sektörde 400 milyon adet basıldı.", "kaynaklar": ["%s"]}]}' % k

    b = P.draft_brief(engine, T, "ayse", "2026-08", chat)
    assert "[K" in b["taslak"].split("## Tehditler")[0] and any(s["tur"] == "dis" for s in b["kaynaklar"])
    P.submit_brief(engine, T, "ayse", b["id"])
    P.decide_brief(engine, T, "mehmet", b["id"], True, None)
    with pytest.raises(P.PazarError, match="silinemez"):
        P.delete_report(engine, T, r["id"])


def test_due_brief_period_only_in_first_week(engine):
    from datetime import date

    assert P.due_brief_donem(engine, T, date(2026, 10, 5)) == "2026-09"
    assert P.due_brief_donem(engine, T, date(2026, 10, 12)) is None
    assert P.valid_donem("2026-01") == "2026-01"
    with pytest.raises(P.PazarError):
        P.valid_donem("2026-13")


# ------------------------------------------------------------------ yetki


def test_access_rules_for_pazar():
    r = A.rule_for
    assert r("/api/v1/pazar/overview") == {"sayfa:pazar-arastirma"}
    assert r("/api/v1/pazar/run-due") == A.SYSTEM
    assert r("/api/v1/pazar/matrix") == {"sayfa:pazar-rakipler", "sayfa:fiyatlama"}
    assert "sayfa:yayin-kurulu" in r("/api/v1/pazar/comparables")
    assert r("/api/v1/pazar/reports/x/file") == {"sayfa:pazar-raporlar"}
    assert r("/api/v1/pazar/figures/x/decision") == {"sayfa:pazar-raporlar"}
    assert r("/api/v1/pazar/meta") == {"sayfa:pazar-arastirma", "sayfa:pazar-rakipler", "sayfa:pazar-raporlar"}
    f = A.features_for
    assert f("POST", "/api/v1/pazar/reports") == ["ozellik:pazar.rapor-yukle"]
    assert f("POST", "/api/v1/pazar/reports/r1/extract") == ["ozellik:pazar.rapor-yukle"]
    assert f("DELETE", "/api/v1/pazar/reports/r1") == ["ozellik:pazar.rapor-yukle"]
    assert f("POST", "/api/v1/pazar/reports/r1/figures") == ["ozellik:pazar.rakam-onay"]
    assert f("POST", "/api/v1/pazar/figures/f1/decision") == ["ozellik:pazar.rakam-onay"]
    assert f("POST", "/api/v1/pazar/category-map/decision") == ["ozellik:pazar.kategori-esleme"]
    assert f("POST", "/api/v1/pazar/refresh") == ["ozellik:pazar.kategori-esleme"]
    assert f("POST", "/api/v1/pazar/briefs/draft") == ["ozellik:pazar.ozet-yaz"]
    assert f("PATCH", "/api/v1/pazar/briefs/b1") == ["ozellik:pazar.ozet-yaz"]
    assert f("POST", "/api/v1/pazar/briefs/b1/submit") == ["ozellik:pazar.ozet-yaz"]
    assert f("POST", "/api/v1/pazar/briefs/b1/approve") == []           # açıkça verilen, ucun içinde
    assert f("GET", "/api/v1/pazar/matrix/export.csv") == ["ozellik:veri.disa-aktar"]
    assert f("POST", "/api/v1/pazar/comparables") == [] and f("POST", "/api/v1/pazar/watchlist") == []
    assert "ozellik:pazar.ozet-onay" in A.explicit_keys() and "ozellik:pazar.ozet-yaz" not in A.explicit_keys()
