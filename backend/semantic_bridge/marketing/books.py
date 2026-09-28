"""Planın kitapları (`semantic_mkt_plan_books`): tek plan birden çok kitap taşır (M17 backlist aktivasyonu: set/tema
kampanyası; M18 aylık plan ve M53 set önerisi de okur).

Her satır `plan_id`, `stok_kodu`, `rol` (`ana` kampanyanın kitabı · `set` set/paket bileşeni · `capraz` çapraz satış
adayı), kitabın adı ve sırası. Tablo çekirdeğe `register_plan_table` ile bağlıdır: taslak plan silinince satırları
silinir, «Revize et» yeni sürüme kopyalar. Kitap listesi yalnız taslak ya da geri gönderilmiş planda değişir (çekirdeğin
`editable` kuralı); her değişiklik plan geçmişine yazılır.

Tek kitaplı planda planın `stok_kodu` alanı o kitaptır (M15/M18 ekranları planı kitabıyla gösterir); birden çok kitapta
boş kalır, kitaplar buradan okunur.
"""
from __future__ import annotations

import threading
from typing import Any, Iterable

import sqlalchemy as sa

from semantic_bridge.marketing import core as C

PLAN_BOOKS = sa.Table(
    "semantic_mkt_plan_books", C._md,
    sa.Column("plan_id", sa.String(24), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("rol", sa.String(8), nullable=False),                    # ana | set | capraz
    sa.Column("ad", sa.String(400)),
    sa.Column("sira", sa.Integer, nullable=False, default=0),
    sa.Column("gerekce", sa.Text),                                     # neden bu planda (fırsat bileşenleri, özel gün…)
    sa.Index("ix_semantic_mkt_plan_books_stok", "stok_kodu"),
)
C.register_plan_table(PLAN_BOOKS)

ROLES = {"ana": "Ana kitap", "set": "Set / paket", "capraz": "Çapraz satış"}

_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    C.ensure(engine)
    with _lock:
        if id(engine) in _ready:
            return
        PLAN_BOOKS.create(engine, checkfirst=True)
        _ready.add(id(engine))


def clean(items: Any) -> list[dict[str, Any]]:
    """Gelen kitap listesi: stok kodu zorunlu, aynı kod bir kez (ilk geçen kalır), rol tanınmıyorsa hata."""
    if not isinstance(items, list) or not items:
        raise C.MarketingError("En az bir kitap seçin.")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, x in enumerate(items):
        x = x if isinstance(x, dict) else {"stokKodu": x}
        code = C.one_line(x.get("stokKodu") or x.get("stok_kodu"), 60)
        if not code:
            raise C.MarketingError(f"{i + 1}. kitap: stok kodu boş.")
        rol = str(x.get("rol") or "ana")
        if rol not in ROLES:
            raise C.MarketingError(f"{i + 1}. kitap: rol ana, set ya da capraz olmalı.")
        if code in seen:
            continue
        seen.add(code)
        out.append({"stok_kodu": code, "rol": rol, "ad": C.one_line(x.get("ad"), 400), "gerekce": C.text(x.get("gerekce"), 4000)})
    return out


def _write(c: Any, plan_id: str, rows: list[dict[str, Any]]) -> None:
    c.execute(PLAN_BOOKS.delete().where(PLAN_BOOKS.c.plan_id == plan_id))
    for i, r in enumerate(rows):
        c.execute(PLAN_BOOKS.insert().values(plan_id=plan_id, sira=i, **r))
    single = rows[0]["stok_kodu"] if len(rows) == 1 else None
    c.execute(C.PLANS.update().where(C.PLANS.c.id == plan_id).values(stok_kodu=single))


def put(engine: sa.engine.Engine, tenant: str, user: str, plan_id: str, items: Any, *, system: bool = False) -> list[dict[str, Any]]:
    """Planın kitap listesinin tamamı. `system`: plan açılırken (taslak, kural denetimi aynı)."""
    rows = clean(items)
    with engine.begin() as c:
        r = C._row(c, tenant, plan_id, lock=True)
        C.editable(r)
        old = [x.stok_kodu for x in c.execute(sa.select(PLAN_BOOKS.c.stok_kodu).where(PLAN_BOOKS.c.plan_id == r.id)
                                              .order_by(PLAN_BOOKS.c.sira)).all()]
        _write(c, r.id, rows)
        c.execute(C.PLANS.update().where(C.PLANS.c.id == r.id).values(guncelleyen=user, guncelleme=C.now()))
        C.event(c, r.id, user, "kitaplar" if not system else "kitaplar-acilis", {"kitap": old},
                {"kitap": [x["stok_kodu"] for x in rows], "rol": {x["stok_kodu"]: x["rol"] for x in rows}})
    return of(engine, plan_id)


def of(engine: sa.engine.Engine, plan_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(PLAN_BOOKS).where(PLAN_BOOKS.c.plan_id == plan_id).order_by(PLAN_BOOKS.c.sira)).all()
    return [{"stokKodu": r.stok_kodu, "rol": r.rol, "rolAdi": ROLES.get(r.rol, r.rol), "ad": r.ad, "sira": r.sira,
             "gerekce": r.gerekce} for r in rows]


def by_codes(engine: sa.engine.Engine, tenant: str, codes: Iterable[str] | None = None, *, kind: str = "",
             include_archive: bool = False) -> dict[str, list[dict[str, Any]]]:
    """Stok kodu → kitabın içinde geçtiği planlar (en yeni önce). `codes` boşsa bütün kitaplar."""
    cond = [C.PLANS.c.tenant_id == tenant]
    if kind:
        cond.append(C.PLANS.c.kind == kind)
    if not include_archive:
        cond.append(C.PLANS.c.durum != "arsiv")
    want = [x for x in (codes or []) if x]
    if want:
        cond.append(PLAN_BOOKS.c.stok_kodu.in_(want))
    q = (sa.select(PLAN_BOOKS.c.stok_kodu, PLAN_BOOKS.c.rol, C.PLANS.c.id, C.PLANS.c.kind, C.PLANS.c.durum, C.PLANS.c.baslik,
                   C.PLANS.c.yayin_tarihi, C.PLANS.c.surum)
         .select_from(PLAN_BOOKS.join(C.PLANS, C.PLANS.c.id == PLAN_BOOKS.c.plan_id)).where(*cond)
         .order_by(C.PLANS.c.id.desc()))
    out: dict[str, list[dict[str, Any]]] = {}
    with engine.connect() as c:
        for r in c.execute(q).all():
            out.setdefault(r.stok_kodu, []).append({"id": r.id, "kind": r.kind, "durum": r.durum,
                                                    "durumAdi": C.STATUSES.get(r.durum, r.durum), "baslik": r.baslik,
                                                    "baslangic": r.yayin_tarihi, "rol": r.rol, "surum": r.surum})
    return out
