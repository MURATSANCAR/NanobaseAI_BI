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
    target = getattr(engine, "engine", engine)
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
           fields: Optional[Callable[[P.Kaynaklar, str], dict[str, str]]] = None) -> P.Kaynaklar:
    """Yakalanan okumalardan kayıt: tek hesap (`text`) bütün okumaları girdi alır; cevabın rakam taşıyan her üst
    anahtarı (skip hariç) bu hesaba bağlanır. `extra(k)`: Logo/CRM sorguları ya da dış kaynak hesapları ekler
    (kimlik listesi döndürür). `fields(k, ref)`: daha ince alan eşlemesi (üst anahtarın üstüne yazar)."""
    k = P.Kaynaklar()
    ids = kaydet(k, ran, engine, prefix, title, description=description or "Bu ekran açılırken koşan okuma.")
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
