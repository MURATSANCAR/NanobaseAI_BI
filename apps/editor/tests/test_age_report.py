"""Yaş uygunluğu raporu (editor.production.age_report, api_age, templates/age_report.typ). Model ve veritabanı yok:
model yerine sahte istemci, kelime derlemi yerine metinden kurulan küçük derlem. Zemberek (zeyrek), Typst ve fontlar
editor-py imajında; yoksa ilgili testler atlanır. Çalıştır:

    pytest apps/editor/tests/test_age_report.py
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

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

pytest.importorskip("zeyrek")

from editor.production import age_report as A, plan as P, spec as S, studio  # noqa: E402
from editor.production.profile import Profile  # noqa: E402

FONTS = Path("/app/data/fonts")
HAS_TYPST = FONTS.joinpath("Andika-Regular.ttf").exists()
try:
    import typst  # noqa: F401
except ImportError:
    HAS_TYPST = False
typeset_only = pytest.mark.skipif(not HAS_TYPST, reason="typst/fontlar yok (editor-py imajında koşar)")

LONG = ("Elif sabah erkenden kalkıp pencereden bahçeye baktığında ağaçların arasında dolaşan küçük kediyi, çiçeklerin "
        "üzerinde uçuşan kelebekleri, çitin yanında oynayan köpeği ve gökyüzünde süzülen kuşları görünce çok sevindi ve "
        "hemen annesine koştu.")
PAGES = [
    [("para", "Elif bahçeye koştu. Kedi ağacın altında uyuyordu. Güneş parlıyordu.")],
    [("heading", "İKİNCİ BÖLÜM"), ("para", LONG)],
    [("para", "Dedesi mutfakta keskin bir bıçak buldu. Elif korktu ve geri çekildi."), ("dialogue", "Dikkat et!")],
    [("para", "Akşam olunca saray ihtişamlı ışıklarla parladı. Elif çok şaşırdı. Herkes bahçeye çıktı.")],
]


def _prof(lo=6, hi=10) -> Profile:
    return Profile(lo, hi, "yayınevi beyanı (künye/CRM)", "RESIMLI_OYKU", "HER_SAYFA", [], {}, {}, {})


def _job(root: Path, band=(6, 10), pages=PAGES) -> Path:
    d = root / "job1"
    d.mkdir(parents=True, exist_ok=True)
    sp = S.build(_prof(*band) if band else _prof())
    studio.write(d, "spec.json", sp.to_json())
    if band:
        studio.write(d, "profile.json", _prof(*band).to_json())
    studio.write(d, "manuscript.json", {"title": "Deneme Kitabı", "author": "Y", "illustrator": None, "meta": {},
                                        "source": {}, "chapters": [{"title": None, "blocks": [
                                            {"kind": "para", "text": t, "pages": []} for pg in pages for _, t in pg]}]})
    studio.write(d, "state.json", {"title": "Deneme Kitabı"})
    studio.write(d, "front.json", {"kunye": [["Yayınevi", "Timaş"]]})
    page = P.geometry(sp)
    out = []
    for i, blocks in enumerate(pages):
        pr = P.preset("text-only", page)
        out.append({"id": f"p_{i:08x}", "chapter": 0, "layout": "text-only", "art": None,
                    "text": {"box": pr["text"], "align": "left", "size": None, "background": None,
                             "blocks": [{"id": f"b{i}{k}", "kind": kind, "runs": [{"text": t}]}
                                        for k, (kind, t) in enumerate(blocks)]},
                    "bubbles": [], "figures": [], "texts": [], "overflow": False})
    P._commit(d, {"version": 1, "rev": 0, "page": page, "pages": out, "assets": {}, "warnings": [],
                  "palette": {"colors": [], "text": "#2C2C2A", "characters": {}}}, "sınama", "kuruldu")
    return d


def _vocab(monkeypatch, d: Path, rare_words=("ihtişamlı",), K=1, extra: dict | None = None):
    """Metnin kendisinden derlem: her kök 100 kitapta, `rare_words`'ün kökleri hiçbirinde."""
    pages, _ = A.job_pages(d)
    toks, _ = A.lemma_tokens(pages)
    rare = {t["lemma"] for t in toks if t["form"] in rare_words}
    assert rare, "seyrek sözcüğün kökü bulunamadı"
    df = {t["lemma"]: (0 if t["lemma"] in rare else 100) for t in toks}
    band = {"books": 288, "K": K, "book_rare_share": [(1, 0.0), (50, 0.01), (95, 0.05), (99, 0.1)], "df": df,
            "rare_books": {}, "book_rare_sizes": [], "same_book_min": 0.5, "same_book_min_size": 5}
    band.update(extra or {})
    monkeypatch.setattr(A, "vocab", lambda: {"bands": {"6-10": band}})
    return rare, toks


