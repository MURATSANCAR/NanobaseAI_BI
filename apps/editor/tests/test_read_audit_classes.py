"""Okunmuş bir kitabın denetiminden çıkan genel hata sınıfları (2026-10-03). Hiçbir kitap, ad ya da sayfa numarası
koddan okunmaz; buradaki metinler elle yazılmıştır. Model, geçit ve veritabanı yok — taklit edilir.

1. Künye: sayfa kuralı yeni künye sayfası yazınca künye okunur (okumanın künye adımı kuraldan önce koşuyordu).
2. Kitap özeti: uzun kitabın son özet girdisi ≤ 24 iddiaya kitap boyunca yayılarak iner; model bir ucu atlarsa
   uygulama o ucun en önemli doğrulanmış iddiasını kelimesi kelimesine ekler (model çağrısı artmaz).
3. İthaf (satırın herhangi bir yerinde «Ad'a») ve epigraf (alıntı + «— Kaynak») kapsam dışı; gövde sayfası değil.
4. Bütün anmaları kapsam dışı sayfalarda olan karakter çıktıda görünmez.
5. Anlatıcıya göreli akrabalık etiketi («Annem») tek kayda katlanır; kayıtlar iç içe geçiyorsa katlanmaz.
6. Bölüm özeti yalnız bölüm aralığındaki iddiaları alır; aynı cümle iki bölümde tekrarlanmaz.
7. Kategori/yaş önerisi tam okumada da (ayrı patched bayrağı) ve okunmuş kitaplar için tek seferlik doldurma.
8. Veritabanı havuzu küçük ve boşta kapanır; gateway bakım anahtarını paylaşılan cevapla sorar.
"""
from __future__ import annotations

import asyncio
import importlib
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

from editor import identity, outputs, page_scope  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "editor"


# ------------------------------------------------------------------ 1. künye
def test_ensure_reports_newly_marked_imprint_pages(monkeypatch):
    import contextlib
    from editor import db
    monkeypatch.setattr(db, "tx", contextlib.nullcontext, raising=False)
    monkeypatch.setattr(page_scope, "plan", lambda c, gid: {
        "found": {2: ("FRONT_MATTER", "künye"), 7: ("NON_STORY", "ithaf")},
        "writes": {2: ("FRONT_MATTER", "künye"), 7: ("NON_STORY", "ithaf")}, "editor_kept": {}, "roles": {}})
    monkeypatch.setattr(page_scope, "apply", lambda c, gid, writes, **k: len(writes))
    out = page_scope.ensure("g")
    assert out["front_matter_written"] == [2] and out["written"] == 2


def test_imprint_read_again_only_when_new_imprint_pages(monkeypatch):
    calls = []

    async def extract_metadata(gid):
        calls.append(gid)
        return {"ISBN": [{"value": "978"}], "AUTHOR": [{"value": "A"}]}
    fake = types.ModuleType("editor.catalog")
    fake.extract_metadata = extract_metadata
    monkeypatch.setitem(sys.modules, "editor.catalog", fake)
    import editor
    monkeypatch.setattr(editor, "catalog", fake, raising=False)
    assert asyncio.run(page_scope.metadata_after_scope("g", {"front_matter_written": []})) is None
    assert calls == []
    got = asyncio.run(page_scope.metadata_after_scope("g", {"front_matter_written": [2, 3]}))
    assert calls == ["g"] and got == {"fields": ["AUTHOR", "ISBN"], "pages": [2, 3]}

    async def boom(gid):
        raise RuntimeError("model yok")
    fake.extract_metadata = boom
    got = asyncio.run(page_scope.metadata_after_scope("g", {"front_matter_written": [2]}))
    assert got["error"].startswith("RuntimeError")          # künye eksikliği çıktıyı düşürmez


