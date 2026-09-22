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
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from semantic_bridge.management import baski_oneri

log = logging.getLogger(__name__)

REPORTS = {m.REPORT_ID: m for m in (baski_oneri,)}
SQL_DIR = Path(__file__).with_name("sql")
MAX_ROWS = 500_000
REFRESH_SECONDS = int(os.environ.get("MANAGEMENT_REPORT_REFRESH_SECONDS", "3600"))
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


class Reports:
    def __init__(self, connection_files):
        self._connection_files = connection_files  # çağrılabilir: çalışma zamanı ayarı açılışta hazır değil
        self._connectors: dict[str, Any] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._guard = threading.Lock()
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

    def _run(self, report, source_id: str, params: dict | None) -> dict:
        connection = next(c for s, c, *_ in report.SOURCES if s == source_id)
        text = sql_text(report.REPORT_ID, source_id)
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
                if state in ("08S01", "08001", "HYT00", "HYT01"):
                    raise RuntimeError(f"{self.database_label(connection)} veritabanına şu an ulaşılamıyor.") from None
                raise RuntimeError(f"“{title}” sorgusu hata verdi: {str(exc)[:200]}") from None
            if truncated:
                raise RuntimeError(f"{source_id}: sonuç {MAX_ROWS} satırı aştı; rapor eksik kalırdı.")
            columns, records = cols, records + rows
        return {"columns": columns, "records": records, "dbMs": int((time.monotonic() - started) * 1000)}

    # ---- önbellek
    def path(self, report_id: str) -> Path:
        return _cache_dir() / f"{report_id}.json"

    def read(self, report_id: str) -> dict:
        snap = _load(self.path(report_id))
        running = self._threads.get(report_id)
        return {**snap, "refreshing": bool(running and running.is_alive())}

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
                data = report.build(lambda sid, params: self._run(report, sid, params))
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
            t.start()
            return True

    def start(self):
        def schedule():
            while not self.stopping.is_set():
                for rid in REPORTS:
                    snap = _load(self.path(rid))
                    if time.time() - snap.get("updatedAt", 0) >= REFRESH_SECONDS and \
                            time.time() - snap.get("failedAt", 0) >= 300:
                        self.start_refresh(rid)
                self.stopping.wait(60)
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
                        "views": [{"id": v["id"], "title": v["title"], "rows": len(v["rows"])}
                                  for v in (snap.get("data") or {}).get("views", [])]})
        return {"reports": out}

    @app.get("/api/v1/management/reports/{report_id}")
    def management_report(report_id: str, request: Request) -> dict[str, Any]:
        gate(request)
        report_of(report_id)
        snap = reports.read(report_id)
        if "data" not in snap and not snap.get("refreshing") and not snap.get("error"):
            reports.start_refresh(report_id)
            snap = reports.read(report_id)
        return {"id": report_id, "refreshIntervalSeconds": REFRESH_SECONDS, **snap}

    @app.get("/api/v1/management/reports/{report_id}/sources")
    def management_report_sources(report_id: str, request: Request) -> dict[str, Any]:
        gate(request)
        report = report_of(report_id)
        stats = (_load(reports.path(report_id)).get("data") or {}).get("sourceStats", {})
        return {
            "sources": [{"id": sid, "connection": conn, "database": reports.database_label(conn), "title": title,
                         "description": desc, "sql": sql_text(report_id, sid), "stats": stats.get(sid)}
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
        return {"started": started, **reports.read(report_id)}

    return reports
