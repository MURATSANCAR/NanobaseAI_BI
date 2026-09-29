"""M52 Tedarik ve baskı: yük tablosu (kapasite / referans eşiği), çakışma, kağıt ihtiyacı, FIFO borç yaşlandırması
(katalog tanımıyla aynı sonuç), tedarikçi sınıflaması ve matbaa–cari eşlemesi, faturası görünmeyen baskı, fatura adayı,
birim maliyet eğilimi, plan girdisi (Baskı Öneri, M10), yük dengeleme önerisi, model metni sayı denetimi, portal
kayıtları ve uçların yetki davranışı.

Sözleşme: kapasite girilmemiş matbaada «kapasite» denmez (referans); FIFO sonucu katalogdaki «vadesi geçmiş» ile aynı;
borç ve maliyet alanı açıkça verilen yetki olmadan gitmez; öneri kararı CRM'e yazmaz; model yeni sayı yazarsa metni
atılır.
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from semantic_bridge import production as P
from semantic_bridge import supply as S
from semantic_bridge import supply_sources as src
from semantic_bridge import supply_store as store
from semantic_bridge import supply_suggest as G
from semantic_layer.store.catalog_store import open_store

T = "t1"
NOW = date(2026, 10, 10)


def gid(n: int) -> str:
    return f"0a1b2c3d-1111-2222-3333-{n:012d}"


def card(n: int, *, printer="A Matbaa", stage="hazirlik", qty=1000.0, baski="2026-10-31", depo=None, bdone=None,
         pub=None, code=None, cost_rows=None, prio="Normal", approval=None, title=None, kind=100000000):
    actual = {}
    if bdone:
        actual["baski"] = {"day": bdone, "source": "logo"}
    if depo:
        actual["depo"] = {"day": depo, "source": "logo"}
    return {"id": gid(n), "name": f"K{n}", "bookTitle": title or f"Kitap {n}", "stockCode": code or f"S{n}", "printNo": 1,
            "firstPrint": True, "kind": "Kitap", "kindCode": kind, "printer": printer, "qty": qty, "stage": stage,
            "stageLabel": stage, "plan": {"baski": baski, "dosya": None, "depo": None}, "actual": actual, "delays": [],
            "publication": pub, "priority": prio, "waiting": None, "approval": approval, "costRows": cost_rows or [],
            "unitPrice": None, "price": None, "created": "2026-01-01"}


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    store._ready.discard(id(e))
    store.ensure(e)
    return e


# ------------------------------------------------------------------ yük


def test_load_table_buckets_forma_and_reference_not_capacity():
    hist = [card(100 + i, stage="tamam", bdone=f"2026-0{m}-10", depo=f"2026-0{m}-20", qty=500) for i, m in enumerate((6, 6, 7))]
    cards = hist + [card(1, baski="2026-10-31", qty=800), card(2, baski="2026-10-31", qty=700),
                    card(3, baski="2026-08-31", qty=100),                       # planı geçmiş
                    card(4, baski=None, qty=50),                                 # tarihsiz
                    card(5, printer=None, baski="2026-11-30", qty=10),
                    card(6, stage="yolda", baski="2026-10-31", qty=9999)]        # baskıdan çıkmış: yük değil
    tech = {gid(1): {"forma": 10}, gid(2): {"forma": 12}}
    t = S.load_table(cards, tech, [], NOW, 3)
    assert [m["key"] for m in t["aylar"]] == [S.OVERDUE, "2026-10", "2026-11", "2026-12", S.UNDATED]
    row = next(r for r in t["satirlar"] if r["matbaa"] == "A Matbaa")
    oct_ = row["hucreler"]["2026-10"]
    assert oct_["jobs"] == 2 and oct_["adet"] == 1500 and oct_["forma"] == 10 * 800 + 12 * 700
    # Referans: son 12 ayın en yüksek ayı (Haziran 1.000 adet); kapasite yok → «referans-ustu», «asim» değil.
    assert row["referans"]["adet"] == 1000 and row["referans"]["ay"] == "2026-06"
    assert oct_["durum"] == "referans-ustu" and oct_["oran"] == 1.5 and oct_["kapasite"] is None
    assert row["hucreler"][S.OVERDUE]["jobs"] == 1 and row["hucreler"][S.UNDATED]["jobs"] == 1
    assert t["satirlar"][-1]["matbaa"] == S.NO_PRINTER
    assert t["toplam"]["2026-10"]["adet"] == 1500           # yoldaki 9.999 sayılmadı


def test_capacity_wins_over_reference_and_month_record_over_default(engine):
    store.add_capacity(engine, T, "u", "U", {"matbaa": "A Matbaa", "kapasiteAdet": "2.000"})
    store.add_capacity(engine, T, "u", "U", {"matbaa": "A Matbaa", "ay": "2026-10", "kapasiteAdet": "1000"})
    caps = store.list_capacity(engine, T)
    assert store.capacity_for(caps, "A Matbaa", "2026-10")["kapasiteAdet"] == 1000
    assert store.capacity_for(caps, "A Matbaa", "2026-11")["kapasiteAdet"] == 2000
    t = S.load_table([card(1, qty=1200), card(2, baski="2026-11-30", qty=1200)], {}, caps, NOW, 2)
    row = t["satirlar"][0]
    assert row["hucreler"]["2026-10"]["durum"] == "asim" and row["hucreler"]["2026-11"]["durum"] == "normal"
    c = S.conflicts(t)
    assert len(c) == 1 and c[0]["ay"] == "2026-10" and c[0]["durum"] == "asim"
    with pytest.raises(store.SupplyError):
        store.add_capacity(engine, T, "u", "U", {"matbaa": "A Matbaa"})
    with pytest.raises(store.SupplyError):
        store.add_capacity(engine, T, "u", "U", {"matbaa": "Yok Matbaa", "kapasiteAdet": 1}, ["A Matbaa"])
    with pytest.raises(store.SupplyError):
        store.add_capacity(engine, T, "u", "U", {"matbaa": "A Matbaa", "ay": "2026-13", "kapasiteAdet": 1})


def test_no_reference_and_no_capacity_is_not_measurable():
    t = S.load_table([card(1, printer="Yeni Matbaa", qty=5)], {}, [], NOW, 1)
    assert t["satirlar"][0]["hucreler"]["2026-10"]["durum"] == "olculemedi"
    assert S.conflicts(t) == []


# ------------------------------------------------------------------ kağıt


def test_paper_need_by_month_and_kind_with_coverage():
    tech = {gid(1): {"parts": [{"part": "icsayfabir", "label": "İç 1", "net": 900.0, "brut": 1000.0, "toplam": 1.0, "cins": "c1", "ebat": "e1"},
                               {"part": "kapak", "label": "Kapak", "net": 40.0, "brut": 50.0, "toplam": None, "cins": "c2", "ebat": None}]},
            gid(2): {"parts": [{"part": "icsayfabir", "label": "İç 1", "net": 450.0, "brut": None, "toplam": None, "cins": "c1", "ebat": "e1"}]},
            gid(3): {"parts": []}}
    names = {"c1": {"ad": "60 gr kitap kağıdı", "gramaj": 60}, "c2": {"ad": "Bristol 300", "gramaj": 300}, "e1": {"ad": "70x100"}}
    cards = [card(1), card(2), card(3), card(4, stage="tamam")]
    p = S.paper_need(cards, tech, names, NOW, 2, "brut")
    oct_c1 = next(r for r in p["satirlar"] if r["ay"] == "2026-10" and r["cins"] == "c1")
    assert oct_c1["kg"] == 1000 and oct_c1["digerKg"] == 1350 and oct_c1["kart"] == 2 and oct_c1["eksikOlcu"] == 1
    assert oct_c1["ebatlar"] == {"70x100": 1000.0}
    assert p["kapsam"] == {"dolu": 2, "bos": 1} and p["kagitsizKartlar"][0]["id"] == gid(3)
    assert p["toplamKg"] == 1050
    net = S.paper_need(cards, tech, names, NOW, 2, "net")
    assert next(r for r in net["satirlar"] if r["cins"] == "c1")["kg"] == 1350


def test_paper_plan_lead_time_and_urgency():
    paper = {"satirlar": [{"ay": "2026-12", "ayAdi": "Aralık 2026", "cins": "c1", "cinsAdi": "60 gr", "gramaj": 60, "kg": 500, "kart": 2},
                          {"ay": S.OVERDUE, "ayAdi": "Planı geçmiş", "cins": "c1", "cinsAdi": "60 gr", "gramaj": 60, "kg": 10, "kart": 1},
                          {"ay": "2026-11", "ayAdi": "Kasım 2026", "cins": None, "cinsAdi": "Kağıt cinsi girilmemiş", "kg": 99, "kart": 1}]}
    plan = G.paper_plan(paper, 30, NOW)
    assert [x["ay"] for x in plan] == [S.OVERDUE, "2026-12"]
    assert plan[0]["acil"] and plan[0]["enGec"] == NOW.isoformat()
    assert plan[1]["enGec"] == "2026-11-01" and not plan[1]["acil"]


# ------------------------------------------------------------------ FIFO borç


def _lines(ref, rows):
    """(vade, tutar) → kumulatif en yeni vadeden geriye (SQL'deki pencere)."""
    rows = sorted(rows, key=lambda x: x[0], reverse=True)
    out, kum = [], 0.0
    for i, (v, t) in enumerate(rows):
        kum += t
        out.append({"ref": ref, "satir": i, "vade": v, "tutar": t, "kumulatif": kum, "faturaNo": None, "faturaTarihi": None})
    return out


def test_fifo_aging_matches_catalog_definition():
    lines = _lines(1, [(date(2026, 11, 5), 300.0), (date(2026, 10, 20), 200.0), (date(2026, 9, 1), 400.0),
                       (date(2026, 6, 1), 500.0)])
    a = S.aging(1000.0, lines, NOW)
    # Açık: en yeni 300 + 200 (gelmemiş) + 400'ün tamamı (39 gün) + 500'ün 100'ü (131 gün).
    assert a["gelmemis"] == 500 and a["g_0_30"] == 500 and a["g_31_60"] == 0
    assert a["k_31_60"] == 400 and a["k_90p"] == 100 and a["plansiz"] == 0
    assert a["vadesiGecmis"] == 500 == a["katalogVadesiGecmis"]
    # Bakiye plan satırlarından büyükse artan «vade planı olmayan» borçtur; katalog onu da vadesi geçmiş sayar.
    b = S.aging(2000.0, lines, NOW)
    assert b["plansiz"] == 600 and b["vadesiGecmis"] == 1500 == b["katalogVadesiGecmis"]
    # Bakiye gelmemişten küçükse vadesi geçmiş yok.
    c = S.aging(250.0, lines, NOW)
    assert c["vadesiGecmis"] == 0 == c["katalogVadesiGecmis"] and c["gelmemis"] == 250
    assert S.aging(-10.0, lines, NOW)["vadesiGecmis"] == 0


def test_fifo_upcoming_buckets():
    lines = _lines(1, [(date(2026, 10, 10), 10.0), (date(2026, 11, 20), 20.0), (date(2026, 12, 20), 30.0), (date(2027, 3, 1), 40.0)])
    a = S.aging(100.0, lines, NOW)
    assert (a["g_0_30"], a["g_31_60"], a["g_61_90"], a["g_90p"]) == (10, 20, 30, 40)


def test_classify_specode_first_then_print_invoice():
    sup = [{"kod": "320.1", "ozelKod": "MATBAALAR"}, {"kod": "320.2", "ozelKod": "kağıtçılar"}, {"kod": "320.3", "ozelKod": None},
           {"kod": "320.4", "ozelKod": "DİĞER"}]
    k = S.classify(sup, ["MATBAALAR"], ["KAĞITÇILAR"], {"320.3"})
    assert k["320.1"] == {"tur": "matbaa", "kaynak": "ozel-kod"} and k["320.2"]["tur"] == "kagit"
    assert k["320.3"] == {"tur": "matbaa", "kaynak": "baski-faturasi"} and k["320.4"]["tur"] == "diger"


def test_supplier_map_votes_manual_override():
    votes = {"A Matbaa": {"320.1": 9, "320.9": 1}, "B Matbaa": {"320.2": 1, "320.3": 1}}
    m = S.supplier_map(votes, {}, 0.6, 3)
    assert m["A Matbaa"]["cari"] == "320.1" and m["A Matbaa"]["kaynak"] == "veri"
    assert m["B Matbaa"]["cari"] is None and m["B Matbaa"]["kaynak"] == "belirsiz"
    m2 = S.supplier_map(votes, {"B Matbaa": {"cari": "320.3", "byName": "Ayşe"}}, 0.6, 3)
    assert m2["B Matbaa"]["cari"] == "320.3" and m2["B Matbaa"]["kaynak"] == "elle"


def test_printer_code_votes_use_m12_rule():
    raw = [{"id": gid(1), "stok": "S1", "olusturma": "2026-03-01"}, {"id": gid(2), "stok": "S2", "olusturma": "2026-03-01"}]
    built = [dict(card(1), printer="A Matbaa"), dict(card(2), printer="A Matbaa")]
    inv = [{"firma": "411", "satirRef": 1, "tarih": "2026-04-01", "stok": "S1", "cariKod": "320.1"},
           {"firma": "411", "satirRef": 2, "tarih": "2026-04-02", "stok": "S2", "cariKod": "320.1"},
           {"firma": "411", "satirRef": 3, "tarih": "2026-04-02", "stok": "", "cariKod": "320.7"}]
    assert S.printer_code_votes(raw, built, inv, P.match_costs) == {"A Matbaa": {"320.1": 2}}


# ------------------------------------------------------------------ faturası görünmeyen, fatura adayı


def test_unbilled_and_invoice_lag():
    billed = [card(10 + i, stage="tamam", depo="2026-05-01", cost_rows=[{"tarih": "2026-05-11", "adet": 1, "tutar": 1}])
              for i in range(S.MIN_SAMPLES)]
    lag = S.invoice_lag(billed)
    assert lag["gun"] == 10 and lag["ornek"] == S.MIN_SAMPLES
    assert S.invoice_lag(billed[:3])["gun"] is None
    cards = billed + [card(1, stage="tamam", depo="2026-09-01"), card(2, stage="tamam", depo="2026-10-05"),
                      card(3, stage="tamam", depo="2026-08-01")]
    ub = S.unbilled(cards, {}, {gid(3)}, NOW, 10, date(2026, 1, 1))
    assert [c["id"] for c in ub] == [gid(1)] and ub[0]["bekleyenGun"] == 39   # 2 henüz bekleme süresinde, 3 elle bağlı


def test_unmatched_invoices_and_candidates():
    raw = [{"id": gid(1), "stok": "S1", "olusturma": "2026-03-01"}]
    inv = [{"firma": "411", "satirRef": 1, "tarih": "2026-04-01", "no": "F1", "cariKod": "320.1", "cari": "A", "stok": "S1", "adet": 1000, "tutar": 5000},
           {"firma": "411", "satirRef": 2, "tarih": "2026-09-01", "no": "F2", "cariKod": "320.1", "cari": "A", "stok": "", "adet": 980, "tutar": 4900},
           {"firma": "411", "satirRef": 3, "tarih": "2025-01-01", "no": "F0", "cariKod": "320.1", "cari": "A", "stok": "", "adet": 5, "tutar": 1}]
    un = S.unmatched_invoices(raw, inv, P.match_costs, {}, date(2026, 1, 1))
    assert [x["satirRef"] for x in un] == ["2"]
    linked = {("411", "2"): {"durum": "onayli"}}
    assert S.unmatched_invoices(raw, inv, P.match_costs, linked, date(2026, 1, 1)) == []
    cards = [card(5, stage="tamam", depo="2026-08-25", qty=1000), card(6, stage="tamam", depo="2026-08-25", qty=500),
             card(7, printer="B Matbaa", stage="tamam", depo="2026-08-25", qty=1000)]
    cands = S.match_candidates(un[0], cards, {gid(5), gid(6), gid(7)}, {"A Matbaa": "320.1", "B Matbaa": "320.2"}, 0.15, 60)
    assert [c["kartId"] for c in cands] == [gid(5)]            # adet ±%15 ve matbaa eşlemesi


def test_choose_card_uses_closed_set_and_none():
    cands = [{"kartId": gid(1), "kitap": "A", "baskiNo": 1, "adet": 1000, "depo": "2026-08-25", "stokKodu": "S1"},
             {"kartId": gid(2), "kitap": "A", "baskiNo": 1, "adet": 1000, "depo": "2026-08-25", "stokKodu": "S1"}]
    seen = {}

    class Llm:
        def choose(self, prompt, choices):
            seen["choices"] = choices
            return SimpleNamespace(choice=choices[1], index=1, probability=0.8)

    kart, prob, how = G.choose_card(Llm(), {"cari": "A", "faturaNo": "F", "tarih": "2026-09-01", "adet": 1000}, cands)
    assert kart == gid(2) and prob == 0.8 and how == "zeki"
    assert len(set(seen["choices"])) == 3 and seen["choices"][-1] == G.NONE_CHOICE      # tekrar eden etiket ayrıştı

    class NoneLlm:
        def choose(self, prompt, choices):
            return SimpleNamespace(choice=G.NONE_CHOICE, index=len(choices) - 1, probability=0.9)

    assert G.choose_card(NoneLlm(), {}, cands) == (None, 0.9, "zeki")
    assert G.choose_card(None, {}, cands) == (gid(1), None, "kural")


# ------------------------------------------------------------------ maliyet, plan girdisi


def test_cost_trend_groups_and_direction():
    rows = lambda d, q, t: [{"tarih": d, "adet": q, "tutar": t}]  # noqa: E731
    cards = [card(1, stage="tamam", cost_rows=rows("2025-12-05", 1000, 10000)),
             card(2, stage="tamam", cost_rows=rows("2026-09-05", 1000, 12000)),
             card(3, stage="tamam", cost_rows=rows("2026-09-15", 1000, 14000))]
    tech = {gid(1): {"cilt": 1, "sayfa": 200}, gid(2): {"cilt": 1, "sayfa": 100}, gid(3): {"cilt": 3, "sayfa": 300}}
    opts = {"new_ciltlemesekli": {1: "Amerikan Cilt", 3: "Sert Kapak"}}
    t = S.cost_trend(cards, tech, opts, NOW, 12, "hepsi", [96, 160, 256, 400])
    g = t["gruplar"][0]
    assert g["is"] == 3 and g["aylar"]["2026-09"]["agirlikliBirim"] == 13 and g["aylar"]["2026-09"]["is"] == 2
    assert g["oncekiDonem"] == 10 and g["sonDonem"] == 13 and g["egilim"] == 0.3
    c = S.cost_trend(cards, tech, opts, NOW, 12, "cilt", [96, 160, 256, 400])
    assert {x["grup"] for x in c["gruplar"]} == {"Amerikan Cilt", "Sert Kapak"}
    s = S.cost_trend(cards, tech, opts, NOW, 12, "sayfa", [96, 160, 256, 400])
    assert {x["grup"] for x in s["gruplar"]} == {"161–256 sayfa", "97–160 sayfa", "257–400 sayfa"}
    assert S.page_band(None, [96]) == "Sayfa sayısı yok" and S.page_band(500, [96, 400]) == "401+ sayfa"


def test_demand_inputs_skip_books_with_open_cards():
    data = {"views": [{"id": "tekrar", "columns": [{"key": "stok_kodu"}, {"key": "urun_adi"}, {"key": "oneri"}, {"key": "oneri_adet"},
                                                   {"key": "tukenme_suresi"}],
                       "rows": [["S1", "A", "Risk/Acil", 3000, 0.4], ["S2", "B", "Kritik", 2000, "∞"], ["S3", "C", "Takip Et", 1, 2.0],
                                ["S4", "D", "Kritik", None, 1.2]]}]}
    rows = S.report_rows(data, "tekrar")
    cards = [card(1, code="S2")]
    d = S.demand_inputs(rows, [{"code": "Y1", "status": "onaylandi", "units": 5000, "launch": "2026-12", "title": "Yeni"},
                               {"code": "S2", "status": "onaylandi", "units": 1, "launch": "2026-11", "title": "Var"},
                               {"code": "Y2", "status": "bekliyor", "units": 1, "launch": "2026-11", "title": "Bekleyen"}], cards)
    assert [x["stokKodu"] for x in d["baskiOneri"]] == ["S1", "S4"] and d["baskiOneriAdet"] == 3000
    assert [x["stokKodu"] for x in d["ilkBaski"]] == ["Y1"] and d["ilkBaskiAdet"] == 5000


def test_incoming_plan_and_actuals():
    cards = [card(1, stage="yolda", baski="2026-10-31"), card(2, baski="2026-12-31", qty=300), card(3, baski="2026-08-31", qty=7)]
    cards[0]["plan"]["depo"] = "2026-11-05"
    out = S.incoming(cards, {"2026-09": {"adet": 1234.0, "fis": 3.0}}, NOW, 3, 2)
    assert [x["adet"] for x in out["plan"]] == [0, 1000, 300]
    assert out["planiGecmis"] == {"adet": 7, "is": 1}
    assert out["gecmis"][-2] == {"ay": "2026-09", "ayAdi": "Eylül 2026", "adet": 1234.0, "fis": 3}


# ------------------------------------------------------------------ öneriler ve model metni


def test_balance_moves_until_under_threshold_and_respects_publication():
    caps = [{"id": "x", "matbaa": "A Matbaa", "ay": None, "kapasiteAdet": 1000.0, "kapasiteForma": None}]
    cards = [card(1, qty=600), card(2, qty=500, pub="2026-10-31"), card(3, qty=300, approval="A Matbaa")]
    t = S.load_table(cards, {}, caps, NOW, 3)
    out = G.balance(t, {}, 1.0)
    assert len(out) == 1 and out[0]["kart"] == gid(1)          # yayın tarihi olan ve onaylı olan kaydırılmadı
    assert out[0]["hedef"] == {"matbaa": "A Matbaa", "ay": "2026-11", "ayAdi": "Kasım 2026", "yukSonra": 600, "esik": 1000}
    rule, facts = G.balance_facts(out[0])
    assert "1.400" in rule and "Kasım 2026" in rule and rule in facts


def test_model_text_rejects_new_numbers_and_tech_names():
    facts = "A Matbaa Ekim 2026 yükü 1.400 adet; eşik 1.000."

    class Llm:
        def __init__(self, text):
            self.text = text

        def chat(self, messages):
            return self.text

    assert G.model_text(Llm("Ekim 2026'da 1.400 adetle eşik 1.000 aşılıyor."), "s", facts)
    assert G.model_text(Llm("Yük 1.600 adet."), "s", facts) is None
    assert G.model_text(Llm("Model 1.400 diyor."), "s", facts) is None
    assert G.model_text(None, "s", facts) is None
    assert G.numbers_ok("1 Ekim 2026", "plan 01.10.2026")


def test_spec_text_is_template_from_card_fields():
    c = dict(card(1), qty=2500, plan={"baski": "2026-10-31", "dosya": "2026-09-15", "depo": None})
    tech = {"forma": 12, "sayfa": 192, "cilt": 1, "baskiTipi": 1, "kitapEbat": "e0",
            "parts": [{"label": "İç 1", "cins": "c1", "ebat": "e1", "brut": 1000.0}]}
    names = {"c1": {"ad": "60 gr", "gramaj": 60}, "e1": {"ad": "70x100"}, "e0": {"ad": "13,5x21"}}
    text = G.spec_text(c, tech, names, {"new_ciltlemesekli": {1: "Amerikan Cilt"}, "new_baskitipi": {1: "Matbu"}})
    assert "2.500" in text and "Amerikan Cilt" in text and "İç 1: 60 gr, 60 gr, ebat 70x100, brüt 1.000 kg" in text
    assert "gönderim" in text


# ------------------------------------------------------------------ portal kayıtları


def test_suggestion_upsert_expire_and_decide(engine):
    s, new = store.upsert_suggestion(engine, T, tur="yuk", anahtar="yuk:k1", baslik="B", payload={"a": 1}, metin="m")
    assert new and s["durum"] == "bekliyor"
    s2, new2 = store.upsert_suggestion(engine, T, tur="yuk", anahtar="yuk:k1", baslik="B2", payload={"a": 2}, metin=None)
    assert not new2 and s2["id"] == s["id"] and s2["veri"] == {"a": 2} and s2["metin"] == "m"
    with pytest.raises(store.SupplyError):
        store.decide_suggestion(engine, T, "u", "U", s["id"], {"karar": "ret"})          # gerekçesiz ret
    d = store.decide_suggestion(engine, T, "u", "U", s["id"], {"karar": "kabul"})
    assert d["durum"] == "kabul" and d["kararVeren"] == "U"
    with pytest.raises(store.SupplyError) as e:
        store.decide_suggestion(engine, T, "u", "U", s["id"], {"karar": "kabul"})
    assert e.value.status == 409
    store.upsert_suggestion(engine, T, tur="yuk", anahtar="yuk:k2", baslik="C", payload={}, metin=None)
    assert store.expire_suggestions(engine, T, "yuk", {"yuk:k1"}) == 1              # kararlıya dokunmaz
    assert {x["durum"] for x in store.list_suggestions(engine, T, "yuk")} == {"kabul", "eskidi"}
    dr = store.add_draft(engine, T, "u", tur="sartname", kart=gid(1), baslik="Ş", payload={}, metin="metin")
    assert dr["durum"] == "taslak"


def test_invoice_link_propose_approve_reject(engine):
    assert store.upsert_link_proposal(engine, T, firma="411", satir="7", fatura_no="F", kart=gid(1), yontem="kural",
                                      olasilik=None, adaylar=[])
    assert not store.upsert_link_proposal(engine, T, firma="411", satir="7", fatura_no="F", kart=gid(2), yontem="zeki",
                                          olasilik=0.7, adaylar=[])                 # bekleyen tazelenir
    cur = store.list_links(engine, T)
    assert len(cur) == 1 and cur[0]["kartId"] == gid(2) and cur[0]["yontem"] == "zeki"
    ok = store.decide_link(engine, T, "u", {"firma": "411", "satirRef": "7", "kartId": gid(2), "karar": "onay"}, {gid(2)})
    assert ok["durum"] == "onayli"
    assert not store.upsert_link_proposal(engine, T, firma="411", satir="7", fatura_no="F", kart=gid(1), yontem="kural",
                                          olasilik=None, adaylar=[])                # onaylı satıra dokunulmaz
    with pytest.raises(store.SupplyError):
        store.decide_link(engine, T, "u", {"firma": "411", "satirRef": "8", "kartId": gid(9), "karar": "onay"}, {gid(2)})
    none = store.decide_link(engine, T, "u", {"firma": "411", "satirRef": "9", "kartId": None, "karar": "onay"})
    assert none["kartId"] is None and none["yontem"] == "elle"


def test_supplier_map_store(engine):
    store.set_supplier_map(engine, T, "u", "U", {"matbaa": "A Matbaa", "cari": "320.01.001"})
    store.set_supplier_map(engine, T, "u", "U", {"matbaa": "A Matbaa", "cari": "320.01.002"})
    assert store.list_supplier_map(engine, T)["A Matbaa"]["cari"] == "320.01.002"
    store.set_supplier_map(engine, T, "u", "U", {"matbaa": "A Matbaa", "kaldir": True})
    assert store.list_supplier_map(engine, T) == {}
    with pytest.raises(store.SupplyError):
        store.set_supplier_map(engine, T, "u", "U", {"matbaa": "A Matbaa", "cari": "320'; DROP"})


# ------------------------------------------------------------------ SQL ve kaynak


def test_sql_files_fill_and_guard():
    sql = src.fill("logo_tedarikci_cari", firma="411", donem="01", yil_basi="2026-01-01", on_ek="320")
    assert "LG_411_01_CLFLINE" in sql and "LIKE '320%'" in sql and "{" not in sql
    with pytest.raises(src.SourceError):
        src.fill("logo_tedarikci_cari", firma="411")
    with pytest.raises(src.SourceError):
        src.firm("41;")
    with pytest.raises(src.SourceError):
        src.code_literal("320' OR 1=1 --")
    assert src.values_rows(["320.1", "320.1", "320.2"]) == "(N'320.1'), (N'320.2')"
    for sid, *_ in src.SOURCES:
        assert src.sql_text(sid).strip()
    gir = src.sql_text("logo_uretim_giris")
    assert "PRODSTAT = 0" in gir and "IOCODE = 1" in gir
    assert "SIGN = 1" in src.sql_text("logo_tedarikci_vade")
    # CRM'e ve Logo'ya yazma yok
    for sid, *_ in src.SOURCES:
        body = "\n".join(x for x in src.sql_text(sid).splitlines() if not x.strip().startswith("--")).upper()
        assert not any(w in body for w in ("INSERT ", "UPDATE ", "DELETE ", "MERGE ", "EXEC "))


def test_settings_defaults_and_bounds():
    conf = lambda k, d="": {"SUPPLY_OVERLOAD_RATIO": "9", "SUPPLY_PAPER_MEASURE": "ton"}.get(k, d)  # noqa: E731
    s = S.settings_from(conf)
    assert s["overloadRatio"] == 3.0 and s["paperMeasure"] == "brut" and s["loadMonths"] == 6
    assert s["printerSpecodes"] == ["MATBAALAR"] and s["paperSpecodes"] == ["KAĞITÇILAR"] and s["pageBands"] == [96, 160, 256, 400]


def test_access_rules_and_catalog():
    from semantic_bridge import access as A

    assert A.rule_for("/api/v1/supply/run-due") == A.SYSTEM
    assert A.page("tedarik") in A.rule_for("/api/v1/supply/load")
    f = A.features_for
    assert f("PUT", "/api/v1/supply/capacity") == ["ozellik:tedarik.kapasite"]
    assert f("POST", "/api/v1/supply/suggestions/abc/decision") == ["ozellik:tedarik.oneri-karar"]
    assert f("POST", "/api/v1/supply/drafts") == ["ozellik:tedarik.oneri-karar"]
    assert f("GET", "/api/v1/supply/export/borc.xlsx") == ["ozellik:veri.disa-aktar"]
    assert f("POST", "/api/v1/supply/invoice-links") == [] and f("PUT", "/api/v1/supply/supplier-map") == []
    assert {"ozellik:tedarik.borc", "ozellik:tedarik.maliyet", "ozellik:tedarik.eslesme"} <= A.explicit_keys()
    assert {"sayfa:tedarik", "sayfa:tedarik-yuk", "sayfa:tedarik-kagit", "sayfa:tedarik-tedarikciler", "sayfa:tedarik-maliyet",
            "ozellik:tedarik.kapasite", "ozellik:tedarik.oneri-karar"} <= A.all_keys()


# ------------------------------------------------------------------ uçlar (sahte M12, Logo/CRM bağlantısız)


def _client(engine, cards, perms):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from semantic_bridge import supply_api

    users = {"a": "ayse", "z": "zekiai"}

    def auth(request):
        u = users.get(request.headers.get("cookie", ""))
        if not u:
            from fastapi import HTTPException
            raise HTTPException(status_code=401)
        return engine, T, u, u.title()

    production = SimpleNamespace(
        cards=lambda e, t, fresh=False, now=None: (cards, {"since": "2025-01-01", "cards": [], "warnings": []}),
        source=SimpleNamespace(snapshot=lambda fresh=False: {"options": {"new_matbaa": {1: "A Matbaa", 2: "B Matbaa"}}}))
    app = FastAPI()
    supply_api.register(app, {
        "auth": auth, "can": lambda u, k: k in perms.get(u, set()), "is_admin": lambda u: u == "zekiai",
        "audit": lambda *a, **k: None, "conf": lambda k, d="": d, "fresh": lambda: False,
        "require_caller": lambda r: None, "runtime": lambda: (engine, T), "production": production,
        "logo_file": lambda: "/yok/logo.json", "crm_file": lambda: "/yok/crm.json", "llm": lambda p: None,
        "send_mail": None,
    })
    return TestClient(app)


def test_api_permissions_and_no_logo(engine):
    cards = [card(1, qty=700, baski=f"{datetime.now(S.TZ).year}-12-31")]
    c = _client(engine, cards, {"ayse": set()})
    a, z = {"cookie": "a"}, {"cookie": "z"}
    meta = c.get("/api/v1/supply/meta", headers=a).json()
    assert meta["me"]["canDebt"] is False and meta["printers"] == ["A Matbaa", "B Matbaa"]
    assert c.get("/api/v1/supply/payments", headers=a).status_code == 403
    assert c.get("/api/v1/supply/cost-trend", headers=a).status_code == 403
    assert c.get("/api/v1/supply/export/borc.xlsx", headers=a).status_code == 403
    # Yönetici: yetki var ama Logo bağlantısı yok → 503 düz cümle, uydurma tutar yok.
    r = c.get("/api/v1/supply/payments", headers=z)
    assert r.status_code == 503
    load = c.get("/api/v1/supply/load", headers=a).json()
    assert load["toplam"] and any("Logo" in w for w in load["uyarilar"])
    assert all("birimFiyat" not in x for row in load["satirlar"] for cell in row["hucreler"].values() for x in cell["cards"])
    ov = c.get("/api/v1/supply/overview", headers=a).json()
    assert "odeme30" not in ov and "maliyet" not in ov
    sup = c.get("/api/v1/supply/suppliers", headers=a).json()
    assert sup["items"] == [] and sup["borcGorunur"] is False
    assert c.put("/api/v1/supply/capacity", json={"matbaa": "Yok"}, headers=a).status_code == 400
    assert c.put("/api/v1/supply/supplier-map", json={"matbaa": "A Matbaa", "cari": "320.1"}, headers=a).status_code == 403
    assert c.post("/api/v1/supply/invoice-links", json={}, headers=a).status_code == 403
    assert c.post("/api/v1/supply/drafts", json={"tur": "x"}, headers=a).status_code == 400
    d = c.post("/api/v1/supply/drafts", json={"tur": "sartname", "kartId": gid(1)}, headers=a)
    assert d.status_code == 201 and "TASLAK" in d.json()["metin"]
    # test verisi bırakılmaz
    from semantic_bridge.supply_store import SUGGESTIONS
    with engine.begin() as conn:
        conn.execute(SUGGESTIONS.delete().where(SUGGESTIONS.c.id == d.json()["id"]))


# ------------------------------------------------------------------ hız (2026-09-29): uç kaynağı beklemez


def test_table_read_gives_the_same_answers_as_the_live_read(engine):
    """Eski hesap = yeni hesap: ilk açılış kaynağı okur ve okumayı tabloya yazar; köprü yeniden başladıktan sonra aynı
    uçlar tablodaki okumayla (kaynağa gitmeden) birebir aynı cevabı verir."""
    import json

    y = datetime.now(S.TZ).year
    cards = [card(1, qty=700, baski=f"{y}-12-31"), card(2, qty=500, stage="matbaada", printer="B Matbaa"),
             card(3, qty=900, stage="tamam", depo=f"{y}-01-10", bdone=f"{y}-01-05")]
    a = {"cookie": "a"}
    paths = ("/overview", "/load", "/paper", "/suppliers", "/unbilled", "/incoming?aylar=6", "/conflicts")
    c1 = _client(engine, cards, {"ayse": set()})
    first = {p: c1.get("/api/v1/supply" + p, headers=a).json() for p in paths}
    assert store.read_at(engine, T) is not None                       # okuma tabloya yazıldı
    c2 = _client(engine, [], {"ayse": set()})                          # köprü yeniden başladı; kaynak artık boş dönse de
    second = {p: c2.get("/api/v1/supply" + p, headers=a).json() for p in paths}
    for p in paths:
        assert json.dumps(second[p], sort_keys=True, default=str) == json.dumps(first[p], sort_keys=True, default=str), p


def test_refresh_does_not_wait_and_the_tour_does(engine, monkeypatch):
    """«Verileri yenile» eldeki okumayla hemen döner, yenisi arka planda okunup tabloya yazılır; tablodan gelen okuma
    tarihleri ve sayı anahtarlarıyla aynıdır; gece turu (`wait`) kaynağı bekler."""
    import threading
    import time as _t

    src_ = S.Source(SimpleNamespace(cards=lambda *a, **k: ([], {})), lambda: "", lambda: "", lambda: "", lambda: {})
    snap0 = {"at": _t.time(), "today": "2026-10-10", "since": "2025-01-01", "cards": [], "rawCards": [], "tech": {},
             "paperNames": {}, "options": {"new_matbaa": {1: "A Matbaa"}}, "planChanges": [], "warnings": [],
             "logo": {"ok": True, "dataEnd": date(2026, 8, 17), "firms": {"2026": "411"},
                      "planLines": [{"ref": 1, "vade": date(2026, 9, 1), "tutar": 10.0, "kumulatif": 10.0}]},
             "db": {}, "runs": {}}
    store.read_put(engine, T, snap0)                                   # gece turu yazmış
    got = store.read_get(engine, T)
    assert got == snap0 and isinstance(got["logo"]["dataEnd"], date) and 1 in got["options"]["new_matbaa"]
    gate = threading.Event()
    reads: list[int] = []

    def slow_read(engine_, tenant, fresh=False, now=None):
        reads.append(1)
        gate.wait(10)
        return {**snap0, "at": snap0["at"] + 1}
    monkeypatch.setattr(src_, "read", slow_read)
    t0 = _t.monotonic()
    s = src_.snapshot(engine, T, fresh=True)
    assert _t.monotonic() - t0 < 1.0 and s["at"] == snap0["at"] and src_.refreshing()
    gate.set()
    src_._bg.join(10)
    assert src_.snapshot(engine, T)["at"] == snap0["at"] + 1 and store.read_at(engine, T) == snap0["at"] + 1
    assert reads == [1]
    assert src_.snapshot(engine, T, True, None, wait=True) and reads == [1, 1]   # gece turu bekler


def test_supplier_invoices_from_the_read_equal_the_single_supplier_query():
    """Tedarikçi sayfası: turda okunan bütün tedarikçi faturalarından süzülen liste = eski tek cari sorgusunun sonucu."""
    since = date(2025, 10, 1)
    rows = [{"cari_kod": "320.01", "tarih": date(2026, 1, 20), "no": "F1", "tur": 4, "tutar": 8400.0, "kdv": 1400.0, "aciklama": "Baskı"},
            {"cari_kod": "320.02", "tarih": date(2026, 2, 1), "no": "F2", "tur": 1, "tutar": 500.0, "kdv": 80.0, "aciklama": None},
            {"cari_kod": "320.01", "tarih": date(2026, 3, 5), "no": "F3", "tur": 1, "tutar": 1200.5, "kdv": 200.1, "aciklama": "Kağıt"},
            {"cari_kod": "320.01", "tarih": date(2025, 9, 30), "no": "F0", "tur": 1, "tutar": 99.0, "kdv": 9.0, "aciklama": None}]

    def run(sql):
        sid = src._filled.last[0]
        if sid == "logo_tedarikci_faturalar":          # SQL: C.CODE = '320.01' AND DATE_ >= since
            return [{k: v for k, v in r.items() if k != "cari_kod"} for r in rows
                    if r["cari_kod"] == "320.01" and r["tarih"] >= since]
        assert sid == "logo_tedarikci_faturalar_tumu" and "LIKE '320%'" in sql
        return [r for r in rows if r["tarih"] >= date(2025, 9, 1)]   # turun penceresi daha erken başlamış olabilir
    old = src.read_supplier_invoices(run, ["411"], "320.01", since)
    new = src.supplier_invoices_of(src.read_all_supplier_invoices(run, ["411"], "320", date(2025, 9, 1)), "320.01", since)
    assert new == old and [x["no"] for x in new] == ["F3", "F1"]
