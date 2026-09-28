"""Sorgu bilgisi — Kayıtlar › telif (M6 sözleşmeler `/telif-sozlesme*`, M54 telif dönemi `/telif-donem`, haklar `/haklar`).

Her rakam ucu için: cevaptaki her sayı bir kaynağa bağlı (`uncovered_numbers` boş), kayıt tutarlı (`problems` boş), her
SQL dolu ve çalıştırılabilir (yer tutucu yok, şablon yok), bağlantı logo|crm|portal. CRM/Logo okumaları sahte
çalıştırıcıyla beslenir; gösterilen metin çalıştırıcıya giden (çalışan) metindir. Tohumlar mevcut testlerden
(`test_contracts`, `test_royalty`) alınır.
"""
from __future__ import annotations

from datetime import date

from semantic_bridge import contracts as C
from semantic_bridge import contracts_kaynak as CK
from semantic_bridge import contracts_royalty as CR
from semantic_bridge import editorial as E
from semantic_bridge import provenance as P
from semantic_bridge import royalty as RY
from semantic_bridge import royalty_kaynak as K
from semantic_bridge import royalty_sources as S
from semantic_bridge.management import expand_sales
from semantic_bridge.management.kaynak import is_template
from semantic_layer.tests.test_royalty import (A_, B_, G1, G2, P1, P2, TEN, FakeSrc, _item, _rows, _terms,  # noqa: F401
                                              engine)

SCHEMA = "Timas_MSCRM.dbo"
PREFIX = "Timas_MSCRM.dbo."
LOGO_DB, CRM_DB = "TIGERDB", "Timas_MSCRM"


def _check(out, ignore):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, ignore) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [] and not is_template(s["sql"]), s["id"]
        assert s["connection"] in ("logo", "crm", "portal")
    return k


def _logo_sales_sql() -> str:
    sql, _ = expand_sales(CR.sales_sql(["K1"], date(2026, 1, 1), date(2026, 6, 30)), date(2026, 9, 28), {2026})
    return sql


# ---------------------------------------------------------------- M6: CRM portföyü (özet, liste)


def _crm_run(records_by_marker):
    """Köprünün `run_sql` biçiminde sahte çalıştırıcı: metindeki işarete göre satır döndürür."""
    def run(sql):
        for marker, recs in records_by_marker:
            if marker in sql:
                return {"records": recs, "totalRows": len(recs), "dbMs": 7, "computedAt": 1790000000.0, "cached": False,
                        "physicalSql": sql}
        raise AssertionError(f"beklenmeyen sorgu: {sql[:80]}")
    return run


def test_summary_and_page(engine):  # noqa: F811
    run = _crm_run([
        ("AS yururlukte", [{"toplam": 120, "yururlukte": 90, "yenilemede": 4, "yaklasan": 6, "ort_telif": 9.4, "telif_dolu": 70}]),
        ("CAST(s.statuscode AS int)", [{"statuscode": "Aktif - Sözleşme", "kod": 100000000, "n": 80}]),
        ("CAST(s.new_SozlesmeTipi AS int)", [{"new_SozlesmeTipi": "Telif Alış", "kod": 5, "n": 110}]),
    ])
    out = E.summary(SCHEMA, run, 60)
    k = _check(P.ekle(out, CK.for_summary(SCHEMA, out, engine)), CK.NOT_RAKAM)
    sql = k["sources"]["sozlesme.crm.ozet"]["sql"]
    assert sql.startswith("USE [Timas_MSCRM];") and "DATEADD(day, 61" in sql  # uyarı günü değeriyle
    assert k["fields"]["avgRoyalty"] == "hesap:ozet" and k["sources"]["sozlesme.crm.ozet"]["stats"]["dbMs"] == 7

    run = _crm_run([
        ("SELECT COUNT(*) AS n", [{"n": 2}]),
        ("OFFSET", [{"new_sozlesmeId": G1, "new_name": "2026-1", "new_Telif": 10, "new_sozlesmeavanstutari": 5000,
                     "kalan_gun": 40, "new_SozlesmeSuresiYil": 5},
                    {"new_sozlesmeId": G2, "new_name": "2026-2", "new_Telif": 12, "kalan_gun": -3}]),
        ("SELECT sk.new_sozlesmeid", [{"new_sozlesmeid": G1, "new_kitapId": P1, "new_name": "Kitap"}]),
        ("SELECT t.new_sozlesmeid", [{"new_sozlesmeid": G1, "kisi": "Ayşe Yazar", "new_Odeme": 100}]),
    ])
    out = E.page(SCHEMA, run, 0, order="bitis", q="", status=100000000, kind=None, expiring_days=60)
    C.adopt_crm(engine, TEN, "u", G1, {"no": "2026-1", "status": "yururlukte", "terms": _terms()})
    C.update_terms(engine, TEN, "u", G1, {"terms": {"rates": {"karton": 9}}, "reason": "imzalı nüsha"})
    state = C.crm_state(engine, TEN, [G1, G2])
    for c in out["items"]:
        c["portal"] = state.get(c["id"].lower())
    assert out["items"][0]["portal"]["diff"] == 1
    k = _check(P.ekle(out, CK.for_page(engine, TEN, SCHEMA, out, 0, status=100000000, expiring_days=60)), CK.NOT_RAKAM)
    assert "s.statuscode = 100000000" in k["sources"]["sozlesme.crm.sayim"]["sql"]
    assert G1 in k["sources"]["sozlesme.crm.taraflar"]["sql"] and G1 in k["sources"]["sozlesme.portalDurum"]["sql"]
    assert k["fields"]["items[].portal"] == "hesap:portalFark"


