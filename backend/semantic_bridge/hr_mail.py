"""İK e-posta bildirimleri: tek kuyruk (`semantic_hr_mail_outbox`), tek gönderici iş, kişi tercihi.

M60 planı (docs/analiz/kullanici-ihtiyaclari/M60-izin-yonetimi-ve-ik-bildirimleri.md §5):
- Yalnız **şirket içi** alıcı: alan adı `HR_MAIL_DOMAINS` listesinde olmalı (varsayılan `timas.com.tr`). Kişisel adres
  (gmail vb.) kuyruğa hiç girmez; satır «alıcı yok» diye kapanır, bildirim portalda kalır.
- Gövdede yalnız olay, tarih ve portal bağlantısı; T.C., IBAN, sağlık, izin türünün hassas adı, belge eki yok. Bu
  modül metni denetlemez — çağıran işlev metni böyle kurar (`hr_leave.mail_*`, `hr_portal` evrak olayları).
- Kip (`HR_MAIL_MODE`): `kapali` (varsayılan; kuyruğa «kapalı» diye yazılır, gönderilmez), `kaydet` (kuyruğa yazılır,
  gönderilmez — test sunucusu), `gonder`. Ayar Yönetim/ekran > env (`admin.conf`).
- Kişi Profilim'den bildirimi kapatabilir (`semantic_hr_mail_prefs`); onay bekleyen yöneticiye/İK'ya giden iş e-postası
  (`zorunlu=True`) kapatılamaz.
- Gönderim: `run_outbox()` 5 dakikada bir (`timas-hr-mail.timer` → `POST /api/v1/hr/mail/run-due`), `budget_api._send_mail`
  ile; başarısız satır 3 kez denenir.
"""
from __future__ import annotations

import logging
import threading
import weakref
from datetime import timedelta
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.hr_core import clean, iso, now

log = logging.getLogger("semantic_bridge.hr.mail")

_md = sa.MetaData()
_ready: "weakref.WeakSet[sa.engine.Engine]" = weakref.WeakSet()
_lock = threading.Lock()
MAX_TRIES = 3
MODES = {"kapali": "Kapalı (hiç gönderilmez)", "kaydet": "Yalnız kaydet (deneme; gönderilmez)", "gonder": "Gönder"}
STATE = {"bekliyor": "Gönderilecek", "gonderildi": "Gönderildi", "hata": "Gönderilemedi", "kapali": "Bildirim kapalı",
         "kaydedildi": "Yalnız kaydedildi", "alici_yok": "Alıcı yok (şirket dışı ya da boş adres)", "tercih": "Kişi kapattı"}

