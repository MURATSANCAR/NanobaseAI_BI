"""CRM bağlayıcısının başlık katlaması: dosya adından gelen başlık CRM adıyla eşleşmeli. Çalıştır:

    python3 apps/editor/tests/test_crm_fold.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "connectors"))

import crm_covers as C  # noqa: E402


def test_file_name_titles_fold_like_crm_titles():
    assert C.fold("Dilek Agaci.indd") == C.fold("Dilek Ağacı")
    assert C.fold("babamsultanabdulhamid-arsiv.pdf") == "babamsultanabdulhamid arsiv"
    assert C.fold("anne-terligi") == C.fold("Anne Terliği")
    assert C.fold("Kitap.Adı Devam") == "kitap adi devam"          # başlık içindeki nokta uzantı değil


def test_api_goes_to_card_service_when_configured_so():
    import io, json, os
    seen = []

    class _R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout=0):
        seen.append((req.full_url, req.get_header("Authorization")))
        return _R(json.dumps({"books": []}).encode())

    real, env = C.urllib.request.urlopen, dict(os.environ)
    C.urllib.request.urlopen = fake
    try:
        for k in ("EDITOR_API", "EDITOR_MCP_KEY"):
            os.environ.pop(k, None)
        os.environ.update(EDITOR_CATALOG_BASE="http://127.0.0.1:18889/", EDITOR_CATALOG_KEY="k1")
        C.api("requests"); C.api("store", {"book_id": "x"})
        os.environ.update(EDITOR_API="http://editor-mcp:8000", EDITOR_MCP_KEY="k2")
        C.api("requests")
    finally:
        C.urllib.request.urlopen = real
        os.environ.clear(); os.environ.update(env)
    assert seen == [("http://127.0.0.1:18889/v1/catalog/cover-requests", "Bearer k1"),
                    ("http://127.0.0.1:18889/v1/catalog/crm-lookups", "Bearer k1"),
                    ("http://editor-mcp:8000/catalog/cover-requests", "Bearer k2")]


def _book(i, name, author, urun=None, project=None):
    from datetime import datetime
    b = {"new_kitapId": i, "new_name": name, "new_KitabnAd": name, "new_urunadi": urun or name,
         "new_yazartext": author, "new_isbn13": None, "new_isbn": None, "new_projekarti": project,
         "ModifiedOn": datetime(2026, 1, int(i[-1]) + 1)}
    b["_titles"] = {t for t in (C.fold(b[k]) for k in ("new_name", "new_KitabnAd", "new_urunadi")) if t}
    b["_compact"] = {t.replace(" ", "") for t in b["_titles"]}
    b["_isbns"] = set()
    return b


def test_dash_or_space_inside_a_word_is_spelling():
    # CRM «E-beveyn», kitabın iç kapağı «Dİjİtal … e-beveyn», editör başlığı «Ebeveyn»
    crm = [_book("a1", "Dijital Dünyada E-beveyn Olmak", "Yazar Bir", project="p"),
           _book("a2", "Dijital Dünyada E-beveyn Olmak", "Yazar Bir", urun="Dijital Dünyada E-Beveyn Olmak"),
           _book("a3", "Yeterince İyi Ebeveyn Olmak", "Yazar İki"),
           _book("a4", "Doğal Ebeveynlik", "Yazar Üç")]
    for title in ("Dijital Dünyada Ebeveyn Olmak", "Dİjİtal Dünyada e-beveyn olmak", "DIJITAL DÜNYADA E BEVEYN OLMAK"):
        how, rows, _ = C.match(crm, [], title)
        assert {r["new_kitapId"] for r in rows} == {"a1", "a2"}, title
        assert how in ("COMPACT+EDITIONS", "TITLE+EDITIONS"), (title, how)
        assert rows[0]["new_kitapId"] == "a1"                      # proje kartı olan kayıt metni verir
    assert C.compact("Allah'ın İsimleri") == C.compact("Allahın İsimleri")


def test_compact_never_beats_an_equal_title_and_never_guesses():
    crm = [_book("b1", "Hoşça Kal", "Yazar Bir"), _book("b2", "Hoşçakal", "Yazar İki")]
    assert [r["new_kitapId"] for r in C.match(crm, [], "Hoşçakal")[1]] == ["b2"]     # tam ad önce
    assert [r["new_kitapId"] for r in C.match(crm, [], "Hoşça Kal")[1]] == ["b1"]
    # tam adı CRM'de olmayan bir yazım iki ayrı yazarın kitabına birden düşerse tahmin yok
    assert C.match(crm, [], "Hoş Çakal")[0] == "AMBIGUOUS"
    # editörün doğruladığı yazar ayırır
    assert [r["new_kitapId"] for r in C.match(crm, [], "Hoş Çakal", ["Yazar İki"])[1]] == ["b2"]
    # boşluksuz eşitlik bir kelimeyi yutamaz: farklı ad eşleşmez
    assert C.match(crm, [], "Hoşça Kalın")[0] == "NONE"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
