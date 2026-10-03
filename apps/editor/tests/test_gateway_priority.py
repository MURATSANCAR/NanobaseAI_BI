"""Etkileşimli öncelik (2026-10-03): Kitaba sor, okumalar yönetici modelin 32 koltuğunu doldururken vLLM FCFS
sırasında dakikalarca bekledi. Yönetici `--scheduling-policy priority` ile açılır; gateway etkileşimli isteğe küçük,
okumaya büyük öncelik koyar; koltuklar doluyken soru BI'ı yavaşlatmadan GPU 0 eşine gidebilir."""
from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest
import yaml

MODELS = Path(__file__).resolve().parents[1] / "deploy" / "models.yaml"


@pytest.fixture()
def G(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynvml", types.SimpleNamespace(nvmlInit=lambda: None))
    dmod = types.ModuleType("docker")
    dmod.from_env = lambda: None
    dtypes = types.ModuleType("docker.types")
    dtypes.DeviceRequest = dtypes.Ulimit = object
    dmod.types = dtypes
    monkeypatch.setitem(sys.modules, "docker", dmod)
    monkeypatch.setitem(sys.modules, "docker.types", dtypes)
    monkeypatch.setenv("EDITOR_MODELS_YAML", str(MODELS))
    monkeypatch.setenv("EDITOR_OVERFLOW_URL", "http://peer:8001")
    monkeypatch.setenv("EDITOR_OVERFLOW_MODEL", "nanobaseAI")
    monkeypatch.setenv("EDITOR_OVERFLOW_CLIENTS", "editor-cards")
    for k in ("EDITOR_OVERFLOW_ANALYSIS_CAP", "EDITOR_OVERFLOW_ANALYSIS_BI_MAX",
              "EDITOR_INTERACTIVE_PRIORITY", "EDITOR_ANALYSIS_PRIORITY"):
        monkeypatch.delenv(k, raising=False)
    sys.modules.pop("editor.gateway", None)
    g = importlib.import_module("editor.gateway")
    yield g
    sys.modules.pop("editor.gateway", None)


class _Box:
    def __init__(self, args, status="running"):
        self.status = status
        self.attrs = {"Args": args}


def _policy(G, monkeypatch, on: bool):
    args = ["/model", "--max-num-seqs=32"] + (["--scheduling-policy=priority"] if on else [])
    monkeypatch.setattr(G, "_container", lambda _a: _Box(args))
    G._priority_seen.clear()


def test_director_args_enable_priority_policy():
    spec = yaml.safe_load(MODELS.read_text())["aliases"]["book-director"]
    assert "--scheduling-policy=priority" in spec["args"]
    assert any(str(x).startswith("--max-num-seqs=") for x in spec["args"])


def test_defaults(G):
    assert G.INTERACTIVE_PRIORITY == 0 and G.ANALYSIS_PRIORITY == 10
    assert G.INTERACTIVE_PRIORITY < G.ANALYSIS_PRIORITY      # vLLM: küçük sayı önce


def test_interactive_gets_high_priority(G, monkeypatch):
    _policy(G, monkeypatch, True)
    p = {"model": "book-director", "messages": []}
    assert G._with_priority(G.ALIASES["book-director"], "chat/completions", p, interactive=True)
    assert p["priority"] == G.INTERACTIVE_PRIORITY


def test_analysis_gets_low_priority(G, monkeypatch):
    _policy(G, monkeypatch, True)
    p = {"model": "book-director", "messages": []}
    assert G._with_priority(G.ALIASES["book-director"], "chat/completions", p, interactive=False)
    assert p["priority"] == G.ANALYSIS_PRIORITY


def test_no_field_when_running_box_has_no_policy(G, monkeypatch):
    # models.yaml'da politika olsa da çalışan eski kap fcfs ise alan gönderilmez (vLLM 400 verirdi).
    _policy(G, monkeypatch, False)
    p = {"model": "book-director", "messages": []}
    assert not G._with_priority(G.ALIASES["book-director"], "chat/completions", p, interactive=False)
    assert "priority" not in p


def test_no_field_on_embeddings(G, monkeypatch):
    _policy(G, monkeypatch, True)
    p = {"model": "book-director", "input": ["x"]}
    assert not G._with_priority(G.ALIASES["book-director"], "embeddings", p, interactive=False)
    assert "priority" not in p


def test_policy_arg_forms(G):
    assert G._policy_priority(["--scheduling-policy", "priority"])
    assert G._policy_priority(["--scheduling-policy=priority"])
    assert not G._policy_priority(["--scheduling-policy=fcfs"])
    assert not G._policy_priority([])


def test_quick_answer_sends_interactive_header():
    src = (Path(__file__).resolve().parents[1] / "src" / "editor" / "quick_answer.py").read_text()
    assert 'llm._post("/v1/chat/completions", req, llm.INTERACTIVE)' in src


# ---------------------------------------------------------- etkileşimli taşma
def _spill(G, monkeypatch, *, serving, peer, spilled=0):
    a = G.ALIASES["book-director"]
    a.inflight = serving + 1                    # proxy bu isteği saymış olur
    G.YIELDING.clear()
    G.overflow_inflight = spilled
    monkeypatch.setattr(G, "_is_running", lambda _a: True)

    async def healthy(_a):
        return True

    async def load():
        return peer

    monkeypatch.setattr(G, "_healthy", healthy)
    monkeypatch.setattr(G, "peer_load", load)
    monkeypatch.setattr(G, "_client_name", lambda _r: "editor-cards")
    return asyncio.run(G._should_overflow(a, object()))


def test_interactive_stays_local_when_seats_free(G, monkeypatch):
    assert not _spill(G, monkeypatch, serving=20, peer=0)


def test_interactive_spills_when_seats_full_and_bi_idle(G, monkeypatch):
    assert _spill(G, monkeypatch, serving=60, peer=8, spilled=8)   # eşteki 8'in hepsi bizim taşanımız


def test_interactive_spill_ignores_analysis_cap(G, monkeypatch):
    # ölçüldü 2026-10-03: analiz taşması hep 8/8; soru bu sınırla hiç geçemezdi
    assert _spill(G, monkeypatch, serving=40, peer=9, spilled=G.ANALYSIS_CAP)


def test_bi_busy_keeps_interactive_local(G, monkeypatch):
    assert not _spill(G, monkeypatch, serving=60, peer=12, spilled=2)   # BI'ın kendi yükü 10 > 2


def test_peer_unreadable_keeps_interactive_local(G, monkeypatch):
    assert not _spill(G, monkeypatch, serving=60, peer=None)
