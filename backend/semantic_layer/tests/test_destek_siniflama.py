"""Destek masası sınıflaması (README «hemen düzeltilecekler» 7): masa artık olasılıksız serbest JSON ile sınıflamaz.

- `yz/secim.py` köprüdeki `llm_choose` ile aynı yöntemi uygular (aynı cevaptan aynı olasılıklar).
- Konu köprüde M51 ile **tek karar** (`/api/v1/support/panel/classify`, `support.panel_classification`): masa türü o
  kararın sınıf adıdır; eşik altı ya da köprüye ulaşılamazsa tür boş kalır, masada ayrıca konu tahmini yapılmaz.
- Öncelik/ekip/duygu eşik altıysa doldurulmaz; «ekibe ait değil» seçimi alan doldurmaz.

Masa kodu frappe'ye bağlıdır; burada frappe küçük bir sahte modülle yerine konur (yalnız saf mantık sınanır).
"""

from __future__ import annotations

import math
import sys
import types
from pathlib import Path

import pytest

from semantic_bridge import support as S
from semantic_layer.runtime import llm_choose as LC

ROOT = Path(__file__).resolve().parents[3]
DESK = ROOT / "apps" / "destek" / "frappe-apps" / "nanobase_brand"


class _Conf(dict):
    pass


@pytest.fixture
def desk(monkeypatch):
    if not (DESK / "nanobase_brand" / "yz" / "secim.py").exists():
        pytest.skip("apps/destek bu kopyada yok (depo kökünden koşturun)")
    fr = types.ModuleType("frappe")
    fr.conf = _Conf()
    fr.errors = []
    fr.created = []
    fr.log_error = lambda *a, **k: fr.errors.append(k.get("title"))

    class _Doc:
        def __init__(self, d):
            self.__dict__.update(d)
            self.flags = types.SimpleNamespace()

        def insert(self):
            fr.created.append(self.name)

    fr.get_doc = lambda d: _Doc(d)
    fr.db = types.SimpleNamespace(commit=lambda: None)
    monkeypatch.setitem(sys.modules, "frappe", fr)
    try:
        import requests  # noqa: F401
    except ImportError:
        rq = types.ModuleType("requests")
        rq.RequestException = Exception
        monkeypatch.setitem(sys.modules, "requests", rq)
    monkeypatch.syspath_prepend(str(DESK))
    for m in [m for m in sys.modules if m.startswith("nanobase_brand")]:
        monkeypatch.delitem(sys.modules, m)
    from nanobase_brand.yz import llm, secim, sinif

    return types.SimpleNamespace(frappe=fr, llm=llm, secim=secim, sinif=sinif)


def _reply(dist: dict[str, float], said: str) -> dict:
    top = [{"token": t, "logprob": math.log(p)} for t, p in dist.items()]
    return {"message": {"content": said}, "logprobs": {"content": [{"token": said, "logprob": math.log(dist[said]),
                                                                    "top_logprobs": top}]}}


# ------------------------------------------------------------------ secim.py = llm_choose


def test_desk_choose_reads_same_probabilities_as_bridge(desk):
    reply = _reply({"A": 0.6, "B": 0.3, " C": 0.05, "x": 0.05}, "A")
    choices = ["Yüksek", "Normal", "Düşük"]
    bridge, _ = LC.read_logprobs(reply, list("ABC"))
    r = desk.secim.sec(lambda msgs, extra: reply, "Öncelik?", choices)
    assert r["choice"] == "Yüksek" and r["method"] == "logprobs"
    for label, c in zip("ABC", choices):
        assert r["probs"][c] == pytest.approx(bridge[label])
    assert r["margin"] == pytest.approx(bridge["A"] - bridge["B"])
    assert desk.secim.emin(r, 0.6, 0.3) and not desk.secim.emin(r, 0.7, 0.3)


def test_desk_choose_request_is_one_token_closed_set(desk):
    seen = []

    def call(msgs, extra):
        seen.append((msgs, extra))
        return _reply({"B": 0.9, "A": 0.1}, "B")

    desk.secim.sec(call, "Soru", ["Olumlu", "Olumsuz"])
    msgs, extra = seen[0]
    assert extra == {"logprobs": True, "top_logprobs": 20, "structured_outputs": {"choice": ["A", "B"]}}
    assert "A) Olumlu" in msgs[-1]["content"] and "yalnız seçeneğin harfini" in msgs[-1]["content"]


def test_fallback_without_probabilities_is_never_confident(desk):
    calls = []

    def call(msgs, extra):
        calls.append(extra)
        if extra:
            raise ValueError("400")
        return {"message": {"content": "B"}}

    r = desk.secim.sec(call, "Soru", ["Olumlu", "Olumsuz"])
    assert calls == [calls[0], None] and r["choice"] == "Olumsuz" and r["probability"] is None
    assert r["method"] == "text" and not desk.secim.emin(r, 0.0, 0.0)
    assert desk.secim.sec(lambda m, e: {"message": {"content": "belki"}}, "S", ["x", "y"])["choice"] is None


def test_more_than_26_choices_play_rounds_and_sum_to_one(desk):
    choices = [f"Ekip {i}" for i in range(30)]

    def call(msgs, extra):
        n = len(extra["structured_outputs"]["choice"])
        dist = {label: (0.7 if label == "A" else 0.3 / (n - 1)) for label in extra["structured_outputs"]["choice"]}
        return _reply(dist, "A")

    r = desk.secim.sec(call, "Hangi ekip?", choices)
    assert r["choice"] == "Ekip 0" and sum(r["probs"].values()) == pytest.approx(1.0)
    assert [len(g) for g in desk.secim.gruplar(choices)] == [15, 15]


