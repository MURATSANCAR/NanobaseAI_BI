"""book_type: yayınevinin tür adından kitap biçimi; hangi denetimin hangi kitaba uyduğu.

Örnekler canlı CRM stok kartlarındaki gerçek tür adlarıdır (new_turlertext, 2026-09-24).
Model ve DB yok. Çalıştırma: editor-py imajında pytest."""
import importlib.util
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402


class _Stub(types.ModuleType):
    """psycopg/httpx kurulu olmayan ortamda yalnız import için taklit; kuruluysa dokunulmaz."""
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


def _missing(root: str) -> bool:
    try:
        return importlib.util.find_spec(root) is None
    except ValueError:  # aynı oturumda önceden taklit edilmiş
        return False


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool", "httpx", "yaml"):
    _root = _mod.split(".")[0]
    if _missing(_root) or _root in sys.modules and isinstance(sys.modules[_root], _Stub):
        sys.modules.setdefault(_mod, _Stub(_mod))

from editor import book_type as bt  # noqa: E402


@pytest.mark.parametrize("genre, forms", [
    ("Roman", {"FICTION"}), ("Hikâye", {"FICTION"}), ("Öykü- Hikaye Kitapları", {"FICTION"}),
    ("Masal", {"FICTION"}), ("Fantastik Öykü", {"FICTION"}), ("Çizgi Roman", {"FICTION"}),
    ("Dini Hikaye", {"FICTION"}),                 # a story about religion, not a religious text
    ("Genç Kurgu", {"FICTION"}), ("Kıssa", {"FICTION"}),
    ("Tarih", {"NARRATIVE_NONFICTION"}), ("Biyografi", {"NARRATIVE_NONFICTION"}),
    ("Hatırat", {"NARRATIVE_NONFICTION"}), ("Osmanlı Tarihi", {"NARRATIVE_NONFICTION"}),
    ("Psikoloji", {"EXPOSITORY"}), ("Kişisel Gelişim", {"EXPOSITORY"}), ("Pedagoji", {"EXPOSITORY"}),
    ("Deneme", {"EXPOSITORY"}), ("Ahlak", {"EXPOSITORY"}), ("Tasavvuf Klasikleri", {"EXPOSITORY"}),
    ("Din/İman", {"EXPOSITORY"}), ("İnceleme-Araştırma", {"EXPOSITORY"}),
    ("Değerler Eğitimi", {"EXPOSITORY"}),         # suffixed stem: eğitimi -> eğitim
    ("Etkinlik", {"ACTIVITY"}), ("Boyama", {"ACTIVITY"}), ("Matematik", {"ACTIVITY"}),
    ("Dini Boyama", {"ACTIVITY"}), ("Eğitici Kartlar", {"ACTIVITY"}),
    ("Şiir", {"POETRY"}),
    ("Bilim", {"EXPOSITORY"}), ("Bilim Kurgu", {"FICTION"}), ("Bilimkurgu", {"FICTION"}),
    # two forms: the book decides between them
    ("Tarih İnceleme Araştırma", {"NARRATIVE_NONFICTION", "EXPOSITORY"}),
    ("Bilim Tarihi", {"NARRATIVE_NONFICTION", "EXPOSITORY"}),
    # names that point to no form are left to the book
    ("Klasik", set()), ("Genç", set()), ("Okul Öncesi", set()), ("Mizah", set()), ("", set()),
])
def test_genre_forms(genre, forms):
    assert bt.forms_of(genre) == forms


def test_short_words_match_only_whole():
    # «anı» (memoir) must not be found inside other words
    assert bt.forms_of("Anime") == set()
    assert bt.forms_of("Anı") == {"NARRATIVE_NONFICTION"}


def test_crm_forms_genres_first_then_web():
    # the 19 books of 2026-09-23, as the CRM records them
    assert bt.crm_forms(["Kişisel Gelişim"], None)["forms"] == ["EXPOSITORY"]
    assert bt.crm_forms(["Roman"], "Yetişkin;Romantik")["forms"] == ["FICTION"]
    # no genre: the web category decides (Aile ile Bağlanma: «Yetişkin;Aile Çocuk»)
    assert bt.crm_forms([], "Yetişkin;Aile Çocuk")["forms"] == ["EXPOSITORY"]
    # several web categories, comma separated
    got = bt.crm_forms([], "Çocuk;6 - 10 Yaş Öykü Hikaye,Çocuk;Dinler ve İnançlar")
    assert got["forms"] == ["EXPOSITORY", "FICTION"]
    # a genre that names a form wins over the web categories
    assert bt.crm_forms(["Tarih"], "Yetişkin;Psikoloji")["forms"] == ["NARRATIVE_NONFICTION"]
    # nothing at all
    assert bt.crm_forms([], None)["forms"] == []
    # campaign categories name no form
    assert bt.crm_forms([], "Yetişkin;Eylül Kitapları")["forms"] == []


def _page(n, text):
    return {"page_no": n, "spans": [{"text": text}]}


def test_sample_skips_front_and_back_matter():
    pages = [_page(i, f"sayfa {i} " + "metin " * 60) for i in range(1, 41)]
    got = bt._sample(pages)
    assert len(got) == bt.SAMPLE_PAGES
    assert all(5 <= n <= 38 for n, _ in got)           # not the first 10 %, not the last 5 %
    assert all(len(t) <= bt.SAMPLE_CHARS for _, t in got)
    assert bt._sample([_page(1, "kısa")]) == []          # no page with enough text


def _profile(form, audience="ADULT", drawn=0, pages=200):
    return {"form": form, "audience": audience, "illustrated_pages": drawn, "pages": pages}


