"""M47 Risk ve uyum: gösterge durumu ve eşik kenarı (tek bildirim, hatırlatma süresi), hazır tanımın eşiksiz gelmesi,
sürümlü eşik onayı (hazırlayan onaylayamaz), risk kaydı (puan yalnız gözden geçirmeyle), görünürlük, ısı haritası ve
«gözden geçir» kuyruğu, aksiyon sahipliği, uyum takvimi (dönem üretimi, kanıt, kapanış), hatırlatmalar (bir kez),
poliçe numarası maskesi, Zeki AI metninde girdi dışı sayı → kural metni, kategori seçimi, gösterge hesapçıları (sahte
bağlantıyla) ve yetki kuralları.

Veriler yapaydır ve yalnız kuralları sınar; gerçek Logo/CRM kabulü test sunucusunda (scripts/acceptance/M47).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from semantic_bridge import access as A
from semantic_bridge import risk as R
from semantic_bridge import risk_sources as S
from semantic_layer.store.catalog_store import open_store

TN = "t1"
NOW = datetime(2026, 9, 28, 6, 15, tzinfo=timezone.utc)
H24 = timedelta(hours=24)


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    R._ready.discard(id(e))
    R.ensure(e)
    return e


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("RISK_DIR", str(tmp_path / "risk"))
    for k in ("RISK_SCORE_BANDS", "RISK_REVIEW_DAYS", "ALERT_REMIND_HOURS", "RISK_COMPLIANCE_WARN_DAYS", "RISK_POLICY_WARN_DAYS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(R, "today", lambda: date(2026, 9, 28))


# ------------------------------------------------------------------ durum ve kenar


def test_state_of_both_directions_and_missing_thresholds():
    assert R.state_of(None, "artis_kotu", 1, 2) == "olculemedi"
    assert R.state_of(5, "artis_kotu", None, None) == "esik_yok"
    assert R.state_of(5, "artis_kotu", 3, 10) == "sari"
    assert R.state_of(10, "artis_kotu", 3, 10) == "kirmizi"
    assert R.state_of(2, "artis_kotu", 3, 10) == "yesil"
    assert R.state_of(40, "azalis_kotu", 50, 30) == "sari"
    assert R.state_of(30, "azalis_kotu", 50, 30) == "kirmizi"
    assert R.state_of(60, "azalis_kotu", 50, 30) == "yesil"
    assert R.state_of(12, "artis_kotu", None, 10) == "kirmizi"   # yalnız kırmızı eşik tanımlı


def test_edge_notifies_once_then_only_after_remind_hours():
    """Kabul 8 (DB'siz): yeşil→kırmızı tek bildirim; kırmızıda kalırken süre dolmadan ikinci bildirim yok."""
    rec, note = R.edge(None, "yesil", NOW, H24)
    assert note is None
    seq = []
    t = NOW
    for hours, st in [(1, "kirmizi"), (2, "kirmizi"), (10, "kirmizi"), (5, "olculemedi"), (6, "kirmizi"), (1, "kirmizi")]:
        t += timedelta(hours=hours)
        rec, note = R.edge(rec, st, t, H24)
        seq.append(note)
    # 1s: yeni; 3s, 13s: yok; 18s ölçülemedi: kırmızı bozulmaz; 24s: 23 saat — yok; 25s: 24 saat doldu → hatırlat
    assert seq == ["yeni", None, None, None, None, "hatirlat"]
    assert rec["durum"] == "kirmizi"
    rec, note = R.edge(rec, "yesil", t + timedelta(hours=1), H24)
    assert note is None and rec["durum"] == "yesil" and rec["notified_at"] is None
    rec, note = R.edge(rec, "kirmizi", t + timedelta(hours=2), H24)
    assert note == "yeni"


# ------------------------------------------------------------------ gösterge tanımı ve ölçüm


def _seed(engine):
    return R.seed_library(engine, TN, S.LIBRARY)


def test_library_seeds_without_thresholds_and_is_idempotent(engine):
    assert _seed(engine) == len(S.LIBRARY)
    assert _seed(engine) == 0
    items = R.indicators(engine, TN)
    assert len(items) == len(S.LIBRARY)
    assert all(g["esikSari"] is None and g["esikKirmizi"] is None and g["sahip"] is None for g in items)
    out, note = R.record_measure(engine, TN, "karsiliksiz_cek", {"deger": 6, "veri_son_gunu": "2026-08-17", "kanit": {"tutar": 6326658}},
                                 "sistem", NOW, H24)
    assert out["durum"] == "esik_yok" and note is None and out["veriSonGunu"] == "2026-08-17"


def test_threshold_draft_needs_another_approver_and_versions(engine):
    _seed(engine)
    with pytest.raises(R.RiskError):
        R.propose_indicator(engine, TN, "cfo", {"kod": "serbest_sql", "ad": "x"}, S.BY_CODE)
    with pytest.raises(R.RiskError):  # arttıkça kötü: sarı > kırmızı olamaz
        R.propose_indicator(engine, TN, "cfo", {"kod": "karsiliksiz_cek", "esikSari": 5, "esikKirmizi": 2}, S.BY_CODE)
    d = R.propose_indicator(engine, TN, "cfo", {"kod": "karsiliksiz_cek", "esikSari": 1, "esikKirmizi": 3, "sahip": "cfo",
                                                "sahipEposta": "cfo@timas.com.tr"}, S.BY_CODE)
    assert d["surum"] == 2 and d["durum"] == "taslak"
    with pytest.raises(R.RiskError) as e:
        R.propose_indicator(engine, TN, "cfo", {"kod": "karsiliksiz_cek", "esikSari": 2}, S.BY_CODE)
    assert e.value.status == 409
    with pytest.raises(R.RiskError) as e:
        R.decide_indicator(engine, TN, "cfo", "karsiliksiz_cek", True, None)
    assert e.value.status == 403
    ok = R.decide_indicator(engine, TN, "koordinator", "karsiliksiz_cek", True, "uygun")
    assert ok["durum"] == "yururlukte" and ok["onaylayan"] == "koordinator"
    v = R.indicator_values(engine, TN, "karsiliksiz_cek")
    assert [s["durum"] for s in v["surumler"]] == ["yururlukte", "arsiv"]
    out, note = R.record_measure(engine, TN, "karsiliksiz_cek", {"deger": 6}, "sistem", NOW, H24)
    assert out["durum"] == "kirmizi" and note == "yeni" and out["esik"]["surum"] == 2
    out, note = R.record_measure(engine, TN, "karsiliksiz_cek", {"deger": 6}, "sistem", NOW + timedelta(hours=2), H24)
    assert note is None
    out, note = R.record_measure(engine, TN, "karsiliksiz_cek", {"deger": None, "hata": "bağlantı yok"}, "sistem", NOW + timedelta(hours=3), H24)
    assert out["durum"] == "olculemedi" and out["hata"] == "bağlantı yok" and note is None
    g = next(x for x in R.indicators(engine, TN) if x["kod"] == "karsiliksiz_cek")
    assert g["kirmiziBaslangic"] is not None and len(g["gecmis"]) == 3


def test_due_indicators_respect_frequency(engine):
    _seed(engine)
    assert set(R.due_indicators(engine, TN, NOW)) == set(S.BY_CODE)
    R.record_measure(engine, TN, "tedarikci_yogunlasmasi_ilk4", {"deger": 40}, "sistem", NOW, H24)   # aylık
    R.record_measure(engine, TN, "logo_veri_gecikmesi", {"deger": 42}, "sistem", NOW, H24)           # günlük
    due = R.due_indicators(engine, TN, NOW + timedelta(hours=23, minutes=30))
    assert "logo_veri_gecikmesi" in due and "tedarikci_yogunlasmasi_ilk4" not in due


# ------------------------------------------------------------------ risk kaydı


def _risk(engine, user="koordinator", **kw):
    _seed(engine)
    body = {"baslik": "Logo veri gecikmesi", "kategori": "bt", "sahip": "bt", "olasilik": 4, "etki": 3,
            "gostergeler": ["logo_veri_gecikmesi"]}
    body.update(kw)
    return R.create_risk(engine, TN, user, body)


def test_create_update_and_score_changes_only_by_review(engine):
    _seed(engine)
    r = _risk(engine)
    assert r["puan"] == 12 and r["seviye"] == "yuksek" and r["sonrakiGozdenGecirme"] == "2026-12-27"
    with pytest.raises(R.RiskError):
        R.update_risk(engine, TN, "koordinator", r["id"], {"etki": 5})
    with pytest.raises(R.RiskError):
        R.update_risk(engine, TN, "koordinator", r["id"], {"gostergeler": ["uydurma"]})
    out, diff = R.update_risk(engine, TN, "koordinator", r["id"], {"tanim": "Kopya dondu", "gostergeler": ["logo_veri_gecikmesi", "maliyet_gecikmesi"]})
    assert "tanim" in diff and diff["gostergeler"]["yeni"] == ["logo_veri_gecikmesi", "maliyet_gecikmesi"]
    rv = R.review_risk(engine, TN, "bt", r["id"], {"olasilik": 5, "etki": 3, "egilim": "artiyor", "not": "canlı erişim yok"})
    assert rv["puan"] == 15 and rv["seviye"] == "kritik" and rv["sonGozdenGecirme"]
    d = R.risk_detail(engine, TN, r["id"])
    assert d["gozdenGecirmeler"][0]["eskiPuan"] == 12 and d["gozdenGecirmeler"][0]["yeniPuan"] == 15


def test_visibility_owner_creator_and_action_owner(engine):
    r = _risk(engine, sahip="depo")
    R.add_action(engine, TN, "koordinator", r["id"], {"eylem": "Tatbikat", "sahip": "lojistik", "termin": "2026-10-10"})
    assert R.list_risks(engine, TN, "depo", False)["total"] == 1
    assert R.list_risks(engine, TN, "lojistik", False)["total"] == 1
    assert R.list_risks(engine, TN, "koordinator", False)["total"] == 1      # açan
    assert R.list_risks(engine, TN, "baskasi", False)["total"] == 0
    assert R.list_risks(engine, TN, "baskasi", True)["total"] == 1


def test_heatmap_queue_and_review_clears_queue(engine):
    _seed(engine)
    R.propose_indicator(engine, TN, "bt", {"kod": "logo_veri_gecikmesi", "esikSari": 7, "esikKirmizi": 30}, S.BY_CODE)
    R.decide_indicator(engine, TN, "koordinator", "logo_veri_gecikmesi", True, None)
    r = _risk(engine)
    _risk(engine, baslik="Sahipsiz risk", sahip=None, gostergeler=[])
    R.record_measure(engine, TN, "logo_veri_gecikmesi", {"deger": 42}, "sistem", datetime.now(timezone.utc), H24)
    sm = R.summary(engine, TN, "koordinator", True, R.indicators(engine, TN))
    assert sm["isiHaritasi"][3][2]["sayi"] == 2          # olasılık 4 × etki 3
    reasons = {q["risk"]["baslik"]: {n["tur"] for n in q["nedenler"]} for q in sm["kuyruk"]}
    assert reasons["Logo veri gecikmesi"] == {"gosterge"} and reasons["Sahipsiz risk"] == {"sahipsiz"}
    assert sm["kirmiziGosterge"][0]["kod"] == "logo_veri_gecikmesi"
    R.review_risk(engine, TN, "bt", r["id"], {"olasilik": 4, "etki": 3, "not": "puan aynı"})
    sm = R.summary(engine, TN, "koordinator", True, R.indicators(engine, TN))
    assert "Logo veri gecikmesi" not in {q["risk"]["baslik"] for q in sm["kuyruk"]}


def test_actions_owner_fields_and_overdue(engine):
    r = _risk(engine)
    a = R.add_action(engine, TN, "koordinator", r["id"], {"eylem": "Canlı Logo erişimi", "sahip": "bt", "termin": "2026-09-20"})
    assert a["gecikti"] and a["kalanGun"] == -8
    with pytest.raises(R.RiskError) as e:
        R.update_action(engine, TN, "bt", a["id"], {"termin": "2026-12-01"}, full=False)
    assert e.value.status == 403
    out, diff = R.update_action(engine, TN, "bt", a["id"], {"durum": "tamamlandi", "not": "VPN açıldı"}, full=False)
    assert out["durum"] == "tamamlandi" and out["tamamlayan"] == "bt" and not out["gecikti"] and "durum" in diff


def test_suggestion_accept_needs_human_score(engine):
    _seed(engine)
    g = {"kod": "karsiliksiz_cek", "ad": "Karşılıksız çıkan çek", "birim": "adet", "sahip": "cfo", "sahipEposta": None}
    s = R.create_suggestion(engine, TN, "koordinator", g, {"baslik": "Çek riski", "tanim": "x"}, {"kategori": "finansal", "emin": True})
    assert s["durum"] == "oneri" and s["puan"] is None and s["gostergeler"] == ["karsiliksiz_cek"]
    with pytest.raises(R.RiskError):
        R.accept_suggestion(engine, TN, "koordinator", s["id"], True, {})
    ok = R.accept_suggestion(engine, TN, "koordinator", s["id"], True, {"olasilik": 3, "etki": 4})
    assert ok["durum"] == "acik" and ok["puan"] == 12


# ------------------------------------------------------------------ uyum


def test_occurrences_clamp_month_end_and_periods():
    assert R.occurrences(date(2026, 1, 31), "aylik", date(2026, 4, 30)) == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]
    assert R.occurrences(date(2026, 3, 31), "ceyreklik", date(2027, 1, 1)) == [date(2026, 3, 31), date(2026, 6, 30), date(2026, 9, 30), date(2026, 12, 31)]
    assert R.occurrences(date(2026, 5, 1), "tek", date(2027, 1, 1)) == [date(2026, 5, 1)]
    assert R._period(date(2026, 8, 5), "ceyreklik") == "2026-Ç3"


