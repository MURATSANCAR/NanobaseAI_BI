"""M9 veri katmanı: kopya seçimi, görüntü kurulumu (sahte sorgu çalıştırıcısıyla), emsal, öneri girdileri,
gerçekleşen marj, backlist revizyonu, hesap ucu."""

from __future__ import annotations

import pytest

from semantic_bridge import pricing as P
from semantic_bridge.pricing import data as D
from semantic_bridge.pricing import sources as SRC


def _fake_run(copies=(("211", "2021-01-02", "2025-12-31", 500000), ("411", "2026-01-01", "2026-08-17", 81000),
                      ("201", "2020-01-01", "2020-12-31", 50000))):
    seen = []

    def run(conn, sql):
        seen.append((conn, sql))
        if "sys.tables" in sql:
            return [{"firma": f} for f, *_ in copies]
        if "MIN(DATE_)" in sql:
            f = sql.split("LG_")[1][:3]
            c = next(x for x in copies if x[0] == f)
            return [{"ilk": c[1], "son": c[2], "fatura": c[3]}]
        if "Komple Bask" in sql:
            if "LG_411" in sql:
                return [{"kod": "15201.01.1", "tarih": "2026-05-01", "fatura": "F1", "matbaa": "A", "adet": 3000, "tutar": 30000},
                        {"kod": "15201.01.2", "tarih": "2026-06-01", "fatura": "F2", "matbaa": "B", "adet": 1000, "tutar": 16000},
                        {"kod": "15201.01.3", "tarih": "2026-07-01", "fatura": "F3", "matbaa": "A", "adet": 5000, "tutar": 40000}]
            return [{"kod": "15201.01.1", "tarih": "2023-03-01", "fatura": "E1", "matbaa": "A", "adet": 2000, "tutar": 10000}]
        if "SUM(CASE WHEN S.TRCODE IN (7, 8, 9) THEN S.AMOUNT ELSE -S.AMOUNT END)" in sql:
            y = 2026 if "LG_411" in sql else 2025
            return [{"kod": "15201.01.1", "yil": y, "adet": 1000, "net": 100000, "brut": 180000, "maliyet": 15000,
                     "maliyetli_adet": 1000, "satis_adet": 1000}]
        if "SPECODE2" in sql:
            return [{"kanal": "KİTABEVİ", "brut": 1000, "net": 550, "adet": 10, "satir": 5},
                    {"kanal": "E-TİCARET", "brut": 1000, "net": 600, "adet": 10, "satir": 5}]
        if "Satış Nakliye" in sql:
            return [{"tutar": 23, "satir": 2}]
        if "15001%" in sql:
            return [{"kod": "15001.060.057082.3H", "ad": "57X82  3.HAMUR 60 GR KAĞIT", "miktar": 1000, "tutar": 48000, "satir": 3, "son": "2026-08-01"},
                    {"kod": "15001.230.070100.BR", "ad": "70X100  BRİSTOL 230 GR KAĞIT", "miktar": 100, "tutar": 3000, "satir": 1, "son": "2026-07-01"},
                    {"kod": "15001.000.000001.BD", "ad": "BANDROL", "miktar": 10000, "tutar": 3000, "satir": 1, "son": "2026-07-01"}]
        if "StringMap" in sql:
            return [{"varlik": "new_Uretim", "alan": "new_ciltlemesekli", "deger": 1, "ad": "Amerikan Cilt"},
                    {"varlik": "new_sozlesme", "alan": "new_teliftipi", "deger": 2, "ad": "Satıştan Ödeme"},
                    {"varlik": "new_sozlesme", "alan": "new_telifturu", "deger": 1, "ad": "Brüt"}]
        if "ROUND(S.PRICE, 2)" in sql:     # logo_fiyat: kitap × ay × fiyat satır sayısı
            if "LG_411" in sql:
                return [{"kod": "15201.01.1", "ay": 202601, "fiyat": 180, "satir": 5, "ilk": "2026-01-05"},
                        {"kod": "15201.01.1", "ay": 202603, "fiyat": 200, "satir": 9, "ilk": "2026-03-10"},
                        {"kod": "15201.01.1", "ay": 202603, "fiyat": 180, "satir": 2, "ilk": "2026-03-01"},
                        # Müşteriye özel indirimli fiyat ayın çoğunluğu olsa da liste fiyatı (200) değişmez.
                        {"kod": "15201.01.1", "ay": 202605, "fiyat": 140, "satir": 15, "ilk": "2026-05-02"},
                        {"kod": "15201.01.1", "ay": 202605, "fiyat": 200, "satir": 13, "ilk": "2026-05-01"},
                        {"kod": "15201.01.1", "ay": 202607, "fiyat": 200, "satir": 4, "ilk": "2026-07-02"},
                        {"kod": "15201.01.1", "ay": 202607, "fiyat": 260, "satir": 1, "ilk": "2026-07-09"}]
            return [{"kod": "15201.01.1", "ay": 202512, "fiyat": 180, "satir": 7, "ilk": "2025-12-01"},
                    {"kod": "15201.01.2", "ay": 202512, "fiyat": 250, "satir": 3, "ilk": "2025-12-03"}]
        if "new_sozlemetipiBase" in sql:
            return [{"kitap": "AAA", "id": "S1", "ad": "2020-1", "tur": "Metin (Eser Sözleşmesi)", "karton": 7, "sert": None,
                     "tek_odeme": None, "olusturma": "2020-01-01"},
                    {"kitap": "AAA", "id": "S2", "ad": "2023-1", "tur": "Metin (Eser Sözleşmesi)", "karton": 8, "sert": 5,
                     "tek_odeme": None, "olusturma": "2023-01-01"},
                    {"kitap": "aaa", "id": "S3", "ad": "2024-1", "tur": "Tercüme", "karton": None, "sert": None,
                     "tek_odeme": 440, "olusturma": "2024-01-01"}]
        if "new_kitapBase" in sql:
            return [{"id": "AAA", "ad": "Bir", "kod": "15201.01.1", "sayfa": 200, "ebat": "13,5x21", "fiyat": 200, "kdv": 0,
                     "telif": 10, "telif_turu": 1, "telif_tipi": 2, "avans": 5000, "avans_para": 1, "stok": 1610,
                     "son_baski": "2026-04-30T21:00:00", "son_baski_adet": 3000, "kapak_cilt": "Amerikan Cilt, Kuşe Kapak"},
                    {"id": "BBB", "ad": "İki", "kod": "15201.01.2", "sayfa": 210, "ebat": "13,5x21", "fiyat": 250, "kdv": 0},
                    {"id": "CCC", "ad": "Üç", "kod": "15201.01.3", "sayfa": 190, "ebat": "13,5x21", "fiyat": 220, "kdv": 0}]
        if "new_UretimBase" in sql:
            return [{"kod": "15201.01.1", "baski_no": 2, "yil": 2026, "tarih": "2026-05-01", "adet": 3000, "fiyat": 200,
                     "sayfa": 200, "cilt": 1, "gramaj": 60, "renk": 1},
                    {"kod": "15201.01.2", "baski_no": 1, "yil": 2026, "tarih": "2026-06-01", "adet": 1000, "fiyat": 250,
                     "sayfa": 210, "cilt": 1, "gramaj": 60, "renk": 1},
                    {"kod": "15201.01.3", "baski_no": 1, "yil": 2026, "tarih": "2026-07-01", "adet": 5000, "fiyat": 220,
                     "sayfa": 190, "cilt": 1, "gramaj": 60, "renk": 1}]
        raise AssertionError(sql[:80])
    return run, seen


