"""SEO & GEO → sezon takvimi (seasons.py): tarih hesabı, anahtar kelime, hazırlık penceresi, hazırlık kararı. Saf işlevler."""
from datetime import date, timedelta

from semantic_bridge.seo_geo import seasons as s


def occ(name, year, **extra):
    return s.occurrences(s.resolve({"name": name, **extra}), year)


def near(a: date, b: date, days: int = 1) -> bool:
    return abs((a - b).days) <= days


# ------------------------------------------------------------------ hareketli günler (miladi kural)

def test_mothers_day_is_second_sunday_of_may():
    assert occ("Anneler Günü", 2024) == [(date(2024, 5, 12), date(2024, 5, 12))]
    assert occ("Anneler Günü", 2025) == [(date(2025, 5, 11), date(2025, 5, 11))]
    assert occ("Anneler Günü", 2026) == [(date(2026, 5, 10), date(2026, 5, 10))]


def test_fathers_day_is_third_sunday_of_june():
    assert occ("Babalar Günü", 2024)[0][0] == date(2024, 6, 16)
    assert occ("Babalar Günü", 2025)[0][0] == date(2025, 6, 15)
    assert occ("Babalar Günü", 2026)[0][0] == date(2026, 6, 21)


def test_rule_beats_crm_week_and_fixed_rule():
    how = s.resolve({"name": "Öğretmenler Günü", "weekFrom": 48, "weekTo": 48})
    assert how["precision"] == "kesin"
    assert s.occurrences(how, 2026) == [(date(2026, 11, 24), date(2026, 11, 24))]


# ------------------------------------------------------------------ hicri takvim (±1 gün)

def test_hijri_conversion_known_dates():
    assert s.hijri_to_gregorian(1445, 10, 1) == date(2024, 4, 10)
    assert near(s.hijri_to_gregorian(1447, 1, 1), date(2025, 6, 26))


def test_ramazan_bayrami_2024_2026():
    for year, real in ((2024, date(2024, 4, 10)), (2025, date(2025, 3, 30)), (2026, date(2026, 3, 20))):
        got = occ("Ramazan Bayramı", year)
        assert len(got) == 1
        start, end = got[0]
        assert near(start, real), (year, start)
        assert (end - start).days == 2  # üç gün


def test_kurban_bayrami_2024_2026():
    for year, real in ((2024, date(2024, 6, 16)), (2025, date(2025, 6, 6)), (2026, date(2026, 5, 27))):
        start, end = occ("Kurban Bayramı", year)[0]
        assert near(start, real), (year, start)
        assert (end - start).days == 3  # dört gün


def test_kandil_is_the_evening_before_and_marked_approximate():
    how = s.resolve({"name": "Mevlid Kandili"})
    assert how["precision"] == "yaklasik" and how["uncertainty"] == 1
    start, _ = s.occurrences(how, 2025)[0]
    assert near(start, date(2025, 9, 3))
    regaip = occ("Regaip Kandili", 2026)
    assert regaip and regaip[0][0].weekday() == 3  # perşembe akşamı


def test_hijri_day_moves_about_eleven_days_a_year():
    a = occ("Ramazan Bayramı", 2025)[0][0]
    b = occ("Ramazan Bayramı", 2026)[0][0]
    # yıl içindeki gün sırası her yıl ~11 gün öne gelir (2025: 30/31 Mart, 2026: 20 Mart)
    assert 9 <= a.timetuple().tm_yday - b.timetuple().tm_yday <= 12
    assert near(a, date(2025, 3, 30)) and near(b, date(2026, 3, 20))


# ------------------------------------------------------------------ CRM haftası, addaki tarih, bilinmeyen

def test_crm_iso_week_range():
    assert s.week_range(2026, 19, 19) == (date(2026, 5, 4), date(2026, 5, 10))
    start, end = s.week_range(2026, 52, 1)
    assert start == date(2026, 12, 21) and end == date(2027, 1, 10)
    assert s.iso_week_monday(2025, 53) == s.iso_week_monday(2025, 52)  # 2025'te 53. hafta yok


def test_week_based_day():
    how = s.resolve({"name": "Kütüphaneler Haftası", "weekFrom": 14, "weekTo": 15})
    assert how["precision"] == "hafta"
    start, end = s.occurrences(how, 2026)[0]
    assert start.weekday() == 0 and end.weekday() == 6 and (end - start).days == 13