def test_imprint_step_order_in_validation_and_reading():
    rb = (SRC / "rebuild.py").read_text(encoding="utf-8")
    assert rb.index("page_scope.ensure") < rb.index("page_scope.metadata_after_scope") < rb.index("critic_pass")
    ar = (SRC / "archive.py").read_text(encoding="utf-8")
    assert ar.index("page_scope.ensure, gid)") < ar.index("page_scope.metadata_after_scope") < ar.index("critic_pass")
    act = (SRC / "workflow" / "activities.py").read_text(encoding="utf-8")
    body = act[act.index("async def book_metadata"):act.index("async def build_card")]
    assert body.index("page_scope.ensure") < body.index("catalog.extract_metadata")


# ------------------------------------------------------------------ 2. kitap özeti
def _snap(n_pages, outside=()):
    claims, evidence, events = [], [], []
    for i, p in enumerate(range(1, n_pages + 1)):
        cid = f"c{i:04d}"
        claims.append({"id": cid, "kind": "EVENT", "claim": f"Olay {p}", "source_pages": [p], "payload": {},
                       "confidence": 0.9})
        evidence.append({"claim_id": cid, "id": f"e{i}", "quote_verified": True})
        events.append({"claim_id": cid, "importance": 0.9 if p % 10 == 0 else 0.3})
    return {"claims": claims, "evidence": evidence, "events": events, "generation_id": "g",
            "scope": {"out_of_scope_pages": list(outside)}}


def test_final_input_is_capped_and_spread_with_both_ends():
    snap = _snap(300, outside=(1, 2, 300))
    kept = [c for c in snap["claims"] if c["source_pages"][0] % 4 == 0 or c["source_pages"][0] in (3, 299)]
    assert len(kept) > 70
    got = outputs.cap_final(snap, kept, 24)
    pages = [c["source_pages"][0] for c in got]
    assert len(got) <= 24 and pages == sorted(pages)
    assert pages[0] == 3 and pages[-1] == 299               # ilk ve son hikâye iddiası
    assert max(b - a for a, b in zip(pages, pages[1:])) <= 2 * 300 / 22 + 4
    small = kept[:10]
    assert outputs.cap_final(snap, small, 24) == small


def test_missing_end_is_filled_by_the_application_without_a_model_call():
    snap = _snap(100)
    claims = snap["claims"]
    rows = outputs.bind_sentences({"sentences": [{"text": f"Olay {p}", "claim_ids": [claims[p - 1]["id"]]}
                                                 for p in (1, 3, 40)]}, claims, snap["evidence"])
    ends = outputs.edge_pages(claims)
    got = outputs.edge_fill(snap, claims, rows, ends, 24)
    assert len(got) == 4
    last = got[-1]
    assert last["added_by"] == "edge_fill" and last["support_check"] == "EXACT_VERIFIED_CLAIM"
    assert ends[1][0] <= last["pages"][0] <= ends[1][1] and last["text"] == f"Olay {last['pages'][0]}"
    # tavan: eklenen girer, sayfaca en sık yerdeki iç cümle çıkar
    full = outputs.bind_sentences({"sentences": [{"text": f"Olay {p}", "claim_ids": [claims[p - 1]["id"]]}
                                                 for p in [1, 2, 3] + list(range(20, 62, 2))]},
                                  claims, snap["evidence"])
    assert len(full) == 24
    got = outputs.edge_fill(snap, claims, full, ends, 24)
    assert len(got) == 24 and got[-1]["added_by"] == "edge_fill" and got[0]["pages"] == [1]


def test_model_summary_accepted_when_the_model_skips_the_end(monkeypatch):
    """Model kitabın yalnız başından seçti: eskiden üç deneme de reddedilir, özet yedeğe düşerdi."""
    snap = _snap(60)
    calls = []

    class FakeLlm:
        def __init__(self, gid):
            pass

        async def chat(self, alias, messages, **kw):
            calls.append(kw["prompt"].name)
            if kw["prompt"].name == "revision_summary":
                return {"sentences": [{"text": "Olay 1", "claim_ids": ["c0"]},
                                      {"text": "Olay 2 oldu.", "claim_ids": ["c1"]}]}, 1
            return {"verdicts": [{"index": 0, "reason": "", "supported": True},
                                 {"index": 1, "reason": "", "supported": True}]}, 2

    import editor.llm as llm
    monkeypatch.setattr(llm, "Llm", FakeLlm)
    out = asyncio.run(outputs.summarize(snap, snap["claims"], "Kitabın olay örgüsü özeti", plot_only=True))
    assert out["status"] == "SOURCE_SUPPORTED_DRAFT" and out["attempts"] == 1
    assert calls == ["revision_summary", "revision_summary_critic"]
    assert out["sentences"][-1]["added_by"] == "edge_fill" and out["sentences"][-1]["pages"][0] >= 58


