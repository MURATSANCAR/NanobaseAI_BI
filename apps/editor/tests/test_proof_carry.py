"""Aynı kitapta kararı taşıma — saf parça (proofing/_carry.py). Model ve veritabanı yok. Çalıştır:

    pytest apps/editor/tests/test_proof_carry.py

`editor.proofing` paketi `editor.db` üzerinden psycopg'yi içe alır; yalnız saf fonksiyonlar gerektiği için
sürücü içe almadan önce taklitlenir (test_proof_decision.py ile aynı)."""

from __future__ import annotations

import datetime as dt
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool"):
    sys.modules.setdefault(_mod, _Stub(_mod))

from editor.proofing import _carry as C  # noqa: E402

T0 = dt.datetime(2026, 9, 20, 10, 0, tzinfo=dt.timezone.utc)
GEN_OLD, GEN_NEW = "g-old", "g-new"


def cur(fid, page, quote=None, check="spelling", bbox=None, blocked=False, **details):
    return {"id": fid, "check": check, "page": page, "quote": quote, "bbox": bbox, "details": details, "blocked": blocked}


def src(fid, page, quote=None, check="spelling", verdict=None, reason=None, at=T0, run="r1", gen=GEN_OLD,
        bbox=None, version="1", **details):
    d = None
    if verdict:
        d = {"id": "d-" + fid, "verdict": verdict, "reason_code": reason, "note": None, "decided_by": "editor1",
             "created_at": at, "check_version": version, "read_at": at}
    return {"id": fid, "run_id": run, "generation_id": gen, "check": check, "page": page, "quote": quote,
            "bbox": bbox, "details": details, "decision": d}


# ------------------------------------------------------------------ normalleştirme ve parmak izi
def test_norm_turkish_case_quotes_dashes_space():
    assert C.norm("  «İSTANBUL’da»  ") == "istanbulda"
    assert C.norm("IŞIK") == "ışık"
    assert C.norm("“Hanne” – dedi…") == "hanne - dedi"
    assert C.norm("kita­bı\n  okudu") == "kitabı okudu"
    assert C.norm(None) == "" and C.norm("  ...  ") == ""


def test_fingerprint_ignores_message_version_and_model_labels():
    a = {"check": "word_variety", "quote": "Babam da bir zamanlar", "details": {"lemma": "baba", "sense": "ebeveyn",
         "p_flaw": 0.9, "count": 3}, "message": "eski metin"}
    b = {"check": "word_variety", "quote": "babam da bir zamanlar.", "details": {"lemma": "baba", "sense": "erkek ebeveyn",
         "p_flaw": 0.4, "count": 3}, "message": "yeni metin"}
    assert C.fingerprint(a) == C.fingerprint(b)


def test_fingerprint_type_key_separates_name_pairs_and_skips_message_rules():
    hanne_anne = {"check": "name_spelling", "quote": "Hanne", "details": {"kind": "ad_varyantı", "form": "Hanne", "book_form": "Anne"}}
    hanne_hana = {"check": "name_spelling", "quote": "Hanne", "details": {"kind": "ad_varyantı", "form": "Hanne", "book_form": "Hana"}}
    assert C.fingerprint(hanne_anne) != C.fingerprint(hanne_hana)
    assert ("book_form", "anne") in C.fingerprint(hanne_anne)[1]
    # yazımda `rule` bir mesaj cümlesidir: kimliğe girmez; `kind` kod olduğu için girer
    punct = {"check": "spelling", "quote": "x ,y", "details": {"kind": "virgül_boşluk", "rule": "Virgülden önce boşluk olmaz."}}
    assert dict(C.fingerprint(punct)[1]) == {"kind": "virgül_boşluk"}
    # model etiketi (kategori) kimlik değil; Türkçe küçük harf her iki tarafta aynı uygulanır (I → ı)
    assert C.ident({"phrase": ["çocuk", "öldürmek"], "kind": "SENSITIVE", "category": "VIOLENCE"}) == (
        ("kind", "sensıtıve"), ("phrase", "çocuk öldürmek"))


