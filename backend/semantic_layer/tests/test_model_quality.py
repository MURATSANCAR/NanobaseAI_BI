"""M50 Zeki AI kalitesi: hata sınıfı kuralları, sürüm kaydı (tek satır, tekrar yazmama, kurulum her zaman), kapı raporu
(önce/sonra: bozulan/düzelen, istek → sıra → rapor, ölçüm penceresine giren kurulum), vaka listesi, geri bildirim
(validated eşlemesi, başkasının cevabı, güncelleme), sınıflama kuyruğu, karne satırları, çeviri ve SEO okumaları, yetki.

Veriler yapaydır ve yalnız kuralları sınar; gerçek kabul test sunucusunda (scripts/acceptance/M50).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import model_quality as MQ
from semantic_bridge import model_quality_sources as src
from semantic_layer.store import schema as S
from semantic_layer.store.catalog_store import open_store

TN = "t1"
DS = "logo"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    MQ._ready.discard(id(e))
    MQ.ensure(e)
    src._reflected.clear()
    src.clear_cache()
    return e


def _log(engine, qid, *, answer_type="TEXT_TO_SQL", executed=True, row_count=3, error=None, username="ayse",
         resolved=None, gate=None, question="2026 net ciro", created=None, latency=1200):
    with engine.begin() as c:
        c.execute(S.sl_query_log.insert().values(
            id=qid, tenant_id=TN, datasource_id=DS, question=question, normalized_question=question.lower(),
            sql_text="SELECT 1", compiler="deterministic", catalog_version=7, resolved_json=resolved or {},
            executed=executed, row_count=row_count, error=error, username=username, answer_type=answer_type,
            answer_summary="özet", gate_json=gate, latency_ms=latency,
            created_at=created or datetime.now(timezone.utc)))


# ------------------------------------------------------------------ sınıf kuralları


def test_classes_seeded_once_and_not_overwritten(engine):
    assert {k["klass"] for k in MQ.load_classes(engine)} >= {"yetki_disi", "tanimsiz_terim", "kaynak_kacirma",
                                                             "olcu_yerine_kolon", "donem_sekil", "veri_yok", "model_reddi"}
    MQ.update_class(engine, "veri_yok", {"label": "Veri tutulmuyor"}, "ekip")
    assert MQ.seed_classes(engine) == 0
    assert next(k for k in MQ.load_classes(engine) if k["klass"] == "veri_yok")["label"] == "Veri tutulmuyor"


@pytest.mark.parametrize("row,want", [
    ({"answer_type": "NOT_PERMITTED"}, "yetki_disi"),
    ({"answer_type": "DATA_SOURCE_UNAVAILABLE"}, "baglanti"),
    ({"answer_type": "CLARIFICATION"}, "netlestirme"),
    ({"answer_type": "INCOMPLETE_ANSWER", "resolved_json": {"unresolved": ["iade oranı"]}}, "tanimsiz_terim"),
    ({"answer_type": "TEXT_TO_SQL", "resolved_json": {"explanation": ["'adet' sayım sözcüğü olarak okundu"]}}, "olcu_yerine_kolon"),
    ({"answer_type": "TEXT_TO_SQL", "resolved_json": {"explanation": ["dönem belirtilmedi → varsayılan bu yıl"]}}, "donem_sekil"),
    ({"answer_type": "INCOMPLETE_ANSWER", "gate_json": {"unmetObligations": ["geçen yılla karşılaştırma yok"]}}, "donem_sekil"),
    ({"answer_type": "DATA_UNAVAILABLE"}, "veri_yok"),
    ({"answer_type": "TEXT_TO_SQL", "executed": True, "row_count": 0}, "veri_yok"),
    ({"answer_type": "NON_SQL_QUERY"}, "model_reddi"),
    ({"answer_type": "SQL_INVALID", "gate_json": {"guardrail": "DELETE"}}, "model_reddi"),
    ({"answer_type": "TEXT_TO_SQL", "executed": True, "row_count": 4}, MQ.UNCLASSIFIED),
])
def test_rule_classification_of_query_log(engine, row, want):
    base = {"answer_type": "", "executed": False, "row_count": None, "error": None, "answer_summary": "",
            "resolved_json": {}, "gate_json": None}
    assert MQ.classify(MQ.evidence_from_log({**base, **row}), MQ.load_classes(engine)) == want


def test_case_classification_from_gate_lines(engine):
    classes = MQ.load_classes(engine)
    assert MQ.classify(MQ.evidence_from_case({"status": "bozuk", "detail": ['sources: ["ANA"] → ["CRM"]']}), classes) == "kaynak_kacirma"
    assert MQ.classify(MQ.evidence_from_case({"status": "bozuk", "detail": ["satır sayısı 3, referans 12"]}), classes) == "donem_sekil"
    assert MQ.classify(MQ.evidence_from_case({"status": "bozuk", "detail": ["beklenen answer, gelen deny: …"]}), classes) == "model_reddi"
    assert MQ.classify(MQ.evidence_from_case({"status": "veri", "detail": ["referans boş döndü"]}), classes) == "veri_yok"
    assert MQ.classify(MQ.evidence_from_case({"status": "bozuk", "answerType": "HTTP_ERROR", "detail": []}), classes) == "baglanti"


def test_rule_validation():
    MQ.validate_rule({"any": [{"answerTypes": ["X"]}, {"unresolved": True}]})
    for bad in ({}, {"any": []}, {"any": [{}]}, {"any": [{"bilinmeyen": ["x"]}]}, {"any": [{"textAny": []}]},
                {"any": [{"unresolved": "evet"}]}):
        with pytest.raises(MQ.QualityError):
            MQ.validate_rule(bad)


def test_inactive_rule_is_skipped(engine):
    MQ.update_class(engine, "model_reddi", {"active": False}, "ekip")
    ev = MQ.evidence_from_log({"answer_type": "NON_SQL_QUERY"})
    assert MQ.classify(ev, MQ.load_classes(engine)) == MQ.UNCLASSIFIED


# ------------------------------------------------------------------ sürüm kaydı


SNAP = {"code_sha": "a" * 40, "catalog_version": 7, "catalog_certified": 120, "knowledge_digest": "k1",
        "rules_digest": None, "language_digest": "l1", "prompt_digest": None, "model_ref": "nanobaseAI@gpu:18885/v1",
        "model_digest": "m1"}


def test_version_record_dedupes_and_marks_changed_parts(engine):
    v1 = MQ.record_version(engine, TN, SNAP, source="kosu", by="zamanlayici")
    v1b = MQ.record_version(engine, TN, SNAP, source="kosu", by="zamanlayici")
    assert v1b["id"] == v1["id"] and v1["kinds"] == ["ilk"]
    v2 = MQ.record_version(engine, TN, {**SNAP, "catalog_version": 8, "model_digest": "m2"}, source="kosu", by="z")
    assert v2["id"] != v1["id"] and set(v2["kinds"]) == {"catalog", "model"}
    v3 = MQ.record_version(engine, TN, {**SNAP, "catalog_version": 8, "model_digest": "m2"}, source="kurulum", by="k")
    assert v3["id"] != v2["id"], "kurulum aynı durumda da yazılır"
    # Ekrana model adı gitmez.
    assert "nanobase" not in json.dumps(v3).lower() and v3["model"].startswith("Zeki AI modeli")
    assert MQ.list_versions(engine, TN)["total"] == 3


# ------------------------------------------------------------------ koşu raporu ve önce/sonra


def _report(cases, **kw):
    return {"suite": "answer", "label": "answers-set100.json", "cases": cases,
            "startedAt": kw.get("started", (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()),
            "finishedAt": kw.get("finished", datetime.now(timezone.utc).isoformat()), **{k: v for k, v in kw.items()
                                                                                          if k not in ("started", "finished")}}


def test_first_run_uses_file_baseline_second_run_compares(engine):
    r1 = MQ.ingest_report(engine, TN, _report([
        {"id": "Q1", "n": 1, "question": "a", "status": "saglam"},
        {"id": "Q2", "n": 2, "question": "b", "status": "bozuk", "detail": ["satır sayısı 1, referans 2"]},
        {"id": "Q3", "n": 3, "question": "c", "status": "saglam"},
    ]), version=None, model_ref=None, env="test", by="t")
    assert (r1["broken"], r1["fixed"], r1["baselineRunId"]) == (1, 0, None)
    r2 = MQ.ingest_report(engine, TN, _report([
        {"id": "Q1", "n": 1, "question": "a", "status": "bozuk", "detail": ["beklenen answer, gelen deny: x"]},
        {"id": "Q2", "n": 2, "question": "b", "status": "saglam"},
        {"id": "Q3", "n": 3, "question": "c", "status": "veri"},
        {"id": "Q4", "n": 4, "question": "d", "status": "bozuk"},
    ]), version=None, model_ref=None, env="test", by="t")
    assert r2["baselineRunId"] == r1["id"]
    assert r2["brokenIds"] == ["Q1"] and r2["fixedIds"] == ["Q2"], "veri bozulma sayılmaz; yeni vaka karşılaştırılmaz"
    cases = MQ.run_cases(engine, TN, r2["id"], change="bozulan")
    assert cases["total"] == 1 and cases["items"][0]["before"]["status"] == "saglam"
    assert cases["items"][0]["klass"] == "model_reddi"
    # Farklı etiket (kısmi koşu) tam koşunun önce/sonrası sayılmaz.
    r3 = MQ.ingest_report(engine, TN, {**_report([{"id": "Q1", "status": "saglam"}]), "label": "answers-set100.json only=Q1"},
                          version=None, model_ref=None, env="test", by="t")
    assert r3["baselineRunId"] is None


def test_request_claim_report_and_duplicate_request(engine):
    req = MQ.request_run(engine, TN, "resolver", "ekip")
    with pytest.raises(MQ.QualityError) as e:
        MQ.request_run(engine, TN, "resolver", "ekip")
    assert e.value.status == 409
    with pytest.raises(MQ.QualityError):
        MQ.request_run(engine, TN, "golden", "ekip")
    jobs = MQ.claim_due(engine, TN)
    assert [j["id"] for j in jobs] == [req["id"]] and MQ.claim_due(engine, TN) == []
    out = MQ.ingest_report(engine, TN, {"suite": "resolver", "label": "set100.jsonl", "requestId": req["id"],
                                        "cases": [{"id": "Q1", "status": "saglam"}]},
                           version=None, model_ref=None, env=None, by="t")
    assert out["id"] == req["id"] and out["status"] == "bitti" and out["requestedBy"] == "ekip"
    with pytest.raises(MQ.QualityError):
        MQ.ingest_report(engine, TN, {"suite": "resolver", "requestId": req["id"], "cases": []},
                         version=None, model_ref=None, env=None, by="t")


def test_install_inside_window_marks_run_polluted(engine):
    start = datetime.now(timezone.utc) - timedelta(minutes=20)
    MQ.record_version(engine, TN, SNAP, source="kurulum", by="k", at=start + timedelta(minutes=5))
    out = MQ.ingest_report(engine, TN, _report([{"id": "Q1", "status": "saglam"}], started=start.isoformat(),
                                               state={"start": {"catalogVersion": 7}, "end": {"catalogVersion": 8}}),
                           version=None, model_ref=None, env="test", by="t",
                           releases_between=lambda a, b: [{"kind": "kurulum", "label": "M48"}])
    kinds = [i.get("kind") or i.get("source") for i in out["installsInWindow"]]
    assert out["polluted"] and "kurulum" in kinds and "durum" in kinds and len(out["installsInWindow"]) == 3


def test_report_validation(engine):
    for body in ({"suite": "x", "cases": []}, {"suite": "answer"}, {"suite": "answer", "cases": [{"id": "Q1", "status": "iyi"}]},
                 {"suite": "answer", "cases": [{"id": "Q1", "status": "saglam"}, {"id": "Q1", "status": "saglam"}]}):
        with pytest.raises(MQ.QualityError):
            MQ.ingest_report(engine, TN, body, version=None, model_ref=None, env=None, by="t")


def test_stale_running_run_expires(engine):
    req = MQ.request_run(engine, TN, "answer", "ekip")
    MQ.claim_due(engine, TN)
    with engine.begin() as c:
        c.execute(MQ.RUNS.update().values(started_at=datetime.now(timezone.utc) - timedelta(hours=9)))
    assert MQ.expire_stale(engine, TN, 6) == 1
    assert MQ.get_run(engine, TN, req["id"])["status"] == "hata"


# ------------------------------------------------------------------ geri bildirim


def test_feedback_sets_validated_and_updates(engine):
    _log(engine, "q1")
    row = src.query_row(engine, TN, DS, "q1")
    out = MQ.record_feedback(engine, TN, row, "ayse", "yanlis", " iade düşülmemiş ")
    assert out["validated"] is False and out["comment"] == "iade düşülmemiş" and "İncelemeye alındı" in out["message"]
    MQ.record_feedback(engine, TN, row, "ayse", "kismen", None)
    with engine.connect() as c:
        assert c.execute(sa.select(S.sl_query_log.c.validated).where(S.sl_query_log.c.id == "q1")).scalar() is None
        assert c.execute(sa.select(sa.func.count()).select_from(MQ.FEEDBACK)).scalar() == 1
    MQ.record_feedback(engine, TN, row, "AYSE", "dogru", None)
    with engine.connect() as c:
        assert c.execute(sa.select(S.sl_query_log.c.validated).where(S.sl_query_log.c.id == "q1")).scalar() in (True, 1)
    assert MQ.my_feedback(engine, TN, "q1", "ayse")["verdict"] == "dogru"


def test_feedback_on_someone_elses_answer(engine):
    _log(engine, "q2", username="mehmet")
    row = src.query_row(engine, TN, DS, "q2")
    with pytest.raises(MQ.QualityError) as e:
        MQ.record_feedback(engine, TN, row, "ayse", "yanlis", None)
    assert e.value.status == 403
    assert MQ.record_feedback(engine, TN, row, "ayse", "yanlis", None, is_admin=True)["ok"]
    with pytest.raises(MQ.QualityError):
        MQ.record_feedback(engine, TN, row, "mehmet", "belki", None)


def test_queue_triage_and_auto_class(engine):
    _log(engine, "q3", answer_type="INCOMPLETE_ANSWER", resolved={"unresolved": ["iade oranı"]})
    fb = MQ.record_feedback(engine, TN, src.query_row(engine, TN, DS, "q3"), "ayse", "yanlis", "yok")
    q = src.feedback_queue(engine, TN, DS, state="yeni")
    assert q["total"] == 1 and q["items"][0]["effectiveKlass"] == "tanimsiz_terim" and q["items"][0]["klassSource"] == "kural"
    assert "result" not in q["items"][0]["query"], "sonuç satırları kuyrukta gösterilmez"
    out = MQ.triage_feedback(engine, TN, fb["id"], {"klass": "kaynak_kacirma"}, "ekip")
    assert out["triageState"] == "siniflandi" and out["klassSource"] == "insan"
    with pytest.raises(MQ.QualityError):
        MQ.triage_feedback(engine, TN, fb["id"], {"klass": "uydurma"}, "ekip")
    items = src.classified_items(engine, TN, DS, datetime.now(timezone.utc) - timedelta(days=30))
    assert [i["klass"] for i in items] == ["kaynak_kacirma"] and items[0]["source"] == "geri-bildirim"


# ------------------------------------------------------------------ karne


def test_bi_row_counts(engine):
    now = datetime.now(timezone.utc)
    _log(engine, "a1")
    _log(engine, "a2", answer_type="NON_SQL_QUERY", executed=False, row_count=None)
    _log(engine, "a3", answer_type="CLARIFICATION", executed=False, row_count=None)
    _log(engine, "a4", answer_type="MODULE_INTRO", executed=False, row_count=None)
    _log(engine, "old", created=now - timedelta(days=60))
    MQ.record_feedback(engine, TN, src.query_row(engine, TN, DS, "a1"), "ayse", "yanlis", None)
    since = now - timedelta(days=30)
    row = MQ.bi_row(src.query_rows(engine, TN, DS, since - timedelta(days=0)), src.feedback_rows(engine, TN, since),
                    {"answer": None, "resolver": None}, now=now, since=since)
    m = {x["key"]: x["value"] for x in row["metrics"]}
    assert m["questions"] == 3 and m["answeredRate"] == round(1 / 3, 4) and m["denyRate"] == round(1 / 3, 4)
    assert m["wrong"] == 1 and m["feedbackRate"] == 1.0 and row["measured"]
    assert len(row["trend"]) == 4 and row["trend"][-1]["questions"] == 3


def test_empty_rows_say_unmeasured():
    assert MQ.seo_row({"approved": 0, "rejected": 0})["note"] == "ölçülmedi"
    assert MQ.seo_row(None)["measured"] is False
    assert MQ.translation_row({"segments": 0})["measured"] is False
    assert MQ.redaction_row(None)["measured"] is False


def test_translation_stats_mqm_formula(engine):
    md = sa.MetaData()
    jobs = sa.Table("semantic_translation_jobs", md, sa.Column("id", sa.String, primary_key=True), sa.Column("tenant_id", sa.String))
    segs = sa.Table("semantic_translation_segments", md, sa.Column("id", sa.String, primary_key=True), sa.Column("job_id", sa.String),
                    sa.Column("draft", sa.Text), sa.Column("target", sa.Text), sa.Column("status", sa.String),
                    sa.Column("words", sa.Integer), sa.Column("approved_at", sa.DateTime(timezone=True)))
    errs = sa.Table("semantic_translation_errors", md, sa.Column("id", sa.String, primary_key=True), sa.Column("job_id", sa.String),
                    sa.Column("segment_id", sa.String), sa.Column("severity", sa.String))
    md.create_all(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as c:
        c.execute(jobs.insert().values(id="j", tenant_id=TN))
        c.execute(segs.insert(), [
            {"id": "s1", "job_id": "j", "draft": "Merhaba dünya", "target": "Merhaba dünya", "status": "onaylandi", "words": 50, "approved_at": now},
            {"id": "s2", "job_id": "j", "draft": "Kötü taslak", "target": "İyi çeviri", "status": "onaylandi", "words": 50, "approved_at": now},
            {"id": "s3", "job_id": "j", "draft": None, "target": "Elle", "status": "onaylandi", "words": 100, "approved_at": now},
            {"id": "s4", "job_id": "j", "draft": "x", "target": "y", "status": "cevrildi", "words": 10, "approved_at": None}])
        c.execute(errs.insert(), [{"id": "e1", "job_id": "j", "segment_id": "s2", "severity": "buyuk"},
                                  {"id": "e2", "job_id": "j", "segment_id": "s3", "severity": "kucuk"}])
    st = src.translation_stats(engine, TN, now - timedelta(days=30))
    assert (st["segments"], st["changed"], st["reviewedWords"], st["penalty"]) == (2, 1, 200, 6)
    assert st["mqm"] == 97.0 and 0 < st["editRate"] <= 0.5


def test_seo_unedited_counts_only_decisions_with_the_field(engine):
    md = sa.MetaData()
    props = sa.Table("semantic_seo_proposals", md, sa.Column("id", sa.String, primary_key=True), sa.Column("tenant_id", sa.String),
                     sa.Column("status", sa.String), sa.Column("decided_at", sa.DateTime(timezone=True)))
    md.create_all(engine)
    from semantic_bridge import admin as admin_mod
    admin_mod.ensure(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as c:
        c.execute(props.insert(), [{"id": "p1", "tenant_id": TN, "status": "onaylandi", "decided_at": now},
                                   {"id": "p2", "tenant_id": TN, "status": "onaylandi", "decided_at": now},
                                   {"id": "p3", "tenant_id": TN, "status": "reddedildi", "decided_at": now},
                                   {"id": "p4", "tenant_id": TN, "status": "hazir", "decided_at": None}])
    admin_mod.audit(engine, "u", "approve", "seo_product", "1", "a", {"fields": ["title"], "duzenlenen": []})
    admin_mod.audit(engine, "u", "approve", "seo_product", "2", "b", {"fields": ["title"], "duzenlenen": ["title"]})
    admin_mod.audit(engine, "u", "approve", "seo_product", "3", "c", {"fields": ["title"]})
    st = src.seo_stats(engine, TN, now - timedelta(days=1))
    assert (st["approved"], st["rejected"], st["pending"], st["unedited"], st["editKnown"]) == (2, 1, 1, 1, 2)


# ------------------------------------------------------------------ yetki


def test_access_rules():
    assert A.rule_for("/api/v1/model-quality/report") == A.SYSTEM
    assert A.rule_for("/api/v1/model-quality/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/model-quality/feedback") == A.OPEN
    assert A.rule_for("/api/v1/model-quality/feedback/mine") == A.OPEN
    assert A.rule_for("/api/v1/model-quality/queue") == frozenset({A.page("zeki-kalite")})
    assert A.rule_for("/api/v1/model-quality/scorecard") == frozenset({A.page("zeki-kalite")})
    assert A.features_for("POST", "/api/v1/feedback") == ["ozellik:zeki.geri-bildirim"]
    assert A.features_for("POST", "/api/v1/model-quality/feedback") == ["ozellik:zeki.geri-bildirim"]
    explicit = A.explicit_keys()
    assert {"sayfa:zeki-kalite", "ozellik:zeki-kalite.kosu", "ozellik:zeki-kalite.karar"} <= explicit
    assert "ozellik:zeki.geri-bildirim" not in explicit