# ------------------------------------------------------------------ 3. ithaf ve epigraf
def _novel(n=200):
    body = ("Sabah erkenden kalktı, pencereyi açtı ve sokağı uzun uzun seyretti; komşular işe gidiyor, çocuklar "
            "okula koşuyordu. Kahvesini bitirince kapıyı çekip çıktı ve köşedeki fırına kadar yürüdü, sonra eve döndü.")
    pages = {p: [body] for p in range(1, n + 1)}
    pages[1] = ["Bana masallar anlatan", "büyükannem Fatma'ya."]
    pages[2] = ["“Bütün mutlu aileler birbirine benzer.”", "— Lev Tolstoy"]
    pages[3] = ["BİRİNCİ BÖLÜM", body]
    return pages


def test_dedication_anywhere_in_the_line_and_epigraph_without_suggestion():
    found = page_scope.classify(_novel(), set(), 200, ["Roman"], [])
    assert found[1] == ("NON_STORY", "ithaf")
    assert found[2] == ("NON_STORY", "epigraf")
    assert 3 not in found and 4 not in found               # gövdenin ilk sayfası kapsamda


def test_body_and_dialogue_are_not_dedication_or_epigraph():
    assert not page_scope.is_dedication(["Kedi topu Ayşe'ye verdi."])     # yönelme fiilden önce
    assert page_scope.is_dedication(["Annem Ayşe'ye ve babam Ali'ye,"])
    assert page_scope.is_dedication(["Can'a"])
    assert not page_scope.is_dedication(["Ayşe Ankara'da doğdu."])        # bulunma eki
    assert not page_scope.is_epigraph(["Ali kapıyı açtı.", "— Merhaba Ayşe"])     # tırnaksız, öneri yok
    assert not page_scope.is_epigraph(["— Gel buraya.", "— Tamam."])             # diyalog
    assert not page_scope.is_epigraph(["“Gel,” dedi.", "— Geliyorum, dedi Ali."])  # kaynak değil, cümle
    assert page_scope.is_epigraph(["İnsan yaşadıkça öğrenir.", "– Atasözü"], suggested=True)


def test_short_picture_book_body_page_is_not_a_dedication():
    pages = {p: ["Kedi bahçede oynadı."] for p in range(1, 33)}
    pages[2] = ["Top yuvarlandı, Ayşe'ye."]                  # resimli kitabın gövdesi, ön sayfa sınırında
    pages[5] = ["Kedi topu verdi Ayşe'ye."]                  # ilk %5'in dışında: öneri olmadan aranmaz
    found = page_scope.classify(pages, set(), 32, ["Kedi"], [])
    assert 5 not in found
    # sınır: ilk %5 (en az 2 sayfa) — sayfa 2 ithaf biçimini taşıyorsa ithaf sayılır; gövde sayfası 3+ asla
    assert all(p <= 2 for p in found)


# ------------------------------------------------------------------ 4. kapsam dışı karakter
def test_character_only_on_out_of_scope_pages_is_not_shown():
    chars = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    mentions = {"a": {198, 199}, "b": {5, 199}}               # c: anması yok → hüküm yok
    assert page_scope.characters_outside(chars, mentions, {2, 198, 199}) == {"a"}


def test_capture_filters_characters_by_mention_pages():
    src = (SRC / "outputs.py").read_text(encoding="utf-8")
    assert "page_scope.characters_outside(characters, mention_pages, outside)" in src
    assert "'characters_unused'" in src