class FakeLlm:
    """age_fit.sensitive ve öneri çağrıları için sahte istemci: «bıçak» geçen pasaj şiddet, gerisi yok."""

    def __init__(self):
        self.calls = []

    async def choose(self, alias, messages, letters, pages=None, prompt=None, **kw):
        self.calls.append(("choose", prompt.name))
        text = messages[0]["content"].split("PASAJ:")[-1]
        return ({"B": 0.95, **{k: 0.05 / 7 for k in letters if k != "B"}} if "bıçak" in text
                else {"A": 0.97, **{k: 0.03 / 7 for k in letters if k != "A"}}), 1

    async def chat(self, alias, messages, schema=None, prompt=None, **kw):
        self.calls.append(("chat", prompt.name))
        body = messages[0]["content"]
        if "bicimler" in (schema or {}).get("properties", {}):
            forms = [ln.split("«")[1].split("»")[0] for ln in body.splitlines() if ln.startswith("- «")]
            return {"anlam": "çok gösterişli", "bicimler": [{"bicim": f, "oneriler": ["gösterişli", f]} for f in forms]}, 2
        return {"category": "VIOLENCE", "quote": "keskin bir bıçak buldu", "reason": "Silah olarak görülebilecek eşya."}, 3


@pytest.fixture
def job(tmp_path, monkeypatch):
    root = tmp_path / "production"
    d = _job(root)
    monkeypatch.setattr(studio, "root", lambda: root)
    monkeypatch.setattr(P, "after_write", lambda *a, **k: None)
    monkeypatch.setattr(P, "_typeset", lambda d, plan, build: plan.__setitem__("warnings", []))
    return d


def _run(d, llm=None):
    assert A.claim(d, "sinama")
    return asyncio.run(A.run(d, "sinama", llm=llm or FakeLlm()))


# ------------------------------------------------------------------ metin
def test_job_pages_from_plan(job):
    pl = P.load(job)
    pl["pages"][0]["bubbles"] = [{"id": "b1", "text": "Merhaba!"}]
    pl["pages"][0]["texts"] = [{"id": "t1", "runs": [{"text": "Süs yazısı"}], "z": 3}]
    studio.write(job, "plan.json", pl)
    pages, src = A.job_pages(job)
    assert src == "plan" and [p["page_no"] for p in pages] == [P.FRONT + i + 1 for i in range(4)]
    assert pages[2]["pid"] == "p_00000002" and pages[2]["label"] == f"{P.FRONT + 3}. sayfa"
    assert {"text": "– Dikkat et!", "role": "body"} in pages[2]["spans"]           # konuşma bloğu tireyle
    assert pages[1]["spans"][0]["role"] == "heading"
    assert {"text": "– Merhaba!", "role": "body"} in pages[0]["spans"]             # balon konuşma satırı
    assert {"text": "Süs yazısı", "role": "heading"} in pages[0]["spans"]          # serbest yazı okunabilirliğe girmez
    h = A.text_hash(pages)
    pl["pages"][0]["text"]["blocks"][0]["runs"][0]["text"] += " Yeni cümle."
    studio.write(job, "plan.json", pl)
    assert A.text_hash(A.job_pages(job)[0]) != h


