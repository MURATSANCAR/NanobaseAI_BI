"""Öneri 20 — başarısız soru kümeleri ve sınıf önerisi (`semantic_bridge.model_quality_clusters`): aynı metin birleşir,
anlamca yakın sorular aynı kümeye girer, tek soruluk küme gösterilmez, sınıf önerisi kapalı küme seçimdir (eşik altı
«emin değil»), onay insanda ve onaylanan sınıf sınıf panosunda kuralın önüne geçer; sorular modele maskeli gider.

Gömme ve model sahte; gerçek kabul test sunucusunda.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from semantic_bridge import model_quality as MQ
from semantic_bridge import model_quality_clusters as MC
from semantic_bridge import model_quality_sources as src
from semantic_layer.runtime.llm_choose import Choice
from semantic_layer.store import schema as S
from semantic_layer.store.catalog_store import open_store

TN, DS = "t1", "logo"
CONF = {"MODEL_QUALITY_CLUSTER_MIN_SIM": "0.8"}


def conf(key, default=""):
    return CONF.get(key, default)


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    MQ._ready.discard(id(e))
    MQ.ensure(e)
    MC._ready.discard(id(e))
    MC.ensure(e)
    src._reflected.clear()
    src.clear_cache()
    return e


def _log(engine, qid, question, answer_type="INCOMPLETE_ANSWER"):
    with engine.begin() as c:
        c.execute(S.sl_query_log.insert().values(
            id=qid, tenant_id=TN, datasource_id=DS, question=question, normalized_question=question.lower(),
            sql_text=None, compiler="deterministic", catalog_version=7, resolved_json={}, executed=False, row_count=None,
            error=None, username="ayse", answer_type=answer_type, answer_summary="", gate_json=None, latency_ms=900,
            created_at=datetime.now(timezone.utc)))


def embed(texts):
    """Konu sözcüğüne göre vektör: «iade» ve «stok» soruları iki ayrı yöne düşer."""
    out = []
    for t in texts:
        f = MQ.fold(t)
        out.append([1.0 if "iade" in f else 0.0, 1.0 if "stok" in f else 0.0, 0.05])
    return out


def test_leader_clustering_is_deterministic():
    texts = ["a", "b", "c", "d"]
    vecs = [[1, 0], [0.99, 0.05], [0, 1], [0.02, 1]]
    groups = MC.leader_clusters(texts, [1, 3, 1, 1], vecs, 0.9)
    assert groups == [[1, 0], [2, 3]]                      # en sık metin öncü; büyük küme önce


def test_build_suggest_decide_and_board(engine):
    _log(engine, "q1", "Geçen ay iade oranı nedir?")
    _log(engine, "q2", "geçen ay iade oranı nedir?")      # aynı metin (katlanınca)
    _log(engine, "q3", "Bayilerin iade tutarı kaç?")
    _log(engine, "q4", "Depoda stok kaç adet? Ali 0532 111 22 33")
    _log(engine, "q5", "Stok devir hızı nedir?")
    _log(engine, "q6", "Hava nasıl?")
    prompts = []

    def choose(prompt, labels):
        prompts.append(prompt)
        pick = "Katalogda olmayan terim" if "iade" in prompt else labels[0]
        probs = {l: (0.9 if l == pick else 0.1 / (len(labels) - 1)) for l in labels}
        return Choice(pick, labels.index(pick), probs, "logprobs", margin=0.85 if "iade" in prompt else 0.1, coverage=1.0)

    out = MC.build(engine, TN, DS, days=30, embed=embed, choose=choose, conf=conf)
    assert out["clusters"] == 2 and out["questions"] == 5 and out["singletons"] == 1 and out["asked"] == 2
    assert all("0532" not in p for p in prompts) and any("Hiçbiri" in p for p in prompts)
    lst = MC.listing(engine, TN)
    iade = next(c for c in lst["items"] if any("iade" in s for s in c["samples"]))
    stok = next(c for c in lst["items"] if c is not iade)
    assert iade["size"] == 3 and iade["distinctTexts"] == 2 and iade["confident"] and iade["suggested"] == "tanimsiz_terim"
    assert stok["confident"] is False                     # marj eşik altı → emin değil
    assert all("0532" not in s for s in stok["samples"])

    with pytest.raises(MQ.QualityError, match="var olan"):
        MC.decide(engine, TN, stok["id"], "mehmet", "onayla", "yok_boyle")
    res = MC.decide(engine, TN, iade["id"], "mehmet", "onayla")
    assert res == {"id": iade["id"], "status": "onaylandi", "klass": "tanimsiz_terim", "written": 3}
    with pytest.raises(MQ.QualityError, match="zaten"):
        MC.decide(engine, TN, iade["id"], "mehmet", "reddet")
    items = {i["queryId"]: i for i in src.classified_items(engine, TN, DS, datetime(2000, 1, 1, tzinfo=timezone.utc))}
    assert items["q1"]["klass"] == "tanimsiz_terim" and items["q1"]["klassSource"] == "kume"
    assert items["q5"]["klassSource"] == "kural"

    # Yeniden kurma: onaylanan küme kayıtta kalır, onaylı sorular yeniden kümelenmez.
    out = MC.build(engine, TN, DS, days=30, embed=embed, choose=None, conf=conf)
    assert out["clusters"] == 1 and out["asked"] == 0
    assert len(MC.listing(engine, TN, status="onaylandi")["items"]) == 1
    fresh = MC.listing(engine, TN)["items"][0]
    assert fresh["method"] == "yok" and fresh["suggested"] is None
    assert MC.decide(engine, TN, fresh["id"], "mehmet", "reddet")["status"] == "reddedildi"


def test_no_failures_is_explicit(engine):
    out = MC.build(engine, TN, DS, days=30, embed=embed, choose=None, conf=conf)
    assert out["clusters"] == 0 and "yok" in out["note"]
