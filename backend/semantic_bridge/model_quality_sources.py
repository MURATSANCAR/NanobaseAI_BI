"""M50 Zeki AI kalitesi — okumalar.

Bu modülün yazdığı tablo yoktur; başka modüllerin köprü tablolarını **yalnız okur**: soru kaydı (`sl_query_log`),
SEO önerileri (`semantic_seo_proposals` + `semantic_audit`), çeviri segmentleri ve hataları
(`semantic_translation_*`), redaksiyon önerileri (`semantic_editorial_suggestions`), M48 kurulum kaydı
(`semantic_itops_releases`, varsa). Başka modülün tablosu adıyla yansıtılarak okunur (o modülün kodu içe
aktarılmaz); tablo bu ortamda yoksa satır «kurulu değil» der. Logo'ya ve CRM'e bu modül hiç gitmez.

Sürüm anlık görüntüsü de burada toplanır: kod sürümü, katalog sürümü, bilgi paketi ve kural dosyalarının özeti,
gündelik terim havuzu özeti, model kimliği ve ayar özeti.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge import model_quality as MQ

log = logging.getLogger("semantic_bridge.model_quality.sources")

_reflect_lock = threading.Lock()
_reflected: dict[tuple[int, str], Optional[sa.Table]] = {}
_cache: dict[tuple, tuple[float, Any]] = {}
_CACHE_SEC = 600.0


def _table(engine: sa.engine.Engine, name: str) -> Optional[sa.Table]:
    """Başka modülün tablosu (adıyla yansıtılır). Yoksa None; bir sonraki çağrıda yeniden bakılır."""
    key = (id(engine), name)
    with _reflect_lock:
        t = _reflected.get(key)
        if t is not None:
            return t
        try:
            if not sa.inspect(engine).has_table(name):
                return None
            t = sa.Table(name, sa.MetaData(), autoload_with=engine)
        except Exception as e:  # noqa: BLE001
            log.warning("model_quality: %s okunamadı: %s", name, e)
            return None
        _reflected[key] = t
        return t


def _cached(key: tuple, fn):
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_SEC:
        return hit[1]
    val = fn()
    _cache[key] = (time.monotonic(), val)
    return val


def clear_cache() -> None:
    _cache.clear()


def _aware(v: Any) -> Optional[datetime]:
    if not isinstance(v, datetime):
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _iso(v: Any) -> Optional[str]:
    v = _aware(v)
    return v.isoformat() if v else None


# ------------------------------------------------------------------ soru kaydı (sl_query_log)

_LIGHT = ("id", "question", "normalized_question", "username", "answer_type", "executed", "row_count", "error",
          "validated", "latency_ms", "catalog_version", "created_at", "answer_summary", "sql_text", "compiler",
          "review_flag")


def _log_table():
    from semantic_layer.store import schema as S
    return S.sl_query_log


def query_rows(engine: sa.engine.Engine, tenant: str, ds: str, since: datetime) -> list[dict[str, Any]]:
    """Pencere içindeki soruların hafif satırları (sonuç ve çözüm yükü yok)."""
    L = _log_table()
    cols = [L.c[n] for n in ("id", "answer_type", "executed", "row_count", "error", "latency_ms", "created_at")]
    with engine.connect() as c:
        rows = c.execute(sa.select(*cols).where(L.c.tenant_id == tenant, L.c.datasource_id == ds,
                                                L.c.created_at >= since)).mappings().all()
    return [dict(r) for r in rows]


def failing_rows(engine: sa.engine.Engine, tenant: str, ds: str, since: datetime,
                 extra_ids: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Sınıflanacak sorular: SQL'li cevap almayan, hatalı, boş dönen ya da kullanıcının Kısmen/Yanlış dediği."""
    L = _log_table()
    bad = sa.or_(L.c.answer_type.in_(MQ.NON_ANSWER_TYPES), L.c.error.isnot(None),
                 sa.and_(L.c.executed.is_(True), L.c.row_count == 0))
    cond = sa.or_(bad, L.c.id.in_(list(extra_ids))) if extra_ids else bad
    cols = [L.c[n] for n in _LIGHT] + [L.c.resolved_json, L.c.gate_json]
    with engine.connect() as c:
        rows = c.execute(sa.select(*cols).where(L.c.tenant_id == tenant, L.c.datasource_id == ds,
                                                L.c.created_at >= since, cond)
                         .order_by(L.c.created_at.desc())).mappings().all()
    return [dict(r) for r in rows if (r.get("answer_type") or "") not in MQ.IGNORED_TYPES]


