"""M49 Veri yönetimi ve güvenlik: giriş ve erişim kaydı, kural tabanlı uyarılar, hesap hijyeni, «Herkes» daraltma
önizlemesi, saklama süresi uygulaması ve kişisel veri envanteri.

Analiz: docs/analiz/kullanici-ihtiyaclari/M49-veri-guvenligi.md (14. bölüm kodlama planı).

Ne yazılır (ölçülülük, analiz §8): her istek değil; yalnız giriş denemeleri (giriş servisinden çekilir), sayfa
kapısının verdiği 403 kararları, dışa aktarmalar (sunucu tarafı uçlar kapıda, istemci tarafı CSV/PDF `export-notice`
ile) ve ZEKİ AI'ın yetki dışı soruları (bunlar zaten soru kaydında `answer_type='NOT_PERMITTED'`, burada
kopyalanmaz, okunur). Parola, oturum anahtarı ve TC/e-posta değeri hiçbir tabloya yazılmaz.

Uyarılar model «hissiyle» değil kuralla üretilir (tekrarlanabilir, gerekçesi kanıt satırlarında): art arda hatalı
giriş, mesai dışı toplu dışa aktarma, yeni yönetici, «Herkes» rolüne yetki eklenmesi, saklama işinin durması.

Saklama (kullanıcı kuralı: veri silinmeden önce ne değişeceği gösterilir; kurulum müşteri verisini kendiliğinden
silmez): süreler ayardır (`admin.conf`, `SECURITY_RETENTION_*_DAYS`), uygulama anahtarı `SECURITY_RETENTION_APPLY`
varsayılan kapalıdır. Kapalıyken gece işi yalnız «kaç satır etkilenecek» önizlemesini kanıt satırına yazar; açılması
yönetici kararıdır (`ozellik:guvenlik.saklama`) ve açarken önizleme gösterilmiş olmalıdır. Açıkken iş önce önizlemeyi,
sonra uygulamayı (etkilenen satır sayısı, tarih aralığı) yazar. Soru kaydında satır silinmez, yalnız tam sonuç
boşaltılır; model kuyruğunda yalnız metin boşaltılır (süre ve sayılar M48 kapasite görünümü için kalır).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic_bridge.data_security")

_md = sa.MetaData()

LOGINS = sa.Table(
    "semantic_security_logins", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("username", sa.String(120), nullable=False, index=True),
    sa.Column("ok", sa.Boolean, nullable=False),
    # ok | bad_password | unknown_account (ad yazılmaz) | unknown_domain | bad_format | directory_down | logout | revoked
    sa.Column("reason", sa.String(24), nullable=False),
    sa.Column("addr", sa.String(64)),
    sa.Column("ua_hash", sa.String(32)),
    sa.Column("src_event_id", sa.Integer, index=True),
)

ACCESS = sa.Table(
    "semantic_security_access", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("username", sa.String(120), nullable=False, index=True),
    sa.Column("kind", sa.String(16), nullable=False, index=True),     # forbidden | export
    sa.Column("method", sa.String(8)),
    sa.Column("path", sa.String(400)),
    sa.Column("perm_key", sa.String(200)),
    sa.Column("detail_json", sa.Text),
)

ALERTS = sa.Table(
    "semantic_security_alerts", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("rule", sa.String(40), nullable=False),
    sa.Column("username", sa.String(120)),
    sa.Column("severity", sa.String(12), nullable=False),               # kritik | uyari
    sa.Column("summary", sa.Text, nullable=False),
    sa.Column("evidence_json", sa.Text),
    sa.Column("dedup", sa.String(200), index=True),
    sa.Column("state", sa.String(8), nullable=False, default="open"),   # open | closed
    sa.Column("closed_by", sa.String(120)),
    sa.Column("closed_at", sa.DateTime(timezone=True)),
    sa.Column("verdict", sa.String(16)),                                # gercek | gercek-degil
    sa.Column("note", sa.Text),
    sa.Column("mailed", sa.String(16)),                                 # sent | failed | no_smtp | alici_yok
)

RUNS = sa.Table(
    "semantic_security_retention_runs", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("object", sa.String(32), nullable=False),
    sa.Column("mode", sa.String(12), nullable=False),                   # onizleme | uygulama
    sa.Column("days", sa.Integer),
    sa.Column("cutoff", sa.DateTime(timezone=True)),
    sa.Column("rows_affected", sa.Integer),
    sa.Column("range_from", sa.DateTime(timezone=True)),
    sa.Column("range_to", sa.DateTime(timezone=True)),
    sa.Column("ok", sa.Boolean, nullable=False),
    sa.Column("error", sa.Text),
    sa.Column("actor", sa.String(120)),
)

STATE = sa.Table(
    "semantic_security_state", _md,
    sa.Column("key", sa.String(80), primary_key=True),
    sa.Column("value", sa.Text),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

INVENTORY_FILE = Path(__file__).with_name("data_security_inventory.json")

KIND_LABEL = {"forbidden": "Yetkisiz erişim denemesi", "export": "Dışa aktarma", "not_permitted": "Yetki dışı soru"}
REASON_LABEL = {"ok": "Başarılı giriş", "bad_password": "Hatalı kullanıcı adı ya da parola", "unknown_domain": "Başka etki alanı",
                "directory_down": "Dizine ulaşılamadı", "logout": "Çıkış", "revoked": "Oturum kapatıldı (yönetici)",
                "bad_format": "Geçersiz kullanıcı adı biçimi", "unknown_account": "Dizinde olmayan hesap (ad yazılmaz)"}
RULE_LABEL = {"hatali_giris": "Art arda hatalı giriş", "mesai_disi_aktarim": "Mesai dışı toplu dışa aktarma",
              "yeni_yonetici": "Yeni yönetici", "herkes_genisledi": "«Herkes» rolüne yetki eklendi",
              "saklama_durdu": "Saklama işi çalışmadı"}
FAILED_REASONS = ("bad_password", "unknown_account", "unknown_domain", "bad_format")

_ready: set[int] = set()
_lock = threading.Lock()


class SecurityError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    v = _aware(v)
    return v.isoformat() if v else None


def _local_tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(os.environ.get("TIMAS_TZ", "Europe/Istanbul"))
    except Exception:  # noqa: BLE001 — tz veritabanı yoksa Türkiye saati sabit +03:00
        return timezone(timedelta(hours=3))


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


# ------------------------------------------------------------------ ayarlar


def settings() -> dict[str, Any]:
    """Geçerli ayarlar (ekran > ortam > varsayılan; `admin.SPEC`'te `security` grubu)."""
    from semantic_bridge.admin import conf

    def num(key: str, default: int) -> int:
        try:
            return max(0, int(str(conf(key) or default).strip()))
        except ValueError:
            return default

    hours = (conf("SECURITY_WORK_HOURS") or "08:00-19:00").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$", hours)
    start, end = ((int(m.group(1)) * 60 + int(m.group(2)), int(m.group(3)) * 60 + int(m.group(4))) if m else (480, 1140))
    return {
        "recipients": [x.strip() for x in (conf("SECURITY_ALERT_RECIPIENTS") or "").replace(";", ",").split(",") if "@" in x],
        "failThreshold": max(1, num("SECURITY_FAIL_THRESHOLD", 5)),
        "failWindowMin": max(1, num("SECURITY_FAIL_WINDOW_MIN", 10)),
        "workStart": start,
        "workEnd": end,
        "workHours": hours,
        "workDays": _days(conf("SECURITY_WORK_DAYS") or "1-5"),
        "offhoursExportMin": max(1, num("SECURITY_OFFHOURS_EXPORT_MIN", 3)),
        "offhoursWindowMin": 60,
        "idleDays": num("SECURITY_IDLE_DAYS", 90),
        "testPattern": (conf("SECURITY_TEST_ACCOUNT_PATTERN") or r"^(test|deneme|demo|qa[-_.]|claude)").strip(),
        "dailyAt": (conf("SECURITY_DAILY_AT") or "03:40").strip(),
        "apply": (conf("SECURITY_RETENTION_APPLY") or "0").strip() == "1",
        "days": {o["id"]: num(o["key"], o["default"]) for o in RETENTION},
    }


def _days(spec: str) -> frozenset[int]:
    """«1-5» ya da «1,2,3,4,5,6» → ISO hafta günleri (1 = Pazartesi)."""
    out: set[int] = set()
    for part in str(spec).replace(" ", "").split(","):
        if "-" in part:
            a, _, b = part.partition("-")
            if a.isdigit() and b.isdigit():
                out |= set(range(int(a), int(b) + 1))
        elif part.isdigit():
            out.add(int(part))
    return frozenset(d for d in out if 1 <= d <= 7) or frozenset(range(1, 6))


def off_hours(at: datetime, cfg: dict[str, Any]) -> bool:
    loc = _aware(at).astimezone(_local_tz())
    minute = loc.hour * 60 + loc.minute
    return loc.isoweekday() not in cfg["workDays"] or not (cfg["workStart"] <= minute < cfg["workEnd"])


# ------------------------------------------------------------------ durum anahtarları


def state_get(engine: sa.engine.Engine, key: str, default: Any = None) -> Any:
    with engine.connect() as c:
        row = c.execute(sa.select(STATE.c.value).where(STATE.c.key == key)).first()
    if not row or row[0] is None:
        return default
    try:
        return json.loads(row[0])
    except ValueError:
        return default


def state_set(engine: sa.engine.Engine, key: str, value: Any) -> None:
    body = json.dumps(value, ensure_ascii=False, default=str)
    with engine.begin() as c:
        c.execute(STATE.delete().where(STATE.c.key == key))
        c.execute(STATE.insert().values(key=key, value=body, updated_at=_now()))


# ------------------------------------------------------------------ erişim kaydı


def record_access(engine: sa.engine.Engine, user: str, kind: str, method: str, path: str,
                  perm_key: Optional[str] = None, detail: Optional[dict[str, Any]] = None,
                  at: Optional[datetime] = None) -> None:
    """403 ya da dışa aktarma satırı. Yazılamazsa asıl istek durmaz (kayıt yan üründür, kapı değil)."""
    try:
        ensure(engine)
        with engine.begin() as c:
            c.execute(ACCESS.insert().values(
                at=at or _now(), username=(user or "?")[:120].lower(), kind=kind[:16], method=(method or "")[:8],
                path=(path or "")[:400], perm_key=(perm_key or None) and perm_key[:200],
                detail_json=json.dumps(detail, ensure_ascii=False, default=str)[:4000] if detail else None))
    except Exception as e:  # noqa: BLE001
        log.warning("güvenlik: erişim kaydı yazılamadı (%s %s): %s", kind, path, e)


_NOTICE_FORMATS = {"csv", "xlsx", "pdf", "docx", "png", "json"}


def export_notice(engine: sa.engine.Engine, user: str, body: dict[str, Any]) -> dict[str, Any]:
    """İstemci tarafında üretilen dosyanın (CSV, yazdırma PDF'i) bildirimi. Kişi yalnız kendi aktarımını bildirir."""
    what = " ".join(str(body.get("what") or "").split())[:200]
    fmt = str(body.get("format") or "").strip().lower()
    page = str(body.get("page") or "").strip()[:200]
    if not what:
        raise SecurityError("Neyin dışa aktarıldığı yazılmadı.")
    if fmt not in _NOTICE_FORMATS:
        raise SecurityError("Dosya biçimi tanınmadı.")
    rows = body.get("rows")
    try:
        rows = int(rows) if rows is not None else None
    except (TypeError, ValueError):
        rows = None
    record_access(engine, user, "export", "CLIENT", page or "(istemci)", "ozellik:veri.disa-aktar",
                  {"what": what, "format": fmt, "rows": rows, "client": True})
    return {"ok": True}


def list_access(engine: sa.engine.Engine, store_engine: sa.engine.Engine, tenant: str, ds: str, *,
                kind: str = "", user: str = "", since: Optional[datetime] = None, before: Optional[str] = None,
                page_size: int = 200) -> dict[str, Any]:
    """Erişim kaydı: 403, dışa aktarma ve (soru kaydından okunan) yetki dışı sorular, yeniden eskiye, sayfalı.
    `before` bir önceki sayfanın son satırının zamanıdır (ISO); sayfa boyu tavan değildir, «daha fazla» ile devam eder."""
    out: list[dict[str, Any]] = []
    cfg = settings()
    cut = datetime.fromisoformat(before) if before else None
    u = (user or "").strip().lower()
    if kind in ("", "forbidden", "export"):
        stmt = sa.select(ACCESS)
        if kind:
            stmt = stmt.where(ACCESS.c.kind == kind)
        if u:
            stmt = stmt.where(ACCESS.c.username == u)
        if since:
            stmt = stmt.where(ACCESS.c.at >= since)
        if cut:
            stmt = stmt.where(ACCESS.c.at < cut)
        with engine.connect() as c:
            for r in c.execute(stmt.order_by(ACCESS.c.at.desc()).limit(page_size + 1)).mappings():
                detail = json.loads(r["detail_json"]) if r["detail_json"] else None
                out.append({"id": f"a{r['id']}", "at": _iso(r["at"]), "username": r["username"], "kind": r["kind"],
                            "kindLabel": KIND_LABEL.get(r["kind"], r["kind"]), "method": r["method"], "path": r["path"],
                            "permKey": r["perm_key"], "detail": detail, "offHours": off_hours(r["at"], cfg)})
    if kind in ("", "not_permitted"):
        from semantic_layer.store import schema as S

        Q = S.sl_query_log
        stmt = sa.select(Q.c.id, Q.c.created_at, Q.c.username, Q.c.question, Q.c.answer_summary).where(
            Q.c.tenant_id == tenant, Q.c.datasource_id == ds, Q.c.answer_type == "NOT_PERMITTED")
        if u:
            stmt = stmt.where(sa.func.lower(Q.c.username) == u)
        if since:
            stmt = stmt.where(Q.c.created_at >= since)
        if cut:
            stmt = stmt.where(Q.c.created_at < cut)
        try:
            with store_engine.connect() as c:
                for r in c.execute(stmt.order_by(Q.c.created_at.desc()).limit(page_size + 1)).mappings():
                    out.append({"id": f"q{r['id']}", "at": _iso(r["created_at"]), "username": (r["username"] or "?").lower(),
                                "kind": "not_permitted", "kindLabel": KIND_LABEL["not_permitted"], "method": "POST",
                                "path": "/api/v1/ask", "permKey": None,
                                "detail": {"question": (r["question"] or "")[:200], "answer": (r["answer_summary"] or "")[:300]},
                                "offHours": off_hours(r["created_at"], cfg)})
        except Exception as e:  # noqa: BLE001
            log.warning("güvenlik: soru kaydı okunamadı: %s", e)
    out.sort(key=lambda x: x["at"] or "", reverse=True)
    more = len(out) > page_size
    out = out[:page_size]
    return {"items": out, "next": out[-1]["at"] if more and out else None}


# ------------------------------------------------------------------ giriş servisi


class LoginServiceError(RuntimeError):
    pass


class LoginClient:
    """Giriş servisinin yönetim uçları (`/admin/*`, `LOGIN_ADMIN_TOKEN` başlığıyla). Jeton tanımlı değilse kapalıdır:
    giriş kaydı çekilmez, oturum listesi boş döner ve ekran bunu söyler."""

    def __init__(self, base: Optional[str] = None, token: Optional[str] = None, timeout: float = 10.0):
        self.base = (base or os.environ.get("TIMAS_LOGIN_URL", "http://127.0.0.1:8796")).rstrip("/")
        self.token = os.environ.get("LOGIN_ADMIN_TOKEN", "") if token is None else token
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return len(self.token or "") >= 24

    def _call(self, method: str, path: str, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        if not self.configured:
            raise LoginServiceError("Giriş servisine yönetim bağlantısı tanımlı değil.")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "X-Login-Admin": self.token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:  # noqa: S310 — iç ağ servisi
                return json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise LoginServiceError(f"Giriş servisi {e.code} döndü.") from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise LoginServiceError(f"Giriş servisine ulaşılamadı ({type(e).__name__}).") from e

    def events(self, after: int, limit: int = 1000) -> dict[str, Any]:
        return self._call("GET", "/admin/events?" + urllib.parse.urlencode({"after": after, "limit": limit}))

    def sessions(self) -> list[dict[str, Any]]:
        return list(self._call("GET", "/admin/sessions").get("items") or [])

    def revoke(self, *, username: Optional[str] = None, session: Optional[str] = None, actor: str = "") -> dict[str, Any]:
        return self._call("POST", "/admin/sessions/revoke", {"username": username, "session": session, "actor": actor})


def pull_logins(engine: sa.engine.Engine, client: LoginClient) -> dict[str, Any]:
    """Giriş servisindeki yeni olayları meta veritabanına taşır. İmleç kalıcıdır; servis sıfırlandıysa (en büyük
    kimlik imleçten küçük) baştan okunur ve aynı (kimlik, zaman) ikinci kez yazılmaz."""
    ensure(engine)
    if not client.configured:
        return {"ok": False, "configured": False, "imported": 0}
    cursor = int(state_get(engine, "login_cursor", 0) or 0)
    imported = 0
    try:
        while True:
            page = client.events(cursor)
            items = list(page.get("items") or [])
            max_id = int(page.get("maxId") or 0)
            if max_id < cursor:                 # servis veritabanı yeni: imleç başa
                cursor = 0
                continue
            if not items:
                break
            rows = []
            with engine.connect() as c:
                for ev in items:
                    eid = int(ev.get("id") or 0)
                    at = datetime.fromtimestamp(float(ev.get("at") or 0), tz=timezone.utc)
                    dup = c.execute(sa.select(LOGINS.c.id).where(LOGINS.c.src_event_id == eid, LOGINS.c.at == at)).first()
                    if not dup:
                        rows.append({"at": at, "username": str(ev.get("username") or "?")[:120].lower(),
                                     "ok": bool(ev.get("ok")), "reason": str(ev.get("reason") or "")[:24] or "ok",
                                     "addr": (str(ev.get("addr") or "")[:64] or None),
                                     "ua_hash": (str(ev.get("ua") or "")[:32] or None), "src_event_id": eid})
                    cursor = max(cursor, eid)
            if rows:
                with engine.begin() as c:
                    c.execute(LOGINS.insert(), rows)
                imported += len(rows)
            state_set(engine, "login_cursor", cursor)
            if not page.get("more"):
                break
        state_set(engine, "login_pull", {"at": _iso(_now()), "ok": True, "imported": imported})
        return {"ok": True, "configured": True, "imported": imported}
    except LoginServiceError as e:
        state_set(engine, "login_pull", {"at": _iso(_now()), "ok": False, "error": str(e)})
        return {"ok": False, "configured": True, "imported": imported, "error": str(e)}


def list_logins(engine: sa.engine.Engine, *, user: str = "", ok: Optional[bool] = None, since: Optional[datetime] = None,
                before: Optional[int] = None, page_size: int = 200) -> dict[str, Any]:
    stmt = sa.select(LOGINS)
    if user:
        stmt = stmt.where(LOGINS.c.username == user.strip().lower())
    if ok is not None:
        stmt = stmt.where(LOGINS.c.ok == ok)
    if since:
        stmt = stmt.where(LOGINS.c.at >= since)
    if before:
        stmt = stmt.where(LOGINS.c.id < before)
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(LOGINS.c.id.desc()).limit(page_size + 1)).mappings().all()
    items = [{"id": r["id"], "at": _iso(r["at"]), "username": r["username"], "ok": bool(r["ok"]), "reason": r["reason"],
              "reasonLabel": REASON_LABEL.get(r["reason"], r["reason"]), "addr": r["addr"]} for r in rows[:page_size]]
    return {"items": items, "next": items[-1]["id"] if len(rows) > page_size and items else None}


def last_logins(engine: sa.engine.Engine) -> dict[str, datetime]:
    with engine.connect() as c:
        return {u: _aware(at) for u, at in c.execute(
            sa.select(LOGINS.c.username, sa.func.max(LOGINS.c.at)).where(LOGINS.c.ok.is_(True), LOGINS.c.reason == "ok")
            .group_by(LOGINS.c.username)).all()}


# ------------------------------------------------------------------ kurallar ve uyarılar


def _windows(events: list[tuple[datetime, Any]], width: timedelta, need: int) -> list[list[tuple[datetime, Any]]]:
    """Zamana göre sıralı olaylarda `width` genişliğinde en az `need` olay taşıyan, birbiriyle örtüşmeyen pencereler."""
    out, i = [], 0
    ev = sorted(events, key=lambda x: x[0])
    j = 0
    while j < len(ev):
        while ev[j][0] - ev[i][0] > width:
            i += 1
        if j - i + 1 >= need:
            k = j
            while k + 1 < len(ev) and ev[k + 1][0] - ev[i][0] <= width:
                k += 1
            out.append(ev[i:k + 1])
            i = j = k + 1
            continue
        j += 1
    return out


def _alert_exists(c: Any, dedup: str) -> bool:
    return c.execute(sa.select(ALERTS.c.id).where(ALERTS.c.dedup == dedup)).first() is not None


def _open_alert(c: Any, rule: str, user: Optional[str], severity: str, summary: str, evidence: Any, dedup: str,
                now: datetime) -> Optional[dict[str, Any]]:
    if _alert_exists(c, dedup):
        return None
    res = c.execute(ALERTS.insert().values(at=now, rule=rule, username=user, severity=severity, summary=summary,
                                           evidence_json=json.dumps(evidence, ensure_ascii=False, default=str)[:20000],
                                           dedup=dedup[:200], state="open"))
    return {"id": res.inserted_primary_key[0], "rule": rule, "ruleLabel": RULE_LABEL.get(rule, rule), "username": user,
            "severity": severity, "summary": summary}


def _fmt_local(at: datetime) -> str:
    return _aware(at).astimezone(_local_tz()).strftime("%d.%m.%Y %H:%M")


def evaluate(engine: sa.engine.Engine, tenant: str, now: Optional[datetime] = None, *,
             admin_set: Optional[Iterable[str]] = None, everyone: Optional[dict[str, Any]] = None,
             retention_last_ok: Optional[datetime] = None, cfg: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Kuralları son değerlendirmeden bu yana gelen olaylara uygular; yeni uyarıları döndürür.
    `admin_set` ve `everyone` (Herkes rolünün {all, perms}) çağıran tarafından verilir ki kural saf kalsın."""
    ensure(engine)
    now = now or _now()
    cfg = cfg or settings()
    last = state_get(engine, "rules_at")
    last_at = datetime.fromisoformat(last) if last else now - timedelta(days=1)
    new: list[dict[str, Any]] = []
    with engine.begin() as c:
        # 1) Art arda hatalı giriş: aynı hesap, W dakikada ≥ N.
        w = timedelta(minutes=cfg["failWindowMin"])
        rows = c.execute(sa.select(LOGINS.c.id, LOGINS.c.at, LOGINS.c.username, LOGINS.c.addr).where(
            LOGINS.c.ok.is_(False), LOGINS.c.reason.in_(FAILED_REASONS), LOGINS.c.at >= last_at - w)).all()
        by_user: dict[str, list[tuple[datetime, Any]]] = {}
        for rid, at, u, addr in rows:
            by_user.setdefault(u, []).append((_aware(at), (rid, addr)))
        for u, evs in by_user.items():
            for win in _windows(evs, w, cfg["failThreshold"]):
                addrs = sorted({a for _, (_, a) in win if a})
                summary = (f"«{u}» hesabına {_fmt_local(win[0][0])}–{_fmt_local(win[-1][0])} arasında {len(win)} hatalı giriş "
                           f"denendi (eşik: {cfg['failWindowMin']} dakikada {cfg['failThreshold']})"
                           + (f"; kaynak adres: {', '.join(addrs)}." if addrs else "."))
                a = _open_alert(c, "hatali_giris", u, "kritik", summary,
                                {"events": [i for _, (i, _) in win], "addrs": addrs}, f"hatali_giris:{u}:{win[0][1][0]}", now)
                if a:
                    new.append(a)
        # 2) Mesai dışı toplu dışa aktarma: aynı kişi, 60 dakikada ≥ N, mesai dışı.
        w2 = timedelta(minutes=cfg["offhoursWindowMin"])
        rows = c.execute(sa.select(ACCESS.c.id, ACCESS.c.at, ACCESS.c.username, ACCESS.c.path, ACCESS.c.detail_json).where(
            ACCESS.c.kind == "export", ACCESS.c.at >= last_at - w2)).all()
        by_user = {}
        for rid, at, u, path, det in rows:
            if off_hours(at, cfg):
                what = (json.loads(det).get("what") if det else None) or path
                by_user.setdefault(u, []).append((_aware(at), (rid, what)))
        for u, evs in by_user.items():
            for win in _windows(evs, w2, cfg["offhoursExportMin"]):
                whats = sorted({str(x) for _, (_, x) in win})[:10]
                summary = (f"«{u}» mesai dışında ({_fmt_local(win[0][0])}–{_fmt_local(win[-1][0])}) {len(win)} dışa aktarma yaptı: "
                           + "; ".join(whats) + ".")
                a = _open_alert(c, "mesai_disi_aktarim", u, "kritik", summary, {"events": [i for _, (i, _) in win]},
                                f"mesai_disi_aktarim:{u}:{win[0][1][0]}", now)
                if a:
                    new.append(a)
    # 3) Yeni yönetici: ilk görüntü yalnız taban kaydedilir.
    if admin_set is not None:
        cur = sorted({x.strip().lower() for x in admin_set if x and x.strip()})
        seen = state_get(engine, "admins_seen")
        if seen is not None:
            with engine.begin() as c:
                for u in sorted(set(cur) - set(seen)):
                    a = _open_alert(c, "yeni_yonetici", u, "kritik",
                                    f"«{u}» yönetici oldu (yönetici listesi ya da yönetici AD grubu). Yönetici her ekranı ve her veriyi görür.",
                                    {"before": seen, "after": cur}, f"yeni_yonetici:{u}:{now.date().isoformat()}", now)
                    if a:
                        new.append(a)
        state_set(engine, "admins_seen", cur)
    # 4) «Herkes» genişledi: bütün yetkiler açıldı ya da yeni anahtar eklendi.
    if everyone is not None:
        cur_e = {"all": bool(everyone.get("all")), "perms": sorted(everyone.get("perms") or [])}
        seen_e = state_get(engine, "everyone_seen")
        if seen_e is not None:
            added = sorted(set(cur_e["perms"]) - set(seen_e.get("perms") or []))
            widened = (cur_e["all"] and not seen_e.get("all")) or (not cur_e["all"] and added)
            if widened:
                what = "bütün sayfa ve işlemler açıldı" if cur_e["all"] and not seen_e.get("all") else "eklenen: " + ", ".join(added)
                key = hashlib.sha256(json.dumps(cur_e, sort_keys=True).encode()).hexdigest()[:16]
                with engine.begin() as c:
                    a = _open_alert(c, "herkes_genisledi", None, "kritik",
                                    f"Giriş yapan herkese uygulanan «Herkes» rolü genişledi ({what}).",
                                    {"before": seen_e, "after": cur_e}, f"herkes_genisledi:{key}", now)
                    if a:
                        new.append(a)
        state_set(engine, "everyone_seen", cur_e)
    # 5) Saklama işi 2 gece üst üste çalışmadı (yalnız uygulama açıkken).
    if cfg["apply"]:
        applied_on = state_get(engine, "retention_apply_on")
        since = retention_last_ok or (datetime.fromisoformat(applied_on) if applied_on else None)
        if since is not None and now - _aware(since) > timedelta(hours=48):
            with engine.begin() as c:
                a = _open_alert(c, "saklama_durdu", None, "kritik",
                                f"Saklama süresi işi {_fmt_local(since)}'den beri başarıyla çalışmadı; süresi dolmuş kayıtlar duruyor.",
                                {"lastOk": _iso(since)}, f"saklama_durdu:{now.astimezone(_local_tz()).date().isoformat()}", now)
                if a:
                    new.append(a)
    state_set(engine, "rules_at", _iso(now))
    return new


def alert_text(alerts: list[dict[str, Any]], link: str) -> str:
    lines = ["Portal güvenlik uyarıları:", ""]
    for a in alerts:
        lines.append(f"- [{RULE_LABEL.get(a['rule'], a['rule'])}] {a['summary']}")
    if link:
        lines += ["", f"İnceleyin: {link}"]
    lines += ["", "Bu e-posta portalın güvenlik kurallarından kendiliğinden gelir; uyarıyı ekranda «gerçek / gerçek değil» diye kapatın."]
    return "\n".join(lines)


def mark_mailed(engine: sa.engine.Engine, ids: list[int], status: str) -> None:
    if ids:
        with engine.begin() as c:
            c.execute(ALERTS.update().where(ALERTS.c.id.in_(ids)).values(mailed=status))


def list_alerts(engine: sa.engine.Engine, *, state: str = "open", before: Optional[int] = None,
                page_size: int = 200) -> dict[str, Any]:
    stmt = sa.select(ALERTS)
    if state in ("open", "closed"):
        stmt = stmt.where(ALERTS.c.state == state)
    if before:
        stmt = stmt.where(ALERTS.c.id < before)
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(ALERTS.c.id.desc()).limit(page_size + 1)).mappings().all()
        counts = {s: n for s, n in c.execute(sa.select(ALERTS.c.state, sa.func.count()).group_by(ALERTS.c.state)).all()}
    items = [_alert_view(r) for r in rows[:page_size]]
    return {"items": items, "next": items[-1]["id"] if len(rows) > page_size and items else None,
            "counts": {"open": counts.get("open", 0), "closed": counts.get("closed", 0)}}


def _alert_view(r: Any) -> dict[str, Any]:
    return {"id": r["id"], "at": _iso(r["at"]), "rule": r["rule"], "ruleLabel": RULE_LABEL.get(r["rule"], r["rule"]),
            "username": r["username"], "severity": r["severity"], "summary": r["summary"],
            "evidence": json.loads(r["evidence_json"]) if r["evidence_json"] else None, "state": r["state"],
            "closedBy": r["closed_by"], "closedAt": _iso(r["closed_at"]), "verdict": r["verdict"], "note": r["note"],
            "mailed": r["mailed"]}


def close_alert(engine: sa.engine.Engine, alert_id: int, actor: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Uyarıyı kapatır («gerçek» / «gerçek değil» + not) ya da yeniden açar (`state='open'`)."""
    state = str(body.get("state") or "closed")
    verdict = body.get("verdict")
    note = " ".join(str(body.get("note") or "").split())[:2000]
    with engine.begin() as c:
        row = c.execute(sa.select(ALERTS).where(ALERTS.c.id == alert_id)).mappings().first()
        if not row:
            raise SecurityError("Uyarı bulunamadı.", 404)
        before = {"state": row["state"], "verdict": row["verdict"], "note": row["note"]}
        if state == "open":
            vals = {"state": "open", "closed_by": None, "closed_at": None, "verdict": None}
        elif state == "closed":
            if verdict not in ("gercek", "gercek-degil"):
                raise SecurityError("Kapatırken «gerçek» ya da «gerçek değil» seçilmeli.")
            if verdict == "gercek-degil" and not note:
                raise SecurityError("«Gerçek değil» diye kapatırken nedenini yazın (ör. zamanlanmış iş).")
            vals = {"state": "closed", "closed_by": actor, "closed_at": _now(), "verdict": verdict}
        else:
            raise SecurityError("Durum «open» ya da «closed» olmalı.")
        if note:
            vals["note"] = note
        c.execute(ALERTS.update().where(ALERTS.c.id == alert_id).values(**vals))
        after = c.execute(sa.select(ALERTS).where(ALERTS.c.id == alert_id)).mappings().first()
    return _alert_view(after), {"from": before, "to": {"state": after["state"], "verdict": after["verdict"], "note": after["note"]}}


def digest_text(engine: sa.engine.Engine, store_engine: sa.engine.Engine, tenant: str, ds: str, now: datetime) -> Optional[str]:
    """Günlük özet: son 24 saatte kişi başına 403 ve yetki dışı soru sayısı. Hiç yoksa None (e-posta gitmez)."""
    since = now - timedelta(hours=24)
    counts: dict[str, dict[str, int]] = {}
    with engine.connect() as c:
        for u, n in c.execute(sa.select(ACCESS.c.username, sa.func.count()).where(
                ACCESS.c.kind == "forbidden", ACCESS.c.at >= since).group_by(ACCESS.c.username)).all():
            counts.setdefault(u, {"forbidden": 0, "not_permitted": 0})["forbidden"] = n
    try:
        from semantic_layer.store import schema as S
        Q = S.sl_query_log
        with store_engine.connect() as c:
            for u, n in c.execute(sa.select(sa.func.lower(Q.c.username), sa.func.count()).where(
                    Q.c.tenant_id == tenant, Q.c.datasource_id == ds, Q.c.answer_type == "NOT_PERMITTED",
                    Q.c.created_at >= since).group_by(sa.func.lower(Q.c.username))).all():
                counts.setdefault(u or "?", {"forbidden": 0, "not_permitted": 0})["not_permitted"] = n
    except Exception as e:  # noqa: BLE001
        log.warning("güvenlik: günlük özette soru kaydı okunamadı: %s", e)
    if not counts:
        return None
    lines = [f"Son 24 saat ({_fmt_local(since)} – {_fmt_local(now)}): yetkisiz erişim denemesi ve yetki dışı soru, kişi bazında.", ""]
    for u, v in sorted(counts.items(), key=lambda kv: -(kv[1]["forbidden"] + kv[1]["not_permitted"])):
        lines.append(f"- {u}: {v['forbidden']} sayfa/işlem reddi, {v['not_permitted']} yetki dışı soru")
    lines += ["", "Çoğu, rolü henüz atanmamış kişinin menüde görmediği bir bağlantıyı açmasıdır; tekrarlayan kişi için rolü gözden geçirin."]
    return "\n".join(lines)


# ------------------------------------------------------------------ saklama süresi

#: Saklama nesneleri. `default` gün önerisidir; uygulanması `SECURITY_RETENTION_APPLY` açıkken olur.
#: Gerekçeler: docs/GELISTIRME-GUNLUGU.md 2026-09-28 M49 girişi.
RETENTION: list[dict[str, Any]] = [
    {"id": "query_result", "key": "SECURITY_RETENTION_QUERY_RESULT_DAYS", "default": 90, "label": "Soru sonuçları",
     "what": "Soru kaydındaki tam sonuç tablosu boşaltılır; soru, SQL, özet ve inceleme notu kalır."},
    {"id": "llm_text", "key": "SECURITY_RETENTION_LLM_TEXT_DAYS", "default": 30, "label": "Model sırasındaki metinler",
     "what": "Model sırasındaki soru metni ile model işinin mesajı ve cevabı boşaltılır; süre ve sayılar kalır."},
    {"id": "login", "key": "SECURITY_RETENTION_LOGIN_DAYS", "default": 365, "label": "Giriş kaydı",
     "what": "Süresi dolan giriş olayları silinir."},
    {"id": "access", "key": "SECURITY_RETENTION_ACCESS_DAYS", "default": 365, "label": "Erişim kaydı",
     "what": "Süresi dolan yetkisiz erişim ve dışa aktarma satırları silinir."},
    {"id": "alert", "key": "SECURITY_RETENTION_ALERT_DAYS", "default": 730, "label": "Kapanmış güvenlik uyarıları",
     "what": "Kapatılmış ve süresi dolmuş uyarılar silinir; açık uyarıya dokunulmaz."},
    {"id": "audit", "key": "SECURITY_RETENTION_AUDIT_DAYS", "default": 0, "label": "Değişiklik kaydı",
     "what": "Süresi dolan değişiklik kaydı satırları silinir. 0 = süresiz (yetki değişikliklerinin kanıtı)."},
]
_BY_OBJ = {o["id"]: o for o in RETENTION}
_BATCH = 2000


def _targets(obj: str, tenant: str, ds: str, cutoff: datetime) -> list[dict[str, Any]]:
    """Nesnenin dokunduğu tablolar: (tablo, kimlik kolonu, tarih kolonu, koşul, işlem). İşlem `delete` ya da
    boşaltılacak kolonların değerleri."""
    from semantic_bridge import admin as admin_mod
    from semantic_layer.store import schema as S

    if obj == "query_result":
        Q = S.sl_query_log
        return [{"table": Q, "id": Q.c.id, "date": Q.c.created_at,
                 "where": [Q.c.tenant_id == tenant, Q.c.datasource_id == ds, Q.c.created_at < cutoff, Q.c.result_json.isnot(None)],
                 "action": {"result_json": sa.null()}}]
    if obj == "llm_text":
        L, J = S.sl_llm_queue, S.sl_llm_job
        return [{"table": L, "id": L.c.id, "date": L.c.enqueued_at,
                 "where": [L.c.enqueued_at < cutoff, L.c.question.isnot(None), L.c.status.in_(("DONE", "ABANDONED"))],
                 "action": {"question": sa.null()}},
                {"table": J, "id": J.c.id, "date": J.c.created_at,
                 "where": [J.c.created_at < cutoff, J.c.status.in_(("DONE", "FAILED", "CANCELLED")),
                           sa.or_(J.c.messages_json != "[]", J.c.result.isnot(None))],
                 "action": {"messages_json": "[]", "result": sa.null()}}]
    if obj == "login":
        return [{"table": LOGINS, "id": LOGINS.c.id, "date": LOGINS.c.at, "where": [LOGINS.c.at < cutoff], "action": "delete"}]
    if obj == "access":
        return [{"table": ACCESS, "id": ACCESS.c.id, "date": ACCESS.c.at, "where": [ACCESS.c.at < cutoff], "action": "delete"}]
    if obj == "alert":
        return [{"table": ALERTS, "id": ALERTS.c.id, "date": ALERTS.c.at,
                 "where": [ALERTS.c.at < cutoff, ALERTS.c.state == "closed"], "action": "delete"}]
    if obj == "audit":
        A = admin_mod.AUDIT
        return [{"table": A, "id": A.c.id, "date": A.c.at, "where": [A.c.at < cutoff], "action": "delete"}]
    raise SecurityError(f"Bilinmeyen saklama nesnesi: {obj}")


def _engine_for(obj: str, meta: sa.engine.Engine, store: sa.engine.Engine) -> sa.engine.Engine:
    return store if obj in ("query_result", "llm_text") else meta


def preview(meta: sa.engine.Engine, store: sa.engine.Engine, tenant: str, ds: str, now: Optional[datetime] = None,
            days: Optional[dict[str, int]] = None) -> list[dict[str, Any]]:
    """Her nesne için: süre, kesim tarihi, etkilenecek satır sayısı ve tarih aralığı. `days` verilirse o sürelerle
    hesaplanır (ekranda kaydetmeden önce «bu süreyle kaç satır» sorusu)."""
    now = now or _now()
    cfg = settings()
    out = []
    for o in RETENTION:
        d = (days or {}).get(o["id"], cfg["days"][o["id"]])
        item = {"id": o["id"], "label": o["label"], "what": o["what"], "key": o["key"], "days": d,
                "defaultDays": o["default"], "cutoff": None, "rows": None, "from": None, "to": None, "error": None}
        if d > 0:
            cutoff = now - timedelta(days=d)
            item["cutoff"] = _iso(cutoff)
            try:
                n, lo, hi = 0, None, None
                eng = _engine_for(o["id"], meta, store)
                with eng.connect() as c:
                    for t in _targets(o["id"], tenant, ds, cutoff):
                        cnt, mn, mx = c.execute(sa.select(sa.func.count(), sa.func.min(t["date"]), sa.func.max(t["date"]))
                                                .select_from(t["table"]).where(*t["where"])).one()
                        n += int(cnt or 0)
                        lo = min(x for x in (lo, _aware(mn)) if x) if (lo or mn) else None
                        hi = max(x for x in (hi, _aware(mx)) if x) if (hi or mx) else None
                item.update(rows=n, **{"from": _iso(lo), "to": _iso(hi)})
            except Exception as e:  # noqa: BLE001
                item["error"] = f"{type(e).__name__}: {e}"[:300]
        out.append(item)
    return out


def _apply_one(eng: sa.engine.Engine, t: dict[str, Any]) -> int:
    """Koşula uyan satırları parti parti işler; parti boyu tavan değildir, iş bitene kadar döner."""
    done = 0
    while True:
        with eng.begin() as c:
            ids = [r[0] for r in c.execute(sa.select(t["id"]).where(*t["where"]).limit(_BATCH)).all()]
            if not ids:
                return done
            if t["action"] == "delete":
                c.execute(t["table"].delete().where(t["id"].in_(ids)))
            else:
                c.execute(t["table"].update().where(t["id"].in_(ids)).values(**t["action"]))
            done += len(ids)
        if len(ids) < _BATCH:
            return done


def run_retention(meta: sa.engine.Engine, store: sa.engine.Engine, tenant: str, ds: str, *,
                  now: Optional[datetime] = None, actor: str = "zamanlayici") -> dict[str, Any]:
    """Gece işi: her nesne için önce önizleme satırı; `SECURITY_RETENTION_APPLY` açık ve süre > 0 ise uygulama satırı
    (etkilenen satır, tarih aralığı). Kapalıyken hiçbir şey silinmez."""
    ensure(meta)
    now = now or _now()
    cfg = settings()
    prev = preview(meta, store, tenant, ds, now)
    results = []
    with meta.begin() as c:
        for p in prev:
            c.execute(RUNS.insert().values(at=now, object=p["id"], mode="onizleme", days=p["days"],
                                           cutoff=datetime.fromisoformat(p["cutoff"]) if p["cutoff"] else None,
                                           rows_affected=p["rows"], range_from=datetime.fromisoformat(p["from"]) if p["from"] else None,
                                           range_to=datetime.fromisoformat(p["to"]) if p["to"] else None,
                                           ok=p["error"] is None, error=p["error"], actor=actor))
    all_ok = True
    for p in prev:
        if not cfg["apply"] or p["days"] <= 0 or p["error"] or not p["rows"]:
            results.append({"id": p["id"], "mode": "onizleme", "rows": p["rows"], "error": p["error"]})
            if p["error"]:
                all_ok = False
            continue
        cutoff = datetime.fromisoformat(p["cutoff"])
        err = None
        n = 0
        try:
            eng = _engine_for(p["id"], meta, store)
            for t in _targets(p["id"], tenant, ds, cutoff):
                n += _apply_one(eng, t)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"[:400]
            all_ok = False
            log.warning("güvenlik: saklama uygulanamadı (%s): %s", p["id"], e)
        with meta.begin() as c:
            c.execute(RUNS.insert().values(at=_now(), object=p["id"], mode="uygulama", days=p["days"], cutoff=cutoff,
                                           rows_affected=n, range_from=datetime.fromisoformat(p["from"]) if p["from"] else None,
                                           range_to=datetime.fromisoformat(p["to"]) if p["to"] else None,
                                           ok=err is None, error=err, actor=actor))
        results.append({"id": p["id"], "mode": "uygulama", "rows": n, "error": err})
    if all_ok:
        state_set(meta, "retention_ok_at", _iso(now))
    return {"apply": cfg["apply"], "ok": all_ok, "objects": results}


def list_runs(engine: sa.engine.Engine, *, before: Optional[int] = None, page_size: int = 200) -> dict[str, Any]:
    stmt = sa.select(RUNS)
    if before:
        stmt = stmt.where(RUNS.c.id < before)
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(RUNS.c.id.desc()).limit(page_size + 1)).mappings().all()
    items = [{"id": r["id"], "at": _iso(r["at"]), "object": r["object"],
              "objectLabel": _BY_OBJ.get(r["object"], {}).get("label", r["object"]), "mode": r["mode"], "days": r["days"],
              "cutoff": _iso(r["cutoff"]), "rows": r["rows_affected"], "from": _iso(r["range_from"]), "to": _iso(r["range_to"]),
              "ok": bool(r["ok"]), "error": r["error"], "actor": r["actor"]} for r in rows[:page_size]]
    return {"items": items, "next": items[-1]["id"] if len(rows) > page_size and items else None}


def last_retention_ok(engine: sa.engine.Engine) -> Optional[datetime]:
    v = state_get(engine, "retention_ok_at")
    return datetime.fromisoformat(v) if v else None


def retention_update(engine: sa.engine.Engine, actor: str, body: dict[str, Any], preview_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Süreleri ve uygulama anahtarını `admin.conf`'a yazar (değişiklik kaydıyla). Uygulamayı açmak için ekranın
    önizlemeyi gösterdiğini söylemesi (`onizlemeGoruldu`) şarttır."""
    from semantic_bridge import admin as admin_mod

    values: dict[str, Any] = {}
    for oid, d in (body.get("days") or {}).items():
        o = _BY_OBJ.get(oid)
        if not o:
            raise SecurityError(f"Bilinmeyen saklama nesnesi: {oid}")
        try:
            n = int(d)
        except (TypeError, ValueError):
            raise SecurityError(f"«{o['label']}» için gün sayısı tam sayı olmalı.") from None
        if n < 0:
            raise SecurityError(f"«{o['label']}» için gün sayısı eksi olamaz.")
        if 0 < n < 7:
            raise SecurityError(f"«{o['label']}» için en kısa süre 7 gündür (0 = süresiz).")
        values[o["key"]] = str(n)
    turning_on = False
    if "apply" in body:
        want = bool(body.get("apply"))
        turning_on = want and not settings()["apply"]
        if turning_on and not body.get("onizlemeGoruldu"):
            raise SecurityError("Uygulamayı açmadan önce hangi kaydın ne kadar etkileneceğini gösteren önizlemeye bakın.")
        values["SECURITY_RETENTION_APPLY"] = "1" if want else "0"
    if not values:
        raise SecurityError("Değişiklik yok.")
    try:
        out = admin_mod.save_settings(engine, actor, values)
    except admin_mod.AdminError as e:
        raise SecurityError(str(e)) from e
    if turning_on:
        state_set(engine, "retention_apply_on", _iso(_now()))
        admin_mod.audit(engine, actor, "approve", "setting", "SECURITY_RETENTION_APPLY", "Saklama süresi uygulaması açıldı",
                        {"onizleme": [{"nesne": p["id"], "gun": p["days"], "satir": p["rows"]} for p in preview_rows]})
    return {"changed": out.get("changed", [])}


# ------------------------------------------------------------------ hesap hijyeni


HYGIENE_KIND = {
    "oturum_ad_disi": ("Açık oturumu var, AD'de etkin değil", "kritik"),
    "yonetici_ad_disi": ("Yönetici listesinde, AD'de etkin değil", "kritik"),
    "bag_ad_disi": ("Role kişi olarak bağlı, AD'de etkin değil", "uyari"),
    "crm_etkin_ad_kapali": ("CRM'de etkin, AD'de etkin değil", "uyari"),
    "test_adi": ("Test/deneme adı taşıyan hesap", "uyari"),
    "uzun_suredir_girmedi": ("Uzun süredir giriş yapmamış", "bilgi"),
    "yalniz_herkes": ("Rolü yok, yalnız «Herkes» ile giriyor", "bilgi"),
}


def hygiene(meta: sa.engine.Engine, tenant: str, ds: str, *, directory: Any, sessions: Optional[list[dict[str, Any]]],
            is_admin: Callable[[str], bool], now: Optional[datetime] = None) -> dict[str, Any]:
    """Hesap hijyeni raporu (analiz §4.1): deterministik; AD, CRM ve portal izlerinin kesişimi. Okunamayan kaynak
    notlarda yazar ve o kaynağa dayanan bulgu çıkmaz (yanlış «AD'de yok» demek için)."""
    from semantic_bridge import access as A
    from semantic_bridge import admin as admin_mod

    now = now or _now()
    cfg = settings()
    notes: list[str] = []
    ad: Optional[dict[str, str]] = None
    try:
        ad = {p["subject"].lower(): p.get("label") or p["subject"] for p in directory.list_people()}
    except Exception as e:  # noqa: BLE001
        notes.append(f"Active Directory okunamadı ({type(e).__name__}); AD'ye dayanan bulgular çıkmadı.")
    crm: Optional[dict[str, str]] = None
    try:
        p = directory._crm_prefix()
        rows = directory._crm_rows(
            f"SELECT FullName, DomainName FROM {p}SystemUserBase WHERE IsDisabled = 0 AND AccessMode IN (0, 1) "
            f"AND DomainName IS NOT NULL AND DomainName <> ''")
        crm = {}
        for r in rows:
            acc = A._account(r.get("DomainName"))
            if acc:
                crm[acc] = str(r.get("FullName") or acc)
    except Exception as e:  # noqa: BLE001
        notes.append(f"CRM kullanıcıları okunamadı ({type(e).__name__}); CRM–AD karşılaştırması çıkmadı.")
    if sessions is None:
        notes.append("Giriş servisinin oturum listesi okunamadı; açık oturum bulguları çıkmadı.")

    last = last_logins(meta)
    with meta.connect() as c:
        first_login = c.execute(sa.select(sa.func.min(LOGINS.c.at))).scalar()
    first_login = _aware(first_login)
    footprint: dict[str, set[str]] = {}

    def mark(u: Optional[str], why: str) -> None:
        if u:
            footprint.setdefault(u.strip().lower(), set()).add(why)

    for u in admin_mod.admins():
        mark(u, "yönetici listesi")
    try:
        for p in admin_mod.users(meta, tenant, ds):
            mark(p["username"], "portal kaydı")
    except Exception as e:  # noqa: BLE001
        notes.append(f"Portal kullanıcı izleri okunamadı ({type(e).__name__}).")
    st = A._load(meta, tenant)
    user_bindings: dict[str, list[str]] = {}
    for b in st["bindings"]:
        if b["subject_type"] == "user":
            u = str(b["subject"]).lower()
            mark(u, "rol bağı")
            user_bindings.setdefault(u, []).append(st["roles"].get(b["role_id"], {}).get("name", b["role_id"]))
    for u in last:
        mark(u, "giriş kaydı")
    for s in sessions or []:
        mark(s.get("username"), "açık oturum")

    items: list[dict[str, Any]] = []

    def add(kind: str, u: str, detail: str, display: Optional[str] = None) -> None:
        label, sev = HYGIENE_KIND[kind]
        items.append({"kind": kind, "kindLabel": label, "severity": sev, "username": u,
                      "display": display or (ad or {}).get(u) or (crm or {}).get(u) or u, "detail": detail,
                      "lastLogin": _iso(last.get(u)), "sources": sorted(footprint.get(u, set()))})

    if ad is not None:
        open_by_user: dict[str, int] = {}
        for s in sessions or []:
            u = str(s.get("username") or "").lower()
            if u:
                open_by_user[u] = open_by_user.get(u, 0) + 1
        for u, n in sorted(open_by_user.items()):
            if u not in ad:
                add("oturum_ad_disi", u, f"{n} açık oturum; kişi AD'de etkin görünmüyor. Oturumlarını kapatın.")
        for u in admin_mod.admins():
            if u not in ad:
                add("yonetici_ad_disi", u, "TIMAS_ADMIN_USERS listesinde; AD'de etkin hesap yok.")
        for u, roles in sorted(user_bindings.items()):
            if u not in ad:
                add("bag_ad_disi", u, "Bağlı roller: " + ", ".join(sorted(set(roles))))
        if crm is not None:
            for u, name in sorted(crm.items()):
                if u not in ad:
                    add("crm_etkin_ad_kapali", u, "CRM'de etkin kullanıcı; AD'de etkin hesap yok (AD'de kapalı ya da adı değişmiş).", name)
    try:
        test_rx = re.compile(cfg["testPattern"], re.I)
    except re.error:
        test_rx = None
        notes.append("Test hesabı kalıbı geçersiz; bu bulgu çıkmadı.")
    if test_rx is not None:
        for u in sorted(footprint):
            if test_rx.search(u):
                add("test_adi", u, "İz: " + ", ".join(sorted(footprint[u])))
    if cfg["idleDays"] > 0:
        border = now - timedelta(days=cfg["idleDays"])
        for u in sorted(footprint):
            seen = last.get(u)
            if seen is not None and seen < border:
                add("uzun_suredir_girmedi", u, f"Son giriş {_fmt_local(seen)}; eşik {cfg['idleDays']} gün.")
    recent = {u for u, t in last.items() if cfg["idleDays"] <= 0 or t >= now - timedelta(days=cfg["idleDays"])}
    for u in sorted(recent):
        if is_admin(u):
            continue
        acc = A.effective(meta, tenant, u, lambda _x: False)
        if all(r["id"] == A._role_id(tenant, A.EVERYONE_ID) for r in acc.roles):
            add("yalniz_herkes", u, "Yalnız «Herkes» rolüyle giriyor; «Herkes» daraltılınca bu kişi menüde yalnız Kampüs'ü görür.")
    if first_login is None:
        notes.append("Giriş kaydı henüz boş: «uzun süredir girmedi» ve «rolü yok» bulguları giriş kaydı biriktikçe dolar.")
    counts: dict[str, int] = {}
    for it in items:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
    order = {"kritik": 0, "uyari": 1, "bilgi": 2}
    items.sort(key=lambda x: (order.get(x["severity"], 9), x["kind"], x["username"]))
    return {"items": items, "counts": counts, "kinds": {k: {"label": v[0], "severity": v[1]} for k, v in HYGIENE_KIND.items()},
            "notes": notes, "sources": {"ad": ad is not None, "crm": crm is not None, "sessions": sessions is not None,
                                        "adPeople": len(ad or {}), "crmUsers": len(crm or {})},
            "loginsSince": _iso(first_login), "at": _iso(now)}


# ------------------------------------------------------------------ «Herkes» daraltma önizlemesi


def _matches(st: dict[str, Any], user: str) -> set[str]:
    u = user.lower()
    hit = {rid for rid, r in st["roles"].items() if r["is_system"]}
    for b in st["bindings"]:
        t, s = b["subject_type"], str(b["subject"]).strip().lower()
        if ((u == s) if t == "user" else (u in st["members"].get((t, s), frozenset()))) and b["role_id"] in st["roles"]:
            hit.add(b["role_id"])
    return hit


def _granted(st: dict[str, Any], roles: set[str], override: Optional[tuple[str, bool, frozenset[str]]]) -> frozenset[str]:
    from semantic_bridge import access as A

    every, perms = False, set()
    for rid in roles:
        r = st["roles"][rid]
        if override and rid == override[0]:
            every = every or override[1]
            perms |= set(override[2])
        else:
            every = every or bool(r["all_perms"])
            perms |= r["perms"]
    perms &= A.all_keys()
    return (A.all_keys() - A.explicit_keys()) | frozenset(perms) if every else frozenset(perms)


def preview_everyone(meta: sa.engine.Engine, tenant: str, *, people: dict[str, str], is_admin: Callable[[str], bool],
                     perms: Optional[Iterable[str]] = None, remove: Optional[Iterable[str]] = None,
                     all_perms: bool = False) -> dict[str, Any]:
    """«Herkes» rolü şu hâle gelirse kim neyi kaybeder / kazanır. `perms` yeni anahtar listesidir; verilmezse bugünkü
    Herkes yetkisinden `remove` çıkarılır. Yönetici bir şey kaybetmez (sayılır ama listelenmez). `people` hesap → ad."""
    from semantic_bridge import access as A

    A.ensure(meta, tenant)
    A.invalidate()
    st = A._load(meta, tenant)
    rid = A._role_id(tenant, A.EVERYONE_ID)
    if rid not in st["roles"]:
        raise SecurityError("«Herkes» rolü bulunamadı.", 404)
    herkes = st["roles"][rid]
    current = (A.all_keys() - A.explicit_keys()) | frozenset(herkes["perms"]) if herkes["all_perms"] else frozenset(herkes["perms"])
    keys = A.all_keys()
    if perms is not None:
        new = frozenset(p for p in perms if p)
        unknown = sorted(new - keys)
        if unknown:
            raise SecurityError("Bilinmeyen yetki: " + ", ".join(unknown))
        new_all = bool(all_perms)
    else:
        rm = frozenset(p for p in (remove or []) if p)
        new, new_all = current - rm, False
    labels = {p["key"]: p["label"] for p in A.catalog()["pages"]}
    labels.update({f["key"]: f["label"] for f in A.catalog().get("features", [])})
    labels.update({A.data_key(d["id"]): "Veri: " + d["label"] for d in A.data_domains()})
    per_key: dict[str, int] = {}
    gain_key: dict[str, int] = {}
    rows = []
    admins = 0
    for u in sorted(people):
        if is_admin(u):
            admins += 1
            continue
        roles = _matches(st, u)
        before = _granted(st, roles, None)
        after = _granted(st, roles, (rid, new_all, new))
        lost, gained = sorted(before - after), sorted(after - before)
        for k in lost:
            per_key[k] = per_key.get(k, 0) + 1
        for k in gained:
            gain_key[k] = gain_key.get(k, 0) + 1
        if lost or gained:
            rows.append({"username": u, "display": people.get(u) or u,
                         "roles": sorted(st["roles"][r]["name"] for r in roles if r != rid),
                         "lostPages": [labels.get(k, k) for k in lost if k.startswith("sayfa:")],
                         "lost": [{"key": k, "label": labels.get(k, k)} for k in lost],
                         "gained": [{"key": k, "label": labels.get(k, k)} for k in gained]})
    rows.sort(key=lambda r: (-len(r["lost"]), r["display"].lower()))
    return {"people": len(people), "admins": admins, "affected": len(rows), "items": rows,
            "byKey": sorted(({"key": k, "label": labels.get(k, k), "lose": n} for k, n in per_key.items()),
                            key=lambda x: (-x["lose"], x["label"])),
            "gainByKey": sorted(({"key": k, "label": labels.get(k, k), "gain": n} for k, n in gain_key.items()),
                                key=lambda x: (-x["gain"], x["label"])),
            "current": {"all": bool(herkes["all_perms"]), "perms": sorted(current)},
            "proposed": {"all": new_all, "perms": sorted(new)}}


# ------------------------------------------------------------------ kişisel veri envanteri

#: Ad-soyad kalıbı: yalnız envanterde «kişisel veri (ad)» diye sınıflanır, maskelenmez (analiz §8: maskelenen kolon
#: istemden düşer, ad kolonu sorguları bozar). Ek kalıp `SECURITY_NAME_PATTERNS` (virgülle).
_NAME_RX = r"(^|_)(full_?name|first_?name|last_?name|middle_?name|surname|ad_?soyad|adi_?soyadi|soyad\w*|nick_?name|contact_?name|yetkili\w*)$"


def _name_rx() -> re.Pattern[str]:
    extra = [p for p in os.environ.get("SECURITY_NAME_PATTERNS", "").split(",") if p.strip()]
    return re.compile("|".join([_NAME_RX, *extra]), re.I)


def registry() -> dict[str, Any]:
    data = json.loads(INVENTORY_FILE.read_text(encoding="utf-8"))
    data.pop("_note", None)
    return data


def inventory(meta: sa.engine.Engine, store: sa.engine.Engine, profiles: list[Any]) -> dict[str, Any]:
    """Kaynakta kişisel veri kolonları (katalog profilinden; değer okunmaz) + portal içi kopyalar (defter + canlı satır
    sayısı). Kaynak kolonları: `sensitive` işaretliler (maskeli, istemde yok) ve ad-soyad kalıbına uyanlar (maskesiz)."""
    from semantic_layer.data_source import data_source

    rx = _name_rx()
    # Varlık + kolon başına bir satır: yıllara ait kopyalar (aynı varlığın birden çok tablosu) tek satırda sayılır.
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for p in profiles:
        src = data_source(getattr(p, "schema_name", None))
        for col in getattr(p, "columns", []) or []:
            masked = bool(getattr(col, "sensitive", False))
            if not masked and not rx.search(col.name or ""):
                continue
            key = (p.entity.upper(), (col.name or "").upper())
            row = seen.get(key)
            if row is None:
                row = seen[key] = {"entity": p.entity, "table": getattr(p, "table_name", p.entity), "source": src,
                                   "column": col.name, "tables": 0, "masked": masked,
                                   "reason": (getattr(col, "sensitivity_reason", None) or "kişisel veri") if masked
                                   else "kişisel veri (ad)"}
            row["tables"] += 1
            if masked and not row["masked"]:
                row.update(masked=True, reason=getattr(col, "sensitivity_reason", None) or "kişisel veri")
    source = list(seen.values())
    by_src: dict[str, dict[str, int]] = {}
    for s in source:
        d = by_src.setdefault(s["source"], {"masked": 0, "names": 0})
        d["masked" if s["masked"] else "names"] += 1
    reg = registry()
    cfg = settings()
    portal = []
    for it in reg.get("tables", []):
        eng = store if it["object"].startswith("sl_") else meta
        rows = None
        err = None
        try:
            with eng.connect() as c:
                if sa.inspect(c).has_table(it["object"]):
                    rows = c.execute(sa.text(f'SELECT count(*) FROM "{it["object"]}"')).scalar()  # noqa: S608 — ad defterden
                else:
                    err = "tablo bu kurulumda yok"
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}"
        days = cfg["days"].get(it.get("retention") or "", None)
        portal.append({**it, "kind": "tablo", "rows": rows, "error": err, "retentionDays": days,
                       "retentionLabel": (_BY_OBJ[it["retention"]]["label"] if it.get("retention") in _BY_OBJ else None)})
    for it in reg.get("files", []):
        path = Path(os.environ.get(it.get("env") or "", "") or it.get("default") or "")
        files = size = None
        err = None
        try:
            if path.is_dir():
                files, size = 0, 0
                for f in path.rglob("*"):
                    if f.is_file():
                        files += 1
                        size += f.stat().st_size
            else:
                err = "klasör bu kurulumda yok"
        except OSError as e:
            err = type(e).__name__
        portal.append({**it, "kind": "klasör", "path": str(path), "files": files, "bytes": size, "error": err,
                       "retentionDays": None, "retentionLabel": None})
    return {"source": sorted(source, key=lambda s: (s["source"], s["entity"], s["column"])), "sourceCounts": by_src,
            "sensitiveCount": sum(1 for s in source if s["masked"]), "nameCount": sum(1 for s in source if not s["masked"]),
            "portal": portal}


# ------------------------------------------------------------------ zamanlama


def daily_due(engine: sa.engine.Engine, now: datetime, cfg: dict[str, Any]) -> bool:
    """Günlük kısım (saklama, özet e-posta) yerel saatte `SECURITY_DAILY_AT`'ten sonraki ilk koşuda, günde bir kez."""
    loc = now.astimezone(_local_tz())
    m = re.match(r"^(\d{1,2}):(\d{2})$", cfg["dailyAt"])
    at_min = int(m.group(1)) * 60 + int(m.group(2)) if m else 220
    if loc.hour * 60 + loc.minute < at_min:
        return False
    return state_get(engine, "daily_on") != loc.date().isoformat()


def mark_daily(engine: sa.engine.Engine, now: datetime) -> None:
    state_set(engine, "daily_on", now.astimezone(_local_tz()).date().isoformat())


def summary(meta: sa.engine.Engine, now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or _now()
    since = now - timedelta(hours=24)
    with meta.connect() as c:
        open_alerts = {s: n for s, n in c.execute(sa.select(ALERTS.c.severity, sa.func.count()).where(
            ALERTS.c.state == "open").group_by(ALERTS.c.severity)).all()}
        fails = c.execute(sa.select(sa.func.count()).select_from(LOGINS).where(
            LOGINS.c.ok.is_(False), LOGINS.c.reason.in_(FAILED_REASONS), LOGINS.c.at >= since)).scalar() or 0
        oks = c.execute(sa.select(sa.func.count()).select_from(LOGINS).where(
            LOGINS.c.reason == "ok", LOGINS.c.at >= since)).scalar() or 0
        acc = {k: n for k, n in c.execute(sa.select(ACCESS.c.kind, sa.func.count()).where(
            ACCESS.c.at >= since).group_by(ACCESS.c.kind)).all()}
        last_apply = c.execute(sa.select(RUNS).where(RUNS.c.mode == "uygulama").order_by(RUNS.c.id.desc()).limit(1)).mappings().first()
        last_prev = c.execute(sa.select(RUNS).where(RUNS.c.mode == "onizleme").order_by(RUNS.c.id.desc()).limit(1)).mappings().first()
    return {"openAlerts": {"kritik": open_alerts.get("kritik", 0), "uyari": open_alerts.get("uyari", 0)},
            "last24h": {"loginOk": oks, "loginFailed": fails, "forbidden": acc.get("forbidden", 0), "export": acc.get("export", 0)},
            "retention": {"apply": settings()["apply"], "lastOk": _iso(last_retention_ok(meta)),
                          "lastApply": _iso(last_apply["at"]) if last_apply else None,
                          "lastPreview": _iso(last_prev["at"]) if last_prev else None},
            "loginPull": state_get(meta, "login_pull"), "at": _iso(now)}


def token_ok(supplied: str, token: str) -> bool:
    return bool(token) and hmac.compare_digest(str(supplied or ""), str(token))


def today() -> date:
    return _now().astimezone(_local_tz()).date()
