"""M57 salt okunur kaynakları: portal kullanım sayımı (köprü veritabanı) ve Logo eğitim gideri. Hiçbir yere yazılmaz.

**Portal kullanımı** (kabul betiği `scripts/acceptance/M57/` aynı tanımı bağımsız SQL ile sınar):
- Ekran kullanımı = `semantic_hr_page_visits` (gün, menü öğesi, hesap); pencerede en az bir ziyaret = «kullandı».
- Zeki AI soru = `sl_query_log.username` dolu satırlar (`tenant_id` bu kurulum, `created_at` pencere içinde).
- Kayıt işlemleri = `semantic_audit` (`actor`, `kind`, `at` pencere içinde); tür başına ayrı sütun.
- Hesap → birim: `semantic_hr_employees` (etkin, `username` eşleşmesi); kayıtta olmayan hesaplar ayrı satır.
- Çıktıda **hesap adı yoktur**; hücre = o birimde o ekranı kullanan farklı kişi sayısı. Gizlilik eşiği
  (`HR_PRIVACY_MIN_GROUP`) girildiyse etkin çalışanı eşiğin altındaki birimler ve kayıtsız hesaplar tek satırda
  birleşir ve bu ekranda yazar. Eşik girilmemişse birleştirme yapılmaz (sessiz eşik yok), ekran uyarır.
- Soru metinleri hiçbir çıktıya taşınmaz; yalnız sayılar.

**Logo eğitim gideri** (Kural 16 ile aynı ölçü): `LG_{firma}_01_EMFLINE` ⨝ `LG_{firma}_EMUHACC`, `CANCELLED = 0`,
`SUM(DEBIT - CREDIT)`, hesaplar `HR_TRAINING_ACCOUNTS`'taki kodlar ve alt hesapları. Dönem sonu kapanış fişleri
(aynı fişte bir yansıtma hesabının — 7x1 — borç satırı olan fişler) M46 bütçe gideriyle aynı biçimde dışarıda kalır;
yoksa yıl sonu kapanışı gideri sıfırlar. Yıl → firma `L_CAPIPERIOD`'dan (`budget_sources.firms_by_year`).
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge import budget_sources as bsrc
from semantic_bridge import hr_core as H
from semantic_bridge import hr_learning as L

log = logging.getLogger("semantic_bridge.hr.learning.sources")

SourceError = bsrc.SourceError
SMALL = "__kucuk"
UNREGISTERED = "__kayitsiz"
NO_UNIT = "__birimsiz"
ZEKI = "zeki-soru"

#: Değişiklik kaydı türlerinin ekrandaki adı; listede olmayan tür «İşlem: <tür>» diye görünür.
AUDIT_LABELS = {
    "board": "Pano düzenleme", "report": "Planlı rapor", "alert": "Uyarı kuralı", "alert_rule": "Uyarı kuralı",
    "vocabulary": "Sözlük", "access": "Yetki", "contract": "Sözleşme", "category_tree": "Kategori ağacı",
    "tender": "İhale", "social_post": "Sosyal medya", "translation_job": "Çeviri işi", "studio_job": "Kitap tasarım",
    "hr_candidate": "İşe alım", "hr_position": "Pozisyon", "hr_course": "Eğitim kataloğu", "hr_session": "Eğitim oturumu",
}


def _account(u: Any) -> str:
    s = str(u or "").strip().rsplit("\\", 1)[-1].split("@", 1)[0]
    return s.lower()


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def raw_usage(engine: sa.engine.Engine, tenant: str, days: int) -> dict[str, set[str]]:
    """Modül → farklı hesaplar (pencere içinde). Yalnız sayım için; dışarı hesap adı verilmez."""
    L.ensure(engine)
    from semantic_bridge import admin as admin_mod
    from semantic_layer.store.schema import sl_query_log

    since = _since(days)
    day0 = L.today() - timedelta(days=days - 1)
    out: dict[str, set[str]] = {}
    # Her kaynak ayrı bağlantıda: biri okunamazsa (tablo yok) ötekinin işlemi bozulmasın.
    with engine.connect() as c:
        for route, user in c.execute(sa.select(L.PAGE_VISITS.c.route_prefix, L.PAGE_VISITS.c.username).where(
                L.PAGE_VISITS.c.tenant_id == tenant, L.PAGE_VISITS.c.day >= day0).distinct()).all():
            out.setdefault(route, set()).add(_account(user))
    try:
        with engine.connect() as c:
            users = c.execute(sa.select(sl_query_log.c.username).where(
                sl_query_log.c.tenant_id == tenant, sl_query_log.c.username.isnot(None),
                sl_query_log.c.created_at >= since).distinct()).scalars().all()
    except sa.exc.SQLAlchemyError as e:               # soru kaydı tablosu bu veritabanında yoksa
        log.warning("hr.learning: soru kaydı okunamadı: %s", e)
        users = []
    for u in users:
        if _account(u):
            out.setdefault(ZEKI, set()).add(_account(u))
    try:
        with engine.connect() as c:
            rows = c.execute(sa.select(admin_mod.AUDIT.c.actor, admin_mod.AUDIT.c.kind).where(
                admin_mod.AUDIT.c.at >= since).distinct()).all()
    except sa.exc.SQLAlchemyError as e:
        log.warning("hr.learning: değişiklik kaydı okunamadı: %s", e)
        rows = []
    for actor, kind in rows:
        a = _account(actor)
        if a and a not in ("sistem", "eposta"):
            out.setdefault(f"audit:{kind}", set()).add(a)
    return out


def usage_map(engine: sa.engine.Engine, tenant: str, days: int, min_group: Optional[int]) -> dict[str, Any]:
    """Birim × modül: farklı kişi sayısı. Hesap adı içermez."""
    raw = raw_usage(engine, tenant, days)
    with engine.connect() as c:
        emps = c.execute(sa.select(H.EMPLOYEES.c.username, H.EMPLOYEES.c.unit_id).where(
            H.EMPLOYEES.c.tenant_id == tenant, H.EMPLOYEES.c.status == "aktif")).all()
        units = dict(c.execute(sa.select(H.UNITS.c.id, H.UNITS.c.name).where(H.UNITS.c.tenant_id == tenant)).all())
    unit_of = {str(e.username).lower(): (e.unit_id or NO_UNIT) for e in emps if e.username}
    size: dict[str, int] = {}
    for e in emps:
        k = e.unit_id or NO_UNIT
        size[k] = size.get(k, 0) + 1
    small = {u for u, n in size.items() if min_group and n < min_group}

    def row_of(account: str) -> str:
        u = unit_of.get(account)
        if u is None:
            return SMALL if min_group else UNREGISTERED
        return SMALL if u in small else u

    rows: dict[str, dict[str, set[str]]] = {}
    for module, users in raw.items():
        for a in users:
            rows.setdefault(row_of(a), {}).setdefault(module, set()).add(a)
    out_rows = []
    keys = set(rows) | {u for u in size if u not in small}
    if small:
        keys.add(SMALL)
    for k in keys:
        cells = {m: len(v) for m, v in rows.get(k, {}).items()}
        if k == SMALL:
            name = f"{min_group} kişiden küçük birimler ve kayıtsız hesaplar (birleştirildi)"
            people = sum(size[u] for u in small)
        elif k == UNREGISTERED:
            name, people = "Çalışan kaydında olmayan hesaplar", None
        elif k == NO_UNIT:
            name, people = "Birimi girilmemiş çalışanlar", size.get(k, 0)
        else:
            name, people = units.get(k, "Bilinmeyen birim"), size.get(k, 0)
        out_rows.append({"key": k, "unitId": k if not k.startswith("__") else None, "unitName": name,
                         "employees": people, "cells": cells, "merged": k == SMALL})
    out_rows.sort(key=lambda r: (r["key"].startswith("__"), r["unitName"].casefold()))
    modules = sorted(raw)
    return {"days": days, "since": (L.today() - timedelta(days=days - 1)).isoformat(), "minGroup": min_group,
            "modules": [{"key": m, "label": module_label(m)} for m in modules],
            "totals": {m: len(v) for m, v in raw.items()}, "rows": out_rows,
            "smallUnits": len(small), "note": None if min_group else
            "Gizlilik eşiği girilmedi: küçük birimlerde sayı kişiyi ele verebilir (Portal ayarları → İnsan kaynakları)."}


def module_label(key: str) -> Optional[str]:
    """Menü öğeleri ön yüzde menü adıyla adlandırılır (None); Zeki soru ve kayıt türleri burada."""
    if key == ZEKI:
        return "Zeki AI soru"
    if key.startswith("audit:"):
        kind = key[6:]
        return AUDIT_LABELS.get(kind, f"İşlem: {kind}")
    return None


def my_usage(engine: sa.engine.Engine, tenant: str, user: str, days: int) -> dict[str, Any]:
    """Kişinin kendi kullanımı (yalnız kendisine gösterilir): menü öğesi başına ziyaret günü ve sayısı, soru sayısı."""
    L.ensure(engine)
    from semantic_bridge import admin as admin_mod
    from semantic_layer.store.schema import sl_query_log

    u = _account(user)
    day0 = L.today() - timedelta(days=days - 1)
    since = _since(days)
    with engine.connect() as c:
        visits = c.execute(sa.select(L.PAGE_VISITS.c.route_prefix, sa.func.count(), sa.func.sum(L.PAGE_VISITS.c.count)).where(
            L.PAGE_VISITS.c.tenant_id == tenant, L.PAGE_VISITS.c.username == u, L.PAGE_VISITS.c.day >= day0)
            .group_by(L.PAGE_VISITS.c.route_prefix)).all()
    try:
        with engine.connect() as c:
            asked = c.execute(sa.select(sa.func.count()).where(
                sl_query_log.c.tenant_id == tenant, sa.func.lower(sl_query_log.c.username) == u,
                sl_query_log.c.created_at >= since)).scalar() or 0
    except sa.exc.SQLAlchemyError:
        asked = 0
    try:
        with engine.connect() as c:
            acts = c.execute(sa.select(admin_mod.AUDIT.c.kind, sa.func.count()).where(
                sa.func.lower(admin_mod.AUDIT.c.actor) == u, admin_mod.AUDIT.c.at >= since).group_by(admin_mod.AUDIT.c.kind)).all()
    except sa.exc.SQLAlchemyError:
        acts = []
    return {"days": days, "since": day0.isoformat(),
            "screens": [{"key": r[0], "days": int(r[1]), "visits": int(r[2] or 0)} for r in visits],
            "questions": int(asked),
            "actions": [{"key": f"audit:{k}", "label": module_label(f"audit:{k}"), "count": int(n)} for k, n in acts]}


# ------------------------------------------------------------------ Logo eğitim gideri


def _in_accounts(alias: str, accounts: list[str]) -> str:
    parts = []
    for a in accounts:
        if not L._ACCOUNT.match(a):  # noqa: SLF001 — aynı doğrulama; SQL'e yalnız geçerli kod girer
            raise SourceError(f"Geçersiz hesap kodu: {a}")
        parts.append(f"{alias}.CODE = '{a}' OR {alias}.CODE LIKE '{a}.%'")
    return "(" + " OR ".join(parts) + ")"


def spend_sql(firm: str, year: int, accounts: list[str]) -> str:
    """Ay × hesap: Σ(DEBIT − CREDIT), iptal değil, kapanış fişi hariç."""
    close = bsrc._CLOSE  # noqa: SLF001 — M46 ile aynı yansıtma hesapları
    return f"""
