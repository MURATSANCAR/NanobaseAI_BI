"""Datasource-scoped chat suggestions: defaults + learned popular questions."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.engine import Engine

from nanobase_api.infrastructure.conversation_repo import ConversationRepository

# First-boot / cold-start defaults per datasource (admin seed).
# Learned questions from bi_query_plans / chat history override these over time.
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
        "Aylık fatura adedini grafik olarak göster",
        "Satış siparişlerinin toplam sayısı nedir?",
        "İllere göre fatura dağılımını göster",
        "Stok bakiyesi satır sayısı kaç?",
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


def _norm(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip().lower())
    return s[:240]


def defaults_for(datasource_id: str) -> list[str]:
    sid = (datasource_id or "").strip().lower()
    return list(_DEFAULTS.get(sid) or _GENERIC)


def build_suggestions(
    *,
    engine: Engine,
    tenant_id: str,
    datasource_id: str,
    limit: int = 6,
) -> dict[str, Any]:
    lim = max(1, min(int(limit or 6), 12))
    sid = (datasource_id or "bi_reporting").strip() or "bi_reporting"
    defaults = defaults_for(sid)
    repo = ConversationRepository(engine)
    learned = repo.top_user_questions(
        tenant_id=tenant_id,
        datasource_id=sid,
        limit=lim * 2,
    )

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in learned:
        q = str(item.get("question") or "").strip()
        n = _norm(q)
        if len(n) < 6 or n in seen:
            continue
        seen.add(n)
        out.append(
            {
                "text": q,
                "source": "learned",
                "count": int(item.get("count") or 1),
            }
        )
        if len(out) >= lim:
            break

    for q in defaults:
        n = _norm(q)
        if n in seen:
            continue
        seen.add(n)
        out.append({"text": q, "source": "default", "count": 0})
        if len(out) >= lim:
            break

    return {
        "datasource_id": sid,
        "suggestions": out,
        "learned_count": sum(1 for s in out if s["source"] == "learned"),
        "default_count": sum(1 for s in out if s["source"] == "default"),
    }