def test_band_from_profile(job, tmp_path):
    assert A.band_of(job) == ((6, 10), "yayınevi beyanı (künye/CRM)")
    studio.write(job, "profile.json", {**_prof().to_json(), "age_source": "model okuması"})
    assert A.band_of(job)[1].startswith("Zeki AI okuması")
    (job / "profile.json").unlink()
    assert A.band_of(job) == (None, "yok")


# ------------------------------------------------------------------ kelime düzeyi
def test_rare_words_listed_with_pages(job, monkeypatch):
    rare, toks = _vocab(monkeypatch, job)
    words, st = A.rare_words(A.job_pages(job)[0], (6, 10))
    assert {w["lemma"] for w in words} == rare
    w = words[0]
    assert w["df"] == 0 and w["pages"][0]["page_no"] == P.FRONT + 4 and "ihtişamlı" in w["pages"][0]["sentence"]
    assert st["rare_tokens"] == 1 and st["content_tokens"] == len(toks) and st["rare_share_p95"] == 0.05
    # bant için derlem yoksa liste yok, sayılar yine ölçülür
    words, st = A.rare_words(A.job_pages(job)[0], (13, 16))
    assert words == [] and st["reference"] is None


def test_names_and_function_words_are_not_vocabulary(job):
    toks, _ = A.lemma_tokens(A.job_pages(job)[0])
    assert all(t["pos"] in ("Noun", "Adj", "Adv", "Verb") for t in toks)
    assert not any(t["word"] == "Elif" for t in toks)                                # özel ad


def test_own_book_in_corpus_is_not_counted(job, monkeypatch):
    pages = A.job_pages(job)[0]
    toks, _ = A.lemma_tokens(pages)
    five = sorted({t["lemma"] for t in toks if t["form"] not in ("ihtişamlı",)})[:5]
    rare_books = {lem: [0] for lem in five}
    _vocab(monkeypatch, job, extra={"rare_books": rare_books, "book_rare_sizes": [5]})
    band = A.vocab()["bands"]["6-10"]
    for lem in five:
        band["df"][lem] = 2                                   # K=1: kendisi sayılırsa seyrek değil
    words, st = A.rare_words(pages, (6, 10))
    assert st["own_book_excluded"] and set(five) <= {w["lemma"] for w in words}
    band["book_rare_sizes"] = [50]                             # başka kitap: payı düşük, dışlanmaz
    words, st = A.rare_words(pages, (6, 10))
    assert not st["own_book_excluded"] and not set(five) & {w["lemma"] for w in words}


# ------------------------------------------------------------------ uçtan uca (sahte model)
def test_run_report_verdict_and_decisions(job, monkeypatch):
    _vocab(monkeypatch, job)
    llm = FakeLlm()
    rep = _run(job, llm)
    kinds = {f["kind"] for f in rep["findings"]}
    assert {"LONG_SENTENCE", "SENSITIVE", "BOOK_MEASURES"} <= kinds
    sens = next(f for f in rep["findings"] if f["kind"] == "SENSITIVE")
    assert sens["pid"] == "p_00000002" and sens["severity"] == "WARN" and sens["quote"] == "keskin bir bıçak buldu"
    long_ = next(f for f in rep["findings"] if f["kind"] == "LONG_SENTENCE")
    assert long_["pid"] == "p_00000001"
    assert all("Ateşman" not in f["message"] and "Bezirci" not in f["message"] for f in rep["findings"])
    w = rep["words"][0]
    assert w["suggestion"]["by_form"]["ihtişamlı"] == ["gösterişli"]             # biçimin kendisi öneri değil
    assert w["pages"][0]["pid"] == "p_00000003"
    assert {c["id"] for c in rep["checks"]} >= {"yas", "cumle", "kelime", "hassas", "punto", "yaslama", "buyuk_harf",
                                                "meb_ibare", "yz_beyan"}
    assert ("chat", "studio_age_synonyms") in llm.calls
    v = A.view(job)
    assert v["status"]["state"] == "done" and not v["report"]["stale"]
    assert v["report"]["verdict"]["level"] == "uyumsuz" and "sayfa" in v["report"]["verdict"]["reasons"][0]
    assert A.preflight_line(job)["status"] == "WARN"
    # editör «sorun değil» der: hassas içerik düşer, uzun cümle kalır → sınırda
    A.decide(job, "finding", sens["id"], "dismissed", "editor1", "masal içinde, tehlike yok")
    v = A.view(job)
    assert v["report"]["verdict"]["level"] == "sinirda"
    assert v["report"]["findings"][[f["id"] for f in v["report"]["findings"]].index(sens["id"])]["decision"]["by"] == "editor1"
    A.decide(job, "finding", long_["id"], "dismissed", "editor1")
    assert A.view(job)["report"]["verdict"]["level"] == "uygun"
    assert A.preflight_line(job)["status"] == "OK"
    # kontrol listesi: kim / ne zaman
    A.decide(job, "check", "reklam", "ok", "editor2", "reklam yok")
    c = next(c for c in A.view(job)["checklist"] if c["id"] == "reklam")
    assert c["decision"]["by"] == "editor2" and c["decision"]["note"] == "reklam yok"
    with pytest.raises(ValueError):
        A.decide(job, "check", "uydurma", "ok", "e")
    with pytest.raises(ValueError):
        A.decide(job, "finding", sens["id"], "belki", "e")
    assert len(A.decisions(job)["log"]) == 3
    # metin değişince rapor bayatlar
    pl = P.load(job)
    pl["pages"][0]["text"]["blocks"][0]["runs"][0]["text"] = "Başka metin."
    studio.write(job, "plan.json", pl)
    assert A.view(job)["report"]["stale"] and "yenileyin" in A.preflight_line(job)["detail"]