def test_compliance_events_evidence_and_close(engine):
    it, _ = R.save_item(engine, TN, "hukuk", None, {"alan": "vergi", "madde": "KDV beyannamesi", "siklik": "aylik",
                                                    "ilkSonGun": "2026-09-26", "sorumlu": "muhasebe"})
    n = R.generate_events(engine, TN)
    assert n == 0                                   # save_item zaten üretti; ikinci çağrı eklemez
    cal = R.calendar(engine, TN, "2026-09")
    ev = cal["items"][0]
    assert ev["gecikti"] and ev["madde"] == "KDV beyannamesi"
    with pytest.raises(R.RiskError):
        R.close_event(engine, TN, "hukuk", ev["id"])            # kanıtsız kapanışa açıklama şart
    with pytest.raises(R.RiskError):
        R.attach_event_evidence(engine, TN, "hukuk", ev["id"], "tahakkuk.pdf", b"not a pdf")
    up = R.attach_event_evidence(engine, TN, "hukuk", ev["id"], "tahakkuk.pdf", b"%PDF-1.4 test")
    assert up["durum"] == "kanit" and up["kanitVar"]
    path, name, mime = R.file_of(R.COMP_EVENTS, engine, TN, ev["id"], "kanit")
    assert name == "tahakkuk.pdf" and mime == "application/pdf"
    closed = R.close_event(engine, TN, "hukuk", ev["id"])
    assert closed["durum"] == "kapandi"
    items = R.compliance_items(engine, TN)["items"]
    assert items[0]["kapanan"] == 1 and items[0]["siradaki"]["sonGun"] == "2026-10-26"
    assert R.item_area(engine, TN, it["id"]) == "vergi"


