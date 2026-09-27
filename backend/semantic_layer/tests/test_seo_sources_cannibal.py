"""SEO & GEO → yapay zekânın kaynakları (ai_sources.py) ve yarışan sayfalar (cannibal.py): saf işlevler."""
from datetime import datetime, timedelta, timezone

from semantic_bridge.seo_geo import ai_sources as src, cannibal as cb

OUR, RIVALS = "timas.com.tr", ["dr.com.tr", "idefix.com"]
T0 = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------------ alan adı

def test_registrable_domain_handles_country_second_level_and_platforms():
    assert src.registrable("https://m.dr.com.tr/kitap/x") == "dr.com.tr"
    assert src.registrable("https://tr.wikipedia.org/wiki/Timaş") == "wikipedia.org"
    assert src.registrable("www.bbc.co.uk") == "bbc.co.uk"
    assert src.registrable("https://ali.blogspot.com/2024/liste.html") == "ali.blogspot.com"
    assert src.registrable("https://veli.wordpress.com") == "veli.wordpress.com"
    assert src.registrable("kitapyurdu.com") == "kitapyurdu.com"


def test_gemini_redirect_takes_domain_from_title():
    url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH..."
    assert src.source_domain({"url": url, "title": "timas.com.tr"}) == ("timas.com.tr", True)
    assert src.source_domain({"url": url, "title": "www.hurriyet.com.tr"}) == ("hurriyet.com.tr", True)
    assert src.source_domain({"url": url, "title": "Wikipedia"}) == (src.UNKNOWN, True)


def test_plain_and_google_redirect_urls():
    assert src.source_domain({"url": "https://www.idefix.com/kitap/a", "title": "A"}) == ("idefix.com", False)
    assert src.source_domain({"url": "https://www.google.com/url?q=https://onedio.com/haber/x", "title": ""}) == (
        "onedio.com", True)


# ------------------------------------------------------------------ tür kuralları

def kind(domain, samples=()):
    return src.classify_domain(domain, OUR, RIVALS, samples)[0]


def test_classification_rules_in_order():
    assert kind("timas.com.tr") == "bizim"
    assert kind("dr.com.tr") == "rakip"                   # ayardaki liste
    assert kind("kitapyurdu.com") == "rakip"              # bilinen kitapçı
    assert kind("trendyol.com") == "pazaryeri"
    assert kind("wikipedia.org") == "ansiklopedi"
    assert kind("youtube.com") == "sosyal"
    assert kind("1000kitap.com") == "sosyal"
    assert kind("hurriyet.com.tr") == "haber"
    assert kind("yerelhaber.com") == "haber"              # adında "haber"
    assert kind("iskultur.com.tr") == "yayinevi"
    assert kind("mavikusyayinlari.com") == "yayinevi"     # adında "yayin"
    assert kind("ali.blogspot.com") == "blog"
    assert kind("kitapblogu.com") == "blog"
    assert kind(src.UNKNOWN) == "diger"
    assert kind("ornek.com") == "diger"


def test_blog_by_urls_and_titles():
    samples = [("https://ornek.com/blog/en-iyi-romanlar", "En iyi 10 roman"), ("https://ornek.com/iletisim", "İletişim")]
    assert kind("ornek.com", samples) == "blog"
    assert kind("ornek.com", [("https://ornek.com/a", "A"), ("https://ornek.com/b", "B")]) == "diger"


def test_rival_setting_wins_over_known_lists_and_our_site_first():
    typ, why = src.classify_domain("trendyol.com", OUR, ["trendyol.com"])
    assert typ == "rakip" and "Yönetim" in why
    assert src.classify_domain("timas.com.tr", "timas.com.tr", ["timas.com.tr"])[0] == "bizim"


# ------------------------------------------------------------------ toplama ve hedef listesi

def res(qid, engine, sources, mentioned=False, days=0):
    return {"id": f"{qid}-{engine}-{days}", "question_id": qid, "engine": engine, "asked_at": T0 + timedelta(days=days),
            "mentioned": mentioned, "cited": False, "sources": sources}


def c(url, title=""):
    return {"url": url, "title": title}


QUESTIONS = {"q1": {"text": "En iyi tarih kitapları", "category": None},
             "q2": {"text": "Osmanlı romanı önerisi", "category": None},
             "q3": {"text": "Çocuk kitabı önerisi", "category": None}}


