"""SEO & GEO → rakip sıralaması (competitors.py) ve kimlik hazırlığı (entity.py): saf yardımcılar."""
import json
from datetime import datetime

from semantic_bridge.seo_geo import competitors as comp
from semantic_bridge.seo_geo import entity


# ------------------------------------------------------------------ arama metni

def test_query_drops_parenthetical_suffix_and_adds_author():
    p = {"ProductName": "Kayıp Şehir (Ciltli) [Özel Baskı]", "Model": "Ahmet Ümit"}
    assert comp.build_query(p) == "Kayıp Şehir Ahmet Ümit"


def test_query_does_not_repeat_author_already_in_title():
    p = {"ProductName": "Cemil Meriç Bütün Eserleri", "Model": "Cemil Meriç"}
    assert comp.build_query(p) == "Cemil Meriç Bütün Eserleri"


def test_query_without_author():
    assert comp.build_query({"ProductName": "Defter (Çizgili)"}) == "Defter"


# ------------------------------------------------------------------ alan adı eşleşmesi ve sıralar

def test_domain_matching_includes_subdomains_not_lookalikes():
    assert comp.matches("m.dr.com.tr", "dr.com.tr")
    assert comp.matches("www.dr.com.tr", "https://dr.com.tr/")
    assert not comp.matches("xdr.com.tr", "dr.com.tr")
    assert comp.domain_of("https://WWW.Timas.com.tr/kitap?x=1") == "timas.com.tr"
    assert comp.parse_domains("https://www.dr.com.tr, kitapyurdu.com ;dr.com.tr") == ["dr.com.tr", "kitapyurdu.com"]


SERP = {
    "organic_results": [
        {"position": 1, "link": "https://www.kitapyurdu.com/kitap/kayip-sehir/1.html", "title": "Kayıp Şehir"},
        {"position": 2, "link": "https://m.dr.com.tr/kitap/kayip-sehir", "title": "Kayıp Şehir - D&R"},
        {"position": 3, "link": "https://timas.com.tr/kayip-sehir", "title": "Kayıp Şehir | Timaş"},
        {"position": 7, "link": "https://www.dr.com.tr/yazar/ahmet-umit", "title": "Ahmet Ümit"},
    ],
    "inline_shopping": [{"source": "Timaş Yayınları", "link": "https://www.google.com/shopping/x"}],
    "ai_overview": {"page_token": "abc"},
    "knowledge_graph": {"title": "Ahmet Ümit"},
}


def test_positions_per_domain_best_rank():
    res = comp.organic(SERP)
    p = comp.positions(res, ["timas.com.tr", "dr.com.tr", "kitapyurdu.com", "idefix.com"])
    assert p == {"timas.com.tr": 3, "dr.com.tr": 2, "kitapyurdu.com": 1, "idefix.com": None}


def test_verdict_behind_ahead_absent():
    assert comp.verdict(3, {"dr.com.tr": 2, "idefix.com": None}) == ("geride", {"domain": "dr.com.tr", "position": 2})
    assert comp.verdict(1, {"dr.com.tr": 2})[0] == "onde"
    assert comp.verdict(4, {"dr.com.tr": None})[0] == "onde"
    assert comp.verdict(None, {"dr.com.tr": 5})[0] == "yok"


def test_page_features():
    f = comp.features(SERP, "timas.com.tr")
    assert f["shopping"] and f["shoppingUs"]
    assert f["aiOverview"] and f["aiOverviewUs"] is None      # yalnız sayfa belirteci: kaynaklar bilinmez
    assert f["knowledgePanel"]
    empty = comp.features({}, "timas.com.tr")
    assert not any(empty[k] for k in ("shopping", "aiOverview", "knowledgePanel"))


def test_ai_overview_references_cite_us():
    f = comp.features({"ai_overview": {"references": [{"link": "https://www.timas.com.tr/x"}]}}, "timas.com.tr")
    assert f["aiOverviewUs"] is True


# ------------------------------------------------------------------ kota dilimi

def test_quota_slice_spreads_remaining_over_days_left():
    assert comp.slice_size(240, 0, datetime(2026, 9, 1)) == 8            # 240 / 30
    assert comp.slice_size(240, 200, datetime(2026, 9, 27)) == 10        # 40 / 4 gün (27-30)
    assert comp.slice_size(240, 239, datetime(2026, 9, 30)) == 1
    assert comp.slice_size(240, 240, datetime(2026, 9, 15)) == 0
    assert comp.slice_size(240, 300, datetime(2026, 9, 15)) == 0
    assert comp.slice_size(10, 0, datetime(2026, 2, 28)) == 10          # ayın son günü: kalanın hepsi


# ------------------------------------------------------------------ Wikidata sınıflandırması

def ent(qid, lab, website=None, human=False, **claims):
    c = {}
    if website:
        c["P856"] = [{"mainsnak": {"datavalue": {"value": website}}}]
    if human:
        c["P31"] = [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]
    for prop, vals in claims.items():
        c[prop] = [{"mainsnak": {"datavalue": {"value": v}}} for v in vals]
    return {"id": qid, "labels": {"tr": {"value": lab}}, "claims": c}