@pytest.fixture
def snap():
    run, _ = _fake_run()
    return D.Builder(run).build()


def test_copies_skip_old_and_bound_dates():
    run, seen = _fake_run()
    b = D.Builder(run)
    copies = b.copies()
    assert [c["firm"] for c in copies] == ["211", "411"]
    assert copies[0]["from"] == "2021-01-02" and copies[0]["to"] == "2026-01-01" and copies[1]["to"] == "2026-08-18"


def test_overlapping_copies_keep_bigger():
    run, _ = _fake_run((("105", "2021-01-01", "2021-12-31", 10), ("115", "2021-01-01", "2021-12-31", 20)))
    b = D.Builder(run)
    assert [c["firm"] for c in b.copies()] == ["115"] and b.warnings


def test_other_companies_copies_are_not_measured(monkeypatch):
    """Canlı Logo'da başka şirketin 2026'sı (413) ve test firması (999) da INVOICE taşır; fatura sayısı fazla diye
    seçilmemeli, hatta ölçülmemeli. Hariç tutulan kopya yılı (015) de okunmaz."""
    monkeypatch.setenv("SEMANTIC_FIRMS", "015,016,105,115,171,181,191,201,211,411")
    monkeypatch.delenv("SEMANTIC_EXCLUDE_CONTEXT", raising=False)
    run = _fake_run((("211", "2021-01-02", "2025-12-31", 500000), ("411", "2026-01-01", "2026-08-17", 81000),
                        ("413", "2026-01-01", "2026-09-28", 900000), ("999", "2026-01-01", "2026-09-28", 5),
                        ("015", "2021-01-01", "2021-12-31", 999999)))
    run, seen = run
    b = D.Builder(run)
    assert [c["firm"] for c in b.copies()] == ["211", "411"] and not b.warnings
    assert not any(f in sql for _, sql in seen for f in ("LG_413_", "LG_999_", "LG_015_"))


