"""Sözleşme karşılaştırma (`semantic_bridge.contracts_compare`, `contracts_compare_docs`, `contracts_compare_api`).

Sözleşme: kıyas grubu aynı tip/ödeme türü/para birimi/bölüm ve dönemdir, küçükse ölçütler sırayla gevşer ve yazılır;
grup sözleşmesinin aynı şartlı kopyaları tek sayılır ve sözleşme kendi anlaşmasıyla kıyaslanmaz; sapma kararı sayımdan
(eşik, en az emsal) çıkar; tarama ile sözleşme sayfası aynı kararı verir; serbest metin birebir ve kelime benzerliğiyle
aranır; belge maddelere bölünür, madde madde eşlenir, sayı farkı ve şablon yer tutucusu ayrı işaretlenir; her rakamın
sorgu bilgisi vardır. Veri küçük ve uydurmadır; gerçek CRM kabulü test sunucusunda (scripts/acceptance/sozlesme-karsilastirma).
"""
from __future__ import annotations

from semantic_bridge import access as A
from semantic_bridge import contracts_compare as CC
from semantic_bridge import contracts_compare_api as API
from semantic_bridge import contracts_compare_docs as CD
from semantic_bridge import provenance as P

COLS = ["id", "no", "ana", "statuscode", "bas", "bit", "kitap", "yazar"] + list(CC.DIMS.values()) + [c.key for c in CC.CLAUSES]


def gid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


def row(n: int, *, ana: int | None = None, year: int = 2024, tip: int = 5, odeme: int = 2, para: int = 1, bolum: int = 1,
        **vals) -> list:
    base = {"id": gid(n), "no": f"S{n}", "ana": ("{" + gid(ana).upper() + "}") if ana else None, "statuscode": 100000000,
            "bas": f"{year}-01-15T00:00:00", "bit": None, "kitap": f"Kitap {n}", "yazar": f"Yazar {n}",
            "new_SozlesmeTipi": tip, "new_TelifTipi": odeme, "new_sozlesmeparabirimi": para, "new_ilgilidepartman": bolum}
    for c in CC.CLAUSES:
        base[c.key] = 1 if c.key in ("new_cogaltmahakki", "new_yaymahakki") else None
    base.update(vals)
    return [base.get(c) for c in COLS]


def data(rows: list[list], parties: dict | None = None) -> dict:
    return {"builtAt": "2026-09-29T00:00:00+00:00", "queries": {"portfoy": {"sql": "SELECT 1 FROM Timas_MSCRM.dbo.new_sozlesmeBase", "rows": len(rows), "ms": 5, "at": "2026-09-29T00:00:00+00:00"}},
            "columns": COLS, "rows": rows, "parties": parties or {},
            "labels": {"new_telif": "Karton K Telif %", "new_avanstutariyuzde": "avanstutarıyuzde"},
            "options": {"new_teliftipi": {"2": "Satıştan Ödeme", "3": "Tek Ödeme"}, "new_sozlesmetipi": {"5": "Telif Alış"},
                        "new_sozlesmeparabirimi": {"1": "TL", "2": "USD"}, "new_ilgilidepartman": {"1": "Kültür Editörya"},
                        "new_odemesekli": {"3": "Banka", "1": "Çek"}}}


def portfolio(extra: list[list] | None = None, n: int = 40, **kw) -> CC.Portfolio:
    rows = [row(i, new_Telif=10, new_OdemeSekli=3, new_VadeAY=120) for i in range(1, n + 1)]
    return CC.Portfolio(data(rows + (extra or []), **kw))


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