# ---------------------------------------------------------------- M6: portal kayıtları, sözleşme sayfası, takvim, şablon


def _crm_contract():
    return C.crm_contract(
        {"new_name": "S-1", "tip_kod": 5, "odeme_kod": 2, "esas_kod": 2, "para_kod": 1, "durum_kod": 100000000,
         "new_Telif": 8, "new_SozlesmeBaslangicTarihi": "2025-01-01", "new_SozlesmeBitisTarihi": "2030-01-01",
         "new_yazar_text": "Ali Veli", "new_sozlesmeavanstutari": 1000, "sirket": "TİMAŞ"},
        [{"new_kitapId": "b1", "new_name": "Kitap", "new_StokKodu": "K1", "new_kdvdahilfiyat": 340}],
        [{"kisi": "Ali Veli", "new_Odeme": 100, "new_kisi": "c1"}])


def _crm_log(gid):
    log = CK.Kayit()
    for sql in C.crm_contract_sql(PREFIX, gid) + [C.related_sql(PREFIX, gid, None)]:
        log.add("crm", sql, rows=1, ms=4, at=1790000000.0)
    return log


def test_records_detail_due_and_templates(engine):  # noqa: F811
    crm = _crm_contract()
    C.adopt_crm(engine, TEN, "u", G1, crm)
    rec = C.find(engine, TEN, G1)
    C.update_terms(engine, TEN, "u", G1, {"terms": {"rates": {"karton": 9}}, "reason": "imzalı nüsha"})
    C.add_payment(engine, TEN, "u", G1, {"kind": "diger", "amount": 250, "dueOn": "2026-01-15"})
    t = C.find(engine, TEN, G1)["terms"]
    logged = CK.Kayit()
    logged.add("logo", _logo_sales_sql(), rows=3, ms=900, at=1790000000.0)
    calc = CR.compute(t, period_start=A_, period_end=B_, sales={"K1": {"qty": 100, "net": 5000, "list": 0, "retQty": 2}})
    calc["sorgular"] = logged.items
    s_new = C.save_statement(engine, TEN, "u", rec["id"], calc)
    s_old = C.save_statement(engine, TEN, "u", rec["id"], CR.compute(t, period_start="2026-07-01", period_end="2026-08-31",
                                                                   sales={"K1": {"qty": 1, "net": 10, "list": 0, "retQty": 0}}))
    C.create_addendum(engine, TEN, "u", G1, {"title": "Süre uzatımı", "changes": {"end": "2031-12-31"}})

    out = {"items": C.list_records(engine, TEN)}
    k = _check(P.ekle(out, CK.for_records(engine, TEN, out)), CK.NOT_RAKAM)
    assert k["fields"]["sayac.kayit"] == "hesap:kayitlar" and out["items"][0]["payments"]["overdue"] == 1

    out = C.detail(engine, TEN, G1, lambda _id: crm)
    out["can"] = {"edit": True, "finance": True, "templates": False}
    k = _check(P.ekle(out, CK.for_detail(engine, TEN, out, _crm_log(G1), PREFIX, LOGO_DB)), CK.NOT_RAKAM)
    assert k["sources"]["sozlesme.crm.sozlesme.1"]["sql"].startswith("USE [Timas_MSCRM];")
    assert k["sources"]["sozlesme.kayit"]["origin"] == [f"sozlesme.crm.sozlesme.{i}" for i in (1, 2, 3, 4)]
    new = k["formulas"][k["fields"][f"statements[]:{s_new['id']}"][6:]]
    logo = [i for i in new["inputs"] if i.startswith("sozlesme.hakedis.")]
    assert logo and k["sources"][logo[0]]["sql"].startswith("USE [TIGERDB];") and "V_SatisRaporu_2026" in k["sources"][logo[0]]["sql"]
    old = k["formulas"][k["fields"][f"statements[]:{s_old['id']}"][6:]]
    assert "saklanmasından önce" in old["text"]  # eski hakedişte uydurma SQL yok, not var
    for f in ("sayac.zeyilname", "sayac.odeme", "sayac.hakedis", "sayac.gecmis", "sayac.bekleyen", "diff", "terms"):
        assert f in k["fields"]

    crm_only = C.detail(engine, TEN, G2, lambda _id: crm)
    assert crm_only["record"] is None
    _check(P.ekle(crm_only, CK.for_detail(engine, TEN, crm_only, _crm_log(G2), PREFIX, LOGO_DB)), CK.NOT_RAKAM)

    out = C.due_list(engine, TEN, status="planlandi", within=90)
    k = _check(P.ekle(out, CK.for_due(engine, TEN, out, status="planlandi", within=90)), CK.NOT_RAKAM)
    assert "'planlandi'" in k["sources"]["sozlesme.takvim"]["sql"]

    out = {"items": C.templates(engine, TEN), "fields": {}, "targets": {}}
    _check(P.ekle(out, CK.for_templates(engine, TEN, out)), CK.NOT_RAKAM)


