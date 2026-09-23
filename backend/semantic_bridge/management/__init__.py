"""Yönetim raporları modülü — diğer modüllerden ayrı, kendi kaynakları ve önbelleğiyle çalışır.

Her rapor bu paketteki bir Python modülüdür (`REPORT_ID`, `TITLE`, `SOURCES`, `build`) ve SQL'leri
`sql/<rapor>/<kaynak>.sql` dosyalarındadır. Ekran bu SQL'lerin kendisini gösterir; çalışan metin ile
gösterilen metin aynı dosyadır.

Raporlar sabit, gözden geçirilmiş SQL okur; sohbet motorunun katalog kapısından (`run_sql`) geçmez ve
onun tek bağlantısını meşgul etmez. Bağlantılar salt okunur açılan ayrı bağlantılardır.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from semantic_bridge.management import baski_oneri

log = logging.getLogger(__name__)

REPORTS = {m.REPORT_ID: m for m in (baski_oneri,)}
SQL_DIR = Path(__file__).with_name("sql")
MAX_ROWS = 500_000
# Ekrandaki rapor beş dakikada bir kaynaktan yeniden okunur (kullanıcı kararı 2026-09-22).
REFRESH_SECONDS = int(os.environ.get("MANAGEMENT_REPORT_REFRESH_SECONDS", "300"))
QUERY_TIMEOUT = int(os.environ.get("MANAGEMENT_REPORT_QUERY_TIMEOUT_SEC", "900"))
CONNECTION_LABELS = {"logo": "Logo", "crm": "CRM"}


def _cache_dir() -> Path:
    root = Path(os.environ.get("MANAGEMENT_REPORT_CACHE_DIR", "/data/nanobaseai/bi/var/management-reports"))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _save(path: Path, value: dict) -> None:
    temp = path.with_name("." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x") as stream:
            os.chmod(temp, 0o600)
            json.dump(value, stream, ensure_ascii=False, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def sql_text(report_id: str, source_id: str) -> str:
    return (SQL_DIR / report_id.replace("-", "_") / f"{source_id}.sql").read_text(encoding="utf-8")


def _quoted_list(values: list[str]) -> str:
    return ", ".join("N'" + str(v).replace("'", "''") + "'" for v in values)


# Logo satış görünümü `V_SatisRaporu_ALL2`, 2015'ten bu yana her yılın `V_SatisRaporu_<yıl>` görünümünü
# UNION ALL ile birleştirir; dışarıdaki yıl süzgeci birleşimin kollarını elemediği için her sorgu on iki
# yılın tamamını tarar (ölçüm 2026-09-23: fiyat sorgusu 900 sn'de bitmedi, üç yıllık görünüm 25 sn).
# `{satis:2024}` = 2024'ten bu yıla, `{satis:-1}` = geçen yıldan bu yıla yıllık görünümlerin birleşimi.
# Her kol ALL2'nin kendi süzgecini taşır; kolonlar adla seçilir (SELECT * birleşimi kolon kaydırabilir).
SALES_VIEW_FILTER = "[Malzeme/Hizmet Kodu] NOT LIKE '157%' AND [KDVli Tutar] <> 0"
SALES_COLUMNS = ("[Malzeme/Hizmet Kodu], [Malzeme/Hizmet Adı], [Fatura Tarihi], [Yıl], [Ay], [Miktar], "
                 "[Birim Fiyat], [Net Tutar], [Satır Türü], [Satis_Iade], [Satıcı Kodu], [Sipariş Numarası]")
_SALES_PLACEHOLDER = re.compile(r"\{satis:(-?\d+)\}")


def sales_years(spec: str, today: date) -> list[int]:
    n = int(spec)
    first = today.year + n if n <= 0 else n
    return list(range(first, today.year + 1))


def expand_sales(text: str, today: date, existing: set[int] | None = None) -> tuple[str, list[int]]:
    """Yer tutucuları yıllık görünümlerin birleşimine açar. `existing` verilirse olmayan yıl atlanır
    ve atlanan yıllar döner (ekranda uyarı olur; sessizce eksik okunmaz)."""
    missing: list[int] = []

    def union(match: re.Match) -> str:
        years = sales_years(match.group(1), today)
        use = [y for y in years if existing is None or y in existing]
        missing.extend(y for y in years if y not in use)
        if not use:
            raise RuntimeError(f"Logo'da {years[0]}–{years[-1]} satış görünümlerinin hiçbiri yok.")
        arms = [f"    SELECT {SALES_COLUMNS}\n    FROM dbo.V_SatisRaporu_{y}\n    WHERE {SALES_VIEW_FILTER}" for y in use]
        return "(\n" + "\n    UNION ALL\n".join(arms) + "\n)"

    return _SALES_PLACEHOLDER.sub(union, text), sorted(set(missing))


class Reports:
    def __init__(self, connection_files):
        self._connection_files = connection_files  # çağrılabilir: çalışma zamanı ayarı açılışta hazır değil
        self._connectors: dict[str, Any] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._guard = threading.Lock()
        self._started: dict[str, float] = {}
        self.stopping = threading.Event()
        self.scheduler = None

    # ---- bağlantılar
    def _connector(self, name: str):
        if name not in self._connectors:
            from semantic_layer.profiler.connectors import connector_from_file
            path = self._connection_files().get(name)
            if not path or not Path(path).exists():
                raise RuntimeError(f"{CONNECTION_LABELS.get(name, name)} bağlantısı bu kurulumda tanımlı değil.")
            conn = connector_from_file(path)
            conn.query_timeout = QUERY_TIMEOUT  # rapor sorguları sohbet sorgularından uzun sürebilir
            self._connectors[name] = conn
        return self._connectors[name]

    def database_label(self, name: str) -> str:
        try:
            db = json.loads(Path(self._connection_files()[name]).read_text()).get("database") or ""
        except (OSError, ValueError, KeyError):
            db = ""
        label = CONNECTION_LABELS.get(name, name)
        return f"{label} · {db}" if db else label

    def _sales_years_present(self) -> set[int]:
        conn = self._connector("logo")
        _, rows, _ = conn.execute("SELECT name FROM sys.views WHERE name LIKE 'V[_]SatisRaporu[_]20[0-9][0-9]'", 200)
        return {int(r["name"][-4:]) for r in rows}

    def _run(self, report, source_id: str, params: dict | None, ctx: dict) -> dict:
        connection = next(c for s, c, *_ in report.SOURCES if s == source_id)
        text = sql_text(report.REPORT_ID, source_id)
        missing: list[int] = []
        if _SALES_PLACEHOLDER.search(text):
            if "sales_years" not in ctx:
                ctx["sales_years"] = self._sales_years_present()
            text, missing = expand_sales(text, date.today(), ctx["sales_years"])
        conn = self._connector(connection)
        chunks = [None]
        if params and "stok_kodlari" in params:
            codes = params["stok_kodlari"]
            chunks = [codes[i:i + 400] for i in range(0, len(codes), 400)] or [[]]
        records, columns, started = [], [], time.monotonic()
        title = next(t for s, _, t, *_ in report.SOURCES if s == source_id)
        for chunk in chunks:
            sql = text if chunk is None else text.replace("{stok_kodlari}", _quoted_list(chunk))
            try:
                cols, rows, truncated = conn.execute(sql, MAX_ROWS)
            except Exception as exc:  # noqa: BLE001 — sürücü metni ekrana değil loga
                log.warning("management source %s failed: %s", source_id, str(exc)[:300])
                state = str(getattr(exc, "args", [""])[0])
                if state in ("HYT00", "HYT01"):
                    raise RuntimeError(f"“{title}” sorgusu {QUERY_TIMEOUT} saniyede bitmedi (zaman aşımı).") from None
                if state in ("08S01", "08001"):
                    raise RuntimeError(f"{self.database_label(connection)} veritabanına şu an ulaşılamıyor.") from None
                raise RuntimeError(f"“{title}” sorgusu hata verdi: {str(exc)[:200]}") from None
            if truncated:
                raise RuntimeError(f"{source_id}: sonuç {MAX_ROWS} satırı aştı; rapor eksik kalırdı.")
            columns, records = cols, records + rows
        out = {"columns": columns, "records": records, "dbMs": int((time.monotonic() - started) * 1000), "sql": text}
        if missing:
            out["warning"] = f"Logo'da {', '.join(map(str, missing))} satış görünümü yok; bu yıllar okunmadı."
        return out

    # ---- önbellek
    def path(self, report_id: str) -> Path:
        return _cache_dir() / f"{report_id}.json"

    def read(self, report_id: str, *, with_data: bool = True) -> dict:
        snap = _load(self.path(report_id))
        running = self._threads.get(report_id)
        refreshing = bool(running and running.is_alive())
        last = max(snap.get("updatedAt") or 0, snap.get("failedAt") or 0)
        meta = {k: v for k, v in snap.items() if k != "data"}
        out = {**meta, "refreshing": refreshing, "hasData": "data" in snap,
               "refreshStartedAt": self._started.get(report_id) if refreshing else None,
               "nextRefreshAt": (last + REFRESH_SECONDS) if last else None}
        if with_data and "data" in snap:
            out["data"] = snap["data"]
        return out

    def refresh(self, report_id: str) -> None:
        report = REPORTS[report_id]
        path = self.path(report_id)
        with (path.with_suffix(".lock")).open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return  # başka bir süreç zaten yeniliyor
            previous = _load(path)
            started = time.time()
            try:
                ctx: dict = {}
                data = report.build(lambda sid, params: self._run(report, sid, params, ctx))
                _save(path, {"data": data, "updatedAt": time.time(), "durationMs": int((time.time() - started) * 1000),
                             "error": None})
            except Exception as exc:  # noqa: BLE001 — son başarılı sonuç korunur
                log.warning("management report %s refresh failed: %s", report_id, exc)
                _save(path, {**previous, "error": f"Veriler yenilenemedi: {str(exc)[:300]} Beş dakikada bir yeniden denenir.",
                             "failedAt": time.time()})

    def start_refresh(self, report_id: str) -> bool:
        with self._guard:
            running = self._threads.get(report_id)
            if running and running.is_alive():
                return False
            t = threading.Thread(target=self.refresh, args=(report_id,), daemon=True, name=f"management-{report_id}")
            self._threads[report_id] = t
            self._started[report_id] = time.time()
            t.start()
            return True

    def start(self):
        def schedule():
            while not self.stopping.is_set():
                for rid in REPORTS:
                    snap = _load(self.path(rid))
                    # Başarılı ya da başarısız, son denemeden bu yana aralık dolduysa yeniden oku.
                    last = max(snap.get("updatedAt") or 0, snap.get("failedAt") or 0)
                    if time.time() - last >= REFRESH_SECONDS:
                        self.start_refresh(rid)
                self.stopping.wait(10)
        self.scheduler = threading.Thread(target=schedule, daemon=True, name="management-reports")
        self.scheduler.start()

    def stop(self):
        self.stopping.set()


def register(app, runtime, authorize, session_user):
    """`session_user(request)` oturum sahibini döner ya da 401 atar."""
    reports = Reports(lambda: {
        "logo": runtime().settings.connection_file,
        "crm": os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"),
    })

    def report_of(report_id: str):
        report = REPORTS.get(report_id)
        if report is None:
            raise HTTPException(404, {"code": "NOT_FOUND", "message": "Böyle bir rapor yok."})
        return report

    def gate(request: Request) -> str:
        authorize(request)
        return session_user(request)

    @app.get("/api/v1/management/reports")
    def management_reports(request: Request) -> dict[str, Any]:
        gate(request)
        out = []
        for rid, m in REPORTS.items():
            snap = _load(reports.path(rid))
            out.append({"id": rid, "title": m.TITLE, "description": m.DESCRIPTION,
                        "updatedAt": snap.get("updatedAt"), "sources": len(m.SOURCES),
                        "refreshIntervalSeconds": REFRESH_SECONDS,
                        "views": [{"id": v["id"], "title": v["title"], "rows": len(v["rows"])}
                                  for v in (snap.get("data") or {}).get("views", [])]})
        return {"reports": out}

    @app.get("/api/v1/management/reports/{report_id}")
    def management_report(report_id: str, request: Request, since: float | None = None) -> dict[str, Any]:
        """`since` ekrandaki verinin zamanıdır: değişmediyse yalnız durum döner, binlerce satır tekrar gitmez."""
        gate(request)
        report_of(report_id)
        snap = reports.read(report_id, with_data=False)
        if not snap["hasData"] and not snap.get("refreshing") and not snap.get("error"):
            reports.start_refresh(report_id)
        unchanged = since is not None and snap.get("updatedAt") is not None and abs(float(since) - snap["updatedAt"]) < 1e-3
        snap = reports.read(report_id, with_data=not unchanged)
        return {"id": report_id, "refreshIntervalSeconds": REFRESH_SECONDS, "serverTime": time.time(),
                "unchanged": unchanged, **snap}

    @app.get("/api/v1/management/reports/{report_id}/sources")
    def management_report_sources(report_id: str, request: Request) -> dict[str, Any]:
        gate(request)
        report = report_of(report_id)
        stats = (_load(reports.path(report_id)).get("data") or {}).get("sourceStats", {})
        return {
            "sources": [{"id": sid, "connection": conn, "database": reports.database_label(conn), "title": title,
                         "description": desc, "sql": (stats.get(sid) or {}).get("sql") or sql_text(report_id, sid),
                         "stats": stats.get(sid)}
                        for sid, conn, title, desc in report.SOURCES],
            "formulas": [{"name": n, "text": t} for n, t in report.FORMULAS],
            "notes": list(report.NOTES),
        }

    @app.post("/api/v1/management/reports/{report_id}/refresh")
    def management_report_refresh(report_id: str, request: Request) -> dict[str, Any]:
        user = gate(request)
        report = report_of(report_id)
        started = reports.start_refresh(report_id)
        try:
            from semantic_bridge import admin as admin_mod
            admin_mod.audit(runtime().store.engine, user, "run", "management_report", report_id, report.TITLE,
                            {"started": started})
        except Exception:  # noqa: BLE001 — kayıt düşmesi yenilemeyi durdurmaz
            log.exception("management report audit failed")
        return {"id": report_id, "refreshIntervalSeconds": REFRESH_SECONDS, "serverTime": time.time(),
                "started": started, **reports.read(report_id, with_data=False)}

    return reports
