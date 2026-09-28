"""Sorgu izi: bir uç çalışırken portal veritabanında GERÇEKTEN koşan okuma ifadelerini yakalar (sorgu bilgisi için).

Kılavuzun 1. adımı okumayı `<ad>_stmt()`'e ayırmaktır (gösterilen = çalışan). Okumaları katalog deposunun ya da bir
modülün içinde onlarca yere dağılmış uçlarda aynı güvenceyi yeniden yazmadan verir: motorun `before_execute` olayında,
yalnız bu isteğin (ContextVar) koşturduğu SELECT ifadeleri — nesnenin kendisi — toplanır; `kaydet()` her birini
`P.Kaynaklar.portal()` ile değerleri yerinde metne çevirip kaydeder. Metin koşan ifadenin aynısıdır; elle yazılmış
«benzer» sorgu değildir.

    with izle(engine) as ran:
        out = modul.overview(engine, ...)
    ids = kaydet(k, ran, engine, "portal.kategori", "Kategori ağacı özeti")

Yalnız okuma (SELECT) izlenir; yazma ifadeleri kayda girmez. Aynı metin iki kez koştuysa bir kez yazılır.
"""
from __future__ import annotations

import contextvars
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

import sqlalchemy as sa
from sqlalchemy.sql import Select
from sqlalchemy.sql.selectable import CompoundSelect

from semantic_bridge import provenance as P

_REC: contextvars.ContextVar[Optional[list]] = contextvars.ContextVar("sorgu_izi", default=None)
_hooked: set[int] = set()
_lock = threading.Lock()


def _hook(engine: Any) -> None:
    # Sınıf düzeyinde tek dinleyici: bütün SQLAlchemy motorları (portal). Motor verilmese de (uç motoru ancak
    # yetki denetiminden sonra öğreniyorsa) izleme çalışır. Kayıt yalnız ContextVar açıkken tutulur.
    target = sa.engine.Engine
    with _lock:
        if id(target) in _hooked:
            return

        @sa.event.listens_for(target, "before_execute")
        def _before(conn, clauseelement, multiparams, params, execution_options):  # noqa: ANN001
            rec = _REC.get()
            if rec is not None and isinstance(clauseelement, (Select, CompoundSelect)) and not multiparams \
                    and not params:
                rec.append(clauseelement)

        _hooked.add(id(target))


@contextmanager
def izle(engine: Any) -> Iterator[list]:
    """Blok içinde bu motorda koşan SELECT ifadelerini toplar (iç içe kullanımda dıştaki de görür)."""
    _hook(engine)
    outer = _REC.get()
    ran: list = []
    token = _REC.set(ran)
    try:
        yield ran
    finally:
        _REC.reset(token)
        if outer is not None:
            outer.extend(ran)


def kaynak(engine: Any, ran: list, out: Any, *, prefix: str, title: str, text: str, skip: tuple = (),
           extra: Optional[Callable[[P.Kaynaklar], list[str]]] = None, description: str = "",
           fields: Optional[Callable[[P.Kaynaklar, str], dict[str, str]]] = None,
           origin: Optional[Callable[[P.Kaynaklar], list[str]]] = None) -> P.Kaynaklar:
    """Yakalanan okumalardan kayıt: tek hesap (`text`) bütün okumaları girdi alır; cevabın rakam taşıyan her üst
    anahtarı (skip hariç) bu hesaba bağlanır. `extra(k)`: Logo/CRM sorguları ya da dış kaynak hesapları ekler
    (kimlik listesi döndürür). `origin(k)`: portal tablosunu dolduran asıl sorgular — portal okumalarının kökeni
    olarak yazılır (önbellekten gelen rakamın asıl SQL'i). `fields(k, ref)`: daha ince alan eşlemesi."""
    k = P.Kaynaklar()
    org = [i for i in (origin(k) if origin is not None else []) if i and not i.startswith("hesap:")]
    org_hesap = [i for i in (list(k.formulas) if origin is not None else [])]
    ids = kaydet(k, ran, engine, prefix, title, description=description or "Bu ekran açılırken koşan okuma.",
                 origin=tuple(org))
    ids += [f"hesap:{n}" for n in org_hesap]
    if not ran and org:
        ids += org
    if extra is not None:
        ids += [i for i in extra(k) if i]
    if not ids:
        raise P.ProvenanceError("Bu ekranın okuması yakalanamadı.")
    ref = k.hesap(prefix, text, ids)
    # Ekranın genel «i»si için anahtar (başlık/sekme yanındaki tek düğme): `<SqlInfo alan="_hepsi">`.
    k.alan("_hepsi", ref)
    skipped = set(skip)
    if isinstance(out, dict):
        k.alanlar({key: ref for key, v in out.items() if key not in skipped and P.numeric_paths({key: v})})
    if fields is not None:
        k.alanlar(fields(k, ref))
    return k


