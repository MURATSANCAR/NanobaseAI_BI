"""M40 Trendyol (ilk sürüm: yalnız okuma + panel dosyası): dosya şeması ve kişisel kolonun atlanması, maske, ürün listesinin
bütünüyle değişmesi ve diğer türlerin anahtarla güncellenmesi, stok/fiyat farkı, geciken paket, iade nedeni (kural + Zeki AI
kapalı küme, eşik), cevapsız soru, yanıt taslağı denetimi, vitrin sırası ve öneri, haftalık rapor, çevrimdışı salt okunur
istemci, yetki kuralları ve uçlar.

Veriler yapaydır ve yalnız hesap kurallarını sınar; gerçek Logo ve gerçek panel dosyası kabulü test sunucusunda
(scripts/acceptance/M40).
"""
from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from semantic_bridge import access as AC
from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import platform_common as PC
from semantic_bridge.channels import platforms as P
from semantic_bridge.channels import store as S
from semantic_bridge.channels import trendyol as T
from semantic_bridge.channels import trendyol_import as TI
from semantic_bridge.channels.trendyol_client import TrendyolClient
from semantic_layer.store.catalog_store import open_store

TN = "t1"
NOW = datetime(2026, 8, 20, 12, 0)


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    S._ready.discard(id(e))
    T._ready.discard(id(e))
    T.ensure(e)
    return e


def _st(**kw):
    s = T.settings(lambda k: "")
    s.update(kw)
    return s


def csv(*rows: str) -> bytes:
    return ("\n".join(rows) + "\n").encode("utf-8")


def _seed_logo(engine):
    """Barkod → stok kodu ve Logo/site tarafı: B1 depoda 0, B2 depoda 40, B3 depoda 500, B4 depoda 10."""
    S.replace_all(engine, TN, S.BARCODES, [{"barkod": f"97860500000{i}", "stok_kodu": f"B{i}"} for i in range(1, 5)])
    S.upsert_books(engine, TN, {"B1": "Birinci", "B2": "İkinci", "B3": "Üçüncü", "B4": "Dördüncü"})
    S.replace_all(engine, TN, T.LOGO, [
        {"stok_kodu": "B1", "depo_stok": 0.0, "liste_fiyati": 100.0, "liste_kdv_dahil": True, "site_fiyati": 90.0, "site_stok": 0},
        {"stok_kodu": "B2", "depo_stok": 40.0, "liste_fiyati": 100.0, "liste_kdv_dahil": False, "site_fiyati": None, "site_stok": None},
        {"stok_kodu": "B3", "depo_stok": 500.0, "liste_fiyati": 200.0, "liste_kdv_dahil": True, "site_fiyati": 200.0, "site_stok": 5},
        {"stok_kodu": "B4", "depo_stok": 10.0, "liste_fiyati": None, "liste_kdv_dahil": None, "site_fiyati": None, "site_stok": None},
    ])


PRODUCTS_CSV = csv(
    "Rapor: Ürün listesi;;;;;;",
    "Barkod;Satıcı Stok Kodu;Ürün Adı;Ürün Durumu;Ürün Stok Adedi;Piyasa Satış Fiyatı (KDV Dahil);Trendyol'da Satılacak Fiyat (KDV Dahil)",
    "978605000001;S1;Birinci Kitap;Satışta;12;120;60",
    "978605000002;S2;İkinci Kitap;Satışta Değil;0;120;110",
    "978605000003;S3;Üçüncü Kitap;Satışta;900;250;190",
    "999000000000;S9;Bilinmeyen;Satışta;3;50;40",
)