def test_date_in_name():
    assert s.date_in_name("15 Temmuz Demokrasi ve Milli Birlik Günü") == (7, 15)
    assert s.date_in_name("27 Mayıs Darbesi") == (5, 27)
    assert s.date_in_name("1. İnönü Zaferi") is None
    how = s.resolve({"name": "15 Temmuz Demokrasi ve Milli Birlik Günü", "weekFrom": 29, "weekTo": 29})
    assert s.occurrences(how, 2026) == [(date(2026, 7, 15), date(2026, 7, 15))]


def test_crm_date_field_is_utc():
    assert s._crm_date("2026-11-23 21:00:00") == "11-24"
    how = s.resolve({"name": "Bir Gün", "fixedDate": "11-24"})
    assert s.occurrences(how, 2027) == [(date(2027, 11, 24), date(2027, 11, 24))]


def test_unknown_date_is_not_guessed():
    for name in ("LGS (Liselere Geçiş Sınavı)", "YKS (Üniversite Sınavı)", "Tarihsiz Gün"):
        how = s.resolve({"name": name})
        assert how["precision"] == "bilinmiyor"
        assert s.next_occurrence(how, date(2026, 9, 27)) is None


def test_next_and_previous_occurrence():
    how = s.resolve({"name": "Anneler Günü"})
    assert s.next_occurrence(how, date(2026, 5, 10)) == (date(2026, 5, 10), date(2026, 5, 10))
    assert s.next_occurrence(how, date(2026, 5, 11))[0] == date(2027, 5, 9)
    assert s.previous_occurrence(how, date(2027, 5, 9))[0] == date(2026, 5, 10)
    bayram = s.resolve({"name": "Ramazan Bayramı"})
    start, end = s.next_occurrence(bayram, date(2026, 3, 21))
    assert start <= date(2026, 3, 21) <= end  # süren bayram da görünür


# ------------------------------------------------------------------ anahtar kelime

def test_keywords_from_day_name():
    assert s.keywords("Anneler Günü") == [["anneler"]]
    assert s.keywords("Dünya Su Günü") == [["dunya", "su", "gunu"]]
    assert s.keywords("Atatürk'ü Anma Gençlik Ve Spor Bayramı / Gençlik Haftası") == [["ataturk", "genclik", "spor"], ["genclik"]]
    assert s.keywords("Öğretmenler Günü") == [["ogretmenler"]]


def test_match_uses_turkish_folding_and_suffix_prefix():
    assert s.matches(s.tokens("ANNELER GÜNÜ için kitap"), ["anneler"])
    assert s.matches(s.tokens("annelere hediye kitap"), ["anneler"])
    assert not s.matches(s.tokens("sultan kitapları"), ["su"])
    assert s.matches(s.tokens("dünya su günü etkinlik"), ["dunya", "su", "gunu"])


def test_book_keywords():
    assert s.book_keywords("Küçük Prens") == [["kucuk", "prens"]]
    assert s.book_keywords("Su") == []


def test_scan_counts_each_query_once_per_key():
    entries = [("d:a", ["anneler"]), ("d:s", ["dunya", "su", "gunu"]),
               ("d:g", ["genclik"]), ("d:g", ["ataturk", "genclik", "spor"])]
    rows = [{"keys": ["Anneler Günü hediyesi"], "impressions": 100},
            {"keys": ["anneler günü kitap"], "impressions": 50},
            {"keys": ["dünya su günü"], "impressions": 7},
            {"keys": ["su şişesi"], "impressions": 9},
            {"keys": ["atatürk gençlik ve spor bayramı şiirleri"], "impressions": 10}]
    assert s.scan(rows, s.build_index(entries)) == {"d:a": 150, "d:s": 7, "d:g": 10}


def test_signature_changes_with_keywords():
    a = s.signature([("d:a", ["anneler"])])
    assert a == s.signature([("d:a", ["anneler"])])
    assert a != s.signature([("d:a", ["babalar"])])


# ------------------------------------------------------------------ hazırlık penceresi

def test_lead_window_phases():
    start = date(2026, 11, 24)
    w = s.lead_window(start, start, date(2026, 10, 1))
    assert w == {"prepStart": "2026-11-03", "daysLeft": 54, "prepDaysLeft": 33, "phase": "yaklasiyor"}
    assert s.lead_window(start, start, date(2026, 11, 3))["phase"] == "hazirlik"
    assert s.lead_window(start, start, date(2026, 11, 10))["daysLeft"] == 14
    assert s.lead_window(start, start, start)["phase"] == "suruyor"
    assert s.LEAD_DAYS == (start - date(2026, 11, 3)).days


