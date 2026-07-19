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

# Threshold-alert chips (Alerts page) — scoped to datasource / project.
_ALERT_DEFAULTS: dict[str, list[str]] = {
    "sigorta": [
        "Açık hasar talebi sayısı bir sınırı aşarsa bana e-posta gönder",
        "Günlük yeni poliçe adedi hedefin altına düşerse bana e-posta gönder",
        "Reddedilen hasar oranı kritik eşiğin üstüne çıkarsa bana e-posta gönder",
    ],
    "erp": [
        "Günlük fatura tutarı bir sınırın altına düşerse bana e-posta gönder",
        "Stok bakiyesi kritik seviyenin altına düşerse bana e-posta gönder",
        "Açık satış siparişi sayısı bir eşiği aşarsa bana e-posta gönder",
    ],
    "bi_reporting": [
        "Günlük sipariş adedi bir sınırın altına düşerse bana e-posta gönder",
        "Fatura brüt tutarı bir eşiği aşarsa bana e-posta gönder",
        "Aktif müşteri sayısı beklenenin altına düşerse bana e-posta gönder",
    ],
}

_ALERT_GENERIC = [
    "Önemli bir metrik bir sınırın altına düşerse bana e-posta gönder",
    "Kritik bir gösterge eşiği aşarsa bana e-posta gönder",
    "Günlük kayıt adedi beklenenin altına düşerse bana e-posta gönder",
]


def _norm(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip().lower())
    return s[:240]


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
            else "Seçili veri kaynağında önemli bir metrik eşiği aşarsa e-posta uyarısı oluştur"
        ),
    }
