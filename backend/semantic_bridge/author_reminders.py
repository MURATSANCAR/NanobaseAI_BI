"""M7 hatırlatmaları: yazar ilişkilerinde kişi başına günde tek e-posta özeti.

Özetin içinde (kişinin kendi işleri — yazdığı, katılımcısı olduğu ya da kartın sorumlusu olduğu):
- bugün ve yarınki randevular,
- tarihi geçip notu girilmemiş randevular (yalnız randevuyu yazana: notu yalnız o yazabilir),
- tarihi geçmiş ve bugün vadesi gelen açık «sıradaki adım»lar (gizli notun adımı yalnız görebilenlere).

Boş özet gönderilmez. Aynı gün ikinci kez gönderilmez (`semantic_author_reminders`, kişi × gün); gönderilemeyen bir
sonraki turda yeniden denenir. Kişi Randevular ekranından kapatabilir (tercih `author_reminders` = false). Alıcı adresi
kişi rehberinden (CRM kullanıcısının e-postası); izinli alan adı süzgeci uyarılarla aynı (`ALERT_RECIPIENT_DOMAINS`).
Yalnız yayınevi içi kişilere gider; yazara ya da dışarıya hiçbir şey gönderilmez. Gizli notun konusu ve metni
e-postaya girmez.
"""
from __future__ import annotations

import json
import logging
import ssl
import smtplib
import threading
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import author_relations as R

log = logging.getLogger("semantic.author_reminders")
_md = sa.MetaData()

SENT = sa.Table(
    "semantic_author_reminders", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("username", sa.String(120), primary_key=True),
    sa.Column("day", sa.String(10), primary_key=True),
    sa.Column("email", sa.String(200), nullable=False),
    sa.Column("items", sa.Integer, nullable=False),
    sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
)
PREF_DS = "authors"
PREF_KEY = "author_reminders"

_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _people_of(m: Any, card: Any) -> set[str]:
    parts = {str(p.get("username") or "").lower() for p in R._json(m.participants_json) if isinstance(p, dict)}
    out = {m.created_by.lower(), *parts}
    if card is not None and card.owner:
        out.add(card.owner.lower())
    return {u for u in out if u}


def digest_meetings_stmt(tenant: str, today: date):
    """Özetin randevuları: planlanan randevular + tarihi bugüne gelmiş kapanmamış sıradaki adımlar."""
    return sa.select(R.MEETINGS).where(
        R.MEETINGS.c.tenant_id == tenant, R.MEETINGS.c.status != "iptal",
        sa.or_(R.MEETINGS.c.status == "planlandi",
               sa.and_(R.MEETINGS.c.next_step.isnot(None), R.MEETINGS.c.next_done.is_(False),
                       R.MEETINGS.c.next_due.isnot(None), R.MEETINGS.c.next_due <= today))
    ).order_by(R.MEETINGS.c.starts_at)


