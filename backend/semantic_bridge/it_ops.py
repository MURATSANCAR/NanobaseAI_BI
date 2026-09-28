"""M48 IT altyapı ve sistem yönetimi: halka denetimleri, olaylar, zamanlanmış işler, sürüm kaydı.

ZEKİ'yi ayakta tutan yedi halka (Logo, CRM, giriş, Zeki AI modeli, e-posta, şirket ağı bağlantısı, müşteri VM'i)
5 dk'da bir denenir (`it_ops_sources.run_rings`, mevcut `admin.run_check` denemelerini çağırır); her sonuç
`semantic_itops_checks`'e yazılır. Art arda `ITOPS_FAILS_TO_OPEN` (2) başarısız deneme bir **kopma olayı** açar, ilk
başarılı deneme kapatır. Logo ve CRM'in son kayıt tarihi («veri sonu») eşiği aşarsa ayrı bir **tazelik olayı** açılır —
okunan Logo kopyası donmuşsa (2026-08-17) bağlantı yeşil olsa bile raporlar eskidir.

Bildirim kenarda gider, yalnız iç alıcılara (`ITOPS_RECIPIENTS`, alan adı `ITOPS_INTERNAL_DOMAINS` içinde olmalı): olay
açılınca bir kez, düzelince bir kez (süresiyle), sürerse `ALERT_REMIND_HOURS` (tazelikte `ITOPS_STALE_REMIND_HOURS`)
sonra hatırlatma. Gönderim olmadıysa sonraki turda yeniden denenir. Aynı turdaki olaylar tek e-postada toplanır.

Denetimler yalnız okur; hiçbir servis yeniden başlatılmaz (analiz §8). Rakamı model üretmez; olay taslağında model
yalnız metni yazar, süre ve sayılar bu tablolardan gelir.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic_bridge.it_ops")

_md = sa.MetaData()

CHECKS = sa.Table(
    "semantic_itops_checks", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("ring", sa.String(24), nullable=False),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ok", sa.Boolean),                       # None: uygulanmaz / ölçülemedi (uydurma yeşil yok)
    sa.Column("latency_ms", sa.Integer),
    sa.Column("data_end", sa.DateTime(timezone=True)),  # Logo/CRM son kayıt
    sa.Column("detail", sa.Text),                      # ekrana giden, teknoloji adı ayıklanmış cümle
    sa.Column("source", sa.String(16), nullable=False),  # timer | manual | watchdog
    sa.Index("ix_itops_checks_ring_at", "tenant_id", "ring", "at"),
)

INCIDENTS = sa.Table(
    "semantic_itops_incidents", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("ring", sa.String(24), nullable=False),
    sa.Column("kind", sa.String(12), nullable=False),  # kopma | tazelik
    sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("closed_at", sa.DateTime(timezone=True)),
    sa.Column("first_error", sa.Text),
    sa.Column("last_error", sa.Text),
    sa.Column("notified_at", sa.DateTime(timezone=True)),
    sa.Column("notify_status", sa.String(16)),         # sent | no_smtp | no_recipient | failed
    sa.Column("reminded_at", sa.DateTime(timezone=True)),
    sa.Column("closed_notify", sa.String(16)),         # sent | ... | skip (açılış bildirilmemişse)
    sa.Column("root_cause", sa.Text),
    sa.Column("root_cause_by", sa.String(120)),
    sa.Column("root_cause_at", sa.DateTime(timezone=True)),
    sa.Column("false_alarm", sa.Boolean, nullable=False, default=False),
    sa.Column("postmortem_draft", sa.Text),
    sa.Column("postmortem_status", sa.String(12), nullable=False, default="yok"),  # yok | taslak | yayında
    sa.Column("postmortem_by", sa.String(120)),
    sa.Column("postmortem_at", sa.DateTime(timezone=True)),
    sa.Index("ix_itops_incidents_open", "tenant_id", "ring", "kind", "closed_at"),
)

JOBS = sa.Table(
    "semantic_itops_jobs", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("job", sa.String(120), primary_key=True),
    sa.Column("label", sa.String(200), nullable=False),
    sa.Column("every", sa.String(40)),
    sa.Column("last_at", sa.DateTime(timezone=True)),
    sa.Column("next_at", sa.DateTime(timezone=True)),
    sa.Column("last_ok", sa.Boolean),
    sa.Column("last_error", sa.Text),
    sa.Column("failed_count", sa.Integer),             # tablo kaynaklı işlerde hatalı kayıt sayısı
    sa.Column("total_count", sa.Integer),
    sa.Column("source", sa.String(16), nullable=False),  # systemd | jobs-container | table | watchdog
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

RELEASES = sa.Table(
    "semantic_itops_releases", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("env", sa.String(8), nullable=False),    # test | vm | gpu
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("code_sha", sa.String(64)),
    sa.Column("image", sa.String(300)),
    sa.Column("appledouble_count", sa.Integer),
    sa.Column("reported_by", sa.String(120)),
    sa.Column("note", sa.Text),
)

#: Tur arası durum: haftalık/günlük özetin en son gönderildiği dönem.
STATE = sa.Table(
    "semantic_itops_state", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(60), primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

#: Yedi halka. Ekranda teknoloji adı yok (bellek no-tech-names-on-screens): model «Zeki AI modeli», VPN «Şirket ağı
#: bağlantısı». `recipe`: kopmada BT'nin yapacağı ilk iş, kısa ve sırasıyla.
RINGS: list[dict[str, str]] = [
    {"id": "logo", "label": "Logo", "hint": "Logo veritabanına bağlantı ve son fatura tarihi",
     "recipe": "Önce «Şirket ağı bağlantısı» halkasına bakın; o da kopuksa önce onu düzeltin. Değilse Logo veritabanı "
               "sunucusunun açık olduğunu ve okuma hesabının kilitlenmediğini kontrol edin. Düzelince 5 dk içinde "
               "kendiliğinden kapanır."},
    {"id": "crm", "label": "CRM", "hint": "CRM veritabanına bağlantı ve son değişiklik zamanı",
     "recipe": "CRM veritabanı sunucusunun açık olduğunu ve okuma hesabının kilitlenmediğini kontrol edin. CRM ekranları "
               "açılıyor ama ZEKİ okuyamıyorsa hesabın parolası değişmiş olabilir: Yönetim → Ayarlar → CRM."},
    {"id": "giris", "label": "Giriş", "hint": "Portal girişini doğrulayan şirket dizini",
     "recipe": "Etki alanı denetleyicisine ulaşılamıyor ya da servis hesabı reddedildi. Servis hesabının kilitli ya da "
               "parolasının süresi dolmuş olmadığını kontrol edin; bu sürede kimse portala giremez."},
    {"id": "model", "label": "Zeki AI modeli", "hint": "Soruları cevaplayan yapay zekâ modeli",
     "recipe": "Zeki AI modeli cevap vermiyor: sorular, taslaklar ve özetler bekler; rakamlar ve hazır ekranlar çalışır. "
               "İşletim ekibine haber verin; model sunucusu onların sorumluluğundadır."},
    {"id": "eposta", "label": "E-posta", "hint": "Uyarı ve raporların gittiği posta sunucusu (gönderim yapılmadan denenir)",
     "recipe": "Posta sunucusuna bağlanılamıyor ya da hesap reddedildi: uyarılar ve planlı raporlar gitmez. Gönderen "
               "hesabın parolasını ya da uygulama şifresini Yönetim → Ayarlar → E-posta'dan kontrol edin."},
    {"id": "vpn", "label": "Şirket ağı bağlantısı", "hint": "Sunucumuzun TİMAŞ ağına bağlantısı",
     "recipe": "Şirket ağı bağlantısı düştü: Logo ve CRM okunamaz. Telefonunuza gelen onay bildirimini verin; 1 dk içinde "
               "bağlantı gelmezse işletim ekibine haber verin."},
    {"id": "vm", "label": "Müşteri VM'i", "hint": "TİMAŞ içindeki uygulama sunucusu ve zamanlanmış işleri",
     "recipe": "Müşteri VM'ine ulaşılamıyor ya da zamanlanmış işler bildirim göndermiyor. VM'in açık olduğunu ve "
               "uygulama kapsayıcılarının çalıştığını kontrol edin; kurulum sonrasıysa işletim ekibine haber verin."},
]
RING_BY_ID = {r["id"]: r for r in RINGS}
STALE_RINGS = ("logo", "crm")
STALE_RECIPE = ("Okunan veritabanındaki son kayıt eski. Bağlantı çalışıyor ama veri gelmiyor: okunan veritabanı canlı "
                "sistemin donmuş bir kopyası olabilir. Raporlar bu tarihe kadar doğrudur; canlı veritabanına okuma "
                "erişimi için BT ile görüşün.")

#: Ekrana ve e-postaya giden metinde geçmeyecek teknoloji adları → sade karşılığı. İç günlükte ham metin kalır.
_TECH = [
    (re.compile(r"\bsystemd\b|\bsystemctl\b", re.I), "servis yöneticisi"),
    (re.compile(r"\bdocker\b|\bcontainerd?\b", re.I), "kapsayıcı"),
    (re.compile(r"\bnginx\b", re.I), "web sunucusu"),
    (re.compile(r"\bv?llm\b|\bvllm\b|\bqwen[\w.-]*|\bopenai\b", re.I), "Zeki AI modeli"),
    (re.compile(r"\bopenvpn\b|\bsocat\b", re.I), "şirket ağı bağlantısı"),
    (re.compile(r"\bpy?odbc\b|\bfreetds\b|\bpymssql\b|\bsqlalchemy\b|\bpsycopg2?\b", re.I), "veritabanı sürücüsü"),
    (re.compile(r"\bldap3?\b", re.I), "dizin"),
    (re.compile(r"\bsmtplib\b", re.I), "posta"),
]

SOURCES = ("timer", "manual", "watchdog")
ENVS = ("test", "vm", "gpu")

_ready: set[int] = set()
_lock = threading.Lock()
#: Denetim turları tek sıradan geçer: zamanlayıcı ile «Şimdi dene» aynı olayı iki kez açıp iki kez bildirmesin.
run_lock = threading.Lock()
_LOCAL = timezone(timedelta(hours=3))


class ItOpsError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ yardımcılar


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v)
        except ValueError:
            return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    v = _aware(v)
    return v.isoformat() if v else None


def screen_text(s: Any) -> str:
    """Hata/denetim metnini ekrana uygun kılar: teknoloji adları sade karşılığıyla, boşluklar tek."""
    t = " ".join(str(s or "").split())
    for rx, rep in _TECH:
        t = rx.sub(rep, t)
    return t[:600]


def _minutes(a: Optional[datetime], b: Optional[datetime]) -> Optional[int]:
    a, b = _aware(a), _aware(b)
    if not a or not b:
        return None
    return max(0, int((b - a).total_seconds() // 60))


def human_minutes(m: Optional[int]) -> str:
    if m is None:
        return "—"
    if m < 60:
        return f"{m} dk"
    h, mm = divmod(m, 60)
    if h < 48:
        return f"{h} sa {mm} dk" if mm else f"{h} sa"
    d, hh = divmod(h, 24)
    return f"{d} gün {hh} sa" if hh else f"{d} gün"


def local_str(v: Optional[datetime]) -> str:
    v = _aware(v)
    return v.astimezone(_LOCAL).strftime("%d.%m.%Y %H:%M") if v else "—"


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def settings(conf: Callable[[str, str], str]) -> dict[str, Any]:
    """Eşikler: ekran (admin.conf) > ortam > varsayılan."""
    def num(key: str, default: int) -> int:
        try:
            return max(0, int(str(conf(key, str(default)) or default)))
        except ValueError:
            return default
    return {
        "everySec": num("ITOPS_CHECK_EVERY_SEC", 300),
        "failsToOpen": max(1, num("ITOPS_FAILS_TO_OPEN", 2)),
        "logoStaleDays": num("ITOPS_LOGO_STALE_DAYS", 3),
        "crmStaleHours": num("ITOPS_CRM_STALE_HOURS", 24),
        "remindHours": num("ALERT_REMIND_HOURS", 24),
        "staleRemindHours": num("ITOPS_STALE_REMIND_HOURS", 24),
        "weeklyDay": min(7, max(1, num("ITOPS_WEEKLY_DAY", 1))),
        "reportHour": min(23, num("ITOPS_REPORT_HOUR", 8)),
    }


# ------------------------------------------------------------------ alıcılar (yalnız iç)


def split_addresses(raw: str) -> list[str]:
    return [x for x in dict.fromkeys(p.strip() for p in re.split(r"[,;\s]+", raw or "")) if x]


def internal_recipients(raw: str, domains_raw: str) -> tuple[list[str], list[str]]:
    """(gönderilecek, reddedilen). Alan adı listesi boşsa kimseye gönderilmez: dışarıya sızma yolu açık kalmasın."""
    domains = {d.strip().lower().lstrip("@") for d in (domains_raw or "").split(",") if d.strip()}
    ok, bad = [], []
    for a in split_addresses(raw):
        dom = a.rsplit("@", 1)[1].lower() if a.count("@") == 1 else ""
        (ok if dom and dom in domains and "." in dom else bad).append(a)
    return ok, bad


# ------------------------------------------------------------------ denetim kaydı ve olay mantığı


def record_check(engine: sa.engine.Engine, tenant: str, ring: str, ok: Optional[bool], *, latency_ms: Optional[int] = None,
                 data_end: Optional[datetime] = None, detail: str = "", source: str = "timer",
                 at: Optional[datetime] = None) -> int:
    if ring not in RING_BY_ID:
        raise ItOpsError(f"Bilinmeyen halka: {ring}")
    if source not in SOURCES:
        source = "timer"
    with engine.begin() as c:
        res = c.execute(CHECKS.insert().values(
            tenant_id=tenant, ring=ring, at=at or _now(), ok=ok, latency_ms=latency_ms, data_end=_aware(data_end),
            detail=screen_text(detail), source=source))
        return int(res.inserted_primary_key[0])


def _open_incident(c, tenant: str, ring: str, kind: str) -> Optional[Any]:
    return c.execute(sa.select(INCIDENTS).where(
        INCIDENTS.c.tenant_id == tenant, INCIDENTS.c.ring == ring, INCIDENTS.c.kind == kind,
        INCIDENTS.c.closed_at.is_(None)).order_by(INCIDENTS.c.opened_at.desc())).mappings().first()


def _recent_measured(c, tenant: str, ring: str, n: int) -> list[Any]:
    """Halkanın son n ölçümü (ok None olanlar sayılmaz: «uygulanmaz» bir kopma da düzelme de değildir)."""
    return c.execute(sa.select(CHECKS.c.ok, CHECKS.c.at, CHECKS.c.detail).where(
        CHECKS.c.tenant_id == tenant, CHECKS.c.ring == ring, CHECKS.c.ok.isnot(None))
        .order_by(CHECKS.c.at.desc(), CHECKS.c.id.desc()).limit(n)).mappings().all()


def stale_limit(ring: str, st: dict[str, Any]) -> Optional[timedelta]:
    if ring == "logo":
        return timedelta(days=st["logoStaleDays"]) if st["logoStaleDays"] else None
    if ring == "crm":
        return timedelta(hours=st["crmStaleHours"]) if st["crmStaleHours"] else None
    return None


def evaluate(engine: sa.engine.Engine, tenant: str, results: Iterable[dict[str, Any]], st: dict[str, Any], *,
             now: Optional[datetime] = None) -> dict[str, list[str]]:
    """Bu turun denetim sonuçlarından olay aç/kapat. `results` zaten `record_check` ile yazılmış satırlardır
    (ring, ok, data_end, detail). Dönen: açılan ve kapanan olay kimlikleri."""
    now = now or _now()
    opened: list[str] = []
    closed: list[str] = []
    with engine.begin() as c:
        for r in results:
            ring, ok = r["ring"], r.get("ok")
            # --- kopma
            if ok is not None:
                cur = _open_incident(c, tenant, ring, "kopma")
                if ok and cur:
                    c.execute(INCIDENTS.update().where(INCIDENTS.c.id == cur["id"]).values(closed_at=now))
                    closed.append(cur["id"])
                elif not ok:
                    recent = _recent_measured(c, tenant, ring, st["failsToOpen"])
                    all_failed = len(recent) >= st["failsToOpen"] and all(x["ok"] is False for x in recent)
                    if cur:
                        c.execute(INCIDENTS.update().where(INCIDENTS.c.id == cur["id"]).values(last_error=screen_text(r.get("detail"))))
                    elif all_failed:
                        first = recent[-1]
                        iid = uuid.uuid4().hex
                        c.execute(INCIDENTS.insert().values(
                            id=iid, tenant_id=tenant, ring=ring, kind="kopma", opened_at=_aware(first["at"]) or now,
                            first_error=first["detail"], last_error=screen_text(r.get("detail")), false_alarm=False,
                            postmortem_status="yok"))
                        opened.append(iid)
            # --- tazelik (yalnız ölçülebildiyse: bağlantı yoksa veri sonu bilinmez, eski kararı değiştirmeyiz)
            limit = stale_limit(ring, st) if ring in STALE_RINGS else None
            end = _aware(r.get("data_end"))
            if limit is not None and ok and end is not None:
                cur = _open_incident(c, tenant, ring, "tazelik")
                stale = now - end > limit
                msg = f"{RING_BY_ID[ring]['label']} veri sonu {local_str(end)} ({human_minutes(_minutes(end, now))} önce)"
                if stale and not cur:
                    iid = uuid.uuid4().hex
                    c.execute(INCIDENTS.insert().values(
                        id=iid, tenant_id=tenant, ring=ring, kind="tazelik", opened_at=now, first_error=msg,
                        last_error=msg, false_alarm=False, postmortem_status="yok"))
                    opened.append(iid)
                elif stale and cur:
                    c.execute(INCIDENTS.update().where(INCIDENTS.c.id == cur["id"]).values(last_error=msg))
                elif not stale and cur:
                    c.execute(INCIDENTS.update().where(INCIDENTS.c.id == cur["id"]).values(closed_at=now, last_error=msg))
                    closed.append(cur["id"])
    return {"opened": opened, "closed": closed}


# ------------------------------------------------------------------ bildirim


Sender = Callable[[str, str, list[str]], str]


def _incident_line(row: Any, now: datetime) -> str:
    ring = RING_BY_ID.get(row["ring"], {"label": row["ring"]})
    if row["kind"] == "tazelik":
        return f"- {ring['label']}: veri eski. {row['last_error'] or ''}"
    dur = human_minutes(_minutes(row["opened_at"], row["closed_at"] or now))
    return f"- {ring['label']}: {dur}'dır yok. Son hata: {row['last_error'] or row['first_error'] or '—'}"


def notify(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], send: Sender, recipients: list[str], *,
           link: str = "", now: Optional[datetime] = None) -> dict[str, Any]:
    """Bekleyen bildirimleri tek e-postada gönderir: yeni açılan (ya da açılışı gönderilememiş), düzelen, hatırlatması
    gelen olaylar. Sonuç her olayın satırına yazılır; gönderilemeyen sonraki turda yeniden denenir."""
    now = now or _now()
    with engine.connect() as c:
        rows = c.execute(sa.select(INCIDENTS).where(INCIDENTS.c.tenant_id == tenant, sa.or_(
            INCIDENTS.c.closed_at.is_(None),
            sa.and_(INCIDENTS.c.closed_at.isnot(None), INCIDENTS.c.closed_notify.is_(None))))).mappings().all()
    new, remind, fixed, skip = [], [], [], []
    for r in rows:
        if r["closed_at"] is not None:
            (fixed if r["notify_status"] == "sent" else skip).append(r)
            continue
        if r["notify_status"] != "sent":
            new.append(r)
            continue
        hours = st["staleRemindHours"] if r["kind"] == "tazelik" else st["remindHours"]
        last = _aware(r["reminded_at"]) or _aware(r["notified_at"])
        if hours and last is not None and now - last >= timedelta(hours=hours):
            remind.append(r)
    if skip:
        with engine.begin() as c:
            c.execute(INCIDENTS.update().where(INCIDENTS.c.id.in_([r["id"] for r in skip])).values(closed_notify="skip"))
    if not (new or remind or fixed):
        return {"sent": None, "new": 0, "remind": 0, "fixed": 0}

    parts: list[str] = []
    labels = []
    if new:
        parts += ["Yeni sorun:"] + [_incident_line(r, now) for r in new]
        for r in new:
            ring = RING_BY_ID.get(r["ring"], {"recipe": ""})
            parts.append(f"  Ne yapmalı: {STALE_RECIPE if r['kind'] == 'tazelik' else ring.get('recipe', '')}")
        labels += [RING_BY_ID.get(r["ring"], {"label": r["ring"]})["label"] + (" verisi eski" if r["kind"] == "tazelik" else " koptu") for r in new]
    if fixed:
        parts += ["", "Düzeldi:"] + [
            f"- {RING_BY_ID.get(r['ring'], {'label': r['ring']})['label']}: düzeldi, "
            f"{human_minutes(_minutes(r['opened_at'], r['closed_at']))} sürdü." for r in fixed]
        labels += [RING_BY_ID.get(r["ring"], {"label": r["ring"]})["label"] + " düzeldi" for r in fixed]
    if remind:
        parts += ["", "Sürüyor (hatırlatma):"] + [_incident_line(r, now) for r in remind]
        if not labels:
            labels = ["sürüyor: " + ", ".join(RING_BY_ID.get(r["ring"], {"label": r["ring"]})["label"] for r in remind)]
    parts += ["", f"Denetim zamanı: {local_str(now)}"]
    if link:
        parts += [f"Ayrıntı: {link.rstrip('/')}/sistem-durumu"]
    subject = "ZEKİ sistem durumu: " + ", ".join(labels)
    result = send(subject[:200], "\n".join(parts), recipients) if recipients else "no_recipient"
    with engine.begin() as c:
        for r in new:
            vals: dict[str, Any] = {"notify_status": result}
            if result == "sent":
                vals["notified_at"] = now
            c.execute(INCIDENTS.update().where(INCIDENTS.c.id == r["id"]).values(**vals))
        if result == "sent":
            for r in remind:
                c.execute(INCIDENTS.update().where(INCIDENTS.c.id == r["id"]).values(reminded_at=now))
        for r in fixed:
            if result == "sent":
                c.execute(INCIDENTS.update().where(INCIDENTS.c.id == r["id"]).values(closed_notify="sent"))
    return {"sent": result, "new": len(new), "remind": len(remind), "fixed": len(fixed)}


# ------------------------------------------------------------------ özetler (haftalık, günlük iş hataları)


def state_get(engine: sa.engine.Engine, tenant: str, key: str) -> Optional[str]:
    with engine.connect() as c:
        return c.execute(sa.select(STATE.c.value).where(STATE.c.tenant_id == tenant, STATE.c.key == key)).scalar()


def state_set(engine: sa.engine.Engine, tenant: str, key: str, value: str) -> None:
    with engine.begin() as c:
        n = c.execute(STATE.update().where(STATE.c.tenant_id == tenant, STATE.c.key == key)
                      .values(value=value, updated_at=_now())).rowcount
        if not n:
            c.execute(STATE.insert().values(tenant_id=tenant, key=key, value=value, updated_at=_now()))


def downtime(engine: sa.engine.Engine, tenant: str, since: datetime, until: Optional[datetime] = None) -> dict[str, dict[str, Any]]:
    """Halka başına kopma sayısı ve pencere içine düşen kesinti dakikası (tazelik olayları sayılmaz, «gerçek değil»
    işaretliler de). Açık olay `until`'e kadar sayılır."""
    until = until or _now()
    since = _aware(since)
    with engine.connect() as c:
        rows = c.execute(sa.select(INCIDENTS).where(
            INCIDENTS.c.tenant_id == tenant, INCIDENTS.c.kind == "kopma", INCIDENTS.c.false_alarm.is_(False),
            INCIDENTS.c.opened_at < until,
            sa.or_(INCIDENTS.c.closed_at.is_(None), INCIDENTS.c.closed_at > since))).mappings().all()
    out: dict[str, dict[str, Any]] = {r["id"]: {"count": 0, "minutes": 0} for r in RINGS}
    for r in rows:
        a = max(_aware(r["opened_at"]), since)
        b = min(_aware(r["closed_at"]) or until, until)
        d = out.setdefault(r["ring"], {"count": 0, "minutes": 0})
        d["count"] += 1
        d["minutes"] += max(0, int((b - a).total_seconds() // 60))
    return out


def weekly_text(engine: sa.engine.Engine, tenant: str, now: datetime, failing_jobs: list[dict[str, Any]]) -> tuple[str, str]:
    since = now - timedelta(days=7)
    dt = downtime(engine, tenant, since, now)
    total = sum(v["minutes"] for v in dt.values())
    worst = max(dt.items(), key=lambda kv: kv[1]["minutes"]) if dt else None
    with engine.connect() as c:
        still = c.execute(sa.select(INCIDENTS).where(INCIDENTS.c.tenant_id == tenant, INCIDENTS.c.closed_at.is_(None))).mappings().all()
    lines = [f"Son 7 gün ({local_str(since)} – {local_str(now)})", ""]
    for r in RINGS:
        v = dt.get(r["id"], {"count": 0, "minutes": 0})
        lines.append(f"- {r['label']}: {v['count']} kopma, toplam {human_minutes(v['minutes'])}")
    lines += ["", f"Toplam kesinti: {human_minutes(total)}"]
    if worst and worst[1]["minutes"]:
        lines.append(f"En çok bozulan: {RING_BY_ID.get(worst[0], {'label': worst[0]})['label']}")
    if still:
        lines += ["", "Şu an açık:"] + [_incident_line(r, now) for r in still]
    if failing_jobs:
        lines += ["", "Hatalı zamanlanmış işler:"] + [f"- {j['label']}: {j.get('lastError') or 'başarısız'}" for j in failing_jobs]
    return "ZEKİ haftalık sistem özeti", "\n".join(lines)


def jobs_digest_text(failing: list[dict[str, Any]], now: datetime) -> tuple[str, str]:
    lines = [f"Son 24 saatte hata veren zamanlanmış işler ({local_str(now)}):", ""]
    lines += [f"- {j['label']}: {j.get('lastError') or 'başarısız'} (son koşu {local_str(_aware(j.get('lastAt')))})" for j in failing]
    return f"ZEKİ zamanlanmış iş hataları: {len(failing)} iş", "\n".join(lines)


def due_digests(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], now: datetime) -> dict[str, Optional[str]]:
    """Haftalık özet (seçili gün, saatten sonra, ISO haftada bir) ve günlük iş hatası özeti (saatten sonra, günde bir)
    zamanı geldiyse anahtarlarını döndürür."""
    loc = now.astimezone(_LOCAL)
    out: dict[str, Optional[str]] = {"weekly": None, "daily": None}
    if loc.hour >= st["reportHour"]:
        wk = f"{loc.isocalendar()[0]}-W{loc.isocalendar()[1]:02d}"
        if loc.isoweekday() == st["weeklyDay"] and state_get(engine, tenant, "weekly_sent") != wk:
            out["weekly"] = wk
        day = loc.date().isoformat()
        if state_get(engine, tenant, "daily_sent") != day:
            out["daily"] = day
    return out


# ------------------------------------------------------------------ işler


def upsert_job(engine: sa.engine.Engine, tenant: str, job: str, *, label: str, source: str, every: Optional[str] = None,
               last_at: Optional[datetime] = None, next_at: Optional[datetime] = None, last_ok: Optional[bool] = None,
               last_error: Optional[str] = None, failed_count: Optional[int] = None, total_count: Optional[int] = None) -> None:
    vals = {"label": label[:200], "every": every, "last_at": _aware(last_at), "next_at": _aware(next_at), "last_ok": last_ok,
            "last_error": screen_text(last_error) if last_error else None, "failed_count": failed_count,
            "total_count": total_count, "source": source[:16], "updated_at": _now()}
    with engine.begin() as c:
        n = c.execute(JOBS.update().where(JOBS.c.tenant_id == tenant, JOBS.c.job == job[:120]).values(**vals)).rowcount
        if not n:
            c.execute(JOBS.insert().values(tenant_id=tenant, job=job[:120], **vals))


def job_view(r: Any) -> dict[str, Any]:
    return {"job": r["job"], "label": r["label"], "every": r["every"], "lastAt": _iso(r["last_at"]), "nextAt": _iso(r["next_at"]),
            "lastOk": r["last_ok"], "lastError": r["last_error"], "failedCount": r["failed_count"],
            "totalCount": r["total_count"], "source": r["source"], "updatedAt": _iso(r["updated_at"])}


def list_jobs(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(JOBS).where(JOBS.c.tenant_id == tenant)).mappings().all()
    items = [job_view(r) for r in rows]
    # Hatalı önce, sonra ada göre.
    items.sort(key=lambda j: (j["lastOk"] is not False, j["lastOk"] is None, j["label"].lower()))
    return items


def failing_jobs(engine: sa.engine.Engine, tenant: str, since: Optional[datetime] = None) -> list[dict[str, Any]]:
    out = []
    for j in list_jobs(engine, tenant):
        if j["lastOk"] is False and (since is None or (_aware(j["lastAt"]) or _aware(j["updatedAt"]) or _now()) >= since):
            out.append(j)
    return out


# ------------------------------------------------------------------ sürüm kaydı


def record_release(engine: sa.engine.Engine, tenant: str, body: dict[str, Any], *, by: str = "kurulum") -> dict[str, Any]:
    env = str(body.get("env") or "").strip().lower()
    if env not in ENVS:
        raise ItOpsError(f"Ortam {', '.join(ENVS)} olmalı.")
    sha = str(body.get("codeSha") or body.get("code_sha") or "").strip()[:64]
    if sha and not re.fullmatch(r"[0-9a-fA-F]{7,64}|bilinmiyor", sha):
        raise ItOpsError("Kod sürümü bir git kimliği (sha) olmalı.")
    try:
        ad = body.get("appledoubleCount", body.get("appledouble_count"))
        ad = None if ad is None or ad == "" else int(ad)
    except (TypeError, ValueError):
        raise ItOpsError("Mac artığı sayısı tam sayı olmalı.") from None
    row = {"tenant_id": tenant, "env": env, "at": _now(), "code_sha": sha or None,
           "image": (str(body.get("image") or "").strip()[:300] or None), "appledouble_count": ad,
           "reported_by": str(body.get("reportedBy") or by)[:120], "note": (str(body.get("note") or "")[:2000] or None)}
    with engine.begin() as c:
        rid = c.execute(RELEASES.insert().values(**row)).inserted_primary_key[0]
    return release_view({**row, "id": rid})


def release_view(r: Any) -> dict[str, Any]:
    return {"id": r["id"], "env": r["env"], "at": _iso(r["at"]), "codeSha": r["code_sha"], "image": r["image"],
            "appledoubleCount": r["appledouble_count"], "reportedBy": r["reported_by"], "note": r["note"]}


def list_releases(engine: sa.engine.Engine, tenant: str, *, before: Optional[int] = None, size: int = 50) -> dict[str, Any]:
    q = sa.select(RELEASES).where(RELEASES.c.tenant_id == tenant)
    if before:
        q = q.where(RELEASES.c.id < before)
    size = max(1, min(int(size or 50), 500))
    with engine.connect() as c:
        rows = c.execute(q.order_by(RELEASES.c.id.desc()).limit(size + 1)).mappings().all()
        latest = {}
        for env in ENVS:
            r = c.execute(sa.select(RELEASES).where(RELEASES.c.tenant_id == tenant, RELEASES.c.env == env)
                          .order_by(RELEASES.c.id.desc()).limit(1)).mappings().first()
            if r:
                latest[env] = release_view(r)
    items = [release_view(r) for r in rows[:size]]
    t, v = latest.get("test"), latest.get("vm")
    parity = None
    if t and v and t["codeSha"] and v["codeSha"]:
        parity = t["codeSha"][:12] == v["codeSha"][:12]
    return {"items": items, "next": items[-1]["id"] if len(rows) > size else None, "latest": latest, "parity": parity}


# ------------------------------------------------------------------ olaylar


def incident_view(r: Any, now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or _now()
    ring = RING_BY_ID.get(r["ring"], {"label": r["ring"], "recipe": ""})
    return {
        "id": r["id"], "ring": r["ring"], "ringLabel": ring["label"], "kind": r["kind"],
        "kindLabel": "Veri eski" if r["kind"] == "tazelik" else "Bağlantı koptu",
        "openedAt": _iso(r["opened_at"]), "closedAt": _iso(r["closed_at"]), "open": r["closed_at"] is None,
        "minutes": _minutes(r["opened_at"], r["closed_at"] or now), "firstError": r["first_error"], "lastError": r["last_error"],
        "notifiedAt": _iso(r["notified_at"]), "notifyStatus": r["notify_status"], "remindedAt": _iso(r["reminded_at"]),
        "closedNotify": r["closed_notify"], "rootCause": r["root_cause"], "rootCauseBy": r["root_cause_by"],
        "rootCauseAt": _iso(r["root_cause_at"]), "falseAlarm": bool(r["false_alarm"]),
        "postmortemDraft": r["postmortem_draft"], "postmortemStatus": r["postmortem_status"] or "yok",
        "postmortemBy": r["postmortem_by"], "postmortemAt": _iso(r["postmortem_at"]),
        "recipe": STALE_RECIPE if r["kind"] == "tazelik" else ring.get("recipe", ""),
    }


def list_incidents(engine: sa.engine.Engine, tenant: str, *, state: str = "open", ring: Optional[str] = None,
                   before: Optional[str] = None, size: int = 50) -> dict[str, Any]:
    q = sa.select(INCIDENTS).where(INCIDENTS.c.tenant_id == tenant)
    if state == "open":
        q = q.where(INCIDENTS.c.closed_at.is_(None))
    elif state == "closed":
        q = q.where(INCIDENTS.c.closed_at.isnot(None))
    if ring:
        q = q.where(INCIDENTS.c.ring == ring)
    size = max(1, min(int(size or 50), 500))
    with engine.connect() as c:
        if before:
            ref = c.execute(sa.select(INCIDENTS.c.opened_at).where(INCIDENTS.c.id == before)).scalar()
            if ref is not None:
                q = q.where(sa.or_(INCIDENTS.c.opened_at < ref, sa.and_(INCIDENTS.c.opened_at == ref, INCIDENTS.c.id < before)))
        rows = c.execute(q.order_by(INCIDENTS.c.opened_at.desc(), INCIDENTS.c.id.desc()).limit(size + 1)).mappings().all()
    now = _now()
    items = [incident_view(r, now) for r in rows[:size]]
    return {"items": items, "next": items[-1]["id"] if len(rows) > size else None}


def get_incident(engine: sa.engine.Engine, tenant: str, iid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(INCIDENTS).where(INCIDENTS.c.tenant_id == tenant, INCIDENTS.c.id == iid)).mappings().first()
        if not r:
            raise ItOpsError("Olay bulunamadı.", 404)
        until = _aware(r["closed_at"]) or _now()
        checks = c.execute(sa.select(CHECKS).where(
            CHECKS.c.tenant_id == tenant, CHECKS.c.ring == r["ring"],
            CHECKS.c.at >= _aware(r["opened_at"]) - timedelta(minutes=30), CHECKS.c.at <= until + timedelta(minutes=30))
            .order_by(CHECKS.c.at.asc(), CHECKS.c.id.asc())).mappings().all()
    return {**incident_view(r), "timeline": [check_view(x) for x in checks]}


def update_incident(engine: sa.engine.Engine, tenant: str, iid: str, body: dict[str, Any], user: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Kök neden notu, «gerçek değil» işareti, olay değerlendirmesi taslağının düzeltilmesi ve yayımı. Dönen: (olay, fark)."""
    with engine.connect() as c:
        r = c.execute(sa.select(INCIDENTS).where(INCIDENTS.c.tenant_id == tenant, INCIDENTS.c.id == iid)).mappings().first()
    if not r:
        raise ItOpsError("Olay bulunamadı.", 404)
    vals: dict[str, Any] = {}
    now = _now()
    if "rootCause" in body:
        text = str(body.get("rootCause") or "").strip()[:4000]
        vals.update(root_cause=text or None, root_cause_by=user if text else None, root_cause_at=now if text else None)
    if "falseAlarm" in body:
        vals["false_alarm"] = bool(body.get("falseAlarm"))
    if "postmortem" in body:
        text = str(body.get("postmortem") or "").strip()[:20000]
        vals.update(postmortem_draft=text or None, postmortem_status="taslak" if text else "yok")
    if body.get("publish"):
        draft = vals.get("postmortem_draft", r["postmortem_draft"])
        if not draft:
            raise ItOpsError("Yayımlanacak bir değerlendirme metni yok.")
        if r["closed_at"] is None:
            raise ItOpsError("Açık olayın değerlendirmesi yayımlanmaz; önce olay kapanmalı.")
        vals.update(postmortem_status="yayında", postmortem_by=user, postmortem_at=now)
    if not vals:
        raise ItOpsError("Değiştirilecek alan yok.")
    before = {"rootCause": r["root_cause"], "falseAlarm": bool(r["false_alarm"]), "postmortemStatus": r["postmortem_status"]}
    with engine.begin() as c:
        c.execute(INCIDENTS.update().where(INCIDENTS.c.id == iid).values(**vals))
    out = get_incident(engine, tenant, iid)
    after = {"rootCause": out["rootCause"], "falseAlarm": out["falseAlarm"], "postmortemStatus": out["postmortemStatus"]}
    diff = {k: {"from": before[k], "to": after[k]} for k in before if before[k] != after[k]}
    return out, diff


def save_draft(engine: sa.engine.Engine, tenant: str, iid: str, text: str) -> dict[str, Any]:
    with engine.begin() as c:
        n = c.execute(INCIDENTS.update().where(INCIDENTS.c.tenant_id == tenant, INCIDENTS.c.id == iid).values(
            postmortem_draft=text.strip()[:20000], postmortem_status="taslak")).rowcount
    if not n:
        raise ItOpsError("Olay bulunamadı.", 404)
    return get_incident(engine, tenant, iid)


def draft_prompt(inc: dict[str, Any]) -> list[dict[str, str]]:
    """Olay değerlendirmesi taslağı için mesaj. Sayılar olay tablosundan gelir; modelden yeni rakam istenmez."""
    tl = inc.get("timeline") or []
    fails = sum(1 for x in tl if x["ok"] is False)
    facts = [
        f"Halka: {inc['ringLabel']}", f"Tür: {inc['kindLabel']}",
        f"Başlangıç: {local_str(_aware(inc['openedAt']))}", f"Bitiş: {local_str(_aware(inc['closedAt'])) if inc['closedAt'] else 'sürüyor'}",
        f"Süre: {human_minutes(inc['minutes'])}", f"Başarısız deneme sayısı: {fails}",
        f"İlk hata: {inc['firstError'] or '—'}", f"Son hata: {inc['lastError'] or '—'}",
        f"BT'nin kök neden notu: {inc['rootCause'] or 'yok'}",
    ]
    system = ("Sen bir BT olay değerlendirmesi taslağı yazıyorsun. Yalnız verilen olguları kullan; yeni sayı, tarih ya da "
              "süre uydurma. Türkçe, sade, en çok 12 satır. Başlıklar: Ne oldu, Etki, Süre, Olası neden, Önerilen önlem. "
              "Kök neden notu yoksa «olası neden» için yalnız hata metninden çıkarılabileni yaz ve belirsiz olduğunu söyle.")
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(facts)}]


# ------------------------------------------------------------------ denetim listesi ve durum


def check_view(r: Any) -> dict[str, Any]:
    return {"id": r["id"], "ring": r["ring"], "at": _iso(r["at"]), "ok": r["ok"], "latencyMs": r["latency_ms"],
            "dataEnd": _iso(r["data_end"]), "detail": r["detail"], "source": r["source"]}


def list_checks(engine: sa.engine.Engine, tenant: str, *, ring: Optional[str] = None, since: Optional[datetime] = None,
                before: Optional[int] = None, size: int = 100) -> dict[str, Any]:
    q = sa.select(CHECKS).where(CHECKS.c.tenant_id == tenant)
    if ring:
        q = q.where(CHECKS.c.ring == ring)
    if since:
        q = q.where(CHECKS.c.at >= _aware(since))
    if before:
        q = q.where(CHECKS.c.id < before)
    size = max(1, min(int(size or 100), 1000))
    with engine.connect() as c:
        rows = c.execute(q.order_by(CHECKS.c.id.desc()).limit(size + 1)).mappings().all()
    items = [check_view(r) for r in rows[:size]]
    return {"items": items, "next": items[-1]["id"] if len(rows) > size else None}


def _age_text(end: Optional[datetime], now: datetime) -> str:
    if not end:
        return ""
    m = _minutes(end, now) or 0
    if m < 60 * 24:
        return f"{human_minutes(m)} önce"
    return f"{m // (60 * 24)} gün önce"


def status(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], *, now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or _now()
    rings = []
    with engine.connect() as c:
        open_rows = c.execute(sa.select(INCIDENTS).where(INCIDENTS.c.tenant_id == tenant, INCIDENTS.c.closed_at.is_(None))
                              .order_by(INCIDENTS.c.opened_at.asc())).mappings().all()
        for r in RINGS:
            last = c.execute(sa.select(CHECKS).where(CHECKS.c.tenant_id == tenant, CHECKS.c.ring == r["id"])
                             .order_by(CHECKS.c.at.desc(), CHECKS.c.id.desc()).limit(1)).mappings().first()
            last_ok = c.execute(sa.select(sa.func.max(CHECKS.c.at)).where(
                CHECKS.c.tenant_id == tenant, CHECKS.c.ring == r["id"], CHECKS.c.ok.is_(True))).scalar()
            end = c.execute(sa.select(CHECKS.c.data_end).where(
                CHECKS.c.tenant_id == tenant, CHECKS.c.ring == r["id"], CHECKS.c.data_end.isnot(None))
                .order_by(CHECKS.c.at.desc(), CHECKS.c.id.desc()).limit(1)).scalar()
            inc = [incident_view(x, now) for x in open_rows if x["ring"] == r["id"]]
            down = next((i for i in inc if i["kind"] == "kopma"), None)
            stale = next((i for i in inc if i["kind"] == "tazelik"), None)
            limit = stale_limit(r["id"], st)
            state = ("unknown" if last is None or last["ok"] is None else "down" if down else "fail" if last["ok"] is False
                     else "stale" if stale else "ok")
            rings.append({**{k: r[k] for k in ("id", "label", "hint", "recipe")}, "state": state,
                          "ok": last["ok"] if last else None, "at": _iso(last["at"]) if last else None,
                          "latencyMs": last["latency_ms"] if last else None, "detail": last["detail"] if last else None,
                          "lastOkAt": _iso(last_ok), "dataEnd": _iso(end), "dataEndAge": _age_text(_aware(end), now),
                          "staleLimitHours": int(limit.total_seconds() // 3600) if limit else None,
                          "incident": down, "stale": stale})
    measured = [x for x in rings if x["state"] != "unknown"]
    downs = sorted((x for x in rings if x["incident"]), key=lambda x: -(x["incident"]["minutes"] or 0))
    fails = [x for x in rings if x["state"] == "fail"]
    stales = [x for x in rings if x["stale"]]
    ends = "; ".join(f"{x['label']} veri sonu {local_str(_aware(x['dataEnd']))}" for x in rings if x["dataEnd"])
    if not measured:
        tone, text = "unknown", "Henüz ölçülmedi. İlk denetim turu bekleniyor."
    elif downs:
        head = downs[0]
        tone = "err"
        text = f"{head['label']} bağlantısı {human_minutes(head['incident']['minutes'])}'dır yok"
        if len(downs) > 1:
            text += f"; {len(downs) - 1} halka daha kopuk"
    elif fails:
        tone, text = "warn", f"{', '.join(x['label'] for x in fails)}: son deneme başarısız (tekrarında olay açılır)"
    elif stales:
        tone = "warn"
        text = "Bağlantılar çalışıyor · " + "; ".join(f"{x['label']} verisi eski ({x['dataEndAge']})" for x in stales)
    else:
        tone, text = "ok", "Her şey çalışıyor" + (f" · {ends}" if ends else "")
    return {"at": _iso(now), "summary": {"tone": tone, "text": text}, "rings": rings,
            "open": [incident_view(x, now) for x in open_rows], "thresholds": st}


def banner(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Herkese giden en küçük bilgi: yalnız kopuk halkanın adı ve ne zamandan beri; ayrıntı yok."""
    with engine.connect() as c:
        rows = c.execute(sa.select(INCIDENTS.c.ring, INCIDENTS.c.opened_at).where(
            INCIDENTS.c.tenant_id == tenant, INCIDENTS.c.kind == "kopma", INCIDENTS.c.closed_at.is_(None),
            INCIDENTS.c.false_alarm.is_(False)).order_by(INCIDENTS.c.opened_at.asc())).all()
    return {"items": [{"ring": r[0], "label": RING_BY_ID.get(r[0], {"label": r[0]})["label"], "since": _iso(r[1])} for r in rows]}


def audit_detail(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)[:4000]
