"""Sorgu bilgisi için yakalama: bir uç çağrısında GERÇEKTEN çalışan SQL'i kaydeder (G5 yayılımı, 2026-09-28).

Ortak sözleşme `provenance.py`; kılavuz `docs/analiz/sorgu-bilgisi-kilavuz.md`. Kılavuzdaki «okumayı `*_stmt()`'e ayır»
adımının amacı gösterilen SQL'in çalışan SQL olmasıdır. Onlarca uç ve yüzlerce okuma olan modüllerde (e-ticaret,
kampanya, kanallar, pazar yerleri, SEO & GEO) aynı güvenceyi yakalama verir: uç çalışırken portal veritabanına giden her
`SELECT` sürücü düzeyinde (değerleriyle) ve Logo/CRM'e giden her sorgu metni (sorgu çalıştırıcısı sarılarak) kaydedilir;
kaynak kaydına elle yazılmış «benzer» SQL değil, o istekte koşan metin girer. Satır sayısı ve süre de ölçülür.

Kullanım (uçta):

    with Y.yakala(engine) as q:
        out = E.overview(engine, tenant)
    return P.bagla(out, lambda: K.for_overview(engine, tenant, out, q))

Logo/CRM sorgu çalıştırıcısı: `run = Y.izle(run, "logo", database)` — sarılan çalıştırıcı açık bir yakalamaya metni,
satır sayısını ve süreyi yazar. Tabloyu gece dolduran asıl Logo/CRM sorguları yenileme işinde yakalanır ve
`semantic_query_origin` tablosuna yazılır (`koken_yaz`); ekrandaki rakamın «asıl SQL»i oradan `origin` olarak eklenir.

Kurallar: yalnız okuma (`SELECT`/`WITH`) kaydedilir; yazma, tablo kurma ve yenileme yazıları kaydedilmez. Sonuç satırı
hiçbir zaman kayda girmez (yalnız satır sayısı). Parola/anahtar içeren metin `provenance.clean_sql` ile reddedilir.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Iterator, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy import event

from semantic_bridge import provenance as P

log = logging.getLogger("semantic.sorgu_yakala")

_ACTIVE: ContextVar[tuple["Yakalanan", ...]] = ContextVar("sorgu_yakala_active", default=())
_LISTENING: set[int] = set()
_LOCK = threading.Lock()
_READ = re.compile(r"^\s*(\(\s*)*(select|with)\b", re.I)
_TABLES = re.compile(r"\b(?:from|join)\s+(?:[\"`\[]?\w+[\"`\]]?\.)?[\"`\[]?(\w+)[\"`\]]?", re.I)
_PYFORMAT = re.compile(r"%\((\w+)\)s|%%|%s")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tables_of(sql: str) -> list[str]:
    """SQL'in okuduğu tablolar (FROM/JOIN sırasıyla, tekrarsız, küçük harf)."""
    out: list[str] = []
    bare = re.sub(r"N?'(?:[^']|'')*'", "''", sql or "")
    for m in _TABLES.finditer(bare):
        t = m.group(1).lower()
        if t not in out and t not in ("select", "lateral", "unnest"):
            out.append(t)
    return out


def inline_driver(statement: str, parameters: Any, paramstyle: str) -> str:
    """Sürücüye giden metin + parametreler → değerleri yerinde metin (portal diliyle)."""
    if parameters is None or parameters == () or parameters == {}:
        return statement.replace("%%", "%") if paramstyle in ("pyformat", "format") else statement
    if paramstyle in ("pyformat", "format"):
        seq = list(parameters) if isinstance(parameters, (list, tuple)) else None
        idx = {"i": 0}

        def rep(m: re.Match) -> str:
            if m.group(0) == "%%":
                return "%"
            if m.group(1) is not None:
                return P._literal(parameters[m.group(1)], "portal")
            v = seq[idx["i"]] if seq is not None else None
            idx["i"] += 1
            return P._literal(v, "portal")
        return _PYFORMAT.sub(rep, statement)
    if paramstyle == "named" and isinstance(parameters, dict):
        return P.inline_params(statement, parameters, "portal")
    if isinstance(parameters, dict):
        return P.inline_params(statement, parameters, "portal")
    return P.inline_params(statement, list(parameters), "portal")


