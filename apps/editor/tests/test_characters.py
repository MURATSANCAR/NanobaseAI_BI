"""Seri karakter kartı (editor.production.characters, api_characters, images.Painter kancası): model, görsel kimlik
servisi ve veritabanı yok; sahte çağrılarla kuralı sınar. editor-py imajında koşar:

    pytest apps/editor/tests/test_characters.py
"""

from __future__ import annotations

import asyncio
import io
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

from editor.production import characters as ch, studio  # noqa: E402
from editor.production.art import ArtPlan, Character, Scene, Style  # noqa: E402


def _png(w=64, h=64, color="#3366aa") -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = tmp_path / "series"
    monkeypatch.setattr(ch, "series_root", lambda: root)
    monkeypatch.setattr(studio, "root", lambda: tmp_path / "production")
    monkeypatch.delenv("STUDIO_CHARACTER_RETRIES", raising=False)
    return tmp_path


def _job(tmp: Path, name="job1", series="Meraklı Vombat Kitapları | 3", chars=("Elif",)) -> Path:
    d = tmp / "production" / name
    d.mkdir(parents=True)
    studio.write(d, "job.json", {"id": name, "source": {}, "created_by": "t", "art_mode": "auto"})
    studio.write(d, "manuscript.json", {"title": "Kitap " + name, "author": "Y", "illustrator": None,
                                        "meta": {"SERIES": series} if series else {}, "source": {}, "chapters": []})
    studio.write(d, "artplan.json", {
        "style": {"palette": ["#264653"], "accent": "#264653", "avoid": "text", "style_prompt": "watercolour",
                  "medium": "", "line": "", "lighting": "", "mood": "", "why": ""},
        "characters": [{"name": n, "species": "little girl", "look": "short curly hair", "from_text": [],
                        "role": "ANA", "outfits": [{"name": "gündelik", "look": "yellow raincoat", "from_text": []}],
                        "default_outfit": "gündelik"} for n in chars],
        "scenes": [{"page": 5, "kind": "flow", "moment": "", "quote": "", "characters": list(chars), "scene": "in a park",
                    "setting": "park", "grounded": True, "outfits": {}, "setting_reason": "", "new_day": False,
                    "art_id": None}]})
    return d


def _card(name="Elif", **kw) -> dict:
    return {"name": name, "kind": "çocuk", "age": "7", "species_en": "little girl",
            "look_tr": "kısa kıvırcık saçlı", "look_en": "short curly hair, round face",
            "colors": {"hair": "#6b3e26", "eyes": "#3C8D40"}, "palette_color": "#B0341C",
            "outfits": [{"name": "gündelik", "look_tr": "sarı yağmurluk", "look_en": "yellow raincoat",
                         "color": "#F4D03F", "default": True}], **kw}


# ------------------------------------------------------------------ dizi kimliği
def test_series_from_metadata_imprint_and_editor(store):
    d = _job(store)
    s = ch.job_series(d)
    assert s["key"] == "meraklı vombat kitapları" and s["number"] == 3 and not s["exists"]
    assert s["id"] == "merakli-vombat-kitaplari" and s["source"] == "kitap kaydı"
    d2 = _job(store, "job2", series="Timaş Çocuk")                  # dizi ismi yok: yayınevi etiketi, dizi değil
    assert ch.job_series(d2) is None
    s2 = ch.set_job_series(d2, "Meraklı Vombat Kitapları", "ed")
    assert s2["source"] == "editör" and s2["key"] == s["key"]
    assert ch.set_job_series(d2, "", "ed") is None                 # beyan kaldırılınca kurala dönülür


def test_same_series_reuses_existing_directory(store):
    d = _job(store, series="Timaş Çocuk Meraklı Vombat Kitapları")
    s = ch.job_series(d)
    ch.create_card(s, 0, _card(), "ed")
    d2 = _job(store, "job2", series="Meraklı Vombat Kitapları")      # kısa ad, uzun adın sonu: aynı dizi
    s2 = ch.job_series(d2)
    assert s2["exists"] and s2["id"] == s["id"]


