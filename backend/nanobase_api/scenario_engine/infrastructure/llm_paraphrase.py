"""Optional LLM paraphrase suggestions with equivalence gate (no SQL/metric mutation)."""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan


def llm_paraphrase_enabled() -> bool:
    return os.environ.get("SCENARIO_LLM_PARAPHRASE", "").lower() in ("1", "true", "yes")


def _slot_fingerprint(plan: LogicalPlan) -> str:
    slots = {
        "family": plan.family,
        "entity": plan.entity,
        "period": plan.period,
        "metric": plan.metric,
        "metricColumn": plan.metric_column,
        "dateRole": plan.date_role,
        "status": plan.status_filter,
        "topN": plan.top_n,
        "dimension": plan.dimension,
        "aggregation": plan.aggregation,
    }
    raw = "|".join(f"{k}={slots[k]}" for k in sorted(slots))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _embedding_sim(a: str, b: str) -> float:
    """Cheap hash-overlap similarity proxy when real embed unavailable."""
    def toks(s: str) -> set[str]:
        return {t for t in re.findall(r"[\wçğıöşü]+", s.lower()) if len(t) > 2}

    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def equivalence_gate(
    original: str,
    candidate: str,
    plan: LogicalPlan,
    *,
    min_sim: float = 0.35,
) -> tuple[bool, dict[str, Any]]:
    """Fail closed if candidate drifts from slot fingerprint or embedding similarity."""
    # Forbidden: candidate must not introduce SQL/metric/dateRole tokens that alter semantics
    forbidden = ("select ", " from ", " where ", "insert ", "update ", "delete ")
    low = candidate.lower()
    if any(f in low for f in forbidden):
        return False, {"reason": "sql_leak"}

    # Metric / dateRole tokens in plan must remain compatible (soft: entity word present)
    entity = (plan.entity or "").lower()
    entity_tr = {
        "invoice": ("fatura", "fatural"),
        "customer": ("müşteri", "musteri", "cari"),
        "payment": ("ödeme", "odeme", "tahsil"),
        "product": ("ürün", "urun"),
        "order": ("sipariş", "siparis"),
    }.get(entity, (entity,))
    if entity_tr and not any(e in low for e in entity_tr):
        return False, {"reason": "entity_mismatch", "fingerprint": _slot_fingerprint(plan)}

    sim = _embedding_sim(original, candidate)
    if sim < min_sim:
        return False, {"reason": "low_similarity", "similarity": sim}
    return True, {"similarity": sim, "fingerprint": _slot_fingerprint(plan)}


def maybe_llm_paraphrases(seed: str, plan: LogicalPlan, *, limit: int = 3) -> list[str]:
    """
    When SCENARIO_LLM_PARAPHRASE=1, ask LLM for paraphrases.
    Only returns candidates that pass equivalence_gate. Never mutates SQL/metric/dateRole.
    """
    if not llm_paraphrase_enabled():
        return []

    url = os.environ.get("SCENARIO_LLM_URL") or os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("SCENARIO_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not url or not api_key:
        # Deterministic pseudo-paraphrases for CI with flag on but no LLM
        candidates = [
            seed.replace("getir", "göster"),
            seed.replace("göster", "listele"),
            seed.replace("nedir?", "kaçtır?"),
        ]
    else:
        candidates = _call_llm(seed, plan, url=url, api_key=api_key, limit=limit)

    out: list[str] = []
    for c in candidates:
        c = (c or "").strip()
        if not c or c == seed:
            continue
        ok, _ = equivalence_gate(seed, c, plan)
        if ok:
            out.append(c)
        if len(out) >= limit:
            break
    return out


def _call_llm(seed: str, plan: LogicalPlan, *, url: str, api_key: str, limit: int) -> list[str]:
    import json
    import urllib.request

    prompt = (
        "Aşağıdaki Türkçe BI sorusunu anlamını bozmadan yeniden yaz. "
        "SQL, metrik adı veya tarih rolü ekleme/değiştirme. "
        f"Entity={plan.entity} family={plan.family} period={plan.period}. "
        f"Soru: {seed}\n"
        f"{limit} alternatif satır olarak döndür."
    )
    payload = {
        "model": os.environ.get("SCENARIO_LLM_MODEL", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": "You only paraphrase Turkish BI questions."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }
    endpoint = url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = endpoint + "/v1/chat/completions"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        lines = [ln.strip(" -•\t") for ln in text.splitlines() if ln.strip()]
        return lines[:limit]
    except Exception:
        return []
