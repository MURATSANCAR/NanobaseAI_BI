"""Bütün kitap kişi birleştirmesi okumanın kendi adımı (2026-10-05, «Devlerin Savaşı»: 318 karakterde aynı adlı
kayıtlar kaldı; `identity_fold` yalnız elle çalışıyordu).

- İş akışı (`identity-fold-v1`): kimlik adımından hemen sonra, görsel kimlikten ve son okuma denetimlerinden önce
  `fold_identities` koşar — tam, arşiv ve redaksiyon profilinde; hata okumayı düşürmez (failures.identity_fold).
- Etkinlik ana döngüde iş yapmaz (iş parçacığında); batch_guard'a sorulmaz (kendi işinin nesli).
- Tekrar zararsız: ikinci koşu hiçbir şey yazmaz (çakışma işareti ikinci kez eklenmez); çıktı doğrulaması
  (rebuild.validate / archive.validate) önce birleştirir, hatası kurulumu durdurmaz.
- Kural: şapka (â/î/û) adı ayırmaz; dilde ortak sözcük de olan ad («Almaz» / «almaz») kitap genelinde payı tutmasa
  da her kaydın kendi alıntısı adı cümle ortasında büyük harfle yazıyorsa ad sayılır.

Hiçbir kitap, ad ya da sayfa numarası koddan okunmaz; buradaki metinler elle yazılmıştır. Model ve veritabanı yok."""
from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import inspect
import pathlib
import sys
import time
import types
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

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


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool", "httpx",
             "yaml", "pymupdf", "qdrant_client", "qdrant_client.models"):
    _root = _mod.split(".")[0]
    if _missing(_root) or _root in sys.modules and isinstance(sys.modules[_root], _Stub):
        sys.modules.setdefault(_mod, _Stub(_mod))

from editor import identity, identity_fold, identity_links  # noqa: E402

# kitap genelinde 3 büyük / 2 küçük harfli cümle ortası kullanım: pay 0,6 < 0,8 (ad ile fiil aynı yazılıyor)
BOOK = ("Yolda Toygar, Almaz ile karşılaştı. Bu at kolay kolay yem almaz, dedi seyis. Sonra yine Almaz geldi; "
        "Toygar, Almaz'ın yumruğunu hatırladı. Kimse ondan ders almaz. Akşam oldu.")


def _u(name, pages, quotes, n=None, windows=()):
    return {"name": name, "kind": "HUMAN_ADULT", "sex": "MALE", "entity_scope": "INDIVIDUAL", "pages": set(pages),
            "windows": set(windows), "aliases": [], "n": n if n is not None else len(pages), "quotes": quotes}


# ------------------------------------------------------------------ kural
def test_circumflex_does_not_split_a_name():
    assert identity.name_key("Alâeddin Keykubat") == identity.name_key("Alaeddin Keykubat")
    assert identity.name_key("HÂLİD") == identity.name_key("Halid")              # büyük harf + şapka
    proper = identity.ProperNameTest("Sonra Alâeddin Keykubat geldi. Ardından Alaeddin Keykubat gitti.", 0.8, 1)
    clusters, refused = identity.same_name_plan(
        [_u("Alâeddin Keykubat", [211], []), _u("Alaeddin Keykubat", [202], [])], proper)
    assert clusters == [[0, 1]]


def test_common_word_name_joins_when_each_record_writes_it_as_a_name():
    proper = identity.ProperNameTest(BOOK, 0.8, 1)
    assert not proper("Almaz")                                       # kitap geneli: pay tutmuyor
    units = [_u("Almaz", [106, 113], ["Yolda Toygar, Almaz ile karşılaştı.", "Toygar, Almaz'ın yumruğunu"]),
             _u("Almaz", [129], ["bacağı aksayan Almaz yine geldi"])]
    clusters, refused = identity.same_name_plan(units, proper)
    assert clusters == [[0, 1]] and not refused
    # bütün kitap planı (K18 etiket yolu) aynı kaydı bir de «etiket» diye reddetmez
    lp = identity_links.link_plan(units, {}, proper, "")
    assert lp["clusters"] == [[0, 1]] and not lp["refused"]


def test_common_word_name_without_own_evidence_stays_refused():
    proper = identity.ProperNameTest(BOOK, 0.8, 1)
    # ikinci kaydın alıntısı adı yalnız cümle başında yazıyor: büyük harf cümlenin, ad kanıtı değil
    units = [_u("Almaz", [106], ["Yolda Toygar, Almaz ile karşılaştı."]), _u("Almaz", [129], ["Almaz geldi."])]
    clusters, refused = identity.same_name_plan(units, proper)
    assert clusters == [] and refused[0]["reason"] == "NOT_A_PROPER_NAME"
    # alıntıda küçük harfle (sözcük olarak) geçiyorsa da ad değil
    units[1]["quotes"] = ["kimse ondan ders almaz"]
    assert identity.same_name_plan(units, proper)[0] == []
    # alıntısız kayıt (eski birimler, düz işlev) eski kural: reddedilir
    assert identity.same_name_plan([_u("Almaz", [1], []), _u("Almaz", [9], [])], proper)[0] == []
    assert identity.same_name_plan([_u("Almaz", [1], ["a, Almaz b"]), _u("Almaz", [9], ["c, Almaz d"])],
                                   lambda n: False)[0] == []