# ------------------------------------------------------------------ kitap hazırlığı

def test_readiness_levels():
    assert s.readiness(85, [], None, "var")["level"] == "hazir"
    assert s.readiness(60, ["kritik"], None, "var")["level"] == "duzelt"
    assert s.readiness(90, ["yüksek"], None, None)["level"] == "duzelt"
    assert s.readiness(60, [], "hazir", None)["level"] == "onay_bekliyor"
    assert s.readiness(60, [], "onaylandi", None)["level"] == "onaylandi"
    assert s.readiness(60, [], "reddedildi", None)["level"] == "duzelt"
    r = s.readiness(90, ["orta"], None, "eksik")
    assert r["level"] == "hazir" and r["rightsWarning"] and r["openIssues"] == 1 and r["blockingIssues"] == 0


# ------------------------------------------------------------------ geçen yıl artışı

def test_uplift_against_baseline_and_site():
    day = date(2025, 5, 11)
    m = s.monday(day)
    win = [m - timedelta(weeks=k) for k in range(s.WINDOW_WEEKS)]
    base = [m - timedelta(weeks=k) for k in range(s.WINDOW_WEEKS, s.WINDOW_WEEKS + s.BASELINE_WEEKS)]
    series = {w: 200.0 for w in win} | {w: 100.0 for w in base}
    site = {w: 1000.0 for w in win + base}
    u = s.uplift(series, site, day, set(win + base))
    assert u["upliftPct"] == 100.0 and u["siteUpliftPct"] == 0.0 and u["netPt"] == 100.0
    assert u["impressions"] == 800
    assert s.uplift(series, site, day, set(win)) is None  # kıyas haftaları okunmamış (16 aydan eski)


def test_weekly_and_gsc_weeks():
    rows = [{"keys": ["2026-09-14"], "impressions": 5}, {"keys": ["2026-09-20"], "impressions": 7}]
    assert s.weekly(rows) == {date(2026, 9, 14): 12.0}
    weeks = s.gsc_weeks(date(2026, 9, 27))
    assert weeks[-1] == date(2026, 9, 14)  # kesin verisi tamamlanan son hafta
    assert all(w.weekday() == 0 for w in weeks)
    assert weeks[0] >= date(2026, 9, 27) - timedelta(days=s.GSC_HISTORY_DAYS)


# ------------------------------------------------------------------ CRM okuma ve birleştirme

def test_read_crm_merges_same_named_days():
    def execute(sql, limit):
        if "new_new_kitap_new_ozelgunlerBase" in sql:
            return [], [{"day_id": "a", "book_id": "k1", "name": "Kitap Bir", "ean": "978-1111111111"},
                        {"day_id": "B", "book_id": "k1", "name": "Kitap Bir", "ean": "9781111111111"},
                        {"day_id": "b", "book_id": "k2", "name": "Kitap İki", "ean": "9782222222222"}], False
        return [], [{"id": "A", "name": "Dünya Okuma Günü", "w1": 37, "w2": 37, "web": 1, "dt": None},
                    {"id": "B", "name": "Dünya Okuma Günü", "w1": 37, "w2": 37, "web": 0, "dt": None}], False

    days, books = s.read_crm("Timas_MSCRM.dbo", execute)
    assert len(days) == 1 and days[0]["crmIds"] == ["A", "B"] and days[0]["web"] and days[0]["weekFrom"] == 37
    assert sorted(b["ean"] for b in books[days[0]["key"]]) == ["9781111111111", "9782222222222"]


def test_builtin_days_do_not_duplicate_crm_days():
    crm_day = {"key": "anneler-gunu", "name": "Anneler Günü", "source": "crm", "crmIds": ["x"], "weekFrom": 19,
               "weekTo": 19, "fixedDate": None, "web": True}
    names = [d["name"] for d in s.merge_builtin([crm_day])]
    assert names.count("Anneler Günü") == 1 and "Ramazan Bayramı" in names and "Kurban Bayramı" in names


def test_guide_for_day():
    titles = ["Anneler Günü için 10 kitap", "Yaz tatili okuma listesi"]
    assert s.guide_for([["anneler"]], titles) == ["Anneler Günü için 10 kitap"]
    assert s.guide_for([["ogretmenler"]], titles) == []
