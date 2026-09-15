"""Yönetim: sistem ayarları, herkesin tanımları ve değişiklik kaydı.

Ayar önceliği: yönetim ekranında kaydedilen değer > servis ortam dosyası (`/etc/nanobase/semantic-bridge.env`)
> varsayılan. Böylece SMTP gibi ayarlar sunucuya girmeden ekrandan verilir; ekrandan silinen ayar ortam
dosyasındaki değere döner. Gizli değerler (parola) hiçbir uçtan geri dönmez, kayıtta da yalnız "değişti" yazar.

Değişiklik kaydı (`semantic_audit`) kim, ne zaman, neyi oluşturdu/güncelledi/sildi/çalıştırdı sorusunun
cevabıdır. Kayıt yazılamazsa asıl işlem durmaz; kayıt bir yan üründür, kapı değil.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
import threading
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Optional

import sqlalchemy as sa

log = logging.getLogger(__name__)

_md = sa.MetaData()

SETTINGS = sa.Table(
    "semantic_settings", _md,
    sa.Column("key", sa.String(80), primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

AUDIT = sa.Table(
    "semantic_audit", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("actor", sa.String(120), nullable=False, index=True),
    sa.Column("action", sa.String(16), nullable=False),
    sa.Column("kind", sa.String(24), nullable=False, index=True),
    sa.Column("object_id", sa.String(120)),
    sa.Column("title", sa.String(300)),
    sa.Column("detail", sa.Text),
)

#: Ekrandan yönetilen ayarlar. `env` servis dosyasındaki adıdır; ekran değeri yoksa oradan okunur.
SPEC: list[dict[str, Any]] = [
    # E-posta
    {"key": "ALERT_SMTP_HOST", "group": "email", "label": "SMTP sunucusu", "type": "text", "default": "",
     "help": "Örn. smtp.office365.com ya da mail.timas.com.tr"},
    {"key": "ALERT_SMTP_PORT", "group": "email", "label": "Port", "type": "int", "default": "587",
     "help": "587 (STARTTLS) ya da 465 (SSL)"},
    {"key": "ALERT_SMTP_USER", "group": "email", "label": "Kullanıcı adı", "type": "text", "default": "",
     "help": "Gönderici hesabın oturum adı; sunucu kimlik istemiyorsa boş"},
    {"key": "ALERT_SMTP_PASSWORD", "group": "email", "label": "Parola", "type": "secret", "default": "",
     "help": "Kaydedilen parola ekranda bir daha gösterilmez"},
    {"key": "ALERT_SMTP_FROM", "group": "email", "label": "Gönderen adresi", "type": "email", "default": "",
     "help": "Boşsa kullanıcı adı kullanılır"},
    {"key": "ALERT_SMTP_SSL", "group": "email", "label": "Doğrudan SSL (465)", "type": "bool", "default": "0", "help": ""},
    {"key": "ALERT_SMTP_STARTTLS", "group": "email", "label": "STARTTLS", "type": "bool", "default": "1",
     "help": "SSL kapalıyken bağlantıyı şifreler"},
    {"key": "ALERT_RECIPIENT_DOMAINS", "group": "email", "label": "İzinli alıcı alan adları", "type": "text", "default": "",
     "help": "Virgülle, örn. timas.com.tr. Boşsa her adrese gönderilir"},
    # Bildirim ve raporlar
    {"key": "ALERT_LINK", "group": "delivery", "label": "E-postadaki bağlantı", "type": "text",
     "default": "", "help": "Uyarı ve rapor e-postalarının sonuna eklenen adres"},
    {"key": "ALERT_REMIND_HOURS", "group": "delivery", "label": "Uyarı hatırlatma (saat)", "type": "int", "default": "24",
     "help": "Eşik aşılmaya devam ederse kaç saat sonra yeniden bildirilir"},
    {"key": "REPORT_KEEP_FILES", "group": "delivery", "label": "Rapor başına saklanan dosya", "type": "int", "default": "10",
     "help": "Eski dosyalar bu sayıdan sonra silinir"},
    # Toplantı odaları
    {"key": "ROOM_DAY_START", "group": "rooms", "label": "Takvim başlangıcı", "type": "time", "default": "08:00",
     "help": "Oda takviminin ilk saati, SS:DD"},
    {"key": "ROOM_DAY_END", "group": "rooms", "label": "Takvim bitişi", "type": "time", "default": "20:00",
     "help": "Oda takviminin son saati, SS:DD (24:00 gece yarısı)"},
    {"key": "ROOM_SLOT_MINUTES", "group": "rooms", "label": "Saat adımı (dakika)", "type": "int", "default": "30",
     "help": "Takvimdeki en küçük aralık: 15, 30 ya da 60"},
    # Yetki
    {"key": "TIMAS_ADMIN_USERS", "group": "access", "label": "Yöneticiler", "type": "users",
     "default": "timasai,muratsancar", "help": "AD hesap adları, virgülle. Bu ekranı yalnız bunlar açar"},
]
_BY_KEY = {s["key"]: s for s in SPEC}
GROUPS = [
    {"id": "email", "label": "E-posta (SMTP)", "help": "Uyarı ve planlı rapor e-postaları bu hesapla gider."},
    {"id": "delivery", "label": "Bildirim ve raporlar", "help": "Gönderim davranışı."},
    {"id": "rooms", "label": "Toplantı odaları", "help": "Rezervasyon takviminin saatleri."},
    {"id": "access", "label": "Yetki", "help": "Yönetim ekranına kimlerin gireceği."},
]

KIND_LABEL = {"report": "Planlı rapor", "alert": "Uyarı", "board": "Pano kartı", "setting": "Ayar",
              "term": "Sözlük terimi", "annotation": "Kolon açıklaması", "session": "Oturum",
              "room": "Toplantı odası", "booking": "Oda rezervasyonu"}

_ready: set[int] = set()
_lock = threading.Lock()
_engine: Optional[sa.engine.Engine] = None
_cache: dict[str, Any] = {"at": 0.0, "values": {}}
_TTL = 5.0


class AdminError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def ensure(engine: sa.engine.Engine) -> None:
    """Tabloları kurar ve ayar okuyucusunu bu veritabanına bağlar."""
    global _engine
    with _lock:
        if id(engine) not in _ready:
            _md.create_all(engine, checkfirst=True)
            _ready.add(id(engine))
        _engine = engine


# ------------------------------------------------------------------ ayarlar


def _stored() -> dict[str, str]:
    if _engine is None:
        return {}
    if time.monotonic() - _cache["at"] < _TTL:
        return _cache["values"]
    try:
        with _engine.connect() as c:
            rows = c.execute(sa.select(SETTINGS.c.key, SETTINGS.c.value)).all()
        _cache.update(at=time.monotonic(), values={k: v for k, v in rows})
    except Exception as e:  # noqa: BLE001
        log.warning("admin: ayarlar okunamadı, ortam değerleri kullanılıyor: %s", e)
        return {}
    return _cache["values"]


def conf(key: str, default: str = "") -> str:
    """Ayarın geçerli değeri: ekran > ortam > varsayılan."""
    stored = _stored()
    if key in stored:
        return stored[key]
    if key in os.environ:
        return os.environ[key]
    spec = _BY_KEY.get(key)
    return spec["default"] if spec and default == "" else default


def admins() -> list[str]:
    return [u.strip().lower() for u in conf("TIMAS_ADMIN_USERS").split(",") if u.strip()]


def is_admin(user: Optional[str]) -> bool:
    return bool(user) and user.strip().lower() in admins()  # type: ignore[union-attr]


def _validate(spec: dict[str, Any], raw: Any) -> str:
    t = spec["type"]
    v = "" if raw is None else str(raw).strip()
    if t == "bool":
        return "1" if v in ("1", "true", "True", "on", "evet") else "0"
    if t == "int":
        try:
            n = int(v)
        except ValueError:
            raise AdminError(f"«{spec['label']}» bir tam sayı olmalı.") from None
        if n < 0:
            raise AdminError(f"«{spec['label']}» eksi olamaz.")
        return str(n)
    if t == "time":
        import re as _re
        m = _re.match(r"^([01]\d|2[0-4]):([0-5]\d)$", v)
        if not m or (m.group(1) == "24" and m.group(2) != "00"):
            raise AdminError(f"«{spec['label']}» SS:DD biçiminde olmalı, örn. 08:30.")
        return v
    if t == "email" and v and ("@" not in v or " " in v):
        raise AdminError(f"«{spec['label']}» geçerli bir e-posta adresi değil.")
    if t == "users":
        users = [u.strip().lower() for u in v.split(",") if u.strip()]
        if not users:
            raise AdminError("En az bir yönetici kalmalı.")
        return ",".join(dict.fromkeys(users))
    if t == "secret":
        return str(raw or "")
    return v


def settings_view() -> dict[str, Any]:
    stored = _stored()
    rows = {}
    if _engine is not None:
        with _engine.connect() as c:
            rows = {r["key"]: r for r in c.execute(sa.select(SETTINGS)).mappings().all()}
    items = []
    for s in SPEC:
        k = s["key"]
        source = "screen" if k in stored else "env" if k in os.environ else "default"
        value = conf(k)
        item = {k2: s[k2] for k2 in ("key", "group", "label", "type", "help")}
        item.update(source=source, updatedBy=rows[k]["updated_by"] if k in rows else None,
                    updatedAt=_iso(rows[k]["updated_at"]) if k in rows else None)
        if s["type"] == "secret":
            item.update(value=None, hasValue=bool(value))
        else:
            item.update(value=value, hasValue=bool(value))
        items.append(item)
    return {"groups": GROUPS, "items": items}


def save_settings(engine: sa.engine.Engine, actor: str, values: dict[str, Any]) -> dict[str, Any]:
    changed: list[dict[str, Any]] = []
    now = _now()
    clean: dict[str, str] = {}
    for k, raw in values.items():
        spec = _BY_KEY.get(k)
        if not spec:
            raise AdminError(f"Bilinmeyen ayar: {k}")
        # Boş gönderilen parola "değiştirme" demektir; silmek için ayrı uç var.
        if spec["type"] == "secret" and (raw is None or str(raw) == ""):
            continue
        clean[k] = _validate(spec, raw)
    if "TIMAS_ADMIN_USERS" in clean and actor.lower() not in clean["TIMAS_ADMIN_USERS"].split(","):
        raise AdminError("Kendinizi yöneticilerden çıkaramazsınız; önce başka bir yönetici bunu yapmalı.")
    with engine.begin() as c:
        for k, v in clean.items():
            old = conf(k)
            if old == v and k in _stored():
                continue
            c.execute(SETTINGS.delete().where(SETTINGS.c.key == k))
            c.execute(SETTINGS.insert().values(key=k, value=v, updated_by=actor, updated_at=now))
            secret = _BY_KEY[k]["type"] == "secret"
            changed.append({"key": k, "label": _BY_KEY[k]["label"],
                            "from": None if secret else old, "to": None if secret else v})
    _cache["at"] = 0.0
    for ch in changed:
        audit(engine, actor, "update", "setting", ch["key"], ch["label"],
              {"from": ch["from"], "to": ch["to"]} if ch["from"] is not None or ch["to"] is not None else {"secret": True})
    return {"changed": [c["key"] for c in changed], **settings_view()}


def reset_setting(engine: sa.engine.Engine, actor: str, key: str) -> dict[str, Any]:
    spec = _BY_KEY.get(key)
    if not spec:
        raise AdminError(f"Bilinmeyen ayar: {key}")
    if key == "TIMAS_ADMIN_USERS":
        raise AdminError("Yönetici listesi sıfırlanamaz; düzenleyerek değiştirin.")
    with engine.begin() as c:
        n = c.execute(SETTINGS.delete().where(SETTINGS.c.key == key)).rowcount
    _cache["at"] = 0.0
    if n:
        audit(engine, actor, "delete", "setting", key, spec["label"], {"to": "ortam dosyası / varsayılan"})
    return settings_view()


def smtp_test(to: str) -> tuple[bool, str]:
    """Geçerli ayarla bir deneme e-postası gönderir; hata metnini olduğu gibi döndürür."""
    from semantic_bridge import alerts as alerts_mod

    cfg = alerts_mod.smtp_settings()
    if not cfg:
        return False, "SMTP sunucusu ya da gönderen adresi girilmemiş."
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = "ZEKİ deneme e-postası", cfg["sender"], to
    msg.set_content("Bu e-posta ZEKİ yönetim ekranından gönderilen denemedir. Uyarı ve planlı rapor e-postaları bu ayarla gidecek.")
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
        return True, f"{to} adresine gönderildi."
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:400]


# ------------------------------------------------------------------ değişiklik kaydı


def audit(engine: Optional[sa.engine.Engine], actor: Optional[str], action: str, kind: str,
          object_id: Optional[str], title: Optional[str], detail: Any = None) -> None:
    eng = engine or _engine
    if eng is None:
        return
    try:
        ensure(eng)
        with eng.begin() as c:
            c.execute(AUDIT.insert().values(
                at=_now(), actor=(actor or "sistem")[:120], action=action[:16], kind=kind[:24],
                object_id=(str(object_id)[:120] if object_id else None), title=(str(title)[:300] if title else None),
                detail=json.dumps(detail, ensure_ascii=False, default=str)[:20000] if detail is not None else None))
    except Exception as e:  # noqa: BLE001
        log.warning("admin: değişiklik kaydı yazılamadı (%s %s): %s", action, kind, e)


def audit_list(engine: sa.engine.Engine, *, kind: Optional[str] = None, actor: Optional[str] = None,
               action: Optional[str] = None, q: Optional[str] = None, before: Optional[int] = None,
               limit: int = 100) -> dict[str, Any]:
    stmt = sa.select(AUDIT)
    if kind:
        stmt = stmt.where(AUDIT.c.kind == kind)
    if actor:
        stmt = stmt.where(AUDIT.c.actor == actor)
    if action:
        stmt = stmt.where(AUDIT.c.action == action)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(sa.or_(AUDIT.c.title.ilike(like), AUDIT.c.object_id.ilike(like), AUDIT.c.actor.ilike(like)))
    if before:
        stmt = stmt.where(AUDIT.c.id < before)
    limit = max(1, min(int(limit or 100), 500))
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(AUDIT.c.id.desc()).limit(limit + 1)).mappings().all()
    items = [{
        "id": r["id"], "at": _iso(r["at"]), "actor": r["actor"], "action": r["action"], "kind": r["kind"],
        "kindLabel": KIND_LABEL.get(r["kind"], r["kind"]), "objectId": r["object_id"], "title": r["title"],
        "detail": json.loads(r["detail"]) if r["detail"] else None,
    } for r in rows[:limit]]
    return {"items": items, "next": items[-1]["id"] if len(rows) > limit else None}


def changes(before: dict[str, Any], after: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    """İki kaydın kayda değer alanlarındaki farkı: {alan: {from, to}}."""
    out = {}
    for k in keys:
        if before.get(k) != after.get(k):
            out[k] = {"from": before.get(k), "to": after.get(k)}
    return out


# ------------------------------------------------------------------ herkesin tanımları


def all_reports(engine: sa.engine.Engine, tenant: str, ds: str) -> list[dict[str, Any]]:
    from semantic_bridge import reports as rm

    rm.ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(rm.REPORTS).where(*rm._scope(tenant, ds, None))
                         .order_by(rm.REPORTS.c.created_at.desc())).mappings().all()
    return [{**rm.to_dict(r), "owner": r["username"]} for r in rows]


def all_cards(engine: sa.engine.Engine, tenant: str, ds: str) -> list[dict[str, Any]]:
    from semantic_bridge import board as bm

    bm.ensure(engine)
    C = bm.CARDS
    cols = [C.c.id, C.c.username, C.c.title, C.c.question, C.c.chart, C.c.refresh, C.c.refresh_at,
            C.c.created_at, C.c.updated_at, C.c.result_at, C.c.last_auto_at, C.c.last_error]
    with engine.connect() as c:
        rows = c.execute(sa.select(*cols).where(C.c.tenant_id == tenant, C.c.datasource_id == ds)
                         .order_by(C.c.username, C.c.position)).mappings().all()
    return [{"id": r["id"], "owner": r["username"], "title": r["title"], "question": r["question"] or "",
             "chart": r["chart"], "refresh": r["refresh"], "refreshAt": r["refresh_at"],
             "createdAt": _iso(r["created_at"]), "updatedAt": _iso(r["updated_at"]),
             "resultAt": _iso(r["result_at"]), "lastAutoAt": _iso(r["last_auto_at"]), "lastError": r["last_error"]}
            for r in rows]


def delete_card(engine: sa.engine.Engine, tenant: str, ds: str, card_id: str) -> Optional[dict[str, Any]]:
    from semantic_bridge import board as bm

    C = bm.CARDS
    with engine.begin() as c:
        row = c.execute(sa.select(C.c.id, C.c.username, C.c.title).where(
            C.c.id == card_id, C.c.tenant_id == tenant, C.c.datasource_id == ds)).mappings().first()
        if not row:
            return None
        c.execute(C.delete().where(C.c.id == card_id))
    return dict(row)


def users(engine: sa.engine.Engine, tenant: str, ds: str) -> list[dict[str, Any]]:
    """Sistemi kullanan kişiler: tanımı ya da kaydı olan her hesap, son hareketiyle."""
    from semantic_bridge import board as bm
    from semantic_bridge import reports as rm

    people: dict[str, dict[str, Any]] = {}

    def person(u: str) -> dict[str, Any]:
        key = (u or "").lower()
        return people.setdefault(key, {"username": u, "cards": 0, "reports": 0, "actions": 0, "lastSeen": None,
                                       "admin": is_admin(u)})

    def seen(p: dict[str, Any], at: Optional[datetime]) -> None:
        s = _iso(at)
        if s and (p["lastSeen"] is None or s > p["lastSeen"]):
            p["lastSeen"] = s

    with engine.connect() as c:
        for u, n, last in c.execute(sa.select(bm.CARDS.c.username, sa.func.count(), sa.func.max(bm.CARDS.c.updated_at))
                                    .where(bm.CARDS.c.tenant_id == tenant, bm.CARDS.c.datasource_id == ds)
                                    .group_by(bm.CARDS.c.username)).all():
            p = person(u); p["cards"] = n; seen(p, last)
        for u, n, last in c.execute(sa.select(rm.REPORTS.c.username, sa.func.count(), sa.func.max(rm.REPORTS.c.updated_at))
                                    .where(*rm._scope(tenant, ds, None)).group_by(rm.REPORTS.c.username)).all():
            p = person(u); p["reports"] = n; seen(p, last)
        for u, n, last in c.execute(sa.select(AUDIT.c.actor, sa.func.count(), sa.func.max(AUDIT.c.at))
                                    .where(AUDIT.c.actor != "sistem").group_by(AUDIT.c.actor)).all():
            p = person(u); p["actions"] = n; seen(p, last)
    for a in admins():
        person(a)["admin"] = True
    return sorted(people.values(), key=lambda p: (p["lastSeen"] or ""), reverse=True)


# ------------------------------------------------------------------ sistem durumu


def _unit(name: str) -> dict[str, Any]:
    """systemd birimini okur (yetki gerektirmez). systemctl yoksa bilinmiyor döner."""
    import subprocess

    props = "ActiveState,SubState,LastTriggerUSec,NextElapseUSecRealtime,Result"
    try:
        out = subprocess.run(["systemctl", "show", name, "-p", props], capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return {"unit": name, "state": "unknown"}
    kv = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return {"unit": name, "state": kv.get("ActiveState") or "unknown", "sub": kv.get("SubState"),
            "last": kv.get("LastTriggerUSec") or None, "next": kv.get("NextElapseUSecRealtime") or None,
            "result": kv.get("Result")}


TIMERS = [
    {"unit": "timas-alerts.timer", "label": "Uyarı kontrolü", "every": "15 dk"},
    {"unit": "timas-reports.timer", "label": "Planlı raporlar", "every": "5 dk"},
    {"unit": "timas-board.timer", "label": "Pano kartı tazeleme", "every": "15 dk"},
    {"unit": "nanobase-semantic-worker.timer", "label": "Gece katalog taraması", "every": "gece"},
    {"unit": "nanobase-semantic-watchdog.timer", "label": "Köprü sağlık denetimi", "every": "5 dk"},
]
SERVICES = [
    {"unit": "nanobase-semantic-bridge.service", "label": "Sorgu motoru (köprü)"},
    {"unit": "timas-login.service", "label": "Giriş servisi (Active Directory)"},
    {"unit": "timas-vpn-mfa.service", "label": "TİMAŞ VPN"},
    {"unit": "timas-mssql-14330.service", "label": "Logo/CRM veritabanı tüneli"},
]


_STAMP = r"\w{3} \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S+"


def _timer_times() -> dict[str, tuple[Optional[str], Optional[str]]]:
    """Göreli (OnUnitActiveSec) zamanlayıcılarda `systemctl show` sıradaki anı boş verir; list-timers verir.
    Satır biçimi: NEXT LEFT LAST PASSED UNIT ACTIVATES — sıradaki yoksa satır "-" ile başlar."""
    import re
    import subprocess

    try:
        out = subprocess.run(["systemctl", "list-timers", "--all", "--no-legend", "--no-pager"],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return {}
    times: dict[str, tuple[Optional[str], Optional[str]]] = {}
    for line in out.splitlines():
        unit = next((w for w in line.split() if w.endswith(".timer")), None)
        if not unit:
            continue
        stamps = re.findall(_STAMP, line)
        if line.lstrip().startswith("-"):
            times[unit] = (None, stamps[0] if stamps else None)
        else:
            times[unit] = (stamps[0] if stamps else None, stamps[1] if len(stamps) > 1 else None)
    return times


def system_status() -> dict[str, Any]:
    times = _timer_times()
    timers = []
    for t in TIMERS:
        u = {**t, **_unit(t["unit"])}
        nxt, last = times.get(t["unit"], (None, None))
        u["next"] = nxt or u.get("next")
        u["last"] = last or u.get("last")
        timers.append(u)
    return {"services": [{**s, **_unit(s["unit"])} for s in SERVICES], "timers": timers}