def test_other_check_is_another_finding():
    assert C.fingerprint({"check": "spelling", "quote": "a"}) != C.fingerprint({"check": "hyphenation", "quote": "a"})


# ------------------------------------------------------------------ eşleme
def test_align_single_quote_wins_over_page():
    pairs, amb = C.align([40], [12])
    assert pairs == {0: 0} and amb == {}


def test_align_nearest_page_and_tie_is_ambiguous():
    pairs, amb = C.align([13, 41], [12, 40])
    assert pairs == {0: 0, 1: 1}
    pairs, amb = C.align([10], [9, 11])
    assert pairs == {} and set(amb[0]) == {0, 1}


def test_align_page_bound_needs_same_page_with_shift():
    assert C.align([5], [7], page_bound=True) == ({}, {})
    assert C.align([9], [7], delta=2, page_bound=True)[0] == {0: 0}


def test_ranks_split_same_page_by_box():
    rows = [{"page": 3, "bbox": [100, 600, 200, 620]}, {"page": 3, "bbox": [100, 200, 200, 220]}, {"page": 4, "bbox": None}]
    assert C.ranks(rows) == [(3, 1), (3, 0), (4, None)]
    pairs, _ = C.align(C.ranks(rows[:2]), C.ranks(list(reversed(rows[:2]))))
    assert pairs == {0: 1, 1: 0}


def test_page_shift_majority():
    fp = lambda q: ("spelling", (), q)  # noqa: E731
    current = [{"_fp": fp(q), "page": p} for q, p in (("a", 12), ("b", 20), ("c", 33), ("d", 50))]
    source = [{"_fp": fp(q), "page": p} for q, p in (("a", 10), ("b", 18), ("c", 31), ("d", 49))]
    assert C.page_shift(current, source) == 2
    assert C.page_shift(current[:2], [{"_fp": fp("a"), "page": 10}, {"_fp": fp("b"), "page": 20}]) == 0  # çoğunluk yok


# ------------------------------------------------------------------ taşıma
def test_carry_reject_and_accept_with_source():
    current = [cur("n1", 12, "hepsinide", kind="bilinmeyen_kelime", word="hepsinide"),
               cur("n2", 30, "Hanne", check="name_spelling", form="Hanne", book_form="Anne")]
    sources = [src("o1", 12, "hepsinide", verdict="REJECT", reason="INTENDED_STYLE", kind="bilinmeyen_kelime", word="hepsinide"),
               src("o2", 30, "Hanne", check="name_spelling", verdict="ACCEPT", run="r2", form="Hanne", book_form="Anne")]
    out, st = C.carry(current, sources, GEN_NEW)
    assert out["n1"]["decision"]["verdict"] == "REJECT" and out["n1"]["finding_id"] == "o1"
    assert out["n2"]["decision"]["verdict"] == "ACCEPT"
    assert st["carried_reject"] == 1 and st["carried_accept"] == 1
    pub = C.public(out["n1"], GEN_NEW)
    assert pub["inherited"] is True and pub["reasonCode"] == "INTENDED_STYLE" and pub["source"]["decisionId"] == "d-o1"
    assert pub["source"]["sameReading"] is False and pub["source"]["checkVersion"] == "1"


def test_own_decision_blocks_carry_but_keeps_its_place():
    # n1 kendi kararlı ve o1'in yerinde: o1 n1'e eşlenir, n2'ye kaymaz (ikisi de aynı alıntı)
    current = [cur("n1", 12, "hepsinide", blocked=True), cur("n2", 80, "hepsinide")]
    sources = [src("o1", 12, "hepsinide", verdict="REJECT", reason="OTHER"), src("o2", 79, "hepsinide")]
    out, _ = C.carry(current, sources, GEN_NEW)
    assert out == {}


def test_newest_decision_wins_and_clear_stops_carry():
    current = [cur("n1", 5, "yanlış")]
    older = src("o1", 5, "yanlış", verdict="REJECT", reason="OTHER", at=T0, run="r1")
    newer = src("o2", 5, "yanlış", verdict="ACCEPT", at=T0 + dt.timedelta(days=1), run="r2")
    out, _ = C.carry(current, [older, newer], GEN_NEW)
    assert out["n1"]["decision"]["verdict"] == "ACCEPT"
    cleared = src("o3", 5, "yanlış", verdict="CLEAR", at=T0 + dt.timedelta(days=2), run="r3")
    out, st = C.carry(current, [older, newer, cleared], GEN_NEW)
    assert out == {} and st["cleared"] == 1


