"""Film köprü uçları (semantic_bridge/editorial_studio_film.py): stüdyo servisine giden yol, editör başlığı, kayıt,
kimlik/yol denetimi, medya akışında ileri sarma (Range) ve indirme yetkisi. Stüdyo servisi sahte (httpx MockTransport)."""
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from semantic_bridge import editorial_studio as es
from semantic_bridge import editorial_studio_film as F

FID = "f_0123abcd"
JOB = "20261004101010abcdef"
OLD = "20261004101010aaaaaa"
GONE = "20261004101010bbbbbb"


@pytest.fixture
def env(monkeypatch):
    seen: list[httpx.Request] = []
    audits: list[tuple] = []
    video = bytes(range(256)) * 40

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        path = req.url.path
        if path.endswith("/media/cekim/s01c01.v1.mp4"):
            rng = req.headers.get("range")
            if rng:
                a, b = (int(x) for x in rng.removeprefix("bytes=").split("-"))
                return httpx.Response(206, content=video[a:b + 1], headers={
                    "content-type": "video/mp4", "content-range": f"bytes {a}-{b}/{len(video)}", "accept-ranges": "bytes"})
            return httpx.Response(200, content=video, headers={"content-type": "video/mp4"})
        if path.endswith("/media/cikti/paylasim/tiktok.mp4"):
            return httpx.Response(409, json={"detail": "Paylaşım paketi onaylanmadan indirilemez."})
        if path == f"/v1/studio/jobs/{OLD}/films":
            return httpx.Response(404, json={"detail": "Not Found"})
        if path == f"/v1/studio/jobs/{GONE}/films":
            return httpx.Response(404, json={"detail": "iş yok"})
        if path.endswith("/media/kare/x.exe"):
            return httpx.Response(200, content=b"MZ", headers={"content-type": "application/octet-stream"})
        return httpx.Response(200, json={"ok": True, "path": path, "body": req.content.decode() or None})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(es, "_base", lambda: ("http://studio", {"Authorization": "Bearer k"}, ""))
    monkeypatch.setattr(es, "_client", lambda ca, timeout=30: httpx.Client(transport=transport))
    monkeypatch.setattr(es, "_fresh", lambda ca: httpx.Client(transport=transport))
    app = FastAPI()
    perms = {"veri.disa-aktar": False}
    F.register(app, {"auth": lambda req: ("engine", "t", "ayse.editor", None),
                     "audit": lambda *a: audits.append(a),
                     "can": lambda user, key: perms[key.removeprefix("ozellik:")]})
    return TestClient(app), seen, audits, perms, video


def test_stage_start_maps_path_sets_editor_and_audits(env):
    c, seen, audits, _, _ = env
    r = c.post(f"/api/v1/editorial/studio/jobs/{JOB}/films/{FID}/stages/kareler",
               json={"only": ["s01c02", "../x"], "direction": "daha karanlık", "platforms": ["tiktok"], "evil": 1})
    assert r.status_code == 200
    req = seen[-1]
    assert req.url.path == f"/v1/studio/jobs/{JOB}/films/{FID}/stages/kareler"
    assert req.headers["x-editor"] == "ayse.editor"
    assert json.loads(req.read()) == {"only": ["s01c02"], "direction": "daha karanlık", "platforms": ["tiktok"]}
    assert audits and audits[-1][3] == "studio_film" and "kareler" in audits[-1][5]


def test_bad_ids_and_stages_are_rejected_before_the_service(env):
    c, seen, _, _, _ = env
    assert c.post(f"/api/v1/editorial/studio/jobs/{JOB}/films/f_nope/stages/senaryo", json={}).status_code == 400
    assert c.post(f"/api/v1/editorial/studio/jobs/{JOB}/films/{FID}/stages/yok", json={}).status_code == 404
    assert c.post(f"/api/v1/editorial/studio/jobs/{JOB}/films/{FID}/frames/../select", json={"v": 1}).status_code == 404
    assert c.get(f"/api/v1/editorial/studio/jobs/{JOB}/films/{FID}/media/../../etc/passwd").status_code == 404
    assert c.get(f"/api/v1/editorial/studio/jobs/{JOB}/films/{FID}/media/kare/x.exe").status_code == 404
    assert not seen


def test_media_streams_and_forwards_range(env):
    c, seen, _, _, video = env
    url = f"/api/v1/editorial/studio/jobs/{JOB}/films/{FID}/media/cekim/s01c01.v1.mp4"
    full = c.get(url)
    assert full.status_code == 200 and full.content == video and full.headers["content-type"] == "video/mp4"
    part = c.get(url, headers={"Range": "bytes=10-19"})
    assert part.status_code == 206 and part.content == video[10:20]
    assert part.headers["content-range"].startswith("bytes 10-19/")
    assert seen[-1].headers["range"] == "bytes=10-19"


def test_download_needs_export_permission_and_service_approval(env):
    c, _, _, perms, _ = env
    url = f"/api/v1/editorial/studio/jobs/{JOB}/films/{FID}/media/cikti/paylasim/tiktok.mp4?download=true"
    assert c.get(url).status_code == 403
    perms["veri.disa-aktar"] = True
    r = c.get(url)
    assert r.status_code == 409 and "onaylanmadan" in r.text


def test_old_studio_without_film_routes_reads_as_not_available(env):
    c, _, _, _, _ = env
    r = c.get(f"/api/v1/editorial/studio/jobs/{OLD}/films")
    assert r.status_code == 200 and r.json()["available"] is False and r.json()["films"] == []
    gone = c.get(f"/api/v1/editorial/studio/jobs/{GONE}/films")
    assert gone.status_code == 404 and "iş yok" in gone.text