def test_reminders_once_and_narrowest_window(engine):
    r = _risk(engine, sahipEposta="bt@timas.com.tr")
    R.add_action(engine, TN, "koordinator", r["id"], {"eylem": "Yedek", "termin": "2026-10-02", "sahipEposta": "depo@timas.com.tr"})
    R.save_item(engine, TN, "hukuk", None, {"alan": "kvkk", "madde": "VERBİS güncelleme", "siklik": "tek", "ilkSonGun": "2026-10-01",
                                            "sorumluEposta": "kvkk@timas.com.tr"})
    R.save_policy(engine, TN, "cfo", None, {"tur": "Yangın", "policeNo": "TR-12345678", "bit": "2026-11-15"})
    rem = R.due_reminders(engine, TN)
    kinds = sorted(x["tur"] for x in rem)
    assert kinds == ["aksiyon", "police", "uyum"]
    uyum = next(x for x in rem if x["tur"] == "uyum")
    assert uyum["key"].startswith("uyum-3:") and uyum["eposta"] == "kvkk@timas.com.tr"
    R.mark_sent(engine, TN, [x["key"] for x in rem])
    assert R.due_reminders(engine, TN) == []


def test_policy_number_is_masked(engine):
    p, _ = R.save_policy(engine, TN, "cfo", None, {"tur": "Nakliyat", "policeNo": "AB 1234 5678", "teminat": [{"ad": "Emtia", "tutar": "1.250.000"}]})
    assert p["policeNo"] == "••••5678" and p["teminat"] == [{"ad": "Emtia", "tutar": 1250000.0}]
    assert R.mask_policy_no("") is None


