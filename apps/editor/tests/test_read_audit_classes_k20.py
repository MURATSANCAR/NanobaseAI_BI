"""Okuma denetimi 2026-10-06 (44 arşiv okuması): genel hata sınıfları K20–K23. Hiçbir kitap, ad ya da sayfa numarası
koddan okunmaz; buradaki metinler elle yazılmıştır, model ve veritabanı yok. Her sınıfta yanlış pozitif sınırı var.

K20. Baskı/üretim notu («BIÇAK», «KAPAK içine baskı», «PANTONE 129», «EBAT: 22 X 22») ve dizgi dosyasında kalmış özgün
     dil satırı bölüm adı/okuma metni değildir; künye satırı, öyküdeki «bıçak», etkinlik yönergesindeki ölçü, iki dilli
     kitabın İngilizcesi, kaynakça, kısa alıntı etkilenmez.
K21. Resimli kitabın iri puntolu gövde cümlesi bölüm açmaz; bilgi kitabının büyük harfli konu başlıkları, bölüm başı
     boşluklu şiir başlıkları ve mektup romanının (≥ 3, hepsi hitap) mektupları kalır.
K22. Künyede adı olmayan çevirmenin özgeçmişi (ad başlıklı ya da çeviri/editörlük sözlü) kapsam dışı; birinci şahıs
     anı ve gövde sayfası değil.
K23. Aynı kitabın iki dosyası (aynı ad, uyumlu sayfa, görsel karma benzer) tek küme; okunmuşa dokunulmaz, sıradaki
     kopya bekletilir; aynı adlı farklı kitap kümelenmez.
"""
from __future__ import annotations

from types import SimpleNamespace

from editor import archive, chapters as typeset, page_scope, print_note, source
from editor.print_note import book_context, foreign_language, note_kind, print_note_kind, strip_notes

LONG = "Sabah erkenden kalktı ve dükkânın kepengini yavaşça kaldırdı, içeri serin bir koku doldu."
H, BODY = 600.0, 10.0


# ------------------------------------------------------------------ K20
def test_print_notes_are_recognised():
    for t in ("BIÇAK", "KAPAK içine baskı", "Pencere açıldığında görünen kısım BIÇAK", "PANTONE 129",
              "pantone 206U", "Pantone 603 U", "BIÇAK KAPAK içine baskı"):
        assert print_note_kind(t) == "dizgi", t
    for t in ("EBAT: 22 X 22 SAYFA: 56", "HERVÉ TULLET EBAT: 22 X 22", "22 x 28 cm"):
        assert print_note_kind(t) == "spec", t


def test_print_note_false_positive_borders():
    # künye satırı künye okumasına kalır
    for t in ("1. Baskı Mart 2016", "Baskı ve Cilt: Örnek Matbaacılık", "Kapak Tasarımı: Ayşe Yılmaz", "ISBN 978-605"):
        assert print_note_kind(t) is None, t
    # öyküde bıçak, yara izi, pencere; etkinlikte ölçü; ürün listesi
    for t in ("Kasap bıçağı tezgâha bıraktı.", "Yüzünde derin bir bıçak izi vardı.",
              "Pencere açıldığında içeri soğuk hava doldu.", "20 x 30 cm'lik bir kâğıt alın ve ikiye katlayın.",
              "Boy Cetveli (20x110 cm)", "(21x29,7cm - 35 adet)", "Bıçak"):
        assert print_note_kind(t) is None, t
    # notla metin aynı satırda: satır gövdedir, not parçası çıkar
    assert print_note_kind("KAPAK içine baskı İşte burada!") is None
    assert strip_notes("KAPAK içine baskı İşte burada!") == "İşte burada!"


def test_lone_knife_needs_a_production_file():
    alphabet = ["B harfiyle başlayan sözcükler", "BIÇAK", "Balık suda yüzer, bıçak mutfakta durur."]
    assert note_kind("BIÇAK", book_context(alphabet)) is None
    proof = alphabet + ["KAPAK içine baskı", "Pencere açıldığında görünen kısım"]
    assert note_kind("BIÇAK", book_context(proof)) == "dizgi"