def digests(engine: sa.engine.Engine, tenant: str, now: Optional[datetime] = None) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Kişi başına özet: {kullanıcı: {"randevu": [...], "not": [...], "adim": [...]}}. Salt okuma."""
    now = now or R._now()
    today = now.astimezone(R.TZ).date()
    tomorrow_end = datetime.combine(today + timedelta(days=2), datetime.min.time(), tzinfo=R.TZ).astimezone(timezone.utc)
    with engine.connect() as c:
        cards = {r.id: r for r in c.execute(R.cards_stmt(tenant)).fetchall()}
        rows = c.execute(digest_meetings_stmt(tenant, today)).fetchall()
    out: dict[str, dict[str, list[dict[str, Any]]]] = {}

    def add(user: str, kind: str, item: dict[str, Any]) -> None:
        out.setdefault(user, {"randevu": [], "not": [], "adim": []})[kind].append(item)

    for m in rows:
        card = cards.get(m.card_id)
        if card is None:
            continue
        day, hhmm = R._local_parts(m.starts_at)
        starts = R._utc(m.starts_at)
        ends = starts + timedelta(minutes=m.minutes or 60)
        for u in _people_of(m, card):
            visible = R._visible(m, u, False)
            topic = m.topic if visible else "Gizli görüşme"
            if m.status == "planlandi" and now <= starts < tomorrow_end:
                add(u, "randevu", {"card": card.name, "cardId": card.id, "date": day, "time": hhmm, "topic": topic,
                                   "where": m.room_name or m.location or R.CHANNELS.get(m.channel, m.channel)})
            elif m.status == "planlandi" and ends < now and u == m.created_by.lower():
                add(u, "not", {"card": card.name, "cardId": card.id, "date": day, "time": hhmm, "topic": topic})
            if (m.status == "yapildi" and m.next_step and not m.next_done and m.next_due and m.next_due <= today
                    and visible):
                add(u, "adim", {"card": card.name, "cardId": card.id, "step": m.next_step, "due": m.next_due.isoformat(),
                                "late": m.next_due < today})
    return out


def _fmt_day(d: str) -> str:
    y, m, dd = d.split("-")
    return f"{dd}.{m}.{y}"


def render(user_display: str, items: dict[str, list[dict[str, Any]]], link: str, today: date) -> tuple[str, str]:
    n = sum(len(v) for v in items.values())
    subject = f"ZEKİ AI · Yazar ilişkileri: bugün {n} iş"
    lines = [f"Merhaba {user_display},", "", "Yazar ilişkilerinde sizi bekleyenler:"]
    if items["randevu"]:
        lines += ["", "Randevular (bugün ve yarın)"]
        for r in items["randevu"]:
            when = "Bugün" if r["date"] == today.isoformat() else "Yarın"
            lines.append(f"  • {when} {r['time']} — {r['card']}: {r['topic']} ({r['where']})")
    if items["not"]:
        lines += ["", "Notu girilmemiş randevular"]
        for r in items["not"]:
            lines.append(f"  • {_fmt_day(r['date'])} {r['time']} — {r['card']}: {r['topic']}")
    if items["adim"]:
        lines += ["", "Sıradaki adımlar"]
        for r in sorted(items["adim"], key=lambda x: x["due"]):
            tag = "gecikti" if r["late"] else "bugün"
            lines.append(f"  • {r['card']}: {r['step']} ({_fmt_day(r['due'])}, {tag})")
    if link:
        lines += ["", f"Randevular ekranı: {link}"]
    lines += ["", "Bu e-postayı Randevular ekranındaki «Sabah e-posta özeti» seçeneğinden kapatabilirsiniz."]
    return subject, "\n".join(lines)


def _send(cfg: dict[str, Any], to: str, subject: str, text: str) -> None:
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, cfg["sender"], to
    msg.set_content(text)
    ctx = ssl.create_default_context()
    server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20, context=ctx) if cfg["ssl"]
              else smtplib.SMTP(cfg["host"], cfg["port"], timeout=20))
    with server as s:
        if not cfg["ssl"] and cfg["starttls"]:
            s.starttls(context=ctx)
        if cfg["user"]:
            s.login(cfg["user"], cfg["password"])
        s.send_message(msg)


def enabled_for(engine: sa.engine.Engine, tenant: str, user: str) -> bool:
    from semantic_bridge import prefs
    prefs.ensure(engine)
    v = prefs.get(engine, tenant, PREF_DS, user, PREF_KEY)["value"]
    return v is not False


def run_due(engine: sa.engine.Engine, tenant: str, directory: Callable[[], dict[str, dict[str, str]]], *,
            link: str = "", now: Optional[datetime] = None, dry_run: bool = False, not_before: str = "08:15",
            send: Optional[Callable[[dict[str, Any], str, str, str], None]] = None) -> dict[str, Any]:
    """Günün özetlerini gönderir. `directory()` → {kullanıcı: {"email", "name"}} (kişi rehberi).
    Dönüş: kişi başına sonuç (gönderildi / zaten gönderildi / kapalı / adres yok / izin dışı / hata)."""
    from semantic_bridge import alerts
    ensure(engine)
    now = now or R._now()
    local = now.astimezone(R.TZ)
    today = local.date()
    # Zamanlayıcı sık çağırabilir (müşteri ortamında 15 dk'lık iş döngüsü): özet günün bu saatinden önce gitmez.
    try:
        hh, mm = (int(x) for x in (not_before or "08:15").split(":"))
    except ValueError:
        hh, mm = 8, 15
    if not dry_run and (local.hour, local.minute) < (hh, mm):
        return {"day": today.isoformat(), "skipped": f"özet saati ({hh:02d}:{mm:02d}) gelmedi", "sent": 0, "users": {}}
    per_user = digests(engine, tenant, now)
    cfg = alerts.smtp_settings()
    people = directory() if per_user else {}
    report: dict[str, Any] = {"day": today.isoformat(), "smtp": bool(cfg), "users": {}}
    with engine.connect() as c:
        done = {r.username for r in c.execute(sa.select(SENT.c.username).where(SENT.c.tenant_id == tenant,
                                                                               SENT.c.day == today.isoformat())).fetchall()}
    for user, items in sorted(per_user.items()):
        n = sum(len(v) for v in items.values())
        if user in done:
            report["users"][user] = "zaten gönderildi"
            continue
        if not enabled_for(engine, tenant, user):
            report["users"][user] = "kişi kapattı"
            continue
        person = people.get(user) or {}
        email = (person.get("email") or "").strip()
        if not email:
            report["users"][user] = "rehberde e-posta yok"
            continue
        try:
            email = alerts._recipients([email])[0]
        except Exception as e:  # noqa: BLE001 — izinli alan adında değil
            report["users"][user] = f"izin dışı adres: {e}"
            continue
        if dry_run:
            report["users"][user] = f"gönderilecek ({n} iş)"
            continue
        if not cfg:
            report["users"][user] = "e-posta sunucusu tanımlı değil"
            continue
        subject, text = render(person.get("name") or user, items, link, today)
        try:
            (send or _send)(cfg, email, subject, text)
        except Exception as e:  # noqa: BLE001 — bir sonraki turda yeniden denenir
            log.warning("author reminder %s gönderilemedi: %s", user, e)
            report["users"][user] = "gönderilemedi"
            continue
        with engine.begin() as c:
            c.execute(SENT.insert().values(tenant_id=tenant, username=user, day=today.isoformat(), email=email,
                                           items=n, sent_at=R._now()))
        report["users"][user] = f"gönderildi ({n} iş)"
    report["sent"] = sum(1 for v in report["users"].values() if v.startswith("gönderildi"))
    return report