ORDERS_CSV = csv(
    "Paket No;Sipariş Numarası;Sipariş Tarihi;Sipariş Durumu;Kargo Firması;Kargoya Teslim Edilmesi Gereken Tarih;Barkod;Ürün Adı;Adet;Faturalanacak Tutar;Alıcı;Teslimat Adresi;Telefon",
    "P1;O1;15.08.2026 10:00;Yeni;Aras;17.08.2026 10:00;978605000003;Üçüncü;3;570;Ayşe Yılmaz;Kadıköy İstanbul;05321234567",
    "P2;O2;18.08.2026 09:00;Kargoya Verildi;Aras;19.08.2026 10:00;978605000003;Üçüncü;2;380;Ali Veli;Çankaya;05329876543",
    "P3;O3;19.08.2026 09:00;İptal Edildi;Aras;20.08.2026 10:00;978605000001;Birinci;1;60;X;Y;Z",
    ";;19.08.2026 09:00;Yeni;;;978605000001;Birinci;1;60;;;",
)


# ------------------------------------------------------------------ dosya


def test_parse_skips_personal_columns_and_counts_bad_rows():
    out = TI.parse("siparis", "siparisler.csv", ORDERS_CSV)
    assert len(out["rows"]) == 3 and out["bad"] == 1               # paket/sipariş no'su boş satır atlanır, sayılır
    assert set(out["columns"]) >= {"paket_no", "siparis_no", "barkod", "adet", "tutar", "termin"}
    assert {"Alıcı", "Teslimat Adresi", "Telefon"} <= set(out["personal"])
    joined = str(out["rows"])
    assert "Ayşe" not in joined and "05321234567" not in joined and "Kadıköy" not in joined
    r = out["rows"][0]
    assert r["paket_id"] == "P1" and r["siparis_tarihi"] == datetime(2026, 8, 15, 10, 0) and r["tutar"] == 570.0


def test_product_columns_pick_the_longest_matching_name():
    out = TI.parse("urun", "urunler.csv", PRODUCTS_CSV)
    assert out["columns"]["fiyat"].startswith("Trendyol'da Satılacak") and out["columns"]["piyasa_fiyati"].startswith("Piyasa")
    assert out["columns"]["stok"] == "Ürün Stok Adedi" and out["columns"]["satici_stok_kodu"] == "Satıcı Stok Kodu"
    flags = {r["barkod"]: r["satisa_acik"] for r in out["rows"]}
    assert flags["978605000001"] is True and flags["978605000002"] is False     # «Satışta Değil» kapalı


def test_parse_rejects_a_file_without_the_needed_columns():
    with pytest.raises(TI.ImportError_):
        TI.parse("siparis", "x.csv", csv("Ürün;Adet", "A;1"))
    with pytest.raises(TI.ImportError_):
        TI.parse("bilinmeyen", "x.csv", ORDERS_CSV)


def test_mask_hides_contact_details_and_long_numbers():
    t = PC.mask("Merhaba, ayse@ornek.com ya da 0532 123 45 67; TC 12345678901, www.site.com. Kitap 3 günde gelsin")
    assert "ayse@" not in t and "0532" not in t and "12345678901" not in t and "www." not in t
    assert "3 günde" in t


def test_barcode_and_dates_from_excel_values():
    assert PC.barcode(9786050812345.0) == "9786050812345" and PC.barcode(" 978 605 ") == "978605"
    assert PC.when("27.09.2026 14:05") == datetime(2026, 9, 27, 14, 5)
    assert PC.when(46000) is not None and PC.when("çöp") is None
    assert PC.num("1.250,50") == 1250.5 and PC.num("₺ 99,90") == 99.9 and PC.num("") is None