def sample_results():
    red = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/x"
    return [
        res("q1", "gemini", [c(red, "hurriyet.com.tr"), c(red, "timas.com.tr")], mentioned=True),
        res("q1", "openai", [c("https://www.hurriyet.com.tr/kitap/a"), c("https://www.hurriyet.com.tr/kitap/b")]),
        res("q2", "openai", [c("https://www.hurriyet.com.tr/kitap/c"), c("https://onedio.com/haber/x")]),
        res("q3", "perplexity", [c("https://onedio.com/haber/y"), c("https://www.dr.com.tr/k")], days=1),
        res("q3", "gemini", [], days=1),
    ]


def test_aggregate_counts_answers_citations_questions_and_share():
    agg = src.aggregate(sample_results(), QUESTIONS, OUR, RIVALS)
    h = agg["domains"]["hurriyet.com.tr"]
    assert h["answers"] == 3 and h["citations"] == 4 and h["questionCount"] == 2
    assert h["engines"] == {"gemini": 1, "openai": 2}
    assert h["mentionedAnswers"] == 1 and abs(h["mentionShare"] - 1 / 3) < 1e-9
    assert abs(h["share"] - 3 / 5) < 1e-9
    s = agg["summary"]
    assert s["answers"] == 5 and s["answersWithSources"] == 4 and s["oursCited"] == 1 and s["mentioned"] == 1
    assert [t["date"] for t in agg["trend"]] == ["2026-09-20", "2026-09-21"]
    assert agg["trend"][0]["answers"] == 3 and agg["trend"][1]["withSources"] == 1


def test_engine_filter():
    agg = src.aggregate(sample_results(), QUESTIONS, OUR, RIVALS, engine="openai")
    assert agg["summary"]["answers"] == 2
    assert agg["domains"]["hurriyet.com.tr"]["answers"] == 2


def test_target_list_excludes_ours_rivals_and_mentioned():
    agg = src.aggregate(sample_results(), QUESTIONS, OUR, RIVALS)
    d = agg["domains"]
    # onedio: 2 soru, Timaş hiç anılmıyor → hedef. hurriyet: 3 cevabın 1'inde anılıyor (%33 > %25) → hedef değil.
    assert d["onedio.com"]["target"] is True
    assert d["hurriyet.com.tr"]["target"] is False
    assert d["timas.com.tr"]["target"] is False
    assert d["dr.com.tr"]["target"] is False
    assert [x["domain"] for x in src.rank(d.values(), "hedef")] == ["onedio.com"]


def test_single_question_is_not_a_target():
    agg = src.aggregate([res("q1", "openai", [c("https://ornek.com/a")])], QUESTIONS, OUR, RIVALS)
    assert agg["domains"]["ornek.com"]["target"] is False


def test_detail_view_lists_all_urls_questions_and_daily_share():
    agg = src.aggregate(sample_results(), QUESTIONS, OUR, RIVALS)
    v = src.view(agg["domains"]["hurriyet.com.tr"], QUESTIONS, full=True, trend=agg["trend"])
    assert v["urlCount"] == 4 and len(v["examples"]) == 4
    assert {q["text"] for q in v["questionList"]} == {"En iyi tarih kitapları", "Osmanlı romanı önerisi"}
    assert v["trend"][0] == {"date": "2026-09-20", "answers": 3, "total": 3, "share": 1.0}
    short = src.view(agg["domains"]["hurriyet.com.tr"], QUESTIONS)
    assert len(short["examples"]) == src.EXAMPLES_IN_LIST and short["urlCount"] == 4


def test_by_question_uses_latest_result_per_engine():
    rs = [res("q1", "openai", [c("https://a.com/x")]), res("q1", "openai", [c("https://b.com/y")], days=2)]
    out = src.by_question(rs, QUESTIONS, OUR, RIVALS)
    assert out[0]["engines"]["openai"]["sources"][0]["domain"] == "b.com"


# ------------------------------------------------------------------ yarışan sayfalar

def row(q, page, clicks, impr, pos):
    return {"keys": [q, page], "clicks": clicks, "impressions": impr, "position": pos}


def test_detect_needs_two_pages_with_impressions():
    rows = [row("kuyucaklı yusuf", "https://timas.com.tr/a", 10, 100, 6), row("kuyucaklı yusuf", "https://timas.com.tr/b", 2, 60, 8),
            row("kuyucaklı yusuf", "https://timas.com.tr/c", 0, 2, 40),     # eşik altı, sayılmaz
            row("tek sayfa", "https://timas.com.tr/a", 5, 100, 3),
            {"keys": ["sayfasız"], "clicks": 1, "impressions": 100, "position": 2}]
    groups = cb.detect(rows)
    assert [g["query"] for g in groups] == ["kuyucaklı yusuf"]
    g = groups[0]
    assert [p["url"] for p in g["pages"]] == ["https://timas.com.tr/a", "https://timas.com.tr/b"]
    assert g["impressions"] == 160 and abs(g["pages"][0]["share"] - 100 / 160) < 1e-9


