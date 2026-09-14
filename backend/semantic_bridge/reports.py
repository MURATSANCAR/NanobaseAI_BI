"""Planlı raporlar: "bana her sabah 08:00'de … Excel'i hazırla, x@y.com'a gönder" cümlesinden plan.

Plan bir sorudur (uyarılar gibi): her çalışmada soru motora yeniden sorulur ki "bu ay", "geçen hafta"
çalıştığı güne göre anlamlansın. Dosya (Excel/CSV) sunucuda üretilir, e-posta ayarı varsa gönderilir;
yoksa dosya yine üretilir, "SMTP yok" diye işaretlenir ve ekrandan indirilir. Sessiz kesme yok: rapora
tüm satırlar yazılır (`run_complete`), satır sayısı e-postada ve kayıtta durur.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import mimetypes
import os
import re
import smtplib
import ssl
import threading
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import alerts as alerts_mod

log = logging.getLogger(__name__)

_md = sa.MetaData()

REPORTS = sa.Table(
    "semantic_reports", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("datasource_id", sa.String(80), nullable=False),
    sa.Column("username", sa.String(120), nullable=False, index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("prompt", sa.Text),
    sa.Column("question", sa.Text, nullable=False),
    sa.Column("sql", sa.Text),
    sa.Column("fmt", sa.String(8), nullable=False, default="xlsx"),
    sa.Column("recurrence", sa.String(8), nullable=False, default="daily"),
    sa.Column("at_time", sa.String(5), nullable=False, default="08:00"),
    sa.Column("weekday", sa.Integer),
    sa.Column("monthday", sa.Integer),
    sa.Column("once_at", sa.DateTime(timezone=True)),
    sa.Column("recipients", sa.Text, nullable=False, default="[]"),
    sa.Column("status", sa.String(8), nullable=False, default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("next_run_at", sa.DateTime(timezone=True)),
    sa.Column("last_run_at", sa.DateTime(timezone=True)),
    sa.Column("last_status", sa.String(16)),
    sa.Column("last_error", sa.Text),
    sa.Column("last_file", sa.Text),
    sa.Column("last_rows", sa.Integer),
)

FORMATS = {"xlsx", "csv"}
RECURRENCES = {"daily", "weekly", "monthly", "once"}
STATUSES = {"active", "paused", "done"}
WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_EMAIL = re.compile(r"[^@\s,;<>()]+@[^@\s,;<>()]+\.[^@\s,;<>()'’]+")

_ready: set[int] = set()
_ready_lock = threading.Lock()
_due_lock = threading.Lock()
_LOCAL = timezone(timedelta(hours=float(os.environ.get("ALERT_TZ_OFFSET_HOURS", "3"))))
REPORT_DIR = Path(os.environ.get("REPORT_DIR", "/data/nanobaseai/bi/var/reports"))
KEEP_FILES = int(os.environ.get("REPORT_KEEP_FILES", "10"))


class ReportError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""


def ensure(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    v = _aware(v)
    return v.isoformat() if v else None


# ------------------------------------------------------------------ cümleyi çözme

_WD = {
    "pazartesi": 0, "salı": 1, "sali": 1, "çarşamba": 2, "carsamba": 2, "perşembe": 3, "persembe": 3,
    "cuma": 4, "cumartesi": 5, "pazar": 6,
}
# Cümleden düşen kalıplar: plan ve teslim sözleri. Kalan kısım veri sorusudur; kişi ekranda düzeltir.
_DROP = [
    r"\b(her|hergün)\s+(sabah|gün|akşam|öğlen|hafta|ay)(\s+(başı|sonu))?\b",
    r"\bgünlük\b|\bhaftalık\b|\baylık\b|\bhaftada\s+bir\b|\bayda\s+bir\b|\bbir\s+kez\b|\btek\s+sefer(lik)?\b",
    r"\bher\s+(pazartesi|salı|sali|çarşamba|carsamba|perşembe|persembe|cuma|cumartesi|pazar)(\s+(sabahı|günü))?\b",
    r"\b(pazartesi|salı|sali|çarşamba|carsamba|perşembe|persembe|cuma|cumartesi|pazar)(\s+(sabahı|günü))?\b",
    r"\bsaat\s+\d{1,2}([:.]\d{2})?['’]?(de|da|te|ta)?\b",
    r"\b\d{1,2}[:.]\d{2}['’]?(de|da|te|ta)?\b",
    r"\b\d{1,2}['’](de|da|te|ta)\b",
    r"\bayın\s+\d{1,2}['’]?(i|ı|u|ü|si|sı|ünde|inde|ında|unda)?\b",
    r"\bsabah(ları|leyin)?\b|\bakşam(ları)?\b|\böğlen\b",
    r"\b(bana|bize)\b",
    r"\b(e-?posta|mail|e-?mail)\s*(olarak|ile|yoluyla)?\s*(at|gönder|yolla|ilet)\b",
    r"\b(mail|e-?posta|e-?mail)(e|a|ye|ya|ime|ıma)?\b",
    r"\b(gönder|yolla|ilet|at|paylaş)(ir\s+misin|ebilir\s+misin|sin|in)?\b",
    r"\b(hazırla|hazırlayıp|oluştur|oluşturup|çıkar|çıkarıp|üret|üretip|yap|yapıp)(r\s+mısın|ır\s+mısın|bilir\s+misin|sın|sin)?\b",
    r"\b(bir|birer)\s+(excel|xlsx|csv|rapor|dosya|liste|tablo)\b",
    r"\b(excel|xlsx|csv)(['’]?(i|ı|e|a|de|da|ye|ya|ini|ıni|inde))?(\s+(olarak|dosyası|formatında|halinde|tablosu|raporu))?\b",
    r"\b(rapor|raporu|raporunu|raporunu|dosya|dosyası|dosyasını|liste|listesi|listesini|tablo|tablosu)\b",
    r"\b(olsun|olacak|olmalı|içinde|içeren|içersin|şeklinde|halinde|olarak|lütfen|rica ederim|ve|ile)\b",
    r"\b(adres(ine|lerine)?|kişi(ye|lere)?|ekibine|ekibe)\b",
]
_DROP_RE = [re.compile(p, re.IGNORECASE) for p in _DROP]


def parse_prompt(text: str) -> dict[str, Any]:
    """Türkçe cümleden plan: zaman, sıklık, alıcılar, biçim ve veri sorusu."""
    raw = " ".join(str(text or "").split())
    low = raw.lower()
    recipients = sorted({m.strip(".,;") for m in _EMAIL.findall(raw)})
    fmt = "csv" if re.search(r"\bcsv\b", low) and not re.search(r"\bexcel|xlsx\b", low) else "xlsx"

    at = None
    m = re.search(r"\b(\d{1,2})[:.](\d{2})\b", low)
    if m:
        at = (int(m.group(1)), int(m.group(2)))
    else:
        m = re.search(r"\bsaat\s+(\d{1,2})\b", low) or re.search(r"\b(\d{1,2})['’](de|da|te|ta)\b", low)
        if m:
            at = (int(m.group(1)), 0)
    if at is None:
        at = (12, 0) if "öğlen" in low else (18, 0) if "akşam" in low else (8, 0)
    hh, mm = at
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        hh, mm = 8, 0
    at_time = f"{hh:02d}:{mm:02d}"

    recurrence, weekday, monthday = "daily", None, None
    wd = next((v for k, v in _WD.items() if re.search(rf"\b{k}\b", low)), None)
    if re.search(r"\b(her\s+ay|aylık|ayda\s+bir|ayın\s+\d)", low):
        recurrence = "monthly"
        m = re.search(r"ayın\s+(\d{1,2})", low)
        monthday = int(m.group(1)) if m else 1
        monthday = max(1, min(28, monthday))
    elif wd is not None or re.search(r"\b(her\s+hafta|haftalık|haftada\s+bir)\b", low):
        recurrence = "weekly"
        weekday = wd if wd is not None else 0
    elif re.search(r"\b(bir\s+kez|tek\s+sefer|yarın|bugün)\b", low):
        recurrence = "once"

    q = raw
    for email in _EMAIL.findall(raw):
        q = q.replace(email, " ")
    for rx in _DROP_RE:
        q = rx.sub(" ", q)
    q = re.sub(r"\bher\b", " ", q, flags=re.IGNORECASE)  # "her ayın 1'inde" kalıntısı
    q = re.sub(r"\s*[,;:]\s*", " ", q)
    q = re.sub(r"\s+", " ", q).strip(" .,-–—'’\"")
    if len(q) < 3:
        q = raw
    title = q[:1].upper() + q[1:]
    return {
        "question": q,
        "title": title[:120],
        "recurrence": recurrence,
        "at": at_time,
        "weekday": weekday,
        "monthday": monthday,
        "recipients": recipients,
        "fmt": fmt,
    }


# ------------------------------------------------------------------ zaman


def next_run(recurrence: str, at_time: str, weekday: Optional[int], monthday: Optional[int],
             once_at: Optional[datetime], *, after: Optional[datetime] = None) -> Optional[datetime]:
    """Bir sonraki çalışma anı (UTC). `after`dan kesinlikle sonra."""
    after = _aware(after) or _now()
    if recurrence == "once":
        o = _aware(once_at)
        return o if o and o > after else None
    hh, mm = (int(x) for x in (at_time or "08:00").split(":"))
    local = after.astimezone(_LOCAL)
    cand = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if recurrence == "daily":
        if cand <= local:
            cand += timedelta(days=1)
    elif recurrence == "weekly":
        wd = int(weekday or 0)
        cand += timedelta(days=(wd - cand.weekday()) % 7)
        if cand <= local:
            cand += timedelta(days=7)
    elif recurrence == "monthly":
        md = max(1, min(28, int(monthday or 1)))
        cand = cand.replace(day=md)
        if cand <= local:
            y, mo = (cand.year + (cand.month // 12), cand.month % 12 + 1)
            cand = cand.replace(year=y, month=mo)
    else:
        return None
    return cand.astimezone(timezone.utc)


def when_label(rep: dict[str, Any]) -> str:
    r, at = rep["recurrence"], rep["at"]
    if r == "daily":
        return f"Her gün {at}"
    if r == "weekly":
        return f"Her {WEEKDAYS[int(rep.get('weekday') or 0)].lower()} {at}"
    if r == "monthly":
        return f"Her ayın {int(rep.get('monthday') or 1)}'i {at}"
    o = rep.get("onceAt")
    return f"Bir kez · {o[:16].replace('T', ' ') if o else at}"


# ------------------------------------------------------------------ kayıt


def _recipients(raw: Any) -> list[str]:
    items = raw if isinstance(raw, list) else re.split(r"[,;\s]+", str(raw or ""))
    out: list[str] = []
    for x in items:
        x = str(x).strip()
        if not x:
            continue
        if not _EMAIL.fullmatch(x):
            raise ReportError(f"«{x}» geçerli bir e-posta adresi değil.")
        if x.lower() not in {o.lower() for o in out}:
            out.append(x)
    return out


def _clean(body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not partial or "question" in body:
        q = " ".join(str(body.get("question") or "").split())
        if not q:
            raise ReportError("Raporun neyi listeleyeceği yazılmalı.")
        out["question"] = q[:2000]
    if not partial or "title" in body:
        t = " ".join(str(body.get("title") or body.get("question") or "").split())
        out["title"] = (t or "Adsız rapor")[:300]
    if "prompt" in body:
        out["prompt"] = str(body.get("prompt") or "")[:4000] or None
    if "sql" in body:
        out["sql"] = str(body.get("sql") or "")[:50000] or None
    if not partial or "fmt" in body:
        f = str(body.get("fmt") or "xlsx").lower()
        out["fmt"] = f if f in FORMATS else "xlsx"
    if not partial or "recurrence" in body:
        r = str(body.get("recurrence") or "daily").lower()
        if r not in RECURRENCES:
            raise ReportError("Sıklık günlük, haftalık, aylık ya da tek seferlik olmalı.")
        out["recurrence"] = r
    if not partial or "at" in body:
        at = str(body.get("at") or "08:00").strip()
        if not _HHMM.match(at):
            raise ReportError("Saat SS:DD biçiminde olmalı (örn. 08:00).")
        out["at_time"] = at
    if "weekday" in body:
        w = body.get("weekday")
        out["weekday"] = int(w) % 7 if w is not None and str(w) != "" else None
    if "monthday" in body:
        d = body.get("monthday")
        out["monthday"] = max(1, min(28, int(d))) if d is not None and str(d) != "" else None
    if "onceAt" in body:
        o = body.get("onceAt")
        try:
            out["once_at"] = datetime.fromisoformat(str(o)).astimezone(timezone.utc) if o else None
        except ValueError:
            raise ReportError("Tek seferlik tarih anlaşılamadı.") from None
    if not partial or "recipients" in body:
        out["recipients"] = json.dumps(_recipients(body.get("recipients")), ensure_ascii=False)
    if "status" in body:
        s = str(body.get("status") or "").lower()
        if s not in STATUSES:
            raise ReportError("Durum etkin, duraklatılmış ya da bitti olmalı.")
        out["status"] = s
    return out


def to_dict(row: Any) -> dict[str, Any]:
    d = {
        "id": row["id"],
        "title": row["title"],
        "prompt": row["prompt"] or "",
        "question": row["question"],
        "sql": row["sql"] or "",
        "fmt": row["fmt"],
        "recurrence": row["recurrence"],
        "at": row["at_time"],
        "weekday": row["weekday"],
        "monthday": row["monthday"],
        "onceAt": _iso(row["once_at"]),
        "recipients": json.loads(row["recipients"] or "[]"),
        "status": row["status"],
        "createdAt": _iso(row["created_at"]),
        "updatedAt": _iso(row["updated_at"]),
        "nextRunAt": _iso(row["next_run_at"]),
        "lastRunAt": _iso(row["last_run_at"]),
        "lastStatus": row["last_status"],
        "lastError": row["last_error"],
        "lastRows": row["last_rows"],
        "hasFile": bool(row["last_file"] and Path(row["last_file"]).exists()),
    }
    d["when"] = when_label(d)
    return d


def _scope(tenant: str, ds: str, user: Optional[str]):
    conds = [REPORTS.c.tenant_id == tenant, REPORTS.c.datasource_id == ds]
    if user is not None:
        conds.append(REPORTS.c.username == user)
    return conds


def list_reports(engine: sa.engine.Engine, tenant: str, ds: str, user: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(REPORTS).where(*_scope(tenant, ds, user)).order_by(REPORTS.c.created_at.desc())).mappings().all()
    return [to_dict(r) for r in rows]


def get_report(engine: sa.engine.Engine, tenant: str, ds: str, user: Optional[str], rid: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        row = c.execute(sa.select(REPORTS).where(REPORTS.c.id == rid, *_scope(tenant, ds, user))).mappings().first()
    return to_dict(row) if row else None


def _row(engine: sa.engine.Engine, rid: str) -> Any:
    with engine.connect() as c:
        return c.execute(sa.select(REPORTS).where(REPORTS.c.id == rid)).mappings().first()


def _with_next(vals: dict[str, Any], base: Optional[Any] = None) -> dict[str, Any]:
    g = lambda k: vals[k] if k in vals else (base[k] if base is not None else None)  # noqa: E731
    status = g("status") or "active"
    if status != "active":
        vals["next_run_at"] = None
        return vals
    vals["next_run_at"] = next_run(g("recurrence") or "daily", g("at_time") or "08:00", g("weekday"), g("monthday"), g("once_at"))
    if vals["next_run_at"] is None and (g("recurrence") == "once"):
        raise ReportError("Tek seferlik raporun tarihi geçmiş; ileri bir zaman verin.")
    return vals


def create_report(engine: sa.engine.Engine, tenant: str, ds: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    vals = _clean(body, partial=False)
    vals.setdefault("status", "active")
    if vals["recurrence"] == "once" and not vals.get("once_at"):
        # Tek seferlik: bugün o saat geçmediyse bugün, geçtiyse yarın.
        vals["once_at"] = next_run("daily", vals["at_time"], None, None, None)
    now = _now()
    rid = f"rpt-{uuid.uuid4().hex[:12]}"
    vals = _with_next(vals)
    vals.update(id=rid, tenant_id=tenant, datasource_id=ds, username=user, created_at=now, updated_at=now)
    with engine.begin() as c:
        c.execute(REPORTS.insert().values(**vals))
    return get_report(engine, tenant, ds, user, rid)  # type: ignore[return-value]


def update_report(engine: sa.engine.Engine, tenant: str, ds: str, user: str, rid: str, body: dict[str, Any]) -> Optional[dict[str, Any]]:
    base = _row(engine, rid)
    if not base or base["username"] != user or base["tenant_id"] != tenant:
        return None
    vals = _clean(body, partial=True)
    if base["status"] == "done" and vals.get("status") == "active" and base["recurrence"] == "once" and "onceAt" not in body:
        vals["once_at"] = next_run("daily", vals.get("at_time") or base["at_time"], None, None, None)
    vals = _with_next(vals, base)
    vals["updated_at"] = _now()
    with engine.begin() as c:
        c.execute(REPORTS.update().where(REPORTS.c.id == rid).values(**vals))
    return get_report(engine, tenant, ds, user, rid)


def delete_report(engine: sa.engine.Engine, tenant: str, ds: str, user: str, rid: str) -> bool:
    with engine.begin() as c:
        n = c.execute(REPORTS.delete().where(REPORTS.c.id == rid, *_scope(tenant, ds, user))).rowcount
    if n:
        d = REPORT_DIR / rid
        for p in d.glob("*"):
            p.unlink(missing_ok=True)
        if d.exists():
            d.rmdir()
    return bool(n)


def file_of(engine: sa.engine.Engine, tenant: str, ds: str, user: str, rid: str) -> Optional[tuple[Path, str]]:
    row = _row(engine, rid)
    if not row or row["username"] != user or not row["last_file"]:
        return None
    p = Path(row["last_file"])
    if not p.exists() or p.parent != REPORT_DIR / rid:
        return None
    return p, mimetypes.guess_type(p.name)[0] or "application/octet-stream"


# ------------------------------------------------------------------ dosya


def _safe_name(title: str) -> str:
    t = title.lower()
    for a, b in (("ç", "c"), ("ğ", "g"), ("ı", "i"), ("ö", "o"), ("ş", "s"), ("ü", "u")):
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return (t or "rapor")[:60]


def build_file(rid: str, title: str, fmt: str, columns: list[dict[str, Any]], rows: list[dict[str, Any]], now: datetime) -> Path:
    d = REPORT_DIR / rid
    d.mkdir(parents=True, exist_ok=True)
    stamp = now.astimezone(_LOCAL).strftime("%Y%m%d-%H%M")
    names = [c["name"] for c in columns]
    if fmt == "csv":
        path = d / f"{_safe_name(title)}-{stamp}.csv"
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
        w.writerow(names)
        for r in rows:
            w.writerow([("" if r.get(n) is None else str(r.get(n)).replace(".", ",") if isinstance(r.get(n), float) else r.get(n)) for n in names])
        path.write_text("﻿" + buf.getvalue(), encoding="utf-8")
    else:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        wb = Workbook(write_only=False)
        ws = wb.active
        ws.title = "Rapor"
        ws.append(names)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="7C5CFF")
            cell.alignment = Alignment(vertical="center")
        widths = [min(48, max(8, len(n) + 2)) for n in names]
        for r in rows:
            vals = []
            for i, n in enumerate(names):
                v = r.get(n)
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                vals.append(v)
                widths[i] = min(48, max(widths[i], len(str(v if v is not None else "")) + 2))
            ws.append(vals)
        numeric = {c["name"] for c in columns if str(c.get("type", "")).lower() in ("float", "int", "integer", "decimal", "number", "numeric", "double", "money", "bigint")}
        for i, n in enumerate(names, start=1):
            ws.column_dimensions[get_column_letter(i)].width = widths[i - 1]
            if n in numeric:
                for cell in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                    cell[0].number_format = "#,##0.00"
        ws.freeze_panes = "A2"
        if names:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(names))}{max(1, len(rows) + 1)}"
        path = d / f"{_safe_name(title)}-{stamp}.xlsx"
        wb.save(path)
    # Yalnız son N dosya kalır.
    files = sorted(d.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[KEEP_FILES:]:
        old.unlink(missing_ok=True)
    return path


# ------------------------------------------------------------------ e-posta


def send_file(rep: dict[str, Any], path: Path, rows: int, now: datetime, link: str = "") -> str:
    to = rep.get("recipients") or []
    if not to:
        return "no_recipient"
    cfg = alerts_mod.smtp_settings()
    if not cfg:
        return "no_smtp"
    msg = EmailMessage()
    msg["Subject"] = f"ZEKİ rapor: {rep['title']}"
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(to)
    lines = [
        f"«{rep['title']}» raporu ekte.",
        "",
        f"Soru: {rep['question']}",
        f"Satır: {rows:,}".replace(",", "."),
        f"Üretim: {now.astimezone(_LOCAL).strftime('%d.%m.%Y %H:%M')}",
        f"Plan: {rep['when']}",
    ]
    if link:
        lines += ["", f"Planlı raporlar: {link}"]
    msg.set_content("\n".join(lines))
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    maintype, subtype = ctype.split("/", 1)
    msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
    try:
        if cfg["ssl"]:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=30, context=ssl.create_default_context()) as s:
                if cfg["user"]:
                    s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as s:
                if cfg["starttls"]:
                    s.starttls(context=ssl.create_default_context())
                if cfg["user"]:
                    s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
        return "sent"
    except Exception as e:  # noqa: BLE001
        log.warning("reports: e-posta gönderilemedi (%s): %s", rep["id"], e)
        return "failed"


# ------------------------------------------------------------------ çalıştırma

Asker = Callable[[str], dict[str, Any]]
Fetcher = Callable[[str], tuple[list[dict[str, Any]], list[dict[str, Any]]]]


def run_report(engine: sa.engine.Engine, rid: str, asker: Asker, fetcher: Fetcher, *, manual: bool,
               now: Optional[datetime] = None, link: str = "") -> dict[str, Any]:
    """Soruyu yeniden sorar, tüm satırları dosyaya yazar, gönderir; sonucu kayda işler."""
    now = now or _now()
    base = _row(engine, rid)
    if not base:
        raise ReportError("Rapor bulunamadı.")
    rep = to_dict(base)
    upd: dict[str, Any] = {"last_run_at": now}
    try:
        answer = asker(rep["question"])
        sql = str(answer.get("sql") or rep["sql"] or "").strip()
        if not sql:
            raise ReportError(str(answer.get("summary") or answer.get("explanation") or "Motor bu soruya SQL üretmedi."))
        columns, rows = fetcher(sql)
        path = build_file(rid, rep["title"], rep["fmt"], columns, rows, now)
        status = send_file(rep, path, len(rows), now, link)
        upd.update(sql=sql[:50000], last_file=str(path), last_rows=len(rows), last_status=status, last_error=None)
    except Exception as e:  # noqa: BLE001
        msg = str(e) if isinstance(e, ReportError) else f"Rapor üretilemedi: {str(e)[:400]}"
        upd.update(last_status="failed", last_error=msg[:1000])
    if not manual:
        if base["recurrence"] == "once":
            upd.update(status="done", next_run_at=None)
        else:
            upd["next_run_at"] = next_run(base["recurrence"], base["at_time"], base["weekday"], base["monthday"], base["once_at"], after=now)
    with engine.begin() as c:
        c.execute(REPORTS.update().where(REPORTS.c.id == rid).values(**upd))
    return to_dict(_row(engine, rid))


def run_due(engine: sa.engine.Engine, tenant: str, ds: str, asker: Asker, fetcher: Fetcher, *,
            now: Optional[datetime] = None, link: str = "") -> dict[str, Any]:
    now = now or _now()
    summary: dict[str, Any] = {"due": 0, "sent": 0, "produced": 0, "errors": []}
    with _due_lock:
        with engine.connect() as c:
            rows = c.execute(sa.select(REPORTS.c.id, REPORTS.c.username).where(
                *_scope(tenant, ds, None), REPORTS.c.status == "active",
                REPORTS.c.next_run_at.is_not(None), REPORTS.c.next_run_at <= now)).mappings().all()
        for r in rows:
            summary["due"] += 1
            out = run_report(engine, r["id"], asker, fetcher, manual=False, now=now, link=link)
            if out["lastStatus"] == "failed":
                summary["errors"].append({"id": r["id"], "user": r["username"], "error": out["lastError"]})
            else:
                summary["produced"] += 1
                if out["lastStatus"] == "sent":
                    summary["sent"] += 1
    return summary
