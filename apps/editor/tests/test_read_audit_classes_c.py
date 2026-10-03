"""Okuma denetimi düzeltmeleri C (2026-10-03, arşiv pilotu): genel hata sınıfları K10–K12 ve arama dizini temizliği.
Hiçbir kitap, ad ya da sayfa numarası koddan okunmaz; buradaki adlar ve metinler elle yazılmıştır. Model, geçit,
veritabanı ve Qdrant yok — taklit edilir; PDF'ler pymupdf ile burada çizilir.

K10. Yazısı çizime çevrilmiş (metin katmanı yok, raster resim yok, mürekkep var) sayfa OCR'a ve görsel taramaya girer
     (NO_LAYER_WITH_INK); boş/beyaz sayfa girmez.
K11. Kitap olmayan dosya (katalog, bülten, broşür, yalnız kapak) NOT_A_BOOK: karakter/olay/duygu okunmaz, öneri yok,
     listede «kitap değil»; etkinlik/boyama kitabı ve künyeli/tanıtımlı gerçek kitap kitaptır.
K12. Uç sayfalar kitap uzunluğuna göre: resimli kitapta s.3 ithafı, okumanın önerisi olmayan yazar özgeçmişi, arka kapak
     tanıtımı, başlıksız yazar notu kapsam dışı; gövdenin ilk sayfası ve biyografi kitabının gövdesi kapsamda kalır.
Ek.  Arama dizini: aynı neslin eski yapı anahtarlı noktaları silinir, güncel olana dokunulmaz.
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


def _missing(root: str) -> bool:
    try:
        return importlib.util.find_spec(root) is None
    except ValueError:
        return False


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool", "httpx", "yaml"):
    _root = _mod.split(".")[0]
    if _missing(_root) or _root in sys.modules and isinstance(sys.modules[_root], _Stub):
        sys.modules.setdefault(_mod, _Stub(_mod))

from editor import book_type as bt, page_scope  # noqa: E402

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "editor"
DB = pathlib.Path(__file__).resolve().parents[1] / "db" / "migrations"

BODY = ("Sabah erkenden kalktı ve dükkânın kepengini yavaşça kaldırdı, içeri serin bir koku doldu; sokak "
        "henüz uyanmamıştı ve martılar çatıların üstünde dönüp duruyordu, uzakta bir vapur düdüğü duyuldu.")


# ------------------------------------------------------------------ K10 metin katmanı yok, mürekkep var
def test_layerless_ink_rule():
    from editor import document as D
    assert D.layerless_with_ink(2, 0, 0.05)
    assert D.layerless_with_ink(0, 0, D.LAYERLESS_INK_MIN)
    assert not D.layerless_with_ink(0, 0, 0.004)            # boş/beyaz sayfa (ölçülen boş sayfalar ≤ 0,005)
    assert not D.layerless_with_ink(0, 0, None)
    assert not D.layerless_with_ink(120, 0, 0.3)            # metin katmanı var
    assert not D.layerless_with_ink(0, 1, 0.3)              # raster resim: NO_LAYER_WITH_IMAGES zaten açar


def _outlined_pdf(path: pathlib.Path, kinds: list[str]) -> pathlib.Path:
    """kinds: outlined (yazı yerine dolu vektör yollar) | blank | text | outlined_two (2 karakterlik katman + yollar)."""
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    for k in kinds:
        p = doc.new_page(width=400, height=600)
        if k == "text":
            y = 60
            for _ in range(20):
                p.insert_text((40, y), "Bir varmış bir yokmuş, evvel zaman içinde, kalbur saman içinde.", fontsize=10)
                y += 18
        if k.startswith("outlined"):
            # yazıya çevrilmiş satır: her satır harf gövdesi gibi küçük dolu dikdörtgenlerden TEK yol (gerçek dizgi
            # programı satırı/paragrafı birleşik yol olarak verir: çizim sayısı 40'ın altında kalır), katman boş
            for row in range(18):
                sh = p.new_shape()
                for col in range(30):
                    x, y = 40 + col * 10.5, 70 + row * 25
                    sh.draw_rect(pymupdf.Rect(x, y, x + 6, y + 9))
                sh.finish(color=(0, 0, 0), fill=(0, 0, 0))
                sh.commit()
        if k == "outlined_two":
            p.insert_text((40, 40), "1.", fontsize=8)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path


class _J:
    def __init__(self, obj):
        self.obj = obj


class _Conn:
    def __init__(self):
        self.rows = []

    def execute(self, sql, row=None):
        self.rows.append(row)


def test_manifest_gives_outlined_pages_an_ocr_reason(tmp_path, monkeypatch):
    pymupdf = pytest.importorskip("pymupdf")
    import contextlib
    from editor import document as D
    pdf = _outlined_pdf(tmp_path / "k.pdf", ["outlined", "blank", "text", "outlined_two"])
    conn = _Conn()
    monkeypatch.setattr(D, "_open_version", lambda bv, repair=True: (pymupdf.open(pdf), {"id": "bv"}))
    monkeypatch.setattr(D, "render_page", lambda bv, i: {"path": f"p{i}.png", "dpi": 100})
    monkeypatch.setattr(D.db, "J", _J, raising=False)
    monkeypatch.setattr(D.db, "tx", lambda: contextlib.nullcontext(conn), raising=False)
    out = D.create_page_manifest("bv")
    assert out["needs_ocr"] == [1, 4]
    reasons = {r[1]: r[10].obj["ocr_reasons"] for r in conn.rows}
    assert reasons[1] == ["NO_LAYER_WITH_INK"] and "NO_LAYER_WITH_INK" in reasons[4]
    assert reasons[2] == [] and reasons[3] == []           # boş sayfa ve düz metin sayfası OCR'a gitmez


def test_archive_visual_pages_take_outlined_pages(tmp_path, monkeypatch):
    pymupdf = pytest.importorskip("pymupdf")
    from editor import archive as A, document
    pdf = _outlined_pdf(tmp_path / "k.pdf", ["text", "outlined", "blank", "text", "outlined_two"])
    monkeypatch.setattr(document, "_open_version", lambda bv, repair=True: (pymupdf.open(pdf), {}))
    out = A.visual_pages("bv")
    assert all(A.measure_page(pg)[1] < A.MIN_DRAWINGS for pg in pymupdf.open(pdf))   # çizim sayısıyla seçilmez
    assert out["pages"] == [1, 2, 5]                       # kapak + yazısı çizime çevrilmiş iki sayfa
    assert out["rule"]["layerless_ink"] == document.LAYERLESS_INK_MIN
    # ön tarama satırı da aynı kuralla (üçlü ölçü)
    assert A.page_is_visual(0.0, 3, True) and not A.page_is_visual(0.0, 3, False)
    assert A.select_visual([(0.0, 0), (0.0, 3, True), (0.0, 3, False)]) == [1, 2]


def test_vision_does_not_skip_a_light_outlined_page():
    src = (SRC / "vision.py").read_text()
    assert "NO_LAYER_WITH_INK" in src and "drawn_text" in src


# ------------------------------------------------------------------ K11 kitap değil
CATALOGUE_PAGE = ("Kuş Kanadında Masallar 7+ yaş Yazar: Deniz Ak 96 sayfa 13,5 x 21 cm ISBN 978-605-000-111-2 "
                  "Fiyatı: 120,00 TL Ormanda Bir Gün 5+ yaş 48 sayfa 20 x 20 cm ISBN 978-605-000-222-9 90,00 TL")
NOVEL = BODY + " " + BODY


def test_few_pages_is_not_a_book():
    assert bt.not_a_book(["Kapak"], 1) == {"reason": "FEW_PAGES", "pages": 1}
    assert bt.not_a_book([NOVEL] * 4, 4)["reason"] == "FEW_PAGES"
    assert bt.not_a_book([NOVEL] * 16, 16) is None               # en kısa resimli kitaplar 16 sayfa


def test_catalogue_is_not_a_book():
    texts = ["Katalog", "Değerli okurlarımız, bu yıl yayımladığımız kitaplar..."] + [CATALOGUE_PAGE] * 20 + [NOVEL] * 6
    got = bt.not_a_book(texts, len(texts))
    assert got["reason"] == "CATALOGUE" and got["listing_pages"] == 20
    assert bt.listing_page(CATALOGUE_PAGE)


@pytest.mark.parametrize("texts", [
    # künye sayfası (bir ISBN, bir ebat) + arka sayfalarda üç kitap tanıtımı: kitap
    ["İstanbul 2026", "Yayın Yönetmeni: Ali Veli ISBN 978-605-000-333-6 Sertifika No: 1 13,5 x 21 cm"]
    + [NOVEL] * 190 + [CATALOGUE_PAGE] * 3,
    # etkinlik/boyama kitabı: kısa yönergeler, fiyat ya da ISBN dizisi yok
    ["Bu kitabın sahibi:"] + ["Resmi boya. Noktaları birleştir ve çiz. Kaç tane elma var? Say ve yaz."] * 23,
])
def test_real_books_are_books(texts):
    assert bt.not_a_book(texts, len(texts)) is None


def test_not_a_book_form_and_prompt():
    p = {"form": bt.NOT_A_BOOK, "audience": "CHILD", "pages": 32, "illustrated_pages": 30}
    assert not bt.is_book(p) and bt.is_book({"form": "ACTIVITY"}) and bt.is_book(None)
    assert not bt.is_story(p)
    assert "kitap olmayan" in bt.describe(p)
    prompt = bt.classify_prompt("Deneme", [], ["FICTION", bt.NOT_A_BOOK], [(5, "metin")])
    assert "N = kitap değil" in prompt and "etkinlik ve boyama kitabı kitaptır" in prompt
    assert "NOT_A_BOOK" in (DB / "032_not_a_book.sql").read_text()


def test_model_choice_always_offers_not_a_book(monkeypatch):
    seen = {}

    class FakeLlm:
        def __init__(self, gid):
            pass

        async def choose(self, alias, messages, letters, pages=None):
            seen["letters"] = letters
            return {"N": 0.9, "K": 0.1}, 7

    from editor import source
    monkeypatch.setattr(source, "read", lambda gid: [{"page_no": i, "spans": [{"text": NOVEL}]} for i in range(1, 41)])
    fake_llm = types.ModuleType("editor.llm")
    fake_llm.Llm = FakeLlm
    fake_knowledge = types.ModuleType("editor.knowledge")
    fake_knowledge.DIRECTOR = "book-director"
    monkeypatch.setitem(sys.modules, "editor.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "editor.knowledge", fake_knowledge)
    got = asyncio.run(bt._model_form("g", "Deneme", [], ["FICTION"]))
    assert seen["letters"] == ["K", "N"] and got["form"] == bt.NOT_A_BOOK


def test_profile_takes_the_rule_before_shelf_and_model(monkeypatch):
    stored = {}

    def one(sql, *args):
        if sql.startswith("SELECT * FROM book_profile"):
            return stored.get("row")
        if "FROM generation g" in sql and "b.title" in sql:
            return {"book_id": "b1", "title": "katalog", "book_version_id": "bv1"}
        if "FROM book_crm_record" in sql:
            return None
        if "FROM page" in sql:
            return {"n": 32, "drawn": 30}
        if sql.startswith("INSERT INTO book_profile"):
            keys = ("generation_id", "form", "form_source", "form_detail", "audience", "audience_source",
                    "age_from", "age_to", "illustrated_pages", "pages", "model_call_id")
            stored["row"] = dict(zip(keys, args))
            return {"generation_id": args[0]}
        raise AssertionError(sql)

    async def no_model(*a):
        raise AssertionError("model sorulmamalı")

    monkeypatch.setattr(bt.db, "one", one, raising=False)
    monkeypatch.setattr(bt.db, "J", lambda v: v, raising=False)
    monkeypatch.setattr(bt, "settings", lambda: type("S", (), {"min_illustration_ink": 0.02})())
    monkeypatch.setattr(bt, "_archive_hint", lambda gid: {"audience": "CHILD", "forms": ["FICTION"]})
    monkeypatch.setattr(bt, "_refresh_from_crm", lambda row: None)
    monkeypatch.setattr(bt, "_model_form", no_model)
    monkeypatch.setattr(bt, "_not_a_book_of", lambda gid, n: {"reason": "CATALOGUE", "listing_pages": 21})
    row = asyncio.run(bt.profile("g1"))
    assert (row["form"], row["form_source"]) == (bt.NOT_A_BOOK, "RULE")
    assert row["form_detail"]["not_a_book"]["reason"] == "CATALOGUE"


def test_not_a_book_reads_no_characters_events_or_emotions(monkeypatch):
    pytest.importorskip("temporalio")
    from editor.workflow import activities as act

    async def prof(gid):
        return {"form": bt.NOT_A_BOOK}

    def boom(*a, **k):
        raise AssertionError("kitap olmayan dosyada okuma adımı koşmamalı")

    monkeypatch.setattr(act.book_type, "profile", prof)
    monkeypatch.setattr(act.knowledge, "text_chunks", boom)
    monkeypatch.setattr(act.knowledge, "link_emotions_and_themes", boom)
    assert asyncio.run(act.text_chunks("g")) == []
    assert asyncio.run(act.emotions_themes("g")) == {"skipped": bt.NOT_A_BOOK}


def test_no_recommendation_for_not_a_book(monkeypatch):
    from editor import recommend as R

    async def boom(*a, **k):
        raise AssertionError("öneri modeli çağrılmamalı")

    monkeypatch.setattr(R.db, "one", lambda sql, *a: {"form": bt.NOT_A_BOOK}, raising=False)
    monkeypatch.setattr(R, "suggest", boom)
    assert asyncio.run(R.run("g")) == {"status": bt.NOT_A_BOOK, "skipped": True}


def test_listing_marks_not_a_book_and_hides_suggestion():
    from editor import recommend as R
    rec = {"status": "OK", "category": ["Çocuk", "Masal"], "audience": "CHILD", "age_from": 6, "age_to": 9,
           "confidence": "HIGH", "reason": "r", "evidence_pages": [3]}
    books = [{"id": "a", "title": "Katalog"}, {"id": "b", "title": "Masal"}]
    extra = {"a": {"rec": rec, "isbns": [], "titles": ["Katalog"], "authors": [],
                   "not_a_book": R.not_a_book_view({"form": bt.NOT_A_BOOK, "detail": {"reason": "CATALOGUE"}})},
             "b": {"rec": rec, "isbns": [], "titles": ["Masal"], "authors": [], "not_a_book": None}}
    R.attach(books, extra, [])
    assert books[0]["not_a_book"] == {"reason": "CATALOGUE"} and books[0]["suggestion"] is None
    assert books[0]["review"]["review"] is False
    assert books[1]["not_a_book"] is None and books[1]["suggestion"]["confidence"] == "HIGH"
    assert R.not_a_book_view({"form": "FICTION"}) is None
    assert R.not_a_book_view({"form": bt.NOT_A_BOOK, "detail": None}) == {"reason": "MODEL"}


def test_card_profile_says_not_a_book():
    from editor import presentation as P
    p = {"form": bt.NOT_A_BOOK, "form_source": "RULE", "audience": "UNKNOWN",
         "form_detail": {"not_a_book": {"reason": "FEW_PAGES", "pages": 2}}}
    assert P.profile_view(p)["notABook"] == {"reason": "FEW_PAGES"}
    assert P.profile_view({**p, "form": "FICTION", "form_detail": {}})["notABook"] is None


def test_screens_show_not_a_book_badge():
    root = pathlib.Path(__file__).resolve().parents[3]
    labels = (root / "src/canvas/editorial/pharmacy/labels.ts").read_text()
    row = (root / "src/canvas/editorial/pharmacy/PharmacyScreen.tsx").read_text()
    detail = (root / "src/canvas/editorial/pharmacy/PharmacyDetail.tsx").read_text()
    assert "Kitap değil" in row and "Kitap değil" in detail and "notABookText" in labels
    for text in (labels, row, detail):
        assert "'NOT_A_BOOK'" not in text and ">NOT_A_BOOK" not in text   # ekranda kod adı yazılmaz


# ------------------------------------------------------------------ K12 uç sayfalar
def _picture_book(n=32, author="Deniz Ayaz"):
    pages = {p: [BODY] for p in range(5, n + 1)}
    pages[1] = ["ÖRNEK YAYINLARI İSTANBUL 2025"]
    pages[2] = ["Yayın Yönetmeni Ali Veli", "Editör Can Can", "ISBN 978-605-000-444-3", "Sertifika No: 12364",
                "Baskı ve Cilt: Matbaa A.Ş."]
    pages[3] = ["Mavi Ayaz’a, kitap okumayı seven bütün çocuklara ve öğretmenlerine", "ornekcocuk.com"]
    pages[4] = [f"{author.upper()}", f"{author} 1980 yılında İzmir’de doğdu. Üniversiteden mezun oldu. "
                "Çocuklar için yazdığı kitapları birçok dile çevrildi."]
    return pages


def test_dedication_on_page_three_of_a_picture_book():
    found = page_scope.classify(_picture_book(), set(), 32, ["Örnek Kitap"], [])
    assert found[3] == ("NON_STORY", "ithaf")
    # okumanın önerisi olmasa da yazar özgeçmişi (yazarlık sözüyle; ad bilinmiyor)
    assert found[4] == ("FRONT_MATTER", "yazar tanıtımı")
    assert 5 not in found and 6 not in found                      # gövdenin ilk sayfaları kalır


def test_dedicated_person_is_not_a_character():
    found = page_scope.classify(_picture_book(), set(), 32, ["Örnek Kitap"], [])
    roles = {p: {"role": r, "source": "auto"} for p, (r, _) in found.items()}
    out = page_scope.out_of_scope(roles)
    chars = [{"id": "c1"}, {"id": "c2"}]
    # ithaftaki kişi yalnız s.3'te anılıyor: gizlenir; gövdedeki kişi kalır
    assert page_scope.characters_outside(chars, {"c1": {3}, "c2": {3, 7}}, out) == {"c1"}


@pytest.mark.parametrize("lines", [
    ["Mert’e annesi bir hediye aldı."],                           # gövde cümlesi, yönelme ekli adla açılıyor
    ["“Bugün parka gidiyoruz!”"],                                 # tek konuşma: s.3'te epigraf değil
    ["Kedi Pamuk’a süt verdiler. Pamuk çok sevindi."],
])
def test_short_body_page_three_stays_in_scope(lines):
    pages = _picture_book()
    pages[3] = lines
    found = page_scope.classify(pages, set(), 32, ["Örnek Kitap"], [])
    assert 3 not in found


def test_author_bio_needs_the_name_in_a_biography():
    pages = _picture_book(n=200)
    # biyografi kitabının gövdesi: konusu olan kişinin doğumu, yazarın özgeçmişi değil
    pages[4] = ["Ahmet Paşa 1850 yılında Selanik’te doğdu; medreseden mezun oldu ve eserleri bugün okunuyor."]
    found = page_scope.classify(pages, set(), 200, ["Örnek"], ["Zeynep Kaya"], form="NARRATIVE_NONFICTION")
    assert 4 not in found
    found = page_scope.classify(pages, set(), 200, ["Örnek"], [], form="NARRATIVE_NONFICTION")
    assert 4 not in found                                         # ad bilinmiyorsa kural yok
    pages[4] = ["Zeynep Kaya 1975’te Konya’da doğdu, tarih bölümünden mezun oldu."]
    found = page_scope.classify(pages, set(), 200, ["Örnek"], ["Zeynep Kaya"], form="NARRATIVE_NONFICTION")
    assert found[4] == ("FRONT_MATTER", "yazar tanıtımı")


def test_bio_is_third_person_and_at_the_edges():
    assert not page_scope.is_author_bio(["1975’te Konya’da doğdum, tarih bölümünden mezun oldum; eserleri severim."], [])
    assert page_scope.is_author_bio(["Doğum tarihi 1972. Bilime olan merakı onu yazmaya başlattı."], [])
    pages = _picture_book(n=200)
    pages[100] = ["Kahramanımız 1900 yılında doğdu ve ödülü aldı; yazarlığa sonra başladı."]   # gövde ortası
    assert 100 not in page_scope.classify(pages, set(), 200, ["Örnek"], [])


def test_back_cover_and_author_note_at_the_end():
    pages = _picture_book(n=48)
    pages[47] = ["Sevgili okur, bu kitabı yazarken çocukluğumun bahçesini düşündüm."]
    pages[48] = ["Bu kitapta küçük bir tilkinin sürükleyici yolculuğuna tanık olacaksınız. 6+ yaş", "ornek.com"]
    found = page_scope.classify(pages, set(), 48, ["Örnek Kitap"], [])
    assert found[48] == ("NON_STORY", "arka kapak") and found[47] == ("NON_STORY", "yazar notu")
    assert 46 not in found                                        # son hikâye sayfası kalır


def test_last_story_page_and_nonfiction_conclusion_stay():
    pages = _picture_book(n=48)
    pages[48] = ["Tilki eve döndü, annesine sarıldı ve o gece mutlu bir uykuya daldı."]
    assert 48 not in page_scope.classify(pages, set(), 48, ["Örnek Kitap"], [])
    pages[48] = ["Sonuç olarak bu kitapta ele aldığımız konular, dönemin ekonomik yapısını açıklamaya yardım eder."]
    assert 48 not in page_scope.classify(pages, set(), 48, ["Örnek Kitap"], [])


def test_promotion_pages_before_the_last_page():
    pages = _picture_book(n=160)
    pages[158] = ["UZAY KASABASINDA BİR GÜN", "“Baban önemli bir görev için gidiyor,” dedi annesi."]
    pages[159] = ["İlk Genç", "BAŞKA BİR KİTAP", "Kısa tanıtım burada."]
    pages[160] = ["Yeni kitap önerimiz için karekodu telefon kameranıza okutunuz."]
    found = page_scope.classify(pages, {158, 159, 160}, 160, ["Örnek Kitap"], [])
    assert found[158] == ("NON_STORY", "arka kapak") and found[159][0] == "NON_STORY"
    assert 157 not in found
    # okumanın önerisi olmayan büyük harfli başlıklı gövde sayfası (son bölüm) kalır
    found = page_scope.classify(pages, {159, 160}, 160, ["Örnek Kitap"], [])
    assert 158 not in found


def test_edge_windows_follow_book_length():
    assert page_scope.edge_windows(32) == (4, 31)
    assert page_scope.edge_windows(300) == (15, 298)


# ------------------------------------------------------------------ Ek: arama dizini temizliği
def test_prune_deletes_only_old_keys_of_the_same_generation(monkeypatch):
    pytest.importorskip("qdrant_client")
    from qdrant_client import models
    from editor import retrieval as RT
    calls = {}

    class FakeQ:
        async def count(self, coll, exact=True, count_filter=None):
            calls["filter"] = count_filter
            return types.SimpleNamespace(count=5)

        async def delete(self, coll, wait=True, points_selector=None):
            calls["deleted"] = points_selector.filter

    monkeypatch.setattr(RT, "qdrant", lambda: FakeQ())
    assert asyncio.run(RT.prune_stale("gen-1", "key-new")) == 5
    f = calls["deleted"]
    assert f.must[0].key == "generation_id" and f.must[0].match.value == "gen-1"
    assert f.must_not[0].key == "build_key" and f.must_not[0].match.value == "key-new"
    assert isinstance(f.must_not[1], models.IsEmptyCondition)      # anahtarsız eski noktalara dokunulmaz
    assert asyncio.run(RT.prune_stale("gen-1", "")) == 0             # güncel anahtar yoksa silme yok


def test_cached_index_rebuilt_when_its_points_are_gone_and_old_keys_pruned(monkeypatch):
    pytest.importorskip("qdrant_client")
    from editor import rebuild, retrieval as RT
    log = []
    monkeypatch.setattr(rebuild, "begin", lambda *a: {"indexed": 10})
    monkeypatch.setattr(rebuild, "publish", lambda *a: log.append("publish"))

    async def build(kind, snap, built, key):
        log.append("build")
        return {"indexed": 10}

    async def present(gid, key, n):
        return False

    async def prune(gid, key):
        log.append(("prune", gid, key))
        return 3

    monkeypatch.setattr(rebuild, "build", build)
    monkeypatch.setattr(RT, "index_present", present)
    monkeypatch.setattr(RT, "prune_stale", prune)
    asyncio.run(rebuild.produce("search_index", {"generation_id": "g"}, "d", {}, "k2"))
    assert log == ["build", "publish", ("prune", "g", "k2")]
    log.clear()
    asyncio.run(rebuild.produce("report", {"generation_id": "g"}, "d", {}, "k3"))
    assert log == ["publish"]                                      # başka çıktı: önbellek, temizlik yok