SELECT MONTH(F.DATE_) AS ay, A.CODE AS hesap, MAX(A.DEFINITION_) AS hesap_adi, SUM(F.DEBIT - F.CREDIT) AS tutar
FROM dbo.LG_{firm}_01_EMFLINE AS F
JOIN dbo.LG_{firm}_EMUHACC AS A ON A.LOGICALREF = F.ACCOUNTREF
WHERE F.CANCELLED = 0 AND {_in_accounts('A', accounts)}
  AND F.DATE_ >= '{year}-01-01' AND F.DATE_ < '{year + 1}-01-01'
  AND NOT EXISTS (
    SELECT 1 FROM dbo.LG_{firm}_01_EMFLINE AS K
    JOIN dbo.LG_{firm}_EMUHACC AS KA ON KA.LOGICALREF = K.ACCOUNTREF
    WHERE K.ACCFICHEREF = F.ACCFICHEREF AND K.CANCELLED = 0 AND K.SIGN = 0 AND LEFT(KA.CODE, 3) IN {close})
GROUP BY MONTH(F.DATE_), A.CODE""".strip()


def data_end_sql(firm: str) -> str:
    return f"SELECT MAX(DATE_) AS son FROM dbo.LG_{firm}_01_EMFLINE WHERE CANCELLED = 0"


def candidates_sql(firm: str) -> str:
    """Adı eğitim/seminer/kurs geçen 7'li hesaplar: İK ve Mali İşler seçer (ayar `HR_TRAINING_ACCOUNTS`)."""
    like = " OR ".join(f"DEFINITION_ LIKE N'%{w}%'" for w in ("EĞİTİM", "eğitim", "Eğitim", "EGITIM", "Egitim", "egitim",
                                                                  "SEMİNER", "Seminer", "seminer", "SEMINER", "KURS", "Kurs", "kurs"))
    return f"SELECT CODE AS kod, DEFINITION_ AS ad FROM dbo.LG_{firm}_EMUHACC WHERE CODE LIKE '7%' AND ({like}) ORDER BY CODE"


