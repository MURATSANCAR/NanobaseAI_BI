"""Uyarı kuralları: bir soru, bir koşul, bir eşik, alıcılar. Kontrol bu serviste yapılır.

Kural bir SQL değil bir sorudur. "Bu ayın iade tutarı" her kontrolde yeniden sorulur; böylece "bu ay"
kontrolün yapıldığı ayı anlatır, kuralın kurulduğu günün tarihlerine donmaz. SQL yalnız gösterilir.

Bildirim kenarda gider: kural eşiği ilk aştığında. Hâlâ aşıyorsa `ALERT_REMIND_HOURS` sonra bir kez
daha hatırlatır. Gönderim olmadıysa (e-posta ayarı yok, sunucu hata verdi) bir sonraki kontrolde yeniden
denenir — e-posta ayarı sonradan eklense de bekleyen uyarı kaybolmaz.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import smtplib
import ssl
import threading
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Callable, Optional

import sqlalchemy as sa

log = logging.getLogger(__name__)

_md = sa.MetaData()

RULES = sa.Table(
    "semantic_alert_rules", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("datasource_id", sa.String(80), nullable=False),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("question", sa.Text, nullable=False),
    sa.Column("sql", sa.Text, nullable=False),
    sa.Column("column_name", sa.String(200)),
    sa.Column("condition", sa.String(8), nullable=False),
    sa.Column("threshold", sa.Float, nullable=False),
    sa.Column("recipients", sa.Text, nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("created_by", sa.String(120)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_value", sa.Float),
    sa.Column("last_checked_at", sa.DateTime(timezone=True)),
    sa.Column("last_triggered_at", sa.DateTime(timezone=True)),
    sa.Column("state", sa.String(16), nullable=False),
    sa.Column("last_error", sa.Text),
    sa.Column("last_notified_at", sa.DateTime(timezone=True)),
    sa.Column("last_notify", sa.String(16)),
)

EVENTS = sa.Table(
    "semantic_alert_events", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("rule_id", sa.String(40), nullable=False, index=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("value", sa.Float),
    sa.Column("triggered", sa.Boolean, nullable=False),
    sa.Column("notify", sa.String(16)),
    sa.Column("error", sa.Text),
)

CONDITIONS = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}
_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")

_ready: set[int] = set()
_ready_lock = threading.Lock()


class AlertError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek, düz Türkçe bir hata."""


def ensure(engine: sa.engine.Engine) -> None:
    """Tablolar yoksa kurar. Motor başına bir kez; var olan tabloya dokunmaz."""
    with _ready_lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    """SQLite saat dilimini saklamaz; okunan naif değer UTC'dir."""
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    v = _aware(v)
    return v.isoformat() if v else None


def to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "question": row["question"],
        "sql": row["sql"],
        "column": row["column_name"],
        "condition": row["condition"],
        "threshold": row["threshold"],
        "recipients": json.loads(row["recipients"] or "[]"),
        "status": row["status"],
        "created_by": row["created_by"],
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
        "last_value": row["last_value"],
        "last_checked_at": _iso(row["last_checked_at"]),
        "last_triggered_at": _iso(row["last_triggered_at"]),
        "state": row["state"],
        "last_error": row["last_error"],
        "last_notified_at": _iso(row["last_notified_at"]),
        "last_notify": row["last_notify"],
    }


def _recipients(raw: Any) -> list[str]:
    items = raw if isinstance(raw, list) else re.split(r"[,;\s]+", str(raw or ""))
    out: list[str] = []
    for x in items:
        x = str(x).strip()
        if not x:
            continue
        if not _EMAIL.match(x):
            raise AlertError(f"«{x}» geçerli bir e-posta adresi değil.")
        if x.lower() not in {o.lower() for o in out}:
            out.append(x)
    return out