def test_store_replaces_products_and_upserts_orders_by_key(engine):
    _seed_logo(engine)
    up = TI.store(engine, TN, "ayse", "urun", "urunler.csv", PRODUCTS_CSV)
    assert up["satir"] == 4 and up["eslesen"] == 3
    TI.store(engine, TN, "ayse", "urun", "urunler2.csv", csv("Barkod;Ürün Stok Adedi", "978605000001;5"))
    assert [r.barkod for r in T._rows(engine, T.PRODUCTS, TN)] == ["978605000001"]       # son liste esas
    first = TI.store(engine, TN, "ayse", "siparis", "s1.csv", ORDERS_CSV)
    again = TI.store(engine, TN, "ali", "siparis", "s2.csv", csv(
        "Paket No;Barkod;Sipariş Durumu;Adet", "P1;978605000003;Teslim Edildi;3"))
    rows = {r.paket_id: r for r in T._rows(engine, T.ORDERS, TN)}
    assert len(rows) == 3 and rows["P1"].durum == "Teslim Edildi" and rows["P1"].import_id == again["id"]
    TI.delete(engine, TN, again["id"])
    assert "P1" not in {r.paket_id for r in T._rows(engine, T.ORDERS, TN)}            # güncellenen satır son dosyayla gider
    assert TI.get(engine, TN, first["id"])["kalan"] == 2
    with pytest.raises(TI.ImportError_):
        TI.store(engine, TN, "ayse", "siparis", "bos.csv", b"")


# ------------------------------------------------------------------ stok ve fiyat


def test_stock_diff_categories(engine):
    _seed_logo(engine)
    TI.store(engine, TN, "ayse", "urun", "urunler.csv", PRODUCTS_CSV)
    out = T.stock_diff(engine, TN, _st())
    by = {r["barkod"]: r["fark"] for r in out["items"]}
    assert by["978605000001"] == "trendyolda-var-depoda-yok"      # 12 Trendyol'da, depoda 0
    assert by["978605000002"] == "depoda-var-kapali"              # depoda 40, Trendyol'da kapalı
    assert by["978605000003"] == "trendyol-fazla"                 # 900 > 500
    assert by["999000000000"] == "eslesmedi"
    assert out["counts"] == {"trendyolda-var-depoda-yok": 1, "depoda-var-kapali": 1, "trendyol-fazla": 1, "eslesmedi": 1}
    only = T.stock_diff(engine, TN, _st(), fark="depoda-var-kapali")
    assert only["total"] == 1 and only["items"][0]["stokKodu"] == "B2"
    assert T.stock_diff(engine, TN, _st(minDepo=50))["counts"]["depoda-var-kapali"] == 0


def test_price_flags_gross_up_vat_and_use_unit_costs(engine):
    _seed_logo(engine)
    TI.store(engine, TN, "ayse", "urun", "urunler.csv", PRODUCTS_CSV)
    rows = {r["stokKodu"]: r for r in T.price_rows(engine, TN, _st(), lambda codes: {"B3": {"maliyet": 200.0}})}
    assert "esik-alti" in rows["B1"]["isaret"] and abs(rows["B1"]["indirim"] - 0.4) < 1e-9     # 60 / 100
    assert "site-ucuz" not in rows["B1"]["isaret"]                                              # site 90 > 60
    assert rows["B2"]["listeFiyat"] == 100.0 and "liste-ustu" in rows["B2"]["isaret"]          # KDV hariç, oran 0: brütlenmez
    brut = {r["stokKodu"]: r for r in T.price_rows(engine, TN, _st(listeKdv=0.2))}
    assert brut["B2"]["listeFiyat"] == pytest.approx(120.0) and "liste-ustu" not in brut["B2"]["isaret"]
    assert "maliyet-alti" in rows["B3"]["isaret"] and rows["B3"]["birimMaliyet"] == 200.0
    assert "site-ucuz" in rows["B3"]["isaret"] or rows["B3"]["siteFiyat"] >= 190
    no_cost = {r["stokKodu"]: r for r in T.price_rows(engine, TN, _st())}
    assert "maliyet-alti" not in no_cost["B3"]["isaret"] and no_cost["B3"]["birimMaliyet"] is None


# ------------------------------------------------------------------ sipariş, iade