def test_title_variant_is_not_joined_by_name():
    """«X Bey» ile «X» aynı ad anahtarı değildir; bu planda birleşmez (unvan koruması ayrı karardır)."""
    proper = identity.ProperNameTest("Ali, Menteşeoğlu Mustafa Bey ile Menteşeoğlu Mustafa'yı andı.", 0.8, 1)
    clusters, _ = identity.same_name_plan([_u("Menteşeoğlu Mustafa", [109, 197], []),
                                          _u("Menteşeoğlu Mustafa Bey", [308], [])], proper)
    assert clusters == []


def _fold_db(monkeypatch, rows, pages, quotes, page_text):
    from editor import config, db, source
    calls = {"read": 0}

    def all_rows(sql, *a):
        if sql == identity_fold._CHARS:
            return rows
        if sql == identity_fold._PAGES:
            return pages
        if sql == identity_fold._QUOTES:
            return quotes
        raise AssertionError(sql)

    def read(gid):
        calls["read"] += 1
        return [{"page_no": p, "text": t} for p, t in page_text.items()]
    monkeypatch.setattr(db, "all_rows", all_rows)
    monkeypatch.setattr(source, "read", read)
    monkeypatch.setattr(source, "body_text", lambda ps: "\n".join(p["text"] for p in ps))
    monkeypatch.setattr(config, "settings", lambda: SimpleNamespace(proper_name_min_share=0.8,
                                                                    proper_name_min_uses=1))
    return calls


def _row(cid, name, window):
    return {"id": cid, "canonical_name": name, "aliases": [], "kind": "HUMAN_ADULT", "traits": {"sex": "MALE"},
            "identity_status": "CONFIRMED", "identity_confidence": 0.95, "first_page": 1, "description": "",
            "windows": [{"window": window}], "attributes": 0}


def test_fold_plan_reads_each_records_text_quotes(monkeypatch):
    rows = [_row("c1", "Almaz", 2), _row("c2", "Almaz", 3)]
    pages = [{"character_id": "c1", "pages": [106, 113], "n": 2}, {"character_id": "c2", "pages": [129], "n": 1}]
    quotes = [{"character_id": "c1", "via": "TEXT", "quote": "Yolda Toygar, Almaz ile karşılaştı."},
              {"character_id": "c1", "via": "VISUAL", "quote": "almaz"},          # görsel anma sayılmaz
              {"character_id": "c2", "via": "BOTH", "quote": "bacağı aksayan Almaz yine geldi"}]
    _fold_db(monkeypatch, rows, pages, quotes, {106: BOOK})
    p = identity_fold.plan("g", "Kitap")
    assert [(j["keep"], j["fold"]) for j in p["joins"]] == [("c1", ["c2"])]
    assert p["_units"]["c1"]["quotes"] == ["Yolda Toygar, Almaz ile karşılaştı."]


def test_fold_plan_of_a_generation_without_characters_reads_nothing(monkeypatch):
    calls = _fold_db(monkeypatch, [], [], [], {})
    p = identity_fold.plan("g", "Kitap")
    assert p["characters"] == 0 and p["joins"] == [] and calls["read"] == 0
    assert identity_fold.run("g")["records_folded"] == 0


# ------------------------------------------------------------------ tekrar zararsız, batch_guard'a sorulmaz
class _Conn:
    def __init__(self):
        self.sql = []

    def execute(self, sql, args=None):
        self.sql.append((sql, args))
        return SimpleNamespace(fetchall=lambda: [], fetchone=lambda: None)


def _tx(monkeypatch):
    from editor import db
    conn = _Conn()

    @contextlib.contextmanager
    def tx():
        yield conn
    monkeypatch.setattr(db, "tx", tx)
    return conn


def test_apply_flags_an_alias_conflict_once(monkeypatch):
    conn = _tx(monkeypatch)
    mark = {"alias": "bee", "records": 2}
    p = {"generation_id": "g", "joins": [],
         "alias_conflicts": [{"alias": "bee", "action": "flag", "records": 2, "owner": None, "holders": ["c1", "c2"]}],
         "_unnamed": {"c1": False, "c2": False},
         "_units": {"c1": {"traits": {"alias_conflicts": [mark], "unnamed": False}, "aliases": ["Bee"]},
                    "c2": {"traits": {"unnamed": False}, "aliases": ["Bee"]}}}
    identity_fold.apply(p)
    flagged = [a for s, a in conn.sql if "alias_conflicts" in s]
    assert [a[1] for a in flagged] == ["c2"]                         # c1 zaten işaretli
    # ikinci koşu: ikisi de işaretli, «unnamed» değişmedi → hiçbir yazma yok
    p["_units"]["c2"]["traits"]["alias_conflicts"] = [mark]
    conn.sql.clear()
    identity_fold.apply(p)
    assert conn.sql == []