def test_lookup_and_statement_preview(engine):  # noqa: F811
    log = CK.Kayit()
    run = log.res(_crm_run([("new_kitapBase b", [{"new_kitapId": P1, "new_name": "Kitap", "new_StokKodu": "K1",
                                                   "new_kdvdahilfiyat": 120, "toplam": 45}])]))
    rows = run(C.book_lookup_sql(PREFIX, "kitap", 0))["records"]
    out = {"items": C._crm_books(rows), **C.lookup_page(rows, 0)}
    k = _check(P.ekle(out, CK.for_lookup(log, PREFIX, out)), CK.NOT_RAKAM)
    assert "LIKE N'%kitap%'" in k["sources"]["sozlesme.crm.secici.1"]["sql"]

    rec = C.create_draft(engine, TEN, "a", {"terms": {"title": "S", "parties": [{"name": "Y", "share": 100}],
                                                      "books": [{"title": "B", "stockCode": "K1"}], "rates": {"karton": 10},
                                                      "advance": 100, "start": "2026-01-01"}})
    log = CK.Kayit()
    log.add("logo", "SELECT name FROM sys.views WHERE name LIKE 'V[_]SatisRaporu[_]20[0-9][0-9]'", rows=6, ms=3)
    log.add("logo", _logo_sales_sql(), rows=4, ms=800)
    log.add("logo", CR.data_end_sql(2026), rows=1, ms=5)
    out = CR.compute(rec["terms"], period_start=A_, period_end=B_, sales={"K1": {"qty": 10, "net": 3000, "list": 0, "retQty": 0}},
                     data_end="2026-08-17")
    out["source"] = "Logo satış görünümleri (faturalı satır), stok kodu ile"
    out["sorgular"] = log.items
    k = _check(P.ekle(out, CK.for_calc(engine, TEN, out, rec["id"], {"logo": LOGO_DB, "crm": CRM_DB})), CK.NOT_RAKAM)
    assert {"net", "gross", "lines", "advanceOffset", "sorgular"} <= set(k["fields"])
    assert "sozlesme.kayit" in k["formulas"]["hakedis"]["inputs"]


