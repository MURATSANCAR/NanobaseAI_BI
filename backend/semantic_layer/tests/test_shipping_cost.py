"""M44 Kargo maliyeti (/kargo/maliyet): tedarikçi grubu vergi kimliğinden (pazar yeri) ve ayardan (kargo firması),
taşıyıcı kodu sadeleştirme ve CRM/ayar eşlemesi, irsaliye başı maliyet yalnız eşlenmiş taşıyıcıda, net ciro oranı,
pazar yeri gönderisi başı, sorgu bilgisi (kaynaksız rakam yok) ve SQL dosyalarının korumadan geçmesi.

Veriler yapaydır ve yalnız kuralları sınar; Logo/CRM'e bağlanılmaz (sahte çalıştırıcı, SQL'ler gerçek dosyalardan).
"""
from __future__ import annotations

from datetime import date

import pytest

from semantic_bridge import access as A
from semantic_bridge import provenance as P
from semantic_bridge import shipping as S
from semantic_bridge import shipping_kaynak as K
from semantic_bridge import shipping_sources as src
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_sorgu_bilgisi_shipping import _check

TN = "t1"
COST = "ozellik:kargo.maliyet"
PAGE = "sayfa:kargo-maliyet"
FIRM = "0a000000-0000-0000-0000-000000000001"
Y = S.today().year

# Vergi kimlikleri yapay; «11111111111» yer tutucu (eşleşmeye girmemeli).
VKN_ARAS, VKN_DSM, VKN_HB, PLACEHOLDER = "0680000001", "3130000002", "2650000003", "11111111111"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    S._ready.discard(id(e))
    S.ensure(e)
    return e


def cost_rows():
    return [
        {"fatura": 1, "tarih": date(Y, 1, 20), "cari": "32001.01.AR001", "unvan": "ARAS KARGO A.Ş.", "vergi": VKN_ARAS,
         "hizmet": "760.34.341", "hizmet_adi": "Posta Ve Kargo Giderleri", "tutar": 300.0},
        {"fatura": 2, "tarih": date(Y, 2, 20), "cari": "32001.01.AR001", "unvan": "ARAS KARGO A.Ş.", "vergi": VKN_ARAS,
         "hizmet": "760.34.341", "hizmet_adi": "Posta Ve Kargo Giderleri", "tutar": 150.0},
        {"fatura": 3, "tarih": date(Y, 2, 25), "cari": "32001.01.DS001", "unvan": "DSM GRUP", "vergi": VKN_DSM,
         "hizmet": "760.34.342", "hizmet_adi": "Satış Nakliye Giderleri", "tutar": 380.0},
        {"fatura": 3, "tarih": date(Y, 2, 25), "cari": "32001.01.DS001", "unvan": "DSM GRUP", "vergi": VKN_DSM,
         "hizmet": "760.34.341", "hizmet_adi": "Posta Ve Kargo Giderleri", "tutar": 20.0},
        {"fatura": 4, "tarih": date(Y, 2, 26), "cari": "32001.01.D-002", "unvan": "D-MARKET", "vergi": f" {VKN_HB} ",
         "hizmet": "760.34.341", "hizmet_adi": "Posta Ve Kargo Giderleri", "tutar": 30.0},
        {"fatura": 5, "tarih": date(Y, 1, 5), "cari": "32001.02.K001", "unvan": "Nakliyeci", "vergi": PLACEHOLDER,
         "hizmet": "770.34.341", "hizmet_adi": "Posta Ve Kargo Giderleri", "tutar": 120.0},
    ]


def receivers():
    return [
        {"cari": "120.01.DSM", "unvan": "DSM GRUP (müşteri)", "vergi": VKN_DSM, "kod": "UPS", "irsaliye": 190},
        {"cari": "120.01.DSM", "unvan": "DSM GRUP (müşteri)", "vergi": VKN_DSM, "kod": "aras", "irsaliye": 10},
        {"cari": "120.01.DMK", "unvan": "D-MARKET (müşteri)", "vergi": VKN_HB, "kod": "HEPSİJET", "irsaliye": 15},
        {"cari": "120.09.PER", "unvan": "Perakende", "vergi": PLACEHOLDER, "kod": "aras", "irsaliye": 40},
    ]