def _timeout() -> int:
    try:
        return int(os.environ.get("HR_LEARNING_QUERY_TIMEOUT_SEC", "300"))
    except ValueError:
        return 300


def read_spend(connection_file: str, year: int, accounts: list[str]) -> dict[str, Any]:
    """Yılın eğitim gideri: toplam, ay ve hesap kırılımı, verinin son tarihi. Hesap ayarı yoksa SourceError değil,
    `configured: False` döner (ekran ayarı ister)."""
    if not accounts:
        return {"year": year, "configured": False, "total": None, "months": [], "accounts": [], "dataEnd": None}
    run = bsrc.runner(connection_file, _timeout())
    firms = bsrc.firms_by_year(run)
    firm = firms.get(year)
    if not firm:
        raise SourceError(f"Logo'da {year} yılının dönemi yok.")
    from semantic_bridge import hr_kaynak

    text = spend_sql(firm, year, accounts)
    rows = run(text)
    hr_kaynak.record("logo", f"Logo muhasebe · eğitim gider hesapları · {year}", text,
                     description="Ay × hesap: borç − alacak; iptal ve dönem sonu kapanış fişleri hariç. Hesaplar ayardan.")
    months: dict[int, float] = {}
    by_acc: dict[str, dict[str, Any]] = {}
    total = 0.0
    for r in rows:
        v = float(r.get("tutar") or 0)
        m = int(r["ay"])
        months[m] = months.get(m, 0.0) + v
        code = str(r.get("hesap") or "").strip()
        a = by_acc.setdefault(code, {"code": code, "name": " ".join(str(r.get("hesap_adi") or "").split()), "amount": 0.0})
        a["amount"] += v
        total += v
    end_rows = run(data_end_sql(firm))
    hr_kaynak.record("logo", "Logo muhasebe veri sonu", data_end_sql(firm), description="Son muhasebe satırının tarihi.")
    end = end_rows[0].get("son") if end_rows else None
    return {"year": year, "configured": True, "firm": firm, "total": round(total, 2),
            "months": [{"month": m, "amount": round(v, 2)} for m, v in sorted(months.items())],
            "accounts": sorted(({**a, "amount": round(a["amount"], 2)} for a in by_acc.values()), key=lambda x: x["code"]),
            "dataEnd": end.date().isoformat() if isinstance(end, datetime) else (end.isoformat() if isinstance(end, date) else None)}


def read_candidates(connection_file: str, year: int) -> list[dict[str, str]]:
    run = bsrc.runner(connection_file, _timeout())
    firms = bsrc.firms_by_year(run)
    firm = firms.get(year) or (firms[max(firms)] if firms else None)
    if not firm:
        raise SourceError("Logo'da dönem bulunamadı.")
    return [{"code": str(r.get("kod") or "").strip(), "name": " ".join(str(r.get("ad") or "").split())}
            for r in run(candidates_sql(firm))]
