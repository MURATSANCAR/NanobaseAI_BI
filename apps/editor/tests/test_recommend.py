"""Kategori ve yaş önerisi (editor.recommend): sitenin ağacı, eşleme, karşılaştırma, kayda geçiş — modelsiz."""
from pathlib import Path

import pytest

from editor import archive, recommend as R


def row(i, title, cat, isbn=None, authors=(), cats=None, sales=0):
    return {"id": f"tsoft-{i}", "title": title, "authors": list(authors), "isbn": isbn, "category": cat,
            "categories": cats if cats is not None else [cat], "page_url": f"https://x/{i}", "sales": sales}


ROWS = [
    row(1, "Meslekler", ["Çocuk", "Okul Öncesi"], isbn="978-605-08-1111-1", authors=["Ayşe Can"]),
    row(2, "Kayıp Şehir", ["Genç", "Gizem ve Macera"], cats=[["Genç", "Gizem ve Macera"], ["Çocuk", "9-12 Yaş"],
                                                            ["Çok Satan", "Çok Satan Çocuk Kitapları"]]),
    row(3, "Aile", ["Yetişkin", "Aile"], authors=["A Yazar"]),
    row(4, "AİLE", ["Yetişkin", "Psikoloji"], authors=["B Yazar"]),
    row(5, "Ramazan", ["Ramazan Kitapları"]),
]


def test_tree_is_reader_roots_without_age_leaves_or_showcases():
    t = R.tree(ROWS)
    assert "Çocuk > Okul Öncesi" in t and "Genç > Gizem ve Macera" in t and "Yetişkin > Psikoloji" in t
    assert "Çocuk > 9-12 Yaş" not in t                       # yaş ayrı alan
    assert not any(x.startswith(("Çok Satan", "Ramazan")) for x in t)   # vitrin/kampanya kökü
    assert t == sorted(t, key=lambda x: (R.fold(x), x))       # aynı girdi aynı istem


def test_age_leaf_parsing():
    assert R.age_of_path(["Çocuk", "9-12 Yaş"]) == (9, 12)
    assert R.age_of_path(["Çocuk", "13+ Yaş"]) == (13, None)
    assert R.age_of_path(["Çocuk", "Hikaye"]) is None


def test_match_isbn_first_then_unique_title_then_author():
    ix = R.SiteIndex(ROWS)
    assert R.match(ix, ["9786050811111"], ["başka ad"], [])["row"]["id"] == "tsoft-1"
    assert R.match(ix, [], ["MESLEKLER"], [])["by"] == "TITLE"
    # iki ürün aynı adı taşıyor: yazar yoksa eşleşme yok (tahmin yok), yazar tek ürüne indirirse o
    assert R.match(ix, [], ["Aile"], []) is None
    m = R.match(ix, [], ["Aile"], ["b yazar"])
    assert m["row"]["id"] == "tsoft-4" and m["by"] == "TITLE_AUTHOR"
    assert R.match(ix, [], ["Yok Böyle Kitap"], []) is None
    assert R.match(ix, [], ["1- Meslekler"], [])["row"]["id"] == "tsoft-1"     # sıra öneki ad değil
    assert R.match(ix, [], ["kayipsehir"], [])["row"]["id"] == "tsoft-2"       # dosya adında boşluk yok
    assert R.match(ix, ["123"], [], []) is None               # kısa sayı ISBN değil


def test_site_view_keeps_paths_as_is_and_reads_site_age():
    v = R.site_view(R.match(R.SiteIndex(ROWS), [], ["Kayıp Şehir"], []))
    assert v["found"] and v["categories"] == ["Genç > Gizem ve Macera", "Çocuk > 9-12 Yaş",
                                              "Çok Satan > Çok Satan Çocuk Kitapları"]
    assert (v["age_from"], v["age_to"]) == (9, 12)
    assert R.site_view(None) == {"found": False}


def rec(cat, aud, lo, hi):
    return {"status": "OK", "category": cat.split(" > "), "audience": aud, "age_from": lo, "age_to": hi}


def test_compare_only_site_vs_suggestion():
    site = R.site_view(R.match(R.SiteIndex(ROWS), [], ["Kayıp Şehir"], []))
    assert R.compare(site, rec("Genç > Gizem ve Macera", "YOUNG", 10, 14)) == {"review": False, "reasons": []}
    assert R.compare(site, rec("Genç", "YOUNG", 10, 12))["review"] is False          # ata yol uyumlu
    got = R.compare(site, rec("Yetişkin > Roman", "ADULT", 18, None))
    assert got["review"] and set(got["reasons"]) == {"AUDIENCE", "CATEGORY", "AGE"}
    # sitede yoksa ya da öneri yoksa gözden geçirme işareti yok
    assert R.compare({"found": False}, rec("Yetişkin > Roman", "ADULT", 18, None))["review"] is False
    assert R.compare(site, None)["review"] is False
    assert R.compare(site, {"status": "FAILED"})["review"] is False


def test_settle_closed_set_age_order_and_evidence():
    cats = R.tree(ROWS)
    out = R.settle({"category": "Çocuk > Okul Öncesi", "audience": "CHILD", "age_from": 6, "age_to": 3,
                    "confidence": "HIGH", "reason": " Kısa cümleler. ", "evidence_pages": [4, 4, 99]}, cats, [4, 7])
    assert out["category"] == ["Çocuk", "Okul Öncesi"] and (out["age_from"], out["age_to"]) == (3, 6)
    assert out["evidence_pages"] == [4] and out["reason"] == "Kısa cümleler."
    assert R.settle({"category": "Yetişkin > Aile", "audience": "ADULT", "age_from": 18, "age_to": 99,
                     "confidence": "LOW", "reason": "", "evidence_pages": [7]}, cats, [7])["age_to"] is None
    with pytest.raises(ValueError):
        R.settle({"category": "Uydurma > Yol", "audience": "ADULT", "age_from": 1, "age_to": 2,
                  "confidence": "LOW", "reason": "", "evidence_pages": []}, cats, [])


