"""Sözleşme karşılaştırma (`semantic_bridge.contracts_compare`, `contracts_compare_docs`, `contracts_compare_api`).

Sözleşme: kıyas grubu aynı tip/ödeme türü/para birimi/bölüm ve dönemdir, küçükse ölçütler sırayla gevşer ve yazılır;
grup sözleşmesinin aynı şartlı kopyaları tek sayılır ve sözleşme kendi anlaşmasıyla kıyaslanmaz; sapma kararı sayımdan
(eşik, en az emsal) çıkar; tarama ile sözleşme sayfası aynı kararı verir; serbest metin birebir ve kelime benzerliğiyle
aranır; belge maddelere bölünür, madde madde eşlenir, sayı farkı ve şablon yer tutucusu ayrı işaretlenir; her rakamın
sorgu bilgisi vardır. Veri küçük ve uydurmadır; gerçek CRM kabulü test sunucusunda (scripts/acceptance/sozlesme-karsilastirma).
"""
from __future__ import annotations

import pytest

from semantic_bridge import access as A
from semantic_bridge import contracts_compare as CC
from semantic_bridge import contracts_compare_api as API
from semantic_bridge import contracts_compare_docs as CD
from semantic_bridge import provenance as P

COLS = (["id", "no", "ana", "statuscode", "bas", "bit", "kitap", "yazar"] + list(CC.DIMS.values()) + [c.key for c in CC.CLAUSES]
        + list(CC.META_COLS) + list(CC.EVENT_COLS))


def gid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


def row(n: int, *, ana: int | None = None, year: int = 2024, tip: int = 5, odeme: int = 2, para: int = 1, bolum: int = 1,
        **vals) -> list:
    base = {"id": gid(n), "no": f"S{n}", "ana": ("{" + gid(ana).upper() + "}") if ana else None, "statuscode": 100000000,
            "bas": f"{year}-01-15T00:00:00", "bit": None, "kitap": f"Kitap {n}", "yazar": f"Yazar {n}",
            "new_SozlesmeTipi": tip, "new_TelifTipi": odeme, "new_sozlesmeparabirimi": para, "new_ilgilidepartman": bolum,
            "kitapsay": 1, "ulkevar": 1}
    for c in CC.CLAUSES:
        base[c.key] = 1 if c.key in ("new_cogaltmahakki", "new_yaymahakki") else None
    base.update(vals)
    return [base.get(c) for c in COLS]


def data(rows: list[list], parties: dict | None = None, books: dict | None = None) -> dict:
    return {"books": books or {}, "bookOptions": {"1": "Yetişkin", "3": "Çocuk"}, "builtAt": "2026-09-29T00:00:00+00:00", "queries": {"portfoy": {"sql": "SELECT 1 FROM Timas_MSCRM.dbo.new_sozlesmeBase", "rows": len(rows), "ms": 5, "at": "2026-09-29T00:00:00+00:00"}},
            "columns": COLS, "rows": rows, "parties": parties or {},
            "labels": {"new_telif": "Karton K Telif %", "new_avanstutariyuzde": "avanstutarıyuzde"},
            "options": {"new_teliftipi": {"2": "Satıştan Ödeme", "3": "Tek Ödeme"}, "new_sozlesmetipi": {"5": "Telif Alış"},
                        "new_sozlesmeparabirimi": {"1": "TL", "2": "USD"}, "new_ilgilidepartman": {"1": "Kültür Editörya"},
                        "new_odemesekli": {"3": "Banka", "1": "Çek"}}}


RATES = {"2024-01": {"kur": 30.0, "gun": "2023-12-29", "kaynak": "TCMB döviz alış"},
         "2021-01": {"kur": 7.5, "gun": "2020-12-31", "kaynak": "TCMB döviz alış"}}


def portfolio(extra: list[list] | None = None, n: int = 40, rates: dict | None = None, **kw) -> CC.Portfolio:
    rows = [row(i, new_Telif=10, new_OdemeSekli=3, new_VadeAY=120, new_SozlesmeSuresiYil=5) for i in range(1, n + 1)]
    return CC.Portfolio(data(rows + (extra or []), **kw), RATES if rates is None else rates)


CFG = CC.Cfg(min_peers=20, rare=0.05, years=5)


def subj(port: CC.Portfolio, n: int) -> CC.Subject:
    return CC.Subject.of_entry(port.entry_of[gid(n)])


def clause(out: dict, key: str) -> dict:
    return next(c for g in out["groups"] for c in g["clauses"] if c["key"] == key)


# ------------------------------------------------------------------ değerler