def test_run_does_not_ask_batch_guard(monkeypatch):
    from editor import batch_guard
    monkeypatch.setattr(batch_guard, "busy", lambda ids: {g: "okuma sürüyor" for g in ids})
    applied = []
    plan = {"generation_id": "g", "characters": 2, "records_folded": 1, "records_blocked": 0, "characters_after": 1,
            "joins": [{"name": "Ali", "keep": "c1", "fold": ["c2"], "rules": ["SAME_NAME"],
                       "blocked_by_attributes": []}], "refused": [{"reason": "SAME_PAGE"}], "narrator": None,
            "alias_conflicts": [], "unnamed": 0, "minor": 0, "_unnamed": {}, "_units": {}}
    monkeypatch.setattr(identity_fold, "plan", lambda gid, title=None: plan)
    monkeypatch.setattr(identity_fold, "apply", lambda p: applied.append(p["generation_id"]) or {"applied": []})
    out = identity_fold.run("g")
    assert applied == ["g"] and out["records_folded"] == 1
    assert out["joins"] == [{"name": "Ali", "records": 2, "rules": ["SAME_NAME"], "blocked": 0}]
    assert out["refused"] == {"SAME_PAGE": 1} and "_units" not in out


def test_output_validation_folds_first_and_survives_a_failure(monkeypatch):
    from editor import archive, rebuild
    for fn in (rebuild.validate, archive.validate):
        src = inspect.getsource(fn)
        assert "fold_identities" in src and src.index("fold_identities") < src.index("critic_pass"), fn
    monkeypatch.setattr(identity_fold, "run", lambda gid: (_ for _ in ()).throw(ConnectionResetError("db")))
    assert "db" in rebuild.fold_identities("g")["error"]
    monkeypatch.setattr(identity_fold, "run", lambda gid: {"characters": 3, "records_folded": 1,
                                                           "records_blocked": 0, "characters_after": 2, "joins": []})
    assert rebuild.fold_identities("g") == {"characters": 3, "records_folded": 1, "records_blocked": 0,
                                            "characters_after": 2}


# ------------------------------------------------------------------ etkinlik ana döngüde iş yapmaz
def test_fold_activity_keeps_the_loop_turning(monkeypatch):
    pytest.importorskip("temporalio")
    from editor.workflow import activities as A
    from test_activity_loop import BLOCK, MAX_GAP, Ticker
    assert A.fold_identities in A.ALL
    monkeypatch.setattr(identity_fold, "run", lambda gid: (time.sleep(BLOCK), {"records_folded": 0})[1])

    async def main():
        with Ticker() as t:
            assert await A.fold_identities("g") == {"records_folded": 0}
        return t.max_gap
    assert asyncio.run(main()) < MAX_GAP


# ------------------------------------------------------------------ iş akışı
FOLD = {"characters": 5, "records_folded": 2, "records_blocked": 0, "characters_after": 3, "joins": []}


def _order(calls, *names):
    seen = [n for n, _ in calls]
    return [seen.index(n) for n in names]


def test_full_reading_folds_after_identity_before_visual_identity_and_final_read():
    from test_step_retry import _finish, _run
    out, calls, hist = _run("full", {"fold_identities": lambda n, gid: FOLD})
    status, result = _finish(calls)
    assert status == "SUCCEEDED" and "identity-fold-v1" in hist
    ident, fold, vis, proof, outputs = _order(calls, "resolve_identity", "fold_identities", "visual_identity",
                                              "proofreading", "rebuild_outputs")
    assert ident < fold < vis and fold < proof and fold < outputs
    assert [v for n, v in calls if n == "fold_identities"] == [["g1"]]
    assert result["identity_fold"] == {k: FOLD[k] for k in ("characters", "records_folded", "records_blocked",
                                                            "characters_after")}


def test_archive_reading_folds_before_visual_identity_and_outputs():
    from test_step_retry import _finish, _run
    out, calls, hist = _run("archive", {"fold_identities": lambda n, gid: FOLD})
    status, result = _finish(calls)
    assert status == "SUCCEEDED" and "identity-fold-v1" in hist
    ident, fold, vis, outputs = _order(calls, "resolve_identity", "fold_identities", "visual_identity",
                                       "archive_outputs")
    assert ident < fold < vis < outputs


def test_redaction_folds_before_final_read_checks():
    from test_step_retry import _finish, _run
    out, calls, hist = _run("redaction", {"fold_identities": lambda n, gid: FOLD})
    status, result = _finish(calls)
    assert status == "SUCCEEDED" and result["identity_fold"]["records_folded"] == 2
    fold, proof = _order(calls, "fold_identities", "proofreading")
    assert fold < proof


def test_fold_failure_never_fails_the_reading():
    from test_step_retry import _app_error, _finish, _run

    def boom(n, gid):
        raise _app_error("plan kırıldı", "ValueError")
    out, calls, hist = _run("archive", {"fold_identities": boom})
    status, result = _finish(calls)
    assert status == "SUCCEEDED" and "plan kırıldı" in result["failures"]["identity_fold"][0]
    assert "identity_fold" not in result
    assert sum(1 for n, _ in calls if n == "fold_identities") == 1        # ValueError yeniden denenmez