# ------------------------------------------------------------------ tek konu kararı (köprü)


def test_panel_classification_returns_single_decision_without_personal_data():
    classes = [{"klass": "kargo-gecikmesi", "label": "Kargo gecikmesi", "description": "Kargo nerede", "active": True},
               {"klass": "diger", "label": "Diğer", "description": "", "active": True},
               {"klass": "eski", "label": "Eski", "description": "", "active": False}]
    ins = {"ticket": "HD-1", "klass": "kargo-gecikmesi", "klassP": 0.91, "klassMargin": 0.8, "klassMethod": "logprobs",
           "klassBy": "zeki", "klassGuess": "kargo-gecikmesi", "urgency": "normal", "urgencyP": 0.7,
           "raisedByHash": "abc", "draft": "x"}
    out = S.panel_classification(ins, classes)
    assert out["confident"] and out["label"] == "Kargo gecikmesi" and out["p"] == 0.91
    assert "raisedByHash" not in out and "draft" not in out
    assert [c["klass"] for c in out["classes"]] == ["kargo-gecikmesi", "diger"]
    unsure = S.panel_classification(dict(ins, klass=None), classes)
    assert not unsure["confident"] and unsure["label"] is None and unsure["guessLabel"] == "Kargo gecikmesi"


# ------------------------------------------------------------------ masa: sinif.oner


def _doc():
    return types.SimpleNamespace(name="HD-1", subject="Kargom gelmedi", description="<p>3 gündür bekliyorum</p>",
                                 raised_by="a@b.com", opening_date="2026-09-28", modified="2026-09-28 10:00:00")


def test_topic_comes_from_bridge_and_type_is_created_once(desk, monkeypatch):
    monkeypatch.setattr(desk.sinif, "konu", lambda doc: {"confident": True, "label": "Kargo gecikmesi", "p": 0.9,
                                                         "description": "Kargo nerede", "by": "zeki"})
    asked = []

    def choose(prompt, choices, **kw):
        asked.append(choices)
        best = choices[0]
        return {"choice": best, "probability": 0.95, "margin": 0.9, "probs": None, "method": "logprobs"}

    monkeypatch.setattr(desk.llm, "choose", choose)
    types_ = ["Unspecified"]
    out = desk.sinif.oner(_doc(), "metin", types_, ["High", "Low"], ["Billing"], ("Olumlu", "Nötr"))
    assert out["ticket_type"] == "Kargo gecikmesi" and types_ == ["Unspecified", "Kargo gecikmesi"]
    assert desk.frappe.created == ["Kargo gecikmesi"]
    assert out["priority"] == "High" and out["agent_group"] == "Billing" and out["duygu"] == "Olumlu"
    assert all("Kargo gecikmesi" not in c for c in asked)          # masa konuyu ayrıca sormaz
    assert "%90" in out["gerekce"]
    # aynı ad (harf farkıyla) varsa yeni tür açılmaz
    desk.frappe.created.clear()
    out = desk.sinif.oner(_doc(), "metin", ["KARGO GECİKMESİ"], [], [], ("Olumlu",))
    assert out["ticket_type"] == "KARGO GECİKMESİ" and desk.frappe.created == []


def test_unsure_fields_stay_empty_and_no_desk_topic_guess(desk, monkeypatch):
    monkeypatch.setattr(desk.sinif, "konu", lambda doc: {"confident": False, "label": None, "guessLabel": "Fatura"})
    answers = {"High": 0.5, "Billing": 0.95}

    def choose(prompt, choices, **kw):
        c = choices[0]
        if c == "Olumlu":
            return {"choice": desk.sinif.EKIPSIZ, "probability": 0.99, "margin": 0.9}
        return {"choice": c, "probability": answers.get(c, 0.9), "margin": 0.1 if c == "High" else 0.9}

    monkeypatch.setattr(desk.llm, "choose", choose)
    out = desk.sinif.oner(_doc(), "metin", ["Fatura"], ["High", "Low"], ["Billing"], ("Olumlu", "Nötr"))
    assert "ticket_type" not in out and "priority" not in out and "duygu" not in out
    assert out["agent_group"] == "Billing" and "konu: emin değil (en olası Fatura)" in out["gerekce"]


def test_nothing_reachable_raises_model_unavailable(desk, monkeypatch):
    monkeypatch.setattr(desk.sinif, "konu", lambda doc: None)

    def choose(*a, **k):
        raise desk.llm.ModelUnavailable("yok")

    monkeypatch.setattr(desk.llm, "choose", choose)
    with pytest.raises(desk.llm.ModelUnavailable):
        desk.sinif.oner(_doc(), "metin", [], ["High"], [], ("Olumlu",))


def test_bridge_address_follows_model_address(desk):
    f = desk.sinif.baglam_adresi
    assert f("https://portal.nanobase.ai/destek-llm/v1", None) == "https://portal.nanobase.ai/destek-baglam/v1"
    assert f("https://portal.nanobase.ai/destek-llm/v1/", None) == "https://portal.nanobase.ai/destek-baglam/v1"
    assert f("http://model:8000/v1", None) is None
    assert f("http://x/v1", "https://kopru/destek-baglam/v1/") == "https://kopru/destek-baglam/v1"