def test_orders_mark_late_packages_only_when_not_shipped(engine):
    _seed_logo(engine)
    TI.store(engine, TN, "ayse", "siparis", "s.csv", ORDERS_CSV)
    out = T.orders(engine, TN, now=NOW)
    late = {x["paketId"]: x["gecikti"] for x in out["items"]}
    assert late == {"P1": True, "P2": False, "P3": False}          # P2 kargoda, P3 iptal
    assert out["geciken"] == 1 and out["paketSayisi"] == 3 and out["adet"] == 6
    assert out["kitaplar"][0]["stokKodu"] == "B3" and out["kitaplar"][0]["adet"] == 5
    assert T.orders(engine, TN, durum="geciken", now=NOW)["total"] == 1
    assert T.orders(engine, TN, bas="2026-08-18", bit="2026-08-19", now=NOW)["paketSayisi"] == 2


def test_late_counts_packages_not_book_lines(engine):
    """Çok kitaplı paket bir kez gecikir: «Geciken paket» satır değil paket sayar; liste satırları göstermeye devam eder."""
    _seed_logo(engine)
    extra = b"P1;O1;15.08.2026 10:00;Yeni;Aras;17.08.2026 10:00;978605000001;Birinci;1;60;X;Y;Z\n"
    TI.store(engine, TN, "ayse", "siparis", "s.csv", ORDERS_CSV + extra)
    out = T.orders(engine, TN, now=NOW)
    assert out["geciken"] == 1 and out["paketSayisi"] == 3
    assert T.orders(engine, TN, durum="geciken", now=NOW)["total"] == 2      # P1'in iki kitap satırı


class Choice:
    def __init__(self, choice, p, margin):
        self.choice, self.probability, self.margin, self.method = choice, p, margin, "logprobs"

    def confident(self, min_prob, min_margin=0.0):
        return self.probability >= min_prob and self.margin >= min_margin


class ChooseLlm:
    def __init__(self, answers, text="Merhaba, ilginiz için teşekkür ederiz."):
        self.answers, self.prompts, self.text = list(answers), [], text

    def choose(self, prompt, labels):
        self.prompts.append((prompt, labels))
        return self.answers.pop(0)

    def chat(self, messages, **kw):
        self.prompts.append((messages[-1]["content"], None))
        return self.text


CLAIMS_CSV = csv(
    "İade Talep No;Barkod;İade Nedeni;Müşteri Açıklaması;Talep Tarihi;Adet",
    "C1;978605000003;Hasarlı Ürün;Kutu ezik geldi;16.08.2026;1",
    "C2;978605000003;Diğer;Aradım ulaşamadım 05321234567;17.08.2026;1",
    "C3;978605000001;Diğer;Sayfalar ters basılmış, kargo da geç geldi;18.08.2026;1",
    "C4;978605000001;;;18.08.2026;1",
)


def test_claims_rule_then_model_with_threshold(engine):
    _seed_logo(engine)
    TI.store(engine, TN, "ayse", "siparis", "s.csv", ORDERS_CSV)
    TI.store(engine, TN, "ayse", "iade", "i.csv", CLAIMS_CSV)
    llm = ChooseLlm([Choice("Vazgeçti", 0.91, 0.7), Choice("Baskı hatası", 0.5, 0.1)])
    out = T.classify_claims(engine, TN, llm, _st())
    assert out == {"kural": 2, "zeki": 1, "eminDegil": 1, "kalan": 0, "atlandi": None}
    rows = {r.talep_id: r for r in T._rows(engine, T.CLAIMS, TN)}
    assert (rows["C1"].neden_sinifi, rows["C1"].sinif_yontemi) == ("Hasarlı ürün", "kural")
    assert (rows["C2"].neden_sinifi, rows["C2"].olasilik) == ("Vazgeçti", 0.91)
    assert rows["C3"].neden_sinifi is None and rows["C3"].sinif_yontemi == "emin-degil"      # iki kural: modele, eşik altı
    assert rows["C4"].neden_sinifi == "Diğer"                                                # metin yok
    assert "05321234567" not in llm.prompts[0][0] and llm.prompts[0][1] == T.CLAIM_CLASSES   # maskeli, kapalı küme
    assert T.classify_claims(engine, TN, None, _st()) == {"kural": 0, "zeki": 0, "eminDegil": 0, "kalan": 0, "atlandi": None}
    view = T.claims(engine, TN)
    b3 = next(b for b in view["kitaplar"] if b["stokKodu"] == "B3")
    assert b3["iadeAdet"] == 2 and b3["satisAdet"] == 5 and b3["oran"] == pytest.approx(0.4)
    assert view["sinifsiz"] == 1