def test_number_text_and_zero_is_empty():
    assert CC.parse_num_text("1.000") == (1000.0, None)
    assert CC.parse_num_text("2,5") == (2.5, None)
    assert CC.parse_num_text("0") == (None, None)
    assert CC.parse_num_text(" Limitsiz ") == (None, "Limitsiz")
    assert CC.norm_value(CC.BY_KEY["new_Telif"], 0) is None
    assert CC.norm_value(CC.BY_KEY["new_iletimhakki"], 0) is False


def test_crm_label_used_unless_it_looks_like_a_column_name():
    port = portfolio()
    assert port.labels["new_Telif"] == "Karton K Telif %"
    assert port.labels["new_avanstutariyuzde"] == "Avans yüzdesi"


# ------------------------------------------------------------------ sapma kararları


def test_high_rate_rare_value_and_missing_clause():
    port = portfolio([row(99, new_Telif=18, new_OdemeSekli=1, new_VadeAY=None)])
    out = CC.compare(port, subj(port, 99), CFG)
    assert clause(out, "new_Telif")["status"] == "yuksek"
    assert "0/40" in clause(out, "new_Telif")["reason"]
    assert clause(out, "new_OdemeSekli")["status"] == "nadir"
    assert clause(out, "new_VadeAY")["status"] == "eksik"
    assert clause(out, "new_iletimhakki")["status"] == "olagan"          # hepsinde yok: bu da yok
    assert out["criteria"]["emsal"] == 40 and out["criteria"]["gevsetilen"] == []


def test_ordinary_contract_has_no_deviation_and_scan_agrees_with_page():
    port = portfolio([row(99, new_Telif=18, new_OdemeSekli=1)])
    scan = {port.entries[r["e"]].id: {d["key"] for d in r["devs"]} for r in port.scan(CFG)["rows"]}
    for n in (1, 99):
        out = CC.compare(port, subj(port, n), CFG)
        page = {c["key"] for g in out["groups"] for c in g["clauses"] if c["status"] in CC.DEVIATING}
        assert scan[gid(n)] == page
    assert scan[gid(1)] == set()


def test_group_copies_count_once_and_are_not_own_peers():
    # 5 kitaplık grup sözleşmesi (aynı şartlar) + 25 tekil sözleşme: grup tek emsal sayılır
    group = [row(100 + i, ana=100, new_Telif=12) for i in range(5)]
    port = portfolio(group, n=25)
    assert len(port.entries) == 26
    out = CC.compare(port, subj(port, 102), CFG)
    assert out["criteria"]["emsal"] == 25
    assert all(p["id"] != gid(100) for p in out["peers"])


def test_agreement_is_represented_once_by_its_main_record():
    # ana kayıt %12, iki kopya %15: anlaşma emsal havuzunda bir kez ve ana kaydın değeriyle; farklı kopya kendi değeriyle incelenir
    group = [row(100, ana=100, new_Telif=12), row(101, ana=100, new_Telif=15), row(102, ana=100, new_Telif=15)]
    port = portfolio(group, n=25)
    assert len(port.entries) == 27 and len(port.reps) == 26
    assert port.rep_of[gid(100)].values["new_Telif"] == 12
    out = CC.compare(port, subj(port, 1), CFG)
    assert out["criteria"]["emsal"] == 25 and out["criteria"]["sozlesme"] == 27
    assert clause(CC.compare(port, subj(port, 101), CFG), "new_Telif")["value"] == 15


def test_small_group_relaxes_in_order_and_says_so():
    port = portfolio([row(99, bolum=2, new_Telif=10, new_OdemeSekli=3, new_VadeAY=120)])
    out = CC.compare(port, subj(port, 99), CFG)
    assert out["criteria"]["gevsetilen"] == ["Dönem", "İlgili bölüm"]
    assert out["criteria"]["emsal"] == 40


def test_rare_clause_and_too_few_values():
    port = portfolio([row(99, new_sozlesmeavanstutari=50000), row(200, new_sozlesmeavanstutari=10000)])
    c = clause(CC.compare(port, subj(port, 99), CFG), "new_sozlesmeavanstutari")
    assert c["status"] == "nadir-madde" and "1/41" in c["reason"]    # avans yalnız 1/41 emsalde var
    port = portfolio([row(99, new_sozlesmeavanstutari=50000)] + [row(200 + i, new_sozlesmeavanstutari=10000) for i in range(3)])
    c = clause(CC.compare(port, subj(port, 99), CFG), "new_sozlesmeavanstutari")
    assert c["status"] == "emsal-az"                                 # 3/43 dolu: madde nadir değil, karar için değer az


def test_amounts_only_compared_in_same_currency():
    usd = [row(300 + i, para=2, new_sozlesmeavanstutari=1000) for i in range(25)]
    port = portfolio(usd + [row(99, para=2, new_sozlesmeavanstutari=1000)])
    c = clause(CC.compare(port, subj(port, 99), CFG), "new_sozlesmeavanstutari")
    assert c["n"] == 25 and c["status"] == "olagan"