def slips():
    return [
        {"ay": 1, "kod": "aras", "irsaliye": 100, "son": date(Y, 1, 31)},
        {"ay": 2, "kod": "ARAS", "irsaliye": 50, "son": date(Y, 2, 27)},
        {"ay": 2, "kod": "UPS", "irsaliye": 200, "son": date(Y, 2, 27)},
        {"ay": 2, "kod": "HEPSİJET", "irsaliye": 10, "son": date(Y, 2, 27)},
        {"ay": 2, "kod": "hepsijet", "irsaliye": 5, "son": date(Y, 2, 27)},
        {"ay": 2, "kod": None, "irsaliye": 300, "son": date(Y, 2, 28)},
        {"ay": 2, "kod": "  ", "irsaliye": 1, "son": date(Y, 2, 28)},
    ]


def sales():
    return [{"ay": 1, "satis": 10000.0, "iade": 1000.0, "son": date(Y, 1, 31)},
            {"ay": 2, "satis": 20000.0, "iade": 0.0, "son": date(Y, 2, 27)}]


CRM_CARRIERS = {"a": {"ad": "ARAS KARGO", "kod": "ARAS"}, "u": {"ad": "UPS KARGO", "kod": "ups"}}


def view(codes: str = "ARAS KARGO=32001.01.AR001", **over):
    kw = dict(cost_rows=cost_rows(), receivers=receivers(), slips=slips(), sales=sales(), carriers=CRM_CARRIERS,
              carrier_codes=S.parse_carrier_codes(codes), asof=date(Y, 12, 31), notes=[])
    kw.update(over)
    return S.cost_view(Y, **kw)


def by(items, key, value):
    return next(i for i in items if i[key] == value)


# ------------------------------------------------------------------ yardımcılar


def test_tax_key_accepts_10_or_11_digits_and_drops_placeholders():
    assert S.tax_key(" 068 000 0001 ") == "0680000001"
    assert S.tax_key("12345678901") == "12345678901"
    assert S.tax_key(PLACEHOLDER) is None and S.tax_key("0000000000") is None
    assert S.tax_key("12345") is None and S.tax_key("12A4567890") is None
    assert S.tax_key(None) is None and S.tax_key("") is None


def test_carrier_code_is_case_and_turkish_letter_insensitive():
    assert S.carrier_code("HEPSİJET") == S.carrier_code("hepsijet") == "hepsijet"
    assert S.carrier_code(" UPS ") == "ups" and S.carrier_code("DEPO") == S.carrier_code("depo") == "depo"
    assert S.carrier_code("mng kargo") == "mngkargo"
    assert S.carrier_code(None) == S.carrier_code("") == S.carrier_code("  ") == S.NO_CARRIER


def test_default_service_codes_setting_and_admin_declaration():
    from semantic_bridge import admin as AD

    assert S.settings_from(lambda key, default="": default)["costServiceCodes"] == ["760.34.341", "760.34.342", "770.34.341"]
    spec = AD._BY_KEY["SHIPPING_COST_SERVICE_CODES"]
    assert spec["group"] == "shipping" and spec["default"] == S.COST_SERVICE_CODES_DEFAULT and spec["help"]
    assert S.settings_from(lambda key, default="": "700.1;700.2" if key == "SHIPPING_COST_SERVICE_CODES" else default)[
        "costServiceCodes"] == ["700.1", "700.2"]


# ------------------------------------------------------------------ gruplama


def test_supplier_groups_come_from_tax_number_and_carrier_setting():
    v = view()
    groups = {s["cari"]: s["grup"] for s in v["bySupplier"]}
    assert groups["32001.01.DS001"] == "pazarYeri"          # müşterimiz, aynı vergi no, bize kargo faturası kesiyor
    assert groups["32001.01.D-002"] == "pazarYeri"          # vergi no boşluklu yazılmış: yine eşleşir
    assert groups["32001.01.AR001"] == "kargo"              # ayarda eşlenmiş cari
    assert groups["32001.02.K001"] == "nakliye"             # yer tutucu vergi no alıcıyla eşleşmez
    t = v["totals"]
    assert t["gider"] == 1000.0 and t["kargo"] == 450.0 and t["pazarYeri"] == 430.0 and t["nakliye"] == 120.0
    assert t["fatura"] == 5 and t["tedarikci"] == 4                       # 3 numaralı fatura iki hizmet satırı, tek fatura
    dsm = by(v["bySupplier"], "cari", "32001.01.DS001")
    assert dsm["gider"] == 400.0 and dsm["fatura"] == 1 and [h["kod"] for h in dsm["hizmetler"]] == ["760.34.341", "760.34.342"]
    assert dsm["pay"] == 0.4 and dsm["grupAdi"] == "Pazar yeri"