def _threshold(raw: Any) -> float:
    try:
        v = float(str(raw).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        raise AlertError("Eşik bir sayı olmalı.") from None
    if not math.isfinite(v):
        raise AlertError("Eşik bir sayı olmalı.")
    return v


def _clean(body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not partial or "question" in body or "sql" in body:
        q = str(body.get("question") or "").strip()
        sql = str(body.get("sql") or "").strip()
        if not q and not sql:
            raise AlertError("Kuralın neyi ölçeceği yazılmalı.")
        out["question"], out["sql"] = q[:2000], sql[:20000]
    if not partial or "title" in body:
        title = str(body.get("title") or body.get("question") or "").strip()
        if not title:
            raise AlertError("Kurala bir ad verin.")
        out["title"] = title[:300]
    if not partial or "condition" in body:
        c = str(body.get("condition") or "").strip().lower()
        if c not in CONDITIONS:
            raise AlertError("Koşul büyüktür, büyük eşittir, küçüktür ya da küçük eşittir olmalı.")
        out["condition"] = c
    if not partial or "threshold" in body:
        out["threshold"] = _threshold(body.get("threshold"))
    if not partial or "recipients" in body:
        out["recipients"] = json.dumps(_recipients(body.get("recipients")), ensure_ascii=False)
    if "column" in body:
        out["column_name"] = (str(body.get("column") or "").strip() or None)
    if "status" in body:
        s = str(body.get("status") or "").strip().lower()
        if s not in ("active", "paused"):
            raise AlertError("Durum etkin ya da duraklatılmış olmalı.")
        out["status"] = s
    return out


def list_rules(engine: sa.engine.Engine, tenant: str, ds: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(RULES).where(RULES.c.tenant_id == tenant, RULES.c.datasource_id == ds)
                         .order_by(RULES.c.created_at.desc())).mappings().all()
    return [to_dict(r) for r in rows]


def get_rule(engine: sa.engine.Engine, tenant: str, ds: str, rule_id: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        row = c.execute(sa.select(RULES).where(RULES.c.id == rule_id, RULES.c.tenant_id == tenant,
                                               RULES.c.datasource_id == ds)).mappings().first()
    return to_dict(row) if row else None


def create_rule(engine: sa.engine.Engine, tenant: str, ds: str, body: dict[str, Any], *, by: Optional[str] = None) -> dict[str, Any]:
    vals = _clean(body, partial=False)
    now = _now()
    rid = f"alr-{uuid.uuid4().hex[:12]}"
    vals.update(id=rid, tenant_id=tenant, datasource_id=ds, status=vals.get("status", "active"),
                column_name=vals.get("column_name") or (str(body.get("column") or "").strip() or None),
                created_by=(str(by or body.get("created_by") or "").strip()[:120] or None),
                created_at=now, updated_at=now, state="unknown")
    with engine.begin() as c:
        c.execute(RULES.insert().values(**vals))
    return get_rule(engine, tenant, ds, rid)  # type: ignore[return-value]


def update_rule(engine: sa.engine.Engine, tenant: str, ds: str, rule_id: str, body: dict[str, Any]) -> Optional[dict[str, Any]]:
    vals = _clean(body, partial=True)
    if not vals:
        return get_rule(engine, tenant, ds, rule_id)
    vals["updated_at"] = _now()
    # Eşik ya da koşul değiştiyse eski "tetiklendi" hâli yeni kuralı anlatmaz; bir sonraki kontrol karar verir.
    if {"threshold", "condition", "question", "sql"} & vals.keys():
        vals.update(state="unknown", last_notify=None)
    with engine.begin() as c:
        n = c.execute(RULES.update().where(RULES.c.id == rule_id, RULES.c.tenant_id == tenant,
                                           RULES.c.datasource_id == ds).values(**vals)).rowcount
    return get_rule(engine, tenant, ds, rule_id) if n else None


def delete_rule(engine: sa.engine.Engine, tenant: str, ds: str, rule_id: str) -> bool:
    with engine.begin() as c:
        n = c.execute(RULES.delete().where(RULES.c.id == rule_id, RULES.c.tenant_id == tenant,
                                           RULES.c.datasource_id == ds)).rowcount
        if n:
            c.execute(EVENTS.delete().where(EVENTS.c.rule_id == rule_id))
    return bool(n)


def events(engine: sa.engine.Engine, rule_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(EVENTS).where(EVENTS.c.rule_id == rule_id)
                         .order_by(EVENTS.c.at.desc(), EVENTS.c.id.desc()).limit(max(1, limit))).mappings().all()
    return [{"at": _iso(r["at"]), "value": r["value"], "triggered": bool(r["triggered"]),
             "notify": r["notify"], "error": r["error"]} for r in rows]


# ------------------------------------------------------------------ ölçüm


def _number(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def value_of(answer: dict[str, Any], column: Optional[str]) -> float:
    """Cevaptan kuralın tek sayısını çıkarır. Birden çok satır bir değer değildir; tahmin edilmez."""
    recs = answer.get("records")
    if recs is None:
        raise AlertError(str(answer.get("summary") or answer.get("explanation") or "Motor bu soruya bir değer döndürmedi."))
    if not recs:
        raise AlertError("Sorgu satır döndürmedi.")
    if len(recs) > 1:
        raise AlertError(f"Sorgu {len(recs)} satır döndürdü; uyarı tek bir değer ister. Soruyu tek sayıya indirin.")
    row = recs[0]
    if column and column in row:
        v = _number(row[column])
        if v is None:
            raise AlertError(f"«{column}» sayısal bir değer değil.")
        return v
    nums = [v for v in (_number(x) for x in row.values()) if v is not None]
    if len(nums) != 1:
        raise AlertError("Cevapta tek bir sayı yok; hangi kolonun izleneceğini belirtin.")
    return nums[0]


def breached(value: float, condition: str, threshold: float) -> bool:
    return {"gt": value > threshold, "gte": value >= threshold,
            "lt": value < threshold, "lte": value <= threshold}[condition]


Runner = Callable[[dict[str, Any]], dict[str, Any]]
Notifier = Callable[[dict[str, Any], float], str]


def check(engine: sa.engine.Engine, tenant: str, ds: str, runner: Runner, notifier: Notifier, *,
          only: Optional[str] = None, now: Optional[datetime] = None,
          remind: Optional[timedelta] = None) -> dict[str, Any]:
    """Etkin kuralları ölçer, durumlarını yazar, gerekiyorsa bildirir."""
    now = now or _now()
    remind = remind if remind is not None else timedelta(hours=float(os.environ.get("ALERT_REMIND_HOURS", "24")))
    q = sa.select(RULES).where(RULES.c.tenant_id == tenant, RULES.c.datasource_id == ds)
    q = q.where(RULES.c.id == only) if only else q.where(RULES.c.status == "active")
    with engine.connect() as c:
        rules = [to_dict(r) for r in c.execute(q).mappings().all()]
    summary = {"checked": 0, "triggered": 0, "notified": 0, "errors": []}
    for rule in rules:
        summary["checked"] += 1
        upd: dict[str, Any] = {"last_checked_at": now}
        ev: dict[str, Any] = {"rule_id": rule["id"], "at": now, "triggered": False}
        try:
            answer = runner(rule)
            value = value_of(answer, rule["column"])
            trig = breached(value, rule["condition"], float(rule["threshold"]))
            upd.update(last_value=value, state="triggered" if trig else "ok", last_error=None)
            ev.update(value=value, triggered=trig)
            if answer.get("sql") and not rule["question"]:
                pass
            elif answer.get("sql"):
                upd["sql"] = str(answer["sql"])[:20000]
            if trig:
                summary["triggered"] += 1
                was = rule["state"] == "triggered"
                if not was:
                    upd["last_triggered_at"] = now
                last_sent = _aware(datetime.fromisoformat(rule["last_notified_at"])) if rule["last_notified_at"] else None
                due = (not was) or rule["last_notify"] != "sent" or (last_sent is not None and now - last_sent >= remind)
                if due:
                    result = notifier(rule, value)
                    upd["last_notify"] = result
                    ev["notify"] = result
                    if result == "sent":
                        upd["last_notified_at"] = now
                        summary["notified"] += 1
            else:
                upd["last_notify"] = None
        except Exception as e:  # noqa: BLE001 — bir kuralın hatası ötekileri durdurmaz
            msg = str(e) if isinstance(e, AlertError) else f"Kontrol başarısız: {str(e)[:300]}"
            upd.update(state="error", last_error=msg[:500])
            ev["error"] = msg[:500]
            summary["errors"].append({"id": rule["id"], "error": msg[:300]})
        with engine.begin() as c:
            c.execute(RULES.update().where(RULES.c.id == rule["id"]).values(**upd))
            c.execute(EVENTS.insert().values(**ev))
    return summary


# ------------------------------------------------------------------ e-posta


def smtp_settings() -> Optional[dict[str, Any]]:
    host = os.environ.get("ALERT_SMTP_HOST", "").strip()
    sender = (os.environ.get("ALERT_SMTP_FROM") or os.environ.get("ALERT_SMTP_USER") or "").strip()
    if not host or not sender:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("ALERT_SMTP_PORT", "587")),
        "user": os.environ.get("ALERT_SMTP_USER", "").strip(),
        "password": os.environ.get("ALERT_SMTP_PASSWORD", ""),
        "sender": sender,
        "ssl": os.environ.get("ALERT_SMTP_SSL", "0") == "1",
        "starttls": os.environ.get("ALERT_SMTP_STARTTLS", "1") != "0",
    }


def email_status() -> dict[str, Any]:
    cfg = smtp_settings()
    return {"configured": bool(cfg), "sender": cfg["sender"] if cfg else None}


def _tr(v: float) -> str:
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s[:-3] if s.endswith(",00") else s


def render(rule: dict[str, Any], value: float, link: str = "") -> tuple[str, str]:
    subject = f"ZEKİ uyarı: {rule['title']}"
    lines = [
        f"«{rule['title']}» kuralı eşiği aştı.",
        "",
        f"Şu anki değer: {_tr(value)}",
        f"Koşul: değer {CONDITIONS[rule['condition']]} {_tr(float(rule['threshold']))}",
    ]
    if rule.get("question"):
        lines.append(f"Ölçülen: {rule['question']}")
    lines += ["", f"Kontrol zamanı: {datetime.now().strftime('%d.%m.%Y %H:%M')}"]
    if link:
        lines += ["", f"Ayrıntı: {link}"]
    return subject, "\n".join(lines)


def email_notifier(link: str = "") -> Notifier:
    def send(rule: dict[str, Any], value: float) -> str:
        to = rule.get("recipients") or []
        if not to:
            return "no_recipient"
        cfg = smtp_settings()
        if not cfg:
            return "no_smtp"
        subject, text = render(rule, value, link)
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, cfg["sender"], ", ".join(to)
        msg.set_content(text)
        try:
            ctx = ssl.create_default_context()
            server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20, context=ctx) if cfg["ssl"]
                      else smtplib.SMTP(cfg["host"], cfg["port"], timeout=20))
            with server as s:
                if not cfg["ssl"] and cfg["starttls"]:
                    s.starttls(context=ctx)
                if cfg["user"]:
                    s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
            return "sent"
        except Exception as e:  # noqa: BLE001
            log.warning("alert e-posta gönderilemedi (%s): %s", rule.get("id"), e)
            return "failed"
    return send