def test_story_forms():
    assert bt.is_story(_profile("FICTION"))
    assert bt.is_story(_profile("NARRATIVE_NONFICTION"))
    assert bt.is_story(_profile("UNKNOWN"))              # unclassified: read as before
    assert not bt.is_story(_profile("EXPOSITORY"))
    assert not bt.is_story(_profile("ACTIVITY"))
    assert not bt.is_story(_profile("POETRY"))


def test_describe():
    assert bt.describe(_profile("FICTION", "CHILD", drawn=30, pages=32)) == "çocuklar için resimli kurgu bir kitap"
    assert bt.describe(_profile("FICTION", "ADULT")) == "yetişkinler için kurgu bir kitap"
    assert bt.describe(_profile("UNKNOWN", "UNKNOWN")) == "bir kitap"


def test_checks_by_kind_of_book():
    """Every check runs on every book; where its premise does not hold it reports advice."""
    from editor.proofing import advisory_reason, as_advice
    adult_novel = _profile("FICTION", "ADULT")
    self_help = _profile("EXPOSITORY", "ADULT")
    child_story = _profile("FICTION", "CHILD")
    child_activity = _profile("ACTIVITY", "CHILD")
    unknown = _profile("UNKNOWN", "UNKNOWN")
    # story continuity: advice outside a story
    for name in ("appearance", "props", "setting", "timeline", "dialogue"):
        assert advisory_reason(name, adult_novel) is None
        assert advisory_reason(name, unknown) is None
        assert advisory_reason(name, self_help).startswith("öneri:")
        assert advisory_reason(name, child_activity).startswith("öneri:")
    # age: advice for an adult's book
    assert advisory_reason("age_fit", child_story) is None
    assert advisory_reason("age_fit", child_activity) is None
    assert advisory_reason("age_fit", _profile("FICTION", "YOUNG")) is None
    assert advisory_reason("age_fit", unknown) is None
    assert advisory_reason("age_fit", adult_novel).startswith("öneri:")
    # checks that hold for every book never turn into advice
    for name in ("spelling", "name_spelling", "hyphenation", "layout", "edition_diff", "imprint_crm",
                 "series_canon", "text_contradictions"):
        for p in (adult_novel, self_help, child_activity, unknown):
            assert advisory_reason(name, p) is None


def test_advice_keeps_the_finding_and_opens_no_question():
    from editor.proofing import as_advice
    found = [{"page": 4, "severity": "WARN", "message": "Ayşe'nin çantası s.4'te kırmızı, s.9'da mavi",
              "quote": "kırmızı çantası", "details": {"pair": [4, 9]}},
             {"page": None, "severity": "ERROR", "message": "m"}]
    got = as_advice(found, "öneri: kitap bir hikâye anlatmıyor")
    assert [f["severity"] for f in got] == ["INFO", "INFO"]           # record() queues only non-INFO
    assert got[0]["message"] == found[0]["message"] and got[0]["quote"] == found[0]["quote"]
    assert got[0]["details"] == {"pair": [4, 9], "advisory": "öneri: kitap bir hikâye anlatmıyor",
                                 "severity_as_found": "WARN"}
    assert got[1]["details"]["severity_as_found"] == "ERROR"
    assert found[0]["severity"] == "WARN"                               # the input is not changed


# ------------------------------------------------------------------ künye kadrosu
@pytest.mark.parametrize("name, quote, page, role", [
    # künye bloğu tek alıntı: iki ve daha çok etiket → her ad kendi etiketinin görevi
    ("İhsan Sönmez", "Yayın Yönetmeni: İhsan Sönmez Editör: Ayşe Tuba Ayman Kapak Tasarımı: Ravza Kızıltuğ",
     2, "yayin yonetmeni"),
    ("Ayşe Tuba Ayman", "Yayın Yönetmeni: İhsan Sönmez Editör: Ayşe Tuba Ayman Kapak Tasarımı: Ravza Kızıltuğ",
     2, "editor"),
    ("Ravza Kızıltuğ", "Yayın Yönetmeni: İhsan Sönmez Editör: Ayşe Tuba Ayman Kapak Tasarımı: Ravza Kızıltuğ",
     2, "kapak tasarimi"),
    # tek satır künye, kitabın başında
    ("Tuba Şaklıoğlu", "Yayına Hazırlayan: Tuba Şaklıoğlu", 4, "yayina hazirlayan"),
    ("Sakine Korkmaz", "Yayına Hazırlayan\nSakine Korkmaz", 3, "yayina hazirlayan"),
    # kitabın sonundaki künye
    ("Ravza Kızıltuğ", "Kapak Tasarımı: Ravza Kızıltuğ", 207, "kapak tasarimi"),
])
def test_credit_names_are_not_characters(name, quote, page, role):
    from editor.naming import credit_role
    assert credit_role(name, quote, page, 208) == role


@pytest.mark.parametrize("name, quote, page", [
    ("Ahmet", "Editör Ahmet kapıyı açtı ve içeri girdi.", 40),        # romanda mesleği editör olan kişi
    ("Ahmet", "Editör Ahmet geldi.", 90),                               # tek etiket, kitabın ortası
    ("Maria", "Maria kapağı kapattı ve böcekleri kutuya koydu.", 2),     # etiket yok
    ("Zeynep", "Zeynep, editörün odasına girdi.", 3),                    # etiket adın yanında değil
    ("Leyla", "Bu kitap Leyla'ya ithaf edilmiştir.", 5),
])
def test_people_of_the_text_stay_characters(name, quote, page):
    from editor.naming import credit_role
    assert credit_role(name, quote, page, 208) is None
