"""Runtime learned query cache — remember successful Q→SQL for fast repeats / near-duplicates.

Not a semantic "verified truth" catalog: this is an execution-success cache so that
when a user asks again (exact or highly similar wording), chat skips NL→SQL LLM.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

_TR_MAP = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")

_PERIOD_MARKERS = (
    "bugun",
    "bugunku",
    "dun",
    "dunku",
    "bu hafta",
    "gecen hafta",
    "bu ay",
    "bu ayki",
    "gecen ay",
    "gecen ayki",
    "bu yil",
    "bu yilki",
    "gecen yil",
    "bu ceyrek",
    "gecen ceyrek",
    "ay basindan",
    "yil basindan",
    "son 7",
    "son 30",
    "son 90",
    "2024",
    "2025",
    "2026",
    "2027",
)

_PERIOD_CANON = {
    "bugun": "TODAY",
    "bugunku": "TODAY",
    "dun": "YESTERDAY",
    "dunku": "YESTERDAY",
    "bu hafta": "CURRENT_WEEK",
    "gecen hafta": "PREVIOUS_WEEK",
    "bu ay": "CURRENT_MONTH",
    "bu ayki": "CURRENT_MONTH",
    "gecen ay": "PREVIOUS_MONTH",
    "gecen ayki": "PREVIOUS_MONTH",
    "bu yil": "CURRENT_YEAR",
    "bu yilki": "CURRENT_YEAR",
    "gecen yil": "PREVIOUS_YEAR",
    "bu ceyrek": "CURRENT_QUARTER",
    "gecen ceyrek": "PREVIOUS_QUARTER",
    "ay basindan": "MTD",
    "yil basindan": "YTD",
    "son 7": "LAST_7",
    "son 30": "LAST_30",
    "son 90": "LAST_90",
}


def _period_key(norm: str) -> frozenset[str]:
    hits = set()
    for m in _PERIOD_MARKERS:
        if m in norm:
            hits.add(_PERIOD_CANON.get(m, m))
    for y in re.findall(r"\b20\d{2}\b", norm):
        hits.add(y)
    return frozenset(hits)

# Collapse TR paraphrases before Jaccard so "kaç X var" ≈ "X sayısı nedir"
_TOKEN_CANON = {
    "kac": "COUNT",
    "sayisi": "COUNT",
    "sayi": "COUNT",
    "adet": "COUNT",
    "tane": "COUNT",
    "toplami": "SUM",
    "toplam": "SUM",
    "tutari": "SUM",
    "tutar": "SUM",
    "listele": "LIST",
    "goster": "LIST",
    "getir": "LIST",
    "nedir": "Q",
    "ne": "Q",
    "var": "Q",
    "musteri": "customer",
    "musteriler": "customer",
    "cari": "customer",
    "cariler": "customer",
    "fatura": "invoice",
    "faturalar": "invoice",
    "faturalari": "invoice",
    "siparis": "order",
    "siparisler": "order",
    "urun": "product",
    "urunler": "product",
    "stok": "stock",
    "odeme": "payment",
    "odemeler": "payment",
}


def normalize_question(q: str) -> str:
    s = (q or "").strip().translate(_TR_MAP).lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    return s.strip()


def _canonical_tokens(norm: str) -> set[str]:
    out: set[str] = set()
    for tok in norm.split():
        out.add(_TOKEN_CANON.get(tok, tok))
    return out


def question_hash(q: str) -> str:
    return hashlib.sha256(normalize_question(q).encode("utf-8")).hexdigest()


def _token_jaccard(a: str, b: str) -> float:
    ta = _canonical_tokens(a)
    tb = _canonical_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


_LOCK = threading.RLock()
_MEM: dict[tuple[str, str, str], dict[str, Any]] = {}  # (tenant, ds, qhash) → row
_MEM_BY_DS: dict[tuple[str, str], list[dict[str, Any]]] = {}
_SCHEMA_READY = False

# BUG (fixed): _MEM/_MEM_BY_DS used to be write-through-only — populated by
# remember()/_bump_hit() and additively hydrated once per (tenant, datasource)
# per process lifetime. A row corrected or deleted directly in Postgres (e.g.
# an operator fixing a bad learned answer) was invisible to any already-running
# worker: it kept serving the stale in-memory copy to every user, across both
# uvicorn workers, until someone thought to restart the service. Exact-match
# lookups now always re-verify against the DB (a single indexed read — cheap
# next to the multi-minute LLM path this cache exists to skip); the fuzzy
# "similar" bucket is periodically re-synced (evicting rows Postgres no
# longer has) instead of being trusted forever.
_DS_HYDRATED_AT: dict[tuple[str, str], float] = {}
HYDRATE_TTL_SEC = float(os.environ.get("BI_LEARNED_CACHE_TTL_SEC", "60"))


def _periods_compatible(a: str, b: str) -> bool:
    pa, pb = _period_key(a), _period_key(b)
    if not pa and not pb:
        return True
    if not pa or not pb:
        # one dated, one undated — only OK if SQL has no period binds (checked later)
        return False
    return pa == pb


@dataclass
class LearnedHit:
    id: str
    question: str
    sql: str
    score: float
    match: str  # exact | similar
    hit_count: int = 0
    source: str = "learned_cache"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "sql": self.sql,
            "score": self.score,
            "match": self.match,
            "hit_count": self.hit_count,
            "source": self.source,
        }


def ensure_schema(engine: Engine) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS bi_learned_queries (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(128) NOT NULL DEFAULT 'default',
                  datasource_id VARCHAR(128) NOT NULL,
                  question TEXT NOT NULL,
                  normalized_question TEXT NOT NULL,
                  question_hash VARCHAR(64) NOT NULL,
                  sql_text TEXT NOT NULL,
                  sql_source VARCHAR(64),
                  hit_count INTEGER NOT NULL DEFAULT 1,
                  success_count INTEGER NOT NULL DEFAULT 1,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  last_hit_at TIMESTAMPTZ
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_bi_learned_qhash
                  ON bi_learned_queries (tenant_id, datasource_id, question_hash)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_bi_learned_ds_updated
                  ON bi_learned_queries (tenant_id, datasource_id, updated_at DESC)
                """
            )
        )
    _SCHEMA_READY = True


