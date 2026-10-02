"""Kitabın kendisi olmayan sayfalar ve kitap özeti (2026-10-02 denetimi: 22 kitabın 22'sinde özet yedeğe düştü).

- Okumanın NON_STORY önerisi tek başına sayfayı çıkarmaz (kurgu dışı gövde); metni künye/tanıtım olan çıkar.
- Kapsam dışı sayfanın olay iddiası çıktıda kullanılmaz, silinmez.
- Olay özetinin uçları hikâye sayfalarıdır; yedek özet bütün kitaba sayfa dilimleriyle yayılır.
"""
import asyncio

from editor import outputs, page_scope

BODY = ("Ahlak, insanın yapıp etmelerini ve bu yapıp etmelerin dayandığı huyları inceleyen bir ilimdir; "
        "bu bölümde onun kaynakları ele alınır ve düşünürlerin görüşleri sırayla değerlendirilir.")


def _book(n=120):
    pages = {p: ["DENEME KİTABI", BODY, BODY] for p in range(1, n + 1)}
    pages[1] = ["İstanbul 2026"]
    pages[2] = ["DENEME KİTABI Ayşe Yılmaz", "ÖRNEK YAYINLARI", "EDİTÖR Ali Veli", "Yayın Yönetmeni Can Can",
                "ISBN 978-605-08-0000-0", "Yayıncı Sertifika No: 12364", "Baskı ve Cilt: Matbaa A.Ş."]
    pages[3] = ["Deneme Kitabı", "Ayşe Yılmaz"]
    pages[4] = ["AYŞE YILMAZ", "Ayşe Yılmaz 1980 yılında Konya'da doğdu. Lisans eğitimini Ankara'da tamamladı."]
    pages[5] = ["İÇİNDEKİLER", "Önsöz / 7 Giriş / 11 Birinci Bölüm / 15 İkinci Bölüm / 40"]
    pages[7] = ["Ekin’e, şu an birlikte koşup oynadıklarına ve onları sarıp sarmalayanlara...", "İstanbul 2025"]
    pages[8] = ["ÖNSÖZ", BODY]
    pages[n - 2] = ["Son bölümün son paragrafı burada biter.",
                    "Yeni kitap önerimiz için karekodu telefon kameranıza okutunuz."]
    pages[n - 1] = ["iyi ki kitaplar var...", "BAŞKA BİR KİTAP", "ZEYNEP KAYA", "Tanıtım yazısı burada."]
    pages[n] = []
    return pages


def test_suggestion_alone_never_removes_a_body_page():
    pages = _book()
    # okuma kurgu dışı gövdenin hepsine «hikâye dışı» dedi
    found = page_scope.classify(pages, set(range(1, 121)), 120, ["Deneme Kitabı"], ["Ayşe Yılmaz"])
    assert found[2] == ("FRONT_MATTER", "künye")
    assert found[3] == ("FRONT_MATTER", "iç kapak")
    assert found[4] == ("FRONT_MATTER", "yazar tanıtımı")
    assert found[5] == ("NON_STORY", "içindekiler")
    assert found[7] == ("NON_STORY", "ithaf")
    assert found[119] == ("NON_STORY", "yayınevi tanıtımı")
    for p in (8, 9, 60, 117, 118):            # önsöz, gövde; 118 yalnız kısmen tanıtım: sayfa kalır
        assert p not in found, p


def test_imprint_and_advert_tail_found_without_any_suggestion():
    pages = _book()
    found = page_scope.classify(pages, set(), 120, ["Deneme Kitabı"], [])
    assert found[2][0] == "FRONT_MATTER"       # güçlü künye işareti (ISBN + sertifika)
    assert found[119] == ("NON_STORY", "yayınevi tanıtımı")     # kitabın son sayfaları aday
    assert 4 not in found and 7 not in found   # yazar tanıtımı, ithaf yalnız öneriyle


