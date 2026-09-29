"""Tablo kurulumunun sürüm damgası: `ensure` her açılışta veritabanına sormaz.

Köprünün ~100 modülü kendi tablolarını ilk istekte `create_all(checkfirst=True)` ile kurar; bu, tablo ve dizin
başına bir katalog sorgusu, kolon ekleyen modüllerde ayrıca kolon listesi okuması demektir. Test sunucusunda köprü
günde onlarca kez yeniden başlar ve her seferinde her modülün ilk isteği bu turu yeniden öder — tablolar zaten
kurulu olduğu hâlde.

Damga: kurulumun tanımı (tabloların CREATE TABLE + CREATE INDEX metni, bu veritabanının diliyle) özetlenir ve
kurulum başarıyla bittiğinde `sl_schema_stamp` tablosuna yazılır. Sonraki açılışta aynı özet kayıtlıysa kurulum
atlanır; tabloya kolon ya da dizin eklenince özet değişir ve kurulum (kolon ekleme adımıyla birlikte) bir kez daha
koşar. Bütün damgalar süreç başına tek sorguyla okunur.

SQLite'ta (testler, yerel CLI) damga kullanılmaz: her seferinde kurulur. `SCHEMA_STAMP=0` damgayı kapatır;
`sl_schema_stamp`'tan satır silmek o kurulumu bir sonraki açılışta yeniden koşturur.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa
from sqlalchemy.schema import CreateIndex, CreateTable

log = logging.getLogger("semantic_layer.schema_stamp")

_md = sa.MetaData()
STAMPS = sa.Table(
    "sl_schema_stamp", _md,
    sa.Column("name", sa.Text(), primary_key=True),          # kurulumun adı (tablo adları ya da modülün verdiği ad)
    sa.Column("stamp", sa.String(64), nullable=False),        # kurulum tanımının özeti
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
)

_lock = threading.Lock()
#: id(engine) → {ad: damga}; None = bu veritabanında damga okunamadı (her kurulum eskisi gibi koşar).
_known: dict[int, Optional[dict[str, str]]] = {}
#: Bu süreçte damgası doğrulanmış kurulumlar: (id(engine), ad, extra, tablo kimlikleri).
_done: set[tuple[Any, ...]] = set()


def enabled(engine: Any) -> bool:
    if os.environ.get("SCHEMA_STAMP", "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    if not isinstance(engine, sa.engine.Engine):
        return False                      # bağlantı ya da sahte nesne: eskisi gibi
    if engine.dialect.name == "sqlite":
        return os.environ.get("SCHEMA_STAMP_SQLITE", "").strip() == "1"
    return True


def _ddl(table: sa.Table, dialect: Any) -> str:
    try:
        parts = [str(CreateTable(table).compile(dialect=dialect))]
        parts += sorted(str(CreateIndex(ix).compile(dialect=dialect)) for ix in table.indexes)
        return "\n".join(parts)
    except Exception:  # noqa: BLE001 — derlenemeyen tip: tanım yine de ad + kolonlarla özetlenir
        cols = ",".join(f"{c.name}:{type(c.type).__name__}:{c.nullable}:{c.primary_key}" for c in table.columns)
        return f"{table.name}({cols})"


def fingerprint(tables: Iterable[sa.Table], dialect: Any, extra: str = "") -> str:
    h = hashlib.sha256(extra.encode())
    for t in sorted(tables, key=lambda t: t.name):
        h.update(b"\0")
        h.update(_ddl(t, dialect).encode())
    return h.hexdigest()[:32]


def _stamps(engine: sa.engine.Engine) -> Optional[dict[str, str]]:
    key = id(engine)
    if key in _known:
        return _known[key]
    with _lock:
        if key in _known:
            return _known[key]
        try:
            STAMPS.create(engine, checkfirst=True)
            with engine.connect() as c:
                rows = {str(n): str(s) for n, s in c.execute(sa.select(STAMPS.c.name, STAMPS.c.stamp))}
        except Exception as e:  # noqa: BLE001 — damga okunamıyorsa kurulumlar her açılışta koşar
            log.warning("schema stamp: damgalar okunamadı, kurulumlar eskisi gibi koşacak: %s", e)
            rows = None
        _known[key] = rows
        return rows


def _write(engine: sa.engine.Engine, name: str, stamp: str) -> None:
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as c:
            done = c.execute(sa.update(STAMPS).where(STAMPS.c.name == name).values(stamp=stamp, at=now)).rowcount
            if not done:
                c.execute(sa.insert(STAMPS).values(name=name, stamp=stamp, at=now))
    except Exception as e:  # noqa: BLE001 — yarışta başka süreç yazmış olabilir; bir sonraki açılış yeniden dener
        log.info("schema stamp: %s yazılamadı: %s", name, e)
        return
    known = _known.get(id(engine))
    if known is not None:
        known[name] = stamp


def run(engine: Any, tables: Iterable[sa.Table], install: Callable[[], Any], *, name: Optional[str] = None,
        extra: str = "") -> bool:
    """`install()` yalnız bu tabloların tanımı son başarılı kurulumdan beri değiştiyse koşar. Döner: koştu mu.

    `extra`: tanımda görünmeyen ama kurulumu değiştiren bir şey (ör. kolon ekleme adımının sürümü)."""
    tables = list(tables)
    if not enabled(engine):
        install()
        return True
    key = name or ",".join(sorted(t.name for t in tables))
    seen = (id(engine), key, extra, tuple(id(t) for t in tables))
    if seen in _done:                     # bu süreçte zaten doğrulandı (sık çağrılan yollar DDL derlemez)
        return False
    stamp = fingerprint(tables, engine.dialect, extra)
    known = _stamps(engine)
    if known is not None and known.get(key) == stamp:
        _done.add(seen)
        return False
    install()
    if known is not None:
        _write(engine, key, stamp)
        _done.add(seen)
    return True


def create_all(metadata: sa.MetaData, engine: Any, *, tables: Optional[list[sa.Table]] = None) -> bool:
    """`metadata.create_all(engine, checkfirst=True)` — damgası güncelse hiç sormadan geçer."""
    chosen = list(tables) if tables is not None else list(metadata.sorted_tables)
    return run(engine, chosen, lambda: metadata.create_all(engine, tables=tables, checkfirst=True))


def forget(engine: Any = None) -> None:
    """Süreç içindeki damga belleğini boşaltır (testler)."""
    with _lock:
        if engine is None:
            _known.clear()
            _done.clear()
        else:
            _known.pop(id(engine), None)
            for k in [k for k in _done if k[0] == id(engine)]:
                _done.discard(k)
