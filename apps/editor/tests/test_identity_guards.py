"""Kimlik adımının dört genel koruması (2026-09-30 ölçümünden çıkan sınıflar), sentetik metinle.

1. Kimlik adımı okumayı bitirmez: bağlam aşımı / sözleşme reddi daha küçük pencereyle yeniden
   denenir, hiçbiri okunamazsa anmalar çözülmemiş kalır ve editöre tek soru gider.
2. Takma ad, kitapta karakterin başka bir adıyla aynı sayfada hiç yazılmıyorsa reddedilir
   (uzun adın içindeki kısa ad o uzun adındır).
3. Tanımın atıf sayfası, adın ilk geçtiği sayfadan ayrıdır: tanımın kelimelerinin geçtiği sayfa.
4. Yalnız kitap hakkındaki sayfalarda (yazar notu, künye, karakter listesi) geçen kişi karakter
   olarak yazılmaz.

Hiçbir kitap, ad ya da sayfa numarası koddan okunmaz; buradaki metinler elle yazılmıştır.
Model, geçit ve veritabanı yok — taklit edilir. Çalıştırma: editor-py imajında
`python -m pytest tests/test_identity_guards.py`."""
from __future__ import annotations

import asyncio
import contextlib
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


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool", "httpx",
             "yaml", "pymupdf"):
    _root = _mod.split(".")[0]
    if _missing(_root) or _root in sys.modules and isinstance(sys.modules[_root], _Stub):
        sys.modules.setdefault(_mod, _Stub(_mod))
if _missing("langgraph"):
    _lg, _lgg = types.ModuleType("langgraph"), types.ModuleType("langgraph.graph")

    class _SG:
        def __init__(self, *a, **k): pass
        def add_node(self, *a, **k): pass
        def add_edge(self, *a, **k): pass
        def add_conditional_edges(self, *a, **k): pass
        def compile(self, *a, **k): return self

    _lgg.StateGraph, _lgg.START, _lgg.END = _SG, "START", "END"
    sys.modules.setdefault("langgraph", _lg)
    sys.modules.setdefault("langgraph.graph", _lgg)