def test_build_snapshot(snap):
    assert snap["dataEnd"] == "2026-08-17"
    assert [p["unit"] for p in snap["prints"]["15201.01.1"]] == [5.0, 10.0]   # tarih sırası
    assert snap["sales"]["15201.01.1"]["2026"]["net"] == 100000
    ch = {c["channel"]: c for c in snap["channels"]}
    assert ch["KİTABEVİ"]["discount"] == pytest.approx(0.45) and ch["E-TİCARET"]["share"] == pytest.approx(600 / 1150, abs=1e-4)
    assert snap["distribution"]["rate"] == pytest.approx(23 / 1150, abs=1e-4)
    assert snap["paper"]["innerByGsm"]["60"] == 48.0 and snap["paper"]["coverPerKg"] == 30.0
    assert snap["paper"]["bandrol"]["unit"] == pytest.approx(0.3)
    roy = snap["books"]["15201.01.1"]["royalty"]
    assert roy["rate"] == 0.10 and roy["basis"] == "kapak" and roy["on"] == "satis" and roy["advance"] == 5000
    assert snap["crmPrints"]["15201.01.1"][0]["binding"] == "Amerikan Cilt"
    # Satırlar her kopyadan kendi tarih aralığıyla okunur.
    assert any("'20260101'" in s or "'20210102'" in s for s in snap["sql"]["logo_baski"])


def test_parse_trim_and_paper(snap):
    assert D.parse_trim("13,5x21") == (13.5, 21.0)
    assert D.parse_trim("13,5*19,5") == (13.5, 19.5)
    assert D.parse_trim("yok") is None
    pc = D.paper_cost(snap, 200, (13.5, 21.0), 60)
    kg = 100 * 0.02835 * 60 / 1000 * 1.1
    assert pc["innerKg"] == pytest.approx(kg, abs=1e-5)
    assert pc["parts"]["inner"] == pytest.approx(kg * 48, abs=1e-3)
    assert pc["parts"]["bandrol"] == pytest.approx(0.3) and not pc["missing"]


def test_comparables_and_suggestion(snap):
    comp = D.comparables(snap, 200, "Amerikan Cilt", exclude="15201.01.1")
    assert {r["code"] for r in comp["rows"]} == {"15201.01.2", "15201.01.3"}
    assert comp["price"]["median"] == 235
    none = D.comparables(snap, 400)
    assert none["count"] == 0
    sug = D.suggested_inputs(snap, {"code": "15201.01.1", "pages": 200, "trim": "13,5x21", "gsm": 60,
                                    "binding": "Amerikan Cilt"}, {"channelMix": None, "sellThrough": 1, "targetMargin": 0.15,
                                                                  "variableRate": 0.05})
    assert sug["royaltyRate"] == 0.10 and sug["advance"] == 5000
    assert sug["discount"] == pytest.approx(1 - 1150 / 2000)
    # İki emsal baskı eğri kurmaya yetmez (en az üç nokta): baskı hizmeti boş, yalnız kâğıt önerilir.
    assert sug["printService"] is None and sug["printPerCopy"] == pytest.approx(sug["paper"]["perCopy"])