def test_customer_with_a_handful_of_slips_is_not_a_marketplace():
    # 2026 ölçümü: 2 irsaliyeli lojistik müşterisi bir kez kargo faturası kesmişti; pazar yeri sayılıp gönderi başı
    # 15.750 ₺ görünüyordu. Alıcının payı yılın taşıyıcı kodlu irsaliyelerinin %1'inden azsa pazar yeri değildir.
    vkn = "4440000004"
    rows = cost_rows() + [{"fatura": 9, "tarih": date(Y, 2, 1), "cari": "32001.01.DN001", "unvan": "DN LOJİSTİK", "vergi": vkn,
                           "hizmet": "760.34.342", "hizmet_adi": "Satış Nakliye Giderleri", "tutar": 31500.0}]
    rx = receivers() + [{"cari": "120.01.DN", "unvan": "DN LOJİSTİK (müşteri)", "vergi": vkn, "kod": "aras", "irsaliye": 2}]
    v = view(cost_rows=rows, receivers=rx)
    assert by(v["bySupplier"], "cari", "32001.01.DN001")["grup"] == "nakliye"
    assert all("DN LOJİSTİK" not in m["unvan"] for m in v["marketplaces"])
    assert S.MARKET_MIN_SHARE == 0.01


def test_marketplace_per_shipment_far_from_median_is_not_shown():
    # Kargo bedeli başka hesaba yazılan pazar yerinde gider ÷ irsaliye anlamsız küçük çıkar (2026: 0,01 ₺); gösterilmez.
    extra = [("3330000005", "N11", 70.0, 30), ("5550000006", "AMAZON", 0.2, 40)]
    rows, rx = cost_rows(), receivers()
    for i, (vkn, name, amt, n) in enumerate(extra):
        rows.append({"fatura": 20 + i, "tarih": date(Y, 2, 3), "cari": f"32001.01.X{i}", "unvan": name, "vergi": vkn,
                     "hizmet": "760.34.341", "hizmet_adi": "Posta Ve Kargo Giderleri", "tutar": amt})
        rx.append({"cari": f"120.01.X{i}", "unvan": f"{name} (müşteri)", "vergi": vkn, "kod": "UPS", "irsaliye": n})
    ms = view(cost_rows=rows, receivers=rx)["marketplaces"]
    amazon = next(m for m in ms if m["unvan"] == "AMAZON")
    assert amazon["gonderiBasi"] is None and amazon.get("sapma") is True
    assert next(m for m in ms if m["unvan"] == "N11")["gonderiBasi"] is not None and not next(m for m in ms if m["unvan"] == "N11").get("sapma")


def test_without_receivers_nothing_is_a_marketplace():
    v = view(receivers=[])
    assert all(s["grup"] != "pazarYeri" for s in v["bySupplier"]) and v["marketplaces"] == []
    assert v["totals"]["pazarYeri"] == 0.0


def test_without_carrier_mapping_carrier_group_is_empty():
    v = view(codes="")
    assert all(s["grup"] != "kargo" for s in v["bySupplier"])
    assert by(v["bySupplier"], "cari", "32001.01.AR001")["grup"] == "nakliye"


# ------------------------------------------------------------------ taşıyıcı ve irsaliye başı


def test_carrier_codes_merge_and_map_to_crm_names():
    v = view()
    aras = by(v["byCarrier"], "ad", "ARAS KARGO")
    assert aras["kodlar"] == ["aras"] and aras["irsaliye"] == 150                 # «aras» + «ARAS» tek satır
    ups = by(v["byCarrier"], "kod", "ups")
    assert ups["crmFirma"] == "UPS KARGO" and ups["irsaliye"] == 200
    hj = by(v["byCarrier"], "kod", "hepsijet")
    assert hj["irsaliye"] == 15 and hj["ad"] == "HEPSİJET" and hj["crmFirma"] is None   # CRM'de yok: en sık yazılış
    none = v["byCarrier"][-1]
    assert none["tasiyiciYok"] and none["kod"] == S.NO_CARRIER and none["irsaliye"] == 301 and not none["eslendi"]
    assert v["totals"]["irsaliye"] == 365 and v["totals"]["tasiyiciYok"] == 301