def izli(engine: Any, fn: Callable[[], Any], **kw: Any) -> Any:
    """`fn()`'i izleyerek koşturur ve cevabına sorgu bilgisini ekler (`kaynak()` anahtarlarıyla). Kayıt kurulamazsa
    rakamlar yine döner, pencere nedeni yazar (`P.bagla`)."""
    with izle(engine) as ran:
        out = fn()
    if not isinstance(out, dict):
        return out
    return P.bagla(out, lambda: kaynak(engine, ran, out, **kw))


# ------------------------------------------------------------------ Logo / CRM okumaları (dış bağlantı)

_EXT: contextvars.ContextVar[Optional[list]] = contextvars.ContextVar("sorgu_izi_dis", default=None)


@contextmanager
def izle_dis() -> Iterator[list]:
    """Blok içinde Logo/CRM'de koşan metinleri toplar (okuyan fonksiyon `dis()` ile bildirir)."""
    outer = _EXT.get()
    got: list = []
    token = _EXT.set(got)
    try:
        yield got
    finally:
        _EXT.reset(token)
        if outer is not None:
            outer.extend(got)


def dis(connection: str, sql: str, *, rows: Optional[int] = None, ms: Optional[int] = None) -> None:
    """Okuyan fonksiyon koşturduğu metni bildirir (izleme yoksa hiçbir şey yapmaz; okuma yolunu yavaşlatmaz)."""
    rec = _EXT.get()
    if rec is not None and sql:
        import time as _t

        rec.append({"connection": connection, "sql": sql, "rows": rows, "ms": ms, "at": _t.time()})


def dis_kaydet(k: P.Kaynaklar, got: list, prefix: str, title: str, logo_db: Optional[str], crm_db: Optional[str],
               *, description: str = "") -> list[str]:
    """Yakalanan Logo/CRM metinlerini kayda yazar (aynı metin bir kez; satır ve süre ilk koşunun)."""
    seen: dict[tuple, str] = {}
    ids: list[str] = []
    for x in got:
        key = (x["connection"], x["sql"])
        if key in seen:
            continue
        sid = f"{prefix}.{len(seen) + 1}"
        seen[key] = sid
        conn = "crm" if x["connection"] == "crm" else "logo"
        ids.append(k.sorgu(sid, f"{title} · {'CRM' if conn == 'crm' else 'Logo'}", conn, x["sql"],
                           database=crm_db if conn == "crm" else logo_db, rows=x.get("rows"), ms=x.get("ms"),
                           ran_at=x.get("at"), description=description or "Bu ekran açılırken koşan okuma."))
    return ids