def test_future_start_year_and_fraction_rate_warnings():
    port = portfolio([row(99, year=2105, new_Telif=0.07)])
    w = CC.warnings_of(subj(port, 99))
    assert any("2105" in x for x in w) and any("kesir" in x for x in w)


# ------------------------------------------------------------------ serbest metin


def test_free_text_template_vs_unique():
    common = [row(400 + i, new_telifaciklamasi2="31 december, yıllık rapor günü") for i in range(6)]
    port = portfolio(common + [row(99, new_telifaciklamasi2="31 December yıllık rapor günü",
                                   new_haklaraciklama="Film hakkı yazarda saklıdır, dizi uyarlaması için ayrı izin alınır.")])
    texts = {t["key"]: t for t in CC.compare(port, subj(port, 99), CFG)["texts"]}
    assert texts["new_telifaciklamasi2"]["status"] == "kalip" and texts["new_telifaciklamasi2"]["birebir"] == 6
    assert texts["new_haklaraciklama"]["status"] == "ozgun" and texts["new_haklaraciklama"]["ornekler"] == []
    specials = next(r["specials"] for r in port.scan(CFG)["rows"] if port.entries[r["e"]].id == gid(99))
    assert specials == ["new_haklaraciklama"]


def test_near_duplicate_text_found_by_word_overlap():
    port = portfolio([row(500, new_not="Ödeme iş tesliminden sonraki ayın son haftası 6 taksit şeklinde yapılacaktır."),
                      row(99, new_not="Ödeme iş tesliminden sonraki ayın son haftası 6 taksit şeklinde yapılacaktır")])
    t = CC.compare(port, subj(port, 99), CFG)["texts"][0]
    assert t["birebir"] == 1 and t["status"] == "az"
    port2 = portfolio([row(500, new_not="Ödeme iş tesliminden sonraki ayın son haftası 6 taksit şeklinde yapılacaktır ayrıca"),
                       row(99, new_not="Ödeme iş tesliminden sonraki ayın son haftası 6 taksit şeklinde yapılacaktır")])
    t2 = CC.compare(port2, subj(port2, 99), CFG)["texts"][0]
    assert t2["benzer"] == 1 and t2["ornekler"][0]["benzerlik"] >= 0.8


# ------------------------------------------------------------------ aynı hak sahibi


def test_history_diffs_against_latest_earlier_contract_of_same_party():
    parties = {gid(600): [["p1", "Ayşe Yılmaz"]], gid(601): [["p1", "Ayşe Yılmaz"]], gid(99): [["p1", "Ayşe Yılmaz"]]}
    port = portfolio([row(600, year=2019, new_Telif=8), row(601, year=2022, new_Telif=10), row(99, year=2025, new_Telif=12)],
                     parties=parties)
    h = CC.history(port, subj(port, 99))
    assert h["taraflar"] == ["Ayşe Yılmaz"] and h["onceki"]["no"] == "S601"
    assert {"key": "new_Telif", "label": "Karton K Telif %", "old": "%10", "new": "%12"} in h["degisen"]
    assert [x["no"] for x in h["items"]] == ["S601", "S600"]


def test_portal_terms_compare_only_mapped_clauses():
    port = portfolio()
    terms = {"kind": "telif-alis", "paymentType": "satis", "currency": "TRY", "rates": {"karton": 18}, "advance": None,
             "start": "2026-02-01", "parties": [], "title": "Yeni", "rights": {"cogaltma": True}}
    s = CC.subject_from_terms("belge", "belge-x", "x.pdf", terms, only_present=True)
    out = CC.compare(port, s, CFG)
    keys = {c["key"] for g in out["groups"] for c in g["clauses"]}
    assert keys == {"new_Telif", "new_cogaltmahakki"}
    assert clause(out, "new_Telif")["status"] == "yuksek"
    assert "İlgili bölüm" in out["criteria"]["bilinmeyen"]


# ------------------------------------------------------------------ belge


DOC_A = """TELİF SÖZLEŞMESİ
Madde 1 - Taraflar
Timaş Yayınları ile yazar arasında yapılmıştır.
Madde 2 - Telif
Yayınevi net satış tutarı üzerinden %10 telif öder.
Madde 3 - Süre
Sözleşme 10 yıl geçerlidir.
Madde 4 - Film hakları
Film ve dizi uyarlama hakları yazarda kalır.
"""
DOC_B = """TELİF SÖZLEŞMESİ
Madde 1 - Taraflar
Timaş Yayınları ile yazar arasında yapılmıştır.
Madde 2 - Süre
Sözleşme 10 yıl geçerlidir.
Madde 3 - Telif
Yayınevi net satış tutarı üzerinden %12 telif öder.
Madde 4 - Uyuşmazlık
İstanbul mahkemeleri yetkilidir.
"""