def test_per_slip_cost_only_when_carrier_is_mapped():
    v = view()
    aras = by(v["byCarrier"], "ad", "ARAS KARGO")
    assert aras["eslendi"] and aras["gider"] == 450.0 and aras["irsaliyeBasi"] == 3.0
    assert aras["eslenenCariler"] == [{"cari": "32001.01.AR001", "unvan": "ARAS KARGO A.Ş."}]
    ups = by(v["byCarrier"], "kod", "ups")
    assert not ups["eslendi"] and ups["gider"] is None and ups["irsaliyeBasi"] is None and ups["eslenenCariler"] == []
    none = v["byCarrier"][-1]
    assert none["irsaliyeBasi"] is None and none["gider"] is None
    assert ups["durum"] == "pazarYeri" and ups["adayCariler"] == []        # 200 irsaliyenin 190'ı pazar yerine
    assert by(v["byCarrier"], "kod", "hepsijet")["durum"] == "pazarYeri"
    assert any(n.startswith("Bedelini pazar yeri faturalayan taşıyıcı:") for n in v["notes"])
    assert not any("eşlenmemiş taşıyıcı" in n for n in v["notes"])


def test_unmapped_carrier_with_invoice_gets_a_candidate():
    v = view(codes="")
    aras = by(v["byCarrier"], "ad", "ARAS KARGO")
    assert aras["durum"] == "eslenebilir" and not aras["eslendi"]
    assert [a["cari"] for a in aras["adayCariler"]] == ["32001.01.AR001"]
    assert any(n.startswith("Logo'da faturası bulunan ama carisi eşlenmemiş taşıyıcı: ARAS KARGO") for n in v["notes"])
    # «KARGO» iki taşıyıcı adında geçer, ayırt edici değil: UPS'e Aras aday gösterilmez
    assert by(v["byCarrier"], "kod", "ups")["adayCariler"] == []


def test_code_without_any_invoice_is_not_asked_to_be_mapped():
    v = view(slips=slips() + [{"ay": 2, "kod": "depo", "irsaliye": 30, "son": date(Y, 2, 27)}])
    depo = by(v["byCarrier"], "kod", "depo")
    assert depo["durum"] == "faturasiz" and depo["adayCariler"] == [] and depo["irsaliyeBasi"] is None
    assert any(n.startswith("Logo'da kargo faturası bulunmayan irsaliye kodları: depo") for n in v["notes"])


def test_supplier_mapped_to_another_carrier_is_not_a_candidate():
    extra = [{"ay": 2, "kod": "araskargo", "irsaliye": 5, "son": date(Y, 2, 27)}]
    v = view(slips=slips() + extra)                                        # 32001.01.AR001 Aras'a eşli
    assert by(v["byCarrier"], "kod", "araskargo")["durum"] == "faturasiz"


def test_mapping_by_raw_carrier_code_works_without_crm_name():
    v = view(codes="ARAS KARGO=32001.01.AR001;hepsijet=32001.01.D-002")
    hj = by(v["byCarrier"], "kod", "hepsijet")
    assert hj["eslendi"] and hj["gider"] == 30.0 and hj["irsaliyeBasi"] == 2.0
    assert by(v["bySupplier"], "cari", "32001.01.D-002")["grup"] == "pazarYeri"     # vergi no eşleşmesi önce gelir
    assert by(v["bySupplier"], "cari", "32001.01.D-002")["tasiyicilar"] == ["hepsijet"]


def test_crm_unavailable_falls_back_to_codes():
    v = view(carriers={})
    aras = by(v["byCarrier"], "kod", "aras")
    assert aras["crmFirma"] is None and aras["ad"] == "aras" and aras["irsaliye"] == 150
    assert not aras["eslendi"]                                   # ayar anahtarı «ARAS KARGO»; kod «aras» eşleşmez


# ------------------------------------------------------------------ pazar yeri


def test_marketplace_per_shipment_excludes_slips_of_other_mapped_carriers():
    v = view()
    dsm = by(v["marketplaces"], "unvan", "DSM GRUP")
    assert dsm["gider"] == 400.0 and dsm["irsaliye"] == 190 and dsm["baskaTasiyici"] == 10    # «aras» Aras'ın faturasında
    assert dsm["gonderiBasi"] == round(400 / 190, 2)
    assert dsm["alicilar"] == [{"cari": "120.01.DSM", "unvan": "DSM GRUP (müşteri)", "irsaliye": 190}]
    assert dsm["kodlar"] == [{"kod": "ups", "ad": "UPS KARGO", "irsaliye": 190}]
    hb = by(v["marketplaces"], "unvan", "D-MARKET")
    assert hb["irsaliye"] == 15 and hb["gonderiBasi"] == 2.0
    ups = by(v["byCarrier"], "kod", "ups")
    assert ups["pazarYeriIrsaliye"] == 190 and ups["pazarYerleri"] == [{"unvan": "DSM GRUP", "irsaliye": 190}]
    assert v["marketplaces"][0]["unvan"] == "DSM GRUP"           # gidere göre sıralı


