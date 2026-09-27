"""M12 Üretim yönetimi: geriye doğru takvim, ölçülen süreler, gerçekleşen tarihin kaynağı, gecikme ve basamaklı
bildirim, matbaa istatistiği ve puanı, portal kayıtları, CRM/Logo birleştirmesi (üretim emri, giriş fişi, baskı
faturası) ve SQL biçimi.

Sözleşme: portal kaydı CRM/Logo tarihini ezmez; Logo CRM'den önce gelir; yeterli örnek yoksa süre uydurulmaz (plan
boş kalır); ilerlemiş iş geride kalan adım için gecikme saymaz; gecikme ayardaki günü aşınca yöneticiye; baskı
tekrarı kartına önceki baskının tarihi ve emri sayılmaz; planlanan giriş fişi gerçekleşen sayılmaz.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from semantic_bridge import production as P
from semantic_bridge import production_plan as PL
from semantic_bridge import production_store as S
from semantic_layer.store.catalog_store import open_store

T = "t1"
CARD = "0a1b2c3d-1111-2222-3333-444455556666"
CARD2 = "0a1b2c3d-1111-2222-3333-777788889999"
BOOK = "9f8e7d6c-1111-2222-3333-444455556666"
SETTINGS = {"filesDay": 15, "monthsBefore": 1, "escalateDays": 7, "staleDays": 180}


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    S._ready.discard(id(e))
    S.ensure(e)
    return e


def _card(**act):
    return {"actual": {k: {"day": v, "source": "crm"} for k, v in act.items()}}


def test_files_due_and_month_end():
    assert PL.files_due(date(2026, 11, 1)) == date(2026, 10, 15)
    assert PL.files_due(date(2026, 1, 20)) == date(2025, 12, 15)
    assert PL.files_due(date(2026, 3, 31), files_day=31, months_before=1) == date(2026, 2, 28)
    assert PL.files_due(date(2026, 3, 5), files_day=10, months_before=0) == date(2026, 3, 10)
    assert PL.month_end(date(2026, 2, 1)) == date(2026, 2, 28)


def test_crm_dates_are_utc_and_read_as_istanbul_day():
    # Bağlayıcı tarihleri ISO metni olarak verir; CRM gece yarısını UTC 21:00 saklar.
    assert P._dayiso("2026-06-30T21:00:00") == "2026-07-01"
    assert P._dayiso(datetime(2026, 6, 30, 21)) == "2026-07-01"
    assert P._dayiso("2026-08-14T00:00:00") == "2026-08-14" and P._dayiso("2026-08-14") == "2026-08-14"
    assert P._dayiso("1900-01-01T00:00:00") is None and P._dayiso(None) is None


def test_leads_need_samples_and_skip_negative():
    few = [_card(dosya="2026-01-01", baski="2026-01-11")] * (PL.MIN_SAMPLES - 1)
    assert PL.measure_leads(few)["dosya>baski"]["days"] is None
    many = [_card(dosya="2026-01-01", baski=f"2026-01-{10 + i % 5:02d}") for i in range(PL.MIN_SAMPLES)]
    many.append(_card(dosya="2026-02-10", baski="2026-02-01"))   # sıra dışı giriş: süreye katılmaz
    many.append({"actual": {"dosya": {"day": None}, "baski": {"day": "2026-02-01"}}})   # tarihsiz: sayılmaz
    lead = PL.measure_leads(many)["dosya>baski"]
    assert lead["days"] == 11 and lead["samples"] == PL.MIN_SAMPLES and lead["negative"] == 1


def test_template_measured_on_new_books_only():
    cards = [{"firstPrint": True, "crmPlan": {"baski": "2026-11-01", "dosya": "2026-10-15", "grafik": "2026-09-25"}}
             for _ in range(PL.MIN_SAMPLES)]
    cards.append({"firstPrint": False, "crmPlan": {"baski": "2026-11-01", "dosya": "2026-11-30"}})
    t = PL.measure_template(cards)
    assert t["dosya"]["days"] == -17 and t["dosya"]["samples"] == PL.MIN_SAMPLES and t["grafik"]["days"] == -37
    assert t["son"]["days"] is None


def test_backward_plan_expected_and_risk():
    leads = {"matbaa>dosya": {"days": 6}, "dosya>baski": {"days": 12}, "baski>depo": {"days": 0}}
    template = {"grafik": {"days": -37}, "son": {"days": -27}, "dagilim": {"days": 5}}
    b = PL.backward(date(2026, 11, 1), leads, template)
    assert b["plan"] == {"matbaa": "2026-10-09", "dosya": "2026-10-15", "baski": "2026-11-30", "depo": "2026-11-30"}
    assert b["expected"] == {"baski": "2026-10-27", "depo": "2026-10-27"} and b["risk"] == []
    assert [e["day"] for e in b["extra"]] == ["2026-09-25", "2026-10-05", "2026-11-06"]
    slow = PL.backward(date(2026, 11, 1), {"dosya>baski": {"days": 50}, "baski>depo": {"days": 0}}, {})
    assert len(slow["risk"]) == 2 and slow["plan"]["matbaa"] is None and slow["extra"] == []   # ölçülmeyen uydurulmaz


def test_actual_priority_logo_then_crm_then_portal_and_status():
    crm = {"dosya": "2026-09-01", "matbaa": None, "depo": "2026-09-20"}
    manual = {"matbaa": {"day": "2026-08-30", "by": "Ayşe"}, "dosya": {"day": "2026-08-01", "by": "Ayşe"}}
    a = PL.resolve_actual({"baski": "2026-09-17", "depo": "2026-09-18"}, crm, manual)
    assert a["depo"] == {"day": "2026-09-18", "source": "logo"} and a["baski"]["source"] == "logo"
    assert a["dosya"]["source"] == "crm" and a["dosya"]["day"] == "2026-09-01"   # portal CRM'i ezmez
    assert a["matbaa"]["source"] == "portal"
    s = PL.resolve_actual({}, {}, {}, ("matbaa", "dosya", "baski", "depo"))
    assert s["depo"] == {"day": None, "source": "crm"}


def test_delays_escalate_and_ignore_passed_steps():
    plan = {"matbaa": "2026-08-25", "dosya": "2026-09-01", "baski": "2026-09-15", "depo": "2026-09-25"}
    today = date(2026, 9, 28)
    d = PL.delays(plan, {}, today, escalate_days=7)
    assert [x["milestone"] for x in d] == ["matbaa", "dosya", "baski", "depo"]
    assert d[1]["days"] == 27 and d[1]["level"] == "yonetici" and d[3]["level"] == "sorumlu"
    d2 = PL.delays(plan, {"baski": {"day": "2026-09-20"}}, today)
    assert [x["milestone"] for x in d2] == ["depo"]
    assert PL.stage({"baski": {}}) == "yolda" and PL.stage({"depo": {}}) == "tamam" and PL.stage({}) == "hazirlik"
    assert PL.stage({"matbaa": {}}) == "matbaa-secildi" and PL.stage({"matbaa": {}, "dosya": {}}) == "matbaada"


def test_printer_stats_and_score():
    today = date(2026, 9, 28)
    cards = [
        {"printer": "A", "stage": "tamam", "actual": {"dosya": {"day": "2026-05-01"}, "baski": {"day": "2026-05-21"}, "depo": {"day": "2026-05-21"}},
         "plan": {"baski": "2026-05-31"}, "unitPrice": None, "price": 10000, "qty": 1000, "created": "2026-04-20", "quality": "sorunsuz"},
        {"printer": "A", "stage": "tamam", "actual": {"dosya": {"day": "2026-06-01"}, "depo": {"day": "2026-06-30"}},
         "plan": {"baski": "2026-06-20"}, "price": 24000, "qty": 2000, "created": "2025-06-01", "quality": "sorun"},
        {"printer": "A", "stage": "hazirlik", "actual": {}, "plan": {}, "price": None, "qty": 500, "created": "2026-09-01"},
        {"printer": "A", "stage": "iptal", "actual": {}, "plan": {}, "qty": 9, "created": "2026-09-01"},
        {"printer": None, "actual": {}, "created": "2026-09-01"},
    ]
    [a] = PL.printer_stats(cards, today)
    assert a["jobs"] == 3 and a["open"] == 1 and a["done"] == 2 and a["copies"] == 3500
    assert a["onTimeRate"] == 0.5 and a["measured"] == 2 and a["leadDays"] == 24
    assert a["unitRecent"] == 10.0 and a["unitPrevious"] == 12.0 and a["unitTrend"] == round(-2 / 12, 4)
    assert a["qualityRate"] == 0.5
    s = PL.score(a, 11.0)
    assert s["parts"] == {"onTime": 25.0, "price": 30.0, "quality": 10.0} and not s["notes"]
    assert PL.score({"unitPrice": 16.5}, 11.0)["parts"]["price"] == 15.0
    blank = PL.score({"onTimeRate": None, "unitPrice": None, "qualityRate": None}, None)
    assert blank["score"] == 50 and len(blank["notes"]) == 3


def test_entries_validation_current_and_delete(engine):
    today = date(2026, 9, 28)
    with pytest.raises(S.ProductionError, match="ileri"):
        S.add_entry(engine, T, "ayse", "Ayşe", CARD, {"kind": "gercek", "milestone": "depo", "day": "2026-10-01"}, today)
    with pytest.raises(S.ProductionError, match="bir cümle"):
        S.add_entry(engine, T, "ayse", "Ayşe", CARD, {"kind": "kalite", "value": "sorun"}, today)
    with pytest.raises(S.ProductionError):
        S.add_entry(engine, T, "ayse", "Ayşe", "yok", {"kind": "not", "note": "x"}, today)
    e1 = S.add_entry(engine, T, "ayse", "Ayşe", CARD.upper(), {"kind": "gercek", "milestone": "dosya", "day": "2026-09-01"}, today)
    S.add_entry(engine, T, "mehmet", "Mehmet", CARD, {"kind": "gercek", "milestone": "dosya", "day": "2026-09-03"}, today)
    S.add_entry(engine, T, "ayse", "Ayşe", CARD, {"kind": "yayin", "day": "2026-12-01"}, today)
    entries, _ = S.load(engine, T)
    cur = S.current(entries[CARD])
    assert cur["actual"]["dosya"]["day"] == "2026-09-03" and cur["publication"]["day"] == "2026-12-01"
    with pytest.raises(S.ProductionError) as e:
        S.delete_entry(engine, T, "mehmet", False, e1["id"])
    assert e.value.status == 403
    S.delete_entry(engine, T, "ayse", False, e1["id"])
    entries, _ = S.load(engine, T)
    assert all(x["id"] != e1["id"] for x in entries[CARD])


def test_quotes(engine):
    with pytest.raises(S.ProductionError, match="fiyat"):
        S.add_quote(engine, T, "ayse", "Ayşe", CARD, {"printer": "A"})
    q = S.add_quote(engine, T, "ayse", "Ayşe", CARD, {"printer": "A", "unitPrice": "1.250,5", "deliveryDay": "2026-10-10"})
    assert q["unitPrice"] == 1250.5 and q["deliveryDay"] == "2026-10-10"
    assert S.add_quote(engine, T, "ayse", "Ayşe", CARD, {"printer": "A", "totalPrice": "12.5"})["totalPrice"] == 12.5
    _, quotes = S.load(engine, T, [CARD])
    assert len(quotes[CARD]) == 2


def _crm(cid, created, kart, **dates):
    row = {"id": cid.upper(), "name": "Kitap", "idno": None, "stok": "KTP001", "baski_no": 1, "kart": kart, "tip": 100000000,
           "matbaa": 7, "durum": 1, "oncelik": None, "bekleme": None, "bandrol": None, "adet": 3000, "oneri_adet": None,
           "net_adet": None, "fiyat": 240, "olusturma": created, "kitap_id": BOOK.upper(), "kitap": "Deneme Kitabı",
           "editor": "Ayşe", "grafiker": None}
    row.update({k.lower(): v for k, v in dates.items()})
    return row


def _snap():
    first = _crm(CARD2, datetime(2026, 3, 1, 9), 2, new_DepoGiriTarihi=datetime(2026, 4, 9, 21))
    second = _crm(CARD, datetime(2026, 8, 1, 9), 1, new_baskiyahazirtarihi=datetime(2026, 8, 31, 21),
                  new_DepoGiriTarihi=datetime(2026, 4, 9, 21),                  # önceki baskıdan kopya
                  new_uretimteslimtarihi=datetime(2026, 8, 14, 21), new_new_baskitarihi=datetime(2026, 8, 31, 21))
    second.update(idno="URTN-202600000001", baski_no=2)
    return {"cards": [second, first],
            "options": {"new_matbaa": {7: "Örnek Matbaa"}, "new_uretimtipi": {100000000: "Kitap"},
                        "new_baskikartidurumu": {1: "Baskı Tekrarı", 2: "Yeni Baskı"}},
            "orders": [{"firma": "411", "ref": 55, "no": "E-2", "idno": "urtm-202600000001", "tarih": datetime(2026, 9, 2),
                        "plan_adet": 3000, "durum": 3, "stok": "KTP001"},
                       {"firma": "411", "ref": 40, "no": "E-1", "idno": "", "tarih": datetime(2026, 3, 10),
                        "plan_adet": 5000, "durum": 3, "stok": "KTP001"}],
            "receipts": [{"firma": "411", "emir": 55, "ps": 1, "tarih": datetime(2026, 9, 25), "adet": 3000, "no": "P"},
                         {"firma": "411", "emir": 55, "ps": 0, "tarih": datetime(2026, 9, 14), "adet": 1000, "no": "1"},
                         {"firma": "411", "emir": 55, "ps": 0, "tarih": datetime(2026, 9, 16), "adet": 2100, "no": "2"},
                         {"firma": "411", "emir": 40, "ps": 0, "tarih": datetime(2026, 3, 20), "adet": 5000, "no": "3"}],
            "costs": [{"firma": "411", "tarih": datetime(2026, 9, 20), "cari": "ÖRNEK MATBAACILIK", "stok": "KTP001", "adet": 3000, "tutar": 27000},
                      {"firma": "411", "tarih": datetime(2026, 3, 25), "cari": "ÖRNEK MATBAACILIK", "stok": "KTP001", "adet": 5000, "tutar": 40000}],
            "firms": ["411"], "since": "2024-01-01", "at": 0, "crmMs": 1, "logoMs": 1, "warnings": []}


def test_build_cards_joins_logo_costs_and_windows():
    leads = {"dosya>baski": {"days": 10}, "baski>depo": {"days": 0}, "matbaa>dosya": {"days": None}}
    cards = {c["id"]: c for c in P.build_cards(_snap(), {}, leads=leads, settings=SETTINGS, now=date(2026, 9, 28), template={})}
    c, old = cards[CARD], cards[CARD2]
    assert c["logoMatch"] == "no" and old["logoMatch"] == "stok"          # URTM yazımı da eşleşir; eski emir eski karta
    assert c["bookId"] == BOOK and c["printer"] == "Örnek Matbaa" and c["cardKind"] == "Baskı Tekrarı" and not c["firstPrint"]
    assert c["actual"]["dosya"] == {"day": "2026-09-01", "source": "crm"}       # UTC 21:00 → İstanbul günü
    assert c["actual"]["baski"] == {"day": "2026-09-14", "source": "logo"}      # planlanan fiş (25 Eylül) sayılmaz
    assert c["actual"]["depo"] == {"day": "2026-09-16", "source": "logo"} and c["logoQty"] == 3100
    assert c["plan"]["dosya"] == "2026-08-15" and c["plan"]["baski"] == "2026-09-30" and c["plan"]["depo"] == "2026-09-25"
    assert c["unitPrice"] == 9.0 and c["costSupplier"] == "ÖRNEK MATBAACILIK" and c["coverPrice"] == 240
    assert old["unitPrice"] == 8.0 and old["actual"]["depo"]["day"] == "2026-03-20"
    assert c["stage"] == "tamam" and c["delays"] == []


def test_inherited_crm_dates_ignored_on_reprint():
    snap = _snap()
    snap["orders"], snap["receipts"], snap["costs"] = [], [], []
    cards = {c["id"]: c for c in P.build_cards(snap, {}, leads={}, settings=SETTINGS, now=date(2026, 9, 28), template={})}
    assert "depo" not in cards[CARD]["actual"]                                  # 9 Nisan önceki baskının
    assert cards[CARD2]["actual"]["depo"]["day"] == "2026-04-10"               # yeni kitap kartında sayılır


def test_publication_anchor_delays_and_filters():
    snap = _snap()
    snap["receipts"], snap["costs"] = [], []
    entries = {CARD: [{"id": "x" * 32, "kind": "yayin", "day": "2026-10-01", "milestone": None, "value": None, "note": None,
                       "byName": "Ayşe"}]}
    leads = {"dosya>baski": {"days": 10}, "baski>depo": {"days": 0}}
    cards = {c["id"]: c for c in P.build_cards(snap, entries, leads=leads, settings=SETTINGS, now=date(2026, 10, 5), template={})}
    c = cards[CARD]
    assert c["planBasis"] == "yayin" and c["plan"]["dosya"] == "2026-09-15" and c["plan"]["baski"] == "2026-10-31"
    assert c["delays"] == [] and c["stage"] == "matbaada"
    late = P.build_cards(snap, entries, leads=leads, settings=SETTINGS, now=date(2026, 11, 10), template={})
    lc = next(x for x in late if x["id"] == CARD)
    assert [(d["milestone"], d["days"], d["level"]) for d in lc["delays"]] == [("baski", 10, "yonetici"), ("depo", 10, "yonetici")]
    assert P.filter_cards([lc], durum="gecikme") == [lc] and P.filter_cards([lc], durum="tamam") == []
    assert P.filter_cards([lc], q="deneme kitabi") == [lc] and P.filter_cards([lc], tur="ilk") == []
    assert P.filter_cards([lc], urun="kitap") == [lc] and P.filter_cards([lc], urun="diger") == []
    stale = P.build_cards(snap, entries, leads=leads, settings=SETTINGS, now=date(2027, 6, 1), template={})
    assert next(x for x in stale if x["id"] == CARD)["stage"] == "eski"
    assert P.filter_cards(stale, durum="acik") == []


def test_cancelled_card_has_no_delays():
    snap = _snap()
    snap["cards"][0]["durum"] = P.STATUS_CANCELLED
    snap["receipts"] = []
    c = next(x for x in P.build_cards(snap, {}, leads={}, settings=SETTINGS, now=date(2026, 12, 1), template={}) if x["id"] == CARD)
    assert c["stage"] == "iptal" and c["delays"] == []


def test_suggest_prefers_quotes_and_explains():
    stats = [{"printer": "A", "jobs": 10, "open": 2, "done": 8, "copies": 1, "onTimeRate": 0.9, "measured": 8, "leadDays": 20,
              "leadSamples": 8, "unitPrice": 10.0, "unitSamples": 8, "unitRecent": 10.0, "unitPrevious": 9.0, "unitTrend": 0.1,
              "qualityRate": None, "qualityMarked": 0, "last": None}]
    quotes = [{"printer": "B", "unitPrice": 9.0, "deliveryDay": "2026-10-10"}]
    out = P.suggest({}, stats, quotes, 10.0)
    assert [s["printer"] for s in out] == ["B", "A"]
    assert any("teklif verdi" in w for w in out[0]["why"]) and any("zamanında" in w for w in out[1]["why"])


def test_studio_links_by_book_or_title():
    c = {"bookId": BOOK, "bookTitle": "Deneme Kitabı"}
    jobs = {"items": [
        {"id": "1", "title": "Başka", "source": {"crm_book_id": BOOK.upper()}, "steps": [{"key": "preflight", "status": "done"}]},
        {"id": "2", "title": "DENEME KİTABI", "source": {}, "steps": []},
        {"id": "3", "title": "Alakasız", "source": {}, "steps": []},
    ]}
    out = P.studio_links(c, jobs)
    assert [x["job"] for x in out] == ["1", "2"] and out[0]["ready"] and not out[1]["ready"]


def test_sql_shapes():
    sql = P.crm_cards_sql("Timas_MSCRM.dbo", date(2024, 1, 1))
    assert "Timas_MSCRM.dbo.new_UretimBase" in sql and "r.statecode = 0" in sql and "'2024-01-01'" in sql
    assert "<> 8" in sql and "100000011" in sql                                   # e-kitap basılmaz
    with pytest.raises(S.ProductionError):
        P.crm_cards_sql("x;drop", date(2024, 1, 1))
    assert "LG_411_PRODORD" in P.logo_orders_sql("411", date(2024, 1, 1))
    r = P.logo_receipts_sql("211", "01", date(2024, 1, 1))
    assert "LG_211_01_STFICHE" in r and "TRCODE = 13" in r and "PRODSTAT" in r and "l.STOCKREF = o.ITEMREF" in r
    assert "730.38.381" in P.logo_costs_sql("411", "01", date(2024, 1, 1))
    with pytest.raises(S.ProductionError):
        P.logo_orders_sql("41; --", date(2024, 1, 1))
    with pytest.raises(S.ProductionError):
        P.logo_receipts_sql("411", "1;", date(2024, 1, 1))


def test_settings_defaults_and_bounds():
    s = P.settings_from(lambda k, d="": {"PRODUCTION_FILES_DAY": "40", "PRODUCTION_ESCALATE_DAYS": "abc"}.get(k, d))
    assert s["filesDay"] == 28 and s["escalateDays"] == 7 and s["monthsBefore"] == 1 and s["staleDays"] == 180
    assert s["historyFrom"] == date(P.today().year - 2, 1, 1).isoformat()
