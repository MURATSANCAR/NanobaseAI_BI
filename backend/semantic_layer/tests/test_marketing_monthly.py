"""M18 Aylık pazarlama planı ve satış föyü: dönem yardımcıları, çakışma kuralları, kaynak eşitlemede elle düzeltmenin
korunması, bütçe dağılımı (hedef payı × önceki ay açığı), müdür düzeltmesi ve çekirdek bütçe satırlarına yansıma, onay ve
revizyonda ay kalemlerinin kopyalanması, föy alanları ve kaynakları, fiyat/barkod uyumsuzluğu, CRM değişince «eski»,
föy onayında iki göz, eksik alan ve gerekçeli kabul, PDF sayfa sayısı, yetki kuralları ve uçlar.

Veriler yapaydır ve yalnız kuralları sınar; gerçek CRM/Logo kabulü test sunucusunda (`scripts/acceptance/m18/`).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import budget as B
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import foy as F
from semantic_bridge.marketing import monthly as M
from semantic_bridge.marketing import plans as P
from semantic_layer.store.catalog_store import open_store

T = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for s in (C._ready, B._ready, M._ready, F._ready):
        s.discard(id(e))
    C.ensure(e)
    B.ensure(e)
    M.ensure(e)
    F.ensure(e)
    yield e
    for s in (C._ready, B._ready, M._ready, F._ready):
        s.discard(id(e))


def _st(**over):
    s = M.settings(lambda k: "")
    s.update(over)
    return s


def _fst(**over):
    s = F.settings(lambda k: "")
    s.update(over)
    return s


def _book(code, pub, **kw):
    b = {"kitapId": None, "stokKodu": code, "ad": f"Kitap {code}", "yazar": "Yazar", "yayinevi": "Timaş", "kitaplik": "Roman",
         "hedefKitle": "Yetişkin", "statu": None, "kapak": None,
         "tarihler": {"crm-kitap": pub, "crm-proje": None, "uretim-dagilim": None, "uretim-depo": None},
         "projeId": None, "projeAdi": None, "sorumlu": None, "sorumluHesap": None}
    b.update(kw)
    return b


class FakeCrm:
    def __init__(self, books=None, camps=None, days=None, spend=None, raw=None):
        self._books, self._camps, self._days, self._spend, self._raw = books or [], camps or [], days or [], spend or [], raw or {}

    def new_books(self, frm, to, fresh=False):
        return list(self._books)

    def campaigns(self, frm, to, fresh=False):
        return list(self._camps)

    def all_special_days(self, fresh=False):
        return list(self._days)

    def spend(self, since, fresh=False):
        return list(self._spend)

    def region_targets(self, year, month, codes):
        return {}

    def foy_books(self, codes, fresh=False):
        return {c: self._raw[c] for c in codes if c in self._raw}

    def book(self, stok, fresh=False):
        b = next((x for x in self._books if x["stokKodu"] == stok), None)
        return {**b, "metinler": {}, "proje": {}} if b else None

    def email_of(self, user):
        return None


def _targets(monkeypatch, items):
    def fake(engine, tenant, year, codes=None, segment="", yayinevi="", with_actuals=True):
        return {"year": year, "plan": {"id": "BP1", "version": 1, "title": "Bütçe", "scenario": "temel"}, "items": items}
    monkeypatch.setattr(B, "approved_targets", fake)


def _t(code, seg, month_ciro, month=11):
    aylik = [{"ay": i + 1, "adet": 0.0, "ciro": 0.0} for i in range(12)]
    aylik[month - 1] = {"ay": month, "adet": 10.0, "ciro": month_ciro}
    aylik[month - 2] = {"ay": month - 1, "adet": 10.0, "ciro": month_ciro}
    return {"stokKodu": code, "segment": seg, "aylik": aylik, "hedef": {"adet": 10, "ciro": month_ciro * 2, "marj": None}}


# ------------------------------------------------------------------ dönem


def test_period_helpers():
    assert M.parse_donem("2026-11") == "2026-11"
    for bad in ("2026-13", "26-11", "2026/11", ""):
        with pytest.raises(C.MarketingError):
            M.parse_donem(bad)
    assert M.shift("2026-12", 1) == "2027-01" and M.shift("2026-01", -1) == "2025-12"
    assert M.default_donem(date(2026, 9, 14), 15) == "2026-09" and M.default_donem(date(2026, 9, 15), 15) == "2026-10"
    ws = M.weeks("2026-11")
    assert ws[0]["baslangic"] == "2026-11-01" and ws[-1]["bitis"] == "2026-11-30"
    assert all(date.fromisoformat(w["baslangic"]).weekday() == 0 for w in ws[1:])
    assert M.nth_workday(2026, 11, 3) == date(2026, 11, 4)    # 1 Kasım 2026 pazar


# ------------------------------------------------------------------ çakışma


def _it(i, tur="yeni", kaynak="crm-kitap", hafta="2026-W46", kitaplik="Gençlik", **kw):
    return {"id": i, "tur": tur, "kaynak": kaynak, "hafta": hafta, "kitaplik": kitaplik, "hedef_kitle": "Genç", "baslik": i,
            "baslangic": kw.pop("baslangic", "2026-11-10"), "bitis": kw.pop("bitis", None), "kanal": kw.pop("kanal", None),
            "detay": kw.pop("detay", {}), **kw}


def test_same_week_same_library_launches_conflict():
    out = M.conflicts([_it("a"), _it("b"), _it("c", kitaplik="Roman"), _it("d", hafta="2026-W47")], ["kitaplik"])
    assert set(out) == {"a", "b"} and out["a"][0]["ile"] == ["b"]
    both = M.conflicts([_it("a"), _it("c", kitaplik="Roman")], ["kitaplik", "hedef-kitle"])
    assert set(both) == {"a", "c"} and both["a"][0]["kural"] == "ayni-hafta-hedef-kitle"


def test_overlapping_campaigns_on_the_same_channel_conflict():
    a = _it("k1", tur="b2b-kampanya", kaynak="crm-kampanya", baslangic="2026-11-01", bitis="2026-11-15",
            kanal="satis-kampanyasi", detay={"mecra": "B2B"})
    b = _it("k2", tur="b2b-kampanya", kaynak="crm-kampanya", baslangic="2026-11-10", bitis="2026-11-20",
            kanal="satis-kampanyasi", detay={"mecra": "B2B"})
    c = _it("k3", tur="b2b-kampanya", kaynak="crm-kampanya", baslangic="2026-11-10", bitis="2026-11-20",
            kanal="satis-kampanyasi", detay={"mecra": "CRM"})
    d = _it("k4", tur="b2b-kampanya", kaynak="crm-kampanya", baslangic="2026-11-16", bitis="2026-11-30",
            kanal="satis-kampanyasi", detay={"mecra": "CRM"})
    out = M.conflicts([a, b, c, d], ["kitaplik"])
    assert set(out) == {"k1", "k2", "k3", "k4"} and out["k1"][0]["ile"] == ["k2"] and out["k3"][0]["ile"] == ["k4"]


# ------------------------------------------------------------------ kurma ve eşitleme


def test_build_collects_sources_and_keeps_manual_edits(engine, monkeypatch):
    _targets(monkeypatch, [_t("N1", "yeni", 1000.0), _t("B1", "backlist", 3000.0)])
    crm = FakeCrm(books=[_book("N1", "2026-11-10"), _book("N2", "2026-11-11"), _book("OUT", "2026-12-02")],
                  camps=[{"id": "c1", "ad": "Kasım B2B", "tip": 1, "baslangic": "2026-11-01", "bitis": "2026-11-30", "mecra": 2}],
                  days=[{"id": "d1", "ad": "Öğretmenler Günü", "hafta1": None, "hafta2": None, "tarih": "2020-11-24", "kitapSayisi": 7}])
    st = _st()
    res = M.build(engine, T, "ayse", crm, st, "2026-11")
    v = M.view(engine, T, "2026-11", st)
    kinds = sorted(x["tur"] for x in v["items"])
    assert kinds == ["b2b-kampanya", "ozel-gun", "yeni", "yeni"]           # OUT aralık dışı
    assert v["cakismaSayisi"] == 2                                           # N1, N2 aynı hafta, aynı kitaplık
    n1 = next(x for x in v["items"] if x["stokKodu"] == "N1")
    assert n1["detay"]["hedefAy"]["ciro"] == 1000.0
    assert any("backlist" in n for n in res["notlar"])                       # M17 yokken söylenir
    M.update_item(engine, T, "ayse", res["planId"], "2026-11", n1["id"], {"baslangic": "2026-11-17"}, st)
    crm._books = [_book("N1", "2026-11-12")]                                  # CRM'de gün değişti, N2 düştü
    M.build(engine, T, "ayse", crm, st, "2026-11")
    items = {x["stokKodu"]: x for x in M.view(engine, T, "2026-11", st)["items"] if x["tur"] == "yeni"}
    assert set(items) == {"N1"} and items["N1"]["baslangic"] == "2026-11-17" and items["N1"]["elle"]
    assert M.view(engine, T, "2026-11", st)["cakismaSayisi"] == 0


def test_user_item_is_kept_and_only_it_can_be_deleted(engine, monkeypatch):
    _targets(monkeypatch, [])
    crm = FakeCrm(books=[_book("N1", "2026-11-10")])
    st = _st()
    pid = M.build(engine, T, "ayse", crm, st, "2026-11")["planId"]
    mine = M.add_item(engine, T, "ayse", pid, "2026-11", {"tur": "diger", "baslik": "Kitap fuarı", "baslangic": "2026-11-20"}, st)
    with pytest.raises(C.MarketingError):
        M.add_item(engine, T, "ayse", pid, "2026-11", {"tur": "diger", "baslik": "Aralık", "baslangic": "2026-12-20"}, st)
    M.build(engine, T, "ayse", crm, st, "2026-11")
    ids = {x["id"] for x in M.items_of(engine, pid)}
    assert mine["id"] in ids
    src = next(x for x in M.items_of(engine, pid) if x["kaynak"] == "crm-kitap")
    with pytest.raises(C.MarketingError) as e:
        M.delete_item(engine, T, "ayse", pid, src["id"], st)
    assert e.value.status == 409
    M.delete_item(engine, T, "ayse", pid, mine["id"], st)


# ------------------------------------------------------------------ bütçe


def test_segment_weight_boosts_the_segment_under_target():
    t = {"segment": {"yeni": {"ciro": 250.0}, "backlist": {"ciro": 750.0}}}
    w = M.segment_weights(t, {"yeni": {"oran": 1.1}, "backlist": {"oran": 0.7}})
    assert w["yeni"]["carpan"] == 1.0 and w["backlist"]["carpan"] == pytest.approx(1.3)
    assert w["backlist"]["pay"] == pytest.approx(0.75 * 1.3 / (0.25 + 0.75 * 1.3))
    assert M.segment_weights({"segment": {}}, {}) == {}


def test_budget_suggestion_sums_to_frame_manual_value_survives_and_mirrors_lines(engine, monkeypatch):
    _targets(monkeypatch, [_t("N1", "yeni", 1000.0), _t("B1", "backlist", 3000.0)])
    spend = [{"id": "s1", "tip": 1, "tipAdi": "Basın", "tutar": 600.0, "stokKodu": "N1"},
             {"id": "s2", "tip": 4, "tipAdi": "Sosyal Medya", "tutar": 400.0, "stokKodu": "B1"}]
    crm = FakeCrm(books=[_book("N1", "2026-11-10")], spend=spend)
    st = _st(monthlyBudget=10_000.0)
    pid = M.build(engine, T, "ayse", crm, st, "2026-11")["planId"]
    rows = M.budget_of(engine, pid)
    assert round(sum(r["oneri"] for r in rows), 2) == 10_000.0
    assert {(r["segment"], r["kanal"]) for r in rows} == {("yeni", "basin"), ("backlist", "sosyal-medya")}
    total = M.put_budget(engine, T, "mudur", pid, "2026-11", {"items": [{"segment": "yeni", "kanal": "basin", "onayli": 4000}]})
    backlist = next(r for r in M.budget_of(engine, pid) if r["segment"] == "backlist")
    assert total == 4000 + backlist["oneri"]
    plan = C.plan_full(engine, T, pid)
    assert plan["butceToplam"] == total and len(plan["lines"]) == 2
    M.build(engine, T, "ayse", crm, st, "2026-11")                            # yeniden kurma düzeltmeyi korur
    assert next(r for r in M.budget_of(engine, pid) if r["segment"] == "yeni")["onayli"] == 4000


def test_frame_prefers_manual_then_setting_then_rate(engine):
    plan = {"butceCerceve": 5000.0, "butceCerceveKaynak": {"kaynak": "elle"}}
    t = {"segment": {"yeni": {"ciro": 100_000.0}, "backlist": {"ciro": 100_000.0}}}
    assert M.frame_of(engine, plan, t, _st())["kaynak"] == "elle"
    assert M.frame_of(engine, {}, t, _st(monthlyBudget=7000.0))["tutar"] == 7000.0
    fr = M.frame_of(engine, {}, t, _st(rate=0.02))
    assert fr["tutar"] == 4000.0 and fr["kaynak"] == "oran"
    assert M.frame_of(engine, {}, {"segment": {}}, _st(rate=0.02))["tutar"] is None


def test_month_plan_approval_revision_copies_items_and_delete_cleans(engine, monkeypatch):
    _targets(monkeypatch, [_t("N1", "yeni", 1000.0)])
    crm = FakeCrm(books=[_book("N1", "2026-11-10")], spend=[{"id": "s1", "tip": 1, "tipAdi": "Basın", "tutar": 1.0, "stokKodu": "N1"}])
    st = _st(monthlyBudget=1000.0)
    pid = M.build(engine, T, "ayse", crm, st, "2026-11")["planId"]
    C.submit(engine, T, "ayse", pid)
    with pytest.raises(C.MarketingError):
        M.build(engine, T, "ayse", crm, st, "2026-11")                        # onaydaki plan yeniden kurulmaz
    C.decide(engine, T, "mudur", pid, True, None, level="pazarlama", threshold=None)
    new = C.revise(engine, T, "ayse", pid, "hedef değişti")
    assert len(M.items_of(engine, new["id"])) == len(M.items_of(engine, pid)) == 1
    assert len(M.budget_of(engine, new["id"])) == 1
    assert M.find_plan(engine, T, "2026-11")["id"] == new["id"]
    assert M.find_plan(engine, T, "2026-11", approved=True)["id"] == pid
    C.delete_plan(engine, T, new["id"])
    with engine.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(M.ITEMS).where(M.ITEMS.c.plan_id == new["id"])).scalar() == 0


def test_previous_month_ratio_uses_the_same_books(engine, monkeypatch):
    _targets(monkeypatch, [_t("N1", "yeni", 1000.0, month=11), _t("B1", "backlist", 2000.0, month=11)])
    with engine.begin() as c:
        c.execute(B.SALES.insert(), [{"year": 2026, "month": 10, "stok_kodu": "N1", "adet": 5, "ciro": 500.0, "maliyet": 0, "maliyetli_ciro": 0},
                                     {"year": 2026, "month": 10, "stok_kodu": "157X", "adet": 5, "ciro": 999.0, "maliyet": 0, "maliyetli_ciro": 0}])
    B.meta_set(engine, "data_end", {"date": "2026-10-31"})
    t, a = M.month_targets(engine, T, "2026-10"), M.month_actuals(engine, "2026-10")
    r = M.segment_ratios(t, a)
    assert r["yeni"]["oran"] == 0.5 and r["backlist"]["oran"] == 0.0
    assert a["sirketCiro"] == 500.0 and not a["kismi"]                       # 157 ticari ürün hariç


# ------------------------------------------------------------------ föy


def _raw(**kw):
    r = {"stok_kodu": "N1", "ad": "Kitap", "yazar": "Yazar", "yayinevi": "Timaş", "kitaplik": "Roman", "dizi": None,
         "hedef_kitle": "Genç", "yas_bas": 12, "yas_bit": 16, "siniflar": None, "ean13": "9786050812345", "isbn13": "978-605-08-1234-5",
         "kdv_dahil_fiyat": 250.0, "perakende_fiyat": None, "uzeri_fiyat": 250.0, "foy_taslak_fiyat": "250 TL", "sayfa": 320,
         "ebat": "13,5x21", "cilt": "Amerikan Cilt", "kapak": None, "ilk_yayin": "2026-11-10",
         "new_TantmFyMetni": "Tek satır tanıtım.", "new_tanitimfoymetni": None, "new_kitapspotu": None,
         "new_ozet": "Arka kapak.", "new_kitabinonecikanyanlari": "- Güçlü karakterler\n- Okul listelerine uygun",
         "new_editorunkitabaveyazaradairgorusleri": None}
    r.update(kw)
    return r


def _valid_ean(prefix12: str) -> str:
    s = sum(int(x) * (3 if i % 2 else 1) for i, x in enumerate(prefix12))
    return prefix12 + str((10 - s % 10) % 10)


def test_foy_fields_come_from_crm_with_their_source():
    ean = _valid_ean("978605081234")
    f = F.from_crm(_raw(ean13=ean, isbn13=ean), "2026-11-10", "crm-kitap")
    assert f["fiyat"] == {"deger": 250.0, "kaynak": "crm:new_kdvdahilfiyat"}
    assert f["barkod"]["deger"] == ean and f["hedefKitle"]["deger"] == "Genç · 12–16 yaş"
    assert f["argumanlar"]["deger"] == ["Güçlü karakterler", "Okul listelerine uygun"]
    assert f["tanitim"]["kaynak"] == "crm:new_TantmFyMetni"
    assert F.missing(f, F.DEFAULT_REQUIRED.split(",")) == []
    assert F.missing(F.from_crm(_raw(new_kitabinonecikanyanlari=None, kdv_dahil_fiyat=None, uzeri_fiyat=None), None, None),
                     F.DEFAULT_REQUIRED.split(",")) == ["fiyat", "argumanlar"]


def test_foy_mismatches():
    ean = _valid_ean("978605081234")
    ok = _raw(ean13=ean, isbn13=ean)
    f = F.from_crm(ok, None, None)
    assert F.blocking(F.mismatches(f, ok, {"fiyat": 250.0}, 0.01)) == []
    bad = _raw(ean13=ean, isbn13=_valid_ean("978605081299"), foy_taslak_fiyat="240,00")
    kinds = {m["tur"] for m in F.mismatches(F.from_crm(bad, None, None), bad, {"fiyat": 260.0}, 0.01)}
    assert kinds == {"fiyat-logo", "fiyat-taslak", "barkod-isbn"}
    broken = _raw(ean13="9786050812340", isbn13=None)
    assert "barkod-gecersiz" in {m["tur"] for m in F.mismatches(F.from_crm(broken, None, None), broken, None, 0.01)}
    info = F.mismatches(f, ok, None, 0.01, "Logo kapalı")
    assert F.blocking(info) == [] and info[0]["tur"] == "logo-okunamadi"


def test_foy_refresh_keeps_manual_fields_and_marks_approved_as_stale(engine):
    fs = _fst()
    ean = _valid_ean("978605081234")
    raw = _raw(ean13=ean, isbn13=ean)
    assert F.upsert_from_crm(engine, T, "N1", "2026-11", raw, "2026-11-10", "crm-kitap", None, None, fs) == "acildi"
    F.update(engine, T, "ayse", "N1", "2026-11", {"alanlar": {"tanitim": "Elle yazılan tanıtım"}}, fs, raw)
    assert F.upsert_from_crm(engine, T, "N1", "2026-11", _raw(ean13=ean, isbn13=ean, new_ozet="Yeni arka kapak"),
                             "2026-11-10", "crm-kitap", None, None, fs) == "tazelendi"
    got = {a["key"]: a for a in F.get(engine, T, "N1", fs["required"], "2026-11")["alanlar"]}
    assert got["tanitim"]["deger"] == "Elle yazılan tanıtım" and got["tanitim"]["kaynak"] == "elle"
    assert got["ozet"]["deger"] == "Yeni arka kapak"
    with pytest.raises(C.MarketingError):
        F.decide(engine, T, "ayse", "N1", "2026-11", True, {}, fs)          # son düzelten onaylayamaz
    out = F.decide(engine, T, "satis", "N1", "2026-11", True, {}, fs)
    assert out["durum"] == "onayli"
    changed = _raw(ean13=ean, isbn13=ean, kdv_dahil_fiyat=275.0, uzeri_fiyat=275.0, foy_taslak_fiyat=None)
    assert F.upsert_from_crm(engine, T, "N1", "2026-11", changed, "2026-11-10", "crm-kitap", None, None, fs) == "eski"
    assert F.get(engine, T, "N1", fs["required"], "2026-11")["eski"]
    assert F.upsert_from_crm(engine, T, "N1", "2026-11", changed, "2026-11-10", "crm-kitap", None, None, fs, force=True) == "yenilendi"
    again = F.get(engine, T, "N1", fs["required"], "2026-11")
    assert again["durum"] == "taslak" and again["surum"] == 2 and not again["eski"]


def test_foy_approval_needs_complete_fields_and_reasoned_acceptance_of_mismatch(engine):
    fs = _fst()
    ean = _valid_ean("978605081234")
    F.upsert_from_crm(engine, T, "N1", "2026-11", _raw(ean13=ean, isbn13=ean, new_kitabinonecikanyanlari=None),
                      "2026-11-10", "crm-kitap", None, None, fs)
    with pytest.raises(C.MarketingError) as e:
        F.decide(engine, T, "satis", "N1", "2026-11", True, {}, fs)
    assert "Neden satılır" in str(e.value)
    F.set_args(engine, T, "N1", "2026-11", ["Birinci", "İkinci", "Üçüncü"], fs, {"kim": "ayse"})
    F.upsert_from_crm(engine, T, "N2", "2026-11", _raw(stok_kodu="N2", ean13=ean, isbn13=ean), "2026-11-10", "crm-kitap",
                      {"fiyat": 300.0, "kaynak": "Logo"}, None, fs)
    with pytest.raises(C.MarketingError):
        F.decide(engine, T, "satis", "N2", "2026-11", True, {}, fs)
    ok = F.decide(engine, T, "satis", "N2", "2026-11", True, {"kabul": True, "not": "Logo fiyatı Aralık'ta güncellenecek"}, fs)
    assert ok["durum"] == "onayli" and ok["onayNotu"]
    assert F.decide(engine, T, "satis", "N1", "2026-11", True, {}, fs)["durum"] == "onayli"
    todo = F.crm_todo(F.get(engine, T, "N1", fs["required"], "2026-11"))
    assert [t["alan"] for t in todo] == ["new_kitabinonecikanyanlari"]


def test_ean13_drawing_and_pdf_has_one_page_per_foy(engine):
    ean = _valid_ean("978605081234")
    assert F.ean13_ok(ean) and not F.ean13_ok(ean[:-1] + str((int(ean[-1]) + 1) % 10))
    from semantic_bridge.marketing import foy_pdf as FP

    mods = FP.ean13_modules(ean)
    assert mods and len(mods) == 95 and mods.startswith("101") and mods.endswith("101")
    pytest.importorskip("fpdf")
    fs = _fst()
    for code in ("N1", "N2", "N3"):
        F.upsert_from_crm(engine, T, code, "2026-11", _raw(stok_kodu=code, ean13=ean, isbn13=ean, new_ozet="uzun " * 3000),
                          "2026-11-10", "crm-kitap", None, None, fs)
    items = F.list_month(engine, T, "2026-11", fs["required"])
    import re

    body = FP.foy_pdf(items, "Kasım 2026", {})
    assert len(re.findall(rb"/Type\s*/Page(?!s)", body)) == 3              # uzun metin sayfayı taşırmaz


# ------------------------------------------------------------------ yetki


def test_access_rules_for_monthly_plan_and_foy():
    month, foy = A.page("pazarlama-aylik"), A.page("pazarlama-foy")
    assert A.rule_for("/api/v1/marketing/months/2026-11") == frozenset({month})
    assert A.rule_for("/api/v1/marketing/months/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/marketing/foy") == frozenset({foy, month})
    assert A.rule_for("/api/v1/marketing/foy/N1.pdf") == frozenset({foy, month})
    assert foy in A.rule_for("/api/v1/marketing/meta")
    assert month in A.rule_for("/api/v1/budget/targets") and month in A.rule_for("/api/v1/budget/deviations")
    assert A.rule_for("/api/v1/marketing/contract/plans") == frozenset({A.page("pazarlama-yeni-kitap")})
    f = A.features_for
    w = "ozellik:pazarlama.plan-yaz"
    assert f("POST", "/api/v1/marketing/months/2026-11/build") == [w]
    assert f("PATCH", "/api/v1/marketing/months/2026-11/items/abc") == [w]
    assert f("POST", "/api/v1/marketing/months/2026-11/approve") == []
    assert f("GET", "/api/v1/marketing/months/2026-11/summary.pdf") == ["ozellik:veri.disa-aktar"]
    assert f("PUT", "/api/v1/marketing/foy/N1") == ["ozellik:pazarlama.foy-yaz"]
    assert f("POST", "/api/v1/marketing/foy/N1/draft-args") == ["ozellik:pazarlama.foy-yaz"]
    assert f("POST", "/api/v1/marketing/foy/N1/approve") == [] and f("POST", "/api/v1/marketing/foy/paket/2026-11/send") == []
    assert f("GET", "/api/v1/marketing/foy/N1.pdf") == [] and f("GET", "/api/v1/marketing/foy/paket/2026-11.pdf") == []
    ex = A.explicit_keys()
    assert {"ozellik:pazarlama.foy-onay", "ozellik:pazarlama.foy-gonder"} <= ex and "ozellik:pazarlama.foy-yaz" not in ex
    assert {month, foy} <= A.all_keys()


# ------------------------------------------------------------------ uçlar


def test_endpoints_build_view_foy_and_explicit_approval(monkeypatch, store, settings):
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
    A._ready.clear()
    A.invalidate()
    for s in (C._ready, B._ready, M._ready, F._ready):
        s.discard(id(store.engine))
    _targets(monkeypatch, [])
    app = create_app(Runtime(settings, store=store, llm=FakeLlm([""])))
    client = TestClient(app)
    ay = (date.today().replace(day=1) + timedelta(days=40)).strftime("%Y-%m")
    pub = f"{ay}-10"
    ean = _valid_ean("978605081234")
    fake = FakeCrm(books=[_book("N9", pub)], raw={"N9": _raw(stok_kodu="N9", ean13=ean, isbn13=ean)})
    crm = app.state.marketing["crm"]
    for name in ("new_books", "campaigns", "all_special_days", "spend", "region_targets", "foy_books", "book", "email_of"):
        monkeypatch.setattr(crm, name, getattr(fake, name))
    a, z = {"cookie": "timas_session=a"}, {"cookie": "timas_session=z"}

    assert client.get(f"/api/v1/marketing/months/{ay}", headers=a).json()["plan"] is None
    built = client.post(f"/api/v1/marketing/months/{ay}/build", headers=a)
    assert built.status_code == 200, built.text
    v = built.json()
    assert v["plan"]["kind"] == "aylik" and v["plan"]["donem"] == ay and [x["stokKodu"] for x in v["items"]] == ["N9"]
    assert client.get("/api/v1/marketing/months/2026-13", headers=a).status_code == 400
    meta = client.get("/api/v1/marketing/meta", headers=a).json()
    assert meta["monthly"]["draftDay"] == 15 and meta["me"]["canFoyWrite"] and not meta["me"]["canFoyApprove"]

    lst = client.get(f"/api/v1/marketing/foy?donem={ay}", headers=a)
    assert lst.status_code == 200, lst.text
    assert lst.json()["kpi"]["toplam"] == 1
    denied = client.post(f"/api/v1/marketing/foy/N9/approve?donem={ay}", json={}, headers=a)
    assert denied.status_code == 403                                       # açıkça verilen yetki yok
    ok = client.post(f"/api/v1/marketing/foy/N9/approve?donem={ay}", json={"kabul": True, "not": "Logo fiyatı okunamadı"}, headers=z)
    assert ok.status_code == 200, ok.text
    assert ok.json()["durum"] == "onayli"
    assert client.post(f"/api/v1/marketing/foy/paket/{ay}/send", headers=a).status_code == 403
    assert client.post("/api/v1/marketing/months/run-due", headers=a).status_code == 403
    assert client.get(f"/api/v1/marketing/contract/month/{ay}", headers=a).json()["plan"] is None   # onaylı ay planı yok


# ------------------------------------------------------------------ hız: föy ekranı eşitleme kaydından okur


def _foy_app(monkeypatch, store, settings, fake):
    """Föy uçları için köprü: CRM sahte, Logo bağlantısı tanımsız (fiyat okunamadı notu). CRM ve Logo çağrıları sayılır.
    Dönen `calls` her CRM/Logo okumasının adını toplar; `fake`in yöntemleri çağrı anında aranır (testte değiştirilebilir)."""
    from fastapi.testclient import TestClient

    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    users = {"timas_session=a": "ayse"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: [])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    monkeypatch.delenv("SEMANTIC_ADMIN_TOKEN", raising=False)
    A._ready.clear()
    A.invalidate()
    for s in (C._ready, B._ready, M._ready, F._ready):
        s.discard(id(store.engine))
    _targets(monkeypatch, [])
    app = create_app(Runtime(settings, store=store, llm=FakeLlm([""])))
    calls: list[str] = []
    crm = app.state.marketing["crm"]

    def counted(name):
        def fn(*a, **kw):
            calls.append(name)
            return getattr(fake, name)(*a, **kw)
        return fn
    for name in ("new_books", "campaigns", "all_special_days", "spend", "region_targets", "foy_books", "book", "email_of"):
        monkeypatch.setattr(crm, name, counted(name))
    orig = F.LogoPrices.read

    def logo_read(self, *a, **kw):
        calls.append("logo")
        return orig(self, *a, **kw)
    monkeypatch.setattr(F.LogoPrices, "read", logo_read)
    return TestClient(app), calls


def _no_prov(j: dict) -> dict:
    return {k: v for k, v in j.items() if k != "kaynaklar"}


def _prov_ok(j: dict) -> dict:
    from semantic_bridge import provenance as PV
    from semantic_bridge.marketing import kaynak_aylik as KA

    k = j.get("kaynaklar")
    assert k and not k.get("error"), k
    assert PV.uncovered_numbers(j, KA.NOT_RAKAM) == []
    assert PV.problems(j) == []
    return k


def test_foy_screen_reads_sync_record_without_crm_or_logo(monkeypatch, store, settings):
    """Eski hesap = yeni hesap: ilk açılış (eşitleme) ile sonraki okuma (yalnız föy tablosu + eşitleme kaydı) aynı cevabı
    verir; sonraki okumada CRM'e ve Logo'ya hiç gidilmez. «CRM'den yenile» (yenile=true) yine CRM ve Logo'yu okur."""
    ay = (date.today().replace(day=1) + timedelta(days=40)).strftime("%Y-%m")
    ean = _valid_ean("978605081234")
    fake = FakeCrm(books=[_book("N9", f"{ay}-10", sorumlu="Ayşe Yılmaz"), _book("N8", f"{ay}-12")],
                   raw={"N9": _raw(stok_kodu="N9", ean13=ean, isbn13=ean)})       # N8'in föy kartı yok → not
    client, calls = _foy_app(monkeypatch, store, settings, fake)
    h = {"cookie": "timas_session=a", "x-data-refresh": "1"}

    first = client.get(f"/api/v1/marketing/foy?donem={ay}", headers=h)
    assert first.status_code == 200, first.text
    j1 = first.json()
    assert {"new_books", "foy_books", "logo"} <= set(calls)                  # dönem hiç eşitlenmemişti: eşitlendi
    assert j1["kpi"]["toplam"] == 1 and j1["crmOkuma"]
    assert j1["items"][0]["kitap"] == {"yazar": "Yazar", "yayinevi": "Timaş", "kitaplik": "Roman", "yayinTarihi": f"{ay}-10",
                                       "sorumlu": "Ayşe Yılmaz"}
    assert j1["notlar"] == ["N8: CRM kitap kartı etkin değil; föy açılmadı."]
    assert j1["logoNotu"]                                                    # bağlantı tanımsız: eski davranış
    snap = F.read_sync(store.engine, settings.tenant_id, ay)
    assert snap and sorted(snap["kitap"]) == ["N8", "N9"] and snap["kitap"]["N9"]["tarihKaynagi"] == "crm-kitap"
    assert snap["logo"] == []                                                # okunamadı: gösterilecek çalışmış Logo SQL'i yok

    calls.clear()
    second = client.get(f"/api/v1/marketing/foy?donem={ay}", headers=h)
    assert second.status_code == 200, second.text
    j2 = second.json()
    assert calls == []                                                       # istek anında CRM/Logo yok
    assert _no_prov(j2) == _no_prov(j1)
    k = _prov_ok(j2)
    assert "foy.esitleme" in k["sources"] and "foy.esitleme" in k["sources"]["foy.liste"]["origin"]
    assert "foy-sync:" + ay in k["sources"]["foy.esitleme"]["sql"]
    assert "foy.crm.yeni" in k["sources"] and "foy.crm.alan.1" in k["sources"]
    for durum in ("taslak", "eksik", "uyumsuz", "eski", "onayli"):
        assert client.get(f"/api/v1/marketing/foy?donem={ay}&durum={durum}", headers=h).status_code == 200
    assert calls == []

    # Tek föy: eşitleme kaydında kitap var → CRM'e gidilmez; cevap eski okumayla (CRM'den) aynı.
    fast = client.get(f"/api/v1/marketing/foy/N9?donem={ay}", headers=h)
    assert fast.status_code == 200, fast.text
    assert calls == []
    jf = fast.json()
    assert jf["kitap"] == {"yayinKaynagi": "crm-kitap", "sorumlu": "Ayşe Yılmaz"}
    kf = _prov_ok(jf)
    assert "foy.esitleme" in kf["sources"]["foy.kayit"]["origin"]
    nodonem = client.get("/api/v1/marketing/foy/N9", headers=h)              # dönemsiz: föyün (ay dışı olmayan) ayı
    assert nodonem.status_code == 200 and nodonem.json()["donem"] == ay and calls == []
    with store.engine.begin() as c:                                          # kayıt yoksa eski yol: CRM okunur
        c.execute(C.META.delete().where(C.META.c.key == F.sync_key(ay)))
    old = client.get(f"/api/v1/marketing/foy/N9?donem={ay}", headers=h)
    assert old.status_code == 200, old.text
    assert {"foy_books", "book"} <= set(calls)
    assert _no_prov(old.json()) == _no_prov(jf)
    _prov_ok(old.json())

    # «CRM'den yenile»: CRM ve Logo yeniden okunur, kayıt yeniden yazılır.
    calls.clear()
    again = client.get(f"/api/v1/marketing/foy?donem={ay}&yenile=true", headers=h)
    assert again.status_code == 200, again.text
    assert {"new_books", "foy_books", "logo"} <= set(calls)
    assert F.read_sync(store.engine, settings.tenant_id, ay)
    assert again.json()["kpi"] == j1["kpi"]


def test_foy_list_keeps_last_sync_when_crm_fails(monkeypatch, store, settings):
    """«CRM'den yenile»de CRM okunamazsa eski davranış: not düşer, föyler son okunan hâlleriyle; kitap künyesi son
    eşitleme kaydından gelir."""
    from semantic_bridge.marketing.sources import SourceError

    ay = (date.today().replace(day=1) + timedelta(days=40)).strftime("%Y-%m")
    ean = _valid_ean("978605081234")
    fake = FakeCrm(books=[_book("N9", f"{ay}-10")], raw={"N9": _raw(stok_kodu="N9", ean13=ean, isbn13=ean)})
    client, calls = _foy_app(monkeypatch, store, settings, fake)
    h = {"cookie": "timas_session=a", "x-data-refresh": "1"}
    assert client.get(f"/api/v1/marketing/foy?donem={ay}", headers=h).json()["kpi"]["toplam"] == 1

    def down(*a, **kw):
        raise SourceError("CRM bağlantısı yok")
    monkeypatch.setattr(fake, "new_books", down)
    r = client.get(f"/api/v1/marketing/foy?donem={ay}&yenile=true", headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["notlar"] == ["CRM okunamadı; föyler son okunan hâlleriyle: CRM bağlantısı yok"] and j["logoNotu"] is None
    assert j["kpi"]["toplam"] == 1 and j["items"][0]["kitap"]["yazar"] == "Yazar"
    _prov_ok(j)


def test_logo_runs_from_sync_record_are_the_foy_origin(engine):
    """Logo fiyatı okunduysa çalışmış SQL eşitleme kaydına yazılır ve föy sayfasının kökeninde aynen görünür (süreç yeniden
    başlasa da: kayıttan okunur)."""
    from semantic_bridge import provenance as PV
    from semantic_bridge.marketing import kaynak_aylik as KA

    this_year = date.today().year
    views = [{"name": f"V_SatisRaporu_{y}"} for y in range(2020, this_year + 2)]

    def runner():
        def run(sql):
            if "sys.views" in sql:
                return views
            return [{"stok_kodu": "N1", "birim_fiyat": 240.0, "son_fiyat_degisikligi": None}]
        return run

    logo = F.LogoPrices(runner)
    prices, note = logo.read(["N1"], "satis")
    runs = logo.runs_for(["N1"])
    fst = _fst()
    F.upsert_from_crm(engine, T, "N1", "2026-11", _raw(), "2026-11-10", "crm-kitap", prices.get("N1"), note, fst)
    F.save_sync(engine, T, "2026-11", [{**_book("N1", "2026-11-10"), "yayinTarihi": "2026-11-10", "yayinKaynagi": "crm-kitap"}],
                [], note, runs, _st()["dateOrder"])
    snap = F.read_sync(engine, T, "2026-11")
    assert [r["sql"] for r in snap["logo"]] == [r["sql"] for r in runs]
    out = F.get(engine, T, "N1", fst["required"], "2026-11")
    out["crmTodo"], out["logo"], out["kitap"] = [], next((x for x in out["uyumsuzluk"] if x["tur"] == "fiyat-logo"), None), {}
    out = PV.ekle(out, KA.for_foy(engine, T, "Timas_MSCRM.dbo", out, F.LogoPrices(runner), "TIGERDB", sync=snap))
    k = out["kaynaklar"]
    assert PV.problems(out) == [] and PV.uncovered_numbers(out, KA.NOT_RAKAM) == []
    shown = [s for sid, s in k["sources"].items() if sid.startswith("foy.logo.fiyat.")]
    assert len(shown) == len(runs) == 2
    assert [s["stats"]["rows"] for s in shown] == [r["rows"] for r in runs]
    assert all("SatisRaporu" in s["sql"] for s in shown)
    assert "foy.esitleme" in k["sources"]["foy.kayit"]["origin"]