def pages(text: str) -> list[dict]:
    return [{"sayfa": "1", "metin": text, "okuma": "metin"}]


def test_split_numbered_clauses_and_paragraph_fallback():
    cl = CD.split(pages(DOC_A))
    assert [c["no"] for c in cl] == [None, "1", "2", "3", "4"] and cl[2]["baslik"] == "Telif"
    para = CD.split(pages("Birinci paragraf.\n\nİkinci paragraf burada.\n"))
    assert [c["metin"] for c in para] == ["Birinci paragraf.", "İkinci paragraf burada."]


def test_diff_changed_number_moved_added_removed():
    d = CD.diff(CD.split(pages(DOC_A)), CD.split(pages(DOC_B)))
    by = {(r["a"] or {}).get("baslik") or (r["b"] or {}).get("baslik"): r for r in d["maddeler"]}
    assert by["Taraflar"]["durum"] == "ayni" and by["Süre"]["durum"] == "ayni"
    assert by["Telif"]["durum"] == "yeri-degismis" and by["Telif"]["sayilar"] == {"a": ["%10"], "b": ["%12"]}
    assert by["Film hakları"]["durum"] == "eklenmis" and by["Uyuşmazlık"]["durum"] == "cikarilmis"
    assert sum(d["sayim"].values()) == len(d["maddeler"])


def test_template_placeholders_are_fill_not_difference():
    tpl = CD.split(pages("Madde 1 - Telif\nYayınevi {{telif_esasi}} {{telif_karton}} telif öder.\nMadde 2 - Süre\nSüre {{sure_yil}} yıldır.\n"))
    doc = CD.split(pages("Madde 1 - Telif\nYayınevi net satış üzerinden %10 telif öder.\nMadde 2 - Süre\nSüre 5 yıldır.\n"))
    d = CD.diff(doc, tpl, b_is_template=True)
    ops = [o["op"] for r in d["maddeler"] for o in r.get("fark") or []]
    assert "fill" in ops and "del" not in ops
    assert d["sayim"] == {"ayni": 2, "degismis": 0, "yeri-degismis": 0, "eklenmis": 0, "cikarilmis": 0}


def test_corpus_marks_clause_missing_from_archive():
    a = CD.split(pages(DOC_A))
    res = CD.against_corpus(a, [({"ref": "b", "title": "B"}, CD.split(pages(DOC_B)))])
    by = {r["a"]["baslik"]: r["durum"] for r in res["maddeler"] if r["a"]["baslik"]}
    assert by["Taraflar"] == "ayni" and by["Film hakları"] == "arsivde-yok"


# ------------------------------------------------------------------ yetki ve sorgu bilgisi


def test_compare_endpoints_have_their_own_page():
    assert A.rule_for("/api/v1/editorial/contracts/compare/scan") == frozenset({A.page("sozlesme-karsilastirma")})
    assert A.rule_for("/api/v1/editorial/contracts/item/x") == frozenset({A.page("telif-sozlesme")})
    keys = A.all_keys()
    assert "sayfa:sozlesme-karsilastirma" in keys and API.UPLOAD in keys


def test_every_number_on_scan_and_contract_has_a_source():
    port = portfolio([row(99, new_Telif=18, new_OdemeSekli=1, new_not="Özel madde metni burada duruyor.")])
    scan = CC.scan_page(port, CFG, only="hepsi")
    scan["ayar"] = {"yil": 5}
    scan = P.ekle(scan, API.kaynak_scan(port, "Timas_MSCRM.dbo."))
    assert P.uncovered_numbers(scan, API.NOT_RAKAM) == [] and P.problems(scan) == []
    s = subj(port, 99)
    out = CC.compare(port, s, CFG)
    out.update({"subject": CC.subject_head(port, s), "history": CC.history(port, s), "ayar": {"yil": 5, "emsal": 20}})
    out = P.ekle(out, API.kaynak_contract(port, "Timas_MSCRM.dbo."))
    assert P.uncovered_numbers(out, API.NOT_RAKAM) == [] and P.problems(out) == []


# ------------------------------------------------------------------ Faz 1: kur, şekil, inceleme, taslak, liste


def test_tl_amounts_are_compared_in_dollars_at_start_month():
    # 2021'de 30.000 TL (7,5 → 4.000 USD) ile 2024'te 120.000 TL (30 → 4.000 USD) aynı gerçek tutar
    old = [row(700 + i, year=2021, new_sozlesmeavanstutari=30000) for i in range(30)]
    port = portfolio(old + [row(99, year=2024, new_sozlesmeavanstutari=120000)], n=0)
    c = clause(CC.compare(port, subj(port, 99), CC.Cfg(min_peers=20, rare=0.05, years=5)), "new_sozlesmeavanstutari")
    assert c["status"] == "olagan" and c["kiyas"] == 4000.0 and c["medyan"] == 4000.0
    assert "≈ 4.000 USD (Ocak 2024 kuru 30)" in c["valueLabel"] and c["medyanAd"].endswith("USD")