# ------------------------------------------------------------------ ciro oranı ve aylar


def test_net_sales_ratio_and_months():
    v = view()
    t = v["totals"]
    assert t["netCiro"] == 29000.0 and t["oran"] == round(1000 / 29000, 6)
    assert t["irsaliyeBasi"] == round(1000 / 365, 2)
    jan, feb = v["byMonth"]
    assert jan["ay"] == f"{Y}-01" and jan["netCiro"] == 9000.0 and jan["kargo"] == 300.0 and jan["nakliye"] == 120.0
    assert jan["toplam"] == 420.0 and jan["oran"] == round(420 / 9000, 6) and jan["irsaliye"] == 100
    assert feb["pazarYeri"] == 430.0 and feb["irsaliye"] == 265
    assert {x["kod"]: x["irsaliye"] for x in feb["tasiyici"]} == {"ups": 200, "aras": 50, "hepsijet": 15}
    assert v["dataEnd"] == f"{Y}-02-27" and v["giderSonu"] == f"{Y}-02-26" and v["irsaliyeSonu"] == f"{Y}-02-28"


def test_no_sales_means_no_ratio_not_zero():
    v = view(sales=[])
    assert v["totals"]["netCiro"] is None and v["totals"]["oran"] is None
    assert all(m["oran"] is None for m in v["byMonth"])


def test_invoice_lag_is_noted_from_data():
    lagging = [dict(r, tarih=date(Y, 1, 10)) for r in cost_rows()]
    v = view(cost_rows=lagging)
    assert any("faturası henüz gelmemiş" in n for n in v["notes"])
    assert not any("faturası henüz gelmemiş" in n for n in view()["notes"])


# ------------------------------------------------------------------ SQL dosyaları


def test_cost_sql_files_pass_guard_and_leave_no_placeholder():
    built = [
        src.sql("logo_kargo_gider", f="411", hizmetler=src.service_codes(["760.34.341", "770.34.341"]), bas=f"{Y}-01-01", bit=f"{Y + 1}-01-01"),
        src.sql("logo_kargo_alici", f="411", hizmetler=src.service_codes(["760.34.341"]), bas=f"{Y}-01-01", bit=f"{Y + 1}-01-01"),
        src.sql("logo_kargo_irsaliye", f="411", bas=f"{Y}-01-01", bit=f"{Y + 1}-01-01"),
        src.sql("logo_net_ciro", f="411", bas=f"{Y}-01-01", bit=f"{Y + 1}-01-01"),
    ]
    for s in built:
        assert src.guard(s) == s
        assert "--" not in s and P.placeholders_left(s) == []
        assert not any(col in s.lower() for col in src.FORBIDDEN_COLUMNS)
        assert P.clean_sql(s)                                   # sır izi / parola kolonu yok
    assert "LINETYPE = 4" in built[0] and "'760.34.341', '770.34.341'" in built[0]
    with pytest.raises(src.SourceError):
        src.service_codes([])
    with pytest.raises(src.SourceError):
        src.service_codes(["760'; DROP"])


# ------------------------------------------------------------------ uç: yetki, sorgu bilgisi, anlık görüntü


class CostRun:
    """Sahte bağlantı: `sql()` ile kurulan metnin dosya adına göre satır döndürür."""

    def __call__(self, text: str) -> list[dict]:
        if "L_CAPIPERIOD" in text:
            return [{"FIRMNR": 411, "BEGDATE": date(Y - 1, 1, 1), "ENDDATE": date(Y, 12, 31)}]
        last = getattr(src._tl, "last", None)
        name = last[0] if last and last[1] == text else ""
        return {
            "crm_kargo_firma": [{"id": FIRM, "ad": "ARAS KARGO", "kod": "aras"}],
            "logo_kargo_gider": cost_rows(), "logo_kargo_alici": receivers(), "logo_kargo_irsaliye": slips(),
            "logo_net_ciro": sales(),
        }.get(name, [])


