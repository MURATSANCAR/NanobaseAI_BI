"""Uçta çalışan CRM/Logo sorgularının kaydı (sorgu bilgisi, 2026-09-28).

Bazı uçlar CRM ya da Logo'yu istek anında bir `run(sql)` işleviyle okur (kişiler, yazar ilişkileri, serbest çalışanın
Logo kartı). Ekrandaki «i» penceresi o istekte ÇALIŞAN metni göstermelidir: çalıştırıcı (`run_sql`) metni fiziksel
tabloya çevirir (`physicalSql`), sonuç önbellekten gelebilir (`computedAt`). `RunLog` çalıştırıcıyı sarar; her çağrının
istenen metnini, çalışan metnini, satır sayısını, süresini ve ne zaman hesaplandığını tutar. Sonuç satırları KAYDA
GİRMEZ (kişisel veri: yalnız satır sayısı).

Uçta tek satır:

    return SK.bagla_run(run, lambda r: modul.fonksiyon(schema, r, ...), lambda out, log: K.for_x(out, log, ...))
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from semantic_bridge import provenance as P


class RunLog:
    """`run(sql, *a, **kw)` sarmalayıcısı. Dönen değer aynen geçer; kayıt yalnız metin ve sayaçlardır."""

    def __init__(self, run: Callable[..., Any]):
        self._run = run
        self.items: list[dict[str, Any]] = []

    def __call__(self, sql: str, *a: Any, **kw: Any) -> Any:
        t0 = time.monotonic()
        out = self._run(sql, *a, **kw)
        ms = int((time.monotonic() - t0) * 1000)
        item: dict[str, Any] = {"asked": sql, "sql": sql, "rows": None, "dbMs": ms, "at": time.time(), "cached": False}
        if isinstance(out, dict):
            item["sql"] = out.get("physicalSql") or sql
            recs = out.get("records")
            item["rows"] = out.get("totalRows") if out.get("totalRows") is not None else (len(recs) if isinstance(recs, list) else None)
            if out.get("dbMs") is not None:
                item["dbMs"] = out.get("dbMs")
            if out.get("computedAt"):
                item["at"] = out.get("computedAt")
            item["cached"] = bool(out.get("cached"))
        elif isinstance(out, (list, tuple)):
            item["rows"] = len(out)
        self.items.append(item)
        return out

    def find(self, asked: str) -> Optional[dict[str, Any]]:
        """İstenen metni `asked` olan son çağrı (aynı `*_sql(...)` işleviyle yeniden kurulan metin)."""
        for it in reversed(self.items):
            if it["asked"] == asked:
                return it
        return None

    def find_all(self, contains: str) -> list[dict[str, Any]]:
        return [it for it in self.items if contains in it["asked"]]

    def sorgu(self, k: P.Kaynaklar, sid: str, title: str, conn: str, asked: str, *, database: Optional[str] = None,
              description: str = "", period: Optional[str] = None, origin: tuple = ()) -> Optional[str]:
        """İstekte çalışmış sorguyu kayda ekler; çalışmadıysa (ör. boş kimlik listesi) None döner — uydurulmaz."""
        it = self.find(asked)
        if it is None:
            return None
        return kaydet(k, sid, title, conn, it, database=database, description=description, period=period, origin=origin)


def kaydet(k: P.Kaynaklar, sid: str, title: str, conn: str, it: dict[str, Any], *, database: Optional[str] = None,
           description: str = "", period: Optional[str] = None, origin: tuple = ()) -> str:
    """Kaydedilmiş bir çağrıyı (`RunLog.items` ya da okuma kaydındaki aynı biçimli sözlük) kaynak olarak ekler."""
    note = " Sonuç bu istekte önbellekten verildi; sorgu gösterilen anda çalıştı." if it.get("cached") else ""
    return k.sorgu(sid, title, conn, it["sql"], database=database, rows=it.get("rows"), ms=it.get("dbMs"),
                   ran_at=it.get("at"), description=(description + note).strip(), period=period, origin=origin)


def bagla_out(out: Any, build: Callable[[Any], Optional[P.Kaynaklar]]) -> Any:
    """Uç gövdesinde tek satır, cevap bir ifadeyse: `return SK.bagla_out(modul.x(...), lambda o: K.for_x(..., o))`."""
    return P.bagla(out, lambda: build(out))


def bagla_run(run: Callable[..., Any], call: Callable[[RunLog], Any],
              build: Callable[[Any, RunLog], Optional[P.Kaynaklar]]) -> Any:
    """Uç gövdesinde tek satır: `run`'ı kaydediciyle sarar, uç işlevini çağırır, cevaba `kaynaklar` ekler.
    Hata (HTTPException vb.) olduğu gibi yükselir; kayıt kurulamazsa rakamlar yine döner (`P.bagla`)."""
    log = RunLog(run)
    out = call(log)
    return P.bagla(out, lambda: build(out, log))