# ------------------------------------------------------------------ soru, yorum, taslak


QUESTIONS_CSV = csv(
    "Soru No;Barkod;Soru;Cevap;Soru Tarihi;Müşteri Adı",
    "Q1;978605000003;Bu kitabın ikinci cildi var mı? ayse@ornek.com;;19.08.2026 08:00;Ayşe",
    "Q2;978605000003;Kaç sayfa?;380 sayfa;18.08.2026 08:00;Ali",
    "Q3;978605000001;Ne zaman gelir?;;20.08.2026 10:00;Veli",
)


def test_questions_unanswered_and_late(engine):
    _seed_logo(engine)
    up = TI.store(engine, TN, "ayse", "soru", "q.csv", QUESTIONS_CSV)
    assert "Müşteri Adı" in up["kolonlar"]["kisiselOlabilir"]
    out = T.questions(engine, TN, _st(), cevapsiz=True, now=NOW)
    assert out["cevapsiz"] == 2 and out["total"] == 2 and out["geciken"] == 1           # Q1 28 saat, Q3 2 saat
    assert out["items"][0]["id"] == "Q1" and "[e-posta]" in out["items"][0]["metin"]


def test_reply_draft_passes_the_guard_and_is_not_sent(engine):
    _seed_logo(engine)
    TI.store(engine, TN, "ayse", "soru", "q.csv", QUESTIONS_CSV)
    llm = ChooseLlm([], text="Merhaba, ikinci cilt hazırlık aşamasındadır. Bu yanıt Qwen ile yazıldı. İlginiz için teşekkürler.")
    out = T.draft_reply(engine, TN, "ayse", llm, "soru", "Q1")
    assert "Qwen" not in out["taslak"] and out["dusen"] == 1 and "teşekkürler" in out["taslak"]
    assert "ayse@" not in llm.prompts[0][0]
    row = next(r for r in T._rows(engine, T.QUESTIONS, TN) if r.soru_id == "Q1")
    assert row.taslak == out["taslak"] and row.taslak_yazan == "ayse" and row.cevaplandi is False
    with pytest.raises(T.DraftError):
        T.draft_reply(engine, TN, "ayse", None, "soru", "Q1")
    with pytest.raises(T.DraftError):
        T.draft_reply(engine, TN, "ayse", llm, "soru", "YOK")


def test_reviews_average_and_low_scores(engine):
    _seed_logo(engine)
    TI.store(engine, TN, "ayse", "yorum", "y.csv", csv(
        "Barkod;Puan;Yorum;Yorum Tarihi", "978605000003;5;Harika;10.08.2026", "978605000003;2;Baskı soluk;12.08.2026",
        "978605000001;1;Gelmedi;13.08.2026"))
    out = T.reviews(engine, TN, max_puan=3)
    assert out["total"] == 2 and out["dusuk"] == 2 and out["ortalama"] == pytest.approx(8 / 3, abs=0.01)
    assert out["kitaplar"][0]["stokKodu"] == "B1" and out["kitaplar"][0]["ortalama"] == 1.0


# ------------------------------------------------------------------ vitrin ve haftalık