# ------------------------------------------------------------------ Zeki AI


def test_foreign_numbers_and_fallback_to_rule_text():
    facts = {"gosterge": "Karşılıksız çek", "deger": 6.0, "birim": "adet", "durum": "Kırmızı", "veriSonGunu": "2026-08-17"}
    assert R.foreign_numbers("6 çek, 2026-08-17 tarihli", facts) == set()
    assert R.foreign_numbers("6 çek, toplam 7.500.000 ₺", facts) == {"7500000"}
    draft, src_, note = R.draft_suggestion(facts, lambda m: '{"baslik": "Çek riski", "tanim": "Kayıp 7.500.000 ₺ olabilir"}')
    assert src_ == "kural" and "7500000" in note and "Karşılıksız çek" in draft["baslik"]
    draft, src_, note = R.draft_suggestion(facts, lambda m: '{"baslik": "Tahsilat riski artıyor", "tanim": "Bu yıl 6 çek karşılıksız çıktı."}')
    assert src_ == "zeki" and note is None and draft["baslik"] == "Tahsilat riski artıyor"
    draft, src_, _ = R.draft_suggestion(facts, None)
    assert src_ == "kural"


def test_report_text_uses_only_facts():
    sm = {"sayilar": {"canli": 3, "kritik": 1, "gosterge": 15, "kirmizi": 1, "esiksiz": 10}, "ilk10": [], "kirmiziGosterge": [],
          "gecikenAksiyon": [], "kuyruk": [1, 2], "uyumBuAy": []}
    f = R.report_facts(sm, [], "2026-Ç3")
    text, src_, _ = R.draft_report_text(f, lambda m: "# Brifing\nCanlı risk 3, tahmini zarar 12.000.000 ₺.")
    assert src_ == "kural" and "Canlı risk: 3" in text
    text, src_, _ = R.draft_report_text(f, lambda m: "# Brifing\nCanlı risk 3; kritik 1.")
    assert src_ == "zeki"