def tam_kaynak(engine: Any, ran: list, got: list, out: Any, *, prefix: str, title: str, text: str,
               logo_db: Optional[str], crm_db: Optional[str], skip: tuple = (), dis_adi: Optional[str] = None,
               onceki: Optional[list] = None) -> P.Kaynaklar:
    """Uçta koşan portal okumaları (`ran`) + Logo/CRM metinleri (`got`, `onceki`: önbellek kaydından gelen, onu
    dolduran asıl okumalar) + gerekirse SQL'siz kaynağın adı (`dis_adi`) → tek hesap; cevabın rakam taşıyan her üst
    anahtarı ve `_hepsi` bu hesaba bağlanır."""
    k = P.Kaynaklar()
    ids = kaydet(k, ran, engine, prefix, title, description="Bu ekran açılırken koşan okuma.") if engine is not None else []
    ids += dis_kaydet(k, got, f"{prefix}.kaynak", title, logo_db, crm_db)
    if onceki:
        ids += dis_kaydet(k, onceki, f"{prefix}.onbellek", f"{title} (önbelleği dolduran)", logo_db, crm_db,
                          description="Önbellekteki özeti dolduran okuma; satır, süre ve zaman o okumanındır.")
    if dis_adi:
        ids.append(k.hesap(f"{prefix}.dis", "SQL'i olmayan kaynak.", dis=dis_adi))
    if not ids:
        raise P.ProvenanceError("Bu ekranın okuması yakalanamadı.")
    ref = k.hesap(prefix, text, ids)
    k.alan("_hepsi", ref)
    skipped = set(skip)
    if isinstance(out, dict):
        k.alanlar({key: ref for key, v in out.items() if key not in skipped and P.numeric_paths({key: v})})
    return k


def izlenir(prefix: str, title: str, text: str, *, engine: Callable[[], Any], dbs: Callable[[], tuple],
            skip: tuple = (), dis_adi: Optional[str] = None, onceki: Optional[Callable[[Any], list]] = None,
            key: str = "kaynaklar"):
    """Uç süsleyicisi (`@app.get` altına): uç koşarken portal ve Logo/CRM okumalarını yakalar, cevaba sorgu bilgisini
    ekler. `onceki(out)`: cevabın önbellek kaydındaki asıl okumalar. Kayıt kurulamazsa rakamlar yine döner."""
    import functools
    import inspect

    def build(out: Any, ran: list, got: list) -> Any:
        if not isinstance(out, dict):
            return out

        def make() -> P.Kaynaklar:
            eng = engine() if engine is not None else None
            return tam_kaynak(eng, ran if eng is not None else [], got, out, prefix=prefix, title=title, text=text, logo_db=dbs()[0],
                              crm_db=dbs()[1], skip=skip, dis_adi=dis_adi, onceki=onceki(out) if onceki else None)
        if key == "kaynaklar":
            return P.bagla(out, make)
        try:
            out[key] = make().to_dict()
        except Exception:  # noqa: BLE001
            out[key] = {"sources": {}, "formulas": {}, "fields": {},
                        "error": "Bu ekranın sorgu bilgisi hazırlanamadı; rakamlar etkilenmedi."}
        return out

    def deco(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrapper(*a, **kw):
                with izle_dis() as got, izle(engine() if engine is not None else None) as ran:
                    out = await fn(*a, **kw)
                return build(out, ran, got)
            return awrapper

        @functools.wraps(fn)
        def wrapper(*a, **kw):
            with izle_dis() as got, izle(engine() if engine is not None else None) as ran:
                out = fn(*a, **kw)
            return build(out, ran, got)
        return wrapper
    return deco


def kaydet(k: P.Kaynaklar, ran: list, engine: Any, prefix: str, title: str, *, description: str = "",
           origin: tuple = (), limit_chars: Optional[int] = None) -> list[str]:
    """Yakalanan ifadeleri kayda yazar; kimlikleri döndürür (`prefix.1`, `prefix.2`, …). Aynı metin bir kez."""
    seen: dict[str, str] = {}
    ids: list[str] = []
    for stmt in ran:
        try:
            text = P.portal_sql(stmt, engine)
        except Exception:  # noqa: BLE001 — metne çevrilemeyen ifade (ör. bağlı olmayan tür) kayda yazılamaz
            continue
        if limit_chars and len(text) > limit_chars:
            continue
        if text in seen:
            continue
        sid = f"{prefix}.{len(seen) + 1}"
        seen[text] = sid
        tables = sorted({t.name for t in getattr(stmt, "get_final_froms", lambda: [])() if hasattr(t, "name")})
        ids.append(k.portal(sid, f"{title}{' · ' + ', '.join(tables) if tables else ''}", text, engine,
                            description=description, origin=origin))
    return ids
