"""M31 Okul tanıtım ve ziyaret: kademe ↔ sınıf, kitap sınıfları, ad eşleşmesi, akademik dönem, öncelik puanı,
dış veri yükleme (ilçe endeksi, takvim) ve çakışma, katalog seçimi, bayi adayları, portal kayıtları (ortak ziyaret
tablosu, plan, bayi bağı), yetki kuralları.

Sözleşme: sayısı çevrilemeyen öğrenci «bilinmiyor» kalır (0 sayılmaz); puan bileşenleri ekranda yazılı ve toplamı
ağırlıkları aşmaz; yükleme satırı sessizce düşmez; katalog «hepsi» seçilince kesilmez; gizli not başkasına gitmez;
geçmiş bayi bağı iki kez yazılmaz; model metnindeki sayı verilen bilgide yoksa metin kullanılmaz.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from semantic_bridge import access as A
from semantic_bridge import school_visits as SV
from semantic_layer.store.catalog_store import open_store

T = "t1"
IL = "11111111-1111-1111-1111-111111111111"
S1 = "aaaaaaaa-0000-0000-0000-000000000001"
S2 = "aaaaaaaa-0000-0000-0000-000000000002"
S3 = "aaaaaaaa-0000-0000-0000-000000000003"
ACC1 = "bbbbbbbb-0000-0000-0000-000000000001"
ACC2 = "bbbbbbbb-0000-0000-0000-000000000002"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    SV._ready.discard(id(e))
    SV.ensure(e)
    return e


def _settings(**over):
    s = SV.settings_from(lambda key, default="": default)
    s.update(over)
    return s


def _snap():
    base = {"kurum_tipi": 1, "kurum_turu": 1, "okul_turu": 9, "il_id": IL, "il": "İstanbul", "ilce_id": None}
    schools = [
        dict(base, id=S1, okul_adi="Moda İlkokulu", kademe=3, ogrenci=1240, ilce="Kadıköy", sahip_hesap="TIMAS\\ayse", degisti="2026-05-01T09:00:00"),
        dict(base, id=S2, okul_adi="Kadıköy Anadolu Lisesi", kademe=4, ogrenci=None, ilce="Kadıköy", kurum_turu=2),
        dict(base, id=S3, okul_adi="Üsküdar Ortaokulu", kademe=5, ogrenci=800, ilce="Üsküdar", il_temsilci_hesap="TIMAS\\mehmet"),
    ]
    visits = [
        {"id": "e1", "tip": 1, "sekil": 1, "durum": 100000002, "ziyaret_yeri": S1, "gerceklesen": "2025-10-01T07:00:00",
         "bayi_id": ACC1, "sorumlu_hesap": "TIMAS\\ayse"},
        {"id": "e2", "tip": 1, "sekil": 2, "durum": 100000002, "ziyaret_yeri": None, "okul_metni": "USKUDAR ORTA OKULU",
         "il_id": IL, "gerceklesen": "2025-11-01T07:00:00", "sorumlu_hesap": "TIMAS\\mehmet"},
    ]
    dealers = [
        {"id": ACC1, "ad": "Moda Kitabevi", "cari_kodu": "120.01", "kanal": 100000001, "il": "İstanbul", "ilce": "Kadıköy", "logicalref": "501"},
        {"id": ACC2, "ad": "Üsküdar Kitap", "cari_kodu": "120.02", "kanal": 100000008, "il": "İstanbul", "ilce": "Üsküdar", "logicalref": "502"},
    ]
    books = [
        {"id": "k1", "ad": "Minik Kaşif", "stok_kodu": "15201001", "crm_fiyat": 120, "new_1sinif": 1, "new_2sinif": 1},
        {"id": "k2", "ad": "Gençlik Romanı", "stok_kodu": "15201002", "crm_fiyat": 250, "new_9sinif": 1},
        {"id": "k3", "ad": "Tükenmiş Kitap", "stok_kodu": "15201003", "crm_fiyat": 100, "new_3sinif": 1},
        {"id": "k4", "ad": "Yaşa Göre", "stok_kodu": "15201004", "crm_fiyat": 90, "new_8yas": 1},
    ]
    return {
        "schools": schools, "visits": visits, "orders": [
            {"id": "o1", "tip": 11, "olustu": "2026-02-01T09:00:00", "firma": "Moda İlkokulu", "il_id": IL},
            {"id": "o2", "tip": 13, "olustu": "2026-03-01T09:00:00", "firma": "Başka Bir Kurum", "il_id": IL},
        ],
        "history": [{"ziyaret_yeri": S1, "bayi_id": ACC1, "adet": 2, "son": "2025-10-01T07:00:00"}],
        "dealers": dealers, "books": books, "users": [{"hesap": "TIMAS\\ayse", "ad": "Ayşe"}], "districts": [],
        "stock": {"15201001": 40.0, "15201002": 10.0, "15201003": 0.0, "15201004": 5.0},
        "prices": [{"stok_kodu": "15201001", "fiyat": 130, "cari_kodu_ozel": ""}, {"stok_kodu": "15201001", "fiyat": 110, "cari_kodu_ozel": "B"}],
        "clcards": [], "dealerItems": [{"cari_kodu": "120.01", "stok_kodu": "15201001", "adet": 300},
                                        {"cari_kodu": "120.02", "stok_kodu": "15201002", "adet": 50}],
        "dealerMonths": [], "firms": {2026: "411"}, "asOf": "2026-09-28", "at": 1.0, "warnings": [],
    }


def _model(**over):
    return SV.Model(_snap(), _settings(**over), {})


# ------------------------------------------------------------------ saf kurallar


def test_school_grades_from_kademe_type_and_university():
    assert SV.school_grades(1, 3, None) == frozenset({1, 2, 3, 4})
    assert SV.school_grades(1, 5, None) == frozenset({5, 6, 7, 8})
    assert SV.school_grades(1, None, 9) == frozenset(range(1, 9))       # Temel Eğitim, kademe boş
    assert SV.school_grades(1, 6, None) == frozenset()                   # RAM: katalog yok
    assert SV.school_grades(3, None, None) == SV.UNIVERSITY


def test_book_grades_prefer_grade_bits_then_ages_then_range():
    assert SV.book_grades({"new_okuloncesi": 1, "new_1sinif": 1}) == frozenset({0, 1})
    assert SV.book_grades({"new_8yas": 1, "new_9yas": 1}) == frozenset({2, 3})
    assert SV.book_grades({"yas_bas": 4, "yas_bit": 7}) == frozenset({0, 1})
    assert SV.book_grades({"hedef_kitle": 3}) == SV.UNIVERSITY
    assert SV.book_grades({}) == frozenset()
    assert SV.grades_text({5, 6, 7, 8}) == "5.–8. sınıf"


def test_name_matching_is_spelling_tolerant():
    assert SV.name_key("Moda İlk Okulu") == SV.name_key("MODA ILKOKULU")
    assert SV.name_score("Üsküdar Orta Okulu", "ÜSKÜDAR ORTAOKULU") == 1.0
    assert SV.name_score("Moda İlkokulu", "Kadıköy Anadolu Lisesi") == 0.0


def test_academic_terms():
    assert SV.term_of(date(2026, 9, 28)) == "2026-2027/1"
    assert SV.term_of(date(2027, 1, 15)) == "2026-2027/1"
    assert SV.term_of(date(2027, 3, 1)) == "2026-2027/2"
    assert SV.term_range("2026-2027/1") == (date(2026, 9, 1), date(2027, 1, 31))
    assert SV.term_range("2026-2027") == (date(2026, 9, 1), date(2027, 8, 31))
    with pytest.raises(SV.SchoolError):
        SV.term_range("2026-2028")


def test_priority_components_are_explained_and_bounded():
    w = SV.DEFAULT_WEIGHTS
    sc = {"students": 1240, "grades": frozenset({1, 2, 3, 4}), "kurumTuruKod": 2, "kurumTuru": "Özel"}
    out = SV.score_school(sc, weights=w, ref_students=1000, last_visit=None, orders=[{"type": 13, "created": "2026-02-01"}],
                          fitting=12, endeks=5.0, endeks_range=(1.0, 5.0), has_dealer=True, now=date(2026, 9, 28))
    assert out["score"] == sum(w.values())                               # her bileşen tam
    assert {p["key"] for p in out["parts"]} == set(w)
    unknown = SV.score_school(dict(sc, students=None), weights=w, ref_students=1000, last_visit="2026-09-01", orders=[],
                              fitting=0, endeks=None, endeks_range=None, has_dealer=False, now=date(2026, 9, 28))
    parts = {p["key"]: p for p in unknown["parts"]}
    assert parts["ogrenci"]["points"] == 0 and "bilinmiyor" in parts["ogrenci"]["note"]
    assert parts["ziyaret"]["points"] == 0 and parts["bolge"]["note"] == "ilçe endeksi yüklenmedi"
    assert unknown["score"] < out["score"]


def test_context_upload_parsing_reports_every_dropped_row():
    rows = SV.read_table({"csv": "il;ilce;endeks\nİstanbul;Kadıköy;4,85\nİstanbul;;3\nAnkara;Çankaya;abc\n"})
    parsed = SV.parse_context("ilce_endeks", rows, {"istanbul|kadikoy": {"id": "x", "il": "İstanbul", "ilce": "Kadıköy"}})
    assert [k for k, _ in parsed["items"]] == ["istanbul|kadikoy"]
    assert parsed["items"][0][1]["endeks"] == 4.85
    assert len(parsed["bad"]) == 2
    cal = SV.parse_context("takvim", SV.read_table({"csv": "baslangic,bitis,tur,ad,il\n17.11.2026,21.11.2026,tatil,Ara tatil,\n"
                                                             "2026-12-07,2026-12-11,sınav,Deneme,İstanbul\n"}), {})
    assert len(cal["items"]) == 2 and cal["items"][1][1]["tur"] == "sinav"
    ctx = {"takvim": [v for _, v in cal["items"]]}
    assert SV.conflicts(ctx, date(2026, 11, 18), date(2026, 11, 18), "Ankara")[0]["kind"] == "tatil"
    assert SV.conflicts(ctx, date(2026, 12, 8), date(2026, 12, 8), "Ankara") == []
    assert SV.conflicts(ctx, date(2026, 12, 8), date(2026, 12, 8), "İstanbul")[0]["name"] == "Deneme"


def test_numbers_from_the_model_must_come_from_the_facts():
    assert SV.numbers_ok("1.240 öğrencili okul", '{"ogrenci": 1240}')
    assert not SV.numbers_ok("Geçen yıl 35 kitap aldılar", '{"ogrenci": 1240}')


# ------------------------------------------------------------------ model


def test_model_links_visits_orders_and_books():
    m = _model()
    assert m.schools[S2]["students"] is None                              # TRY_CAST boş: bilinmiyor
    assert [v["id"] for v in m.visits[S1]] == ["e1"]
    assert [v["id"] for v in m.visits_by_name[S3]] == ["e2"]              # «USKUDAR ORTA OKULU» ad eşleşmesi
    assert [o["id"] for o in m.orders_by_school.get(S1, [])] == ["o1"]    # firma adı = okul adı
    assert m.prices["15201001"]["price"] == 130                           # genel liste önce
    fit = {b["code"] for b in m.fitting_books({1, 2, 3, 4})}
    assert fit == {"15201001", "15201004"}                                # stoksuz 15201003 düşer


def test_catalog_selection_never_cuts_when_all_is_asked():
    m = _model()
    sel = SV.select_catalog(m, m.schools[S1], {"adet": "hepsi"})
    assert sel["total"] == 2 and len(sel["items"]) == 2
    assert sel["items"][0]["code"] == "15201001"                           # ildeki bayi satışı önce
    capped = SV.select_catalog(m, m.schools[S1], {"adet": "hepsi", "fiyatUst": 100})
    assert [b["code"] for b in capped["items"]] == ["15201004"]


def test_dealer_candidates_prefer_same_district_and_grade_sales():
    m = _model()
    c = SV.dealer_candidates(m, m.schools[S1], linked_counts={}, risk={})
    assert c[0]["code"] == "120.01" and c[0]["sameIlce"] and c[0]["gradeSales"] == 300
    assert any("birlikte gidilmiş" in w for w in c[0]["why"])
    risky = SV.dealer_candidates(m, m.schools[S1], linked_counts={}, risk={"501": {"riskFill": 0.95}})
    assert risky[0]["warning"]


# ------------------------------------------------------------------ portal kayıtları


def test_visit_roundtrip_hides_secret_note(engine):
    m = _model()
    vals = SV.visit_values({"durum": "yapildi", "gerceklesen": "2026-09-20", "ilgi": "yuksek", "kisiRolu": "mudur",
                            "istenenKitaplar": ["15201001"], "not": "Sınıf seti istendi", "gizli": True,
                            "sonrakiAdim": "Teklif götür", "sonrakiTarih": "2026-10-05"}, m, date(2026, 9, 28))
    vid = SV.add_visit(engine, T, "ayse", "Ayşe", S1, vals)
    rows = SV.load_visits(engine, T, school=S1)
    assert len(rows) == 1 and rows[0]["tur"] == "okul" and rows[0]["hedef_kimlik"] == S1
    mine = SV.visit_view(rows[0], viewer="ayse", can_all=False)
    other = SV.visit_view(rows[0], viewer="mehmet", can_all=True)
    assert mine["note"] == "Sınıf seti istendi" and mine["books"][0]["title"] == "Minik Kaşif"
    assert other["note"] is None and other["hidden"]
    assert mine["tone"] == "olumlu" and mine["day"] == "2026-09-20"
    assert SV.last_visits(engine, T) == {S1: "2026-09-20"}
    assert SV.portal_owners(engine, T)[S1] == {"ayse"}
    assert vid


def test_visit_validation(engine):
    with pytest.raises(SV.SchoolError):
        SV.visit_values({"durum": "yapildi"}, None, date(2026, 9, 28))                    # ilgi seçilmedi
    with pytest.raises(SV.SchoolError):
        SV.visit_values({"durum": "yapildi", "ilgi": "orta", "gerceklesen": "2026-10-10"}, None, date(2026, 9, 28))
    with pytest.raises(SV.SchoolError):
        SV.visit_values({"durum": "yapildi", "ilgi": "orta", "bayiYonlendirildi": True}, None, date(2026, 9, 28))


def test_history_links_are_written_once_and_decisions_stick(engine):
    m = _model()
    assert SV.sync_history_links(engine, T, m)["created"] == 1
    assert SV.sync_history_links(engine, T, m)["created"] == 0
    links = SV.load_links(engine, T, school=S1)
    assert links[0]["kaynak"] == "gecmis" and links[0]["durum"] == "onayli" and links[0]["cari_kodu"] == "120.01"
    row = SV.add_link(engine, T, "ayse", S3, m.dealers["120.02"], kaynak="elle", durum="oneri", puan=None, gerekce=None)
    again = SV.add_link(engine, T, "ayse", S3, m.dealers["120.02"], kaynak="elle", durum="oneri", puan=None, gerekce=None)
    assert row["id"] == again["id"]
    done = SV.decide_link(engine, T, row["id"], "mudur", False, "Başka bayi")
    assert done["durum"] == "reddedildi" and "Başka bayi" in done["gerekce"]
    assert set(SV.approved_links(engine, T)) == {S1}


def test_plan_rows_and_update(engine):
    row = {"id": "p" * 32, "tenant_id": T, "sahip": "ayse", "sahip_ad": "Ayşe", "donem": "2026-2027/1", "hafta": date(2026, 9, 28),
           "gun": date(2026, 9, 29), "ziyaret_yeri_id": S1, "okul_adi": "Moda İlkokulu", "puan": 70.0, "gerekce": "x",
           "model_gerekce": None, "durum": "oneri", "not": None, "onaylayan": None, "onay_zamani": None, "olusturan": "ayse",
           "olusturma": datetime.now(timezone.utc), "guncelleyen": None, "guncelleme": None}
    SV.insert_plans(engine, [row])
    out = SV.update_plan(engine, T, "p" * 32, {"durum": "onayli", "onaylayan": "mudur"})
    assert out["durum"] == "onayli"
    assert SV.load_plans(engine, T, week=date(2026, 9, 28), owner="ayse")[0]["id"] == "p" * 32


# ------------------------------------------------------------------ yetki


def test_access_rules_for_schools():
    assert A.rule_for("/api/v1/schools") == {"sayfa:okul-tanitim"}
    assert A.rule_for(f"/api/v1/schools/{S1}/visits") == {"sayfa:okul-tanitim"}
    assert A.rule_for("/api/v1/schools/run-due") == A.SYSTEM
    f = A.features_for
    assert f("POST", f"/api/v1/schools/{S1}/visits") == ["ozellik:okul.ziyaret"]
    assert f("POST", "/api/v1/schools/plan/generate") == ["ozellik:okul.ziyaret"]
    assert f("PATCH", "/api/v1/schools/plan/" + "p" * 32) == ["ozellik:okul.ziyaret"]
    assert f("POST", "/api/v1/schools/plan/" + "p" * 32 + "/approve") == []             # okul.plan ucun içinde
    assert f("POST", f"/api/v1/schools/{S1}/dealers/x/approve") == []                   # açıkça verilen, ucun içinde
    assert f("POST", "/api/v1/schools/context/upload") == ["ozellik:okul.baglam-yukle"]
    assert f("GET", "/api/v1/schools/catalogs/abc.pdf") == ["ozellik:veri.disa-aktar"]
    assert f("POST", "/api/v1/schools/run-due") == []
    assert f("GET", f"/api/v1/schools/{S1}") == []
    assert "ozellik:okul.bayi-onay" in A.explicit_keys() and "ozellik:okul.herkesinki" in A.explicit_keys()


# ------------------------------------------------------------------ Zeki AI kapalı küme seçim


class _Choice:
    def __init__(self, choice, p, margin):
        self.choice, self.probability, self.margin, self.method = choice, p, margin, "logprobs"

    def confident(self, min_p, min_margin=0.0, min_coverage=0.0):
        return self.choice is not None and self.probability >= min_p and self.margin >= min_margin


class _ChooseLlm:
    def __init__(self, pick, p=0.95, margin=0.9):
        self.pick, self.p, self.margin, self.calls = pick, p, margin, []

    def choose(self, prompt, choices, system=None):
        self.calls.append(choices)
        return _Choice(choices[self.pick(choices)], self.p, self.margin)


def test_school_name_match_uses_closed_choice_with_threshold():
    m = _model()
    cands = [m.schools[S1], m.schools[S3]]
    sure = SV.ai_pick_school(_ChooseLlm(lambda cs: 1), "Üsküdar Orta", cands, 0.9, 0.5)
    assert sure["school"] == S3
    unsure = SV.ai_pick_school(_ChooseLlm(lambda cs: 1, p=0.6), "Üsküdar Orta", cands, 0.9, 0.5)
    assert unsure["available"] and unsure["school"] is None                 # emin değil → «belirsiz»
    none = SV.ai_pick_school(_ChooseLlm(lambda cs: len(cs) - 1), "Başka okul", cands, 0.9, 0.5)
    assert none["school"] == ""                                              # «Hiçbiri» → kalıcı ret
    assert SV.ai_pick_school(object(), "x", cands, 0.9, 0.5)["available"] is False   # kapısız istemci: karar yok


def test_dealer_pick_and_note_fields():
    m = _model()
    cands = SV.dealer_candidates(m, m.schools[S1], linked_counts={}, risk={})
    r = SV.ai_pick_dealer(_ChooseLlm(lambda cs: 1), m.schools[S1], cands, 0.7, 0.3)
    assert r["code"] == cands[1]["code"]
    llm = _ChooseLlm(lambda cs: 0)
    llm.chat = lambda messages, **kw: '{"kitaplar": ["Minik Kaşif"], "sonrakiAdim": "Teklif götür", "bayiYonlendirildi": true}'
    out = SV.ai_note_fields(llm, "Müdürle görüştüm, çok ilgili. Minik Kaşif istendi.", m.books, 0.7, 0.3)
    assert out["ilgi"] == "yuksek" and out["kisiRolu"] == "mudur"
    assert out["istenenKitaplar"] == [{"code": "15201001", "title": "Minik Kaşif"}] and out["bayiYonlendirildi"] is True