class Boom:
    def __call__(self, text: str) -> list[dict]:
        raise src.SourceError("Kaynağa gidilmemeliydi")


def _client(engine, monkeypatch, perms: set[str], run=None):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from semantic_bridge import shipping_api

    monkeypatch.setattr(src, "runner", lambda path: run or CostRun())
    app = FastAPI()
    conf = {"SHIPPING_LOGO_CARRIER_CODES": "ARAS KARGO=32001.01.AR001"}
    shipping_api.register(app, {
        "auth": lambda r: (engine, TN, "ayse", "Ayşe"), "require_caller": lambda r: None, "can": lambda u, k: k in perms,
        "is_admin": lambda u: False, "audit": lambda *a, **k: None, "conf": lambda k, d="": conf.get(k, d),
        "engine": lambda: engine, "tenant": lambda: TN, "logo_file": lambda: "", "crm_file": lambda: "",
        "llm": lambda p: None, "send_mail": lambda *a: "ok",
    })
    return TestClient(app)


def test_access_rules_for_cost_page():
    assert A.rule_for("/api/v1/shipping/cost") == frozenset({PAGE})
    assert A.rule_for("/api/v1/shipping/export/maliyet.xlsx") == frozenset({PAGE})
    assert PAGE in A.rule_for("/api/v1/shipping/meta")
    assert PAGE in A.all_keys() and PAGE not in A.explicit_keys()


def test_cost_endpoint_needs_cost_right_and_valid_year(engine, monkeypatch):
    assert _client(engine, monkeypatch, {PAGE}).get("/api/v1/shipping/cost").status_code == 403
    c = _client(engine, monkeypatch, {PAGE, COST})
    r = c.get(f"/api/v1/shipping/cost?yil={Y - 5}")
    assert r.status_code == 400 and str(Y) in r.json()["detail"]["message"]
    m = c.get("/api/v1/shipping/meta").json()["me"]
    assert m["maliyetSayfa"] is True
    assert _client(engine, monkeypatch, {COST}).get("/api/v1/shipping/meta").json()["me"]["maliyetSayfa"] is False


def test_cost_endpoint_every_number_has_a_source(engine, monkeypatch):
    c = _client(engine, monkeypatch, {PAGE, COST})
    r = c.get("/api/v1/shipping/cost")
    assert r.status_code == 200, r.text
    out = r.json()
    k = _check(out)
    assert out["period"]["yil"] == Y and out["yillar"] == [Y - 1, Y] and out["totals"]["gider"] == 1000.0
    for name in ("logo_kargo_gider", "logo_kargo_alici", "logo_kargo_irsaliye", "logo_net_ciro"):
        sid = f"kargo.cost.{name}"
        assert sid in k["sources"] and "LG_411_" in k["sources"][sid]["sql"], sid
    assert "kargo.cost.logo_net_ciro" in k["formulas"]["ciro"]["inputs"]
    assert "kargo.cost.logo_kargo_irsaliye" in k["formulas"]["irsaliye"]["inputs"]
    assert "hesap:gider" in k["formulas"]["gonderiBasi"]["inputs"]
    assert any(i.startswith("kargo.ayar.") for i in k["formulas"]["gider"]["inputs"])       # hizmet kodu ayarı
    assert k["fields"]["totals.irsaliyeBasi"] == "hesap:gonderiBasi"


def test_cost_snapshot_answers_without_logo(engine, monkeypatch):
    live = _client(engine, monkeypatch, {PAGE, COST}).get("/api/v1/shipping/cost").json()
    r = _client(engine, monkeypatch, {PAGE, COST}, run=Boom()).get("/api/v1/shipping/cost")
    assert r.status_code == 200, r.text
    out = r.json()
    assert {k: v for k, v in out.items() if k != "kaynaklar"} == {k: v for k, v in live.items() if k != "kaynaklar"}
    k = _check(out)
    snap = k["sources"]["kargo.cost.anlik"]
    assert snap["connection"] == "portal" and "kargo.cost.logo_kargo_gider" in snap["origin"]


def test_cost_export_writes_supplier_table(engine, monkeypatch):
    c = _client(engine, monkeypatch, {PAGE, COST})
    r = c.get("/api/v1/shipping/export/maliyet.xlsx")
    assert r.status_code == 200 and r.headers["content-type"].startswith(S.XLSX_MIME)
    assert _client(engine, monkeypatch, {COST}).get("/api/v1/shipping/export/maliyet.xlsx").status_code == 403