# ------------------------------------------------------------------ 5. kimlik: göreli etiket
def _u(name, pages, windows=(), sex="FEMALE", n=3):
    return {"name": name, "kind": "HUMAN_ADULT", "sex": sex, "entity_scope": "INDIVIDUAL", "pages": set(pages),
            "windows": set(windows), "n": n}


def test_relative_label_records_fold_into_one():
    assert identity.is_relative_label("Annem") and identity.is_relative_label("Kız kardeşim")
    assert identity.is_relative_label("sevgili büyükannem") and identity.is_relative_label("oğlum")
    assert not identity.is_relative_label("annesi") and not identity.is_relative_label("Kadın")
    assert not identity.is_relative_label("Beatrice")
    units = [_u("Annem", [3, 20], [0], n=9), _u("annem", [60, 70], [2]), _u("Annem", [120], [4]),
             _u("Kız kardeşim", [30], [1]), _u("kız kardeşim", [150], [5])]
    proper = lambda name: False                              # hiçbiri ad gibi yazılmıyor
    clusters, refused = identity.same_name_plan(units, proper)
    assert sorted(clusters) == [[0, 1, 2], [3, 4]]


def test_relative_labels_of_several_narrators_do_not_fold():
    # iki anlatıcı dönüşümlü: iki «annem» kitabın aynı kesiminde iç içe
    units = [_u("Annem", [10, 30, 50], [0, 1, 2], n=9), _u("Annem", [20, 40, 60], [3, 4, 5])]
    clusters, refused = identity.same_name_plan(units, lambda n: False)
    assert clusters == [] and refused[0]["reason"] == "RELATIVE_LABEL_INTERLEAVED"
    # akrabalık değil: göreli etiket yine birleşmez
    clusters, refused = identity.same_name_plan([_u("kadın", [3], [0]), _u("Kadın", [90], [4])], lambda n: False)
    assert clusters == [] and refused[0]["reason"] == "NOT_A_PROPER_NAME"
    # cinsiyet çelişkisi korunur
    clusters, _ = identity.same_name_plan([_u("Annem", [3], [0]), _u("Annem", [90], [4], sex="MALE")],
                                          lambda n: False)
    assert clusters == []


# ------------------------------------------------------------------ 6. bölüm özeti girdisi
def test_chapter_input_only_claims_inside_the_chapter_once():
    chapters = [{"title": "1", "page_from": 1, "page_to": 10}, {"title": "2", "page_from": 11, "page_to": 20}]
    claims = [{"id": "a", "source_pages": [3, 4]},            # bölüm 1
              {"id": "b", "source_pages": [10, 11]},          # sınırda: çoğu eşit → ilk bölüm, bir kez
              {"id": "c", "source_pages": [2, 18]},           # iki bölüme yayılan tema: hiçbirine
              {"id": "t", "source_pages": [1, 40, 90]},       # bütün kitaba yayılan tema
              {"id": "d", "source_pages": [21]},              # tolerans içinde (bölüm 2'nin sonu + 1)
              {"id": "e", "source_pages": []}]
    got = outputs.chapter_claims(chapters, claims)
    assert [c["id"] for c in got[0]] == ["a", "b"]
    assert [c["id"] for c in got[1]] == ["d"]


def test_same_sentence_kept_only_in_its_first_chapter():
    chs = [{"title": "1", "sentences": [{"text": "Kitap sevgi üzerinedir."}, {"text": "Ali geldi."}]},
           {"title": "2", "sentences": [{"text": "Kitap  sevgi üzerinedir."}, {"text": "Ali gitti."}]}]
    got = outputs.dedupe_chapter_sentences(chs)
    assert [s["text"] for s in got[1]["sentences"]] == ["Ali gitti."]
    assert len(got[0]["sentences"]) == 2


def test_rebuild_uses_the_chapter_input_rule():
    rb = (SRC / "rebuild.py").read_text(encoding="utf-8")
    assert "outputs.chapter_claims(snap['chapters'],snap['claims'])" in rb
    assert "outputs.dedupe_chapter_sentences" in rb