class FakeChoice:
    def __init__(self, choice, p, margin):
        self.choice, self.probability, self.margin = choice, p, margin

    def confident(self, min_prob, min_margin=0.0, min_coverage=0.0):
        return self.probability >= min_prob and self.margin >= min_margin


def test_classify_closed_set():
    calls = []

    def choose(prompt, labels):
        calls.append(labels)
        return FakeChoice(R.KATEGORILER["yasal"], 0.92, 0.8)

    out = R.classify("Süresi biten sözleşmeyle satış", choose)
    assert out["kategori"] == "yasal" and out["emin"] and calls[0] == list(R.KATEGORILER.values())
    low = R.classify("x", lambda p, l: FakeChoice(R.KATEGORILER["bt"], 0.5, 0.1))
    assert low["kategori"] == "bt" and not low["emin"]
    assert R.classify("x", None) is None


# ------------------------------------------------------------------ hesapçılar (sahte bağlantı)


class FakeRun:
    def __init__(self, answers):
        self.answers, self.sql = answers, []

    def __call__(self, sql):
        self.sql.append(sql)
        for key, rows in self.answers:
            if key in sql:
                return rows
        raise AssertionError("beklenmeyen sorgu: " + sql[:120])


def _ctx(logo, crm=None, state=None):
    c = S.Context(logo_file=lambda: "", crm_file=lambda: "", crm_schema=lambda: "Timas_MSCRM.dbo", app_state=state,
                  asof=date(2026, 9, 28))
    c._cache["logo"] = logo
    if crm is not None:
        c._cache["crm"] = crm
    c._cache["firm"] = ("411", 2026)
    return c


