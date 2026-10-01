"""CRM'de pasif kayıt hiçbir ekrana gelmez (kullanıcı kararı 2026-09-29).

Dynamics CRM her kaydı silmek yerine pasife alır (`statecode = 1`). Köprünün CRM okuyan onlarca modülü
her tabloya `statecode = 0` yazmayı tek tek hatırlamak zorunda kalırsa biri unutur; ölçümde 65 modülden
bir kısmı ana tabloyu süzüp bağlandığı tabloları (kişi, firma, kitap) süzmüyordu. Bu yüzden süzgeç
bağlantının kendisindedir: CRM bağlantısından geçen her SELECT'te etkin/pasif ayrımı olan tablo,
`(SELECT * FROM <tablo> WHERE statecode = 0) <takma ad>` olarak okunur.

Hangi tablo: CRM veritabanında `statecode` kolonu olan `new_*` tabloları ile `ContactBase` ve
`AccountBase`. 2026-09-29 canlı ölçümü (.28 Timas_MSCRM): `new_*` tablolarının hepsinde durum yalnız
0 (etkin) / 1 (pasif), özel etkinlik (açık/tamamlandı durumlu) tablo yok. Standart varlıkların
çoğunda (fırsat, sipariş, fatura, vaka, etkinlik) durum etkin/pasif değil süreç aşamasıdır
(kazanıldı, tamamlandı, çözüldü); onlar süzülmez. Kullanıcı hesabı (`SystemUserBase`) de süzülmez:
kapalı hesap geçmiş kayıttaki editörün adıdır, ayrıca `IsDisabled` ile gösterilir.

Etkin kayıtta durum nedeni «Pasif» (2026-09-29): CRM'de bazı kayıtlar `statecode = 0` (etkin) iken durum nedeni
(`statuscode`) «Pasif» taşıyor (ör. eski yüklemeden gelen kitap kartları: aramada «Pasif» etiketiyle görünüyordu).
Kullanıcı kuralı: pasif olan hiçbir yerde gelmez. Tablo başına etiketi «Pasif…» ya da «Inactive…» olan durum nedenleri
(`StringMapBase`, bütün diller) bir kez okunur; süzgeç `statuscode NOT IN (…)` da ekler. Okunamazsa yalnız `statecode`.

Sorgu metni yeniden yazılmaz; yalnız tablo başvurusunun karakter aralığı değiştirilir (sqlglot
tanıtıcı konumları). Ayrıştırılamayan sorgu olduğu gibi gider ve günlüğe yazılır.

Kapatmak için: `CRM_ACTIVE_ONLY=0`.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from functools import lru_cache
from typing import Any, Optional

log = logging.getLogger(__name__)

#: `new_*` dışında süzülen standart varlıklar (durumları yalnız etkin/pasif).
STANDARD = ("ContactBase", "AccountBase")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RETRY_SEC = 300


def enabled() -> bool:
    return os.environ.get("CRM_ACTIVE_ONLY", "1").strip().lower() not in ("0", "false", "hayir", "off")


def is_crm_database(database: Any) -> bool:
    """Dynamics CRM veritabanları `<kurum>_MSCRM` adını taşır."""
    return str(database or "").strip().upper().endswith("_MSCRM")


def candidate(name: str) -> bool:
    n = (name or "").strip("[]")
    return n.lower().startswith("new_") and n.lower().endswith("base") or n in STANDARD


def tables_sql(database: str) -> str:
    if not _NAME.match(database or ""):
        raise ValueError(f"veritabanı adı geçerli değil: {database!r}")
    names = ", ".join(f"'{n}'" for n in STANDARD)
    return (
        f"SELECT t.name FROM [{database}].sys.tables t"
        f" WHERE (t.name LIKE 'new[_]%Base' OR t.name IN ({names}))"
        f" AND EXISTS (SELECT 1 FROM [{database}].sys.columns c WHERE c.object_id = t.object_id AND c.name = 'statecode')"
    )


def passive_sql(database: str) -> str:
    """Tablo (varlık adı, küçük harf) başına pasif anlamlı durum nedeni kodları. Temel tablo = varlık adı + «Base»."""
    if not _NAME.match(database or ""):
        raise ValueError(f"veritabanı adı geçerli değil: {database!r}")
    return (
        f"SELECT DISTINCT LOWER(e.Name) AS ent, sm.AttributeValue AS code FROM [{database}].dbo.StringMapBase sm"
        f" JOIN [{database}].dbo.EntityView e ON e.ObjectTypeCode = sm.ObjectTypeCode"
        f" WHERE sm.AttributeName = 'statuscode'"
        f" AND (LTRIM(sm.Value) LIKE N'Pasif%' OR LTRIM(sm.Value) LIKE N'Inactive%')"
    )


def passive_codes(rows: Any) -> dict[str, tuple[int, ...]]:
    """`passive_sql` satırları → {«new_kitapbase»: (2, …)}."""
    out: dict[str, set[int]] = {}
    for r in rows or []:
        ent, code = str(r.get("ent") or "").strip().lower(), r.get("code")
        if not ent or code is None:
            continue
        try:
            out.setdefault(f"{ent}base", set()).add(int(code))
        except (TypeError, ValueError):
            continue
    return {k: tuple(sorted(v)) for k, v in out.items()}


def predicate(table: str, alias: Optional[str], passive: dict) -> str:
    """Tek pasif kuralı metni: `statecode = 0` ve durum nedeni «Pasif…/Inactive…» değil. Sarmal bunu alt sorguya,
    sorgusunu kendisi yazan motorlar (finans motoru) doğrudan kendi WHERE/ON koşuluna koyar."""
    p = f"{alias}." if alias else ""
    codes = passive.get(table.lower()) or ()
    if not codes:
        return f"{p}statecode = 0"
    return f"{p}statecode = 0 AND ({p}statuscode IS NULL OR {p}statuscode NOT IN ({', '.join(str(c) for c in codes)}))"


def _where(table: str, passive: dict) -> str:
    return predicate(table, None, passive)


def missing(sql: str, eligible: set[str] | frozenset, passive: Optional[dict] = None) -> list[str]:
    """Sorguyu yeniden yazmadan denetler: süzülmesi gereken her tablo başvurusunun kendi kapsamında (FROM için
    WHERE, JOIN için ON — LEFT hedefi dahil) `<takma ad>.statecode = 0` VE-koşulu, pasif durum nedeni olan tabloda
    ayrıca `<takma ad>.statuscode` koşulu var mı. Eksik başvurular «tablo takma_ad» listesi olarak döner;
    ayrıştırılamayan sorgu eksik sayılır (denetimden kaçamaz)."""
    import sqlglot
    from sqlglot import exp

    passive = passive or {}
    try:
        trees = [t for t in sqlglot.parse(sql, read="tsql") if t is not None]
    except Exception as e:  # noqa: BLE001 — denetlenemeyen sorgu geçmez
        return [f"ayrıştırılamadı: {str(e)[:80]}"]

    def parts(node: Any) -> list:
        while isinstance(node, exp.Paren):
            node = node.this
        if isinstance(node, exp.And):
            return parts(node.left) + parts(node.right)
        return [node]

    def column(node: Any, alias: str, name: str) -> bool:
        return isinstance(node, exp.Column) and node.name.lower() == name and (node.table or "").lower() == alias

    def zero(node: Any) -> bool:
        return isinstance(node, exp.Literal) and not node.is_string and node.this.strip() == "0"

    out: list[str] = []
    for tree in trees:
        for tb in tree.find_all(exp.Table):
            name = tb.name.lower()
            if name not in eligible:
                continue
            alias = (tb.alias or tb.name).lower()
            parent, scope = tb.parent, None
            if isinstance(parent, exp.Join):
                scope = parent.args.get("on")
            elif isinstance(parent, exp.From) and parent.parent is not None:
                where = parent.parent.args.get("where")
                scope = where.this if where is not None else None
            conj = parts(scope) if scope is not None else []
            state = any(isinstance(c, exp.EQ) and ((column(c.left, alias, "statecode") and zero(c.right))
                                                   or (column(c.right, alias, "statecode") and zero(c.left))) for c in conj)
            status = not passive.get(name) or any(column(x, alias, "statuscode") for c in conj for x in c.find_all(exp.Column))
            if not (state and status):
                out.append(f"{tb.name} {alias}")
    return out


def _span(tb: Any) -> Optional[tuple[int, int, int, str]]:
    """Tablo başvurusunun metindeki yeri: başlangıç, tablo adının sonu, takma adın sonu (dahil) ve takma ad.
    Takma ad yoksa tablo adı takma ad olur; `new_kitapBase.kolon` gibi nitelenmiş kolonlar çalışmaya devam eder."""
    parts = [tb.args.get(k) for k in ("catalog", "db", "this")]
    metas = [p.meta for p in parts if p is not None and getattr(p, "meta", None)]
    if not metas or any("start" not in m or "end" not in m for m in metas):
        return None
    start, name_end = min(m["start"] for m in metas), max(m["end"] for m in metas)
    alias = tb.args.get("alias")
    if alias is None or alias.this is None:
        return start, name_end, name_end, tb.name
    am = getattr(alias.this, "meta", None) or {}
    if "end" not in am:
        return None
    return start, name_end, am["end"], alias.this.name


@lru_cache(maxsize=4096)
def _rewrite(sql: str, eligible: frozenset, passive_items: tuple = ()) -> str:
    passive = dict(passive_items)
    import sqlglot
    from sqlglot import exp

    try:
        trees = [t for t in sqlglot.parse(sql, read="tsql") if t is not None]
    except Exception as e:  # noqa: BLE001 — ayrıştırılamayan sorgu olduğu gibi gider
        log.warning("CRM etkin kayıt süzgeci sorguyu ayrıştıramadı, süzgeçsiz gidiyor: %s", str(e)[:200])
        return sql
    cuts: list[tuple[int, int, str]] = []
    for tree in trees:
        if tree.find(exp.Insert, exp.Update, exp.Delete, exp.Merge):
            return sql
        for tb in tree.find_all(exp.Table):
            if not isinstance(tb.parent, (exp.From, exp.Join)) or tb.name.lower() not in eligible:
                continue
            if tb.args.get("hints") or tb.args.get("joins") or tb.args.get("pivots"):
                continue
            span = _span(tb)
            if span is None:
                log.warning("CRM etkin kayıt süzgeci %s tablosunun yerini bulamadı; süzgeçsiz", tb.name)
                continue
            start, name_end, end, alias = span
            cuts.append((start, end, f"(SELECT * FROM {sql[start:name_end + 1]} WHERE {_where(tb.name, passive)}) {_quote(alias)}"))
    if not cuts:
        return sql
    out = sql
    for start, end, text in sorted(cuts, reverse=True):
        out = out[:start] + text + out[end + 1:]
    return out


def _quote(name: str) -> str:
    return name if _NAME.match(name) else f"[{name.replace(']', ']]')}]"


def rewrite(sql: str, eligible: set[str] | frozenset, passive: Optional[dict] = None) -> str:
    """`eligible`: küçük harfli tablo adları; `passive`: tablo → pasif durum nedeni kodları (`passive_codes`).
    Uygun tablo geçmiyorsa sorgu hiç ayrıştırılmaz."""
    if not sql or not eligible or not enabled():
        return sql
    low = sql.lower()
    if not any(t in low for t in eligible):
        return sql
    return _rewrite(sql, frozenset(eligible), tuple(sorted((passive or {}).items())))


class ActiveOnly:
    """CRM bağlayıcısının sarmalı: `execute`, `batches` ve `dry_run` etkin kayıt süzgecinden geçer;
    geri kalan her şey (profil çıkarma, satır sayımı, örnek satır) asıl bağlayıcıya aynen gider."""

    def __init__(self, inner: Any, database: str):
        self._inner = inner
        self._database = database
        self._eligible: Optional[frozenset] = None
        self._passive: dict[str, tuple[int, ...]] = {}
        self._failed_at = 0.0
        self._lock = threading.Lock()

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)

    @property
    def inner(self) -> Any:
        return self._inner

    def eligible(self) -> frozenset:
        if self._eligible is not None:
            return self._eligible
        with self._lock:
            if self._eligible is not None:
                return self._eligible
            if self._failed_at and time.monotonic() - self._failed_at < _RETRY_SEC:
                return frozenset()
            try:
                _, rows, _ = self._inner.execute(tables_sql(self._database), 100000)
                eligible = frozenset(str(r.get("name") or "").lower() for r in rows if r.get("name"))
                try:
                    _, prow, _ = self._inner.execute(passive_sql(self._database), 100000)
                    self._passive = {k: v for k, v in passive_codes(prow).items() if k in eligible}
                except Exception as e:  # noqa: BLE001 — durum nedeni okunamazsa yalnız statecode süzülür
                    log.warning("CRM pasif durum nedenleri okunamadı, yalnız statecode süzülüyor: %s", str(e)[:200])
                self._eligible = eligible
                log.info("CRM etkin kayıt süzgeci: %d tablo, %d tabloda pasif durum nedeni", len(eligible), len(self._passive))
            except Exception as e:  # noqa: BLE001 — süzgeç kurulamazsa okuma durmaz, günlüğe yazılır
                self._failed_at = time.monotonic()
                log.warning("CRM etkin kayıt süzgecinin tablo listesi okunamadı: %s", str(e)[:200])
                return frozenset()
        return self._eligible

    def _sql(self, sql: str) -> str:
        return rewrite(sql, self.eligible(), self._passive) if enabled() else sql

    def execute(self, sql: str, limit: int):
        return self._inner.execute(self._sql(sql), limit)

    def batches(self, sql: str, *a: Any, **kw: Any):
        return self._inner.batches(self._sql(sql), *a, **kw)

    def dry_run(self, sql: str) -> None:
        return self._inner.dry_run(self._sql(sql))


def wrap(connector: Any, database: Any) -> Any:
    if isinstance(connector, ActiveOnly) or not is_crm_database(database):
        return connector
    return ActiveOnly(connector, str(database))