class Yakalanan:
    """Bir yakalama penceresinde koşan okumalar: `queries` = [{connection, sql, rows, ms, at, tables, database}]."""

    def __init__(self) -> None:
        self.queries: list[dict[str, Any]] = []

    def ekle(self, connection: str, sql: str, rows: Optional[int], ms: Optional[int], database: Optional[str] = None) -> None:
        text = (sql or "").strip()
        if not text or not _READ.match(text):
            return
        tables = tables_of(text)
        if connection == "portal" and (not tables or any(t.startswith(("pg_", "sqlite_", "information_schema")) for t in tables)):
            return  # tablo kurma denetimi, sistem kataloğu: ekrandaki rakamın sorgusu değil
        for q in self.queries:
            if q["sql"] == text and q["connection"] == connection:
                q["runs"] += 1
                return
        self.queries.append({"connection": connection, "sql": text, "rows": rows, "ms": ms, "at": _now(),
                             "tables": tables, "database": database, "runs": 1})

    def extend(self, queries: Iterable[dict[str, Any]]) -> None:
        for q in queries or ():
            self.ekle(q["connection"], q["sql"], q.get("rows"), q.get("ms"), q.get("database"))

    def of(self, *tables: str, connection: Optional[str] = None) -> list[dict[str, Any]]:
        want = {t.lower() for t in tables}
        return [q for q in self.queries if (not want or want & set(q["tables"]))
                and (connection is None or q["connection"] == connection)]