def test_library_and_computers_match():
    assert set(S.COMPUTERS) == set(S.BY_CODE)
    assert all(x["yon"] in R.DIRECTIONS and x["birim"] in R.UNITS and x["siklik"] in R.FREQ_LABELS for x in S.LIBRARY)


def test_data_delay_and_concentration():
    logo = FakeRun([("MAX(DATE_) AS son FROM dbo.LG_411_01_INVOICE", [{"son": "2026-08-17"}]),
                    ("GROUP BY I.CLIENTREF", [{"n": 50.0, "kod": "A"}, {"n": 30.0, "kod": "B"}, {"n": 10.0, "kod": "C"},
                                              {"n": 5.0, "kod": "D"}, {"n": 5.0, "kod": "E"}])])
    c = _ctx(logo)
    assert S.k_data_delay(c)["deger"] == 42.0
    top4 = S.k_customer_top4(c)
    assert top4["deger"] == pytest.approx(95.0) and top4["kanit"]["toplam"] == 100.0 and len(top4["kanit"]["ilk"]) == 4
    assert S.k_customer_top10(c)["deger"] == pytest.approx(100.0)
    assert sum(1 for s in logo.sql if "GROUP BY I.CLIENTREF" in s) == 1          # aynı turda bir kez okunur
    assert "TRCODE IN (2,3,7,8,9)" in logo.sql[-1] and "'2026-01-01'" in logo.sql[-1]


def test_bounced_cheque_sql_follows_rule_12():
    sql = S.bounced_cheque_sql("411", 2026, [1, 2])
    assert "STATUS = 11" in sql and "DEVIR = 0" in sql and "EXISTS" in sql and "K.AMOUNT" in sql and "DOC IN (1, 2)" in sql
    c = _ctx(FakeRun([("CSCARD", [{"adet": 6, "tutar": 6326658.0}]), ("MAX(DATE_) AS son", [{"son": "2026-08-17"}])]))
    out = S.k_bounced_cheques(c)
    assert out["deger"] == 6 and out["kanit"]["tutar"] == 6326658.0