def query_row(engine: sa.engine.Engine, tenant: str, ds: str, qid: str) -> Optional[dict[str, Any]]:
    L = _log_table()
    cols = [L.c[n] for n in _LIGHT] + [L.c.resolved_json, L.c.gate_json]
    with engine.connect() as c:
        r = c.execute(sa.select(*cols).where(L.c.id == qid, L.c.tenant_id == tenant, L.c.datasource_id == ds)).mappings().first()
    return dict(r) if r else None


def queries_by_id(engine: sa.engine.Engine, tenant: str, ds: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    L = _log_table()
    cols = [L.c[n] for n in _LIGHT] + [L.c.resolved_json, L.c.gate_json]
    out: dict[str, dict[str, Any]] = {}
    with engine.connect() as c:
        for i in range(0, len(ids), 500):
            for r in c.execute(sa.select(*cols).where(L.c.tenant_id == tenant, L.c.datasource_id == ds,
                                                      L.c.id.in_(ids[i:i + 500]))).mappings().all():
                out[r["id"]] = dict(r)
    return out


def query_brief(r: dict[str, Any]) -> dict[str, Any]:
    """Kuyrukta gösterilen soru özeti. Sonuç satırları (kişisel veri içerebilir) gösterilmez."""
    return {"id": r["id"], "question": r.get("question"), "username": r.get("username"),
            "answerType": r.get("answer_type"), "answerSummary": r.get("answer_summary"), "sql": r.get("sql_text"),
            "rowCount": r.get("row_count"), "error": r.get("error"), "catalogVersion": r.get("catalog_version"),
            "latencyMs": r.get("latency_ms"), "createdAt": _iso(r.get("created_at")), "reviewFlag": r.get("review_flag")}


def same_question_wrong(engine: sa.engine.Engine, tenant: str, ds: str, normalized: str, since: datetime) -> int:
    """Aynı soruya (normalleştirilmiş metin) pencere içinde verilen «Yanlış» sayısı (farklı kişi/soru kaydı)."""
    L = _log_table()
    F = MQ.FEEDBACK
    with engine.connect() as c:
        return int(c.execute(sa.select(sa.func.count()).select_from(F.join(L, L.c.id == F.c.query_id)).where(
            F.c.tenant_id == tenant, L.c.datasource_id == ds, L.c.normalized_question == normalized,
            F.c.verdict == "yanlis", F.c.at >= since)).scalar() or 0)


# ------------------------------------------------------------------ geri bildirim


def feedback_rows(engine: sa.engine.Engine, tenant: str, since: datetime) -> list[dict[str, Any]]:
    F = MQ.FEEDBACK
    with engine.connect() as c:
        rows = c.execute(sa.select(F).where(F.c.tenant_id == tenant, F.c.at >= since)).mappings().all()
    return [dict(r) for r in rows]


def feedback_queue(engine: sa.engine.Engine, tenant: str, ds: str, *, verdict: str = "", state: str = "",
                   page: int = 0, size: int = 50) -> dict[str, Any]:
    F = MQ.FEEDBACK
    size = max(1, min(int(size or 50), 200))
    page = max(0, int(page or 0))
    conds = [F.c.tenant_id == tenant]
    if verdict:
        conds.append(F.c.verdict.in_(verdict.split(",")))
    if state:
        conds.append(F.c.triage_state.in_(state.split(",")))
    with engine.connect() as c:
        total = int(c.execute(sa.select(sa.func.count()).select_from(F).where(*conds)).scalar() or 0)
        rows = c.execute(sa.select(F).where(*conds).order_by(F.c.at.desc()).limit(size).offset(page * size)).mappings().all()
        counts = {f"{v}:{s}": int(n) for v, s, n in c.execute(
            sa.select(F.c.verdict, F.c.triage_state, sa.func.count()).where(F.c.tenant_id == tenant)
            .group_by(F.c.verdict, F.c.triage_state)).all()}
    qs = queries_by_id(engine, tenant, ds, [r["query_id"] for r in rows])
    classes = MQ.load_classes(engine)
    items = []
    for r in rows:
        q = qs.get(r["query_id"])
        auto = MQ.classify(MQ.evidence_from_log(q), classes) if q and r["verdict"] != "dogru" else None
        items.append(MQ.feedback_row_view(r, query_brief(q) if q else None, auto))
    return {"items": items, "total": total, "page": page, "size": size, "counts": counts}


# ------------------------------------------------------------------ SEO önerileri


def seo_stats(engine: sa.engine.Engine, tenant: str, since: datetime) -> Optional[dict[str, Any]]:
    P = _table(engine, "semantic_seo_proposals")
    if P is None:
        return None
    A = _table(engine, "semantic_audit")
    with engine.connect() as c:
        by = {s: int(n) for s, n in c.execute(sa.select(P.c.status, sa.func.count()).where(
            P.c.tenant_id == tenant, P.c.decided_at >= since).group_by(P.c.status)).all()}
        pending = int(c.execute(sa.select(sa.func.count()).select_from(P).where(
            P.c.tenant_id == tenant, P.c.status == "hazir")).scalar() or 0)
        last = c.execute(sa.select(sa.func.max(P.c.decided_at)).where(P.c.tenant_id == tenant)).scalar()
        unedited = known = 0
        if A is not None:
            # Karar kaydında «duzenlenen» alanı 2026-09-28'den (M50) sonra yazılır; önceki onaylar sayılmaz.
            for (detail,) in c.execute(sa.select(A.c.detail).where(A.c.kind == "seo_product", A.c.action == "approve",
                                                                    A.c.at >= since)).all():
                d = MQ._loads(detail, {})
                if isinstance(d, dict) and "duzenlenen" in d:
                    known += 1
                    unedited += 0 if d.get("duzenlenen") else 1
    return {"approved": by.get("onaylandi", 0), "rejected": by.get("reddedildi", 0), "pending": pending,
            "unedited": unedited, "editKnown": known, "last": _iso(last)}


# ------------------------------------------------------------------ çeviri


_WS = re.compile(r"\s+")


def _norm(text: Any) -> str:
    return _WS.sub(" ", str(text or "")).strip()


def translation_stats(engine: sa.engine.Engine, tenant: str, since: datetime) -> Optional[dict[str, Any]]:
    """Zeki AI taslağı olan ve pencere içinde onaylanan segmentlerde taslağın düzeltilme oranı; incelenen (onaylanan)
    bütün segmentlerde kalite puanı (M4 formülü: (1 − ceza ÷ incelenen kelime) × 100; küçük 1, büyük 5, kritik 25)."""
    J = _table(engine, "semantic_translation_jobs")
    S = _table(engine, "semantic_translation_segments")
    E = _table(engine, "semantic_translation_errors")
    if J is None or S is None:
        return None

    def compute() -> dict[str, Any]:
        weights = {"kucuk": 1, "buyuk": 5, "kritik": 25}
        join = S.join(J, J.c.id == S.c.job_id)
        base = [J.c.tenant_id == tenant, S.c.status == "onaylandi", S.c.approved_at >= since]
        with engine.connect() as c:
            drafted = c.execute(sa.select(S.c.draft, S.c.target, S.c.words).select_from(join)
                                .where(*base, S.c.draft.isnot(None), S.c.draft != "")).all()
            reviewed_words = int(c.execute(sa.select(sa.func.coalesce(sa.func.sum(S.c.words), 0)).select_from(join)
                                           .where(*base)).scalar() or 0)
            penalty = 0
            if E is not None:
                seg_ids = sa.select(S.c.id).select_from(join).where(*base)
                for sev, n in c.execute(sa.select(E.c.severity, sa.func.count()).where(E.c.segment_id.in_(seg_ids))
                                        .group_by(E.c.severity)).all():
                    penalty += weights.get(sev, 0) * int(n)
            last = c.execute(sa.select(sa.func.max(S.c.approved_at)).select_from(join)
                             .where(J.c.tenant_id == tenant, S.c.status == "onaylandi")).scalar()
        changed = 0
        wsum = 0
        wdist = 0.0
        for draft, target, words in drafted:
            a, b = _norm(draft), _norm(target)
            w = int(words or 0) or 1
            wsum += w
            if a != b:
                changed += 1
                wdist += (1 - difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio()) * w
        return {"segments": len(drafted), "changed": changed,
                "editRate": round(wdist / wsum, 4) if wsum else None,
                "mqm": round((1 - penalty / reviewed_words) * 100, 2) if reviewed_words else None,
                "penalty": penalty, "reviewedWords": reviewed_words, "last": _iso(last)}

    return _cached(("ceviri", id(engine), tenant, since.date().isoformat()), compute)


# ------------------------------------------------------------------ redaksiyon


def redaction_stats(engine: sa.engine.Engine, tenant: str, since: datetime) -> Optional[dict[str, Any]]:
    W = _table(engine, "semantic_editorial_works")
    G = _table(engine, "semantic_editorial_suggestions")
    if W is None or G is None:
        return None
    join = G.join(W, W.c.id == G.c.work_id)
    with engine.connect() as c:
        by = {s: int(n) for s, n in c.execute(sa.select(G.c.status, sa.func.count()).select_from(join).where(
            W.c.tenant_id == tenant, G.c.decided_at >= since).group_by(G.c.status)).all()}
        modified = int(c.execute(sa.select(sa.func.count()).select_from(join).where(
            W.c.tenant_id == tenant, G.c.decided_at >= since, G.c.status == "kabul", G.c.applied_text.isnot(None),
            G.c.applied_text != G.c.suggestion)).scalar() or 0)
        pending = int(c.execute(sa.select(sa.func.count()).select_from(join).where(
            W.c.tenant_id == tenant, G.c.status == "bekliyor")).scalar() or 0)
        last = c.execute(sa.select(sa.func.max(G.c.decided_at)).select_from(join).where(W.c.tenant_id == tenant)).scalar()
    return {"accepted": by.get("kabul", 0), "rejected": by.get("red", 0), "modified": modified, "pending": pending,
            "last": _iso(last)}


# ------------------------------------------------------------------ M48 kurulum kaydı (yalnız okuma)


def itops_releases(engine: sa.engine.Engine, tenant: str, start: Optional[datetime], end: Optional[datetime]) -> list[dict[str, Any]]:
    """M48 Sistem durumu'nun kurulum kaydından ölçüm penceresine düşenler. Tablo yoksa boş."""
    R = _table(engine, "semantic_itops_releases")
    if R is None or not start or not end:
        return []
    with engine.connect() as c:
        rows = c.execute(sa.select(R).where(R.c.tenant_id == tenant, R.c.at >= start, R.c.at <= end)
                         .order_by(R.c.at)).mappings().all()
    return [{"kind": "kurulum", "source": "sistem-durumu", "at": _iso(r["at"]), "env": r.get("env"),
             "codeSha": r.get("code_sha"), "label": f"Kurulum ({r.get('env') or '—'}) {str(r.get('code_sha') or '')[:12]}"}
            for r in rows]


def itops_release_list(engine: sa.engine.Engine, tenant: str, *, limit: int = 0) -> list[dict[str, Any]]:
    R = _table(engine, "semantic_itops_releases")
    if R is None:
        return []
    q = sa.select(R).where(R.c.tenant_id == tenant).order_by(R.c.at.desc())
    if limit:
        q = q.limit(limit)
    with engine.connect() as c:
        rows = c.execute(q).mappings().all()
    return [{"at": _iso(r["at"]), "env": r.get("env"), "codeSha": r.get("code_sha"), "note": r.get("note")} for r in rows]


# ------------------------------------------------------------------ sürüm anlık görüntüsü


def files_digest(paths: list[Path], *, suffixes: tuple[str, ...] = (".md", ".yml", ".yaml", ".json", ".txt", ".sql")) -> Optional[str]:
    """Klasörlerdeki metin dosyalarının (göreli yol + içerik) özeti. Hiç dosya yoksa None."""
    h = hashlib.sha256()
    seen = 0
    for root in paths:
        if not root.exists():
            continue
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in suffixes
                                                     and not p.name.startswith("._"))
        for f in files:
            try:
                h.update(str(f.relative_to(root.parent if root.is_file() else root)).encode("utf-8"))
                h.update(f.read_bytes())
                seen += 1
            except OSError as e:
                log.warning("model_quality: %s okunamadı: %s", f, e)
    return h.hexdigest()[:32] if seen else None