def test_showcase_ranks_deep_stock_fast_sellers_and_saves_a_suggestion(engine):
    _seed_logo(engine)
    TI.store(engine, TN, "ayse", "urun", "u.csv", PRODUCTS_CSV)
    TI.store(engine, TN, "ayse", "siparis", "s.csv", ORDERS_CSV)
    out = T.showcase(engine, TN, _st())
    assert [r["stokKodu"] for r in out["items"]] == ["B3"]          # B1 iptal + depo 0; B3 depo 500, 5 adet
    assert out["veriSonu"] == "2026-08-19"
    s = T.showcase_suggest(engine, TN, "ayse", _st(), ["B3", "B1"], ChooseLlm([], text="Stok derin.\n5 kitap iyi satıyor."), "Kasım")
    assert s["platform"] == "trendyol" and s["tur"] == "vitrin" and s["durum"] == "taslak"
    assert [k["stokKodu"] for k in s["payload"]["kitaplar"]] == ["B3"] and s["gerekce"] == "Stok derin."
    with pytest.raises(T.DraftError):
        T.showcase_suggest(engine, TN, "ayse", _st(), ["B1"], None, None)


def test_weekly_uses_the_last_data_day_and_strips_numbers_from_the_summary(engine):
    _seed_logo(engine)
    TI.store(engine, TN, "ayse", "siparis", "s.csv", ORDERS_CSV)
    TI.store(engine, TN, "ayse", "iade", "i.csv", CLAIMS_CSV)
    llm = ChooseLlm([], text="Geciken paketler öne alınmalı.\nToplam 3 paket var.")
    out = T.weekly(engine, TN, _st(), llm=llm, now=NOW)
    assert (out["bas"], out["bit"]) == ("2026-08-13", "2026-08-19")
    assert out["siparis"]["paket"] == 3 and out["iade"]["talep"] == 4 and out["siparis"]["geciken"] == 1
    assert out["ozet"] == "Geciken paketler öne alınmalı."


# ------------------------------------------------------------------ istemci ve yetki


def test_offline_client_refuses_writes_and_never_reaches_the_network():
    def boom(request):
        raise AssertionError(f"ağ çağrısı: {request.method} {request.url}")

    c = TrendyolClient(lambda k: "123" if k == "TRENDYOL_SELLER_ID" else "gizli", transport=httpx.MockTransport(boom))
    for method, path in (("PUT", "product/sellers/123/products/price-and-inventory"), ("POST", "product/sellers/123/products"),
                         ("PUT", "order/sellers/123/shipment-packages/9"), ("POST", "qna/sellers/123/questions/5/answers"),
                         ("GET", "order/sellers/123/claims/9/approve"), ("DELETE", "product/sellers/123/products")):
        with pytest.raises(P.ReadOnlyViolation):
            c.request(method, path)
    with pytest.raises(P.PlatformError):                            # izinli okuma da bu sürümde gönderilmez
        c.get("product/sellers/123/products")
    st = c.status()
    assert st["bagli"] is False and st["tanimli"] is True


