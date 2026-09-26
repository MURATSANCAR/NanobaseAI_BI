"""Okur araçları (editor.production.reader, api_reader): model sahte istemciyle, veritabanı yok.

    pytest apps/editor/tests/test_reader.py
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from test_plan import QUIET, _mini  # noqa: F401  (stub modüller ve küçük plan)
from editor.production import plan as P, reader as R, studio  # noqa: E402


class FakeLlm:
    """Okumada: 1. ve 2. okuma «bahçeye koştu»yu işaretler (çoğunluk), 1. okuma ayrıca «güldü»yü (azınlık),
    3. okuma metinde olmayan bir alıntı uydurur (atılmalı). Sayfa çevirmede bağlama göre güçlü/zayıf."""

    def __init__(self):
        self.calls: dict[str, int] = {}
        self.chats = self.chooses = 0

    async def chat(self, alias, messages, *, prompt=None, schema=None, pages=None, max_tokens=0, temperature=0.0,
                   thinking=None, retries=2):
        self.chats += 1
        text = messages[0]["content"]
        if prompt is R.READ:
            k = self.calls.get(text, 0)
            self.calls[text] = k + 1
            assert schema["properties"]["flags"]["items"]["properties"]["item"]["enum"][0] == "M1"
            if k == 0:
                return {"flags": [{"item": "M1", "kind": "KELIME", "quote": "bahçeye koştu", "reason": "bilmiyorum",
                                   "replacement": "bahçeye gitti"},
                                  {"item": "M1", "kind": "SIKICI", "quote": "güldü", "reason": "sıkıldım",
                                   "replacement": ""}]}, 1
            if k == 1:
                return {"flags": [{"item": "M1", "kind": "KELIME", "quote": "Bahçeye  koştu", "reason": "zor",
                                   "replacement": "bahçeye gitti"}]}, 1
            return {"flags": [{"item": "M1", "kind": "CUMLE", "quote": "metinde olmayan bir cümle", "reason": "x",
                               "replacement": "y"}]}, 1
        assert prompt is R.TURN_FIX
        self.fixes = getattr(self, "fixes", 0) + 1
        if self.fixes == 1:
            return {"technique": "AMA", "replacement": "Elif güldü ama sonra ağladı.", "reason": "duygu"}, 1
        return {"technique": "AMA", "replacement": "Elif güldü ama birden bir ses duydu…", "reason": "yarım kaldı"}, 1

    async def choose(self, alias, messages, choices, *, prompt=None, pages=None, seed=17, retries=2):
        self.chooses += 1
        text = messages[0]["content"]
        if prompt is R.TURN_REFUTE:                  # ilk aday hikâyeyi değiştirir (düşer), ikincisi kalır
            return ({"A": 0.2, "B": 0.8} if "ağladı" in text else {"A": 0.85, "B": 0.15}), 1
        if prompt is R.REPLACE:                      # bozuk Türkçe öneri düşer
            return ({"A": 0.1, "B": 0.9} if "uyku uykuya" in text else {"A": 0.8, "B": 0.2}), 1
        if prompt is R.REFUTE:
            return ({"A": 0.9, "B": 0.1} if "güldü" in text.split("İddia")[1] else {"A": 0.3, "B": 0.7}), 1
        return ({"A": 0.9, "B": 0.07, "C": 0.03} if "koştu 1." in text else {"A": 0.1, "B": 0.3, "C": 0.6}), 1


def test_locate_is_verbatim_after_folding():
    t = "Elif “Bak!” dedi.  Sonra  İpek'e koştu."
    assert R.locate("bak!", t) == (6, 10)
    s, e = R.locate("sonra ipek’e koştu", t)
    assert t[s:e] == "Sonra  İpek'e koştu"
    assert R.locate("Sonra İpek'e koştu.", t) is not None                  # sondaki nokta metinde var
    assert R.locate("koştu hemen", t) is None and R.locate("", t) is None and R.locate("a", t) is None


def test_last_sentence():
    t = "Kedi koştu. «Nereye?» dedi Ali! Kapı açıldı"
    s, e = R.last_sentence(t)
    assert t[s:e] == "Kapı açıldı"
    s, e = R.last_sentence("Tek cümle.")
    assert (s, e) == (0, 10)
    assert R.last_sentence("   ") is None
    t = "Aslan çok sevindi.\n“Yaşasın! Parka gidiyoruz!” diye zıpladı."
    s, e = R.last_sentence(t)
    assert t[s:e] == "“Yaşasın! Parka gidiyoruz!” diye zıpladı."
    t = "Güneş battı. Annesi, “Eve dönme zamanı,” dedi."
    s, e = R.last_sentence(t)
    assert t[s:e] == "Annesi, “Eve dönme zamanı,” dedi."


def test_vote_keeps_majority_and_merges_overlaps():
    f = lambda p, s, e, k="KELIME": {"target": "block", "id": "b1", "start": s, "end": e, "quote": "x" * (e - s),  # noqa: E731
                                     "kind": k, "reason": "", "replacement": "r" if p == 0 else "", "pass": p}
    passes = [[f(0, 5, 18), f(0, 30, 35)], [f(1, 5, 12, "CUMLE")], [f(2, 7, 18)]]
    out = R.vote(passes, 3)
    assert len(out) == 1 and out[0]["votes"] == 3 and out[0]["kind"] == "KELIME"
    assert (out[0]["start"], out[0]["end"]) == (5, 18) and out[0]["replacement"] == "r"
    assert out[0]["kinds"] == ["CUMLE", "KELIME"]
    assert R.vote([[f(0, 1, 3)]], 1)[0]["votes"] == 1                        # tek okuma: her işaret kalır
    assert R.vote([[f(0, 1, 3)], []], 2) == []                              # iki okumada tek oy yetmez


def test_child_run_votes_verifies_and_records(tmp_path):
    d = tmp_path / "job"
    _mini(d)
    run = R.new_run(d, "child", "editör", passes=3)
    assert run["age"] == 4 and run["progress"] == [0, 5]
    llm = FakeLlm()
    out = asyncio.run(R.execute(d, run["id"], llm))
    assert out["status"] == "done" and llm.chats == 15 and llm.chooses == 5          # öneri sınaması sayfa başı 1
    view = R.flat(R.load_run(d, run["id"]))
    assert all(f["kind"] == "KELIME" and f["votes"] == 2 and f["passes"] == 3 for f in view["flags"])
    assert len(view["flags"]) == 5 and {f["no"] for f in view["flags"]} == {4, 5, 6, 7, 8}
    f = view["flags"][0]
    pg = P.load(d)["pages"][0]
    text = "".join(r["text"] for r in pg["text"]["blocks"][0]["runs"])
    assert text[f["start"]:f["end"]] == f["quote"] == "bahçeye koştu" and f["replacement"] == "bahçeye gitti"
    assert view["stats"] == {"raw": 15, "dropped": 5, "shown": 5, "failed_pages": 0, "failed_passes": 0, "refuted": 0}
    assert "plan" not in view and "targets" not in view
    R.decide(d, run["id"], f["fid"], "applied", "editör")
    assert R.flat(R.load_run(d, run["id"]))["flags"][0]["decision"] == "applied"
    with pytest.raises(KeyError):
        R.decide(d, run["id"], "k_yok", "applied", "e")
    with pytest.raises(ValueError):
        R.decide(d, run["id"], f["fid"], "sil", "e")
    assert R.latest(d, "child")["flags"] == 5
    # Ana dosyaya karar yazılmaz: koşu sürerken yeniden yazılsa da karar kaybolmaz.
    assert "decisions" not in json.loads((d / R.DIR / f"{run['id']}.json").read_text())


def test_checkable_flags_are_refuted_before_the_editor(tmp_path):
    """Konuşan/resim iddiası ayrı soruyla sınanır: doğrulanmayan işaret düşer ve sayılır."""
    d = tmp_path / "job"
    plan = _mini(d)

    class Llm(FakeLlm):
        async def chat(self, alias, messages, **kw):
            return {"flags": [{"item": "M1", "kind": "KONUSAN", "quote": "güldü", "reason": "kim?", "replacement": ""},
                              {"item": "M1", "kind": "KONUSAN", "quote": "bahçeye koştu", "reason": "kim?",
                               "replacement": ""}]}, 1
    res = asyncio.run(R.read_page(Llm(), d, plan, 0, 6, 1, asyncio.Semaphore(2)))
    assert [f["quote"] for f in res["flags"]] == ["güldü"] and res["refuted"] == 1 and res["flags"][0]["check"] == 0.9


def test_broken_replacement_falls_back_to_another_reading():
    f = {"start": 20, "end": 31, "quote": "mışıl mışıl", "replacement": "uyku uykuya", "alternatives": ["tatlı tatlı"]}
    text = "Etimesgutlu aslan, mışıl mışıl uykuya daldı."
    f["start"], f["end"] = R.locate("mışıl mışıl", text)
    rep, rejected = asyncio.run(R.pick_replacement(FakeLlm(), 3, f, text, 8, asyncio.Semaphore(1)))
    assert rep == "tatlı tatlı" and rejected == 1
    f["alternatives"] = []
    assert asyncio.run(R.pick_replacement(FakeLlm(), 3, f, text, 8, asyncio.Semaphore(1))) == ("", 1)


def test_child_prompt_uses_book_age_and_scene(tmp_path):
    d = tmp_path / "job"
    plan = _mini(d)
    ap = studio.read(d, "artplan.json")
    ap["scenes"] = [{"page": 5, "kind": "flow", "moment": "an", "quote": "q", "characters": ["Elif"],
                     "scene": "Elif mavi kapının önünde", "setting": "bahçe", "grounded": True, "art_id": "a_00000001"}]
    studio.write(d, "artplan.json", ap)
    items = R.page_items(plan["pages"][1])
    scene = R.scene_text(d, plan["pages"][1], plan)
    assert "mavi kapı" in scene and "Elif" in scene
    p = R.child_prompt(9, items, scene, "önce")
    assert "9 yaşında bir çocuksun" in p and "RESIM" in p and "[M1] (paragraf)" in p
    assert "RESIM" not in R.child_prompt(9, items, None, "")
    assert "RESIM" not in R.child_schema(["M1"], False)["properties"]["flags"]["items"]["properties"]["kind"]["enum"]
    assert "gençsin" in R.child_prompt(15, items, None, "") and "okursun" in R.child_prompt(30, items, None, "")


def test_turn_run_only_for_weak_page_ends(tmp_path):
    d = tmp_path / "job"
    _mini(d)
    run = R.new_run(d, "turn", "editör", passes=3)
    assert [t["spread"] for t in run["targets"]] == [[4, 5], [6, 7]]          # son çift sayfadan sonra çevrilmez
    assert all(t["quote"] == "güldü." or t["quote"].endswith("güldü.") for t in run["targets"])
    llm = FakeLlm()
    asyncio.run(R.execute(d, run["id"], llm))
    view = R.flat(R.load_run(d, run["id"]))
    strong, weak = view["spreads"]
    assert strong["status"] == "strong" and "replacement" not in strong
    assert weak["status"] == "suggested" and weak["technique"] == "AMA" and weak["replacement"].startswith("Elif güldü ama")
    assert weak["technique_label"] == "«Ama…» kalıbı" and weak["tried"] == 2 and weak["check"] == 0.85
    assert llm.chooses == 2 + 2 and llm.chats == 2                           # ölçüm ×2, aday ×2 + çürütme ×2
    R.decide(d, run["id"], weak["fid"], "rejected", "e")
    assert R.flat(R.load_run(d, run["id"]))["spreads"][1]["decision"] == "rejected"


def test_turn_hidden_for_books_without_pictures(tmp_path):
    d = tmp_path / "job"
    _mini(d)
    prof = studio.read(d, "profile.json")
    prof["illustration"] = "YOK"
    studio.write(d, "profile.json", prof)
    assert not R.picture_book(d, P.load(d))                                   # 5 sayfanın 1'inde resim
    with pytest.raises(ValueError):
        R.new_run(d, "turn", "e")


def test_interrupted_run_resumes_only_missing_pages(tmp_path):
    d = tmp_path / "job"
    _mini(d)
    run = R.new_run(d, "child", "e", passes=1)
    rec = studio.read(d / R.DIR, f"{run['id']}.json")
    first = rec["plan"]["pages"][0]["id"]
    rec["pages"][first] = {"no": 4, "flags": [], "done": True}
    rec["updated"] = time.time() - 3600
    studio.write(d / R.DIR, f"{run['id']}.json", rec)
    assert R.load_run(d, run["id"])["status"] == "interrupted"
    llm = FakeLlm()
    asyncio.run(R.execute(d, run["id"], llm))
    assert llm.chats == 4 and R.load_run(d, run["id"])["status"] == "done"


def test_api_reader(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from editor.production import api, api_reader
    root = tmp_path / "production"
    _mini(root / "job1")
    monkeypatch.setattr(studio, "root", lambda: root)
    monkeypatch.setattr(api, "KEY", "k")
    monkeypatch.setattr(api_reader, "_llm", lambda d: FakeLlm())
    h = {"Authorization": "Bearer k", "X-Editor": "sinama"}
    with TestClient(api.app) as c:
        assert c.get("/v1/studio/jobs/job1/plan/reader").status_code == 401            # anahtar şart
        info = c.get("/v1/studio/jobs/job1/plan/reader", headers=h).json()
        assert info["age"] == 4 and info["picture_book"] and info["child"] is None
        assert c.post("/v1/studio/jobs/job1/plan/reader/child", headers={"Authorization": "Bearer k"},
                      json={"passes": 3}).status_code == 400                               # X-Editor yok
        assert c.post("/v1/studio/jobs/job1/plan/reader/child", headers=h, json={"passes": 0}).status_code == 422
        studio.set_busy(root / "job1", {"key": "hat", "mode": "run"})
        r = c.post("/v1/studio/jobs/job1/plan/reader/child", headers=h, json={"passes": 3})
        assert r.status_code == 409 and r.json()["code"] == "BUSY"
        studio.set_busy(root / "job1", None)
        rid = c.post("/v1/studio/jobs/job1/plan/reader/child", headers=h, json={"passes": 3}).json()["run"]["id"]
        for _ in range(100):
            view = c.get(f"/v1/studio/jobs/job1/plan/reader/runs/{rid}", headers=h).json()
            if view["status"] != "running":
                break
            time.sleep(0.05)
        assert view["status"] == "done" and len(view["flags"]) == 5
        fid = view["flags"][0]["fid"]
        r = c.post(f"/v1/studio/jobs/job1/plan/reader/runs/{rid}/decisions", headers=h,
                   json={"flag": fid, "decision": "dismissed"})
        assert r.status_code == 200 and r.json()["decisions"][fid]["by"] == "sinama"
        assert c.get("/v1/studio/jobs/job1/plan/reader/runs/r_00000000", headers=h).status_code == 404
        assert c.get("/v1/studio/jobs/job1/plan/reader", headers=h).json()["child"]["id"] == rid