# ---------------------------------------------------------------- M54: koşu


class LoggedSrc(FakeSrc):
    """Sahte kaynak + gerçek kaydedici: hesapta çalışan metin koşuya yazılır."""

    def __init__(self, items, rows):
        super().__init__(items, rows)
        rec = CK.Kayit()
        self.log = rec.items
        self._crm = rec.rows(lambda sql: [{} for _ in items], "crm")
        self._logo = rec.rows(lambda sql: rows, "logo")

    def scope(self):
        for sql in (S.heads_sql(PREFIX, (100000000,), (2, 7)), S.books_sql(PREFIX, (100000000,), (2, 7)),
                    S.parties_sql(PREFIX, (100000000,), (2, 7))):
            self._crm(sql)
        return super().scope()

    def sales(self, codes, a, b, present):
        self._logo(expand_sales(CR.sales_sql(list(codes), a, b), date(2026, 9, 28), present)[0])
        return super().sales(codes, a, b, present)


def _run(engine, items, rows, user="hazirlayan"):  # noqa: F811
    run = RY.create_run(engine, TEN, "acan", {"periodStart": A_, "periodEnd": B_})
    RY.mark_computing(engine, TEN, user, run["id"])
    return RY.compute_run(engine, TEN, run["id"], user, LoggedSrc(items, rows), {"statuses": [100000000], "paymentCodes": [2, 7]})


def test_run_keeps_executed_sql_out_of_the_screen_payload(engine):  # noqa: F811
    run = _run(engine, [_item(G1)], _rows())
    assert "sorgular" not in run["scope"]  # çalışan metin yalnız sorgu bilgisinde
    q = RY.run_queries(engine, TEN, run["id"])
    assert [x["conn"] for x in q] == ["crm", "crm", "crm", "logo"] and "V_SatisRaporu_2026" in q[3]["sql"]


def test_run_lines_line_and_approval(engine):  # noqa: F811
    items = [_item(G1), _item(G2, parties=[{"name": "Ali", "share": 50, "contactId": P2},
                                           {"name": "Ayşe Yazar", "share": 50, "contactId": P1}],
                               books=[{"title": "İki", "stockCode": "K2"}])]
    run = _run(engine, items, _rows("K1", 100, 1000.0) + _rows("K2", 200, 3000.0))
    rid = run["id"]
    out = {**RY.get_run(engine, TEN, rid), "can": {}}
    k = _check(P.ekle(out, K.for_run(engine, TEN, rid, out, LOGO_DB, CRM_DB)), K.NOT_RAKAM)
    origin = k["sources"]["telif.kosu"]["origin"]
    assert len(origin) == 4 and k["sources"][origin[0]]["sql"].startswith("USE [Timas_MSCRM];")
    assert k["sources"][origin[3]]["sql"].startswith("USE [TIGERDB];") and k["sources"][origin[3]]["connection"] == "logo"
    assert k["fields"]["summary.totals"] == "hesap:toplam" and "avans açılış" in k["formulas"]["toplam"]["text"]

    out = {"items": RY.list_runs(engine, TEN)}
    _check(P.ekle(out, K.for_runs(engine, TEN, out)), K.NOT_RAKAM)
    out = RY.lines(engine, TEN, rid)
    _check(P.ekle(out, K.for_lines(engine, TEN, rid, out, "", LOGO_DB, CRM_DB)), K.NOT_RAKAM)
    ln = RY.line(engine, TEN, rid, out["items"][0]["id"])
    _check(P.ekle(ln, K.for_line(engine, TEN, rid, ln["id"], ln, LOGO_DB, CRM_DB)), K.NOT_RAKAM)

    RY.submit(engine, TEN, "gonderen", rid, {"acceptDataEnd": True, "note": "veri 17 Ağustos'a kadar"})
    RY.mark_approving(engine, TEN, "onaylayan", rid)
    assert RY.approve_run(engine, TEN, rid, "onaylayan")["status"] == "onayli"
    out = RY.parties(engine, TEN, rid)
    _check(P.ekle(out, K.for_parties(engine, TEN, rid, out)), K.NOT_RAKAM)
    r, rows = RY.payment_rows(engine, TEN, rid)
    out = {"items": rows, "totals": {"TRY": {"gross": 1.0, "advance": 0.0, "withholding": 0.0, "net": 1.0, "payees": 1}},
           "run": {"id": r["id"], "no": r["no"], "label": r["label"]}}
    _check(P.ekle(out, K.for_payments(engine, TEN, rid, out)), K.NOT_RAKAM)
    out = {"items": RY.contract_lines(engine, TEN, G1)}
    _check(P.ekle(out, K.for_contract_lines(engine, TEN, G1, out)), K.NOT_RAKAM)

    # Koşudan oluşan M6 hakedişinin «i»si koşunun hesabında çalışan metne bağlanır.
    det = C.detail(engine, TEN, G1, lambda _id: None)
    k = _check(P.ekle(det, CK.for_detail(engine, TEN, det, None, PREFIX, LOGO_DB)), CK.NOT_RAKAM)
    s = det["statements"][0]
    assert s["calc"]["kosu"]["id"] == rid
    ins = k["formulas"][k["fields"][f"statements[]:{s['id']}"][6:]]["inputs"]
    assert any(i.startswith("sozlesme.kosu.") for i in ins)