def test_actuals_and_old_book_compare(snap):
    act = D.actuals(snap)
    one = next(r for r in act["rows"] if r["code"] == "15201.01.1")
    assert one["printed"] == 5000 and one["printCost"] == 40000 and one["sold"] == 2000
    assert one["unitCost"] == 15.0 and one["margin"] == pytest.approx(1 - 30000 / 200000)
    assert D.actuals(snap, q="iki")["count"] == 1          # «İki»: Türkçe büyük İ
    assert D.search_books(snap, "İKİ")["items"][0]["code"] == "15201.01.2"
    det = D.book_detail(snap, "15201.01.1")
    assert det["spec"]["pages"] == 200 and det["spec"]["binding"] == "Amerikan Cilt" and len(det["salesByYear"]) == 2
    assert D.book_detail(snap, "yok") is None
    # Eski kitaplar: fiyatı olan her kitap listede (hesaplanamayan nedeniyle); bizim hesap «Kitap hesabı»nın önerisi.
    from semantic_bridge.pricing import form as F
    from semantic_bridge.pricing import karsilastir as KS
    res = KS.compare_all(snap, defaults={"targetMargin": 0.15, "variableRate": 0.05, "overheadRate": 0.0, "sellThrough": 1.0,
                                         "qtys": [1000, 2000, 3000, 5000], "channelMix": None},
                         tariff=F.default_tariff(), kur=None, freelance={}, market={}, calculate=P.calculate)
    priced = {c for c, b in snap["books"].items() if b.get("price")}
    assert {r["code"] for r in res["rows"]} == priced
    for r in res["rows"]:
        assert r["status"] in KS.STATUS
        if r["status"] == "hesaplanamadi":
            assert r["reason"]
        else:
            assert r["diff"] == pytest.approx(r["ours"] - r["price"]) and r["ours"] % 5 == 0
    sel = KS.select(res, new=True)
    assert sel["total"] == len(res["rows"]) and sum(sel["counts"].values()) == sel["total"]


def test_calculate_endpoint_logic(snap):
    out = P.calculate(snap, {"spec": {"pages": 200, "binding": "Amerikan Cilt"},
                             "inputs": {"printPerCopy": 20, "printSetup": 5000, "fixed": {"ceviri": 20000},
                                        "royaltyRate": 0.1, "vat": 0, "discount": 0.45, "variableRate": 0.02,
                                        "qtys": [1000, 3000], "targetMargin": 0.1, "chosenQty": 3000}})
    assert [s["qty"] for s in out["scenarios"]] == [1000, 3000]
    assert out["summary"]["price"] == out["recommendation"]["price"] and out["summary"]["price"] % 5 == 0
    assert {c["channel"] for c in out["channels"]} == {"KİTABEVİ", "E-TİCARET"}
    with pytest.raises(P.S.PricingError, match="baskı ve kâğıt"):
        P.calculate(snap, {"inputs": {"printPerCopy": 0}})


def test_sources_are_read_only():
    for s in SRC.SOURCES:
        head = s.sql.lstrip().upper()
        assert head.startswith("SELECT") and not any(w in head for w in ("INSERT ", "UPDATE ", "DELETE ", "DROP "))
    with pytest.raises(ValueError):
        SRC.logo_sql("logo_satis", "41; DROP", "20260101", "20270101")


class _Conn:
    def __init__(self, name, run):
        self.name, self.run, self.closed = name, run, False

    def execute(self, sql, limit):
        return [], self.run(self.name, sql), False

    def close(self):
        self.closed = True


def test_store_refresh_persists_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("PRICING_DATA_DIR", str(tmp_path))
    run, _ = _fake_run()
    conns = []

    def connect(name):
        conns.append(_Conn(name, run))
        return conns[-1]

    st = D.Store(connect)
    assert st.get() is None and st.status()["refreshing"] is False
    st.refresh()
    assert st.get()["dataEnd"] == "2026-08-17" and st.status()["error"] is None
    assert {c.name for c in conns} == {"logo", "crm"} and all(c.closed for c in conns)

    # Kurulum hata verirse önceki görüntü kalır, hata durumda yazılır.
    def broken(name):
        raise RuntimeError("bağlantı yok")

    st2 = D.Store(broken)
    st2.refresh()
    assert st2.get()["dataEnd"] == "2026-08-17" and "yenilenemedi" in st2.status()["error"]


def test_store_unwritable_dir(tmp_path, monkeypatch):
    f = tmp_path / "dosya"
    f.write_text("x")
    monkeypatch.setenv("PRICING_DATA_DIR", str(f / "alt"))
    st = D.Store(lambda name: None)
    st.refresh()
    assert "yazılamıyor" in st.status()["error"] and st.get() is None


def test_snapshot_backlist_fields(snap):
    """Fiyat Çalışması Excel'inin sütunları: stok, son baskı, son fiyat değişimi, tür başına telif, tek ödeme."""
    b = snap["books"]["15201.01.1"]
    assert snap["version"] == D.SNAPSHOT_VERSION
    assert b["stock"] == 1610 and b["lastPrintDate"] == "2026-04-30" and b["lastPrintQty"] == 3000
    assert b["coverNote"] == "Amerikan Cilt, Kuşe Kapak"
    # 180 → 200: değişim, 200'ün ilk görüldüğü gün; iki kopyanın ayları birleşir.
    assert b["priceChange"] == {"price": 200, "date": "2026-03-10", "prev": 180, "since": None}
    # Aynı türde iki sözleşme: en yenisi (8/5); yalnız tek ödemeli tercüme oranı boş bırakmaz, tutarı toplanır.
    assert b["royalties"] == {"Metin (Eser Sözleşmesi)": {"karton": 8, "sert": 5, "contract": "2023-1"}}
    assert b["singlePay"] == 440 and b["contracts"] == 3
    two = snap["books"]["15201.01.2"]
    assert two["priceChange"]["date"] is None and two["priceChange"]["since"] == "2025-12-01"
    assert two["royalties"] == {} and two["singlePay"] is None
    assert not any("fiyat geçmişi" in w or "sözleşme" in w for w in snap["warnings"])