def test_pick_org_prefers_official_website():
    ents = {"Q1": ent("Q1", "Timaş Yayınları"), "Q2": ent("Q2", "Timaş Yayın Grubu", website="https://www.timas.com.tr/")}
    assert entity.pick_org(["Q1", "Q2"], ents, "https://timas.com.tr") == ("Q2", "site")


def test_pick_org_by_exact_name_or_ambiguous():
    ents = {"Q1": ent("Q1", "Timaş Yayınları"), "Q3": ent("Q3", "Timaş", human=True)}
    assert entity.pick_org(["Q1", "Q3"], ents, "https://timas.com.tr") == ("Q1", "ad")
    two = {"Q1": ent("Q1", "Timaş Yayınları"), "Q4": ent("Q4", "TİMAŞ YAYINLARI")}
    assert entity.pick_org(["Q1", "Q4"], two, "https://timas.com.tr") == (None, "belirsiz")
    assert entity.pick_org([], {}, "https://timas.com.tr") == (None, "yok")


def test_author_status_from_lookup():
    assert entity.author_status({"status": "bulundu", "facts": {"wikipedia": "https://tr.wikipedia.org/wiki/X"}}) == "wikipedia"
    assert entity.author_status({"status": "bulundu", "facts": {"wikipedia": None}}) == "wikidata"
    assert entity.author_status({"status": "belirsiz"}) == "belirsiz"
    assert entity.author_status({"status": "yok"}) == "yok"
    assert entity.author_needs("yok") and entity.author_needs("belirsiz")


def test_split_authors():
    assert entity.split_authors("Ahmet Ümit, Ayşe Kulin & Can Dündar") == ["Ahmet Ümit", "Ayşe Kulin", "Can Dündar"]
    assert entity.split_authors(None) == []


# ------------------------------------------------------------------ Organization JSON-LD önerisi

WD = entity.org_facts({
    **ent("Q123", "Timaş Yayınları", website="https://timas.com.tr", P2003=["timasyayinlari"], P2002=["timasyayinlari"],
          P571=[{"time": "+1982-00-00T00:00:00Z"}]),
    "sitelinks": {"trwiki": {"title": "Timaş Yayınları"}},
})


def test_org_facts_reads_socials_and_wikipedia():
    assert WD["url"] == "https://www.wikidata.org/wiki/Q123"
    assert WD["wikipedia"]["trwiki"] == "https://tr.wikipedia.org/wiki/Tima%C5%9F_Yay%C4%B1nlar%C4%B1"
    assert [s["network"] for s in WD["socials"]] == ["Instagram", "X (Twitter)"]
    assert WD["inception"] == "1982"


def test_sameas_recommendation_merges_and_dedupes():
    current = ["https://instagram.com/timasyayinlari", "https://www.facebook.com/timasyayinlari/"]
    got = entity.recommend_sameas(WD, current)
    assert got[0] == "https://www.wikidata.org/wiki/Q123"
    assert got[1].startswith("https://tr.wikipedia.org/")
    assert "https://www.instagram.com/timasyayinlari/" in got
    assert "https://instagram.com/timasyayinlari" not in got          # aynı hesap, www farkı
    assert "https://www.facebook.com/timasyayinlari/" in got           # sayfada olan korunur
    ld = entity.org_jsonld("https://timas.com.tr", WD, {"logo": {"url": "https://timas.com.tr/logo.png"}})
    assert ld["name"] == "Timaş Yayınları" and ld["logo"] == "https://timas.com.tr/logo.png"
    assert ld["foundingDate"] == "1982" and ld["sameAs"] == entity.recommend_sameas(WD, None)
    json.dumps(ld)


def test_org_checklist():
    site_org = {"@type": "Organization", "name": "Timaş", "logo": None, "sameAs": ["https://www.wikidata.org/wiki/Q123"]}
    checks = {c["id"]: c["ok"] for c in entity.org_checks(WD, "site", site_org, True, "https://timas.com.tr")}
    assert checks["wikidata"] and checks["wikidata_site"] and checks["wikidata_social"] and checks["wikipedia"]
    assert checks["site_org"] and not checks["site_name"] and not checks["site_logo"]
    assert checks["sameas_wikidata"] and not checks["sameas_wikipedia"] and not checks["sameas_social"]
    unread = {c["id"]: c["ok"] for c in entity.org_checks(None, "yok", None, False, "https://timas.com.tr")}
    assert unread == {"wikidata": False, "site_org": None}


# ------------------------------------------------------------------ ISBN ve Google Kitaplar

def test_isbn_variants_for_turkish_groups():
    v = entity.isbn_variants("9786051234567")
    assert v[0] == "9786051234567" and "978-605-12-3456-7" in v and "978-605-1234-56-7" in v
    assert entity.isbn_variants("9780306406157") == ["9780306406157"]
    assert entity.isbn13("978-605-12-3456-7") == "9786051234567" and entity.isbn13("8690000000000") is None


def test_google_books_checks():
    ok = entity.gb_checks("9786051234567", {"rights": "var", "statusFlag": None, "previewPdf": "https://x/pdf"}, "https://img")
    assert all(ok.values())
    bad = entity.gb_checks(None, {"rights": "eksik", "statusFlag": "cekildi", "previewPdf": None}, None)
    assert not any(bad.values())
    assert entity.gb_checks("9786051234567", None, "https://img") == {
        "isbn": True, "rights": False, "status": False, "cover": True, "pdf": False}