def test_foreign_source_lines_only_in_turkish_production_files():
    tr = ["Çocuklar bahçede koşuyor ve gülüşüyorlardı.", "Annesi onlara sıcak bir çorba getirdi."] * 4
    de = ["Ist ein Geräusch aus dem Weltall zu hören?", "Der Duft von Blumen erinnert uns an den Frühling."]
    assert foreign_language(de[0]) == "de" and foreign_language(de[1]) == "de"
    proof = book_context(tr + de + ["KAPAK içine baskı"])
    assert proof["turkish"] and note_kind(de[0], proof) == "foreign"
    assert note_kind(tr[0], proof) is None
    # dizgi notu olmayan Türkçe kitapta (iki dilli öğrenme kitabı, alıntı) yabancı satır içeriktir
    learn = book_context(tr + ["Look! Our gym is very big and we can run.", "We can jump, skip rope and dance."])
    assert note_kind("Look! Our gym is very big and we can run.", learn) is None
    # yabancı dildeki baskı (Türkçe az): hiçbir satırı not değil
    fr = ["Pour utiliser notre temps avec sagesse, nous devons prier.", "Le nom est suivi par une prière."] * 6
    ctx = book_context(fr + ["KAPAK içine baskı"])
    assert not ctx["turkish"] and note_kind(fr[0], ctx) is None


def test_foreign_line_borders():
    for t in ("Hervé Tullet", "To be, or not", "“To be, or not to be, that is the question.”",
              "70 Darwin, On the Origin of Species by", "Smith, J. (2001). The history of the empire.",
              "le tü kö an zam", "ab er sö yley elim Fe er ti.", "Ali ile Ayşe der ki bu ist değil."):
        assert foreign_language(t) is None, t


def test_print_note_block_role_and_display():
    ctx = book_context(["KAPAK içine baskı", "Pencere açıldığında görünen kısım", "Kuş ağaçta öttü ve uçtu."] * 3)
    raw = "BIÇAK\n\nKAPAK içine baskı Cik, cik!\n\nKuş ağaçta öttü."
    page = {"page_no": 3, "needs_ocr": False}
    proj = source.project_page("g", page, [{"source": "TEXT_LAYER", "text": raw}], notes=ctx)
    roles = [(s["text"], s["role"]) for s in proj["spans"]]
    assert roles[0] == ("BIÇAK", source.PRINT_NOTE)
    assert [source.shown(s) for s in source.body_spans(proj)] == ["Cik, cik!", "Kuş ağaçta öttü."]
    # spanın kendisi (kanıt doğrulaması) değişmez
    assert proj["spans"][1]["text"] == "KAPAK içine baskı Cik, cik!"
    plain = source.project_page("g", page, [{"source": "TEXT_LAYER", "text": raw}])
    assert all(s["role"] == "body" for s in plain["spans"])


def _ln(text, y0, size):
    return {"text": text, "y0": y0, "size": size}


def _page(lines):
    return SimpleNamespace(rect=SimpleNamespace(height=H), lines=lines)


def _body(y0, n=14):
    return [_ln(LONG, y0 + 14 * k, BODY) for k in range(n)]


def _lines(p):
    return p.lines


def _pages(doc):
    return [{"page_no": i, "spans": [{"text": ln["text"]} for ln in p.lines]} for i, p in enumerate(doc, 1)]


def test_print_notes_do_not_become_chapters():
    doc = [_page(_body(60)) for _ in range(3)]
    for note in ("BIÇAK", "KAPAK içine baskı", "Pencere açıldığında görünen kısım BIÇAK", "BIÇAK"):
        doc += [_page([_ln(note, 180, 14.0)] + _body(240)), _page(_body(60))]
    found = typeset.chapters_from_pages(_pages(doc), typeset.page_headings(doc, _lines), "Kulak")
    assert [c["title"] for c in found] == ["Kitap"]


# ------------------------------------------------------------------ K21
def test_sentence_heading_borders():
    for t in ("Salsal ve Uğur, Çomar’ın önerisini sevinçle", "Sessizce konuşulanları dinleyen Kirpik Kirpik",
              "Annesi Annesi gülümseyerek cevap verdi:", "Bahçede yürürken kabuğuna bir şey ‘tık’"):
        assert typeset.sentence_heading(t), t
    for t in ("YENİ PADİŞAH", "Kalelerin Fethi Tekerlekli Kuleler", "Ali, Veli ve Ben", "Balığı Olmayan Kız",
              "BİRİNCİ BÖLÜM", "Salsal"):
        assert not typeset.sentence_heading(t), t
    assert typeset.continues_as_sentence("Bahçede yürürken kabuğuna bir şey", "çarptı ve durdu.")
    assert not typeset.continues_as_sentence("Bir Kış Gecesi", "kar yağıyordu usul usul")
    assert not typeset.continues_as_sentence("Bahçede yürürken kabuğuna bir şey çarptı.", "sonra durdu")