def test_advances_and_renewals(engine):  # noqa: F811
    RY.set_advance(engine, TEN, "u", G1, {"amount": 60, "asOf": "2025-12-31", "reason": "2025 mutabakat dosyası"})
    _run(engine, [_item(G1, advance=5000)], _rows(qty=1000, net=10000.0))
    out = RY.advances(engine, TEN, risk_years=3.0)
    k = _check(P.ekle(out, K.for_advances(engine, TEN, out, LOGO_DB, CRM_DB)), K.NOT_RAKAM)
    assert any(i.startswith("telif.hesap.") for i in k["sources"]["telif.avansSatirlari"]["origin"])
    out = {"contractKey": G1, "history": RY.advance_history(engine, TEN, G1)}
    _check(P.ekle(out, K.for_advance_history(engine, TEN, G1, out)), K.NOT_RAKAM)

    log = CK.Kayit()
    sql = S.renewals_sql(PREFIX, date(2026, 9, 28), date(2026, 12, 27))
    rows = log.rows(lambda _s: [{"id": G1, "no": "S-1", "tip_kod": 5, "bit": "2026-11-30", "yenileme_yil": 5, "avans": 1000,
                                 "imha_ay": 12, "kitap": "Kitap"}], "crm")(sql)
    facts = CK.Kayit()
    facts.add("crm", S.renewals_sql(PREFIX, None, None, contract_id=G1), rows=1, ms=5)
    facts.add("logo", _logo_sales_sql(), rows=12, ms=700)
    RY.save_renewal_suggestion(engine, TEN, G1, "2026-11-30", {"decision": "yenile", "probability": 0.81, "text": "Satış güçlü.",
                                                              "inputs": {"Son 36 ay net satış adedi": "1.200",
                                                                         "_sorgular": facts.items}})
    items = RY.renewal_rows(rows, RY.renewal_decisions(engine, TEN), date(2026, 9, 28))
    assert "_sorgular" not in items[0]["suggestion"]["inputs"]  # olgu listesi temiz
    out = {"items": items, "total": 1, "counts": {"bekliyor": 1}, "days": 90, "overdue": False, "today": "2026-09-28"}
    k = _check(P.ekle(out, K.for_renewals(engine, TEN, out, log, CRM_DB, LOGO_DB)), K.NOT_RAKAM)
    assert "'2026-09-28'" in k["sources"]["telif.crm.yenileme.1"]["sql"]
    assert f"items[].suggestion:{G1}" in k["fields"]
    sug = {"decision": "yenile", "probability": 0.81, "text": "Satış güçlü.", "inputs": {"Yenileme sıklığı (yıl)": 5}, "dropped": 1}
    _check(P.ekle(sug, K.for_suggest(engine, TEN, sug, facts, LOGO_DB, CRM_DB)), K.NOT_RAKAM)
    meta = {"periodMonths": 6, "withholdingPct": 17.0, "renewalDays": [90, 60, 30], "riskYears": 3.0,
            "scope": {"statuses": [100000000, 100000007], "paymentCodes": [2, 7]}}
    _check(P.ekle(meta, K.for_meta(engine, TEN, meta)), K.NOT_RAKAM)