def test_missing_rate_is_not_judged():
    old = [row(700 + i, new_sozlesmeavanstutari=30000) for i in range(30)]
    port = portfolio(old + [row(99, year=2023, new_sozlesmeavanstutari=120000)], n=0)
    out = CC.compare(port, subj(port, 99), CC.Cfg(min_peers=20, rare=0.05, years=5))
    c = clause(out, "new_sozlesmeavanstutari")
    assert c["status"] == "kur-yok" and "kuru okunamadı" in c["valueLabel"]


def test_rates_fill_from_tcmb_file_and_old_lira_is_scaled(tmp_path):
    xml = ('<Tarih_Date><Currency CrossOrder="0" Kod="USD" CurrencyCode="USD"><Unit>1</Unit>'
           '<ForexBuying>{}</ForexBuying></Currency></Tarih_Date>')
    seen = []

    def fetch(url):
        seen.append(url)
        if "200301" in url:   # 2016 öncesi biçim: öznitelik sırası farklı, eski lira
            return 200, ('<Tarih_Date><Currency CrossOrder="0" CurrencyCode="USD" Kod="USD"><Unit>1</Unit>'
                         '<ForexBuying>1650000</ForexBuying></Currency></Tarih_Date>')
        if "01012024" in url or "31122023" in url:
            return 200, xml.format("29.8")
        return 404, ""

    r = CC.Rates(lambda: str(tmp_path), fetch)
    assert r.fill("t1", ["2003-01", "2024-01"]) == 2
    got = r.load("t1")
    assert got["2003-01"]["kur"] == 1.65 and got["2024-01"]["kur"] == 29.8
    assert r.missing("t1", {"2003-01", "2024-01", "2025-05"}) == ["2025-05"]


def test_formal_checks_follow_contract_type():
    parties = {gid(99): [["p1", "A"]], gid(98): [["p2", "B"]]}
    port = portfolio([row(99, new_SozlesmeSuresiYil=5, kitapsay=1, new_Telif=10),
                      row(98, kitapsay=0, new_cogaltmahakki=0, new_yaymahakki=0),
                      row(97, tip=1, new_SozlesmeSuresiYil=5, kitapsay=1, new_Telif=10, ulkevar=0)], parties=parties)
    ok = {x["id"]: x["ok"] for x in CC.formal(port, subj(port, 99))}
    assert ok == {"hak": True, "sure": True, "baslangic": True, "tarih": True, "taraf": True, "kitap": True, "ucret": True}
    bad = {x["id"]: x["ok"] for x in CC.formal(port, subj(port, 98))}
    assert not bad["hak"] and not bad["sure"] and not bad["kitap"] and not bad["ucret"] and bad["taraf"]
    sat = {x["id"]: x["ok"] for x in CC.formal(port, subj(port, 97))}
    assert "hak" not in sat and sat["ulke"] is False and sat["taraf"] is False
    row_ = next(r for r in port.scan(CFG)["rows"] if port.entries[r["e"]].id == gid(98))
    assert set(row_["sekil"]) == {"hak", "sure", "kitap", "ucret"}
    page = CC.scan_page(port, CFG, only="sekil")
    assert {i["id"] for i in page["items"]} >= {gid(98), gid(97)} and page["ozet"]["sekil"] >= 2


def test_review_closes_finding_until_value_changes():
    from semantic_bridge import contracts_compare_store as ST

    port = portfolio([row(99, new_Telif=18, new_OdemeSekli=3, new_VadeAY=120, new_SozlesmeSuresiYil=5)],
                     parties={gid(99): [["p1", "A"]]})
    e = port.entry_of[gid(99)]
    review = {"status": "istisna", "statusLabel": "", "closed": True, "valueSig": ST.sig(18.0), "note": "çok satan yazar"}
    rows = CC.scan_rows(port, CFG, reviews={(e.agreement, "new_Telif"): review}, unreviewed=True)
    assert gid(99) not in {x[1].id for x in rows}
    stale = dict(review, valueSig=ST.sig(15.0))
    rows = CC.scan_rows(port, CFG, reviews={(e.agreement, "new_Telif"): stale}, unreviewed=True)
    it = CC.scan_item(port, *next(x for x in rows if x[1].id == gid(99)))
    assert it["sapmalar"][0]["inceleme"]["stale"] is True and it["acikBulgu"] == 1