def _starts(heads, n):
    pages = [{"page_no": i, "spans": [{"text": LONG}]} for i in range(1, n + 1)]
    return [c["title"] for c in typeset.chapters_from_pages(pages, heads)]


def test_picture_book_body_type_is_not_chapters():
    heads = {p: {"title": t, "size": 24.0, "kind": "head"} for p, t in
             ((5, "Bahçede yürürken kabuğuna bir şey ‘tık’"), (9, "Çomar bilmiş bilmiş yanıtladı her şeyi"),
              (13, "Salsal"), (17, "Salsal annesine aklını karıştıran soruyu sordu"),
              (21, "Annesi gülümseyerek cevap verdi:"))}
    assert _starts(heads, 32) == ["Kitap"]
    two = {5: {"title": "Salsal ve Uğur, Çomar’ın önerisini sevinçle", "size": 24.0, "kind": "head"}}
    assert _starts(two, 32) == ["Kitap"]


def test_info_book_headings_and_long_book_survive():
    info = {p: {"title": t, "size": 18.0, "kind": "head"} for p, t in
            ((3, "YENİ PADİŞAH"), (5, "BARIŞ"), (7, "İSTANBUL"), (9, "GÜÇLÜ SAVUNMA"), (11, "FETHE HAZIRLIK"))}
    assert _starts(info, 32)[1:] == ["YENİ PADİŞAH", "BARIŞ", "İSTANBUL", "GÜÇLÜ SAVUNMA", "FETHE HAZIRLIK"]
    # uzun kitapta cümle biçimli başlık çoğunluktaysa kalır (eski kural)
    long_ = {p: {"title": f"Yeniden imparator olma girişimi {k}", "size": 18.0, "kind": "head"}
             for k, p in enumerate((20, 60, 100, 140), 1)}
    assert len(_starts(long_, 200)) == 5


def test_letter_salutations():
    one = {20: {"title": "Sevgili Kaptan Uzunbacak!", "size": 16.0, "kind": "sunk"},
           60: {"title": "Sevgili Bay Uzunbacak!", "size": 16.0, "kind": "sunk"}}
    assert _starts(one, 160) == ["Kitap"]
    letters = {p: {"title": "Sevgili Bay Uzunbacak!", "size": 16.0, "kind": "sunk"} for p in (20, 40, 60, 80)}
    assert _starts(letters, 160).count("Sevgili Bay Uzunbacak!") == 4
    mixed = {20: {"title": "BİRİNCİ YIL", "size": 16.0, "kind": "sunk"},
             40: {"title": "Sevgili Annem,", "size": 16.0, "kind": "sunk"},
             80: {"title": "İKİNCİ YIL", "size": 16.0, "kind": "sunk"}}
    assert _starts(mixed, 160)[1:] == ["BİRİNCİ YIL", "İKİNCİ YIL"]
    assert typeset.salutation("Sevgili Kaptan Uzunbacak!") and not typeset.salutation("Sevgi Üzerine")


# ------------------------------------------------------------------ K22
BIO = ["Ünver Alibey", "1960 yılında Limasol'da doğdu. İstanbul Üniversitesi'nden mezun oldu.",
       "Uzun yıllar yayınevlerinde editör olarak çalıştı.", "Çocuklar için pek çok kitabın çevirileri var."]


def test_translator_bio_without_name_in_imprint():
    assert page_scope.is_author_bio(BIO, ["Alice J. Webster"])
    assert page_scope.is_author_bio(BIO[:2], [])                         # ad başlıklı, kariyer sözü yok
    assert not page_scope.is_author_bio(BIO, ["Alice J. Webster"], need_name=True)
    # birinci şahıs anı, ad başlıksız gövde değil
    assert not page_scope.is_author_bio(["Ünver Alibey", "1960'ta Limasol'da doğdum, sonra mezun oldum."], [])
    assert not page_scope.is_author_bio(["Kasabada herkes onu tanırdı.", "Dedesi bu evde doğdu ve büyüdü."], [])
    pages = {p: [LONG] * 6 for p in range(1, 161)}
    pages[6] = BIO
    assert page_scope.author_bio_pages(pages, 160, []) == {6}