def test_apply_approved_word(job, monkeypatch):
    _vocab(monkeypatch, job, rare_words=("bahçeye",))
    _run(job)
    lem = A.view(job)["report"]["words"][0]["lemma"]
    with pytest.raises(ValueError):
        A.apply_word(job, lem, "bahçeye", "avluya", "e")                     # önce onay
    A.decide(job, "word", lem, "approved", "editor1", choice={"bahçeye": "avluya"})
    rev = P.load(job)["rev"]
    out = A.apply_word(job, lem, "bahçeye", "avluya", "editor1")
    assert out["count"] == 3 and out["pages"] == ["p_00000000", "p_00000001", "p_00000003"]
    pl = P.load(job)
    assert pl["rev"] == rev + 1 and "avluya" in P.page_text(pl["pages"][0]) and "bahçeye" not in P.page_text(pl["pages"][3])
    assert A.decisions(job)["word"][lem]["applied"][0]["by"] == "editor1"
    with pytest.raises(ValueError):
        A.apply_word(job, lem, "bahçeye", "avluya", "editor1")               # artık metinde yok


def test_replace_keeps_capital_and_whole_words():
    plan = {"pages": [{"id": "p1", "text": {"blocks": [{"runs": [{"text": "İhtişamlı saray. Çok ihtişamlı! ihtişamlıca"}]}]},
                       "bubbles": [{"text": "ihtişamlı mı?"}]}]}
    n, pages = A.replace_in_plan(plan, "ihtişamlı", "gösterişli")
    assert n == 3 and pages == ["p1"]
    assert plan["pages"][0]["text"]["blocks"][0]["runs"][0]["text"] == "Gösterişli saray. Çok gösterişli! ihtişamlıca"


def test_adult_book_skips_child_checks(tmp_path, monkeypatch):
    root = tmp_path / "production"
    d = _job(root, band=(18, 99))
    monkeypatch.setattr(studio, "root", lambda: root)
    llm = FakeLlm()
    rep = _run(d, llm)
    assert not rep["child"] and rep["checks"] == [] and rep["words"] == [] and llm.calls == []
    assert A.view(d)["report"]["verdict"]["level"] == "cocuk_degil"


def test_no_band_still_scans_sensitive(tmp_path, monkeypatch):
    root = tmp_path / "production"
    d = _job(root, band=None)
    monkeypatch.setattr(studio, "root", lambda: root)
    rep = _run(d)
    assert rep["band"] is None and any(f["kind"] == "SENSITIVE" for f in rep["findings"])
    v = A.view(d)["report"]["verdict"]
    assert v["level"] == "belirtilmemis" and "belirtilmemiş" in v["reasons"][0]