def test_schema_is_closed():
    s = R.schema(["Çocuk > Hikaye"], [3, 5])
    assert s["additionalProperties"] is False
    assert s["properties"]["category"]["enum"] == ["Çocuk > Hikaye"]
    assert s["properties"]["evidence_pages"]["items"]["enum"] == [3, 5]
    assert set(s["required"]) == set(s["properties"])


def test_sample_takes_short_picture_book_pages():
    pages = [{"page_no": n, "spans": [{"text": "Ali topu attı. Top uçtu gitti, Ayşe güldü."}]} for n in range(1, 25)]
    got = R._sample(pages)
    assert got and all(len(t) >= R.MIN_PAGE_CHARS for _, t in got)


def test_readability_is_deterministic():
    pages = [{"page_no": n, "spans": [{"text": "Ali topu attı. Top uçtu."}, {"text": "- Bak, top!"}]}
             for n in range(1, 21)]
    r = R.readability(pages)
    assert r == R.readability(pages)
    assert r["words_per_text_page"] == 7                      # 5 + 2 kelime
    assert r["words_per_sentence"] == round(7 / 3, 1)         # iki cümle + bir konuşma
    assert r["dialogue_share"] == 0.5
    assert r["syllables_per_word"] == round(sum([2, 2, 2, 1, 2, 1, 1]) / 7, 2)
    assert R.readability([])["words_per_text_page"] == 0


def test_prompt_carries_measures_and_age_scale():
    inp = {"title": "X", "pages": 24, "illustrated_pages": 20, "words_per_text_page": 9, "metadata": [],
           "readability": {"words_per_sentence": 5.2, "letters_per_word": 4.8, "syllables_per_word": 2.1,
                           "dialogue_share": 0.25},
           "book_summary": [], "chapters": [], "sample": []}
    p = R.prompt_text(inp, ["Çocuk > Hikaye"])
    assert "ortalama cümle uzunluğu: 5.2 kelime" in p and "%83" in p and "diyalog payı" in p and "%25" in p
    for step in ("0-3", "3-6", "6-9", "9-12", "12-17", "18+"):
        assert f"- {step}" in p
    assert "ölçülerin uyduğu basamak: 0-3" in p


def test_scale_band_from_measures_only():
    def inp(ill, pages, wpp, wps):
        return {"illustrated_pages": ill, "pages": pages, "words_per_text_page": wpp,
                "readability": {"words_per_sentence": wps}}
    assert R.scale_band(inp(29, 32, 32, 4.8)) == "3-6"        # resimli, kısa metin
    assert R.scale_band(inp(44, 128, 85, 4.9)) == "6-9"       # ilk okuma
    assert R.scale_band(inp(3, 208, 210, 9.5)) is None        # dolu sayfa: tavan yok
    assert R.scale_band(inp(0, 0, 0, 0)) is None
    p = R.prompt_text({**inp(3, 208, 210, 9.5), "title": "Y", "metadata": [], "book_summary": [], "chapters": [],
                       "sample": []}, ["Yetişkin > Roman"])
    assert "ölçülerin uyduğu basamak" not in p


def test_prompt_has_no_book_specific_rule_and_lists_tree():
    inp = {"title": "X", "pages": 24, "illustrated_pages": 20, "words_per_text_page": 9, "metadata": [],
           "book_summary": [{"text": "Bir çocuk.", "pages": [3]}], "chapters": [], "sample": [{"page": 5, "text": "a"}]}
    p = R.prompt_text(inp, ["Çocuk > Hikaye", "Yetişkin > Roman"])
    assert "Çocuk > Hikaye\nYetişkin > Roman" in p and "[sayfa 5]" in p
    assert R.shown_pages(inp) == [3, 5]


def test_attach_and_review_filter():
    books = [{"id": "b1", "title": "Kayıp Şehir", "category": "Kurgu", "read": None, "redaction": None, "proofed": False},
             {"id": "b2", "title": "Meslekler", "category": "Kurgu_Disi", "read": None, "redaction": None, "proofed": False},
             {"id": "b3", "title": "Bilinmez", "category": "Kurgu", "read": None, "redaction": None, "proofed": False}]
    extra = {"b1": {"rec": rec("Yetişkin > Roman", "ADULT", 18, None), "isbns": [], "titles": ["Kayıp Şehir"], "authors": []},
             "b2": {"rec": rec("Çocuk > Okul Öncesi", "CHILD", 3, 6), "isbns": [], "titles": ["Meslekler"], "authors": []}}
    R.attach(books, extra, R.SiteIndex(ROWS))
    assert books[0]["review"]["review"] and not books[1]["review"]["review"]
    assert books[2]["site"] == {"found": False} and books[2]["suggestion"] is None
    assert books[1]["suggestion"]["category"] == "Çocuk > Okul Öncesi"
    page = archive.select(books, review=True)
    assert [b["id"] for b in page["items"]] == ["b1"] and page["facets"]["review"] == 1
    assert archive.select(books)["total"] == 3


def test_migration_and_workflow_marker():
    root = Path(__file__).resolve().parents[1]
    sql = (root / "db" / "migrations" / "031_book_recommendation.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS book_recommendation" in sql
    wf = (root / "src" / "editor" / "workflow" / "workflows.py").read_text(encoding="utf-8")
    assert 'workflow.patched("archive-recommend-v1")' in wf
    i = wf.index('"archive_recommend"')
    assert wf.index("outputs_activity, gid") < i < wf.index('"finish_job", job_id, "SUCCEEDED", summary')