# ---------------------------------------------------------------- haklar


def test_rights_search_card_licenses_notes(engine):  # noqa: F811
    log = CK.Kayit()
    rows = log.rows(lambda _s: [{"new_kitapId": G1, "new_name": "Kitap", "toplam": 3}], "crm")(C.book_lookup_sql(PREFIX, "kit", 0))
    out = {"items": [{"id": G1, "title": "Kitap", "stockCode": None, "isbn": None}], **C.lookup_page(rows, 0)}
    _check(P.ekle(out, K.for_search(log, CRM_DB, out)), K.NOT_RAKAM)

    RY.save_grant(engine, TEN, "u", {"bookId": G1, "kind": "ceviri", "language": "Almanca"})
    RY.save_license(engine, TEN, "u", {"book": "Kitap", "bookId": G1, "buyer": "Verlag", "status": "imzalandi", "advance": 2000,
                                       "rate": 8, "collected": 1000, "authorSharePct": 50, "currency": "EUR"})
    log = CK.Kayit()
    for sql in (S.book_head_sql(PREFIX, G1), S.book_contracts_sql(PREFIX, G1), S.book_parties_sql(PREFIX, G1),
                S.contract_options_sql(PREFIX)):
        log.add("crm", sql, rows=1, ms=3)
    card = {"book": {"id": G1, "title": "Kitap"}, "summary": [{"key": "iletim", "label": "İletim", "state": "var", "why": "x"}],
            "contracts": [{"id": G2, "no": "S-2", "kind": "alis", "crmStatus": 100000000, "rights": {"iletim": True},
                           "inForce": True, "parties": ["Ayşe Yazar"]}],
            "grants": RY.grants(engine, TEN, G1), "licenses": RY.licenses(engine, TEN, book_id=G1)}
    k = _check(P.ekle(card, K.for_book(engine, TEN, G1, card, log, CRM_DB)), K.NOT_RAKAM)
    assert k["sources"]["haklar.crm.kart.2"]["title"] == "CRM kitaba bağlı sözleşmeler (hak bitleri)"
    assert card["licenses"][0]["authorShare"] == 500.0 and k["fields"]["licenses[]"] == "hesap:lisans"

    items = RY.licenses(engine, TEN)
    out = {"items": items, "total": len(items)}
    _check(P.ekle(out, K.for_licenses(engine, TEN, out)), K.NOT_RAKAM)

    pend = RY.pending_notes(engine, TEN, [{"id": G1, "no": "S-1", "metin": "Yalnız Türkiye'de satılabilir"}])
    RY.save_note(engine, TEN, pend[0], {"class": "bolge", "probability": 0.95, "margin": 0.9, "method": "logprobs"}, (0.7, 0.3))
    out = {**RY.notes(engine, TEN), "job": {"running": False, "done": 1, "total": 1, "failed": 0, "error": None, "at": None}}
    k = _check(P.ekle(out, K.for_notes(engine, TEN, out, prefix=PREFIX, crm_db=CRM_DB)), K.NOT_RAKAM)
    assert "new_haklaraciklama" in k["sources"]["haklar.crm.aciklamalar.1"]["sql"]
    read = CK.Kayit()
    read.add("crm", S.notes_sql(PREFIX), rows=40, ms=90)
    k = _check(P.ekle(out, K.for_notes(engine, TEN, out, prefix=PREFIX, crm_db=CRM_DB, last_read=read.items[0])), K.NOT_RAKAM)
    assert k["sources"]["haklar.crm.aciklamalar.1"]["stats"]["rows"] == 40
