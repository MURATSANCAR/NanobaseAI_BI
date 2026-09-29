"""Trendyol/Amazon Aşama 0 (satış modeli tespiti) ve Aşama 1 (mutabakat + hakediş): kalem kuralı, sınıflama (toptan,
konsinye, kendi mağaza, karma, iz yok), pazar yeri carisinin ad/eşleme kuralıyla bulunması (koda sabit ad yok), hakediş
dosyası (uzun/geniş biçim, işaret, kişisel kolon), sipariş numarasının Logo belge alanında bulunması, eşleşti / tutar
farkı / eksik / fazla / iptal / bekliyor, barkod + gün + adet yolu, hakediş ↔ Logo kesinti ve tahsilat, sorgu bilgisi,
yetki kuralları ve uçlar.

Veriler yapaydır ve yalnız kuralları sınar; gerçek Logo ölçümü test sunucusunda (günlük 2026-09-29).
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from semantic_bridge import access as AC
from semantic_bridge import eticaret_sources as E
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge.channels import kaynak_mutabakat as KM
from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import mutabakat as MU
from semantic_bridge.channels import pazaryeri_dosya as PD
from semantic_bridge.channels import pazaryeri_model as PM
from semantic_bridge.channels import sources as src
from semantic_bridge.channels import store as S
from semantic_bridge.channels import trendyol as T
from semantic_bridge.channels import trendyol_import as TI
from semantic_layer.store.catalog_store import open_store

TN = "t1"


def conf(values=None):
    values = values or {}
    return lambda k: values.get(k, "")


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for mod in (S, T, PD, MU):
        mod._ready.discard(id(e))
    T.ensure(e)
    MU.ensure(e)
    return e


def csv(*rows: str) -> bytes:
    return ("\n".join(rows) + "\n").encode("utf-8")


# ------------------------------------------------------------------ kural parçaları


def test_kalem_rule_order():
    k = PM.kalem
    assert k("Satış komisyonu") == "komisyon" and k("Satış iadesi") == "iade" and k("Hakediş ödemesi") == "odeme"
    assert k("Order FBAPerUnitFulfillmentFee") == "kargo" and k("Order Principal") == "satis" and k("Refund Principal") == "iade"
    assert k("E-ticaret stopajı") == "stopaj" and k("Reklam bedeli") == "reklam" and k("Order Tax") == "vergi"
    assert k("Kargo hizmet bedeli") == "kargo" and k("Platform hizmet bedeli") == "hizmet" and k("xyz") == "diger"
    kk = PM.kesinti_kalem          # Logo hizmet kartı (gerçek adlar, 2026-09-29 ölçümü)
    assert kk("Satış Nakliye Giderleri") == "kargo" and kk("Abone Satış Prim Ve Komisyonları") == "komisyon"
    assert kk("Reklam ve İlan Giderleri") == "reklam" and kk("Kırtasiye Giderleri") == "diger" and kk("Satış") == "diger"


def test_name_rules_come_from_settings_not_code():
    r = PM.name_rules(conf({"TRENDYOL_CARI_ADLARI": "DSM GRUP"}), "trendyol")
    assert r["desenler"][0] == "Trendyol" and "DSM GRUP" in r["desenler"]
    r2 = PM.name_rules(conf({"TRENDYOL_CARI_ADLARI": "BAŞKA ŞİRKET"}), "trendyol")
    assert "BAŞKA ŞİRKET" in r2["desenler"]


def test_key_forms_and_tokens():
    assert MU.key_forms("405-1234567-1234567") == {"40512345671234567"}
    assert MU.key_forms("TY100000001") == {"TY100000001", "100000001"}
    assert MU.key_forms("123") == set()
    assert "100000001" in MU.tokens("Sipariş: TY-100000001 / kargo")


# ------------------------------------------------------------------ sınıflama


def _raw(**kw):
    base = {"bas": "2025-01-01", "bit": "2026-08-17", "yillar": [2025, 2026], "eskiSevkTarihi": "2026-07-18",
            "cariler": [{"kod": "T1", "unvan": "DSM GRUP", "kanal": "E-TICARET", "kurallar": ["ad"]}],
            "faturalar": [], "hizmetler": [], "hareketler": [], "sevk": [], "gecikme": [], "doluluk": [], "belgeMetni": [],
            "ayarlar": {"konsinyeGun": 30}, "crm": {}}
    base.update(kw)
    return base


ST = PM.settings(conf())


def test_classify_wholesale_strong():
    raw = _raw(faturalar=[{"yil": 2026, "ay": m, "cari": "T1", "tur": 8, "fatura": 10, "tutar": 1000.0, "doviz": 0} for m in (1, 2, 3, 4)])
    out = PM.classify(raw, ST)
    assert out["model"] == "toptan" and out["guven"] == "guclu"
    assert out["cumle"].startswith("Bu kanalın satış modeli: Toptan (kanıt: DSM GRUP carisine")
    assert out["kesinti"]["bulundu"] is False and "bulunamadı" in out["kesinti"]["cumle"]


def test_classify_consignment_beats_wholesale_and_weak_when_few_months():
    raw = _raw(faturalar=[{"yil": 2026, "ay": 5, "cari": "T1", "tur": 8, "fatura": 3, "tutar": 300.0, "doviz": 0}],
               sevk=[{"yil": 2026, "ay": 2, "cari": "T1", "tur": 8, "satir": 4, "adet": 40, "eskiSatir": 4, "eskiAdet": 40}])
    out = PM.classify(raw, ST)
    assert out["model"] == "konsinye" and out["guven"] == "zayif" and "zayıf" in out["cumle"]
    assert out["izler"]["toptan"]["var"] is True


def test_classify_own_store_from_retail_and_services():
    raw = _raw(faturalar=[{"yil": 2026, "ay": m, "cari": "T1", "tur": 7, "fatura": 50, "tutar": 5000.0, "doviz": 0} for m in (1, 2, 3)],
               hizmetler=[{"yil": 2026, "ay": 1, "cari": "T1", "tur": 4, "hizmetKodu": "H1", "hizmet": "PAZARYERI KOMISYON",
                           "satir": 3, "tutar": 750.0}],
               hareketler=[{"yil": 2026, "ay": 1, "cari": "T1", "modul": 7, "tur": 20, "yon": 1, "hareket": 2, "tutar": 4000.0}])
    out = PM.classify(raw, ST)
    assert out["model"] == "kendi-magaza" and out["guven"] == "guclu"
    assert out["kesinti"]["bulundu"] is True and out["kesinti"]["kalemler"][0]["kalem"] == "komisyon"
    assert out["hakedis"]["bulundu"] is True and "Gelen havale" in out["hakedis"]["cumle"]


def test_classify_mixed_is_undetermined_and_empty_says_why():
    raw = _raw(faturalar=[{"yil": 2026, "ay": 1, "cari": "T1", "tur": 8, "fatura": 5, "tutar": 1.0, "doviz": 0},
                          {"yil": 2026, "ay": 1, "cari": "T1", "tur": 7, "fatura": 5, "tutar": 1.0, "doviz": 0}])
    out = PM.classify(raw, ST)
    assert out["model"] == "belirsiz" and "karma" in out["cumle"] and out["guven"] is None
    none = PM.classify(_raw(cariler=[]), ST)
    assert none["model"] == "belirsiz" and "cari bulunamadı" in none["cumle"]
    quiet = PM.classify(_raw(), ST)
    assert "hareket yok" in quiet["neden"] or "satış, sevk" in quiet["neden"]


def test_small_wholesale_trace_does_not_make_it_mixed():
    """2026-09-29 gerçek ölçümün şekli: mağaza carisine 32 bin perakende fatura (11,5 Mn ₺) + 28 toptan fatura (4,5 bin ₺)."""
    raw = _raw(faturalar=[{"yil": 2026, "ay": m, "cari": "T1", "tur": 7, "fatura": 8000, "tutar": 2_900_000.0, "doviz": 0} for m in (1, 2, 3, 4)]
               + [{"yil": 2026, "ay": 2, "cari": "T1", "tur": 8, "fatura": 28, "tutar": 4535.3, "doviz": 0}])
    out = PM.classify(raw, ST)
    assert out["model"] == "kendi-magaza" and out["guven"] == "guclu"
    assert "yan iz: toptan (satış tutarının %0,0'i)" in out["cumle"] and out["izler"]["toptan"]["yan"] is True
    even = _raw(faturalar=[{"yil": 2026, "ay": 1, "cari": "T1", "tur": 7, "fatura": 5, "tutar": 400.0, "doviz": 0},
                           {"yil": 2026, "ay": 1, "cari": "T1", "tur": 8, "fatura": 5, "tutar": 600.0, "doviz": 0}])
    assert PM.classify(even, ST)["model"] == "belirsiz"


def test_name_only_cari_outside_ecommerce_channel_is_listed_not_counted():
    raw = _raw(cariler=[{"kod": "K1", "unvan": "AMAZON KITAP", "kanal": "KITAPCI", "kurallar": ["ad"],
                         "hesapDisi": "kanal kodu KITAPCI (e-ticaret değil)"}],
               faturalar=[{"yil": 2026, "ay": 1, "cari": "K1", "tur": 8, "fatura": 2, "tutar": 1.0, "doviz": 0}])
    out = PM.classify(raw, ST)
    assert out["cariler"][0]["hesapDisi"] and "cari bulunamadı" in out["kesinti"]["cumle"]


def test_panel_evidence_turns_consumer_invoices_into_own_store():
    out = PM.classify(_raw(), ST, {"eslesenFatura": 30, "eslesenSiparis": 30, "perakende": 30, "farkliCari": 28, "toptan": 0, "ay": 3})
    assert out["model"] == "kendi-magaza" and out["guven"] == "guclu"


# ------------------------------------------------------------------ hakediş dosyası


AMAZON_SETTLEMENT = ("settlement-id\tsettlement-start-date\tsettlement-end-date\tdeposit-date\ttotal-amount\tcurrency\t"
                     "transaction-type\torder-id\tamount-type\tamount-description\tamount\tposted-date\tsku\tbuyer-email\n"
                     "9\t2026-08-01\t2026-08-15\t2026-08-30\t800.00\tTRY\t\t\t\t\t\t\t\t\n"
                     "9\t\t\t\t\t\tOrder\t405-1234567-1234567\tItemPrice\tPrincipal\t1000.00\t2026-08-10\tSKU1\tx@y.z\n"
                     "9\t\t\t\t\t\tOrder\t405-1234567-1234567\tItemFees\tCommission\t-150.00\t2026-08-10\tSKU1\tx@y.z\n"
                     "9\t\t\t\t\t\tOrder\t405-1234567-1234567\tItemFees\tFBAPerUnitFulfillmentFee\t-50.00\t2026-08-10\tSKU1\tx@y.z\n"
                     ).encode("utf-8")


def test_amazon_settlement_long_signed_and_personal_column_skipped():
    p = PD.parse("amazon", "hakedis", "s.txt", AMAZON_SETTLEMENT)
    kal = {(r["kalem"], r["tutar"]) for r in p["rows"]}
    assert kal == {("odeme", 800.0), ("satis", 1000.0), ("komisyon", -150.0), ("kargo", -50.0)}
    assert "buyer-email" in p["personal"] and p["bicim"] == "uzun" and p["eksiyeCevrilen"] == []
    assert all(r["siparis_no"] in (None, "405-1234567-1234567") for r in p["rows"])


def test_trendyol_wide_and_single_amount_sign_flip():
    wide = csv("Sipariş No;Sipariş Tarihi;Satış Tutarı;Komisyon Tutarı;Kargo Bedeli;Hakediş;Müşteri Adı",
               "100000001;10.08.2026;380;57;25;298;Ayşe Yılmaz")
    p = PD.parse("trendyol", "hakedis", "w.csv", wide)
    assert {(r["kalem"], r["tutar"]) for r in p["rows"]} == {("satis", 380.0), ("komisyon", -57.0), ("kargo", -25.0),
                                                              ("net-hakedis", 298.0)}
    assert p["bicim"] == "genis" and "Müşteri Adı" in p["personal"]
    single = csv("İşlem Tarihi;İşlem Tipi;Tutar", "10.08.2026;Satış;380", "10.08.2026;Komisyon;57")
    s = PD.parse("trendyol", "hakedis", "t.csv", single)
    assert {(r["kalem"], r["tutar"]) for r in s["rows"]} == {("satis", 380.0), ("komisyon", -57.0)}
    assert s["eksiyeCevrilen"] == ["Komisyon"]
    with pytest.raises(PD.DosyaError):
        PD.parse("trendyol", "hakedis", "x.csv", csv("Ad;Soyad", "a;b"))
    with pytest.raises(PD.DosyaError):
        PD.parse("trendyol", "siparis", "x.csv", wide)            # Trendyol siparişi M40 yüklemesinde


def test_store_dedups_the_same_settlement_file(engine):
    a = PD.store(engine, TN, "ayse", "amazon", "hakedis", "s.txt", AMAZON_SETTLEMENT)
    PD.store(engine, TN, "ayse", "amazon", "hakedis", "s.txt", AMAZON_SETTLEMENT)
    assert a["satir"] == 4 and len(PD.settlement_rows(engine, TN, "amazon")) == 4
    assert len(PD.list_imports(engine, TN, "amazon")) == 2
    PD.delete(engine, TN, "amazon", a["id"])
    assert len(PD.list_imports(engine, TN, "amazon")) == 1


# ------------------------------------------------------------------ Logo okuması (sahte) ve mutabakat

ORDERS = csv(
    "Paket No;Sipariş Numarası;Sipariş Tarihi;Sipariş Durumu;Barkod;Ürün Adı;Adet;Faturalanacak Tutar",
    "P1;100000001;10.08.2026 10:00;Teslim Edildi;978605000003;Üçüncü;2;380",
    "P2;100000002;11.08.2026 10:00;Teslim Edildi;978605000003;Üçüncü;1;200",
    "P3;100000003;12.08.2026 10:00;Kargoya Verildi;978605000003;Üçüncü;1;100",
    "P4;100000004;12.08.2026 10:00;İptal Edildi;978605000003;Üçüncü;1;100",
    "P5;100000005;19.08.2026 10:00;Yeni;978605000003;Üçüncü;1;50",
)
CLAIMS = csv(
    "İade Talep No;Sipariş Numarası;Barkod;Adet;İade Nedeni;İade Durumu;Talep Tarihi",
    "C1;100000001;978605000003;1;Hasarlı ürün;Onaylandı;15.08.2026",
)
EKSTRE = csv(
    "İşlem Tarihi;İşlem Tipi;Açıklama;Sipariş No;Borç;Alacak;Vade Tarihi;Fatura No",
    "10.08.2026;Satış;Satış;100000001;0;380;20.09.2026;",
    "10.08.2026;Komisyon;Satış komisyonu;100000001;57;0;20.09.2026;TYK2026000000123",
    "11.08.2026;Kargo;Kargo bedeli;100000001;25;0;20.09.2026;",
    "12.08.2026;Satış;Satış;100000003;0;100;20.09.2026;",
    "25.08.2026;Ödeme;Hakediş ödemesi;;298;0;;",
)

INVOICES = [
    {"ref": 1, "tur": 7, "tarih": datetime(2026, 8, 10), "tutar": 380.0, "docode": "TY100000001", "cari": "C-1001", "kanal": "E-TICARET"},
    {"ref": 2, "tur": 7, "tarih": datetime(2026, 8, 11), "tutar": 150.0, "docode": "TY100000002", "cari": "C-1002", "kanal": "E-TICARET"},
    {"ref": 4, "tur": 7, "tarih": datetime(2026, 8, 12), "tutar": 100.0, "specode": "100000004", "cari": "C-1004", "kanal": "E-TICARET"},
    {"ref": 5, "tur": 2, "tarih": datetime(2026, 8, 16), "tutar": 190.0, "genexp1": "Sipariş 100000001 iadesi", "cari": "C-1001"},
    {"ref": 6, "tur": 8, "tarih": datetime(2026, 8, 14), "tutar": 5000.0, "docode": "X", "cari": "T1", "kanal": "E-TICARET"},
    {"ref": 7, "tur": 4, "tarih": datetime(2026, 8, 31), "tutar": 118.0, "ficheno": "TYK2026000000123", "cari": "T1"},
    {"ref": 8, "tur": 7, "tarih": datetime(2026, 8, 12), "tutar": 10.0, "genexp2": "Tel 05321234567", "cari": "C-9999"},
]


def fake_logo(sql: str):
    if "C.CARDTYPE AS kart_turu" in sql:
        return [{"cari_kodu": "T1", "unvan": "DSM GRUP DANISMANLIK ILETISIM", "kanal": "E-TICARET", "kart_turu": 3},
                {"cari_kodu": "X9", "unvan": "TRENDYOL KITAPEVI", "kanal": "KITAPCI", "kart_turu": 1},
                {"cari_kodu": "A1", "unvan": "AMAZON TURKEY PERAKENDE", "kanal": "E-TICARET", "kart_turu": 3}]
    if "F.DOCTRACKINGNR AS doctrackingnr" in sql:
        return [{**{f: None for f in MU.FIELDS}, **r} for r in INVOICES]
    if "S.LINETYPE AS satir_turu" in sql:
        return [{"fatura": 1, "satir_turu": 0, "stok_kodu": "B3", "hizmet_kodu": None, "hizmet": None, "adet": 2, "tutar": 316.67},
                {"fatura": 7, "satir_turu": 4, "stok_kodu": None, "hizmet_kodu": "H1", "hizmet": "PAZARYERI KOMISYON HIZMETI",
                 "adet": 1, "tutar": 100.0}]
    if "CAST(L.DATE_ AS DATE) AS tarih" in sql:
        return [{"cari": "T1", "modul": 7, "tur": 20, "yon": 1, "tarih": date(2026, 8, 26), "hareket": 1, "tutar": 298.0}]
    if "SUM(CASE WHEN ISNULL(F.TRCURR" in sql:
        return [{"cari": "T1", "tur": 8, "ay": m, "fatura": 4, "tutar": 4000.0, "doviz": 0} for m in (1, 2, 3, 4)]
    if "SV.DEFINITION_ AS hizmet, MONTH" in sql:
        return [{"cari": "T1", "tur": 4, "hizmet_kodu": "H1", "hizmet": "PAZARYERI KOMISYON HIZMETI", "ay": 1, "satir": 2, "tutar": 200.0}]
    if "L.SIGN AS yon, MONTH" in sql:
        return [{"cari": "T1", "modul": 7, "tur": 20, "yon": 1, "ay": 2, "hareket": 3, "tutar": 9000.0}]
    if "eski_satir" in sql or "gec_satir" in sql:
        return []
    if "COUNT(DISTINCT F.CLIENTREF) AS cari" in sql:
        return []
    if "AS doctrackingnr" in sql:
        return [{"tur": 8, "fatura": 16, **{f.lower(): 0 for f in PM.BELGE_ALANLARI}, "doctrackingnr": 0}]
    raise AssertionError(sql[:200])


def fake_crm(sql: str):
    if "StringMap" in sql:
        return [{"kod": 9, "ad": "Pazaryeri"}]
    if "AccountBase AS a" in sql:
        return [{"ad": "DSM Grup Danışmanlık", "logicalref": "55", "tip": 9, "yil": 2026, "sayi": 3},
                {"ad": "Amazon Turkey", "logicalref": "66", "tip": 14, "yil": 2026, "sayi": 1}]
    raise AssertionError(sql[:200])


def _patch(monkeypatch):
    monkeypatch.setattr(src, "runner", lambda path, *a, **kw: fake_logo if path == "logo.json" else fake_crm)
    monkeypatch.setattr(src, "firms_by_year", lambda run: {2025: "211", 2026: "411"})
    monkeypatch.setattr(E, "read_data_end", lambda run, firms: date(2026, 8, 31))


def _seed(engine):
    TI.store(engine, TN, "ayse", "siparis", "s.csv", ORDERS)
    TI.store(engine, TN, "ayse", "iade", "i.csv", CLAIMS)
    PD.store(engine, TN, "ayse", "trendyol", "hakedis", "e.csv", EKSTRE)
    S.replace_all(engine, TN, S.BARCODES, [{"barkod": "978605000003", "stok_kodu": "B3"}])


def test_model_refresh_finds_caris_by_rule_and_writes_origin(engine, monkeypatch):
    _patch(monkeypatch)
    out = PM.refresh(engine, TN, "trendyol", "logo.json", "crm.json", "Timas_MSCRM.dbo", conf())
    assert out["cari"] == 1 and out["crmHata"] is None
    raw = S.meta_get(engine, TN, PM.meta_key("trendyol"))
    assert [c["kod"] for c in raw["cariler"]] == ["T1", "X9"] and raw["cariler"][0]["kurallar"] == ["ad"]
    assert raw["cariler"][1]["hesapDisi"] == "kanal kodu KITAPCI (e-ticaret değil)"
    assert [f["ad"] for f in raw["crm"]["firmalar"]] == ["DSM Grup Danışmanlık"]
    assert Y.koken_oku(engine, TN, PM.koken("trendyol"))
    v = PM.view(engine, TN, "trendyol", conf())
    assert v["okundu"] is True and v["model"] == "toptan" and v["crm"]["firmalar"][0]["siparis"][0]["ad"] == "Pazaryeri"
    assert PM.view(engine, TN, "amazon", conf())["okundu"] is False


def test_mapping_rule_adds_a_cari_with_another_name(engine, monkeypatch):
    _patch(monkeypatch)
    S.sync_accounts(engine, TN, [{"cari_kodu": "A1", "unvan": "AMAZON TURKEY PERAKENDE", "kanal": "E-TICARET", "ref": 1, "firma": "411"}], {})
    M.decide(engine, TN, "ayse", "A1", {"platform": "trendyol"})           # insan onayı: ad tutmasa da eşleme kazanır
    cards = PM.discover(fake_logo, engine, TN, "trendyol", conf(), ["411"])
    assert set(cards) == {"T1", "A1", "X9"} and cards["A1"]["kurallar"] == ["esleme-onayli"]
    assert PM.counted(cards) == ["A1", "T1"]


def test_reconcile_by_order_number(engine, monkeypatch):
    _patch(monkeypatch)
    _seed(engine)
    out = MU.refresh(engine, TN, "trendyol", "logo.json", conf())
    assert out["alanIsabeti"] == {"siparis:docode": 2, "siparis:specode": 1, "siparis:genexp1": 1, "belge:ficheno": 1}
    with engine.connect() as c:
        refs = {r.ref for r in c.execute(MU.LOGO_INV.select()).all()}
    assert refs == {1, 2, 4, 5, 6, 7}                                      # 8: ne eşleşti ne pazar yeri carisi
    r = MU.reconcile(engine, TN, "trendyol", conf())
    by = {(x["tur"], x["siparisNo"]): x for x in r["items"] if x["siparisNo"]}
    assert r["yontem"] == "siparis-no"
    assert by[("satis", "100000001")]["sinif"] == "eslesti"
    assert by[("satis", "100000002")]["sinif"] == "tutar-farki" and by[("satis", "100000002")]["fark"] == 50.0
    assert by[("satis", "100000003")]["sinif"] == "eksik-fatura"
    assert by[("satis", "100000004")]["sinif"] == "fazla-fatura"
    assert by[("satis", "100000005")]["sinif"] == "bekliyor"
    assert by[("iade", "100000001")]["sinif"] == "eslesti"
    extra = [x for x in r["items"] if x["siparisNo"] is None]
    assert len(extra) == 1 and extra[0]["faturalar"][0]["ref"] == 6 and extra[0]["sinif"] == "fazla-fatura"
    ov = MU.overview(engine, TN, "trendyol", conf())
    aug = next(m for m in ov["aylik"] if m["ay"] == "2026-08")
    assert (aug["panelSatis"], aug["eslesti"], aug["tutarFarki"], aug["eksik"], aug["fazla"]) == (5, 2, 1, 1, 2)
    assert MU.items(engine, TN, "trendyol", conf(), sinif="eksik-fatura")["total"] == 1
    ev = MU.panel_evidence(engine, TN, "trendyol")
    assert ev["perakende"] == 3 and ev["farkliCari"] == 3
    # Aşama 0'a kanıt: panel siparişi tüketici faturasında + T1'e toptan fatura → karma
    PM.refresh(engine, TN, "trendyol", "logo.json", "crm.json", "Timas_MSCRM.dbo", conf())
    v = PM.view(engine, TN, "trendyol", conf(), ev)
    assert v["model"] == "belirsiz" and "karma" in v["cumle"]


def test_settlement_against_logo(engine, monkeypatch):
    _patch(monkeypatch)
    _seed(engine)
    MU.refresh(engine, TN, "trendyol", "logo.json", conf())
    h = MU.hakedis(engine, TN, "trendyol", conf(), today=date(2026, 9, 1))
    assert h["kesintiToplam"] == 82.0
    assert h["logoKesinti"]["bulundu"] is True and h["logoKesinti"]["toplam"] == 100.0
    assert h["logoTahsilat"]["bulundu"] is True and h["logoTahsilat"]["toplam"] == 298.0
    assert h["belgeler"] == {"toplam": 1, "logodaVar": 1, "logodaYok": []}
    assert [x["siparisNo"] for x in h["logoFaturasiYok"]] == ["100000003"]
    aug = next(m for m in h["aylik"] if m["ay"] == "2026-08")
    assert (aug["satis"], aug["kesinti"], aug["odeme"], aug["logoTahsilat"]) == (480.0, 82.0, 298.0, 298.0)
    assert h["odemeTakvimi"] == [{"tarih": "2026-09-20", "tutar": 398.0}]


def test_settlement_without_logo_kesinti_says_so(engine, monkeypatch):
    _patch(monkeypatch)
    PD.store(engine, TN, "ayse", "trendyol", "hakedis", "e.csv", EKSTRE)
    h = MU.hakedis(engine, TN, "trendyol", conf())
    assert h["logoKesinti"]["bulundu"] is False and "okuması yapılmadı" in h["logoKesinti"]["cumle"]
    assert MU.hakedis(engine, TN, "amazon", conf())["yuklendi"] is False


def test_barcode_day_quantity_fallback(engine, monkeypatch):
    _patch(monkeypatch)
    S.replace_all(engine, TN, S.BARCODES, [{"barkod": "978605000003", "stok_kodu": "B3"}])
    TI.store(engine, TN, "ayse", "siparis", "s.csv", csv(
        "Paket No;Sipariş Numarası;Sipariş Tarihi;Sipariş Durumu;Barkod;Adet;Faturalanacak Tutar",
        "P9;900000001;13.08.2026;Teslim Edildi;978605000003;2;400",
        "P8;900000002;13.08.2026;Teslim Edildi;978605000003;5;400"))
    rows = [{"ref": 6, "tur": 8, "tarih": datetime(2026, 8, 14), "tutar": 5000.0, "docode": "X", "cari": "T1", "kanal": "E-TICARET"}]

    def logo(sql):
        if "F.DOCTRACKINGNR AS doctrackingnr" in sql:
            return [{**{f: None for f in MU.FIELDS}, **r} for r in rows]
        if "S.LINETYPE AS satir_turu" in sql:
            return [{"fatura": 6, "satir_turu": 0, "stok_kodu": "B3", "hizmet_kodu": None, "hizmet": None, "adet": 2, "tutar": 300.0}]
        return fake_logo(sql)

    monkeypatch.setattr(src, "runner", lambda path, *a, **kw: logo)
    MU.refresh(engine, TN, "trendyol", "logo.json", conf())
    r = MU.reconcile(engine, TN, "trendyol", conf())
    by = {x["siparisNo"]: x for x in r["items"]}
    assert r["yontem"] == "barkod-gun-adet"
    assert by["900000001"]["sinif"] == "eslesti" and by["900000002"]["sinif"] == "eksik-fatura"


def test_refresh_needs_panel_files(engine, monkeypatch):
    _patch(monkeypatch)
    with pytest.raises(MU.MutabakatError):
        MU.refresh(engine, TN, "amazon", "logo.json", conf())


# ------------------------------------------------------------------ sorgu bilgisi


def _check(out):
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert P.uncovered_numbers(out, KM.NOT_RAKAM) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [], s
    json.dumps(out, default=str)
    return k


def test_every_number_has_its_query(engine, monkeypatch):
    _patch(monkeypatch)
    _seed(engine)
    MU.refresh(engine, TN, "trendyol", "logo.json", conf())
    PM.refresh(engine, TN, "trendyol", "logo.json", "crm.json", "Timas_MSCRM.dbo", conf())
    with Y.yakala(engine) as q:
        out = PM.view(engine, TN, "trendyol", conf(), MU.panel_evidence(engine, TN, "trendyol"))
    k = _check(P.ekle(out, KM.model(engine, TN, "trendyol", out, q)))
    assert any(s["connection"] == "logo" for s in k["sources"].values())          # asıl sorgu (Logo) eklendi
    with Y.yakala(engine) as q:
        out = MU.overview(engine, TN, "trendyol", conf())
    k = _check(P.ekle(out, KM.mutabakat(engine, TN, "trendyol", out, q)))
    assert any("semantic_mp_logo_invoices" in s["sql"] for s in k["sources"].values())
    with Y.yakala(engine) as q:
        out = MU.items(engine, TN, "trendyol", conf())
    _check(P.ekle(out, KM.mutabakat(engine, TN, "trendyol", out, q)))
    with Y.yakala(engine) as q:
        out = MU.hakedis(engine, TN, "trendyol", conf(), today=date(2026, 9, 1))
    _check(P.ekle(out, KM.hakedis(engine, TN, "trendyol", out, q)))


def test_capture_keeps_queries_that_start_with_comments():
    y = Y.Yakalanan()
    y.ekle("logo", "-- açıklama\n-- ikinci satır\nSELECT C.CODE FROM dbo.LG_411_CLCARD AS C", 1, 2)
    y.ekle("logo", "/* blok */ WITH x AS (SELECT 1 AS a) SELECT a FROM x", 1, 2)
    y.ekle("logo", "-- yalnız açıklama\nDELETE FROM dbo.X", 1, 2)
    assert len(y.queries) == 2


def test_logo_text_fields_are_not_stored(engine, monkeypatch):
    _patch(monkeypatch)
    _seed(engine)
    MU.refresh(engine, TN, "trendyol", "logo.json", conf())
    with engine.connect() as c:
        dump = json.dumps([dict(r._mapping) for r in c.execute(MU.LOGO_INV.select()).all()], default=str)
    assert "05321234567" not in dump and "iadesi" not in dump


# ------------------------------------------------------------------ yetki ve uçlar


def test_access_rules():
    r = AC.rule_for
    assert r("/api/v1/channels/trendyol/mutabakat") == {"sayfa:trendyol-mutabakat"}
    assert r("/api/v1/channels/trendyol/mutabakat/hakedis") == {"sayfa:trendyol-mutabakat"}
    assert r("/api/v1/channels/amazon/mutabakat/liste") == {"sayfa:amazon-mutabakat"}
    assert r("/api/v1/channels/trendyol/model") == {"sayfa:trendyol"}
    assert r("/api/v1/channels/amazon/model/refresh") == {"sayfa:amazon"}
    f = AC.features_for
    assert f("POST", "/api/v1/channels/trendyol/mutabakat/dosyalar") == ["ozellik:trendyol.yukle"]
    assert f("DELETE", "/api/v1/channels/amazon/mutabakat/dosyalar/x") == ["ozellik:amazon.yukle"]
    assert f("GET", "/api/v1/channels/amazon/mutabakat/export/liste.xlsx") == ["ozellik:veri.disa-aktar"]
    assert f("POST", "/api/v1/channels/trendyol/model/refresh") == []
    keys = AC.all_keys()
    assert {"sayfa:trendyol-mutabakat", "sayfa:amazon-mutabakat", "ozellik:amazon.yukle"} <= set(keys)


def test_api_endpoints(monkeypatch, store, settings):
    from semantic_layer.tests.test_trendyol import _api

    client = _api(monkeypatch, store, settings)
    z, a = {"cookie": "timas_session=z"}, {"cookie": "timas_session=a"}
    m = client.get("/api/v1/channels/trendyol/model", headers=z)
    assert m.status_code == 200 and m.json()["okundu"] is False and m.json()["kaynaklar"]
    up = client.post("/api/v1/channels/amazon/mutabakat/dosyalar?tur=hakedis&filename=s.txt", content=AMAZON_SETTLEMENT, headers=z)
    assert up.status_code == 201 and up.json()["satir"] == 4
    assert client.post("/api/v1/channels/amazon/mutabakat/dosyalar?tur=yok&filename=s.txt", content=AMAZON_SETTLEMENT,
                       headers=z).status_code == 400
    h = client.get("/api/v1/channels/amazon/mutabakat/hakedis", headers=z).json()
    assert h["yuklendi"] is True and h["kesintiToplam"] == 200.0 and h["logoKesinti"]["bulundu"] is False
    ov = client.get("/api/v1/channels/amazon/mutabakat", headers=z).json()
    assert ov["okundu"] is False and ov["me"]["canImport"] is True and ov["dosyalar"][0]["tur"] == "hakedis"
    assert client.get("/api/v1/channels/amazon/mutabakat/liste?sinif=eksik-fatura", headers=z).status_code == 200
    x = client.get("/api/v1/channels/amazon/mutabakat/export/liste.xlsx", headers=z)
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert client.get("/api/v1/channels/amazon/mutabakat/export/yok.xlsx", headers=z).status_code == 404
    rf = client.post("/api/v1/channels/amazon/mutabakat/refresh", headers=z)
    assert rf.status_code == 200
    assert client.get("/api/v1/channels/amazon/mutabakat", headers=a).status_code == 200
    assert client.get("/api/v1/channels/amazon/mutabakat").status_code in (401, 403)
    iid = up.json()["id"]
    assert client.delete(f"/api/v1/channels/amazon/mutabakat/dosyalar/{iid}", headers=z).json() == {"ok": True}