def test_expired_selling_excludes_unsold_and_uses_data_end():
    crm = FakeRun([("new_sozlesmeBase", [{"stok": "K1", "ad": "A", "sozlesme": "S1", "bitis": "2025-01-01"},
                                         {"stok": "K2", "ad": "B", "sozlesme": "S2", "bitis": "2024-06-01"}])])
    logo = FakeRun([("MAX(DATE_) AS son", [{"son": "2026-08-17"}]), ("I.CODE IN", [{"stok": "K2", "adet": 12}])])
    out = S.k_expired_selling(_ctx(logo, crm))
    assert out["deger"] == 1 and out["kanit"]["kitaplar"][0]["stok"] == "K2" and out["kanit"]["suresiBitenKitap"] == 2
    assert "'2026-08-17'" in logo.sql[-1] and "INVOICEREF <> 0" in logo.sql[-1]
    assert "NOT EXISTS" in crm.sql[0] and "new_SozlesmeTipi = 5" in crm.sql[0]


def test_module_sources_read_ready_reports():
    rep = {"checks": [{"id": "a", "status": "finding", "affected": 2}, {"id": "b", "status": "passed"}],
           "deepAudit": {"checks": [{"id": "c", "status": "finding", "affected": 1}]}, "lastDate": "2026-08-17", "runId": "r1"}
    snap = {"data": {"views": [{"id": "tekrar", "columns": [{"key": "stok_kodu"}, {"key": "oneri"}],
                                "rows": [["K1", "Risk/Acil"], ["K2", "Kritik"], ["K3", "Risk/Acil"]]}]}, "updatedAt": 1790000000}
    state = SimpleNamespace(financial_audit=SimpleNamespace(load=lambda: rep),
                            management_reports=SimpleNamespace(read=lambda rid: snap))
    c = _ctx(FakeRun([]), state=state)
    assert S.k_audit_findings(c)["deger"] == 2
    st = S.k_stock_urgent(c)
    assert st["deger"] == 2 and [k["stok_kodu"] for k in st["kanit"]["kitaplar"]] == ["K1", "K3"]
    out = S.measure(_ctx(FakeRun([]), state=None), "stok_risk_acil")
    assert out["deger"] is None and out["hata"]


# ------------------------------------------------------------------ yetki


def test_risk_access_rules():
    assert A.rule_for("/api/v1/risk/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/risk/summary") == frozenset({"sayfa:risk-uyum"})
    assert A.features_for("POST", "/api/v1/risk/risks") == ["ozellik:risk.yaz"]
    assert A.features_for("POST", "/api/v1/risk/risks/abc/review") == ["ozellik:risk.yaz"]
    assert A.features_for("POST", "/api/v1/risk/risks/abc/actions") == ["ozellik:risk.yaz"]
    assert A.features_for("PATCH", "/api/v1/risk/actions/abc") == []            # sahibi günceller; uçta denetlenir
    assert A.features_for("POST", "/api/v1/risk/reports/draft") == ["ozellik:risk.yaz"]
    assert A.features_for("POST", "/api/v1/risk/reports/abc/approve") == []     # açıkça verilen, uçta
    assert A.features_for("POST", "/api/v1/risk/indicators") == []              # açıkça verilen, uçta
    assert A.features_for("POST", "/api/v1/risk/compliance/events/e1/close") == ["ozellik:uyum.yaz"]
    assert A.features_for("DELETE", "/api/v1/risk/policies/p1") == ["ozellik:risk.sigorta-bcp"]
    assert A.features_for("GET", "/api/v1/risk/reports/r1/document.docx") == ["ozellik:veri.disa-aktar"]
    assert A.features_for("GET", "/api/v1/risk/risks") == []
    assert {"ozellik:risk.herkesinki", "ozellik:risk.gosterge", "ozellik:risk.gosterge-onay", "ozellik:risk.rapor-onay",
            "ozellik:uyum.kvkk"} <= A.explicit_keys()
    assert {"sayfa:risk-uyum", "ozellik:risk.yaz", "ozellik:uyum.yaz", "ozellik:risk.sigorta-bcp"} <= A.all_keys()
    page = next(p for p in A.catalog()["pages"] if p["key"] == "sayfa:risk-uyum")
    assert page["area"] == "finans" and page.get("explicit") is True