def test_severity():
    def g(*pages):
        tot = sum(p[0] for p in pages)
        return {"pages": [{"impressions": i, "position": pos, "share": i / tot} for i, pos in pages]}
    assert cb.severity(g((100, 6), (60, 8))) == "zararli"
    assert cb.severity(g((100, 3), (60, 8))) == "izle"
    assert cb.severity(g((900, 7), (100, 9))) == "baskin"


def page(url, product=None, link_type=None):
    return {"url": url, "key": cb.path_key(url), "product": product, "linkType": link_type}


def prod(pid, name, active=True, barcode=None):
    return {"id": pid, "name": name, "names": [name], "active": active, "barcode": barcode}


def test_pair_types():
    p = page("https://timas.com.tr/kuyucakli-yusuf", prod("1", "Kuyucaklı Yusuf"))
    assert cb.pair_type(p, page("https://timas.com.tr/kuyucakli-yusuf?utm_source=x"))[0] == "kopya"
    assert cb.pair_type(p, page("https://timas.com.tr/Kuyucakli-Yusuf/"))[0] == "kopya"
    old = page("https://timas.com.tr/kuyucakli-yusuf-eski", prod("2", "Kuyucaklı Yusuf (Ciltli)", active=False))
    assert cb.pair_type(p, old)[0] == "baski"
    same_ean = page("https://timas.com.tr/x", prod("3", "Başka Ad", barcode="978"))
    assert cb.pair_type(page("https://timas.com.tr/y", prod("4", "Farklı", barcode="978")), same_ean)[0] == "baski"
    assert cb.pair_type(p, page("https://timas.com.tr/sabahattin-ali", link_type="model"))[0] == "urun_sayfa"
    assert cb.pair_type(page("https://timas.com.tr/roman", link_type="category"),
                        page("https://timas.com.tr/etiket/roman", link_type="tag"))[0] == "sayfa_sayfa"
    assert cb.pair_type(p, page("https://timas.com.tr/icimizdeki-seytan", prod("5", "İçimizdeki Şeytan")))[0] == "urun_urun"
    assert cb.pair_type(p, page("https://timas.com.tr/bilinmeyen"))[0] == "diger"


def test_same_title_ignores_edition_words_and_case():
    assert cb.same_title("KUYUCAKLI YUSUF - Yeni Baskı", "Kuyucaklı Yusuf (Karton Kapak)")
    assert not cb.same_title("Kuyucaklı Yusuf", "Kürk Mantolu Madonna")


def test_edition_action_redirects_inactive_to_active():
    a = page("https://timas.com.tr/a", prod("1", "Kitap Adı"))
    b = page("https://timas.com.tr/b", prod("2", "Kitap Adı", active=False))
    assert "301" in cb.action("baski", a, b)
    assert "canonical" in cb.action("baski", a, page("https://timas.com.tr/c", prod("3", "Kitap Adı")))


def test_annotate_rank_and_totals():
    rows = [row("kitap adı", "https://timas.com.tr/a", 10, 100, 6), row("kitap adı", "https://timas.com.tr/a?seux=1", 2, 60, 8),
            row("timaş roman", "https://timas.com.tr/r", 5, 50, 7), row("timaş roman", "https://timas.com.tr/s", 5, 50, 9)]
    products = {"/a": prod("1", "Kitap Adı")}
    items = cb.annotate(cb.detect(rows), products, {"/r": "category", "/s": "tag"})
    by_q = {i["query"]: i for i in items}
    assert by_q["kitap adı"]["types"] == ["kopya"] and by_q["kitap adı"]["pages"][0]["primary"]
    assert by_q["kitap adı"]["pages"][1]["product"]["id"] == "1"     # parametreli adres de aynı ürüne
    assert by_q["timaş roman"]["brand"] and by_q["timaş roman"]["types"] == ["sayfa_sayfa"]
    assert [i["query"] for i in cb.rank(items, "zararli", "0")] == ["kitap adı"]
    assert [i["query"] for i in cb.rank(items, "hepsi", "1")] == ["timaş roman"]
    assert cb.rank(items, "hepsi", "", "kopya")[0]["query"] == "kitap adı"
    t = cb.totals(items)
    assert t["severity"]["zararli"]["all"] == 2 and t["severity"]["zararli"]["nonBrand"] == 1
    assert t["types"]["kopya"] == 1 and t["types"]["sayfa_sayfa"] == 1