def test_bio_page_is_not_a_chapter():
    heads = {6: {"title": "Ünver Alibey", "size": 16.0, "kind": "head"}}
    pages = [{"page_no": i, "spans": [{"text": t} for t in (BIO if i == 6 else [LONG])]} for i in range(1, 161)]
    assert [c["title"] for c in typeset.chapters_from_pages(pages, heads)] == ["Kitap"]


# ------------------------------------------------------------------ K23
def test_title_key_and_page_compatibility():
    assert archive.title_key("Kulaklarını Kocaman Aç") == archive.title_key("KULAKLARINI KOCAMAN AÇ (2)")
    assert archive.title_key("Dava özalit") == archive.title_key("Dava")
    assert archive.pages_compatible(55, 27) and archive.pages_compatible(61, 30)
    assert archive.pages_compatible(152, 152) and archive.pages_compatible(100, 108)
    assert not archive.pages_compatible(32, 160) and not archive.pages_compatible(32, 48)


def _h(seed):
    import random
    r = random.Random(seed)
    return r.getrandbits(256)


def test_duplicate_clusters_hold_queued_copy_only():
    same = [[_h(i)] for i in range(8)]
    spread = [[_h(100 + i), _h(2 * i), _h(2 * i + 1)] for i in range(4)]     # iki sayfa yan yana
    pages8 = [[_h(i)] for i in range(8)]
    other = [[_h(500 + i)] for i in range(8)]                               # aynı adlı başka kitap
    files = [
        {"book_id": "a", "title": "Kulaklarını Kocaman Aç", "pages": 8, "path": "x/kulak-ic-baski.pdf",
         "status": "SUCCEEDED", "job_id": "ja", "text_chars": 800},
        {"book_id": "b", "title": "Kulaklarını Kocaman Aç", "pages": 4, "path": "x/kulak-ozalit.pdf",
         "status": "QUEUED", "workflow_id": None, "job_id": "jb", "text_chars": 100},
        {"book_id": "c", "title": "Kulaklarını Kocaman Aç", "pages": 8, "path": "y/kulak.pdf",
         "status": "QUEUED", "workflow_id": None, "job_id": "jc", "text_chars": 800},
    ]
    assert archive.hash_similarity(pages8, spread) >= archive.DUP_SIMILARITY
    assert archive.hash_similarity(same, other) < 0.7
    clusters = archive.duplicate_clusters(files, {"a": same, "b": spread, "c": other})
    assert len(clusters) == 1 and clusters[0]["primary"]["book_id"] == "a"
    assert [m["book_id"] for m in clusters[0]["copies"]] == ["b"]
    acts = archive.hold_actions(clusters)
    assert [a["job_id"] for a in acts] == ["jb"] and acts[0]["duplicate_of"]["book_id"] == "a"
    # okunmuş kopyaya dokunulmaz: ana dosya sıradaysa okunmuş olan ana olur
    files[0]["status"], files[1]["status"] = "QUEUED", "SUCCEEDED"
    files[0]["workflow_id"] = None
    cl = archive.duplicate_clusters(files, {"a": same, "b": spread, "c": other})
    assert cl[0]["primary"]["book_id"] == "b" and [a["job_id"] for a in archive.hold_actions(cl)] == ["ja"]


def test_file_rank_prefers_full_print_file():
    proof = {"book_id": "1", "path": "a/dava-ozalit.pdf", "pages": 200, "text_chars": 400000, "status": "QUEUED"}
    final = {"book_id": "2", "path": "a/dava-135x210.pdf", "pages": 200, "text_chars": 400000, "status": "QUEUED"}
    assert sorted([proof, final], key=archive.file_rank)[0] is final


def test_copies_fold_under_main_book():
    books = [{"id": "a", "title": "Kulak", "pages": 55}, {"id": "b", "title": "Kulak", "pages": 27},
             {"id": "z", "title": "Başka", "pages": 10}]
    out = archive.fold_copies(books, {"b": "a", "z": "missing"})
    assert [b["id"] for b in out] == ["a", "z"]
    assert out[0]["files"] == 2 and out[0]["copies"][0]["id"] == "b" and out[1]["files"] == 1


def test_sample_pages_short_book_all_pages():
    assert archive.sample_pages(27) == list(range(1, 28))
    assert len(archive.sample_pages(400)) == archive.DUP_SAMPLE


def test_print_note_module_is_pure():
    assert print_note.PRINT_NOTE == source.PRINT_NOTE
