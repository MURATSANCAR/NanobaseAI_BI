"""Kimlik bağları (2026-10-03, K16–K19): kısaltma/takma ad yalnız metindeki açık eşlemeyle, anlatıcının yakını,
adsız etiket katlama + «diğer kişiler», hitaptan çıkan yaşın birleşmede sayılmaması. Hiçbir kitap, ad ya da sayfa
numarası koddan okunmaz; buradaki adlar ve cümleler elle yazılmıştır. PDF, model ve veritabanı yok.

Sınır testleri yanlış birleşmeyi yakalar: ön ek benzerliği («Ali»/«Alican», «Bee»/«Beatrice») tek başına bağ
değildir; «X ve Y» iki kişidir; «X'in babası» X değildir; konuşma içindeki «benim adım X» anlatıcıyı belirlemez;
iç içe geçen iki «Kadın» iki kişidir; unvan («Sultan») etiket diye katlanmaz; dede/torun ayrımı korunur.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))


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


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool", "httpx",
             "yaml", "pymupdf", "qdrant_client", "qdrant_client.models"):
    _root = _mod.split(".")[0]
    if _missing(_root) or _root in sys.modules and isinstance(sys.modules[_root], _Stub):
        sys.modules.setdefault(_mod, _Stub(_mod))

from editor import identity, identity_links as L  # noqa: E402

FILL = "Sabah erkenden kalktılar ve yola koyuldular; hava serindi, yol uzundu."


def _u(name, pages, kind="HUMAN_CHILD", sex="FEMALE", aliases=(), windows=(), n=None, scope="INDIVIDUAL", age=None):
    return {"name": name, "kind": kind, "sex": sex, "entity_scope": scope, "pages": set(pages),
            "windows": set(windows), "aliases": list(aliases), "n": n if n is not None else len(pages),
            "age_evidence": age}


LABELS = {"kadın", "adam", "anne", "annesi", "babam", "annem", "kedi", "sultan", "bakıcı", "kız kardeşim",
          "bee nin annesi", "ekin in babası", "lokman ın babası", "babası", "yaşlı kadın", "kâhya kadın"}


def proper(n):
    return identity.name_key(n) not in LABELS


def _plan(units, pages=None, title=""):
    return L.link_plan(units, pages or {}, proper, title)


def _joined(plan, a, b):
    return any(a in g and b in g for g in plan["clusters"])


# ------------------------------------------------------------------ K16 kısaltma / takma ad
def test_footnote_abbreviation_joins_with_its_sentence_as_evidence():
    units = [_u("Bee", range(80, 120)), _u("Beatrice", [34, 50, 67])]
    pages = {33: FILL + "\n* Beatrice isminin kısaltması olan Bee, aynı zamanda bir böceğin adıdır.",
             34: "Beatrice kapıyı açtı."}
    p = _plan(units, pages)
    assert _joined(p, 0, 1)
    link = p["alias_links"][0]
    assert link["page"] == 33 and link["pattern"] == "KISALTMASI_OLAN" and "kısaltması" in link["quote"]
    assert len(link["quote"].split()) <= 15


def test_every_explicit_pattern_links():
    cases = ["Bee, yani Beatrice, kapıda bekliyordu.",
             "Beatrice (Bee) bütün gün okudu.",
             "Bee diye çağırdıkları Beatrice geldi.",
             "Asıl adı Beatrice olan Bee geldi.",
             "Bee, Beatrice'in kısaltmasıdır diye düşündüm; Bee, Beatrice'in kısaltması.",
             "Beatrice'e herkes Bee diye seslenirdi.",
             "Bee lakaplı Beatrice geldi.",
             "Beatrice'in lakabı Bee idi.",
             "Bee'nin asıl adı Beatrice."]
    for sent in cases:
        p = _plan([_u("Bee", range(80, 120)), _u("Beatrice", [34, 50])], {40: sent})
        assert _joined(p, 0, 1), sent


def test_ona_der_needs_one_named_person_before():
    units = [_u("Bee", range(80, 120)), _u("Beatrice", [34, 50]), _u("Stew", [39, 60], kind="HUMAN_ADULT",
                                                                        sex="MALE")]
    assert _joined(_plan(units, {39: "Bu Beatrice. Herkes ona Bee der."}), 0, 1)
    # önceki cümlede iki kişi: «ona» kimdir belli değil
    p = _plan(units, {39: "Benim adım Stew, bu da Beatrice. Biz, ona kısaca Bee diyoruz."})
    assert not _joined(p, 0, 1)
    # soru: «ona Bee der misin?» bir ad koyma cümlesi değil
    assert not _joined(_plan(units, {39: "Bu Beatrice. Ona Bee der misin?"}), 0, 1)


def test_prefix_or_shared_letters_never_join():
    units = [_u("Ali", [3, 9], kind="HUMAN_ADULT", sex="MALE"), _u("Alican", [40, 41], kind="HUMAN_ADULT",
                                                                   sex="MALE")]
    p = _plan(units, {3: "Ali eve geldi. Alican da geldi.", 40: "Alican, Ali'nin oğluydu."})
    assert p["clusters"] == []
    units = [_u("Bee", range(80, 120)), _u("Beatrice", [34, 50])]
    assert _plan(units, {34: "Beatrice ve kedisi. Bee de oradaydı."})["clusters"] == []


def test_names_listed_side_by_side_are_two_people():
    units = [_u("Bee", range(80, 120)), _u("Beatrice", [34, 50])]
    p = _plan(units, {34: "Bee, yani Beatrice geldi.", 90: "Bee ve Beatrice birlikte oynadı."})
    assert p["clusters"] == [] and any(r["reason"] == "ALIAS_COORDINATED" for r in p["refused"])


def test_genitive_is_not_an_identity():
    units = [_u("Ali", [3], kind="HUMAN_ADULT", sex="MALE"), _u("Veli", [40], kind="HUMAN_ADULT", sex="MALE")]
    assert _plan(units, {3: "Ali, yani Veli'nin oğlu, kapıda bekliyordu."})["clusters"] == []


def test_ambiguous_or_incompatible_target_is_refused():
    # adın taşıdığı iki bağdaşan kayıt: hangisi belli değil
    units = [_u("Bee", [80, 81]), _u("Bee", [80, 82]), _u("Beatrice", [34])]
    p = _plan(units, {33: "Beatrice isminin kısaltması olan Bee, bir böcektir."})
    assert not any(2 in g for g in p["clusters"])
    assert any(r["reason"] == "ALIAS_AMBIGUOUS" for r in p["refused"])
    # tek bağdaşan kayıt seçilir (çocuk Bee; yetişkin Bee değil)
    units = [_u("Bee", [80, 90]), _u("Bee", [85, 95], kind="HUMAN_ADULT"), _u("Beatrice", [34])]
    p = _plan(units, {33: "Beatrice isminin kısaltması olan Bee, bir böcektir."})
    assert _joined(p, 0, 2) and not _joined(p, 1, 2)
    # insan ↔ hayvan: metin ne derse desin birleşmez
    units = [_u("Bee", [80]), _u("Beatrice", [34], kind="ANIMAL")]
    p = _plan(units, {33: "Bee, yani Beatrice geldi."})
    assert p["clusters"] == [] and any(r["reason"] == "ALIAS_INCOMPATIBLE" for r in p["refused"])
    # farklı sıra sayısı (tarih): açık cümle de adaşları birleştirmez
    units = [_u("II. Mahmud", [3], kind="HUMAN_ADULT", sex="MALE"),
             _u("Mahmud Han", [80], kind="HUMAN_ADULT", sex="MALE", aliases=["I. Mahmud"])]
    assert _plan(units, {3: "II. Mahmud, yani Mahmud Han, tahta çıktı."})["clusters"] == []


def test_a_sentence_about_another_records_listed_name_does_not_join():
    # okuma «Salih Bozok» adını yanlışlıkla «Mahmut Bey» kaydına eklemiş: «Salih (Salih Bozok)» Mahmut Bey'i
    # Salih yapmaz
    units = [_u("Mahmut Bey", [166], kind="HUMAN_ADULT", sex="MALE", aliases=["Salih Bozok"]),
             _u("Salih", [270], kind="HUMAN_ADULT", sex="MALE")]
    p = _plan(units, {166: "Kel Ali, Salih (Salih Bozok), Davut ve Tevfik oradaydı."})
    assert p["clusters"] == [] and any(r["reason"] == "ALIAS_NOT_A_RECORD_NAME" for r in p["refused"])


def test_alias_conflict_is_fixed_when_the_book_says_whose_name_it_is():
    # tilkinin kaydına kızın lakabı eklenmiş; kitap lakabın kızın olduğunu söylüyor
    units = [_u("Bee", range(80, 120)), _u("Gölge", range(45, 200), kind="ANIMAL", aliases=["Küçük Arı"]),
             _u("Nan", [11, 12], kind="HUMAN_ADULT")]
    p = _plan(units, {150: "Bee'nin lakabı Küçük Arı idi."})
    fix = [c for c in p["alias_conflicts"] if c["alias"] == "küçük arı"]
    assert fix and fix[0]["action"] == "fix" and fix[0]["owner"] == 0 and fix[0]["holders"] == [1]
    # kitap söylemiyorsa: iki kaydın taşıdığı aynı diğer ad yalnız işaretlenir
    units = [_u("Muhammed Emin Hoca", [110], kind="HUMAN_ADULT", sex="MALE", aliases=["Muhammed Hoca"]),
             _u("Muhammed Emin Yıldırım", [92], kind="HUMAN_ADULT", sex="MALE", aliases=["Muhammed Hoca"])]
    c = _plan(units, {})["alias_conflicts"]
    assert c and c[0]["action"] == "flag" and sorted(c[0]["holders"]) == [0, 1]
    # tek kayıttaki diğer ad çakışma değil
    assert _plan([_u("Nan", [3], aliases=["Ingeborg"])], {})["alias_conflicts"] == []


# ------------------------------------------------------------------ K17 anlatıcı
def _family(narrator_pages):
    return [_u("Ekin", range(1, 200), n=40), _u("Babam", [2, 50, 120], kind="HUMAN_ADULT", sex="MALE"),
            _u("Ekin'in babası", [70], kind="HUMAN_ADULT", sex="MALE"),
            _u("Lokman", [5, 60], kind="HUMAN_ADULT", sex="MALE"),
            _u("Lokman'ın babası", [42], kind="HUMAN_ADULT", sex="MALE")]


def test_narrator_relative_joins_the_narrators_possessive():
    pages = {3: "Adım Ekin ve okula yürüyerek giderim.",
             9: "“Ekin, buraya gel,” dedi bana öğretmen.",
             70: "Ekin'in babası kapıda durdu."}
    p = _plan(_family(None), pages, title="Benim Adım Ekin")
    assert p["narrator"]["decided"] and p["narrator"]["name"] == "Ekin"
    assert _joined(p, 1, 2)
    # «Lokman'ın babası» anlatıcının babası DEĞİL
    assert not _joined(p, 1, 4) and not _joined(p, 2, 4) and not _joined(p, 3, 4)


def test_narrator_not_decided_from_speech_title_or_one_hint():
    # yalnız kitap adı, konuşma içinde «benim adım Ekin» ve «ağladım Ekin»: anlatıcı belirlenemez
    pages = {1: "Benim Adım Ekin", 5: "İçindekiler 59 “Benim Adım Ekin, Babamın Sevdiği”",
             14: "Böğürerek ağladım Ekin. Sana bir köy anlattım.",
             66: "“Demek benim adım Ekin ve babamın sevdiği ekinler gibi,” dedi.",
             67: "— Benim adım Ekin, dedi kız.",
             203: "Benim Adım Ekin öyle bir hediye verdin ki giderken yolumu aydınlattın."}
    p = _plan(_family(None), pages, title="Benim Adım Ekin")
    assert not p["narrator"]["decided"] and not _joined(p, 1, 2)
    # tek kanıt yetmez
    p = _plan(_family(None), {3: "Benim adım Ekin."}, title="")
    assert not p["narrator"]["decided"] and not _joined(p, 1, 2)


def test_two_narrators_do_nothing():
    pages = {3: "Benim adım Ekin. Okula giderim.", 4: "Benim adım Ekin, yine ben.",
             100: "Benim adım Lokman. Bu bölümü ben anlatıyorum.", 101: "Bana Lokman derler."}
    p = _plan(_family(None), pages)
    assert not p["narrator"]["decided"] and p["narrator"]["reason"] == "NARRATOR_SEVERAL"
    assert not _joined(p, 1, 2) and not _joined(p, 1, 4)


def test_relative_label_split_in_two_does_not_join():
    units = _family(None) + [_u("Babam", [55, 130], kind="HUMAN_ADULT", sex="MALE")]
    pages = {3: "Benim adım Ekin. Okula giderim.", 4: "Bana Ekin derler."}
    p = _plan(units, pages)
    assert not _joined(p, 2, 1) and not _joined(p, 2, 5)


# ------------------------------------------------------------------ K18 adsız etiket
def test_label_forms():
    assert L.label_key("Annesi") == ("", "anne") == L.label_key("anne") == L.label_key("annesi")
    assert L.label_key("Bee'nin Annesi") == ("bee", "anne")
    assert L.label_key("Kadın") == ("", "kadın")
    assert L.label_key("Annem") is None            # anlatıcıya göreli: ayrı kural
    assert L.label_key("Suna teyze") is None        # ad + hitap: K15
    assert L.label_key("Kadınlar") is None          # topluluk


def test_same_label_with_apart_pages_folds():
    units = [_u("anne", [3, 4], kind="HUMAN_ADULT"), _u("Annesi", [40, 41], kind="HUMAN_ADULT"),
             _u("annesi", [90], kind="HUMAN_ADULT")]
    p = _plan(units)
    assert sorted(p["clusters"][0]) == [0, 1, 2]
    units = [_u("Kadın", [p_], kind="HUMAN_ADULT") for p_ in (10, 30, 60, 90)]
    assert sorted(_plan(units)["clusters"][0]) == [0, 1, 2, 3]


def test_label_on_interleaved_or_conflicting_records_stays_apart():
    # aynı sayfalarda birlikte geçen iki kadın
    p = _plan([_u("Kadın", [10, 30], kind="HUMAN_ADULT"), _u("Kadın", [20, 40], kind="HUMAN_ADULT")])
    assert p["clusters"] == [] and p["refused"][-1]["reason"] == "LABEL_INTERLEAVED"
    # cinsiyet / tür / yaşam evresi çelişkisi
    assert _plan([_u("Kadın", [10], kind="HUMAN_ADULT"), _u("Kadın", [50], kind="HUMAN_ADULT",
                                                            sex="MALE")])["clusters"] == []
    assert _plan([_u("Kedi", [10], kind="ANIMAL"), _u("Kedi", [50], kind="HUMAN_ADULT")])["clusters"] == []
    assert _plan([_u("annesi", [10], kind="HUMAN_CHILD"), _u("annesi", [50], kind="HUMAN_ADULT")])["clusters"] == []
    # sahipli etiket sahibine göre ayrı
    p = _plan([_u("Annesi", [10], kind="HUMAN_ADULT"), _u("Bee'nin Annesi", [50], kind="HUMAN_ADULT")])
    assert p["clusters"] == []
    p = _plan([_u("Bee'nin Annesi", [10], kind="HUMAN_ADULT"), _u("Bee'nin annesi", [50], kind="HUMAN_ADULT")])
    assert p["clusters"] == [[0, 1]] or sorted(p["clusters"][0]) == [0, 1]


def test_titles_and_offices_are_not_labels_to_fold():
    # tarih kitabında farklı yıllardaki iki «Sultan» iki kişidir
    p = _plan([_u("Sultan", [10], kind="HUMAN_ADULT", sex="MALE"), _u("Sultan", [90], kind="HUMAN_ADULT", sex="MALE")])
    assert p["clusters"] == []
    p = _plan([_u("Bakıcı", [10], kind="HUMAN_ADULT", sex="MALE"), _u("Bakıcı", [90], kind="HUMAN_ADULT", sex="MALE")])
    assert p["clusters"] == []
    # saray / lonca görevi: «Kâhya Kadın» bir etiket değil, görevdir
    p = _plan([_u("Kâhya Kadın", [79], kind="HUMAN_ADULT"), _u("Kâhya Kadın", [87, 90], kind="HUMAN_ADULT")])
    assert p["clusters"] == []
    # görünüş sıfatı etiketi bozmaz
    p = _plan([_u("Yaşlı kadın", [10], kind="HUMAN_ADULT"), _u("yaşlı kadın", [90], kind="HUMAN_ADULT")])
    assert p["clusters"] and sorted(p["clusters"][0]) == [0, 1]
    # hayvan etiketi: hepsi hayvansa katlanır
    p = _plan([_u("Kedi", [10], kind="ANIMAL"), _u("Kedi", [50], kind="ANIMAL"), _u("Kedi", [90], kind="OTHER")])
    assert sorted(p["clusters"][0]) == [0, 1, 2]


def test_minor_figures_are_listed_apart():
    assert L.is_minor("Kadın", {}, 2) and L.is_minor("annesi", {}, 1)
    assert not L.is_minor("Kadın", {}, 3)                 # sık anılan figüran ana listede kalır
    assert not L.is_minor("Ekin", {}, 1)
    assert L.is_minor("Doktor", {"unnamed": True}, 1)     # okumanın kararı: kitap ad gibi yazmıyor
    assert not L.is_minor("Kedi", {"unnamed": False}, 1)  # kedinin adı «Kedi»
    assert L.is_minor("Belediye Başkanı", {"name_origin": "DESCRIPTIVE_LABEL"}, 1)
    assert not L.is_minor("Kadın", {}, None)              # anma sayısı bilinmiyorsa ayrılmaz


def test_read_model_splits_the_cast():
    from editor import read_model
    snap = {"claims": [], "characters": [
        {"id": "a", "canonical_name": "Ekin", "aliases": [], "identity_status": "CONFIRMED",
         "identity_confidence": 0.9, "first_page": 1, "traits": {}},
        {"id": "b", "canonical_name": "Kadın", "aliases": [], "identity_status": "CANDIDATE",
         "identity_confidence": 0.7, "first_page": 20, "traits": {"unnamed": True}}]}
    chars = read_model.characters(snap, mentions={"a": 40, "b": 1})
    main, other = read_model.split_minor(chars)
    assert [c["canonical_name"] for c in main] == ["Ekin"] and [c["canonical_name"] for c in other] == ["Kadın"]
    assert not any(c["minor"] for c in read_model.characters(snap))     # sayısız: hepsi ana listede


# ------------------------------------------------------------------ K19 hitaptan çıkan yaş
def _p(name, pages, kind, sex="FEMALE", age=None):
    return _u(name, pages, kind=kind, sex=sex, age=age)


def test_address_word_age_is_not_life_stage_evidence():
    # «Yasemin abla» hitap yüzünden yetişkin okunmuş, «Yasemin» çocuk; sayfalar iç içe ama aynı sayfa yok
    units = [_p("Yasemin", [5, 40, 100], "HUMAN_CHILD"), _p("Yasemin abla", [20, 70], "HUMAN_ADULT")]
    clusters, refused = identity.same_name_plan(units, lambda n: True)
    assert clusters == [[0, 1]] and refused == []
    # metin yaşını söylüyorsa sayılır
    units[1]["age_evidence"] = "HUMAN_ADULT"
    clusters, refused = identity.same_name_plan(units, lambda n: True)
    assert clusters == [] and refused[0]["reason"] == "LIFE_STAGE_ORDER"
    # aynı sayfa yine reddedilir
    units = [_p("Yasemin", [5, 40], "HUMAN_CHILD"), _p("Yasemin abla", [40, 70], "HUMAN_ADULT")]
    assert identity.same_name_plan(units, lambda n: True)[0] == []


def test_grandparent_word_is_a_generation_and_keeps_namesakes_apart():
    # dede ve adını taşıyan torun yan yana: hâlâ iki kişi
    units = [_p("Ahmet dede", [5, 40, 100], "HUMAN_ADULT", sex="MALE"), _p("Ahmet", [10, 70, 160], "HUMAN_CHILD",
                                                                          sex="MALE")]
    clusters, refused = identity.same_name_plan(units, lambda n: True)
    assert clusters == [] and refused[0]["reason"] == "LIFE_STAGE_ORDER"


def test_text_stage():
    assert L.text_stage(["On iki yaşında bir kızdı.", "12 yaşındaki Yasemin"]) == "HUMAN_CHILD"
    assert L.text_stage(["35 yaşında bir kadın"]) == "HUMAN_ADULT"
    assert L.text_stage(["Yasemin abla geldi."]) is None
    assert L.text_stage(["8 yaşında", "40 yaşında"]) is None


def test_fold_and_reading_use_the_same_plan():
    src = (pathlib.Path(__file__).resolve().parents[1] / "src" / "editor")
    assert "identity_links.link_plan(" in (src / "identity_fold.py").read_text(encoding="utf-8")
    assert "identity_links.link_plan(" in (src / "identity.py").read_text(encoding="utf-8")
