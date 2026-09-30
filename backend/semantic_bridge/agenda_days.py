"""Kampüs «Önemli Günler & Ajanda»nın herkese aynı olan kısmı: önümüzdeki `days` gündeki özel günler, resmî tatiller
ve çalışma arkadaşlarının doğum günleri. Kişinin kendi fuar/görev/CRM etkinlikleri `events.agenda`'dadır.

- **Özel günler (CRM):** SEO Sezon takviminin gece okuduğu `new_ozelgunlerBase` + kitap bağı, portal tablosu
  `semantic_seo_seasons_days`. Tarih aynı modülün kuralıyla (`seasons.resolve`, `next_occurrence`): sabit gün, hareketli
  gün (hicri ±1 gün, «yaklaşık»), yoksa CRM'deki ISO haftası (pazartesi–pazar). Tarihi bilinmeyen gün listeye girmez.
- **Resmî tatil:** İK izin takviminin tatil tablosu. Aynı adlı özel gün varsa ayrı satır açılmaz, özel gün işaretlenir.
- **Doğum günü:** İK portalı (`hr_portal.birthdays`); alan kapalı ya da hassassa hiç gelmez. Yıl ve yaş gönderilmez.

Kaynaklardan biri okunamazsa o kısım boş döner, ajandanın geri kalanı bozulmaz.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import sqlalchemy as sa

log = logging.getLogger("semantic.agenda_days")


def special_days(engine, tenant: str, now: date, days: int) -> list[dict[str, Any]]:
    from semantic_bridge.seo_geo import seasons as S

    S.ensure_tables(engine)
    until = now + timedelta(days=days)
    with engine.connect() as c:
        rows = c.execute(sa.select(S.DAYS).where(S.DAYS.c.tenant_id == tenant)).mappings().all()
    out = []
    for r in rows:
        how = S.resolve({"name": r["name"], "weekFrom": r["week_from"], "weekTo": r["week_to"], "fixedDate": r["fixed_date"]})
        occ = S.next_occurrence(how, now) if how["method"] != "unknown" else None
        if not occ or occ[0] > until:
            continue
        start, end = occ
        out.append({"kind": "ozelgun", "id": r["day_key"], "title": r["name"], "day": max(start, now).isoformat(),
                    "startsOn": start.isoformat(), "endsOn": end.isoformat(), "daysLeft": max(0, (start - now).days),
                    "precision": how["precision"], "books": int(r["crm_books"] or 0), "fromCrm": r["source"] == "crm"})
    return out


def holidays(engine, tenant: str, now: date, days: int) -> list[dict[str, Any]]:
    from semantic_bridge import hr_leave as HL

    until = (now + timedelta(days=days)).isoformat()
    rows = [h for y in sorted({now.year, (now + timedelta(days=days)).year}) for h in HL.holidays(engine, tenant, y)]
    return [{"kind": "tatil", "id": h["day"], "title": h["name"], "day": h["day"], "startsOn": h["day"], "endsOn": h["day"],
             "daysLeft": (date.fromisoformat(h["day"]) - now).days, "half": h["half"]}
            for h in rows if now.isoformat() <= h["day"] <= until]


def birthdays(engine, tenant: str, now: date, days: int) -> list[dict[str, Any]]:
    from semantic_bridge import hr_portal as HP

    HP.ensure(engine)
    out = []
    for p in HP.birthdays(engine, tenant, now)["items"]:
        if p["inDays"] > days:
            continue
        d = (now + timedelta(days=p["inDays"])).isoformat()
        out.append({"kind": "dogum", "id": p["id"], "title": p["adSoyad"], "day": d, "daysLeft": p["inDays"],
                    "where": p.get("departman")})
    return out


def _fold(s: str) -> str:
    return " ".join((s or "").casefold().replace("ı", "i").split())


def important_days(engine, tenant: str, now: date, days: int) -> dict[str, Any]:
    """{"importantDays": özel gün + resmî tatil (tarih sırasıyla), "birthdays": doğum günleri}."""
    parts: dict[str, list[dict[str, Any]]] = {}
    for key, fn in (("ozel", special_days), ("tatil", holidays), ("dogum", birthdays)):
        try:
            parts[key] = fn(engine, tenant, now, days)
        except Exception as e:  # noqa: BLE001 — bir kaynak yoksa ajandanın geri kalanı gösterilir
            log.info("önemli günler: %s okunamadı: %s", key, e)
            parts[key] = []
    special = parts["ozel"]
    by_name = {_fold(d["title"]): d for d in special}
    merged = list(special)
    for h in parts["tatil"]:
        twin = by_name.get(_fold(h["title"]))
        if twin:  # CRM haftası kaba olabilir; tatilin kesin günü öne geçer
            twin.update(holiday=True, day=h["day"], startsOn=h["day"], endsOn=h["day"], daysLeft=h["daysLeft"],
                        precision="kesin")
        else:
            merged.append(h)
    merged.sort(key=lambda x: (x["day"], 0 if x["kind"] == "tatil" else 1, x["title"]))
    return {"importantDays": merged, "birthdays": sorted(parts["dogum"], key=lambda x: (x["day"], x["title"]))}