# ------------------------------------------------------------------ kart deposu
def test_card_versions_status_and_history(store):
    s = ch.job_series(_job(store))
    data, c = ch.create_card(s, 0, _card(), "ed")
    assert data["rev"] == 1 and c["status"] == "draft" and c["version"] == 1 and c["colors"]["hair"] == "#6B3E26"
    with pytest.raises(ch.Stale):
        ch.update_card(s, 0, c["id"], _card(), "ed")
    data, c = ch.approve(s, c["id"], True, "ed")
    assert c["status"] == "approved" and c["approved_version"] == 1
    data, c2 = ch.update_card(s, data["rev"], c["id"], _card(look_tr="uzun düz saçlı"), "ed")
    assert c2["status"] == "draft" and c2["version"] == 2 and c2["en_stale"]       # Türkçe değişti, İngilizce eski
    with pytest.raises(ValueError, match="modele giden"):
        ch.approve(s, c["id"], True, "ed")
    data, c3 = ch.update_card(s, data["rev"], c["id"], _card(look_tr="uzun düz saçlı", look_en="long straight hair"),
                              "ed")
    assert not c3["en_stale"]
    assert [h["rev"] for h in ch.history(s["id"])] == [4, 3, 2, 1]
    assert (ch.series_dir(s["id"]) / "gecmis" / "3.json").exists()


def test_card_validation_and_duplicates(store):
    s = ch.job_series(_job(store))
    ch.create_card(s, 0, _card(aliases=["Elifçik"]), "ed")
    with pytest.raises(ValueError, match="zaten var"):
        ch.create_card(s, None, _card(name="Elifçik"), "ed")
    with pytest.raises(ValueError, match="#RRGGBB"):
        ch.create_card(s, None, _card(name="Ayşe", colors={"hair": "kırmızı"}), "ed")
    with pytest.raises(ValueError, match="tür"):
        ch.create_card(s, None, _card(name="Ayşe", kind="robot"), "ed")
    with pytest.raises(ValueError, match="en çok"):              # uzun yazı kesilmez, açık hata
        ch.create_card(s, None, _card(name="Ayşe", look_tr="x" * 3000), "ed")


def test_refs_primary_and_remove(store):
    s = ch.job_series(_job(store))
    _, c = ch.create_card(s, 0, _card(), "ed")
    _, r1 = ch.add_ref(s, c["id"], _png(), {"kind": "upload"}, "ed")
    _, r2 = ch.add_ref(s, c["id"], _png(color="#aa0000"), {"kind": "upload"}, "ed")
    assert r1["primary"] and not r2["primary"] and ch.ref_path(s["id"], c["id"], r2["id"]).exists()
    _, card = ch.ref_action(s, c["id"], r2["id"], "primary", "ed")
    assert [r["primary"] for r in card["refs"]] == [False, True]
    _, card = ch.ref_action(s, c["id"], r2["id"], "remove", "ed")
    assert [r["id"] for r in card["refs"]] == [r1["id"]] and card["refs"][0]["primary"]
    with pytest.raises(ValueError, match="okunamadı"):
        ch.add_ref(s, c["id"], b"not an image", {"kind": "upload"}, "ed")


def test_max_retries_setting(store, monkeypatch):
    assert ch.max_retries() == ch.DEFAULT_RETRIES
    monkeypatch.setenv("STUDIO_CHARACTER_RETRIES", "5")
    assert ch.max_retries() == 5
    ch.set_max_retries(0, "yonetim")                            # yönetim ekranındaki değer ortamdan önce gelir
    assert ch.max_retries() == 0


# ------------------------------------------------------------------ resim hattı
def _approved(store, d, with_ref=True) -> dict:
    s = ch.job_series(d)
    _, c = ch.create_card(s, None, _card(), "ed")
    if with_ref:
        ch.add_ref(s, c["id"], _png(), {"kind": "upload"}, "ed")
    _, c = ch.approve(s, c["id"], True, "ed")
    return c


def _plan() -> ArtPlan:
    st = Style("", "", "", "", ["#264653"], "#264653", "watercolour", "text", "")
    return ArtPlan(st, [Character("Elif", "little girl", "short curly hair", [], "ANA",
                                  [{"name": "gündelik", "look": "yellow raincoat", "from_text": []}], "gündelik"),
                        Character("Ali", "boy", "tall", [], "YAN", [], "")])