def test_ambiguous_is_not_carried_unless_outcome_is_the_same():
    current = [cur("n1", 10, "sardırı")]
    split = [src("o1", 9, "sardırı", verdict="REJECT", reason="OTHER"), src("o2", 11, "sardırı", verdict="ACCEPT")]
    out, st = C.carry(current, split, GEN_NEW)
    assert out == {} and st["ambiguous"] == 1
    same = [src("o1", 9, "sardırı", verdict="REJECT", reason="OTHER"), src("o2", 11, "sardırı", verdict="REJECT", reason="OTHER")]
    out, _ = C.carry(current, same, GEN_NEW)
    assert out["n1"]["decision"]["verdict"] == "REJECT"
    half = [src("o1", 9, "sardırı", verdict="REJECT", reason="OTHER"), src("o2", 11, "sardırı")]
    out, st = C.carry(current, half, GEN_NEW)
    assert out == {} and st["ambiguous"] == 1


def test_same_word_twice_on_a_page_without_boxes_gets_distinct_sources():
    current = [cur("n1", 89, "sardırı"), cur("n2", 89, "sardırı")]
    sources = [src("o1", 89, "sardırı", verdict="REJECT", reason="OTHER", run="r1"),
               src("o2", 89, "sardırı", verdict="REJECT", reason="OTHER", run="r1")]
    out, _ = C.carry(current, sources, GEN_NEW)
    assert {out["n1"]["finding_id"], out["n2"]["finding_id"]} == {"o1", "o2"}


def test_retypeset_shift_moves_quoted_and_page_bound_findings():
    # yeni dizgi: her şey 2 sayfa ileri; alıntısız düzen bulgusu sayfa + tür ile, kaymayla eşlenir
    current = [cur("a", 12, "alfa"), cur("b", 22, "beta"), cur("c", 32, "gama"),
               cur("x", 14, None, check="layout", rule="margin"), cur("x2", 16, None, check="layout", rule="margin")]
    sources = [src("oa", 10, "alfa"), src("ob", 20, "beta"), src("oc", 30, "gama"),
               src("ox", 12, None, check="layout", verdict="REJECT", reason="NOT_AN_ISSUE", rule="margin"),
               src("ox2", 16, None, check="layout", rule="margin")]
    out, st = C.carry(current, sources, GEN_NEW)
    assert set(out) == {"x"} and out["x"]["page"] == 12
    assert st["shifted_generations"] == 1


def test_rule_version_change_still_carries_and_keeps_the_version():
    current = [cur("n1", 3, "Pegamberimizin", check="hyphenation", rule="proper_noun", word="Peygamberimizin")]
    sources = [src("o1", 3, "Pegamberimizin", check="hyphenation", verdict="REJECT", reason="DICTIONARY_GAP", version="1",
                   rule="proper_noun", word="Peygamberimizin")]
    out, _ = C.carry(current, sources, GEN_NEW)
    assert out["n1"]["decision"]["check_version"] == "1"


def test_same_reading_rerun_has_no_shift():
    current = [cur("n1", 7, "söz")]
    sources = [src("o1", 7, "söz", verdict="ACCEPT", gen=GEN_NEW)]
    out, st = C.carry(current, sources, GEN_NEW)
    assert C.public(out["n1"], GEN_NEW)["source"]["sameReading"] is True and st["shifted_generations"] == 0


def test_migration_028_adds_clear_and_carried_from_and_stays_append_only():
    sql = (Path(__file__).resolve().parents[1] / "db" / "migrations" / "028_proof_decision_carry.sql").read_text(encoding="utf-8")
    assert "carried_from uuid REFERENCES proof_decision(id)" in sql
    assert "'CLEAR'" in sql and "DISABLE TRIGGER" not in sql.upper()