def _mem_put(row: dict[str, Any]) -> None:
    key = (row["tenant_id"], row["datasource_id"], row["question_hash"])
    with _LOCK:
        _MEM[key] = row
        ds_key = (row["tenant_id"], row["datasource_id"])
        bucket = _MEM_BY_DS.setdefault(ds_key, [])
        bucket[:] = [r for r in bucket if r["question_hash"] != row["question_hash"]]
        bucket.insert(0, row)
        del bucket[800:]  # cap per datasource in memory


def _mem_evict(tenant_id: str, datasource_id: str, question_hash: str) -> None:
    with _LOCK:
        _MEM.pop((tenant_id, datasource_id, question_hash), None)
        bucket = _MEM_BY_DS.get((tenant_id, datasource_id))
        if bucket:
            bucket[:] = [r for r in bucket if r.get("question_hash") != question_hash]


def _fetch_exact(
    engine: Engine, tenant_id: str, datasource_id: str, question_hash: str
) -> Optional[dict[str, Any]]:
    """Single indexed read (ux_bi_learned_qhash) — the source of truth for
    exact-match lookups; deliberately not trusted from memory alone."""
    from sqlalchemy import text

    ensure_schema(engine)
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    """
                    SELECT id, tenant_id, datasource_id, question, normalized_question,
                           question_hash, sql_text, sql_source, hit_count, success_count
                    FROM bi_learned_queries
                    WHERE tenant_id = :t AND datasource_id = :ds AND question_hash = :qh
                    """
                ),
                {"t": tenant_id, "ds": datasource_id, "qh": question_hash},
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


