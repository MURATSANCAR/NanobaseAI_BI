"""M6 Sözleşmeler: şart doğrulama, fark, zeyilname, ödeme takvimi, hakediş hesabı, şablon ve Word belgesi."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from semantic_bridge import contracts as C
from semantic_bridge import contracts_docs as D
from semantic_bridge import contracts_royalty as R
from semantic_bridge import contracts_terms as T
from semantic_layer.store.catalog_store import open_store

TEN = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    C._ready.discard(id(e))
    C.ensure(e)
    return e


def _terms(**kw):
    base = {
        "title": "Deneme — Yazar", "kind": "telif-alis", "parties": [{"name": "Ayşe Yazar", "role": "yazar", "share": 100}],
        "books": [{"title": "Deneme", "stockCode": "K1", "format": "karton"}], "paymentType": "satis", "basis": "net",
        "rates": {"karton": 10}, "currency": "TRY", "advance": 1000, "start": "2026-01-01", "end": "2030-12-31",
        "periodMonths": 6, "paymentDays": 30,
    }
    base.update(kw)
    return T.clean(base)


# ---------------------------------------------------------------- şartlar


def test_clean_validates_and_patches():
    t = _terms()
    assert t["rates"] == {"karton": 10.0}
    t2 = T.clean({"rates": {"ekitap": "25,5"}, "end": "2031-06-30"}, t)
    assert t2["rates"] == {"karton": 10.0, "ekitap": 25.5}
    assert t2["end"] == "2031-06-30" and t["end"] == "2030-12-31"  # taban değişmez
    with pytest.raises(T.ContractError):
        T.clean({"rates": {"karton": 150}})
    with pytest.raises(T.ContractError):
        T.clean({"start": "2026-02-30"})
    with pytest.raises(T.ContractError):
        T.clean({"start": "2026-05-01", "end": "2026-01-01"})
    with pytest.raises(T.ContractError):
        T.clean({"tiers": [{"from": 100, "rate": 5}]})  # ilk kademe 0'dan başlamalı
    with pytest.raises(T.ContractError):
        T.clean({"bilinmeyen": 1})
    assert T.clean({"openEnded": True, "end": "2030-01-01"})["end"] is None


def test_diff_and_patch_round_trip():
    a = _terms()
    b = T.clean({"rates": {"karton": 12}, "rights": {"iletim": True}, "end": None, "openEnded": True}, a)
    changes = T.diff(a, b)
    fields = {c["field"] for c in changes}
    assert fields == {"rates.karton", "rights.iletim", "end", "openEnded"}
    assert T.clean(T.patch_of(changes), a) == b


def test_warnings_flag_missing_inputs():
    t = T.clean({"title": "x", "paymentType": "satis", "parties": [{"name": "A", "share": 60}, {"name": "B", "share": 30}]})
    w = " ".join(T.warnings(t))
    assert "%90" in w and "oranı" in w and "stok kodu" in w


def test_words_and_money_words():
    assert T.words(12500) == "onikibinbeşyüz"
    assert T.words(1000) == "bin"
    assert T.words(1_001_001) == "birmilyonbinbir"
    assert T.money_words(250.5, "TRY") == "ikiyüzelli Türk lirası elli kuruş"


# ---------------------------------------------------------------- hakediş


def test_month_bounds():
    R.month_bounds("2026-01-01", "2026-06-30")
    with pytest.raises(T.ContractError):
        R.month_bounds("2026-01-02", "2026-06-30")
    with pytest.raises(T.ContractError):
        R.month_bounds("2026-01-01", "2026-06-29")


def test_fold_sales_subtracts_returns_and_prices_each_month():
    rows = [{"kod": "K1", "yil": 2026, "ay": 1, "tur": "Satış", "miktar": 100, "net": 5000, "kapak": 90},
            {"kod": "K1", "yil": 2026, "ay": 1, "tur": "İade", "miktar": -10, "net": -500, "kapak": 90},
            {"kod": "K1", "yil": 2026, "ay": 2, "tur": "Satış", "miktar": 10, "net": 700, "kapak": 120},
            {"kod": "K1", "yil": 2026, "ay": 2, "tur": "İade", "miktar": 5, "net": 250, "kapak": -120}]
    s = R.fold_sales(rows)["K1"]
    assert s["qty"] == 95 and s["net"] == 4950 and s["retQty"] == 15
    assert s["list"] == 90 * 90 + 5 * 120  # her ay kendi kapak fiyatıyla


def test_net_royalty_with_advance_and_withholding():
    t = _terms(withholdingPct=17)
    sales = {"K1": {"qty": 85, "net": 4250, "list": 6800, "retQty": 15}}
    r = R.compute(t, period_start="2026-01-01", period_end="2026-06-30", sales=sales)
    assert r["gross"] == 425.0            # 4250 × %10
    assert r["advanceOffset"] == 425.0    # avans 1000, hepsi mahsup
    assert r["net"] == 0.0 and r["advanceRemaining"] == 575.0
    r2 = R.compute(t, period_start="2026-07-01", period_end="2026-12-31", sales={"K1": {"qty": 200, "net": 10000, "list": 0, "retQty": 0}},
                   advance_used=425.0)
    assert r2["advanceOffset"] == 575.0
    assert r2["withholding"] == round(425.0 * 0.17, 2)
    assert r2["net"] == round(425.0 - 425.0 * 0.17, 2)


def test_gross_basis_uses_list_price_and_discount():
    t = _terms(basis="brut", discountPct=10, advance=None, books=[{"title": "B", "stockCode": "K1", "listPrice": 999}])
    sales = {"K1": {"qty": 100, "net": 1, "list": 6000, "retQty": 0}}
    r = R.compute(t, period_start="2026-01-01", period_end="2026-01-31", sales=sales, list_prices={"K1": 50})
    assert r["base"] == 4500.0 and r["gross"] == 450.0          # elle girilen fiyat önce gelir
    r = R.compute(t, period_start="2026-01-01", period_end="2026-01-31", sales=sales)
    assert r["base"] == 5400.0 and not r["warnings"]             # Logo'daki aylık kapak fiyatı, CRM fiyatı değil
    r = R.compute(t, period_start="2026-01-01", period_end="2026-01-31", sales={"K1": {"qty": 10, "net": 1, "list": 0, "retQty": 0}})
    assert r["base"] == 8991.0 and "CRM" in r["warnings"][0]     # Logo fiyatı yoksa CRM'deki


def test_tiers_split_across_boundary():
    t = _terms(paymentType="satis-kademeli", tiers=[{"from": 0, "rate": 8}, {"from": 1000, "rate": 12}], advance=None)
    r = R.compute(t, period_start="2026-01-01", period_end="2026-06-30",
                  sales={"K1": {"qty": 400, "net": 4000, "list": 0, "retQty": 0}}, prior_qty={"K1": 800})
    # 200 adet %8, 200 adet %12; birim matrah 10
    assert r["gross"] == 200 * 10 * 0.08 + 200 * 10 * 0.12
    assert r["lines"][0]["tiers"] == [{"quantity": 200, "rate": 8}, {"quantity": 200, "rate": 12}]


def test_parties_split_and_equal_split_warning():
    t = _terms(parties=[{"name": "A", "share": 70}, {"name": "B", "share": 30}], advance=None)
    r = R.compute(t, period_start="2026-01-01", period_end="2026-01-31", sales={"K1": {"qty": 10, "net": 1000, "list": 0, "retQty": 0}})
    assert [ln["royalty"] for ln in r["lines"]] == [70.0, 30.0]
    t2 = _terms(parties=[{"name": "A"}, {"name": "B"}], advance=None)
    r2 = R.compute(t2, period_start="2026-01-01", period_end="2026-01-31", sales={"K1": {"qty": 10, "net": 1000, "list": 0, "retQty": 0}})
    assert any("eşit" in w for w in r2["warnings"])
    t3 = _terms(parties=[{"name": "A", "share": 0}, {"name": "B", "share": 0}], advance=None)
    r3 = R.compute(t3, period_start="2026-01-01", period_end="2026-01-31", sales={"K1": {"qty": 10, "net": 1000, "list": 0, "retQty": 0}})
    assert r3["gross"] == 100.0 and [ln["royalty"] for ln in r3["lines"]] == [50.0, 50.0]


def test_negative_period_carries_forward():
    t = _terms(advance=None)
    r = R.compute(t, period_start="2026-01-01", period_end="2026-01-31", sales={"K1": {"qty": -20, "net": -2000, "list": 0, "retQty": 20}})
    assert r["net"] == 0.0 and r["carryOut"] == -200.0
    r2 = R.compute(t, period_start="2026-02-01", period_end="2026-02-28", sales={"K1": {"qty": 30, "net": 3000, "list": 0, "retQty": 0}},
                   carry_in=-200.0)
    assert r2["net"] == 100.0


def test_foreign_currency_needs_rate():
    t = _terms(currency="USD", advance=100)
    s = {"K1": {"qty": 10, "net": 4000, "list": 0, "retQty": 0}}
    no_fx = R.compute(t, period_start="2026-01-01", period_end="2026-01-31", sales=s)
    assert no_fx["currency"] == "TRY" and no_fx["advanceOffset"] == 0
    fx = R.compute(t, period_start="2026-01-01", period_end="2026-01-31", sales=s, fx={"rate": 40.0, "on": "2026-01-31"})
    assert fx["currency"] == "USD" and fx["gross"] == 10.0 and fx["advanceOffset"] == 10.0


def test_tcmb_rate_walks_back_over_weekend():
    from datetime import date
    xml = ('<Tarih_Date><Currency CrossOrder="0" Kod="USD" CurrencyCode="USD"><Unit>1</Unit>'
           '<ForexBuying>46.5747</ForexBuying></Currency><Currency Kod="JPY" CurrencyCode="JPY"><Unit>100</Unit>'
           '<ForexBuying>30.00</ForexBuying></Currency></Tarih_Date>')
    seen = []

    def fetch(url):
        seen.append(url)
        return (200, xml) if url.endswith("26062026.xml") else (404, "")

    r = R.tcmb_rate("USD", date(2026, 6, 28), fetch)   # pazar → cuma
    assert r == {"rate": 46.5747, "on": "2026-06-26", "source": "TCMB döviz alış"}
    assert seen[0].endswith("/202606/28062026.xml")
    assert R.tcmb_rate("JPY", date(2026, 6, 26), fetch)["rate"] == 0.3
    assert R.tcmb_rate("CNY", date(2026, 6, 26), fetch) is None
    assert R.tcmb_rate("USD", date(2026, 7, 20), lambda u: (404, "")) is None


def test_print_based_needs_price_and_quantity():
    t = _terms(paymentType="baski", advance=None)
    with pytest.raises(T.ContractError):
        R.compute(t, period_start="2026-01-01", period_end="2026-01-31", sales={}, prints={"K1": 3000})
    r = R.compute(t, period_start="2026-01-01", period_end="2026-01-31", sales={}, prints={"K1": 3000}, list_prices={"K1": 100})
    assert r["gross"] == 30000.0


def test_flat_fee_contract_has_no_statement():
    with pytest.raises(T.ContractError):
        R.compute(_terms(paymentType="tek"), period_start="2026-01-01", period_end="2026-01-31", sales={})


def test_sales_sql_uses_year_views_and_month_window():
    from datetime import date
    sql = R.sales_sql(["K1", "O'K"], date(2025, 11, 1), date(2026, 4, 30))
    assert "{satis:2025-2026}" in sql and "BETWEEN 24311 AND 24316" in sql and "N'O''K'" in sql


# ---------------------------------------------------------------- kayıt, zeyilname, ödeme, hakediş


def test_draft_lifecycle_and_addendum(engine):
    rec = C.create_draft(engine, TEN, "ayse", {"terms": {"title": "Kitap — Yazar", "parties": [{"name": "Y", "share": 100}], "start": "2026-01-01", "end": "2027-12-31"}})
    assert rec["no"].startswith("TS-") and rec["status"] == "taslak"
    rec = C.update_terms(engine, TEN, "ayse", rec["id"], {"terms": {"rates": {"karton": 9}}, "version": rec["version"]})
    with pytest.raises(C.Conflict):
        C.update_terms(engine, TEN, "mehmet", rec["id"], {"terms": {"rates": {"karton": 8}}, "version": 1})
    with pytest.raises(T.ContractError):
        C.create_addendum(engine, TEN, "ayse", rec["id"], {"title": "x", "changes": {"end": "2028-12-31"}})  # taslağa zeyilname yok
    rec = C.set_status(engine, TEN, "ayse", rec["id"], {"status": "yururlukte", "signedOn": "2026-01-05"})
    assert rec["signedAt"] == "2026-01-05"
    with pytest.raises(T.ContractError):
        C.update_terms(engine, TEN, "ayse", rec["id"], {"terms": {"rates": {"karton": 11}}})  # gerekçesiz değişmez
    fixed = C.update_terms(engine, TEN, "ayse", rec["id"], {"terms": {"rates": {"karton": 11}}, "reason": "Kayıt hatası"})
    assert fixed["terms"]["rates"]["karton"] == 11
    a = C.create_addendum(engine, TEN, "ayse", rec["id"], {"title": "Süre uzatımı", "effectiveOn": "2026-10-01", "changes": {"end": "2029-12-31"}})
    assert a["no"].endswith("/Z-1") and a["changes"][0]["old"] == "2027-12-31"
    with pytest.raises(T.ContractError):
        C.create_addendum(engine, TEN, "ayse", rec["id"], {"title": "Aynı", "changes": {"rates.karton": 11}})  # değişiklik yok
    signed = C.set_addendum_status(engine, TEN, "ayse", a["id"], {"status": "imzalandi", "signedOn": "2026-09-27"})
    assert signed["status"] == "imzalandi"
    assert C.find(engine, TEN, rec["id"])["terms"]["end"] == "2029-12-31"
    with pytest.raises(T.ContractError):
        C.set_addendum_status(engine, TEN, "ayse", a["id"], {"status": "iptal"})
    actions = [e["action"] for e in C.events(engine, TEN, rec["id"])]
    assert {"olustur", "duzenle", "durum", "duzeltme", "zeyilname"} <= set(actions)


def test_expired_contract_reopens_with_extension(engine):
    rec = C.create_draft(engine, TEN, "a", {"terms": {"title": "Eski", "parties": [{"name": "Y"}], "start": "2020-01-01", "end": "2024-12-31"}})
    C.set_status(engine, TEN, "a", rec["id"], {"status": "yururlukte"})
    C.set_status(engine, TEN, "a", rec["id"], {"status": "sona-erdi"})
    a = C.create_addendum(engine, TEN, "a", rec["id"], {"title": "Uzatma", "changes": {"end": "2099-12-31"}})
    C.set_addendum_status(engine, TEN, "a", a["id"], {"status": "imzalandi"})
    assert C.find(engine, TEN, rec["id"])["status"] == "yururlukte"


def test_payments_plan_paid_and_cancel(engine):
    rec = C.create_draft(engine, TEN, "a", {"terms": {"title": "P", "parties": [{"name": "Y"}], "advance": 5000, "start": "2026-01-01"}})
    out = C.plan_payments(engine, TEN, "a", rec["id"])
    assert out["added"] and not C.plan_payments(engine, TEN, "a", rec["id"])["added"]  # ikinci kez eklemez
    p = C.payments(engine, TEN, rec["id"])[0]
    assert p["kind"] == "avans" and p["amount"] == 5000
    with pytest.raises(T.ContractError):
        C.add_payment(engine, TEN, "a", rec["id"], {"kind": "hakedis", "amount": 1})
    paid = C.mark_paid(engine, TEN, "a", p["id"], {"paidOn": "2026-01-10", "paidRef": "DK-1"})
    assert paid["status"] == "odendi" and paid["paidAmount"] == 5000
    with pytest.raises(T.ContractError):
        C.cancel_payment(engine, TEN, "a", p["id"], {})  # ödenmiş kayıt gerekçesiz iptal edilmez
    assert C.cancel_payment(engine, TEN, "a", p["id"], {"note": "Hatalı giriş"})["status"] == "iptal"
    due = C.due_list(engine, TEN, status="")
    assert due["items"][0]["contractNo"] == rec["no"]


# ---------------------------------------------------------------- satır tavanı yok (no-silent-limits)


def _bulk_records(engine, n):
    """Doğrudan tabloya n sözleşme; en eskisi (updated_at en küçük) «Kayıp Kitap» adını taşır."""
    base = datetime(2020, 1, 1, tzinfo=timezone.utc)
    rows = [{"id": f"{i:032x}", "tenant_id": TEN, "crm_id": None, "no": f"TS-2020-{i:05d}", "status": "taslak",
             "terms": _terms(title="Kayıp Kitap" if i == 0 else f"Sözleşme {i}"), "version": 1, "body_edited": False,
             "created_by": "a", "created_at": base, "updated_by": "a", "updated_at": base + timedelta(minutes=i)}
            for i in range(n)]
    with engine.begin() as c:
        c.execute(C.RECORDS.insert(), rows)
    return rows


def test_list_records_returns_every_row_and_searches_the_oldest(engine):
    rows = _bulk_records(engine, 1201)  # eski tavan 1000'di
    now = datetime.now(timezone.utc)
    with engine.begin() as c:  # en eski sözleşmeye bir bekleyen ödeme: özet alt sorguyla hesaplanmalı
        c.execute(C.PAYMENTS.insert().values(id="p" * 32, tenant_id=TEN, contract_id=rows[0]["id"], kind="avans",
                                             due_on="2099-01-01", amount=10, currency="TRY", status="planlandi",
                                             created_by="a", created_at=now, updated_by="a", updated_at=now))
    out = C.list_records(engine, TEN)
    assert len(out) == 1201
    assert out[-1]["no"] == "TS-2020-00000"  # yeniden eskiye; en eski de listede
    assert out[-1]["payments"] == {"planned": 1, "overdue": 0, "next": "2099-01-01"}
    hit = C.list_records(engine, TEN, q="kayıp kitap")
    assert [r["no"] for r in hit] == ["TS-2020-00000"]


def test_events_returns_full_history(engine):
    rec = C.create_draft(engine, TEN, "a", {"terms": {"title": "Uzun geçmiş", "parties": [{"name": "Y"}]}})
    t0 = datetime(2021, 1, 1, tzinfo=timezone.utc)
    with engine.begin() as c:  # eski tavan 500'dü
        c.execute(C.EVENTS.insert(), [{"tenant_id": TEN, "contract_id": rec["id"], "at": t0 + timedelta(minutes=i),
                                       "actor": "a", "action": "duzenle", "summary": f"Değişiklik {i}"} for i in range(700)])
    ev = C.events(engine, TEN, rec["id"])
    assert len(ev) == 701  # 700 + taslağın açılış kaydı
    assert ev[-1]["summary"] == "Değişiklik 0"  # en eski değişiklik kesilmedi


def test_due_list_returns_every_payment_and_totals_match(engine):
    rows = _bulk_records(engine, 1)
    now = datetime.now(timezone.utc)
    n = 2301  # eski tavan 2000'di
    with engine.begin() as c:
        c.execute(C.PAYMENTS.insert(), [{"id": f"{i:032x}", "tenant_id": TEN, "contract_id": rows[0]["id"], "kind": "hakedis",
                                         "due_on": f"{2000 + i // 365:04d}-01-01", "amount": 1, "currency": "TRY",
                                         "status": "planlandi", "created_by": "a", "created_at": now, "updated_by": "a",
                                         "updated_at": now} for i in range(n)])
    due = C.due_list(engine, TEN)
    assert len(due["items"]) == n
    assert due["totals"]["TRY"]["amount"] == n
    assert due["items"][-1]["dueOn"] == f"{2000 + (n - 1) // 365:04d}-01-01"  # en geç vade de listede


def test_statement_approval_order_and_double_payment_guard(engine):
    rec = C.create_draft(engine, TEN, "a", {"terms": {"title": "S", "parties": [{"name": "Y", "share": 100}],
                                                      "books": [{"title": "B", "stockCode": "K1"}], "rates": {"karton": 10},
                                                      "advance": 100, "start": "2026-01-01", "paymentDays": 15}})
    t = C.find(engine, TEN, rec["id"])["terms"]

    def calc(a, b, net):
        ctx = C.statement_context(engine, TEN, rec["id"], a)
        return R.compute(t, period_start=a, period_end=b, sales={"K1": {"qty": 10, "net": net, "list": 0, "retQty": 0}},
                         advance_used=ctx["advanceUsed"], carry_in=ctx["carryIn"])

    s1 = C.save_statement(engine, TEN, "a", rec["id"], calc("2026-01-01", "2026-06-30", 3000))
    s1 = C.approve_statement(engine, TEN, "a", s1["id"], {})
    assert s1["advanceOffset"] == 100 and s1["net"] == 200 and s1["paymentId"]
    pay = next(p for p in C.payments(engine, TEN, rec["id"]) if p["kind"] == "hakedis")
    assert pay["dueOn"] == "2026-07-15" and pay["amount"] == 200
    with pytest.raises(C.Conflict):
        C.save_statement(engine, TEN, "a", rec["id"], calc("2026-03-01", "2026-08-31", 100))  # çakışan dönem
    s2 = C.save_statement(engine, TEN, "a", rec["id"], calc("2026-07-01", "2026-12-31", 1000))
    assert s2["advanceOffset"] == 0  # avans önceki dönemde bitti
    C.approve_statement(engine, TEN, "a", s2["id"], {})
    with pytest.raises(T.ContractError):
        C.cancel_statement(engine, TEN, "a", s1["id"], {"note": "hata"})  # sonraki onaylı dönem var
    C.mark_paid(engine, TEN, "a", pay["id"], {})
    C.cancel_statement(engine, TEN, "a", s2["id"], {"note": "yeniden hesap"})
    with pytest.raises(T.ContractError):
        C.cancel_statement(engine, TEN, "a", s1["id"], {"note": "hata"})  # ödemesi yapılmış


def test_stale_statement_cannot_be_approved(engine):
    rec = C.create_draft(engine, TEN, "a", {"terms": {"title": "S", "parties": [{"name": "Y"}], "books": [{"title": "B", "stockCode": "K1"}],
                                                      "rates": {"karton": 10}, "advance": 100, "start": "2026-01-01"}})
    t = C.find(engine, TEN, rec["id"])["terms"]
    later = C.save_statement(engine, TEN, "a", rec["id"], R.compute(t, period_start="2026-07-01", period_end="2026-12-31",
                                                                  sales={"K1": {"qty": 1, "net": 500, "list": 0, "retQty": 0}}))
    first = C.save_statement(engine, TEN, "a", rec["id"], R.compute(t, period_start="2026-01-01", period_end="2026-06-30",
                                                                  sales={"K1": {"qty": 1, "net": 500, "list": 0, "retQty": 0}}))
    C.approve_statement(engine, TEN, "a", first["id"], {})
    with pytest.raises(C.Conflict):
        C.approve_statement(engine, TEN, "a", later["id"], {})  # avans kullanımı değişti; yeniden hesap gerekir


def test_adopt_crm_once_and_diff(engine):
    crm = C.crm_contract(
        {"new_name": "S-1", "tip_kod": 5, "odeme_kod": 2, "esas_kod": 2, "para_kod": 1, "durum_kod": 100000000,
         "new_Telif": 8, "new_SozlesmeBaslangicTarihi": "2020-01-01 00:00:00", "new_SozlesmeBitisTarihi": "2025-01-01",
         "new_yazar_text": "Ali Veli", "new_cogaltmahakki": 1, "sirket": "TİMAŞ"},
        [{"new_kitapId": "b1", "new_name": "Kitap", "new_StokKodu": " K9 ", "new_kdvdahilfiyat": 340, "new_EKitapStokKodu": "E9"}],
        [{"kisi": "Ali Veli", "new_Odeme": 100, "new_kisi": "c1"}],
    )
    assert crm["status"] == "yururlukte" and crm["terms"]["parties"][0]["role"] == "yazar"
    assert crm["terms"]["books"][0]["stockCode"] == "K9" and crm["terms"]["rights"]["cogaltma"] is True
    assert crm["terms"]["books"][0]["listPrice"] == 340
    assert crm["terms"]["books"][1] == {"id": "b1", "title": "Kitap (e-kitap)", "stockCode": "E9", "isbn": None,
                                        "format": "ekitap", "listPrice": None}
    assert C.parent_of({"new_anasozlesmeid": "{DA38602B-3052-E811-80F2-00155D000C5B}"}) == "da38602b-3052-e811-80f2-00155d000c5b"
    gid = "11111111-2222-3333-4444-555555555555"
    r1 = C.adopt_crm(engine, TEN, "a", gid, crm)
    r2 = C.adopt_crm(engine, TEN, "b", gid.upper(), crm)
    assert r1["id"] == r2["id"]
    C.update_terms(engine, TEN, "a", gid, {"terms": {"rates": {"karton": 9}}, "reason": "imzalı nüsha"})
    d = C.detail(engine, TEN, gid, lambda _id: crm)
    assert [c["field"] for c in d["diff"]] == ["rates.karton"]
    assert C.crm_state(engine, TEN, [gid])[gid]["diff"] == 1


# ---------------------------------------------------------------- şablon ve belge


def _docx_with_split_placeholder() -> bytes:
    doc = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Sözleşme {{sozle</w:t></w:r><w:r><w:t>sme_no}} &amp; </w:t></w:r><w:r><w:t>{{taraflar}}</w:t></w:r></w:p>'
           '<w:p><w:r><w:t>Dokunulmayan paragraf</w:t></w:r></w:p>'
           '<w:p><w:r><w:t>{{yok_boyle}}</w:t></w:r></w:p></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


def test_docx_fill_joins_split_runs():
    data = _docx_with_split_placeholder()
    assert D.check_docx(data) == ["sozlesme_no", "taraflar", "yok_boyle"]
    out, missing = D.docx_fill(data, {"sozlesme_no": "TS-2026-0001", "taraflar": "A & B"})
    assert missing == ["yok_boyle"]
    text = D.docx_text(out)
    assert "Sözleşme TS-2026-0001 & A & B" in text and "Dokunulmayan paragraf" in text


def test_docx_from_text_is_valid_zip():
    data = D.docx_from_text("# BAŞLIK\n\n## Madde 1\nİlk satır\nikinci satır\n\nSon <paragraf>", "T")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode()
    assert 'w:val="Title"' in xml and "&lt;paragraf&gt;" in xml and "<w:br/>" in xml


def test_templates_seed_version_and_document(engine):
    items = C.templates(engine, TEN)
    assert {t["target"] for t in items} == {"sozlesme", "zeyilname", "hakedis"}
    assert all(not t["unknownFields"] for t in items)  # başlangıç şablonlarında tanınmayan alan yok
    tpl = next(t for t in items if t["target"] == "sozlesme" and t["kind"] == "telif-alis")
    upd = C.save_template(engine, TEN, "hukuk", {"body": tpl["body"] + "\nEk madde {{bolge}}", "version": tpl["version"]}, tpl["id"])
    assert upd["version"] == tpl["version"] + 1
    with pytest.raises(C.Conflict):
        C.save_template(engine, TEN, "hukuk", {"name": "x", "version": tpl["version"]}, tpl["id"])
    rec = C.create_draft(engine, TEN, "a", {"terms": {"title": "Belge", "parties": [{"name": "Ali"}], "advance": 12500,
                                                      "start": "2026-01-01", "territory": "Dünya"}, "templateId": tpl["id"]})
    assert "Ali" in rec["body"] and "onikibinbeşyüz" in rec["body"] and "Dünya" in rec["body"]
    data, name, missing = C.document(engine, TEN, "sozlesme", rec["id"])
    assert name.endswith(".docx") and zipfile.ZipFile(io.BytesIO(data)).testzip() is None and not missing
    C.set_status(engine, TEN, "a", rec["id"], {"status": "yururlukte"})
    with pytest.raises(T.ContractError):
        C.set_body(engine, TEN, "a", rec["id"], {"body": "değişti"})  # imzalı metin değişmez
    a = C.create_addendum(engine, TEN, "a", rec["id"], {"title": "Oran", "changes": {"rates.karton": 12}})
    data, _, missing = C.document(engine, TEN, "zeyilname", a["id"])
    assert not missing and "Karton kapak telifi" in D.docx_text(data)


def test_access_catalog_has_explicit_contract_features():
    import json
    from pathlib import Path
    cat = json.loads((Path(C.__file__).parent / "access_catalog.json").read_text())
    feats = {f["key"]: f for f in cat["features"]}
    for k in ("ozellik:sozlesme.duzenle", "ozellik:sozlesme.hakedis", "ozellik:sozlesme.sablon"):
        assert feats[k]["explicit"] is True and feats[k]["page"] == "sayfa:telif-sozlesme"


def test_terms_keep_every_party_book_and_tier():
    t = T.clean({"parties": [{"name": f"Taraf {i}"} for i in range(60)],  # eski tavan 50
                 "books": [{"title": f"Kitap {i}"} for i in range(250)],  # eski tavan 200
                 "tiers": [{"from": i * 100, "rate": 5} for i in range(25)]})  # eski tavan 20
    assert len(t["parties"]) == 60 and t["parties"][-1]["name"] == "Taraf 59"
    assert len(t["books"]) == 250 and t["books"][-1]["title"] == "Kitap 249"
    assert len(t["tiers"]) == 25 and t["tiers"][-1]["from"] == 2400


def test_periods_cover_the_whole_contract():
    from datetime import date

    out = R.periods({"start": "1980-01-01", "periodMonths": 1}, date(2026, 9, 28))  # eski tavan 400 dönem
    assert len(out) == (2026 - 1980) * 12 + 9
    assert out[-1] == (date(2026, 9, 1), date(2026, 9, 30))


def test_crm_related_contracts_are_not_capped():
    sql = C.related_sql("p.", "3f2504e0-4f89-11d3-9a0c-0305e82c3301", None)
    assert "TOP" not in sql.upper().split("FROM")[0]


def test_lookups_page_with_visible_total():
    for build in (C.book_lookup_sql, C.party_lookup_sql):
        first, third = build("p.", "ahmet"), build("p.", "ahmet", 2)
        for sql in (first, third):
            assert "TOP " not in sql.upper() and "COUNT(*) OVER ()" in sql
        assert first.endswith("OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY")
        assert third.endswith("OFFSET 40 ROWS FETCH NEXT 20 ROWS ONLY")
        with pytest.raises(T.ContractError):
            build("p.", "ahmet", "x")
    # kişi ve firma tek listede sayılır: toplam ikisinin birleşimi üzerinden
    assert ") x ORDER BY" in C.party_lookup_sql("p.", "ahmet")
    rows = [{"toplam": 45}] * 20
    assert C.lookup_page(rows, 0) == {"total": 45, "shown": 20, "page": 0}
    assert C.lookup_page([{"toplam": 45}] * 5, 2) == {"total": 45, "shown": 45, "page": 2}
    assert C.lookup_page([], 0) == {"total": 0, "shown": 0, "page": 0}