# ------------------------------------------------------------------ 7. kategori/yaş önerisi
def test_full_reading_recommends_under_its_own_marker():
    wf = (SRC / "workflow" / "workflows.py").read_text(encoding="utf-8")
    assert 'archive and workflow.patched("archive-recommend-v1")' in wf
    assert 'not archive and workflow.patched("full-recommend-v1")' in wf
    i = wf.index('"archive_recommend"')
    assert wf.index("outputs_activity, gid") < i < wf.index('"finish_job", job_id, "SUCCEEDED", summary')


def test_fill_targets_are_read_books_without_ok_suggestion():
    from editor import recommend as R
    rows = [{"id": "g1", "title": "B", "profile": "full", "rec_status": None},
            {"id": "g2", "title": "A", "profile": "archive", "rec_status": "FAILED"},
            {"id": "g3", "title": "C", "profile": "full", "rec_status": "OK"}]
    assert [t["id"] for t in R.fill_targets(rows)] == ["g2", "g1"]
    assert [t["id"] for t in R.fill_targets(rows, "full")] == ["g1"]
    with pytest.raises(SystemExit):                          # --all-read şart; kuru koşu varsayılan
        R.main(["fill"])


# ------------------------------------------------------------------ 8. veritabanı bağlantıları
def test_pool_is_small_and_idle_connections_close(monkeypatch):
    from editor import db
    for k in ("EDITOR_DB_POOL_MAX", "EDITOR_DB_POOL_MIN", "EDITOR_DB_POOL_MAX_IDLE", "EDITOR_DB_POOL_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
    lim = db.pool_limits()
    assert lim["min_size"] == 1 and lim["max_size"] <= 8 and lim["max_idle"] <= 60
    monkeypatch.setenv("EDITOR_DB_POOL_MAX", "4")
    monkeypatch.setenv("EDITOR_DB_POOL_MAX_IDLE", "30")
    monkeypatch.setenv("EDITOR_DB_POOL_MIN", "9")
    lim = db.pool_limits()
    assert lim == {"min_size": 4, "max_size": 4, "max_idle": 30.0, "timeout": 600.0}
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    gw = compose[compose.index("  gateway:"):compose.index("  embed:")]
    assert "EDITOR_DB_POOL_MAX" in gw


def test_gateway_shares_the_maintenance_answer(monkeypatch):
    from pathlib import Path
    monkeypatch.setitem(sys.modules, "pynvml", types.SimpleNamespace(nvmlInit=lambda: None))
    dmod = types.ModuleType("docker")
    dmod.from_env = lambda: None
    dtypes = types.ModuleType("docker.types")
    dtypes.DeviceRequest = dtypes.Ulimit = object
    dmod.types = dtypes
    monkeypatch.setitem(sys.modules, "docker", dmod)
    monkeypatch.setitem(sys.modules, "docker.types", dtypes)
    monkeypatch.setenv("EDITOR_MODELS_YAML", str(Path(__file__).resolve().parents[1] / "deploy" / "models.yaml"))
    monkeypatch.setenv("EDITOR_MAINTENANCE_CHECK_SEC", "60")
    sys.modules.pop("editor.gateway", None)
    g = importlib.import_module("editor.gateway")
    from editor import foundation
    n = {"calls": 0}

    def assert_enabled():
        n["calls"] += 1
    monkeypatch.setattr(foundation, "assert_enabled", assert_enabled)

    async def many():
        await asyncio.gather(*(g.check_enabled() for _ in range(30)))
    asyncio.run(many())
    assert n["calls"] == 1                                   # 30 eşzamanlı istek, tek sorgu

    def down():
        raise RuntimeError("EDITOR_MAINTENANCE: bakım")
    monkeypatch.setattr(foundation, "assert_enabled", down)  # anahtar değişti (başka işlev): yeniden sorulur
    with pytest.raises(RuntimeError):
        asyncio.run(g.check_enabled())
    sys.modules.pop("editor.gateway", None)