def test_out_of_scope_only_from_editor_or_rule():
    roles = {2: {"role": "FRONT_MATTER", "source": "auto"}, 9: {"role": "NON_STORY", "source": "extract"},
             10: {"role": "NON_STORY", "source": "editor"}, 11: {"role": "STORY", "source": "editor"}}
    assert page_scope.out_of_scope(roles) == {2, 10}
    assert page_scope.scoped({"kind": "EVENT", "source_pages": [2, 3]}, {2})
    assert not page_scope.scoped({"kind": "METADATA", "source_pages": [2]}, {2})
    assert not page_scope.scoped({"kind": "EVENT", "source_pages": [9]}, {2, 10})


def _snap(n_pages=200, every=1, outside=()):
    claims, evidence, events = [], [], []
    for i, p in enumerate(range(1, n_pages + 1, every)):
        cid = f"c{i:04d}"
        claims.append({"id": cid, "kind": "EVENT", "claim": f"Olay {p}", "source_pages": [p], "payload": {},
                       "confidence": 0.9})
        evidence.append({"claim_id": cid, "id": f"e{i}", "quote_verified": True})
        events.append({"claim_id": cid, "importance": 0.9 if p % 10 == 0 else 0.3})
    return {"claims": claims, "evidence": evidence, "events": events, "generation_id": "g",
            "scope": {"out_of_scope_pages": list(outside)}}


def test_fallback_spreads_over_the_whole_book_with_both_ends():
    snap = _snap(200)
    rows = outputs.extractive(snap, snap["claims"])
    pages = [r["pages"][0] for r in rows]
    assert len(rows) == 24 and pages == sorted(pages)
    assert pages[0] == 1 and pages[-1] == 200
    # her 200/24 sayfalık dilimden bir iddia: hiçbir aralık iki dilimden geniş değil
    assert max(b - a for a, b in zip(pages, pages[1:])) <= 2 * 200 / 24 + 1
    # dilimin en önemli olayı seçilir (önemi yüksek: 10'un katları)
    assert sum(1 for p in pages[1:-1] if p % 10 == 0) >= 15


def test_fallback_skips_imprint_pages():
    snap = _snap(50, outside=(1, 2, 49, 50))
    rows = outputs.extractive(snap, snap["claims"])
    pages = [p for r in rows for p in r["pages"]]
    assert min(pages) == 3 and max(pages) == 48


def test_spread_fills_only_uncovered_slices():
    snap = _snap(100)
    chosen = {c["id"] for c in snap["claims"][:10]}         # model yalnız ilk 10 sayfadan seçti
    add = outputs.spread(snap, snap["claims"], 10, chosen)
    assert len(add) == 9                                    # ilk dilim dolu, kalan 9 dilimden birer
    assert min(c["source_pages"][0] for c in add) > 10


def test_plot_summary_ends_are_story_pages(monkeypatch):
    """Uç sayfa künye (s.2) ya da tanıtım değil: hikâyenin ilk ve son olayı."""
    snap = _snap(30, outside=())
    snap["claims"] = [c for c in snap["claims"] if c["source_pages"][0] not in (1, 2, 30)]
    asked = []

    class FakeLlm:
        def __init__(self, gid):
            pass

        async def chat(self, alias, messages, **kw):
            if kw["prompt"].name == "revision_summary":
                asked.append(messages[0]["content"])
                return {"sentences": [{"text": "Olay 3", "claim_ids": ["c0"]},
                                      {"text": "Olay 29", "claim_ids": [f"c{len(snap['claims']) - 1}"]}]}, 1
            return {"verdicts": [{"index": 0, "reason": "", "supported": True},
                                 {"index": 1, "reason": "", "supported": True}]}, 2

    import editor.llm as llm
    monkeypatch.setattr(llm, "Llm", FakeLlm)
    out = asyncio.run(outputs.summarize(snap, snap["claims"], "Kitabın olay örgüsü özeti", plot_only=True))
    assert out["status"] == "SOURCE_SUPPORTED_DRAFT"
    assert "Kitabın başı s.3–4, sonu s.28–29" in asked[0]


def test_edges_tolerate_one_paratext_event_at_the_very_end():
    claims = [{"source_pages": [p]} for p in range(1, 201)]
    (a, b), (c, d) = outputs.edge_pages(claims)
    assert (a, b) == (1, 10) and (c, d) == (191, 200)