def test_meb_phrase_and_punto(tmp_path, monkeypatch):
    root = tmp_path / "production"
    d = _job(root, pages=PAGES + [[("para", "Bu kitap MEB tavsiyeli bir eserdir.")]])
    monkeypatch.setattr(studio, "root", lambda: root)
    _vocab(monkeypatch, d)
    rep = _run(d)
    c = {c["id"]: c for c in rep["checks"]}
    assert c["meb_ibare"]["status"] == "warn" and c["meb_ibare"]["pages"][0]["pid"] == "p_00000004"
    # 6 yaş → 1. sınıf, ders kitabında en az 20 punto; çocuk kitabı 16 punto → bilgi olarak dikkat
    assert c["punto"]["status"] == "warn" and "20 punto" in c["punto"]["detail"]
    assert A.grade_for(5) is None and A.grade_for(6) == 1 and A.grade_for(9) == 3


def test_failed_model_marks_run_failed(job, monkeypatch):
    _vocab(monkeypatch, job)

    class Broken(FakeLlm):
        async def chat(self, *a, **k):
            raise RuntimeError("yok")
    with pytest.raises(RuntimeError):
        _run(job, Broken())
    st = A.view(job)["status"]
    assert st["state"] == "failed" and "Zeki AI" in st["error"] and A.claim(job, "x")      # hak geri verildi
    A._running.discard(job.name)


# ------------------------------------------------------------------ PDF ve uçlar
@typeset_only
def test_pdf(job, monkeypatch):
    import pymupdf
    _vocab(monkeypatch, job)
    _run(job)
    A.decide(job, "check", "amac", "ok", "editor1")
    p = A.pdf(job)
    doc = pymupdf.open(p)
    text = "".join(pg.get_text() for pg in doc)
    assert doc.page_count >= 2 and "Yaş uygunluğu raporu" in text and "Uyumsuz" in text and "editor1" in text
    assert "ihtişamlı" in text and "Okul Kütüphaneleri Yönetmeliği" in text
    assert doc.metadata["producer"] == "Zeki AI"
    assert A.pdf(job) == p                                           # değişmediyse aynı dosya


def test_api_age(job, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from editor.production import api
    monkeypatch.setattr(api, "KEY", "k")
    _vocab(monkeypatch, job)
    started = []

    async def fake_run(d, by, llm=None):
        started.append((d.name, by))
        A._running.discard(d.name)
    monkeypatch.setattr(A, "run", fake_run)
    c = TestClient(api.app)
    h = {"Authorization": "Bearer k", "X-Editor": "sinama"}
    assert c.get("/v1/studio/jobs/job1/age").status_code == 401
    r = c.get("/v1/studio/jobs/job1/age", headers=h)
    assert r.status_code == 200 and r.json()["report"] is None and len(r.json()["checklist"]) == len(A.CHECKLIST)
    assert c.get("/v1/studio/jobs/job1/age/pdf", headers=h).status_code == 404
    assert c.post("/v1/studio/jobs/job1/age/run", headers={"Authorization": "Bearer k"}).status_code == 400
    assert c.post("/v1/studio/jobs/job1/age/run", headers=h).json() == {"started": True}
    assert started == [("job1", "sinama")]
    r = c.post("/v1/studio/jobs/job1/age/decisions", headers=h, json={"kind": "check", "id": "telif", "state": "ok"})
    assert r.status_code == 200 and next(x for x in r.json()["checklist"] if x["id"] == "telif")["decision"]["by"] == "sinama"
    assert c.post("/v1/studio/jobs/job1/age/decisions", headers=h,
                  json={"kind": "check", "id": "telif", "state": "hmm"}).status_code == 400
    r = c.post("/v1/studio/jobs/job1/age/words/apply", headers=h, json={"lemma": "x", "form": "iki kelime", "to": "y"})
    assert r.status_code == 400
    assert c.get("/v1/studio/jobs/yok/age", headers=h).status_code == 404