def test_access_rules_for_trendyol_endpoints():
    r = AC.rule_for
    assert r("/api/v1/channels/trendyol/stock-diff") == {"sayfa:trendyol-urunler"}
    assert r("/api/v1/channels/trendyol/claims/classify") == {"sayfa:trendyol-siparisler"}
    assert r("/api/v1/channels/trendyol/questions/Q1/draft") == {"sayfa:trendyol-sorular"}
    assert r("/api/v1/channels/trendyol/showcase") == {"sayfa:trendyol"}
    assert r("/api/v1/channels/trendyol/meta") == {"sayfa:trendyol", "sayfa:trendyol-urunler", "sayfa:trendyol-siparisler", "sayfa:trendyol-sorular"}
    assert r("/api/v1/channels/trendyol/run-due") == AC.SYSTEM
    f = AC.features_for
    assert f("POST", "/api/v1/channels/trendyol/imports") == ["ozellik:trendyol.yukle"]
    assert f("DELETE", "/api/v1/channels/trendyol/imports/x") == ["ozellik:trendyol.yukle"]
    assert f("POST", "/api/v1/channels/trendyol/reviews/r1/draft") == ["ozellik:trendyol.taslak"]
    assert f("POST", "/api/v1/channels/trendyol/showcase/suggest") == ["ozellik:trendyol.taslak"]
    assert f("POST", "/api/v1/channels/trendyol/cariler/ekle") == ["ozellik:kanal.eslesme"]
    assert f("POST", "/api/v1/channels/trendyol/suggestions/x/decision") == []       # açıkça verilen, ucun içinde
    assert f("GET", "/api/v1/channels/trendyol/export/stok-farki.xlsx") == ["ozellik:veri.disa-aktar"]
    assert "ozellik:trendyol.oneri-karar" in AC.explicit_keys()
    assert not any(k.startswith("ozellik:magaza") or k.endswith(".yaz") and "trendyol" in k for k in AC.all_keys())


def _api(monkeypatch, store, settings):
    from fastapi.testclient import TestClient

    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    users = {"timas_session=a": "ayse", "timas_session=z": "zekiai"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    monkeypatch.delenv("SEMANTIC_ADMIN_TOKEN", raising=False)
    AC._ready.clear()
    AC.invalidate()
    app = create_app(Runtime(settings, store=store, llm=FakeLlm(["Merhaba, teşekkür ederiz."])))
    return TestClient(app)


def test_api_upload_lists_and_two_eyes(monkeypatch, store, settings):
    client = _api(monkeypatch, store, settings)
    T.ensure(store.engine)
    tn = settings.tenant_id
    S.replace_all(store.engine, tn, S.BARCODES, [{"barkod": "978605000003", "stok_kodu": "B3"}])
    S.replace_all(store.engine, tn, T.LOGO, [{"stok_kodu": "B3", "depo_stok": 500.0, "liste_fiyati": 200.0,
                                                             "liste_kdv_dahil": True, "site_fiyati": None, "site_stok": None}])
    z, a = {"cookie": "timas_session=z"}, {"cookie": "timas_session=a"}
    meta = client.get("/api/v1/channels/trendyol/meta", headers=z).json()
    assert meta["api"]["bagli"] is False and meta["me"]["canDecide"] is True
    up = client.post("/api/v1/channels/trendyol/imports?tur=urun&filename=u.csv", content=PRODUCTS_CSV, headers=z)
    assert up.status_code == 201 and up.json()["satir"] == 4
    assert client.post("/api/v1/channels/trendyol/imports?tur=yok&filename=u.csv", content=PRODUCTS_CSV, headers=z).status_code == 400
    up2 = client.post("/api/v1/channels/trendyol/imports?tur=siparis&filename=s.csv", content=ORDERS_CSV, headers=z)
    assert up2.status_code == 201
    sd = client.get("/api/v1/channels/trendyol/stock-diff", headers=z).json()
    assert sd["counts"]["trendyol-fazla"] == 1
    sug = client.post("/api/v1/channels/trendyol/showcase/suggest", json={"kitaplar": ["B3"]}, headers=z)
    assert sug.status_code == 201
    sid = sug.json()["id"]
    assert client.post(f"/api/v1/channels/trendyol/suggestions/{sid}/decision", json={"karar": "onayli"}, headers=z).status_code == 403
    assert client.post(f"/api/v1/channels/trendyol/suggestions/{sid}/decision", json={"karar": "onayli"}, headers=a).status_code == 403
    x = client.get("/api/v1/channels/trendyol/export/stok-farki.xlsx", headers=z)
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert client.post("/api/v1/channels/trendyol/run-due", headers=a).status_code == 403
    ov = client.get("/api/v1/channels/trendyol/overview", headers=z).json()
    assert ov["toptan"]["eslendi"] is False and ov["urun"]["toplam"] == 4