from editor import naming  # noqa: E402


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("EDITOR_BUDGET_FORCE_TOKENS", "EDITOR_BUDGET_CHARS_PER_TOKEN", "EDITOR_WINDOW_OVERLAP_PAGES",
              "EDITOR_WINDOW_OVERLAP_ITEMS", "EDITOR_WINDOW_CHAPTER_SNAP", "EDITOR_PROPER_NAME_MIN_SHARE",
              "EDITOR_PROPER_NAME_MIN_USES"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("EDITOR_CONTEXT_TOKENS", "131072")
    monkeypatch.setenv("EDITOR_BUDGET_TOKENIZE", "0")


def _verdict(canonical, aliases):
    return {"person": True, "reject_reason": None, "canonical": canonical, "aliases": list(aliases), "dropped": []}


# ------------------------------------------------------------------ 2. takma ad ortak kanıt ister
def test_name_occurrences_longest_name_owns_its_words():
    pages = {1: "Anna Maria van Schurman geldi. Kız kardeşim Maria güldü.", 2: "Bebek Anna uyudu."}
    occ = naming.name_occurrences(pages, ["Maria", "Anna", "Anna Maria van Schurman"])
    assert occ[1] == {"anna maria van schurman", "maria"}          # içteki «Anna» uzun adındır
    assert occ[2] == {"anna"}


def test_alias_without_a_shared_page_is_refused():
    pages = {10: "Maria bahçede çizim yaptı.", 11: "Annem, Maria, dedi.",
             31: "Tüylü ve endişeli Anna dünyaya geldi.", 33: "Bebek Anna uyudu.",
             140: "Anna Maria van Schurman seksen yaşındaydı. Kız kardeşim Maria diye yazdı."}
    out = naming.screen_shared_evidence(
        [_verdict("Maria", ["Anna"]), _verdict("Anna Maria van Schurman", [])], pages)
    assert out[0]["aliases"] == []
    d = out[0]["dropped"][0]
    assert d["name"] == "Anna" and d["reason"] == naming.NO_SHARED_EVIDENCE and d["pages"] == [31, 33]
    assert out[1]["aliases"] == [] and out[1]["dropped"] == []


def test_alias_linked_by_a_page_or_by_its_form_or_a_chain_is_kept():
    pages = {1: "Mehmet okula gitti.", 2: "Mehmet'e herkes Memo derdi.", 3: "Memo koştu.",
             4: "Memo'ya bazen Memoş da derlerdi.", 5: "Memoş güldü.", 6: "Bulut hoca geldi."}
    out = naming.screen_shared_evidence(
        [_verdict("Mehmet", ["Memo", "Memoş"]), _verdict("Profesör Bulut", ["Bulut"])], pages)
    assert out[0]["aliases"] == ["Memo", "Memoş"] and out[0]["dropped"] == []
    assert out[1]["aliases"] == ["Bulut"]                              # adın kendi kelimesi: bağlı


def test_non_person_verdicts_pass_through():
    v = {"person": False, "reject_reason": naming.SCOPE_NOT_A_PERSON, "canonical": "tayfa",
         "aliases": [], "dropped": []}
    assert naming.screen_shared_evidence([v], {1: "tayfa"}) == [v]


# ------------------------------------------------------------------ 4. kitap hakkındaki sayfalar
def test_paratext_pages_role_and_contributor_on_an_edge_page():
    pages = {p: "Gün geçti." for p in range(1, 101)}
    pages[3] = "Deniz Kaya İzmir'de doğdu. Köpeği Pamuk ile sahilde yürümeyi seviyor."
    pages[50] = "Deniz Kaya adında bir balıkçı vardı."                 # kitabın ortası: hikâye
    pages[99] = "DENİZ KAYA'nın diğer kitapları"
    got = naming.paratext_pages(pages, [4], ["Deniz Kaya", "Kaya"], last_page=100)
    assert got == {3, 4, 99}                          # tek kelimelik ad (Kaya) sayfa belirlemez


def test_edge_page_is_the_credit_bound():
    assert naming.edge_page(6, 40) and naming.edge_page(40, 40) and not naming.edge_page(20, 40)
    assert naming.edge_page(40, 500) and not naming.edge_page(41, 500)


# ------------------------------------------------------------------ 3. tanımın sayfası
def test_description_page_is_where_the_description_is_written():
    pages = {4: "Somurtkan Hala Sirkenaz Bitirim Hürdeniz (Uyanık)",
             47: "Birkaç dakika sonra Helva'nın aklına bir fikir geldi. Terliği aramaya çıkabiliriz.",
             58: "Somurtkan Hala ve torunu geliyor. Herkes ayaktaydı.",
             62: "Sonra kapıda duran Hürdeniz'e döndü. Çok zekiydi. Planlı ve program- lı bir çocuktu.",
             70: "Hürdeniz çantasını aldı. Herkes ayaktaydı."}
    names = {w for n in ("Somurtkan Hala", "Sirkenaz", "Bitirim", "Hürdeniz", "Uyanık", "Helva")
             for w in naming.words(n)}
    got = naming.description_pages("Hürdeniz, Somurtkan Hala'nın torunu, planlı programlı",
                                   pages, [4, 62, 70], names)
    assert got == [62]                                 # kadro sayfası (4) tanımın kaynağı değil
    assert naming.description_pages("Hürdeniz", pages, [4, 62], names) == []


# ------------------------------------------------------------------ 1. kimlik adımı okumayı bitirmez
def test_identity_error_classes():
    from editor import knowledge
    from editor.llm import ContextOverflow, ModelError
    det = knowledge._identity_error_is_deterministic
    assert det(ContextOverflow("400 maximum context length"))
    assert det(ModelError('book-director failed after 3 attempts: 400 {"error": "context length"}'))
    assert det(ModelError("book-director failed after 3 attempts: finish_reason=length after 900 chars"))
    assert det(ValueError("Identity proposal rejected after three attempts: []"))
    assert not det(ModelError("book-director failed after 3 attempts: 503 unavailable"))
    assert not det(ModelError("gpu_busy: another job"))
    assert not det(RuntimeError("connection reset"))


def _fake_book(fail: dict):
    """propose_book taklidi: `fail[shrink]` o küçültmede atılacak hata."""
    calls = []

    async def propose_book(gid, ms, corrections="", shrink=0):
        calls.append(shrink)
        if shrink in fail:
            raise fail[shrink]
        return {"characters": [], "unresolved_mention_ids": [f"m{i}" for i in range(len(ms))],
                "conflicts": []}, 7, {"policy": "p"}
    return propose_book, calls


def test_propose_identity_falls_back_to_smaller_windows(monkeypatch):
    from editor import identity, knowledge
    from editor.llm import ContextOverflow
    fake, calls = _fake_book({0: ContextOverflow("400 context length")})
    monkeypatch.setattr(identity, "propose_book", fake)
    out, call_id, audit = asyncio.run(knowledge._propose_identity("g", [{"id": 1}], "-", False))
    assert calls == [0, 1] and out is not None and call_id == 7
    assert audit["fallback"][0]["shrink"] == 0 and "ContextOverflow" in audit["fallback"][0]["error"]


def test_propose_identity_gives_up_without_raising_and_transient_is_retried(monkeypatch):
    from editor import identity, knowledge
    from editor.llm import ContextOverflow, ModelError
    fake, calls = _fake_book({s: ContextOverflow("400 context length") for s in (0, 1, 2)})
    monkeypatch.setattr(identity, "propose_book", fake)
    out, call_id, audit = asyncio.run(knowledge._propose_identity("g", [{"id": 1}], "-", False))
    assert out is None and calls == [0, 1, 2] and audit["failed"] and len(audit["fallback"]) == 3
    busy, _ = _fake_book({s: ModelError("book-director failed after 3 attempts: 503 busy") for s in (0, 1, 2)})
    monkeypatch.setattr(identity, "propose_book", busy)
    with pytest.raises(ModelError):                     # etkinlik yeniden denesin
        asyncio.run(knowledge._propose_identity("g", [{"id": 1}], "-", False))
    out, _, audit = asyncio.run(knowledge._propose_identity("g", [{"id": 1}], "-", True))
    assert out is None and len(audit["fallback"]) == 3   # son deneme: editöre


def test_propose_book_shrink_never_takes_the_single_call(monkeypatch):
    from editor import identity, knowledge
    pages = [{"page_no": p, "spans": [{"idx": 1, "text": f"Ali {p}. sayfada koştu."}], "issues": []}
             for p in range(1, 101)]
    mentions = [{"id": f"id{p}", "page_no": p, "surface_name": "Ali", "confidence": 0.9,
                 "quote": f"Ali {p}. sayfada koştu."} for p in range(1, 101)]
    calls = []

    async def propose(gid, ms, corrections=""):
        calls.append(len(ms))
        return {"characters": [{"canonical_name": "Ali", "kind": "HUMAN_CHILD", "sex": "MALE",
                                "age_band": "CHILD", "entity_scope": "INDIVIDUAL", "aliases": [],
                                "description": "Ali", "mention_ids": [f"m{i}" for i in range(len(ms))],
                                "merge_basis": "ad", "identity_confidence": 0.9}],
                "unresolved_mention_ids": [], "conflicts": []}, 1, {"attempts": [{}]}

    class NoMerge:
        def __init__(self, gid=None): pass
        async def chat(self, *a, **k): return {"merges": []}, 2

    monkeypatch.setattr(identity.source, "read", lambda gid, page_no=None: pages)
    monkeypatch.setattr(identity, "propose", propose)
    monkeypatch.setattr(identity, "Llm", NoMerge)
    monkeypatch.setattr(knowledge, "chapters", lambda gid: [])
    asyncio.run(identity.propose_book("g", mentions, "-"))
    assert calls == [100]                                              # sığan kitap: tek çağrı
    calls.clear()
    out, _, audit = asyncio.run(identity.propose_book("g", mentions, "-", shrink=1))
    assert len(calls) >= 2 and max(calls) <= 59 and audit["windowed"]  # yarım pencere
    assert sorted(m for c in out["characters"] for m in c["mention_ids"]) == sorted(f"m{i}" for i in range(100))


# ------------------------------------------------------------------ uçtan uca: resolve_character_identity
class _Cur:
    def __init__(self, rows=None):
        self.rows = rows or []

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeLedgerDB:
    """Yalnız kimlik adımının yazdığı/okuduğu SQL: yazılanlar kaydedilir."""

    def __init__(self, role_pages, contributors):
        self.role_pages, self.contributors = role_pages, contributors
        self.executed: list[tuple[str, tuple]] = []
        self.n = 0

    @contextlib.contextmanager
    def tx(self):
        outer = self

        class C:
            def execute(self, sql, params=()):
                outer.executed.append((sql, params))
                outer.n += 1
                if "FROM page_role" in sql:
                    return _Cur([{"page_no": p} for p in outer.role_pages])
                if "to_regclass" in sql:
                    return _Cur([{"t": "ed.book_crm_record"}])
                if "r.authors, r.illustrators" in sql:
                    return _Cur([{"authors": outer.contributors, "illustrators": []}])
                if "SELECT evidence_id FROM character_mention" in sql:
                    return _Cur([{"evidence_id": f"ev-{params[0]}"}])
                if sql.startswith("INSERT INTO claim(") or sql.startswith("INSERT INTO character(") \
                        or sql.startswith("INSERT INTO review_item"):
                    return _Cur([{"id": f"row{outer.n}"}])
                return _Cur()
        yield C()

    def inserted(self, table):
        return [p for s, p in self.executed if s.startswith(f"INSERT INTO {table}(")]


# Elle yazılmış küçük bir kitap: 2. sayfa yazar notu (katkı veren adı, kitabın başında), 3. sayfa
# yalnız adları sıralayan kadro sayfası (çıkarıcının NON_STORY önerisi), hikâye 4. sayfadan.
BOOK = {1: "YAYINEVİ İSTANBUL",
        2: "Deniz Kaya İzmir'de doğdu. Köpeği Pamuk ile sahilde yürümeyi seviyor.",
        3: "Ela Mert",
        4: "Ela sabah kalktı. Sonra Mert kapıyı açtı.",
        5: "Sonra Ela'nın kardeşi Mert güldü. Sonra Ela kitabını aldı.",
        6: "Komşunun bebeği doğdu. Annesi, “Lina'nın güzel bir isim olduğunu düşündüm,” dedi.",
        7: "Ela resim yaptı. Her zaman titiz ve düzenli bir çocuktu.",
        8: "Bebek Lina uyudu."}
BOOK.update({p: "Gün geçti ve akşam oldu." for p in range(9, 41)})

MENTIONS = [("a1", 2, "Deniz Kaya"), ("a2", 2, "Pamuk"), ("e1", 3, "Ela"), ("m1", 3, "Mert"),
            ("e2", 4, "Ela"), ("m2", 4, "Mert"), ("e3", 5, "Ela"), ("m3", 5, "Mert"), ("l1", 6, "Lina"),
            ("e4", 7, "Ela"), ("l2", 8, "Lina")]


def _group(name, ids, desc, kind="HUMAN_CHILD"):
    return {"canonical_name": name, "kind": kind, "sex": "UNKNOWN", "age_band": "UNKNOWN",
            "entity_scope": "INDIVIDUAL", "aliases": [], "description": desc, "mention_ids": ids,
            "merge_basis": "ad", "identity_confidence": 0.9}


def _wire(monkeypatch, db, propose_book):
    from editor import identity, knowledge, ledger
    ms = [{"id": i, "page_no": p, "surface_name": n, "confidence": 0.9, "quote": n} for i, p, n in MENTIONS]
    idx = ledger.PageIndex(text={p: ledger.norm(t) for p, t in BOOK.items()}, visual={}, raw=dict(BOOK),
                           spans={}, generation_id="g")
    monkeypatch.setattr(knowledge.db, "all_rows", lambda sql, *a: ms)
    monkeypatch.setattr(knowledge.db, "tx", db.tx)
    # another test module may have stubbed psycopg before editor.db was imported: JSON as is
    monkeypatch.setattr(knowledge.db, "J", lambda v: v)
    monkeypatch.setattr(ledger.PageIndex, "load", classmethod(lambda cls, c, gid: idx))
    monkeypatch.setattr(knowledge, "corrections_text", lambda gid: "-")
    monkeypatch.setattr(identity, "propose_book", propose_book)
    return ms


def test_resolve_identity_paratext_alias_and_description_page(monkeypatch):
    from editor import knowledge
    ids = {i: f"m{k}" for k, (i, _, _) in enumerate(MENTIONS)}

    async def propose_book(gid, ms, corrections="", shrink=0):
        return {"characters": [
            _group("Deniz Kaya", [ids["a1"]], "Kitabın yazarı", "HUMAN_ADULT"),
            _group("Pamuk", [ids["a2"]], "Yazarın köpeği", "ANIMAL"),
            # model iki ayrı kişiyi birleştirdi: Ela ile bebek Lina
            _group("Ela", [ids[k] for k in ("e1", "e2", "e3", "e4", "l1", "l2")],
                   "Titiz ve düzenli bir çocuk; Mert'in ablası"),
            _group("Mert", [ids[k] for k in ("m1", "m2", "m3")], "Ela'nın kardeşi")],
            "unresolved_mention_ids": [], "conflicts": []}, 11, {"policy": "p"}

    db = FakeLedgerDB(role_pages=[3], contributors=["Deniz Kaya"])
    _wire(monkeypatch, db, propose_book)
    res = asyncio.run(knowledge.resolve_character_identity("g"))
    chars = {p[1]: p for p in db.inserted("character")}
    assert set(chars) == {"Ela", "Mert"}                               # yazar ve köpeği karakter değil
    refused = {r["name"]: r["reason"] for r in res["entities_refused"]}
    assert refused == {"Deniz Kaya": naming.PARATEXT_ONLY, "Pamuk": naming.PARATEXT_ONLY}
    ela = chars["Ela"]
    assert ela[2] == []                                                # Lina takma ad değil
    assert ela[6] == 3                                                 # first_page: adın ilk geçtiği sayfa
    traits = ela[9].obj if hasattr(ela[9], "obj") else ela[9]
    assert traits["description_pages"][0] == 7                         # tanımın sayfası
    assert [d["reason"] for d in traits["names_refused"]] == [naming.NO_SHARED_EVIDENCE]
    loosened = {p[0] for s, p in db.executed if s.startswith("UPDATE character_mention SET character_id=NULL")}
    assert {"l1", "l2", "a1", "a2"} <= loosened
    # Ela'nın kimlik iddiası tanımın sayfasına atıf yapar (kadro sayfasına değil)
    ela_claim = next(p for p in db.inserted("claim") if p[2] == "Ela")
    assert ela_claim[4] == [7]
    assert res["characters"] == 2


def test_resolve_identity_readers_about_the_book_needs_an_edge_page(monkeypatch):
    """Sayfa rolü ve CRM yokken: okuyucunun ABOUT_THE_BOOK kararı yalnız kitabın başında/sonunda
    adı geçen kişide geçerli; hikâyenin ortasındaki kişi yanlış okunsa da karakter kalır."""
    from editor import knowledge
    ids = {i: f"m{k}" for k, (i, _, _) in enumerate(MENTIONS)}

    async def propose_book(gid, ms, corrections="", shrink=0):
        about = {"book_role": "ABOUT_THE_BOOK"}
        return {"characters": [
            _group("Deniz Kaya", [ids["a1"]], "Kitabın yazarı", "HUMAN_ADULT") | about,
            _group("Ela", [ids[k] for k in ("e1", "e2", "e3", "e4")], "Titiz bir çocuk") | about,
            _group("Mert", [ids[k] for k in ("m1", "m2", "m3")], "Ela'nın kardeşi") | {"book_role": "STORY"}],
            "unresolved_mention_ids": [ids[k] for k in ("a2", "l1", "l2")], "conflicts": []}, 11, {"policy": "p"}

    monkeypatch.setitem(BOOK, 7, "Ela resim yaptı. Titiz bir çocuktu.")
    monkeypatch.setitem(BOOK, 30, "Ela eve döndü.")                   # kitabın ortası
    ids["e5"] = f"m{len(MENTIONS)}"                                   # the next mention id
    monkeypatch.setattr(sys.modules[__name__], "MENTIONS", MENTIONS + [("e5", 30, "Ela")])
    db = FakeLedgerDB(role_pages=[], contributors=[])
    _wire(monkeypatch, db, propose_book)

    async def with_e5(gid, ms, corrections="", shrink=0):
        out = await propose_book(gid, ms, corrections, shrink)
        out[0]["characters"][1]["mention_ids"].append(ids["e5"])
        return out
    from editor import identity
    monkeypatch.setattr(identity, "propose_book", with_e5)
    res = asyncio.run(knowledge.resolve_character_identity("g"))
    assert {p[1] for p in db.inserted("character")} == {"Ela", "Mert"}
    assert {r["name"]: r["reason"] for r in res["entities_refused"]} == {"Deniz Kaya": naming.PARATEXT_ONLY}


def test_resolve_identity_that_cannot_be_read_goes_to_the_editor(monkeypatch):
    from editor import knowledge
    from editor.llm import ContextOverflow

    async def propose_book(gid, ms, corrections="", shrink=0):
        raise ContextOverflow("400 This model's maximum context length is 131072 tokens")

    db = FakeLedgerDB(role_pages=[], contributors=[])
    _wire(monkeypatch, db, propose_book)
    res = asyncio.run(knowledge.resolve_character_identity("g"))
    assert res["identity_failed"] and res["characters"] == 0 and res["review_queued"]
    assert db.inserted("character") == []
    claim = db.inserted("claim")[0]
    payload = claim[5].obj if hasattr(claim[5], "obj") else claim[5]
    assert claim[1] == "CHARACTER_IDENTITY" and payload["identity_failed"] and claim[6] == 0.0
    review = next(p for s, p in db.executed if s.startswith("INSERT INTO review_item"))
    assert review[3].startswith("Karakter kimliği birleştirilemedi") and review[4] == 1


def test_read_model_gives_the_description_page_apart_from_the_first_page():
    from editor import read_model
    snap = {"claims": [{"id": "c1", "claim": "Hürdeniz: Somurtkan Hala'nın torunu, planlı programlı"}],
            "characters": [
                {"id": "h", "canonical_name": "Hürdeniz", "aliases": ["Uyanık"], "identity_status": "CONFIRMED",
                 "identity_confidence": 0.9, "first_page": 4, "claim_id": "c1",
                 "traits": {"description_pages": [62, 58]}},
                {"id": "o", "canonical_name": "Eski", "aliases": [], "identity_status": "CANDIDATE",
                 "identity_confidence": 0.5, "first_page": 9, "claim_id": None, "traits": {}}]}
    h, o = read_model.characters(snap)
    assert h["first_page"] == 4 and h["description_page"] == 62 and h["description_pages"] == [62, 58]
    assert o["description_page"] is None and o["description_pages"] == []      # eski okuma: alan yok