OUTBOX = sa.Table(
    "semantic_hr_mail_outbox", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("event", sa.String(40), nullable=False),            # evrak_yeni, evrak_durum, izin_yeni, izin_onay…
    sa.Column("ref_type", sa.String(24)),                         # evrak_talebi | izin_talebi
    sa.Column("ref_id", sa.String(40), index=True),
    sa.Column("recipient", sa.String(200)),
    sa.Column("username", sa.String(120)),                        # alıcının portal hesabı (tercih için), bilinmiyorsa boş
    sa.Column("subject", sa.String(300), nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("state", sa.String(16), nullable=False),
    sa.Column("tries", sa.Integer, nullable=False, default=0),
    sa.Column("error", sa.String(300)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("sent_at", sa.DateTime(timezone=True)),
)

PREFS = sa.Table(
    "semantic_hr_mail_prefs", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("username", sa.String(120), primary_key=True),
    sa.Column("off", sa.Boolean, nullable=False, default=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

TABLE_LABELS = {"semantic_hr_mail_outbox": "İK e-posta kuyruğu", "semantic_hr_mail_prefs": "e-posta bildirim tercihleri"}


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if engine in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(engine)


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    mode = (conf("HR_MAIL_MODE") or "kapali").strip().lower()
    domains = [d.strip().lower().lstrip("@") for d in (conf("HR_MAIL_DOMAINS") or "timas.com.tr").replace(";", ",").split(",") if d.strip()]
    link = (conf("HR_PORTAL_LINK") or conf("ALERT_LINK") or "").split("/uyarilar")[0].rstrip("/")
    return {"mode": mode if mode in MODES else "kapali", "domains": domains, "link": link}


def internal(addr: Optional[str], domains: Iterable[str]) -> Optional[str]:
    a = clean(addr, 200).lower()
    if "@" not in a or " " in a:
        return None
    return a if a.rsplit("@", 1)[1] in set(domains) else None


def pref_off(engine: sa.engine.Engine, tenant: str, username: Optional[str]) -> bool:
    if not username:
        return False
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(PREFS.c.off).where(PREFS.c.tenant_id == tenant, PREFS.c.username == username)).first()
    return bool(r and r.off)


def set_pref(engine: sa.engine.Engine, tenant: str, username: str, off: bool) -> dict[str, Any]:
    ensure(engine)
    with engine.begin() as c:
        c.execute(PREFS.delete().where(PREFS.c.tenant_id == tenant, PREFS.c.username == username))
        c.execute(PREFS.insert().values(tenant_id=tenant, username=username, off=bool(off), updated_at=now()))
    return {"off": bool(off)}


def enqueue(engine: sa.engine.Engine, tenant: str, cfg: dict[str, Any], *, event: str, to: Optional[str], subject: str,
            body: str, ref_type: str = "", ref_id: str = "", username: Optional[str] = None, required: bool = False) -> str:
    """Bir e-postayı kuyruğa yazar; dönen durum satırın `state`'idir. Hata iş akışını durdurmaz (loga yazar)."""
    try:
        ensure(engine)
        addr = internal(to, cfg["domains"])
        if addr is None:
            state = "alici_yok"
        elif cfg["mode"] == "kapali":
            state = "kapali"
        elif not required and pref_off(engine, tenant, username):
            state = "tercih"
        elif cfg["mode"] == "kaydet":
            state = "kaydedildi"
        else:
            state = "bekliyor"
        link = cfg.get("link") or ""
        text = body.replace("{link}", link) if link else body.replace("{link}", "(portal adresi ayarlanmadı)")
        with engine.begin() as c:
            c.execute(OUTBOX.insert().values(tenant_id=tenant, event=event[:40], ref_type=ref_type[:24] or None, ref_id=ref_id[:40] or None,
                                             recipient=addr or (clean(to, 200) or None) and "(şirket dışı)",
                                             username=(username or None) and username[:120], subject=subject[:300],
                                             body=text + "\n\n— Timaş İnsan Kaynakları portalı (bu e-postayı yanıtlamayın)",
                                             state=state, tries=0, created_at=now()))
        return state
    except Exception as e:  # noqa: BLE001 — bildirim yazılamazsa iş akışı sürer
        log.warning("hr: e-posta kuyruğa yazılamadı (%s): %s", event, e)
        return "hata"


def run_outbox(engine: sa.engine.Engine, tenant: str, send: Callable[[str, str, list[str]], str], limit: int = 200) -> dict[str, Any]:
    """Bekleyenleri gönderir. `send` = `budget_api._send_mail` (sent | failed | no_smtp)."""
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(OUTBOX).where(OUTBOX.c.tenant_id == tenant, OUTBOX.c.state.in_(("bekliyor", "hata")),
                                                 OUTBOX.c.tries < MAX_TRIES).order_by(OUTBOX.c.id).limit(limit)).all()
    out = {"sent": 0, "failed": 0, "noSmtp": 0}
    for r in rows:
        res = send(r.subject, r.body, [r.recipient])
        with engine.begin() as c:
            if res == "sent":
                c.execute(OUTBOX.update().where(OUTBOX.c.id == r.id).values(state="gonderildi", tries=r.tries + 1, sent_at=now(), error=None))
                out["sent"] += 1
            else:
                c.execute(OUTBOX.update().where(OUTBOX.c.id == r.id).values(
                    state="hata", tries=r.tries + 1, error="SMTP ayarı yok" if res == "no_smtp" else "gönderilemedi"))
                out["noSmtp" if res == "no_smtp" else "failed"] += 1
        if res == "no_smtp":
            break
    return out


def list_outbox(engine: sa.engine.Engine, tenant: str, *, before: int = 0, limit: int = 100) -> dict[str, Any]:
    """İK için son e-postalar (gövde dahil; gövdede hassas veri yoktur)."""
    ensure(engine)
    limit = max(1, min(int(limit or 100), 500))
    stmt = sa.select(OUTBOX).where(OUTBOX.c.tenant_id == tenant)
    if before:
        stmt = stmt.where(OUTBOX.c.id < int(before))
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(OUTBOX.c.id.desc()).limit(limit + 1)).all()
        since = now() - timedelta(days=1)
        waiting = c.execute(sa.select(sa.func.count()).select_from(OUTBOX).where(
            OUTBOX.c.tenant_id == tenant, OUTBOX.c.state.in_(("bekliyor", "hata")), OUTBOX.c.tries < MAX_TRIES)).scalar() or 0
        failed24 = c.execute(sa.select(sa.func.count()).select_from(OUTBOX).where(
            OUTBOX.c.tenant_id == tenant, OUTBOX.c.state == "hata", OUTBOX.c.created_at >= since)).scalar() or 0
    items = [{"id": r.id, "event": r.event, "refType": r.ref_type, "refId": r.ref_id, "recipient": r.recipient, "subject": r.subject,
              "body": r.body, "state": r.state, "stateLabel": STATE.get(r.state, r.state), "tries": r.tries, "error": r.error,
              "createdAt": iso(r.created_at), "sentAt": iso(r.sent_at)} for r in rows[:limit]]
    return {"items": items, "hasMore": len(rows) > limit, "waiting": int(waiting), "failed24h": int(failed24)}
