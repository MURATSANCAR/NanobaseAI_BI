"""Onay ekranı: kararın dayanağı ekranda görünür olmalı.

Kuyruk satırı terimin ne demek olduğunu söylüyordu, neden öyle bilindiğini söylemiyordu. «doğrulanmış
sorgu ×2» yazan bir rozete bakarak kimse sorumluca onay veremez: kanıtın kendisi — terimin geçtiği
soru, o soruyu cevaplayan SQL, kaynağın kendi cümlesi, kolonda ölçülen sayılar — insanın önünde
olmalı. Buradaki sözleşme odur; ayrıca onaylandığında sorgulara girecek SQL parçası, derleyicinin
üreteceği parçanın aynısı olmalı — ekran ile motorun ayrı şeyler söylemesi en sessiz hatadır.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from semantic_layer.candidates.llm_client import FakeLlm
from semantic_layer.models import (Candidate, Concept, ConceptStatus, Evidence, EvidenceType,
                                   Mapping, SemanticType)
from semantic_layer.tests.conftest import DS, TENANT

QUESTION = "2026 alınan hizmet faturası tutarı"
SQL = ('SELECT c."DEFINITION_" AS cari, SUM(i."NETTOTAL") AS tutar FROM dbo_LG_411_01_INVOICE i '
       'INNER JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF" '
       'WHERE i."CANCELLED" = 0 AND i."TRCODE" IN (4) GROUP BY c."DEFINITION_"')


def _client(store, profiles, connector, settings):
    from semantic_bridge.app import Runtime, create_app

    for p in profiles:
        store.upsert_profile(p)
    return TestClient(create_app(Runtime(settings, store=store, connector=connector, llm=FakeLlm([""]))))


@pytest.fixture
def pending(store, profiles):
    """Bir aday terim ve arkasındaki kanıt: çalışmış bir sorgu, kaynağın cümlesi, ölçülen sayılar."""
    inv = next(p for p in profiles if p.entity == "INVOICE")
    qid = store.log_query(TENANT, DS, QUESTION, sql=SQL, compiler="existing_llm", catalog_version=1,
                          resolved={}, executed=True, row_count=1)
    store.mark_validated(qid, True)
    c, _ = store.upsert_concept(TENANT, DS, "hizmet", SemanticType.DIMENSION_VALUE,
                                mapping=Mapping("", "INVOICE", inv.table_pattern, column="TRCODE",
                                                operator="IN", values=["4"]),
                                status=ConceptStatus.CANDIDATE)
    store.add_evidence(Evidence(c.id, EvidenceType.VALIDATED_SQL, "history_miner", support_count=2,
                                weight=1.0, payload={"precision": 0.8, "pairs": [qid, "pair_yok"]}))
    store.add_evidence(Evidence(c.id, EvidenceType.DOC, "logo/kolonlar.md", support_count=1, weight=0.6,
                                payload={"snippet": "TRCODE 4 = Alınan hizmet faturası"}))
    # gece koşusu her gece aynı adayı yeniden önerir; kuyruk bunu bir kez söylemeli
    for _ in range(3):
        store.add_candidate(Candidate(c.id, "history_miner", payload={"support": 2, "precision": 0.8}))
    return c


def test_the_screen_shows_the_query_the_term_was_learned_from(pending, store, profiles, logo_connector, settings):
    """Onaylayan kişi kelimeyi değil, kelimenin geçtiği işi görür: sorulan soru ve onu cevaplayan SQL."""
    client = _client(store, profiles, logo_connector, settings)

    p = client.get(f"/api/v1/semantic/concepts/{pending.id}/provenance").json()

    ev = {x["kind"]: x for x in p["evidence"]}
    ex = ev["VALIDATED_SQL"]["examples"][0]
    assert ex["question"] == QUESTION, "terim hangi sorudan çıktıysa o soru gösterilmeli"
    assert ex["hits"], "SQL'in hangi satırının iddiayı taşıdığı işaretlenmeli"
    assert all("TRCODE" in ex["lines"][i] for i in ex["hits"])
    assert len(ex["lines"]) > 1, "tek satırlık SQL okunacak şekilde bölünmeli"
    # bir birleştirme sıfatıyla birlikte durur: tek başına "INNER" yazan bir satır sorguyu bozuk gösterir
    assert any(x.upper().startswith("INNER JOIN") for x in ex["lines"])
    assert not any(x.strip().upper() == "INNER" for x in ex["lines"])


def test_a_pair_that_is_gone_is_reported_not_dropped(pending, store, profiles, logo_connector, settings):
    """Kanıtın bir parçası artık bulunamıyorsa, ekran daha az kanıt varmış gibi davranmamalı."""
    client = _client(store, profiles, logo_connector, settings)

    ev = {x["kind"]: x for x in client.get(f"/api/v1/semantic/concepts/{pending.id}/provenance").json()["evidence"]}

    assert ev["VALIDATED_SQL"]["seenIn"] == 2 and ev["VALIDATED_SQL"]["missing"] == 1


def test_the_fragment_shown_is_the_fragment_the_compiler_emits(pending, store, profiles, logo_connector, settings):
    """Ekranda görünen SQL parçası ile motorun üreteceği parça aynı olmalı."""
    from semantic_layer.runtime.compiler import Dialect, _pred_sql

    client = _client(store, profiles, logo_connector, settings)

    t = client.get(f"/api/v1/semantic/concepts/{pending.id}/provenance").json()["target"]

    m = store.list_mappings(pending.id)[0]
    assert t["sql"] == _pred_sql("INVOICE", m, Dialect(settings.dialect))
    assert t["table"] and t["column"] == "TRCODE"


def test_the_source_sentence_and_the_producer_come_with_it(pending, store, profiles, logo_connector, settings):
    """«Nereden çıkardık» sorusunun iki yarısı: kaynağın cümlesi ve bunu üreten adım."""
    client = _client(store, profiles, logo_connector, settings)

    p = client.get(f"/api/v1/semantic/concepts/{pending.id}/provenance").json()

    doc = {x["kind"]: x for x in p["evidence"]}["DOC"]
    assert doc["detail"]["snippet"] == "TRCODE 4 = Alınan hizmet faturası" and doc["source"] == "logo/kolonlar.md"
    assert [x["by"] for x in p["producedBy"]] == ["history_miner"], "aynı adım her gece tekrar yazılır, bir kez söylenir"
    assert p["producedBy"][0]["how"]
    assert p["plain"].startswith("«hizmet»"), "kuyruktaki cümlenin aynısı burada da olmalı"


def test_strongest_evidence_is_first(pending, store, profiles, logo_connector, settings):
    """Sıralama okuma sırasıdır: çalışmış bir sorgu, hakkında yazılmış bir cümleden önce gelir."""
    client = _client(store, profiles, logo_connector, settings)

    kinds = [x["kind"] for x in client.get(f"/api/v1/semantic/concepts/{pending.id}/provenance").json()["evidence"]]

    assert kinds.index("VALIDATED_SQL") < kinds.index("DOC")
