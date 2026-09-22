"""editor.naming over synthetic text: the invariants, not one book.

The real measurement runs against a book in the database on the GPU host; these cases are
written by hand so the rules can be checked anywhere. Run:

    python3 apps/editor/tests/test_naming.py        (or: pytest apps/editor/tests/test_naming.py)

`editor.ledger` pulls in psycopg for its writes; only its pure `norm` is needed here, so
the driver is stubbed before the import.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class _Stub(types.ModuleType):
    """Any name asked of it is an object; nothing here is ever called."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool"):
    sys.modules.setdefault(_mod, _Stub(_mod))

from editor import naming  # noqa: E402

SHARE, USES = 0.8, 1

# A few sentences in the shape the books are written in. "Mert" and "Levent" are people;
# "ben" is a pronoun; "tayfa" is a group word. Nothing here is read from a real book —
# the point is that the rule, not a list, decides.
TEXT = """
Levent sabah erkenden kalktı. Mert onu kapıda bekliyordu.
"Ben hazırım," dedi Levent. Mert güldü, çünkü ben her zaman geç kalırım.
Bütün tayfa toplandığında Levent öne geçti ve tayfa peşinden yürüdü.
Annesi Levent'e seslendi. Annesi her sabah böyle yapardı.
Akşam olunca Mert ile Levent eve döndü; tayfa dağıldı.
"""


def check(cond, label):
    if not cond:
        raise AssertionError(label)
    print(f"  ok  {label}")


def test_usage_ignores_forced_capitals():
    # "Ben" only ever starts a sentence or follows an opening quote; mid-sentence the
    # book writes "ben". So its capital share is 0, and it is not a name.
    mid, cap = naming.usage("Ben", TEXT)
    check(mid >= 1, "'ben' is used mid-sentence")
    check(cap == 0, "'ben' is never capitalised mid-sentence")
    check(not naming.is_proper_name("Ben", TEXT, min_share=SHARE, min_uses=USES),
          "'Ben' is not a proper name")
    # a name written as a name
    mid, cap = naming.usage("Mert", TEXT)
    check(mid >= 1 and cap == mid, "'Mert' is always capitalised mid-sentence")
    check(naming.is_proper_name("Mert", TEXT, min_share=SHARE, min_uses=USES),
          "'Mert' is a proper name")


def test_apostrophe_suffix_and_absent_name():
    check(naming.usage("Levent", TEXT)[0] >= 3, "'Levent'e' counts as a use of Levent")
    check(naming.proper_share("Zuhal", TEXT) is None, "a name the book never uses is unmeasurable")
    check(not naming.is_proper_name("Zuhal", TEXT, min_share=SHARE, min_uses=USES),
          "an unused name is not a proper name")


def test_alias_cannot_be_another_characters_name():
    groups = [{"canonical": "Levent", "aliases": ["Ben", "Mert"], "entity_scope": "INDIVIDUAL"},
              {"canonical": "Mert", "aliases": [], "entity_scope": "INDIVIDUAL"}]
    v = naming.screen_group_names(groups, TEXT, min_share=SHARE, min_uses=USES)
    check(v[0]["aliases"] == [], "Levent keeps no alias")
    reasons = {d["name"]: d["reason"] for d in v[0]["dropped"]}
    check(reasons["Mert"] == naming.OTHER_CHARACTERS_NAME, "'Mert' refused: another character's name")
    check(reasons["Ben"] == naming.NOT_A_PROPER_NAME, "'Ben' refused: not used as a proper name")
    check(v[1]["person"] and v[1]["aliases"] == [], "Mert himself is untouched")


def test_alias_survives_when_it_is_a_name_of_nobody_else():
    text = TEXT + "\nLevent'in asıl adı Levo'ydu; herkes ona Levo derdi ve Levo gülerdi.\n"
    groups = [{"canonical": "Levent", "aliases": ["Levo"], "entity_scope": "INDIVIDUAL"}]
    v = naming.screen_group_names(groups, text, min_share=SHARE, min_uses=USES)
    check(v[0]["aliases"] == ["Levo"], "a real second name is kept")
    check(v[0]["dropped"] == [], "nothing else refused")


def test_same_written_name_for_two_people_is_not_self_refusing():
    text = TEXT + "\nÖbür Mert de geldi, Mert ve Mert birbirine baktı.\n"
    groups = [{"canonical": "Mert", "aliases": [], "entity_scope": "INDIVIDUAL"},
              {"canonical": "Mert", "aliases": [], "entity_scope": "INDIVIDUAL"}]
    v = naming.screen_group_names(groups, text, min_share=SHARE, min_uses=USES)
    check(all(x["person"] and x["canonical"] == "Mert" for x in v),
          "two homonymous people both keep their canonical name")


def test_collective_is_not_a_person():
    groups = [{"canonical": "Tayfa", "aliases": [], "entity_scope": "COLLECTIVE"},
              {"canonical": "Levent", "aliases": ["Tayfa"], "entity_scope": "INDIVIDUAL"}]
    v = naming.screen_group_names(groups, TEXT, min_share=SHARE, min_uses=USES)
    check(not v[0]["person"] and v[0]["reject_reason"] == naming.SCOPE_NOT_A_PERSON,
          "a collective produces no person record")
    check(v[1]["aliases"] == [], "and its name is not handed to a person either")
    check(v[1]["dropped"][0]["reason"] == naming.NOT_A_PROPER_NAME,
          "'tayfa' is written as a common noun, so it is no one's name")


def test_descriptive_canonical_is_not_punished():
    # A character the book only ever calls "Annesi" keeps that canonical name: (b) is an
    # invariant about aliases, and name_origin already marks the label upstream.
    groups = [{"canonical": "Annesi", "aliases": [], "entity_scope": "INDIVIDUAL"}]
    v = naming.screen_group_names(groups, TEXT, min_share=SHARE, min_uses=USES)
    check(v[0]["person"] and v[0]["canonical"] == "Annesi", "a kinship-label character survives")


def test_turkish_case_folding():
    # "İlker" and "ilker" are one word; "Irmak" and "ırmak" are one word; "Irmak" and
    # "irmak" are not. Python's casefold gets all three wrong.
    t = "Sabah İlker geldi, sonra ilker gitti ve yine ilker döndü."
    check(naming.usage("İlker", t)[0] == 3, "İ/i is one letter pair")
    check(naming.proper_share("İlker", t) < 0.8, "and the lower-case uses count against it")
    t2 = "Kıyıda Irmak durdu ve ırmak akıyordu, ırmak boyunca yürüdüler."
    check(naming.usage("Irmak", t2)[0] == 3, "I/ı is one letter pair")
    check(naming.usage("irmak", t2)[0] == 0, "I/ı is not the same pair as İ/i")


def test_unknown_scope_still_a_person():
    groups = [{"canonical": "Levent", "aliases": [], "entity_scope": "UNKNOWN"}]
    check(naming.screen_group_names(groups, TEXT, min_share=SHARE, min_uses=USES)[0]["person"],
          "UNKNOWN scope is not a rejection")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        print(t.__name__)
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
