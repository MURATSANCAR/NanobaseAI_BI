"""Datasource-scoped chat suggestions: defaults + learned popular questions."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))

# Optional demo defaults (exact datasource id match only).
# Custom sources: SECRETS/chat-suggestions.json → {"sources": {"my_ds": ["…"]}}
_DEFAULTS: dict[str, list[str]] = {
    "sigorta": [
        "Hasar taleplerinin toplam sayısı kaç?",
        "Hasar taleplerini duruma göre grafik olarak göster",
        "Aylık yeni poliçe trendini göster",
        "Bölge bazında aktif poliçeleri listele",
        "En çok hasar alan acenteler hangileri?",
        "Son 30 günde açılan hasar taleplerini özetle",
    ],
    "erp": [
        "Kaç müşteri var?",
        "Müşteri sayısı nedir?",
        "Kaç fatura var?",
        "Bugüne ait faturaları getir.",
        "Satış siparişlerinin toplam sayısı nedir?",
        "Son faturaları listele",
    ],
    "bi_reporting": [
        "Kaç müşteri var?",
        "Sipariş sayısı nedir?",
        "Fatura brüt tutarını göster",
        "En çok satılan ürünleri listele",
        "Son siparişleri göster",
        "Ürün kategorilerine göre özet ver",
    ],
}

_GENERIC = [
    "Tabloları ve satır sayılarını özetle",
    "Son 5 kaydı listele",
    "En önemli metrikleri kısaca anlat",
]

# Threshold-alert chips (Alerts page) — scoped to datasource / project.
_ALERT_DEFAULTS: dict[str, list[str]] = {
    "sigorta": [
        "Açık hasar talebi sayısı bir sınırı aşarsa bana bildirim gönder",
        "Günlük yeni poliçe adedi hedefin altına düşerse bana bildirim gönder",
        "Reddedilen hasar oranı kritik eşiğin üstüne çıkarsa bana bildirim gönder",
    ],
    "erp": [
        "Günlük fatura tutarı bir sınırın altına düşerse bana bildirim gönder",
        "Stok bakiyesi kritik seviyenin altına düşerse bana bildirim gönder",
        "Açık satış siparişi sayısı bir eşiği aşarsa bana bildirim gönder",
    ],
    "bi_reporting": [
        "Günlük sipariş adedi bir sınırın altına düşerse bana bildirim gönder",
        "Fatura brüt tutarı bir eşiği aşarsa bana bildirim gönder",
        "Aktif müşteri sayısı beklenenin altına düşerse bana bildirim gönder",
    ],
}

_ALERT_GENERIC = [
    "Önemli bir metrik bir sınırın altına düşerse bana bildirim gönder",
    "Kritik bir gösterge eşiği aşarsa bana bildirim gönder",
    "Günlük kayıt adedi beklenenin altına düşerse bana bildirim gönder",
]


def _norm(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip().lower())
    return s[:240]


# Small in-process cache so chat chips stay fast under repeated loads.
_PREPARED_SQL_CACHE: dict[tuple[str, str, str], dict[str, Any] | None] = {}


def resolve_prepared_sql(
    question: str,
    *,
    tenant_id: str,
    datasource_id: str,
) -> dict[str, Any] | None:
    """Resolve precompiled scenario SQL + binds for a chip question (best-effort)."""
    q = (question or "").strip()
    if len(q) < 4:
        return None
    key = (tenant_id, datasource_id, _norm(q))
    if key in _PREPARED_SQL_CACHE:
        cached = _PREPARED_SQL_CACHE[key]
        return dict(cached) if cached else None
    try:
        from nanobase_api.scenario_engine.application.runtime import try_precompiled_scenario

        hit = try_precompiled_scenario(q, tenant_id=tenant_id, datasource_id=datasource_id)
    except Exception:
        hit = None
    if not hit:
        _PREPARED_SQL_CACHE[key] = None
        return None
    sql = str(hit.get("sqlTemplate") or hit.get("sql") or "").strip()
    if not sql:
        _PREPARED_SQL_CACHE[key] = None
        return None
    payload = {
        "sql_hint": sql,
        "bind_params": dict(hit.get("parameters") or hit.get("bindParams") or {}),
        "scenarioCode": hit.get("scenarioCode"),
        "scenarioId": hit.get("scenarioId"),
    }
    _PREPARED_SQL_CACHE[key] = payload
    return dict(payload)


def _enrich_suggestion(
    item: dict[str, Any],
    *,
    tenant_id: str,
    datasource_id: str,
) -> dict[str, Any]:
    """Attach sql_hint / bind_params when the question matches a published scenario."""
    out = dict(item)
    if out.get("sql_hint"):
        return out
    hit = resolve_prepared_sql(
        str(out.get("text") or ""),
        tenant_id=tenant_id,
        datasource_id=datasource_id,
    )
    if not hit:
        return out
    out["sql_hint"] = hit["sql_hint"]
    if hit.get("bind_params"):
        out["bind_params"] = hit["bind_params"]
    if hit.get("scenarioCode"):
        out["scenarioCode"] = hit["scenarioCode"]
    if out.get("source") == "default":
        out["source"] = "scenario"
    return out


def defaults_for(datasource_id: str) -> list[str]:
    sid = (datasource_id or "").strip()
    if not sid:
        return list(_GENERIC)
    path = SECRETS / "chat-suggestions.json"
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            specs = (raw.get("sources") or {}).get(sid)
            if isinstance(specs, list) and specs:
                return [str(x) for x in specs if str(x).strip()]
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    packs = _remap_reporting_pack(_DEFAULTS)
    return list(packs.get(sid) or _GENERIC)


def build_suggestions(
    *,
    engine: Any = None,
    tenant_id: str,
    datasource_id: str,
    limit: int = 6,
    question_repo: Any | None = None,
) -> dict[str, Any]:
    from nanobase_api.infrastructure.active_source import prefer_datasource_id

    lim = max(1, min(int(limit or 6), 12))
    sid = prefer_datasource_id(datasource_id)
    defaults = defaults_for(sid)
    if question_repo is None:
        from nanobase_api.infrastructure.conversation_repo import ConversationRepository

        question_repo = ConversationRepository(engine)
    learned = question_repo.top_user_questions(
        tenant_id=tenant_id,
        datasource_id=sid,
        limit=lim * 2,
    )

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _push(item: dict[str, Any]) -> None:
        q = str(item.get("text") or "").strip()
        n = _norm(q)
        if len(n) < 6 or n in seen:
            return
        seen.add(n)
        candidates.append(item)

    # SQL-ready defaults first (chat empty-state should be click→fast-answer).
    for q in defaults:
        row = _enrich_suggestion(
            {"text": q, "source": "default", "count": 0},
            tenant_id=tenant_id,
            datasource_id=sid,
        )
        _push(row)

    # Precompiled scenario catalog chips with SQL from compilations.
    try:
        from nanobase_api.scenario_engine.application.param_resolver import resolve_parameters
        from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

        store = get_scenario_store()
        for item in store.suggested_questions(
            tenant_id=tenant_id, datasource_id=sid, limit=max(lim * 3, 12)
        ):
            q = str(item.get("question") or "").strip()
            row: dict[str, Any] = {
                "text": q,
                "source": "scenario",
                "count": 0,
                "category": item.get("category"),
                "scenarioCode": item.get("scenarioCode"),
            }
            sid_sc = item.get("scenarioId")
            if sid_sc:
                inst = store.get_instance(str(sid_sc))
                comp = store.get_compilation(str(sid_sc), dialect="postgres") if inst else None
                if inst is not None and comp is not None and (comp.sql_template or "").strip():
                    row["sql_hint"] = comp.sql_template
                    row["bind_params"] = resolve_parameters(q, inst.logical_plan).to_bind_dict()
            if not row.get("sql_hint"):
                row = _enrich_suggestion(row, tenant_id=tenant_id, datasource_id=sid)
            _push(row)
    except Exception:
        pass

    # Learned history — keep if it resolves to SQL, else low priority filler.
    for item in learned:
        q = str(item.get("question") or "").strip()
        # Long free-form analytics rarely have a prepared script; skip slow miss path.
        if len(q) > 120:
            row = {"text": q, "source": "learned", "count": int(item.get("count") or 1)}
        else:
            row = _enrich_suggestion(
                {"text": q, "source": "learned", "count": int(item.get("count") or 1)},
                tenant_id=tenant_id,
                datasource_id=sid,
            )
        _push(row)

    def _rank(s: dict[str, Any]) -> tuple[int, int, int]:
        ready = 0 if s.get("sql_hint") else 1
        src = {"scenario": 0, "default": 1, "learned": 2}.get(str(s.get("source")), 3)
        return (ready, src, -int(s.get("count") or 0))

    ready = sorted([c for c in candidates if c.get("sql_hint")], key=_rank)
    learned_u = sorted(
        [c for c in candidates if not c.get("sql_hint") and c.get("source") == "learned"],
        key=lambda s: -int(s.get("count") or 0),
    )
    other_u = sorted(
        [c for c in candidates if not c.get("sql_hint") and c.get("source") != "learned"],
        key=_rank,
    )
    out: list[dict[str, Any]] = []
    for bucket in (ready, learned_u, other_u):
        for item in bucket:
            if len(out) >= lim:
                break
            out.append(item)
        if len(out) >= lim:
            break

    return {
        "datasource_id": sid,
        "suggestions": out,
        "learned_count": sum(1 for s in out if s["source"] == "learned"),
        "default_count": sum(1 for s in out if s["source"] == "default"),
        "scenario_count": sum(1 for s in out if s["source"] == "scenario"),
        "prepared_count": sum(1 for s in out if s.get("sql_hint")),
    }


def _remap_reporting_pack(packs: dict[str, list[str]]) -> dict[str, list[str]]:
    out = dict(packs)
    try:
        from nanobase_api.infrastructure.datasource_registry import reporting_datasource_id

        rid = reporting_datasource_id()
        if rid != "bi_reporting" and "bi_reporting" in out:
            out[rid] = out.pop("bi_reporting")
    except Exception:
        pass
    return out


def alert_defaults_for(datasource_id: str) -> list[str]:
    sid = (datasource_id or "").strip()
    if not sid:
        return list(_ALERT_GENERIC)
    path = SECRETS / "alert-suggestions.json"
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            specs = (raw.get("sources") or {}).get(sid)
            if isinstance(specs, list) and specs:
                return [str(x) for x in specs if str(x).strip()]
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    packs = _remap_reporting_pack(_ALERT_DEFAULTS)
    return list(packs.get(sid) or _ALERT_GENERIC)


def build_alert_suggestions(
    *,
    datasource_id: str,
    limit: int = 3,
) -> dict[str, Any]:
    from nanobase_api.infrastructure.active_source import prefer_datasource_id

    lim = max(1, min(int(limit or 3), 8))
    sid = prefer_datasource_id(datasource_id)
    texts = alert_defaults_for(sid)[:lim]
    return {
        "datasource_id": sid,
        "suggestions": [{"text": q, "source": "default", "count": 0} for q in texts],
        "ask_prompt": (
            texts[0]
            if texts
            else "Seçili veri kaynağında önemli bir metrik eşiği aşarsa bana bildirim gönder"
        ),
    }