def _hydrate_ds(engine: Engine, tenant_id: str, datasource_id: str, *, limit: int = 500) -> None:
    """(Re)sync the in-process fuzzy-match bucket for (tenant, datasource) from
    Postgres, evicting entries Postgres no longer has — a plain additive
    hydrate could never notice rows deleted or changed outside the app."""
    from sqlalchemy import text

    ensure_schema(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, tenant_id, datasource_id, question, normalized_question,
                       question_hash, sql_text, sql_source, hit_count, success_count
                FROM bi_learned_queries
                WHERE tenant_id = :t AND datasource_id = :ds
                ORDER BY hit_count DESC, updated_at DESC
                LIMIT :lim
                """
            ),
            {"t": tenant_id, "ds": datasource_id, "lim": limit},
        ).mappings()
        fresh = [dict(r) for r in rows]

    fresh_hashes = {r["question_hash"] for r in fresh}
    ds_key = (tenant_id, datasource_id)
    with _LOCK:
        stale = _MEM_BY_DS.get(ds_key) or []
        for r in stale:
            qh = r.get("question_hash")
            if qh and qh not in fresh_hashes:
                _MEM.pop((tenant_id, datasource_id, qh), None)
        _MEM_BY_DS[ds_key] = []
    for r in fresh:
        _mem_put(r)
    with _LOCK:
        _DS_HYDRATED_AT[ds_key] = time.monotonic()


def remember(
    engine: Engine | None,
    *,
    tenant_id: str,
    datasource_id: str,
    question: str,
    sql: str,
    sql_source: str = "nl2sql_plan",
) -> Optional[str]:
    """Upsert a successful question→SQL pair. Returns learned id."""
    q = (question or "").strip()
    s = (sql or "").strip()
    if not q or not s or engine is None:
        return None
    # Don't learn PLAN_ONLY / empty / explain-only
    if not re.search(r"\bselect\b", s, re.I):
        return None
    # Skip learning bind-template scenarios with unresolved :binds unless already parameterized
    # (chat execute path uses rendered SQL without named binds for gateway)
    norm = normalize_question(q)
    qh = question_hash(q)
    # The primary key is global while the hash was only of the question: the same question learned
    # for a second tenant or datasource collided with the first row, the insert raised, and a blanket
    # except swallowed it — learning simply stopped working for everyone after the first.
    scope = hashlib.sha256(f"{tenant_id}\n{datasource_id}".encode()).hexdigest()[:8]
    lid = f"lq-{scope}-{qh[:16]}"
    now = datetime.now(timezone.utc)
    try:
        from sqlalchemy import text

        ensure_schema(engine)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO bi_learned_queries (
                      id, tenant_id, datasource_id, question, normalized_question,
                      question_hash, sql_text, sql_source, hit_count, success_count,
                      created_at, updated_at, last_hit_at
                    ) VALUES (
                      :id, :t, :ds, :q, :nq, :qh, :sql, :src, 1, 1, :now, :now, :now
                    )
                    ON CONFLICT (tenant_id, datasource_id, question_hash) DO UPDATE SET
                      sql_text = EXCLUDED.sql_text,
                      sql_source = EXCLUDED.sql_source,
                      question = EXCLUDED.question,
                      success_count = bi_learned_queries.success_count + 1,
                      updated_at = EXCLUDED.updated_at,
                      last_hit_at = EXCLUDED.last_hit_at
                    """
                ),
                {
                    "id": lid,
                    "t": tenant_id,
                    "ds": datasource_id,
                    "q": q[:2000],
                    "nq": norm[:2000],
                    "qh": qh,
                    "sql": s[:20000],
                    "src": (sql_source or "nl2sql_plan")[:64],
                    "now": now,
                },
            )
        row = {
            "id": lid,
            "tenant_id": tenant_id,
            "datasource_id": datasource_id,
            "question": q,
            "normalized_question": norm,
            "question_hash": qh,
            "sql_text": s,
            "sql_source": sql_source,
            "hit_count": 1,
            "success_count": 1,
        }
        _mem_put(row)
        return lid
    except Exception as e:  # noqa: BLE001
        # Silent for years: a failed insert returned None and the caller could not tell learning
        # from a deliberate skip. A storage fault that stops the system learning must be visible.
        log.warning("learned query not stored (tenant=%s datasource=%s): %s", tenant_id, datasource_id, e)
        return None