def test_cardset_prompt_line_and_refs(store):
    d = _job(store)
    s = ch.job_series(d)
    _, draft = ch.create_card(s, None, _card(name="Ali"), "ed")        # taslak kart kullanılmaz
    c = _approved(store, d)
    cards = ch.CardSet.for_job(d)
    assert cards.card("elif")["id"] == c["id"] and cards.card("Ali") is None
    plan = _plan()
    line = cards.line(plan.characters[0], "gündelik")
    assert "short curly hair, round face" in line and "(#6B3E26)" in line and "hair" in line
    assert "yellow raincoat" in line and "(#F4D03F)" in line and "Fixed colours" in line
    assert set(cards.ref_paths(["Elif", "Ali"])) == {"Elif"}


def test_painter_uses_card_and_records_check(store, monkeypatch):
    from editor.production import images
    d = _job(store)
    _approved(store, d)
    kicked = []

    async def kick(job):
        kicked.append(job)
        return "wf"
    monkeypatch.setattr(ch, "kick", kick)
    seen = {}

    async def edit(self, prompt, refs, W, H, seed):
        seen.update(prompt=prompt, refs=len(refs))
        return _png(W // 8, H // 8)

    async def enlarge(self, png, W, H):
        return images.upscale(png, W, H), ""
    monkeypatch.setattr(images.Painter, "_edit", edit)
    monkeypatch.setattr(images.Painter, "enlarge", enlarge)
    p = images.Painter(d / "resim", _plan())
    p.refs = {"Elif": str(d / "yok.png"), "Ali": str(d / "ali.png")}
    assert p.refs["Elif"].startswith(str(ch.series_root()))          # kartın görseli işin referansının önüne geçer
    sc = Scene(5, "flow", "", "", ["Elif"], "in a park", "park", True)

    async def go():
        try:
            return await p.page(sc, 20, 20, seed=7)
        finally:
            await p.close()
    rd = asyncio.run(go())
    assert "Fixed colours" in seen["prompt"] and seen["refs"] == 1 and kicked == ["job1"]
    it = ch._checks(d)["items"][rd.path]
    assert it["status"] == "pending" and it["chars"] == ["Elif"] and it["retry"] and it["size"] == [20, 20]
    assert it["prefix"] == "sayfa-05" and it["attempt"] == 0


def test_painter_without_cards_is_unchanged(store, monkeypatch):
    from editor.production import images
    d = _job(store, series=None)
    p = images.Painter(d / "resim", _plan())
    p.refs = {"Elif": "a.png"}
    assert p.refs == {"Elif": "a.png"} and not p.cards
    assert "Elif is little girl: short curly hair. Wearing: yellow raincoat." in p._prompt("x", [_plan().characters[0]])
    asyncio.run(p.close())


# ------------------------------------------------------------------ denetim ve yeniden üretim
def _pending(d: Path, path: str, attempt=0, root=None, retry=True):
    with ch._checks_tx(d) as data:
        data["items"][path] = {"path": path, "prefix": "sayfa-05", "chars": ["Elif"], "cards": {}, "series": "x",
                               "scene": {"page": 5, "kind": "flow", "moment": "", "quote": "", "characters": ["Elif"],
                                         "scene": "", "setting": "", "grounded": True},
                               "size": [20, 20], "direction": "", "retry": retry, "attempt": attempt,
                               "root": root or path, "status": "pending", "at": ""}


def _setup_check(store, monkeypatch, distances, limit):
    from editor.production import images
    d = _job(store)
    _approved(store, d)
    ch.set_max_retries(limit, "yonetim")
    (d / "resim").mkdir()
    first = str(d / "resim" / "sayfa-05.v1.png")
    Path(first).write_bytes(_png())
    studio.add_version(d, "5", first, mode="edit", prompt="", seed=1, by="t", dpi=300)
    _pending(d, first)
    calls = {"check": 0, "page": 0}

    async def check_items(items, cards, threshold):
        for it in items:
            dist = distances[min(calls["check"], len(distances) - 1)]
            calls["check"] += 1
            it["result"] = {"Elif": {"state": "ok" if dist < threshold else "mismatch", "distance": dist}}
            it["status"] = "ok" if dist < threshold else "mismatch"

    async def page(self, sc, w, h, *, version=1, seed=None, direction="", base_image=None, key=None):
        calls["page"] += 1
        path = str(d / "resim" / f"{key}.v{version}.png")
        Path(path).write_bytes(_png())
        rd = images.Render(f"{key}.v{version}", path, 10, 10, 300, seed, [], "edit", 0.1, "p")
        await ch.record(self, rd, sc, w, h, direction, base_image)
        return rd

    async def kick(job):
        return "wf"
    monkeypatch.setattr(ch, "check_items", check_items)
    monkeypatch.setattr(ch, "kick", kick)
    monkeypatch.setattr(images.Painter, "page", page)
    monkeypatch.setattr(studio, "rebuild", lambda d: None)
    return d, calls


def test_check_retries_until_card_matches(store, monkeypatch):
    d, calls = _setup_check(store, monkeypatch, [0.30, 0.25, 0.05], limit=3)
    out = asyncio.run(ch.run_check(d))
    pg = studio.studio_state(d)["pages"]["5"]
    assert calls["page"] == 2 and out["regenerated"] == 2 and len(pg["versions"]) == 3 and pg["selected"] == 3
    items = ch._checks(d)["items"]
    assert sorted(it["attempt"] for it in items.values()) == [0, 1, 2]
    assert {it["root"] for it in items.values()} == {pg["versions"][0]["path"]}
    assert ch.mismatches(d)["items"] == [] and ch.mismatches(d)["ok"] == 1


def test_check_stops_at_setting_and_keeps_best(store, monkeypatch):
    d, calls = _setup_check(store, monkeypatch, [0.40, 0.20, 0.35], limit=2)
    asyncio.run(ch.run_check(d))
    pg = studio.studio_state(d)["pages"]["5"]
    assert calls["page"] == 2 and len(pg["versions"]) == 3
    assert pg["selected"] == 2                                          # en yakın sürüm (0.20) seçili kaldı
    mm = ch.mismatches(d)["items"]
    assert len(mm) == 1 and mm[0]["status"] == "mismatch" and mm[0]["v"] == 2 and mm[0]["characters"][0]["distance"] == 0.2


def test_check_zero_retries_only_flags(store, monkeypatch):
    d, calls = _setup_check(store, monkeypatch, [0.40], limit=0)
    asyncio.run(ch.run_check(d))
    assert calls["page"] == 0 and ch.mismatches(d)["items"][0]["attempt"] == 0


def test_check_does_not_touch_editor_approved(store, monkeypatch):
    d, calls = _setup_check(store, monkeypatch, [0.40], limit=3)
    st = studio.studio_state(d)
    st["pages"]["5"]["approved"] = True
    studio.write(d, "studio.json", st)
    asyncio.run(ch.run_check(d))
    assert calls["page"] == 0 and ch.mismatches(d)["items"][0]["approved"]


def test_identity_service_down_marks_unchecked(store, monkeypatch):
    d, calls = _setup_check(store, monkeypatch, [0.4], limit=3)

    async def down(items, cards, threshold):
        raise ch.IdentityDown("bağlantı yok")
    monkeypatch.setattr(ch, "check_items", down)
    asyncio.run(ch.run_check(d))
    mm = ch.mismatches(d)
    assert calls["page"] == 0 and mm["unchecked"] == 1 and mm["items"][0]["note"].startswith("Görsel kimlik")


def test_check_items_measures_distance_against_refs(store, monkeypatch):
    d = _job(store)
    _approved(store, d)
    img = d / "p.png"
    img.write_bytes(_png(200, 100))
    cards = ch.CardSet.for_job(d)

    async def locate(http, path, who):
        return {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.8}

    async def feats(http, images_b64):
        return [[1.0, 0.0]] * len(images_b64)

    async def dists(http, f):
        return [[0.0, 0.31], [0.31, 0.0]]
    monkeypatch.setattr(ch, "locate_body", locate)
    monkeypatch.setattr(ch, "_features", feats)
    monkeypatch.setattr(ch, "_distances", dists)
    it = {"path": str(img), "chars": ["Elif"]}
    asyncio.run(ch.check_items([it], cards, 0.15))
    assert it["status"] == "mismatch" and it["result"]["Elif"]["distance"] == 0.31
    assert list(ch.series_dir(cards.series["id"]).glob("ref/*.kimlik.json"))       # referans vektörü önbellekte


# ------------------------------------------------------------------ uçlar
def test_api_endpoints(store, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from editor.production import api
    d = _job(store, name="20260925120000abcdef")
    job = d.name
    monkeypatch.setattr(api, "KEY", "k")
    c = TestClient(api.app)
    h = {"Authorization": "Bearer k", "X-Editor": "sinama"}
    base = f"/v1/studio/jobs/{job}/character-cards"
    assert c.get(base).status_code == 401
    v = c.get(base, headers=h).json()
    assert v["series"]["key"] == "meraklı vombat kitapları" and v["cards"] == [] and v["book"][0]["name"] == "Elif"
    assert v["max_retries"] == ch.DEFAULT_RETRIES
    r = c.post(base + "/cards", headers=h, json={"rev": 0, "card": _card()})
    assert r.status_code == 200
    cid, rev = r.json()["card"]["id"], r.json()["rev"]
    r = c.put(base + f"/cards/{cid}", headers=h, json={"rev": 0, "card": _card()})
    assert r.status_code == 409 and r.json()["code"] == "STALE" and r.json()["rev"] == rev
    r = c.put(base + f"/cards/{cid}/refs?filename=elif.png", headers={**h, "Content-Type": "image/png"},
              content=_png())
    assert r.status_code == 200 and r.json()["ref"]["primary"]
    rid = r.json()["ref"]["id"]
    assert c.get(base + f"/cards/{cid}/refs/{rid}?w=0", headers=h).headers["content-type"] == "image/png"
    assert c.post(base + f"/cards/{cid}/approve", headers=h, json={"ok": True}).json()["card"]["status"] == "approved"
    assert c.put("/v1/studio/character-settings", headers=h, json={"max_retries": 4}).json()["max_retries"] == 4
    assert c.get(base, headers=h).json()["max_retries"] == 4
    assert c.put("/v1/studio/character-settings", headers=h, json={"max_retries": -1}).status_code == 422
    d2 = _job(store, name="20260925120000abcde0", series=None)
    r = c.post(f"/v1/studio/jobs/{d2.name}/character-cards/cards", headers=h, json={"rev": 0, "card": _card()})
    assert r.status_code == 409 and r.json()["code"] == "NO_SERIES"
    r = c.put(f"/v1/studio/jobs/{d2.name}/character-cards/series", headers=h, json={"name": "Meraklı Vombat Kitapları"})
    assert r.json()["series"]["exists"]                                  # önceki kitabın dizisi: kartlar hazır
    assert c.get(f"/v1/studio/jobs/{d2.name}/character-cards", headers=h).json()["cards"][0]["id"] == cid
    assert c.get(f"/v1/studio/jobs/{job}/characters/0", headers=h).status_code == 404   # eski uç bozulmadı


def test_workflows_registered():
    from editor.production.flow import ACTIVITIES, WORKFLOWS
    names = {getattr(w, "__temporal_workflow_definition").name for w in WORKFLOWS}
    assert {"CharacterCheck", "CharacterCards", "BookProduction"} <= names
    acts = {getattr(a, "__temporal_activity_definition").name for a in ACTIVITIES}
    assert {"production_character_check", "production_character_cards"} <= acts


def test_prompts_render():
    from editor.prompts import render
    _, body = render("production_character_card", title="t", name="Elif", age="4-8", species="girl", look="x",
                     outfits="-", quotes="-")
    assert "Elif" in body and "{{" not in body
    _, body = render("production_character_card_en", name="Elif", look="kısa saç", outfits="-")
    assert "kısa saç" in body and "{{" not in body