def test_review_store_validates(tmp_path):
    import sqlalchemy as sa
    from semantic_bridge import contracts_compare_store as ST

    eng = sa.create_engine(f"sqlite:///{tmp_path}/r.db")
    with pytest.raises(ST.StoreError):
        ST.save_review(eng, "t", "u", agreement="a", clause="new_Telif", value_sig="1", status="yok")
    with pytest.raises(ST.StoreError):
        ST.save_review(eng, "t", "u", agreement="a", clause="new_Telif", value_sig="1", status="hukuk")
    out = ST.save_review(eng, "t", "u", agreement="a", clause="new_Telif", value_sig="1", status="hukuk", owner="hukuk birimi")
    out = ST.save_review(eng, "t", "v", agreement="a", clause="new_Telif", value_sig="1", status="uygun", note="tamam")
    assert out["status"] == "uygun" and out["by"] == "v" and len(ST.reviews(eng, "t")) == 1
    ST.delete_review(eng, "t", "a", "new_Telif")
    assert ST.reviews(eng, "t") == {}


def test_csv_has_every_filtered_row():
    port = portfolio([row(99, new_Telif=18), row(98, new_Telif=19)])
    text = CC.scan_csv(port, CFG, only="sapan")
    lines = [l for l in text.lstrip("\ufeff").splitlines() if l]
    assert lines[0].startswith("Sözleşme no;") and len(lines) == 1 + len(CC.scan_rows(port, CFG, only="sapan"))


def test_draft_terms_are_checked_without_saving():
    port = portfolio()
    terms = {"kind": "telif-alis", "paymentType": "satis", "currency": "TRY", "rates": {"karton": 18}, "start": "2026-02-01",
             "parties": [{"name": "Yeni Yazar"}], "books": [], "title": "Taslak", "rights": {}, "years": None,
             "openEnded": False, "advance": None}
    s = CC.subject_from_terms("taslak", "taslak", "Taslak", terms)
    out = CC.compare(port, s, CFG)
    assert clause(out, "new_Telif")["status"] == "yuksek"
    fails = {x["id"] for x in out["sekil"] if not x["ok"]}
    assert {"hak", "sure", "kitap"} <= fails


# ------------------------------------------------------------------ Faz 2: ticari ölçütler, satış dilimi, olaylar


def test_extra_dims_narrow_peers_and_relax_first():
    books = {gid(i): [[f"K{i}", 3 if i <= 25 else 1, "Masal" if i <= 25 else "Roman", "Türkçe"]] for i in range(1, 41)}
    books[gid(99)] = [["K99", 3, "Masal,Öykü", "İngilizce"]]
    parties = {gid(i): [[f"p{i}", f"Y{i}", 1 if i <= 22 else 0]] for i in range(1, 41)}
    parties[gid(99)] = [["p99", "Ajans", 1]]
    port = portfolio([row(99)], parties=parties, books=books)
    e = port.entry_of[gid(99)]
    assert e.dims["hedef"] == 3 and e.dims["tur"] == "Masal" and e.dims["dil"] == "ceviri" and e.dims["ajans"] == 1
    cfg = CC.Cfg(min_peers=20, rare=0.05, years=5, dims=("ajans", "hedef"))
    crit = CC.compare(port, subj(port, 99), cfg)["criteria"]
    assert crit["emsal"] == 22 and [b["id"] for b in crit["boyutlar"]][-2:] == ["ajans", "hedef"]
    cfg2 = CC.Cfg(min_peers=20, rare=0.05, years=5, dims=("ajans", "dil"))       # yerli emsal yok → önce dil gevşer
    crit2 = CC.compare(port, subj(port, 99), cfg2)["criteria"]
    assert crit2["gevsetilen"][0] == "Yerli / çeviri" and crit2["emsal"] == 22


def test_sales_tiers_from_last_36_months():
    part = {"data": {"dataEnd": "2026-06-30", "years": {
        "2026": {"rows": {"K1": [[6, 0, 100, 0], [6, 1, -10, 0]], "K2": [[1, 0, 5, 0]]}},
        "2023": {"rows": {"K1": [[6, 0, 999, 0]], "K3": [[7, 0, 50, 0]]}}}}}
    got = CC.sales_last_months(part)
    assert got == {"K1": 90.0, "K2": 5.0, "K3": 50.0}                         # 2023-06 36 ayın dışında, 2023-07 içinde
    assert CC.sales_last_months({"data": {}}) is None
    books = {gid(i): [[f"K{i}", 1, None, None]] for i in range(1, 11)}
    parties = {gid(i): [[f"p{i}", f"Y{i}", 0]] for i in range(1, 11)}
    port = CC.Portfolio(data([row(i) for i in range(1, 11)], parties=parties, books=books), RATES,
                        {f"K{i}": float(i * 10) for i in range(1, 10)})
    tiers = {i: port.entry_of[gid(i)].dims["satis"] for i in range(1, 11)}
    assert tiers[9] == "ust" and tiers[1] == "alt" and tiers[10] == "yok" and tiers[5] == "orta"