def _paths(conf_value: str) -> list[Path]:
    return [Path(x.strip()) for x in (conf_value or "").split(",") if x.strip()]


_REPO = Path(__file__).resolve().parents[2]


def code_sha(conf) -> Optional[str]:
    """Çalışan kodun sürümü: ayar/ortam `MODEL_QUALITY_CODE_SHA` > kaynak ağacındaki `.code-sha` > git HEAD.
    Hiçbiri yoksa None; o zaman sürüm satırı kurulumun bildirdiği kodu taşır."""
    v = (conf("MODEL_QUALITY_CODE_SHA") or "").strip()
    if v:
        return v[:64]
    f = _REPO / ".code-sha"
    try:
        if f.exists():
            return f.read_text(encoding="utf-8").strip()[:64] or None
        head = _REPO / ".git" / "HEAD"
        if head.exists():
            ref = head.read_text(encoding="utf-8").strip()
            if ref.startswith("ref: "):
                p = _REPO / ".git" / ref[5:]
                if p.exists():
                    return p.read_text(encoding="utf-8").strip()[:64]
            elif re.fullmatch(r"[0-9a-f]{40}", ref):
                return ref
    except OSError:
        return None
    return None


def snapshot(rt, conf, *, code: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """(sürüm alanları, iç bilgi). Model kimliği yalnız iç kayıtta tutulur; ekrana «Zeki AI modeli, sürüm …» gider."""
    r = rt()
    s = r.settings
    latest = None
    try:
        latest = r.store.latest_version(s.tenant_id, s.datasource_id)
    except Exception as e:  # noqa: BLE001
        log.warning("model_quality: katalog sürümü okunamadı: %s", e)
    knowledge = [Path(s.project_dir)] if getattr(s, "project_dir", None) else []
    extra_rules = _paths(conf("MODEL_QUALITY_RULES_PATHS"))
    prompts = _paths(conf("MODEL_QUALITY_PROMPT_PATHS"))
    pool = getattr(r, "language_pool", None)
    model_ref = f"{s.llm_model}@{re.sub(r'^https?://', '', str(s.llm_base or ''))}"
    model_settings = {"model": s.llm_model, "base": s.llm_base, "extra": getattr(s, "llm_extra", {}),
                      "timeout": getattr(s, "llm_timeout", None)}
    snap = {
        "code_sha": code or code_sha(conf),
        "catalog_version": (latest or {}).get("version"),
        "catalog_certified": (latest or {}).get("certified_count"),
        "knowledge_digest": files_digest(knowledge) if knowledge else None,
        "rules_digest": files_digest(extra_rules) if extra_rules else None,
        "language_digest": (str(getattr(pool, "content_hash", "") or "")[:32] or None) if pool is not None else None,
        "prompt_digest": files_digest(prompts) if prompts else None,
        "model_ref": model_ref[:200],
        "model_digest": MQ.digest_of(model_settings),
    }
    return snap, {"model_ref": model_ref}


def last_code_sha(engine: sa.engine.Engine, tenant: str) -> Optional[str]:
    V = MQ.VERSIONS
    with engine.connect() as c:
        return c.execute(sa.select(V.c.code_sha).where(V.c.tenant_id == tenant, V.c.code_sha.isnot(None))
                         .order_by(V.c.id.desc()).limit(1)).scalar()


def last_finished(engine: sa.engine.Engine, tenant: str) -> dict[str, Optional[dict[str, Any]]]:
    """Takım başına son bitmiş koşu (karne için)."""
    R = MQ.RUNS
    out: dict[str, Optional[dict[str, Any]]] = {}
    with engine.connect() as c:
        for suite in MQ.SUITES:
            r = c.execute(sa.select(R).where(R.c.tenant_id == tenant, R.c.suite == suite, R.c.status == "bitti")
                          .order_by(R.c.finished_at.desc()).limit(1)).mappings().first()
            out[suite] = MQ.run_view(r) if r else None
    return out


def recent_gate_cases(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    """Her takımın son bitmiş koşusunda sağlam olmayan vakalar (sınıf panosu için)."""
    runs = [r for r in last_finished(engine, tenant).values() if r]
    if not runs:
        return []
    C = MQ.CASES
    with engine.connect() as c:
        rows = c.execute(sa.select(C.c.run_id, C.c.case_id, C.c.question, C.c.status, C.c.klass).where(
            C.c.run_id.in_([r["id"] for r in runs]), C.c.status.notin_(("saglam", "veri")))).mappings().all()
    suite_of = {r["id"]: r["suite"] for r in runs}
    return [{"runId": r["run_id"], "suite": suite_of.get(r["run_id"]), "caseId": r["case_id"], "question": r["question"],
             "status": r["status"], "klass": r["klass"]} for r in rows]


def classified_items(engine: sa.engine.Engine, tenant: str, ds: str, since: datetime) -> list[dict[str, Any]]:
    """Pencere içindeki sınıflanacak sorular: {queryId, question, klass, source, at, answerType, verdict}.
    İnsanın kuyrukta verdiği sınıf kuralın önüne geçer."""
    fb = feedback_rows(engine, tenant, since)
    flagged = {f["query_id"]: f for f in fb if f["verdict"] in ("kismen", "yanlis")}
    rows = failing_rows(engine, tenant, ds, since, tuple(flagged))
    classes = MQ.load_classes(engine)
    from semantic_bridge import model_quality_clusters as MC

    cluster_class = MC.human_classes(engine, tenant)     # başarısız soru kümesinden insanın onayladığı sınıf
    out = []
    for r in rows:
        f = flagged.get(r["id"])
        if (f or {}).get("klass"):
            klass, how = f["klass"], "insan"
        elif r["id"] in cluster_class:
            klass, how = cluster_class[r["id"]], "kume"
        else:
            klass, how = MQ.classify(MQ.evidence_from_log(r), classes), "kural"
        out.append({"queryId": r["id"], "question": r.get("question"), "klass": klass, "klassSource": how,
                    "source": "geri-bildirim" if f else "kayit", "at": r.get("created_at"),
                    "answerType": r.get("answer_type"), "verdict": (f or {}).get("verdict"),
                    "username": r.get("username")})
    return out


def dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def window(days: int) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    return now, now - timedelta(days=max(1, int(days)))


def env_name(conf) -> Optional[str]:
    v = (conf("MODEL_QUALITY_ENV") or os.environ.get("MODEL_QUALITY_ENV") or "").strip().lower()
    return v if v in ("test", "vm") else None
