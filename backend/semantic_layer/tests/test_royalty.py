"""M54 Telif dönemi ve haklar: kapsam SQL'i, istisnalar, M6 motoruyla hesap, iki gözlü onay, beyanname, ödeme listesi,
avans açılışı, yenileme ve hak kartı.

Bu testler SQLite ve yapay satırla kural denetimidir; ürün doğruluğunun kanıtı DEĞİLDİR. Gerçek CRM/Logo kabulü
`scripts/acceptance/m54/` altındadır ve test sunucusunda koşar.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from semantic_bridge import access as A
from semantic_bridge import contracts as C
from semantic_bridge import contracts_royalty as CR
from semantic_bridge import contracts_terms as T
from semantic_bridge import royalty as RY
from semantic_bridge import royalty_sources as S
from semantic_layer.store.catalog_store import open_store

TEN = "t1"
A_, B_ = "2026-01-01", "2026-06-30"
G1 = "11111111-1111-1111-1111-111111111111"
G2 = "22222222-2222-2222-2222-222222222222"
G3 = "33333333-3333-3333-3333-333333333333"
P1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
P2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    C._ready.discard(id(e))
    RY._ready.discard(id(e))
    RY.ensure(e)
    yield e
    C._ready.discard(id(e))
    RY._ready.discard(id(e))


def _terms(**kw):
    base = {
        "title": "Deneme", "kind": "telif-alis",
        "parties": [{"name": "Ayşe Yazar", "role": "yazar", "share": 100, "contactId": P1}],
        "books": [{"title": "Deneme", "stockCode": "K1", "format": "karton"}], "paymentType": "satis", "basis": "net",
        "rates": {"karton": 10}, "currency": "TRY", "start": "2025-01-01", "end": "2030-12-31", "periodMonths": 6,
        "paymentDays": 30,
    }
    base.update(kw)
    return T.clean(base)


def _item(key=G1, **kw):
    return {"key": key, "crmId": key, "recordId": None, "recordStatus": None, "no": f"S-{key[:4]}", "terms": _terms(**kw),
            "crm": {"no": f"S-{key[:4]}", "status": "yururlukte", "terms": _terms(**kw)}, "emails": {P1: "ayse@ornek.com"}}


def _rows(code="K1", qty=100, net=1000.0, ret_qty=0, ret_net=0.0, month=3):
    out = [{"kod": code, "yil": 2026, "ay": month, "tur": "Satış", "miktar": qty, "net": net, "kapak": 20}]
    if ret_qty:
        out.append({"kod": code, "yil": 2026, "ay": month, "tur": "İade", "miktar": -ret_qty, "net": -ret_net, "kapak": 20})
    return out


def _eval(item, rows=None, **kw):
    args = dict(a=A_, b=B_, rows_by_code=S.group_by_code(rows if rows is not None else _rows()), prior_by_code={},
                first_year=2021, data_end="2026-08-17", fx={}, statements=[], opening=None, duplicates=set(),
                withholding_default=None, months=6)
    args.update(kw)
    return RY.evaluate(item, **args)


# ---------------------------------------------------------------- kapsam SQL'i


def test_heads_sql_keeps_m6_columns_and_replaces_only_where():
    p = "Timas_MSCRM.dbo."
    m6 = C.crm_contract_sql(p, G1)[0]
    ours = S.heads_sql(p, (100000000, 100000007), (2, 7))
    assert ours.split(" FROM ")[0] == m6.split(" FROM ")[0]  # kolon listesi birebir
    assert "s.new_TelifTipi IN (2, 7)" in ours and "s.statuscode IN (100000000, 100000007)" in ours
    assert "new_SozlesmeTipi = 5" in ours and G1 not in ours


def test_scope_count_and_parts_use_same_where():
    p = "X.dbo."
    w = S.scope_where((100000000,), (2,))
    for sql in (S.books_sql(p, (100000000,), (2,)), S.parties_sql(p, (100000000,), (2,)), S.scope_count_sql(p, (100000000,), (2,))):
        assert w in sql
    assert "vergi" not in S.parties_sql(p, (1,), (2,)).lower()  # T.C./vergi no okunmaz


def test_codes_of_parses_or_defaults():
    assert S.codes_of("100000000, 100000007", (1,)) == (100000000, 100000007)
    assert S.codes_of("", (2, 7)) == (2, 7)


def test_scope_contracts_groups_rows_through_m6_mapping():
    heads = [{"new_sozlesmeId": G1.upper(), "new_name": "2026-1", "tip_kod": 5, "odeme_kod": 2, "esas_kod": 2, "para_kod": 1,
              "durum_kod": 100000000, "new_Telif": 12, "new_SozlesmeBaslangicTarihi": "2025-01-01", "suresiz": 0,
              "new_yazar_text": "Ayşe Yazar"}]
    books = [{"sid": "{" + G1 + "}", "new_kitapId": G2, "new_name": "Kitap", "new_StokKodu": "K1", "new_EKitapStokKodu": "E1"}]
    parties = [{"sid": G1, "new_kisi": P1, "kisi": "Ayşe Yazar", "new_Odeme": 100, "kisi_eposta": "ayse@ornek.com"}]
    out = S.scope_contracts(heads, books, parties)
    assert len(out) == 1 and out[0]["crmId"] == G1
    t = out[0]["terms"]
    assert [b["stockCode"] for b in t["books"]] == ["K1", "E1"] and t["rates"]["karton"] == 12
    assert out[0]["emails"] == {P1: "ayse@ornek.com"}


def test_renewal_and_rights_sql():
    p = "X.dbo."
    s = S.renewals_sql(p, date(2026, 9, 28), date(2026, 12, 27))
    assert "new_SozlesmeBitisTarihi >= '2026-09-28'" in s and "< '2026-12-27'" in s and "suresiz" in s
    assert "new_SozlesmeBitisTarihi >=" not in S.renewals_sql(p, None, date(2026, 9, 28))
    assert G1 in S.renewals_sql(p, None, None, contract_id=G1)
    with pytest.raises(S.SourceError):
        S.book_contracts_sql(p, "1; DROP TABLE x")
    assert "new_iletimhakki" in S.rights_bit_count_sql(p)


# ---------------------------------------------------------------- dönem


def test_default_period_is_last_completed_half():
    assert RY.default_period(date(2026, 9, 28), 6) == ("2026-01-01", "2026-06-30")
    assert RY.default_period(date(2026, 1, 5), 6) == ("2025-07-01", "2025-12-31")
    assert RY.default_period(date(2026, 3, 1), 1) == ("2026-02-01", "2026-02-28")


# ---------------------------------------------------------------- değerlendirme


def test_evaluate_equals_m6_engine():
    ev = _eval(_item(), _rows(qty=100, net=1000.0, ret_qty=10, ret_net=100.0))
    direct = CR.compute(_terms(), period_start=A_, period_end=B_, sales=CR.fold_sales(_rows(qty=100, net=1000.0, ret_qty=10, ret_net=100.0)),
                        data_end="2026-08-17")
    assert ev["exceptions"] == [] and ev["auto"] is None
    assert ev["calc"]["gross"] == direct["gross"] == 90.0 and ev["calc"]["net"] == direct["net"]
    assert ev["parties"][0]["email"] == "ayse@ornek.com"


def test_missing_stock_code_is_hard_exception():
    ev = _eval(_item(books=[{"title": "Kodsuz", "format": "karton"}]))
    codes = {e["code"]: e for e in ev["exceptions"]}
    assert "stok-kodu-yok" in codes and not codes["stok-kodu-yok"]["acceptable"]
    assert RY.line_status(ev["exceptions"], {}, None)[0] == "istisna"


def test_unknown_advance_is_exception_not_zero():
    ev = _eval(_item(advance=5000))
    assert any(e["code"] == "avans-acilis-yok" for e in ev["exceptions"])
    # sözleşme bu dönem başlıyorsa avans tamamen kazanılmamıştır; açılış gerekmez
    ev2 = _eval(_item(advance=5000, start="2026-01-01"))
    assert not any(e["code"] == "avans-acilis-yok" for e in ev2["exceptions"])
    assert ev2["calc"]["advanceOffset"] == ev2["calc"]["gross"]


def test_opening_balance_drives_offset():
    ev = _eval(_item(advance=5000), _rows(qty=1000, net=10000.0),
               opening={"amount": 60.0, "currency": "TRY", "asOf": "2025-12-31", "by": "u"})
    assert not ev["exceptions"]
    assert ev["calc"]["gross"] == 1000.0 and ev["calc"]["advanceOffset"] == 60.0 and ev["calc"]["net"] == 940.0
    assert ev["calc"]["advanceBasis"]["opening"] == 60.0
    bad = _eval(_item(advance=5000), opening={"amount": 60.0, "currency": "USD", "asOf": "2025-12-31"})
    assert any(e["code"] == "avans-para-birimi" for e in bad["exceptions"])


def test_opening_plus_portal_statements_match_m6_context():
    # açılıştan önce onaylanmış hakediş (mahsup 100) + açılış kalan 50 → etkin avans 150, M6'nın gördüğü kullanılan 100
    st = [{"periodStart": "2025-01-01", "periodEnd": "2025-06-30", "advanceOffset": 100.0, "carryOut": 0.0}]
    ev = _eval(_item(advance=5000), _rows(qty=1000, net=10000.0), statements=st,
               opening={"amount": 50.0, "currency": "TRY", "asOf": "2025-12-31"})
    assert ev["calc"]["advanceUsedBefore"] == 100.0 and ev["calc"]["advanceOffset"] == 50.0


def test_overlapping_approved_statement_blocks():
    st = [{"periodStart": "2026-01-01", "periodEnd": "2026-06-30", "advanceOffset": 0, "carryOut": 0}]
    ev = _eval(_item(), statements=st)
    assert any(e["code"] == "onayli-hakedis-var" for e in ev["exceptions"])


def test_acceptable_exceptions_and_acceptance():
    ev = _eval(_item(parties=[{"name": "A", "share": 60, "contactId": P1}, {"name": "B", "share": 30, "contactId": P2}]))
    assert [e["code"] for e in ev["exceptions"]] == ["pay-toplami"]
    assert RY.line_status(ev["exceptions"], {"kabul": {"codes": ["pay-toplami"]}}, None) == ("hesaplandi", None)


def test_contract_start_clips_sales_and_auto_exclusions():
    rows = _rows(qty=50, net=500.0, month=2) + _rows(qty=100, net=1000.0, month=5)
    ev = _eval(_item(start="2026-04-10"), rows)
    assert ev["calc"]["quantity"] == 100  # Şubat satışı sözleşmeden önce
    assert _eval(_item(start="2026-08-01"))["auto"] == "baslamamis"
    assert _eval(_item(end="2025-06-30"), [])["auto"] == "bitmis-satissiz"
    sold = _eval(_item(end="2025-06-30"))
    assert sold["auto"] is None and any(e["code"] == "sure-bitti-satis-var" for e in sold["exceptions"])
    assert RY.line_status([], {}, "baslamamis")[0] == "haric"
    assert RY.line_status([], {"autoUndone": {"by": "u"}}, "baslamamis")[0] == "hesaplandi"


def test_foreign_currency_needs_rate():
    ev = _eval(_item(currency="USD"))
    assert any(e["code"] == "kur-yok" for e in ev["exceptions"])
    ok = _eval(_item(currency="USD"), fx={"USD": {"rate": 40.0, "on": B_, "source": "test"}})
    assert not ok["exceptions"] and ok["calc"]["currency"] == "USD" and ok["calc"]["gross"] == 2.5


def test_tiered_prior_before_sales_views_is_flagged():
    it = _item(paymentType="satis-kademeli", tiers=[{"from": 0, "rate": 10}, {"from": 1000, "rate": 12}], start="2018-01-01")
    ev = _eval(it, first_year=2021)
    assert any(e["code"] == "kademe-gecmis-eksik" and e["acceptable"] for e in ev["exceptions"])


def test_duplicate_book_and_party_across_contracts():
    a, b, c = _item(G1), _item(G2), _item(G3, books=[{"title": "Başka", "stockCode": "K9"}])
    dups = RY.duplicate_keys([a, b, c])
    assert dups == {G1, G2}


def test_withholding_default_only_for_persons():
    ev = _eval(_item(), withholding_default=17.0)
    assert ev["calc"]["withholdingPct"] == 17.0 and ev["calc"]["withholding"] == round(ev["calc"]["gross"] * 0.17, 2)
    firm = _eval(_item(parties=[{"name": "Ajans", "share": 100, "accountId": P2}]), withholding_default=17.0)
    assert not firm["calc"]["withholdingPct"]


# ---------------------------------------------------------------- koşu, onay, beyanname


class FakeSrc(RY.Sources):
    def __init__(self, items, rows):
        self.items, self.rows = items, rows

    def scope(self):
        return [{"crmId": it["key"], "no": it["no"], "crmStatus": 100000000, "status": "yururlukte", "terms": it["terms"],
                 "emails": it["emails"]} for it in self.items]

    def present_years(self):
        return {2021, 2022, 2023, 2024, 2025, 2026}

    def sales(self, codes, a, b, present):
        return [r for r in self.rows if r["kod"] in codes and CR.ym(a) <= S.month_of(r) <= CR.ym(b)], []

    def data_end(self, present, year):
        return "2026-08-17"

    def fx(self, currency, on):
        return None


def _run(engine, items, rows, user="hazirlayan"):
    run = RY.create_run(engine, TEN, "acan", {"periodStart": A_, "periodEnd": B_})
    RY.mark_computing(engine, TEN, user, run["id"])
    return RY.compute_run(engine, TEN, run["id"], user, FakeSrc(items, rows), {"statuses": [100000000], "paymentCodes": [2, 7]})


def test_run_covers_whole_scope_and_keeps_decisions(engine):
    items = [_item(G1), _item(G2, books=[{"title": "Kodsuz"}]),
             _item(G3, books=[{"title": "C", "stockCode": "K3"}], start="2020-01-01", end="2024-12-31")]
    run = _run(engine, items, _rows())
    s = run["summary"]
    assert s["lines"] == 3 == s["crmScope"]  # sessizce düşen yok
    assert s["counts"] == {"hesaplandi": 1, "istisna": 1, "haric": 1}
    assert s["reasons"] == {"stok-kodu-yok": 1}
    ex = RY.lines(engine, TEN, run["id"], status="istisna")["items"][0]
    RY.decide_line(engine, TEN, "u", run["id"], ex["id"], {"action": "haric", "reason": "kitap satışta değil"})
    with pytest.raises(RY.RoyaltyError):
        RY.decide_line(engine, TEN, "u", run["id"], ex["id"], {"action": "haric"})  # gerekçe şart
    RY.mark_computing(engine, TEN, "hazirlayan", run["id"])
    again = RY.compute_run(engine, TEN, run["id"], "hazirlayan", FakeSrc(items, _rows()), {})
    assert again["summary"]["counts"] == {"hesaplandi": 1, "istisna": 0, "haric": 2}


def test_hard_exception_cannot_be_accepted_and_blocks_submit(engine):
    run = _run(engine, [_item(G1), _item(G2, books=[{"title": "Kodsuz"}])], _rows())
    ex = RY.lines(engine, TEN, run["id"], status="istisna")["items"][0]
    with pytest.raises(RY.RoyaltyError, match="kabul edilemeyen"):
        RY.decide_line(engine, TEN, "u", run["id"], ex["id"], {"action": "kabul", "reason": "x"})
    with pytest.raises(RY.RoyaltyError, match="istisna"):
        RY.submit(engine, TEN, "gonderen", run["id"], {})


def test_two_eyes_and_approval_creates_m6_statements(engine):
    items = [_item(G1), _item(G2, parties=[{"name": "Ali", "share": 50, "contactId": P2},
                                           {"name": "Ayşe Yazar", "share": 50, "contactId": P1}],
                               books=[{"title": "İki", "stockCode": "K2"}])]
    rows = _rows("K1", 100, 1000.0) + _rows("K2", 200, 3000.0)
    run = _run(engine, items, rows)
    run = RY.submit(engine, TEN, "gonderen", run["id"], {"acceptDataEnd": True, "note": "veri 17 Ağustos'a kadar"})
    for who in ("hazirlayan", "gonderen"):
        with pytest.raises(RY.RoyaltyError, match="iki göz"):
            RY.mark_approving(engine, TEN, who, run["id"])
    RY.mark_approving(engine, TEN, "onaylayan", run["id"])
    done = RY.approve_run(engine, TEN, run["id"], "onaylayan")
    assert done["status"] == "onayli"
    with engine.connect() as c:
        sts = c.execute(C.sa.select(C.STATEMENTS).where(C.STATEMENTS.c.status == "onaylandi")).all()
        pays = c.execute(C.sa.select(C.PAYMENTS).where(C.PAYMENTS.c.kind == "hakedis")).all()
    assert len(sts) == 2 == len(pays)
    assert {s.created_by for s in sts} == {"hazirlayan"} and {s.approved_by for s in sts} == {"onaylayan"}
    net_total = sum(float(s.net) for s in sts)
    assert net_total == done["summary"]["totals"]["TRY"]["net"]
    # hak sahibi toplamı = satırların pay oranıyla toplamı
    ps = RY.parties(engine, TEN, run["id"], show_email=False)
    assert ps["all"] == 2
    assert round(sum(p["totals"]["TRY"]["net"] for p in ps["items"]), 2) == round(net_total, 2)
    ayse = next(p for p in ps["items"] if p["name"] == "Ayşe Yazar")
    assert ayse["email"] == "a***@ornek.com" and ayse["contracts"] == 2
    data, name, digest = RY.party_document(engine, TEN, run["id"], ayse["key"])
    assert zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml") and name.endswith(".docx") and len(digest) == 64
    z, _ = RY.statements_zip(engine, TEN, run["id"])
    assert len(zipfile.ZipFile(io.BytesIO(z)).namelist()) == 2
    csv_bytes, _ = RY.payments_csv(engine, TEN, run["id"])
    text = csv_bytes.decode("utf-8-sig")
    assert text.count("\n") == 1 + 3  # başlık + (Ayşe K1, Ali K2, Ayşe K2)
    RY.mark_sent(engine, TEN, "u", run["id"], {"keys": [ayse["key"]], "channel": "eposta"})
    assert RY.parties(engine, TEN, run["id"], status="gonderildi")["total"] == 1
    # onaylı koşu iptal edilmez; aynı dönem ikinci kez açılmaz
    with pytest.raises(RY.RoyaltyError):
        RY.cancel(engine, TEN, "u", run["id"], {"note": "x"})
    with pytest.raises(RY.RoyaltyError):
        RY.create_run(engine, TEN, "u", {"periodStart": A_, "periodEnd": B_})
    assert RY.contract_lines(engine, TEN, G1)[0]["statementId"]


def test_contract_changed_after_compute_fails_that_line(engine):
    run = _run(engine, [_item(G1)], _rows())
    rec = C.adopt_crm(engine, TEN, "u", G1, {"no": "S-1", "status": "yururlukte", "terms": _terms(rates={"karton": 15})})
    assert rec
    RY.submit(engine, TEN, "gonderen", run["id"], {"acceptDataEnd": True, "note": "x"})
    RY.mark_approving(engine, TEN, "onaylayan", run["id"])
    out = RY.approve_run(engine, TEN, run["id"], "onaylayan")
    assert out["status"] == "onayda" and "oluşturulamadı" in out["error"]
    ln = RY.lines(engine, TEN, run["id"])["items"][0]
    assert "değişti" in ln["approvalError"]
    RY.decide_line(engine, TEN, "u", run["id"], ln["id"], {"action": "haric", "reason": "sonraki koşuda"})


def test_create_run_validates_period(engine):
    with pytest.raises(RY.RoyaltyError):
        RY.create_run(engine, TEN, "u", {"periodStart": "2026-01-02", "periodEnd": "2026-06-30"})
    with pytest.raises(RY.RoyaltyError):
        RY.create_run(engine, TEN, "u", {"periodStart": "2030-01-01", "periodEnd": "2030-06-30"})


def test_recover_stuck_run(engine):
    run = RY.create_run(engine, TEN, "u", {"periodStart": A_, "periodEnd": B_})
    RY.mark_computing(engine, TEN, "u", run["id"])
    assert RY.get_run(engine, TEN, run["id"])["status"] == "hesaplaniyor"  # taze iş dokunulmaz
    RY.recover_stuck(engine, older_than=RY.timedelta(seconds=-1))
    r = RY.get_run(engine, TEN, run["id"])
    assert r["status"] == "taslak" and "yarıda" in r["error"]


# ---------------------------------------------------------------- avans, yenileme, haklar


def test_advance_opening_requires_reason_and_keeps_history(engine):
    with pytest.raises(RY.RoyaltyError):
        RY.set_advance(engine, TEN, "u", G1, {"amount": 100, "asOf": "2025-12-31"})
    RY.set_advance(engine, TEN, "u", G1, {"amount": 100, "asOf": "2025-12-31", "reason": "2025 mutabakat dosyası"})
    out = RY.set_advance(engine, TEN, "v", G1, {"amount": 80, "asOf": "2025-12-31", "reason": "düzeltme"})
    assert [h["active"] for h in out["history"]] == [True, False]
    with engine.connect() as c:
        assert RY.openings(c, TEN)[G1]["amount"] == 80


def test_renewal_rows_and_stale_decision(engine):
    rows = [{"id": G1, "no": "S-1", "tip_kod": 5, "bit": "2026-11-30", "yenileme_yil": 5, "kitap": "Kitap"}]
    RY.decide_renewal(engine, TEN, "yy", G1, {"decision": "yenile", "reason": "satış güçlü", "end": "2026-11-30"})
    out = RY.renewal_rows(rows, RY.renewal_decisions(engine, TEN), date(2026, 9, 28))
    assert out[0]["decision"] == "yenile" and out[0]["daysLeft"] == 63
    rows[0]["bit"] = "2031-11-30"  # CRM'de uzatılmış: eski karar geçmişte kalır
    out = RY.renewal_rows(rows, RY.renewal_decisions(engine, TEN), date(2026, 9, 28))
    assert out[0]["decision"] == "bekliyor" and out[0]["staleDecision"]
    with pytest.raises(RY.RoyaltyError):
        RY.decide_renewal(engine, TEN, "yy", G1, {"decision": "birak"})


def test_rights_summary_follows_seo_rule():
    base = {"kind": "alis", "status": 100000000, "ends": "2030-01-01", "open_ended": 0, "no": "S-1",
            "rights": {k: True for k in S.RIGHT_LABELS}}
    lic = [{"status": "imzalandi", "language": "Arapça", "country": "Mısır", "buyer": "Dar", "end": None}]
    s = {x["key"]: x["state"] for x in RY.rights_summary([base], date(2026, 9, 28), lic)}
    assert s["iletim"] == "var" and s["lisans"] == "var"
    miss = dict(base, rights={**base["rights"], "ceviri": False}, no="S-2")
    s = {x["key"]: x["state"] for x in RY.rights_summary([base, miss], date(2026, 9, 28), [])}
    assert s["ceviri"] == "yok" and s["lisans"] == "yok"
    assert {x["state"] for x in RY.rights_summary([], date(2026, 9, 28), [])} >= {"sozlesme-yok"}


def test_grants_licenses_and_notes(engine):
    g = RY.save_grant(engine, TEN, "u", {"bookId": G1, "kind": "ceviri", "language": "Almanca", "country": "Almanya"})
    assert RY.grants(engine, TEN, G1)[0]["id"] == g["id"]
    with pytest.raises(RY.RoyaltyError):
        RY.save_grant(engine, TEN, "u", {"bookId": G1, "kind": "yok"})
    x = RY.save_license(engine, TEN, "u", {"book": "Kitap", "bookId": G1, "buyer": "Verlag", "language": "Almanca",
                                           "status": "imzalandi", "collected": 1000, "authorSharePct": 50, "currency": "EUR"})
    assert x["authorShare"] == 500.0
    items = RY.pending_notes(engine, TEN, [{"id": G1, "no": "S-1", "metin": "Yalnız Türkiye'de satılabilir"}])
    RY.save_note(engine, TEN, items[0], {"class": "bolge", "probability": 0.95, "margin": 0.9, "method": "logprobs"}, (0.7, 0.3))
    assert RY.pending_notes(engine, TEN, [{"id": G1, "metin": "Yalnız Türkiye'de satılabilir"}]) == []
    n = RY.notes(engine, TEN)["items"][0]
    assert n["status"] == "oneri"
    RY.save_note(engine, TEN, dict(items[0], key=G2), {"class": "diger", "probability": 0.5, "margin": 0.1}, (0.7, 0.3))
    assert RY.notes(engine, TEN, status="incele")["total"] == 1
    assert RY.approve_note(engine, TEN, "u", n["id"], {})["status"] == "onayli"


# ---------------------------------------------------------------- yetki


def test_access_rules_and_catalog():
    assert A.rule_for("/api/v1/royalty/runs") == frozenset({A.page("telif-donem")})
    assert A.rule_for("/api/v1/royalty/run-due") == A.SYSTEM
    assert A.page("telif-sozlesme") in A.rule_for("/api/v1/royalty/contracts/abc/lines")
    assert A.rule_for("/api/v1/rights/books/x") == frozenset({A.page("haklar")})
    assert "ozellik:telif.kosu" in A.features_for("POST", "/api/v1/royalty/runs/abc/compute")
    assert "ozellik:telif.kosu" not in A.features_for("POST", "/api/v1/royalty/runs/abc/approve")
    assert "ozellik:veri.disa-aktar" in A.features_for("GET", "/api/v1/royalty/runs/abc/payments.csv")
    assert "ozellik:haklar.lisans" in A.features_for("PATCH", "/api/v1/rights/licenses-out/3")
    assert A.explicit_keys() >= {"ozellik:telif.kosu-onay", "ozellik:telif.bildirim", "ozellik:telif.odeme-listesi",
                                 "ozellik:telif.avans"}
    pages = {p["key"]: p for p in A.catalog()["pages"]}
    assert pages["sayfa:telif-donem"].get("explicit") is True and "sayfa:haklar" in pages


def test_mask_and_fold():
    assert RY.mask_email("ayse@ornek.com") == "a***@ornek.com" and RY.mask_email("") is None
    assert RY.fold("İSTANBUL Çağ") == "istanbul cag"