def test_timeline_lists_events_of_all_copies():
    r1 = row(100, ana=100, new_ekprotokoltarihi="2025-03-01T00:00:00", new_fesihtarihi="2026-01-10T00:00:00")
    r2 = row(101, ana=100, new_Telif=12)
    port = portfolio([r1, r2])
    ev = CC.timeline(port, subj(port, 101))
    assert [x["olay"] for x in ev] == ["Başlangıç", "Ek protokol", "Fesih"]


# ------------------------------------------------------------------ Faz 3: pozisyon, madde türü, eşleşme, maske, rapor


def pos(pid, clause, op, value=None, level="kirmizi", state="onayli", **scope):
    return {"id": pid, "clause": clause, "op": op, "value": value, "level": level, "levelLabel": level, "state": state,
            "scope": {"tip": scope.get("tip"), "odeme": scope.get("odeme"), "para": scope.get("para")}, "reason": None}


def test_position_rules_and_scope():
    port = portfolio([row(99, new_Telif=18, new_iletimhakki=0, new_OdemeSekli=1)])
    s = subj(port, 99)
    rules = [pos(1, "new_Telif", "max", 15), pos(2, "new_Telif", "min", 5), pos(3, "new_iletimhakki", "zorunlu"),
             pos(4, "new_OdemeSekli", "in", [3, 5]), pos(5, "new_Telif", "max", 10, tip=1), pos(6, "new_Telif", "max", 1, state="oneri")]
    got = {x["id"]: x["ok"] for x in CC.positions_for(port, s, rules)}
    assert got == {1: False, 2: True, 3: False, 4: False}                  # 5 kapsam dışı, 6 onaysız
    rows = CC.scan_rows(port, CFG, only="pozisyon", rules=rules)
    assert gid(99) in {e.id for _, e, _ in rows}
    it = CC.scan_item(port, *next(x for x in rows if x[1].id == gid(99)))
    assert {p["id"] for p in it["pozisyon"]} == {1, 3, 4}


def test_suggestions_come_from_peers():
    port = portfolio()
    props = CC.suggest_positions(port, 5, 2, CFG)
    by = {(p["clause"], p["op"]): p for p in props}
    assert by[("new_Telif", "min")]["value"] == 10 and by[("new_Telif", "max")]["value"] == 10
    assert ("new_cogaltmahakki", "zorunlu") in by and ("new_OdemeSekli", "eq") in by
    assert not any(p["clause"] == "new_sozlesmeavanstutari" for p in props)
    with pytest.raises(CC.CompareError):
        CC.suggest_positions(portfolio(n=5), 5, 2, CFG)


def test_position_store_roundtrip(tmp_path):
    import sqlalchemy as sa
    from semantic_bridge import contracts_compare_store as ST

    eng = sa.create_engine(f"sqlite:///{tmp_path}/p.db")
    with pytest.raises(ST.StoreError):
        ST.save_position(eng, "t", "u", {"clause": "yok", "op": "min", "value": 1}, CC.valid_position_clause)
    p = ST.save_position(eng, "t", "u", {"clause": "new_Telif", "op": "max", "value": "15,5", "scope": {"tip": 5}},
                         CC.valid_position_clause, state="oneri")
    assert p["state"] == "oneri" and p["value"] == 15.5 and p["scope"]["tip"] == 5
    assert ST.approve_position(eng, "t", "hukuk", p["id"])["state"] == "onayli"
    t = ST.save_position(eng, "t", "u", {"clause": "tur:fesih", "op": "zorunlu"}, CC.valid_position_clause)
    assert t["clause"] == "tur:fesih" and len(ST.positions(eng, "t", "onayli")) == 2
    ST.delete_position(eng, "t", t["id"])
    assert len(ST.positions(eng, "t")) == 1