def test_price_change_edges():
    assert D.price_change([]) is None
    # Liste fiyatı bir ay düşüp geri döndü: son değişim dönüşün olduğu ay.
    got = D.price_change([(202501, 100, 5, None), (202502, 90, 5, "2025-02-03"), (202503, 100, 5, "2025-03-04")])
    assert got == {"price": 100, "date": "2025-03-04", "prev": 90, "since": None}
    assert D.price_change([(202501, 100, 3, None)])["since"] == "2025-01-01"
    # Tek satırlık fiyat (yanlış giriş) ve payı %15'in altındaki fiyat liste fiyatı sayılmaz.
    assert D.month_list_prices([(202501, 300, 1, None), (202501, 100, 20, None), (202501, 120, 2, None)]) == [(202501, 100, None)]


def test_backlist_ladder_and_manual_prices(snap):
    from semantic_bridge.pricing import form as F
    from semantic_bridge.pricing import karsilastir as KS
    res = KS.compare_all(snap, defaults={"targetMargin": 0.15, "variableRate": 0.05, "overheadRate": 0.0, "sellThrough": 1.0,
                                         "qtys": [1000, 2000, 3000, 5000], "channelMix": None},
                         tariff=F.default_tariff(), kur=None, freelance={}, market={}, calculate=P.calculate)
    one = next(r for r in res["rows"] if r["code"] == "15201.01.1")
    assert one["stock"] == 1610 and one["perPage"] == 1.0 and one["color"] == "Tek renk"
    assert one["priceChanged"] == "2026-03-10" and one["prevPrice"] == 180 and one["singlePay"] == 440
    # Üç kitap aynı grupta (ebat, renk, cilt aynı); merdiven sayfa başına en yüksek fiyat, kitabın basamağı kendi sayfası.
    g = next(x for x in res["groups"] if x["key"] == one["group"])
    assert [(s["pages"], s["price"]) for s in g["steps"]] == [(190, 220), (200, 200), (210, 250)] and g["books"] == 3
    assert one["ladder"] == {"pages": 200, "price": 200, "code": "15201.01.1", "nextPages": 210, "nextPrice": 250}
    assert one["group"].endswith("13,5x21 · Tek renk · Amerikan cilt")
    sel = KS.select(res, new=True, manual={"15201.01.1": {"price": 250, "by": "u", "at": None}}, entered=True)
    assert sel["count"] == 1 and sel["entered"] == 1
    row = sel["rows"][0]
    assert row["newPrice"] == 250 and row["newPct"] == 0.25 and row["newPerPage"] == 1.25 and sel["avgNewPct"] == 0.25
    assert KS.select(res, new=True, group="yok")["count"] == 0
    from semantic_bridge.pricing import compare_csv
    csv_text = compare_csv(sel["rows"])
    assert "Metin (Eser Sözleşmesi) karton" in csv_text and "250,00" in csv_text and "25,0%" in csv_text


def test_compare_cache_persists(tmp_path):
    """Sonuç diske yazılır: yeni süreç (köprü yeniden başladı) aynı girdilerle beklemeden hazır döner."""
    import time
    from semantic_bridge.pricing import karsilastir as KS
    path = tmp_path / "compare.json"
    c1 = KS.Cache(lambda: path)
    assert c1.get("k1", lambda: {"rows": [1]})["ready"] is False
    for _ in range(100):
        if path.exists() and c1.get("k1", lambda: {})["ready"]:
            break
        time.sleep(0.01)
    c2 = KS.Cache(lambda: path)
    got = c2.get("k1", lambda: {"rows": []})
    assert got["ready"] is True and got["result"] == {"rows": [1]}
    # Girdiler değişti: eski sonuç hemen «eski» diye gelir, yenisi arkada hesaplanır.
    got = c2.get("k2", lambda: {"rows": [2]})
    assert got["ready"] is False and got["stale"] is True and got["result"] == {"rows": [1]}