def _listen(engine: Any) -> None:
    key = id(engine)
    if key in _LISTENING:
        return
    with _LOCK:
        if key in _LISTENING:
            return

        def before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            if _ACTIVE.get():
                conn.info.setdefault("_sorgu_yakala_t0", []).append(time.monotonic())

        def after(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            active = _ACTIVE.get()
            if not active:
                return
            stack = conn.info.get("_sorgu_yakala_t0") or []
            t0 = stack.pop() if stack else None
            if executemany or not _READ.match(statement or ""):
                return
            try:
                text = inline_driver(statement, parameters, getattr(conn.dialect, "paramstyle", "qmark"))
            except Exception as e:  # noqa: BLE001 — yakalama rakamı düşürmez
                log.info("sorgu yakalanamadı: %s", e)
                return
            rc = getattr(cursor, "rowcount", -1)
            rows = int(rc) if isinstance(rc, int) and rc >= 0 else None
            ms = int((time.monotonic() - t0) * 1000) if t0 else None
            for y in active:
                y.ekle("portal", text, rows, ms)

        event.listen(engine, "before_cursor_execute", before)
        event.listen(engine, "after_cursor_execute", after)
        _LISTENING.add(key)


@contextmanager
def yakala(*engines: Any) -> Iterator[Yakalanan]:
    """Bu blokta verilen motor(lar)a giden okumaları ve `izle` ile sarılmış Logo/CRM çalıştırıcılarının sorgularını kaydeder."""
    for e in engines:
        if e is not None:
            _listen(e)
    y = Yakalanan()
    token = _ACTIVE.set(_ACTIVE.get() + (y,))
    try:
        yield y
    finally:
        _ACTIVE.reset(token)


def baslat(*engines: Any) -> tuple[Yakalanan, Any]:
    """`with` bloğuna sığmayan uzun işler (yenileme) için: yakalamayı başlatır; `bitir(token)` ile kapatılır."""
    for e in engines:
        if e is not None:
            _listen(e)
    y = Yakalanan()
    return y, _ACTIVE.set(_ACTIVE.get() + (y,))


def bitir(token: Any) -> None:
    try:
        _ACTIVE.reset(token)
    except (ValueError, RuntimeError):  # zaten kapatıldıysa (iki kez çağrı) dokunma
        pass


def db_of(path: Optional[str]) -> Optional[str]:
    """Bağlantı dosyasından yalnız veritabanı adı (USE satırı için)."""
    return P.connection_database(path)


def izle(run: Callable[[str], Any], connection: str, database: Optional[str] = None) -> Callable[[str], Any]:
    """Logo/CRM çalıştırıcısını sarar: metin, satır sayısı ve süre açık yakalamalara yazılır. Metin sürücüye gidenin
    kendisidir (bu modüllerde Logo/CRM SQL'i değerleri yerinde kurulur)."""
    if getattr(run, "_sorgu_yakala", False):
        return run

    def wrapped(sql: str, *a: Any, **kw: Any) -> Any:
        t0 = time.monotonic()
        out = run(sql, *a, **kw)
        active = _ACTIVE.get()
        if active:
            try:
                n = len(out) if hasattr(out, "__len__") else None
            except TypeError:
                n = None
            ms = int((time.monotonic() - t0) * 1000)
            for y in active:
                y.ekle(connection, sql, n, ms, database)
        return out

    wrapped._sorgu_yakala = True  # type: ignore[attr-defined]
    return wrapped


# ------------------------------------------------------------------ asıl sorgu (tabloyu dolduran) kaydı

_md = sa.MetaData()
ORIGIN = sa.Table(
    "semantic_query_origin", _md,
    sa.Column("tenant_id", sa.String(64), primary_key=True),
    sa.Column("key", sa.String(120), primary_key=True),
    sa.Column("seq", sa.Integer, primary_key=True),
    sa.Column("connection", sa.String(16), nullable=False),
    sa.Column("database", sa.String(128)),
    sa.Column("sql_text", sa.Text, nullable=False),
    sa.Column("rows", sa.Integer),
    sa.Column("db_ms", sa.Integer),
    sa.Column("runs", sa.Integer),
    sa.Column("ran_at", sa.String(40)),
)
_ready: set[int] = set()


def ensure(engine: Any) -> None:
    with _LOCK:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def koken_yaz(engine: Any, tenant: str, key: str, y: Yakalanan, connections: Sequence[str] = ("logo", "crm"),
              portal_tables: Sequence[str] = ()) -> int:
    """Yenileme işinde yakalanan Logo/CRM sorgularını (ve `portal_tables` verilirse o tabloları okuyan portal
    sorgularını — ör. başka modülün gece eşitlediği tablo) `key` altına yazar (öncekinin yerine). Yazılan sorgu sayısı."""
    want = {t.lower() for t in portal_tables}
    qs = [q for q in y.queries if q["connection"] in connections
          or (q["connection"] == "portal" and want and want & set(q["tables"]))]
    if not qs:
        return 0
    try:
        ensure(engine)
        with engine.begin() as c:
            c.execute(ORIGIN.delete().where(ORIGIN.c.tenant_id == tenant, ORIGIN.c.key == key))
            c.execute(ORIGIN.insert(), [
                {"tenant_id": tenant, "key": key, "seq": i, "connection": q["connection"], "database": q.get("database"),
                 "sql_text": q["sql"], "rows": q.get("rows"), "db_ms": q.get("ms"), "runs": q.get("runs") or 1,
                 "ran_at": q.get("at")} for i, q in enumerate(qs)])
    except Exception as e:  # noqa: BLE001 — kayıt yazılamasa da yenileme sürer
        log.warning("asıl sorgu kaydı yazılamadı (%s): %s", key, e)
        return 0
    return len(qs)


def koken_oku(engine: Any, tenant: str, key: str) -> list[dict[str, Any]]:
    """Tabloyu dolduran son yenilemenin Logo/CRM sorguları. Bu okuma yakalamaya girmez (ekrandaki rakamın sorgusu değil)."""
    ensure(engine)
    token = _ACTIVE.set(())
    try:
        with engine.connect() as c:
            rows = c.execute(sa.select(ORIGIN).where(ORIGIN.c.tenant_id == tenant, ORIGIN.c.key == key)
                             .order_by(ORIGIN.c.seq)).mappings().all()
    finally:
        _ACTIVE.reset(token)
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ kaynak kaydına aktarma


class Kurucu:
    """Yakalanan sorguları bir `Kaynaklar` kaydına aktarır; tablo adı → okunur başlık (`tablolar`), tablo → asıl sorgu
    anahtarı (`koken`). `k.hesap`/`k.alan` doğrudan `self.k` üzerinden, girdiler tablo adıyla (`self.girdi(...)`)."""

    def __init__(self, engine: Any, tenant: str, q: Yakalanan, *, prefix: str, tablolar: dict[str, tuple[str, str]],
                 koken: Optional[dict[str, Sequence[str]]] = None, koken_basliklari: Optional[dict[str, str]] = None,
                 data_end: Any = None, as_of: Any = None):
        self.k = P.Kaynaklar(data_end=data_end, as_of=as_of)
        self.engine, self.tenant, self.prefix = engine, tenant, prefix
        self.tablolar = {t.lower(): v for t, v in tablolar.items()}
        self.by_table: dict[str, list[str]] = {}
        self._origin_ids: dict[str, list[str]] = {}
        self.reddedilen: list[str] = []
        koken = {t.lower(): list(v) for t, v in (koken or {}).items()}
        titles = koken_basliklari or {}
        used: dict[str, int] = {}
        for q_ in q.queries:
            tables = q_["tables"]
            main = next((t for t in tables if t in self.tablolar), tables[0] if tables else "sorgu")
            title, desc = self.tablolar.get(main, (f"Okuma · {main}", ""))
            n = used.get(main, 0) + 1
            used[main] = n
            sid = f"{prefix}.{main.replace('semantic_', '')}" + (f".{n}" if n > 1 else "")
            if q_["runs"] > 1:
                desc = (desc + " " if desc else "") + f"Bu istekte {q_['runs']} kez çalıştı."
            try:
                if q_["connection"] == "portal":
                    origin: list[str] = []
                    for t in tables:
                        for key in koken.get(t, []):
                            origin += self._origin(key, titles.get(key, ""))
                    self.k.sorgu(sid, title if n == 1 else f"{title} ({n})", "portal", q_["sql"], description=desc,
                                 rows=q_.get("rows"), ms=q_.get("ms"), ran_at=q_.get("at"), origin=list(dict.fromkeys(origin)))
                else:
                    self.k.sorgu(sid, title if n == 1 else f"{title} ({n})", q_["connection"], q_["sql"], description=desc,
                                 database=q_.get("database"), rows=q_.get("rows"), ms=q_.get("ms"), ran_at=q_.get("at"))
            except P.ProvenanceError as e:
                # Parola/anahtar kolonu okuyan ya da sır izi taşıyan okuma gösterilmez; öbür kayıtlar sürer.
                self.reddedilen.append(f"{main}: {e}")
                continue
            for t in tables or [main]:
                self.by_table.setdefault(t, []).append(sid)
            self.by_table.setdefault("*", []).append(sid)

    def _origin(self, key: str, title: str) -> list[str]:
        if key in self._origin_ids:
            return self._origin_ids[key]
        ids: list[str] = []
        try:
            rows = koken_oku(self.engine, self.tenant, key)
        except Exception as e:  # noqa: BLE001
            log.info("asıl sorgu okunamadı (%s): %s", key, e)
            rows = []
        for r in rows:
            sid = f"{self.prefix}.koken.{key}.{r['seq']}"
            label = CONNECTION_TITLE.get(r["connection"], r["connection"])
            desc = "Bu tabloyu dolduran son yenilemede çalışan sorgu."
            if (r.get("runs") or 1) > 1:
                desc += f" Yenilemede {r['runs']} kez çalıştı."
            try:
                self.k.sorgu(sid, f"{title or 'Tabloyu dolduran sorgu'} · {label}" + (f" ({r['seq'] + 1})" if r["seq"] else ""),
                             r["connection"], r["sql_text"], database=r.get("database"), rows=r.get("rows"),
                             ms=r.get("db_ms"), ran_at=r.get("ran_at"), description=desc)
            except P.ProvenanceError as e:
                self.reddedilen.append(f"{key}: {e}")
                continue
            ids.append(sid)
        self._origin_ids[key] = ids
        return ids

    def girdi(self, *tables: str) -> list[str]:
        """Tablo adları (ya da kayıt kimlikleri, `hesap:` başvuruları) → bu istekte o tabloyu okuyan sorguların kimlikleri.
        Hiç tablo verilmezse bu istekteki bütün okumalar."""
        if not tables:
            return list(dict.fromkeys(self.by_table.get("*", [])))
        out: list[str] = []
        for t in tables:
            if t.startswith("hesap:") or t in self.k.sources:
                out.append(t)
            else:
                out += self.by_table.get(t.lower(), [])
        return list(dict.fromkeys(out))

    def hesap(self, name: str, text: str, *tables: str) -> str:
        """Formül + girdi tabloları; tablo bu istekte okunmadıysa (boş veri dalı) bütün okumalara bağlanır."""
        ins = self.girdi(*tables) or self.girdi()
        return self.k.hesap(name, text, ins)

    def sorgu(self, *tables: str) -> str:
        """Alanı doğrudan tek sorguya bağlar (tablonun ilk okuması); yoksa ilk okuma."""
        ids = self.girdi(*tables) or self.girdi()
        if not ids:
            raise P.ProvenanceError("Bu istekte kaydedilen okuma yok.")
        return ids[0]

    def alanlar(self, mapping: dict[str, str]) -> P.Kaynaklar:
        self.k.alanlar(mapping)
        return self.k


CONNECTION_TITLE = {"logo": "Logo", "crm": "CRM", "portal": "Portal"}