def lookup(
    engine: Engine | None,
    *,
    tenant_id: str,
    datasource_id: str,
    question: str,
    similar_threshold: float = 0.55,
) -> Optional[LearnedHit]:
    """Exact hash first, then high-overlap similar question with compatible periods.

    Exact-match always re-verifies against Postgres (see _fetch_exact) instead
    of trusting the in-process cache indefinitely — a single indexed lookup is
    negligible next to the multi-minute LLM path this cache exists to skip,
    and it is what makes externally-corrected/deleted rows actually take
    effect without a service restart.
    """
    q = (question or "").strip()
    if not q:
        return None
    norm = normalize_question(q)
    qh = question_hash(q)
    ds_key = (tenant_id, datasource_id)

    row: Optional[dict[str, Any]] = None
    if engine is not None:
        try:
            row = _fetch_exact(engine, tenant_id, datasource_id, qh)
        except Exception:
            row = None
        if row is not None:
            _mem_put(row)
        else:
            _mem_evict(tenant_id, datasource_id, qh)
    else:
        with _LOCK:
            row = _MEM.get((tenant_id, datasource_id, qh))

    if row and row.get("sql_text"):
        _bump_hit(engine, row)
        return LearnedHit(
            id=str(row["id"]),
            question=str(row["question"]),
            sql=str(row["sql_text"]),
            score=1.0,
            match="exact",
            hit_count=int(row.get("hit_count") or 1),
        )

    # Similar: require period compatibility + high token overlap. The fuzzy
    # bucket is periodically re-synced from Postgres (TTL) rather than hydrated
    # once and trusted forever — see _hydrate_ds's eviction of stale rows.
    if engine is not None:
        last = _DS_HYDRATED_AT.get(ds_key, 0.0)
        if (time.monotonic() - last) > HYDRATE_TTL_SEC:
            try:
                _hydrate_ds(engine, tenant_id, datasource_id)
            except Exception:
                pass

    with _LOCK:
        bucket = list(_MEM_BY_DS.get(ds_key) or [])

    best: Optional[dict[str, Any]] = None
    best_score = 0.0
    for cand in bucket:
        cnorm = str(cand.get("normalized_question") or "")
        if not cnorm or not cand.get("sql_text"):
            continue
        if not _periods_compatible(norm, cnorm):
            continue
        score = _token_jaccard(norm, cnorm)
        if score > best_score:
            best_score = score
            best = cand

    if best and best_score >= similar_threshold:
        # If SQL uses period binds but we somehow passed — still OK (chat path uses resolved SQL)
        _bump_hit(engine, best)
        return LearnedHit(
            id=str(best["id"]),
            question=str(best["question"]),
            sql=str(best["sql_text"]),
            score=round(best_score, 4),
            match="similar",
            hit_count=int(best.get("hit_count") or 1),
        )
    return None


def _bump_hit(engine: Engine | None, row: dict[str, Any]) -> None:
    row["hit_count"] = int(row.get("hit_count") or 0) + 1
    _mem_put(row)
    if engine is None:
        return
    try:
        from sqlalchemy import text

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE bi_learned_queries
                    SET hit_count = hit_count + 1, last_hit_at = :now
                    WHERE tenant_id = :t AND datasource_id = :ds AND question_hash = :qh
                    """
                ),
                {
                    "t": row["tenant_id"],
                    "ds": row["datasource_id"],
                    "qh": row["question_hash"],
                    "now": datetime.now(timezone.utc),
                },
            )
    except Exception:
        pass


def remember_scenario_paraphrase(
    *,
    tenant_id: str,
    datasource_id: str,
    question: str,
    scenario_id: str | None,
) -> None:
    """Attach user wording as scenario paraphrase so exact hash hits next time.

    Only when detected period/family/entity agree with the scenario — otherwise a
    wrong fast-path hit would poison future exact matches.
    """
    if not scenario_id or not (question or "").strip():
        return
    try:
        from nanobase_api.scenario_engine.application.intent_slots import (
            detect_family,
            detect_period,
            entity_score,
            family_compatible,
            period_compatible,
        )
        from nanobase_api.scenario_engine.domain.scenario import ScenarioParaphrase
        from nanobase_api.scenario_engine.domain.status import ScenarioStatus
        from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

        store = get_scenario_store()
        inst = store.get_instance(scenario_id)
        if inst is None:
            return
        plan = inst.logical_plan
        q_period = detect_period(question)
        q_family = detect_family(question)
        if not period_compatible(q_period, plan.period):
            return
        if not family_compatible(q_family, inst.family):
            return
        if entity_score(question, plan.entity, plan.physical_table) < 0.3:
            return
        # Avoid dupes via hash index
        qh = question_hash(question)
        existing = store.find_by_normalized_hash(
            tenant_id=tenant_id, datasource_id=datasource_id, qhash=qh
        )
        if existing is not None:
            return
        para = ScenarioParaphrase(
            id=f"par-learn-{uuid.uuid4().hex[:12]}",
            scenario_id=scenario_id,
            language="tr",
            text=question.strip()[:2000],
            status=ScenarioStatus.PUBLISHED,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
        )
        store.save_paraphrase(para)
    except Exception:
        pass