def test_clause_types_rule_then_model():
    cl = CD.split(pages("Madde 1 - Taraflar\nYayınevi ile yazar arasında yapılmıştır.\n"
                        "Madde 2 - Fesih\nTaraflardan biri ihlal halinde sözleşmeyi feshedebilir.\n"
                        "Madde 3 - Diğer\nTaraflar bu konuda karşılıklı olarak görüşmeyi kabul eder ve iyi niyetle davranır.\n"))

    class Ch:
        def __init__(self, choice, p):
            self.choice, self.probability = choice, p

        def confident(self, a, b):
            return self.probability >= a

    asked = []

    def choose(prompt, labels):
        asked.append(prompt)
        return Ch("Uyuşmazlık ve yetkili mahkeme", 0.9)

    n = CD.classify(cl, choose, mask=lambda t: t.replace("yazar", "[AD]"))
    by = {c["no"]: c for c in cl}
    assert by["1"]["tur"] == "taraflar" and by["1"]["turKaynak"] == "kural"
    assert by["2"]["tur"] == "fesih" and by["3"]["turKaynak"] == "zeki" and n["zeki"] == 1
    assert all("[AD]" in p or "yazar" not in p for p in asked)
    low = CD.split(pages("Madde 1 - Diğer\nTaraflar bu konuda karşılıklı olarak görüşmeyi kabul eder.\n"))
    CD.classify(low, lambda p, l: Ch("Fesih", 0.4))
    assert low[0]["tur"] is None                                           # eşik altı: tür yazılmaz


def test_missing_clause_types_against_archive():
    a = CD.split(pages("Madde 1 - Taraflar\nA ile B arasında.\nMadde 2 - Telif\nTelif oranı %10.\n"))
    b = CD.split(pages("Madde 1 - Taraflar\nA ile B arasında.\nMadde 2 - Fesih\nİhlal halinde feshedilir.\n"))
    CD.classify(a)
    CD.classify(b)
    res = CD.against_corpus(a, [({"ref": "b", "title": "B"}, b)])
    assert [x["tur"] for x in res["eksikTurler"]] == ["fesih"]
    d = CD.diff(a, b)
    assert d["turler"]["yalnizB"] == ["fesih"]


def test_contract_number_found_in_name_or_text():
    known = {"2018000102-1", "2024007074"}.__contains__
    assert CD.find_contract_no("2018000102-1.pdf", "", known) == "2018000102-1"
    assert CD.find_contract_no("tarama.pdf", "Sözleşme No: 2024007074 tarihli", known) == "2024007074"
    assert CD.find_contract_no("2018000102.pdf", "", known) == "2018000102-1"
    assert CD.find_contract_no("x.pdf", "2099000001", known) is None


def test_masking_hides_personal_data():
    cl = [{"no": "1", "baslik": "Taraflar", "metin": "Ayşe Yılmaz, T.C. Kimlik No: 12345678901, e-posta ayse@ornek.com", "_t": ["x"]}]
    out = CD.mask_clauses(cl, ["Ayşe Yılmaz"])
    assert "12345678901" not in out[0]["metin"] and "ayse@ornek.com" not in out[0]["metin"] and "Ayşe Yılmaz" not in out[0]["metin"]
    assert "_t" not in out[0] and cl[0]["metin"].startswith("Ayşe")


def test_upload_retention(tmp_path, monkeypatch):
    import sqlalchemy as sa
    from datetime import timedelta

    monkeypatch.setenv("CONTRACT_DOCS_DIR", str(tmp_path))
    eng = sa.create_engine(f"sqlite:///{tmp_path}/d.db")
    row_ = CD.upload(eng, "t", "u", "a.txt", "Madde 1 - Konu\nDeneme.".encode())
    assert CD.purge_uploads(eng, "t", 0) == [] and CD.purge_uploads(eng, "t", 30) == []
    with eng.begin() as c:
        c.execute(sa.update(CD.DOCS).values(created_at=CD._now() - timedelta(days=40), status="hazir"))
    gone = CD.purge_uploads(eng, "t", 30)
    assert [g["ref"] for g in gone] == [row_["ref"]] and not list(tmp_path.glob("t/karsilastirma/*"))


def test_word_reports_open_and_carry_text():
    import io
    import zipfile
    from semantic_bridge import contracts_compare_report as RP

    port = portfolio([row(99, new_Telif=18, new_OdemeSekli=1)])
    s = subj(port, 99)
    out = CC.compare(port, s, CFG)
    out.update({"subject": CC.subject_head(port, s), "history": CC.history(port, s), "gorunum": {"okunduAn": "x"},
                "pozisyon": CC.positions_for(port, s, [pos(1, "new_Telif", "max", 15)])})
    xml = zipfile.ZipFile(io.BytesIO(RP.contract_docx(out))).read("word/document.xml").decode()
    assert "S99" in xml and "Karton K Telif %" in xml and "Emsalden yüksek" in xml and "en çok %15" in xml
    d = CD.diff(CD.split(pages(DOC_A)), CD.split(pages(DOC_B)))
    d.update({"a": {"title": "A"}, "b": {"title": "B"}})
    xml2 = zipfile.ZipFile(io.BytesIO(RP.diff_docx(d))).read("word/document.xml").decode()
    assert "<w:strike/>" in xml2 and "Film hakları" in xml2 and "Yalnız incelenen belgede" in xml2
