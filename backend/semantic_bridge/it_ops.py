"""M48 IT altyapı ve sistem yönetimi: halka denetimleri, olaylar, zamanlanmış işler, sürüm kaydı.

ZEKİ'yi ayakta tutan yedi halka (Logo, CRM, giriş, Zeki AI modeli, e-posta, şirket ağı bağlantısı, müşteri VM'i)
5 dk'da bir denenir (`it_ops_sources.run_rings`, mevcut `admin.run_check` denemelerini çağırır); her sonuç
`semantic_itops_checks`'e yazılır. **Kopma olayı** yalnız gerçek ve süren kesintide açılır: art arda en az
`ITOPS_FAILS_TO_OPEN` (2) başarısız deneme VE ilk başarısız denemeden bu yana en az `ITOPS_OUTAGE_MIN` (10) dk. Köprünün
kendi açılış kaydının (`note_boot`, `semantic_itops_state.bridge_boots`) ±`ITOPS_RESTART_GRACE_MIN` (5) dk'sına düşen
başarısız deneme sayılmaz: test sunucusunda köprü günde onlarca kez planlı yeniden başlatılır. İlk başarılı deneme olayı
kapatır. Logo ve CRM'in son kayıt tarihi («veri sonu») eşiği aşarsa ayrı bir **tazelik olayı** açılır — okunan Logo
kopyası donmuşsa (2026-08-17) bağlantı yeşil olsa bile raporlar eskidir.

Bildirim kenarda gider, yalnız iç alıcılara (`ITOPS_RECIPIENTS`, alan adı `ITOPS_INTERNAL_DOMAINS` içinde olmalı), ortak
iç bildirim şablonuyla (`ic_bildirim`: HTML + düz metin): olay açılınca bir kez, düzelince bir kez (süresiyle). Aynı olay
için hatırlatma varsayılanda kapalıdır (`ITOPS_REMIND_HOURS`, tazelikte `ITOPS_STALE_REMIND_HOURS` = 0). Gönderim
olmadıysa sonraki turda yeniden denenir. Aynı turdaki kopmalar tek e-postada, düzelmeler tek e-postada toplanır.

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

from semantic_bridge import ic_bildirim as IB

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
    # Sorgu bilgisi: veri sonunu okuyan SQL (Logo/CRM), değerleri yerinde; ekrandaki «i» bunu gösterir.
    sa.Column("sql_text", sa.Text),
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
    # Kopma kapanırken sağlanan düzelme şartları (JSON): kesintisiz süre, veri okuması, zamanlanmış iş.
    sa.Column("resolve_json", sa.Text),
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
               "sunucusunun açık olduğunu ve okuma hesabının kilitlenmediğini kontrol edin."},
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
#: «Veri eski» olayında BT'nin yapacağı iş (bildirim zaten BT'ye gider: «BT ile görüşün» yazılmaz). Sunucu adı ve adresi
#: yazılmaz, «canlı Logo sunucusu» denir.
STALE_RECIPES: dict[str, str] = {
    "logo": ("Okunan Logo sunucusu canlı sistem değil, donmuş bir kopya: bağlantı çalışıyor ama yeni fatura gelmiyor. "
             "Portalın okuma hesabına canlı Logo sunucusunda okuma yetkisi verin. Ardından portalda Yönetim → Ayarlar → "
             "Logo bağlantısında canlı Logo sunucusunu seçin."),
    "crm": ("Okunan CRM veritabanı canlı sistem değil ya da güncellenmiyor: bağlantı çalışıyor ama kitap kayıtlarında yeni "
            "değişiklik gelmiyor. Portalın okuma hesabına canlı CRM sunucusunda okuma yetkisi verin. Ardından portalda "
            "Yönetim → Ayarlar → CRM bağlantısında canlı CRM sunucusunu seçin."),
}
STALE_RECIPE = STALE_RECIPES["logo"]

#: Ekrana ve e-postaya giden metinde geçmeyecek teknoloji adları → sade karşılığı (ortak liste `ic_bildirim.TECH`).
#: İç günlükte ham metin kalır.
_TECH = IB.TECH

#: E-postada halkanın adı («Logo bağlantısı 09:42'den beri yanıt vermiyor») ve etkisi: hangi ekran/iş etkilenir.
MAIL: dict[str, dict[str, str]] = {
    "logo": {"name": "Logo bağlantısı",
             "impact": "Satış, ciro, stok ve finans ekranları ile Zeki AI'ın rakamlı cevapları Logo'yu okuyamaz; ekranlar son "
                       "okunan veriyi gösterir. Planlı raporlar ve uyarılar bu sürede çalışmaz."},
    "crm": {"name": "CRM bağlantısı",
            "impact": "Kitap kartları, yazar ve müşteri bilgileri, sözleşmeler gibi CRM'den okuyan ekranlar güncellenmez; "
                      "CRM'e bağlı zamanlanmış listeler gitmez."},
    "giris": {"name": "Portal girişi",
              "impact": "Şirket dizinine ulaşılamadığı için kimse portala yeni giriş yapamaz. Açık oturumlar çalışmaya devam eder."},
    "model": {"name": "Zeki AI modeli",
              "impact": "Zeki AI'a sorulan sorular, taslaklar ve özetler bekler. Rakamlar, hazır ekranlar ve raporlar çalışır."},
    "eposta": {"name": "E-posta gönderimi",
               "impact": "Uyarılar, planlı raporlar ve bildirimler gönderilemez; bu e-posta da gecikmiş olabilir. Gönderilemeyenler "
                         "bağlantı gelince yeniden denenir."},
    "vpn": {"name": "Şirket ağı bağlantısı",
            "impact": "Sunucumuz TİMAŞ ağına ulaşamıyor: Logo ve CRM okunamaz, bütün veri ekranları son okunan veriyle kalır."},
    "vm": {"name": "Müşteri sunucusu",
           "impact": "TİMAŞ içindeki portal açılmayabilir ya da oradaki zamanlanmış işler (raporlar, uyarılar) çalışmaz."},
}

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
        def install() -> None:
            _md.create_all(engine, checkfirst=True)
            # create_all var olan tabloya kolon eklemez; veri sonu SQL'i sonradan geldi.
            have = {c["name"] for c in sa.inspect(engine).get_columns(CHECKS.name)}
            if "sql_text" not in have:
                with engine.begin() as c:
                    c.execute(sa.text(f"ALTER TABLE {CHECKS.name} ADD COLUMN sql_text TEXT"))
            if "resolve_json" not in {c["name"] for c in sa.inspect(engine).get_columns(INCIDENTS.name)}:
                with engine.begin() as c:
                    c.execute(sa.text(f"ALTER TABLE {INCIDENTS.name} ADD COLUMN resolve_json TEXT"))

        # Sürüm damgası: tanım değişmediyse açılışta veritabanına sorulmaz (kolon eklenince tanım da değişir).
        from semantic_layer.store import schema_stamp
        schema_stamp.run(engine, _md.sorted_tables, install)
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
        # Gürültü önleme: kesinti en az bu kadar sürmeden olay açılmaz (e-posta da gitmez); köprü açılışının önünde ve
        # arkasındaki bu kadar dakikadaki başarısız deneme sayılmaz (planlı yeniden başlatma).
        "outageMin": num("ITOPS_OUTAGE_MIN", 10),
        "restartGraceMin": num("ITOPS_RESTART_GRACE_MIN", 5),
        # «Düzeldi» ancak gerçek çözümde: bu kadar dk kesintisiz başarılı denetim + veri okuması + (varsa) bağlantıyı
        # kullanan zamanlanmış işin kurtulmadan sonra başarılı koşusu.
        "resolveMin": num("ITOPS_RESOLVE_MIN", 15),
        "logoStaleDays": num("ITOPS_LOGO_STALE_DAYS", 3),
        "crmStaleHours": num("ITOPS_CRM_STALE_HOURS", 24),
        # 0: aynı olay için ikinci e-posta yok (düzelince tek «Düzeldi» gider).
        "remindHours": num("ITOPS_REMIND_HOURS", 0),
        "staleRemindHours": num("ITOPS_STALE_REMIND_HOURS", 0),
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
                 at: Optional[datetime] = None, sql_text: Optional[str] = None) -> int:
    if ring not in RING_BY_ID:
        raise ItOpsError(f"Bilinmeyen halka: {ring}")
    if source not in SOURCES:
        source = "timer"
    with engine.begin() as c:
        res = c.execute(CHECKS.insert().values(
            tenant_id=tenant, ring=ring, at=at or _now(), ok=ok, latency_ms=latency_ms, data_end=_aware(data_end),
            detail=screen_text(detail), source=source, sql_text=sql_text))
        return int(res.inserted_primary_key[0])


def _open_incident(c, tenant: str, ring: str, kind: str) -> Optional[Any]:
    return c.execute(sa.select(INCIDENTS).where(
        INCIDENTS.c.tenant_id == tenant, INCIDENTS.c.ring == ring, INCIDENTS.c.kind == kind,
        INCIDENTS.c.closed_at.is_(None)).order_by(INCIDENTS.c.opened_at.desc())).mappings().first()


def in_restart_window(at: Optional[datetime], boots: Iterable[datetime], grace_min: int) -> bool:
    """Deneme bir köprü açılışının ±grace dakikası içinde mi (planlı yeniden başlatma: durma ve açılış anı)."""
    at = _aware(at)
    if at is None or not grace_min:
        return False
    g = timedelta(minutes=grace_min)
    return any(b - g <= at <= b + g for b in boots)


def _fail_streak(c, tenant: str, ring: str, boots: list[datetime], grace_min: int) -> list[Any]:
    """Son başarılı denemeden bu yana süren başarısız denemeler, eskiden yeniye. «Uygulanmaz» (ok None) ölçümler ve
    yeniden başlatma penceresine düşenler sayılmaz: ikisi de kopma değildir."""
    last_ok = c.execute(sa.select(sa.func.max(CHECKS.c.at)).where(
        CHECKS.c.tenant_id == tenant, CHECKS.c.ring == ring, CHECKS.c.ok.is_(True))).scalar()
    q = sa.select(CHECKS.c.ok, CHECKS.c.at, CHECKS.c.detail).where(
        CHECKS.c.tenant_id == tenant, CHECKS.c.ring == ring, CHECKS.c.ok.is_(False))
    if last_ok is not None:
        q = q.where(CHECKS.c.at > last_ok)
    rows = c.execute(q.order_by(CHECKS.c.at.asc(), CHECKS.c.id.asc())).mappings().all()
    return [r for r in rows if not in_restart_window(r["at"], boots, grace_min)]


# ------------------------------------------------------------------ düzelme şartları («gerçekten çözüldü mü»)

#: Halkanın kendi okuması: kopma kapanırken bunun başarılı olduğu söylenir (veri sorgusu olan halkada satır dönmüş olmalı).
DATA_READ = {
    "logo": "Logo'dan son fatura tarihi okundu",
    "crm": "CRM'den son kitap kaydı değişikliği okundu",
    "giris": "Şirket dizininde servis hesabıyla oturum açıldı",
    "model": "Zeki AI modeli deneme sorusuna cevap verdi",
    "eposta": "Posta sunucusunda oturum açıldı",
    "vpn": "Şirket ağındaki sunucuya ulaşıldı",
    "vm": "Müşteri sunucusu yanıt verdi",
}

_LOGO_JOBS = ["kopru-saglik", "tablo:planli-raporlar", "tablo:uyarilar", "tablo:pano-kartlari", "timas-budget.timer"]
#: Bağlantıyı kullanan, sık (en çok saatte bir) çalışan zamanlanmış işler. Gece ya da günde iki kez çalışan iş düzelmeyi
#: yarım gün bekletmesin diye burada değildir. «@jobs-container»: müşteri sunucusundaki iş kapsayıcısının bütün işleri.
RESOLVE_JOBS: dict[str, list[str]] = {
    "logo": _LOGO_JOBS, "vpn": _LOGO_JOBS, "eposta": ["tablo:planli-raporlar"], "vm": ["@jobs-container"],
    "crm": [], "giris": [], "model": [],
}
#: Son 24 saatte hiç koşmamış iş «sık çalışan» sayılmaz (kurulu değil ya da durdurulmuş).
RESOLVE_JOB_ACTIVE = timedelta(hours=24)


def _ring_jobs(c, tenant: str, ring: str, now: datetime) -> list[Any]:
    names = RESOLVE_JOBS.get(ring, [])
    if not names:
        return []
    cond = []
    plain_names = [n for n in names if not n.startswith("@")]
    if plain_names:
        cond.append(JOBS.c.job.in_(plain_names))
    if "@jobs-container" in names:
        cond.append(JOBS.c.source == "jobs-container")
    rows = c.execute(sa.select(JOBS).where(JOBS.c.tenant_id == tenant, sa.or_(*cond))).mappings().all()
    return [r for r in rows if _aware(r["last_at"]) is not None and now - _aware(r["last_at"]) <= RESOLVE_JOB_ACTIVE]


def resolution(c, tenant: str, ring: str, st: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Kopmanın gerçekten çözüldüğünün üç şartı (kullanıcı kararı 2026-09-29, «sanki yapmışız gibi atmayacağız»):
    (a) son başarısız denemeden sonraki ilk başarılı denemeden bu yana en az `resolveMin` dk kesintisiz başarılı denetim;
    (b) halkanın kendi okuması o aralıkta başarılı (Logo/CRM'de veri sonu satırı dönmüş);
    (c) bağlantıyı kullanan sık çalışan işlerden biri o andan sonra başarıyla koşmuş; böyle iş yoksa (a)+(b) yeter ve
    bu e-postada yazar. Dönen sözlük olayın `resolve_json`'una yazılır."""
    need = timedelta(minutes=int(st.get("resolveMin", 0) or 0))
    last_fail = c.execute(sa.select(sa.func.max(CHECKS.c.at)).where(
        CHECKS.c.tenant_id == tenant, CHECKS.c.ring == ring, CHECKS.c.ok.is_(False))).scalar()
    q = sa.select(sa.func.min(CHECKS.c.at)).where(CHECKS.c.tenant_id == tenant, CHECKS.c.ring == ring, CHECKS.c.ok.is_(True))
    if last_fail is not None:
        q = q.where(CHECKS.c.at > last_fail)
    back = _aware(c.execute(q).scalar())
    if back is None:
        return {"ok": False}
    steady = now - back >= need
    rq = sa.select(CHECKS.c.at, CHECKS.c.data_end).where(
        CHECKS.c.tenant_id == tenant, CHECKS.c.ring == ring, CHECKS.c.ok.is_(True), CHECKS.c.at >= back)
    if ring in STALE_RINGS:
        rq = rq.where(CHECKS.c.data_end.isnot(None))
    read = c.execute(rq.order_by(CHECKS.c.at.desc(), CHECKS.c.id.desc()).limit(1)).mappings().first()
    jobs = _ring_jobs(c, tenant, ring, now)
    good = sorted((j for j in jobs if j["last_ok"] is True and _aware(j["last_at"]) >= back),
                  key=lambda j: _aware(j["last_at"]))
    job_state = "yok" if not jobs else ("var" if good else "bekliyor")
    return {
        "ok": bool(steady and read is not None and job_state != "bekliyor"),
        "backAt": back.isoformat(), "confirmedAt": now.isoformat(),
        "steadyMin": int((now - back).total_seconds() // 60), "needMin": int(need.total_seconds() // 60),
        "dataRead": read is not None, "dataText": DATA_READ.get(ring, "Bağlantı denemesi başarılı"),
        "dataEnd": _iso(read["data_end"]) if read is not None and read["data_end"] is not None else None,
        "jobState": job_state, "jobLabel": good[0]["label"] if good else None,
        "jobAt": _iso(good[0]["last_at"]) if good else None, "jobsWaiting": [j["label"] for j in jobs] if not good else [],
    }


def resolve_rows(res: Optional[dict[str, Any]]) -> list[list[str]]:
    """E-postadaki «Ayrıntı»: hangi düzelme şartları sağlandı."""
    if not res:
        return []
    rows = [["Kesintisiz çalışma", f"Sağlandı: {IB.hm_suffix(res['backAt'])} bu yana {human_minutes(res['steadyMin'])} "
                                   f"başarılı denetim (şart: en az {res['needMin']} dk)"],
            ["Veri okuması", "Sağlandı: " + res["dataText"]
             + (f" ({IB.long_date(res['dataEnd'])})" if res.get("dataEnd") else "")]]
    if res.get("jobState") == "var":
        rows.append(["Zamanlanmış iş", f"Sağlandı: «{res['jobLabel']}» {IB.short_dt(res['jobAt'])} tarihinde başarıyla çalıştı"])
    else:
        rows.append(["Zamanlanmış iş", "Bu bağlantıyı kullanan sık çalışan zamanlanmış iş yok; düzelme ilk iki şartla doğrulandı"])
    return rows


# ------------------------------------------------------------------ köprü açılış kaydı (planlı yeniden başlatma)


BOOT_KEEP_DAYS = 30


def boots(engine: sa.engine.Engine, tenant: str) -> list[datetime]:
    raw = state_get(engine, tenant, "bridge_boots")
    try:
        items = json.loads(raw) if raw else []
    except ValueError:
        items = []
    out = [_aware(x) for x in items if isinstance(x, str)]
    return sorted(x for x in out if x is not None)


def note_boot(engine: sa.engine.Engine, tenant: str, at: datetime) -> bool:
    """Köprünün açılış anını kaydeder (süreç başına bir kez; turda çağrılır, yazıyı yalnız ilk seferde yapar).
    Kayıt `BOOT_KEEP_DAYS` günden eskiyi bırakır: o kadar eski açılışa hiçbir deneme düşmez."""
    at = _aware(at)
    have = boots(engine, tenant)
    if any(abs((b - at).total_seconds()) < 1 for b in have):
        return False
    keep = [b for b in have if b >= at - timedelta(days=BOOT_KEEP_DAYS)] + [at]
    state_set(engine, tenant, "bridge_boots", json.dumps([b.isoformat() for b in sorted(keep)]))
    return True


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
    grace = int(st.get("restartGraceMin") or 0)
    outage = timedelta(minutes=int(st.get("outageMin") or 0))
    boot_list = boots(engine, tenant) if grace else []
    with engine.begin() as c:
        for r in results:
            ring, ok = r["ring"], r.get("ok")
            # --- kopma: art arda en az `failsToOpen` deneme VE ilk başarısız denemeden bu yana en az `outageMin` dk.
            # Kısa kesinti ve köprünün planlı yeniden başlatması olay açmaz.
            if ok is not None:
                cur = _open_incident(c, tenant, ring, "kopma")
                if ok and cur:
                    # Tek başarılı deneme olayı kapatmaz: üç şart birlikte (bkz. `resolution`). Sağlanana dek olay açık
                    # kalır; arada yeniden kopma olursa aynı olay sürer, yeni «Kesinti» e-postası gitmez.
                    res = resolution(c, tenant, ring, st, now)
                    if res["ok"]:
                        c.execute(INCIDENTS.update().where(INCIDENTS.c.id == cur["id"]).values(
                            closed_at=_aware(datetime.fromisoformat(res["backAt"])),
                            resolve_json=json.dumps(res, ensure_ascii=False)))
                        closed.append(cur["id"])
                elif not ok:
                    streak = _fail_streak(c, tenant, ring, boot_list, grace)
                    lasting = bool(streak) and now - _aware(streak[0]["at"]) >= outage
                    if cur:
                        c.execute(INCIDENTS.update().where(INCIDENTS.c.id == cur["id"]).values(last_error=screen_text(r.get("detail"))))
                    elif len(streak) >= st["failsToOpen"] and lasting:
                        first = streak[0]
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


# ------------------------------------------------------------------ bildirim (iç şablon: ic_bildirim)


#: Gönderici: hazır bildirimi alıcılara yollar, durum döndürür (sent | no_smtp | no_recipient | failed).
Sender = Callable[[IB.Notice, list[str]], str]

WHY_RECIPIENTS = ("Bu adrese Sistem durumu ayarlarındaki «Kopma ve düzelme bildirimi alıcıları» listesinde olduğu için geldi. "
                  "Aynı olay için ikinci e-posta gönderilmez; düzelince tek bir «Düzeldi» e-postası gelir.")
WHY_WEEKLY = "Bu adrese Sistem durumu ayarlarındaki «Haftalık sağlık özeti alıcıları» listesinde olduğu için geldi."


def _ring(rid: str) -> dict[str, str]:
    base = RING_BY_ID.get(rid, {"id": rid, "label": rid, "hint": "", "recipe": ""})
    return {**base, **MAIL.get(rid, {"name": base["label"], "impact": ""})}


def _join(names: list[str]) -> str:
    names = list(dict.fromkeys(names))
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " ve " + names[-1]


def _fail_count(engine: sa.engine.Engine, tenant: str, ring: str, since: Any, until: Any = None) -> int:
    q = sa.select(sa.func.count()).select_from(CHECKS).where(
        CHECKS.c.tenant_id == tenant, CHECKS.c.ring == ring, CHECKS.c.ok.is_(False), CHECKS.c.at >= _aware(since))
    if until is not None:
        q = q.where(CHECKS.c.at <= _aware(until))
    with engine.connect() as c:
        return int(c.execute(q).scalar() or 0)


def _last_data_end(engine: sa.engine.Engine, tenant: str, ring: str) -> Optional[datetime]:
    with engine.connect() as c:
        return _aware(c.execute(sa.select(CHECKS.c.data_end).where(
            CHECKS.c.tenant_id == tenant, CHECKS.c.ring == ring, CHECKS.c.data_end.isnot(None))
            .order_by(CHECKS.c.at.desc(), CHECKS.c.id.desc()).limit(1)).scalar())


def _limit_text(ring: str, st: dict[str, Any]) -> str:
    lim = stale_limit(ring, st)
    if lim is None:
        return "—"
    h = int(lim.total_seconds() // 3600)
    return f"{h // 24} gün" if h % 24 == 0 and h >= 24 else f"{h} saat"


def down_notice(engine: Optional[sa.engine.Engine], tenant: str, rows: list[Any], now: datetime, link: str = "", *,
                remind: bool = False, fail_counts: Optional[dict[str, int]] = None,
                resolve_min: int = 15) -> IB.Notice:
    """Kopma bildirimi (açılış ya da, ayarla açıldıysa, hatırlatma). Konu: «[Kesinti] Logo bağlantısı 09:42'den beri
    yanıt vermiyor». `fail_counts` verilirse (örnek üretimi) deneme sayısı tablodan okunmaz."""
    rows = sorted(rows, key=lambda r: _aware(r["opened_at"]))
    first = _aware(rows[0]["opened_at"])
    names = _join([_ring(r["ring"])["name"] for r in rows])
    dur = human_minutes(_minutes(first, now))
    tag = "Sürüyor" if remind else "Kesinti"
    subj = f"{names} {IB.hm_suffix(first)} beri yanıt vermiyor" + (f" · {dur}" if remind else "")
    what, impact, actions = [], [], []
    for r in rows:
        g = _ring(r["ring"])
        n = (fail_counts or {}).get(r["ring"])
        if n is None:
            n = _fail_count(engine, tenant, r["ring"], r["opened_at"])
        what.append(f"5 dakikada bir yapılan denetimde {g['name']} {IB.hm_suffix(r['opened_at'])} bu yana {n} kez art arda "
                    f"yanıt vermedi. Kısa bir kesinti değil: olay ancak kesinti sürünce açılır.")
        if g["impact"]:
            impact.append(g["impact"])
        steps = IB.split_steps(g.get("recipe", ""))
        actions += [(f"{g['name']}: {s}" if len(rows) > 1 else s) for s in steps]
    actions.append(f"Bağlantı {resolve_min} dakika kesintisiz çalışıp veri okununca «Düzeldi» e-postası gelir." if resolve_min
                   else "Bağlantı yeniden çalışıp veri okununca «Düzeldi» e-postası gelir.")
    if len(rows) == 1:
        r = rows[0]
        table = IB.Table(title="Ayrıntı", columns=["Alan", "Değer"], rows=[
            ["Başladı", IB.long_dt(r["opened_at"])], ["Süre", human_minutes(_minutes(r["opened_at"], now)) + " (sürüyor)"],
            ["Son hata", IB.plain(r["last_error"] or r["first_error"] or "—", 300)],
            ["Son deneme", IB.long_dt(now)]])
    else:
        table = IB.Table(title="Ayrıntı", columns=["Bağlantı", "Başladı", "Süre", "Son hata"], rows=[
            [_ring(r["ring"])["name"], IB.short_dt(r["opened_at"]), human_minutes(_minutes(r["opened_at"], now)),
             IB.plain(r["last_error"] or r["first_error"] or "—", 160)] for r in rows])
    head = (f"{names} {IB.day_month(first)} {IB.hm_suffix(first)} beri yanıt vermiyor; kesinti şu ana dek {dur} sürdü.")
    return IB.Notice(tone="kesinti", subject=IB.subject(tag, subj), headline=head, what=what,
                     impact=list(dict.fromkeys(impact)), actions=actions, tables=[table],
                     link=IB.portal_link(link, "sistem-durumu"), link_label="Sistem durumunu aç", at=now,
                     why=WHY_RECIPIENTS, tag=tag)


def stale_notice(engine: Optional[sa.engine.Engine], tenant: str, rows: list[Any], st: dict[str, Any], now: datetime,
                 link: str = "", *, remind: bool = False, data_ends: Optional[dict[str, datetime]] = None) -> IB.Notice:
    """Veri eski bildirimi: bağlantı çalışıyor, okunan son kayıt eşikten eski (ör. donmuş Logo kopyası)."""
    items = []
    for r in rows:
        end = (data_ends or {}).get(r["ring"]) or _last_data_end(engine, tenant, r["ring"])
        items.append((r, RING_BY_ID.get(r["ring"], {"label": r["ring"]})["label"], end))
    names = _join([f"{lbl} verisi" for _, lbl, _ in items])
    ends = [e for _, _, e in items if e]
    oldest = min(ends) if ends else None
    since = f"{IB.day_month(oldest)}'{IB.suffix(IB.day_month(oldest).split()[-1])} beri" if oldest else "bir süredir"
    tag = "Sürüyor" if remind else "Uyarı"
    what = [f"{lbl} bağlantısı çalışıyor ama okunan son kayıt {IB.long_date(end) if end else 'bilinmiyor'} "
            f"tarihli ({human_minutes(_minutes(end, now)) if end else '—'} önce). Eşik: {_limit_text(r['ring'], st)}."
            for r, lbl, end in items]
    what += [IB.split_steps(STALE_RECIPES.get(r["ring"], STALE_RECIPE))[0] for r, _, _ in items]
    table = IB.Table(title="Ayrıntı", columns=["Kaynak", "Son kayıt", "Eşik", "Fark edildi"], rows=[
        [lbl, IB.long_date(end) if end else "—", _limit_text(r["ring"], st), IB.short_dt(r["opened_at"])]
        for r, lbl, end in items])
    return IB.Notice(
        tone="uyari", tag=tag, subject=IB.subject(tag, f"{names} {since} güncellenmiyor"),
        headline=f"{names} {since} güncellenmiyor: bağlantı çalışıyor ama yeni kayıt gelmiyor.",
        what=what,
        impact=["Raporlar ve ekranlar son kayıt tarihine kadar doğrudur; o tarihten sonraki fatura, satış ve kayıtlar "
                "hiçbir ekranda görünmez."],
        # Tarifin ilk cümlesi teşhistir («Ne oldu»), kalanı BT'nin adımları.
        actions=[(f"{lbl}: {s}" if len(items) > 1 else s) for r, lbl, _ in items
                 for s in IB.split_steps(STALE_RECIPES.get(r["ring"], STALE_RECIPE))[1:]]
                + ["Canlı sunucudan yeni kayıt okununca «Düzeldi» e-postası gelir."],
        tables=[table], link=IB.portal_link(link, "sistem-durumu"),
        link_label="Sistem durumunu aç", at=now, why=WHY_RECIPIENTS)


def _resolve_of(r: Any) -> Optional[dict[str, Any]]:
    try:
        raw = r.get("resolve_json") if hasattr(r, "get") else None
        return json.loads(raw) if raw else None
    except (ValueError, TypeError):
        return None


def fixed_notice(rows: list[Any], now: datetime, link: str = "") -> IB.Notice:
    """Düzelme bildirimi: olay başına bir kez. Konu: «[Düzeldi] Logo bağlantısı 10:27'de geri geldi · 45 dk sürdü»."""
    rows = sorted(rows, key=lambda r: _aware(r["closed_at"]))
    def name(r: Any) -> str:
        return (f"{RING_BY_ID.get(r['ring'], {'label': r['ring']})['label']} verisi" if r["kind"] == "tazelik"
                else _ring(r["ring"])["name"])
    names = _join([name(r) for r in rows])
    if len(rows) == 1:
        r = rows[0]
        dur = human_minutes(_minutes(r["opened_at"], r["closed_at"]))
        if r["kind"] == "tazelik":
            subj = f"{names} yeniden güncel"
            head = f"{names} yeniden güncel: yeni kayıtlar {IB.hm_suffix(r['closed_at'], 'de')} okunmaya başladı."
        else:
            subj = f"{names} {IB.hm_suffix(r['closed_at'], 'de')} geri geldi · {dur} sürdü"
            head = f"{names} {IB.day_month(r['closed_at'])} {IB.hm_suffix(r['closed_at'], 'de')} yeniden yanıt verdi; kesinti {dur} sürdü."
        table = IB.Table(title="Ayrıntı", columns=["Alan", "Değer"], rows=[
            ["Başladı", IB.long_dt(r["opened_at"])], ["Düzeldi", IB.long_dt(r["closed_at"])], ["Süre", dur]])
    else:
        subj = f"{names} yeniden çalışıyor"
        head = f"{names} yeniden çalışıyor."
        table = IB.Table(title="Ayrıntı", columns=["Bağlantı", "Başladı", "Düzeldi", "Süre"], rows=[
            [name(r), IB.short_dt(r["opened_at"]), IB.short_dt(r["closed_at"]),
             human_minutes(_minutes(r["opened_at"], r["closed_at"]))] for r in rows])
    what = [f"{name(r)} {IB.short_dt(r['closed_at'])} itibarıyla yeniden çalışıyor "
            f"({human_minutes(_minutes(r['opened_at'], r['closed_at']))} sürdü)." for r in rows]
    # Kopmada «Düzeldi» ancak üç şart sağlanınca gider; hangilerinin sağlandığı ayrıntıda yazar.
    tables = [table]
    checks = [(r, _resolve_of(r)) for r in rows if r["kind"] == "kopma"]
    if any(res for _, res in checks):
        what.append("Sorunun gerçekten çözüldüğü doğrulandı: bağlantı kesintisiz çalıştı ve veri okundu; ayrıntıda hangi "
                    "şartların sağlandığı yazıyor.")
        if len(rows) == 1:
            table.rows += resolve_rows(checks[0][1])
        else:
            extra = IB.Table(title="Doğrulama", columns=["Bağlantı", "Şart", "Durum"], rows=[
                [name(r), a, b] for r, res in checks for a, b in resolve_rows(res)])
            tables = [table, extra]
    return IB.Notice(
        tone="duzeldi", subject=IB.subject("Düzeldi", subj), headline=head, what=what,
        impact=["Etkilenen ekranlar ve işler yeniden güncel veriyi okuyor."],
        actions=["Yapmanız gereken bir şey yok.",
                 "Nedenini biliyorsanız Sistem durumu → Olaylar'da bu olaya kök neden notu yazın; olay değerlendirmesi "
                 "oradan hazırlanır."],
        tables=tables, link=IB.portal_link(link, "sistem-durumu"), link_label="Olayı aç", at=now, why=WHY_RECIPIENTS)


def notify(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], send: Sender, recipients: list[str], *,
           link: str = "", now: Optional[datetime] = None) -> dict[str, Any]:
    """Bekleyen bildirimleri gönderir: yeni açılan kopmalar (tek e-posta), yeni «veri eski» olayları (tek e-posta),
    düzelenler (tek e-posta), ayarla açıldıysa hatırlatmalar. Olay `evaluate`'te ancak gerçek ve süren kesintide açılır;
    burada her olay için bir açılış, bir düzelme e-postası gider. Sonuç her olayın satırına yazılır; gönderilemeyen
    sonraki turda yeniden denenir. Açılışı duyurulmamış olayın düzelmesi duyurulmaz."""
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
        return {"sent": None, "new": 0, "remind": 0, "fixed": 0, "mails": []}

    mails: list[dict[str, Any]] = []

    def fire(n: IB.Notice) -> str:
        res = send(n, recipients) if recipients else "no_recipient"
        mails.append({"subject": n.subject, "result": res})
        return res

    new_down = [r for r in new if r["kind"] == "kopma"]
    new_stale = [r for r in new if r["kind"] == "tazelik"]
    rem_down = [r for r in remind if r["kind"] == "kopma"]
    rem_stale = [r for r in remind if r["kind"] == "tazelik"]
    rmin = int(st.get("resolveMin", 15) or 0)
    # Önce bildirimler kurulup gönderilir, sonra sonuçlar tek işlemde satırlara yazılır.
    updates: list[tuple[list[str], dict[str, Any]]] = []
    for group, make in ((new_down, lambda g: down_notice(engine, tenant, g, now, link, resolve_min=rmin)),
                        (new_stale, lambda g: stale_notice(engine, tenant, g, st, now, link))):
        if group:
            res = fire(make(group))
            updates.append(([r["id"] for r in group], {"notify_status": res, **({"notified_at": now} if res == "sent" else {})}))
    if fixed and fire(fixed_notice(fixed, now, link)) == "sent":
        updates.append(([r["id"] for r in fixed], {"closed_notify": "sent"}))
    for group, make in ((rem_down, lambda g: down_notice(engine, tenant, g, now, link, remind=True,
                                                               resolve_min=rmin)),
                        (rem_stale, lambda g: stale_notice(engine, tenant, g, st, now, link, remind=True))):
        if group and fire(make(group)) == "sent":
            updates.append(([r["id"] for r in group], {"reminded_at": now}))
    with engine.begin() as c:
        for ids, vals in updates:
            c.execute(INCIDENTS.update().where(INCIDENTS.c.id.in_(ids)).values(**vals))
    results = [m["result"] for m in mails]
    overall = "sent" if all(x == "sent" for x in results) else next(x for x in results if x != "sent")
    return {"sent": overall, "new": len(new), "remind": len(remind), "fixed": len(fixed), "mails": mails}


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


#: Zamanlanmış iş hatasının BT'nin işi (bağlantı, hesap, yetki, sunucu) olduğunu gösteren sözcükler; gerisi uygulama hatasıdır.
_BT_ERROR = re.compile(
    r"bağlan|ulaşıl|erişil|erişim|yetki|izin ver|reddedil|parola|şifre|oturum aç|kimlik|hesab[ıi]|kilitl|zaman aşımı|"
    r"sunucu|şirket ağı|sertifika|timeout|timed out|connect|refused|unreachable|denied|permission|login|authenticat|"
    r"network|\bdns\b|certificate|\bssl\b|\btls\b", re.I)
APP_INFO_TITLE = "Bilgi için: uygulama ekibi ilgileniyor"


def split_jobs(jobs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(BT'nin yapabileceği: bağlantı/hesap/yetki/sunucu hatası, uygulama tarafında çözülecek hata)."""
    bt, app = [], []
    for j in jobs:
        (bt if _BT_ERROR.search(str(j.get("lastError") or "")) else app).append(j)
    return bt, app


def weekly_notice(engine: Optional[sa.engine.Engine], tenant: str, now: datetime, failing_jobs: list[dict[str, Any]],
                  link: str = "", *, dt: Optional[dict[str, dict[str, Any]]] = None,
                  still: Optional[list[Any]] = None) -> IB.Notice:
    """Haftalık sağlık özeti: son 7 günün kopma sayısı ve süresi bağlantı başına, şu an açık olaylar, hata veren işler.
    `dt` ve `still` verilirse (örnek üretimi) tablolar okunmaz."""
    since = now - timedelta(days=7)
    if dt is None:
        dt = downtime(engine, tenant, since, now)
    total = sum(v["minutes"] for v in dt.values())
    count = sum(v["count"] for v in dt.values())
    hit = [rid for rid, v in dt.items() if v["count"]]
    worst = max(dt.items(), key=lambda kv: kv[1]["minutes"]) if dt else None
    if still is None:
        with engine.connect() as c:
            still = c.execute(sa.select(INCIDENTS).where(INCIDENTS.c.tenant_id == tenant, INCIDENTS.c.closed_at.is_(None))
                              .order_by(INCIDENTS.c.opened_at.asc())).mappings().all()
    period = IB.day_range(since, now - timedelta(days=1))
    if not count:
        head = f"Geçen hafta {len(RINGS)} bağlantının hepsi kesintisiz çalıştı."
    else:
        head = (f"Geçen hafta {len(RINGS)} bağlantıdan {len(RINGS) - len(hit)} tanesi kesintisiz çalıştı; toplam kesinti "
                f"{human_minutes(total)}, en uzunu {_ring(worst[0])['name']} ({human_minutes(worst[1]['minutes'])}).")
    what = [f"{period} arasında {count} kesinti kaydedildi, toplam {human_minutes(total)}." if count
            else f"{period} arasında kesinti kaydedilmedi."]
    bt_jobs, app_jobs = split_jobs(failing_jobs)
    if bt_jobs:
        what.append(f"{len(bt_jobs)} zamanlanmış iş bağlantı, hesap ya da yetki hatası verdi.")
    impact = []
    if count:
        impact.append("Kesinti sürelerinde ilgili ekranlar son okunan veriyi gösterdi, bağlı raporlar ve uyarılar çalışmadı.")
    if still:
        impact.append("Şu an açık sorun var: " + _join([
            (f"{RING_BY_ID.get(r['ring'], {'label': r['ring']})['label']} verisi eski" if r["kind"] == "tazelik"
             else f"{_ring(r['ring'])['name']} yanıt vermiyor") for r in still]) + ". Çözülene kadar ilgili ekranlar etkilenir.")
    if not impact:
        impact.append("Kesinti kaynaklı bir etki olmadı.")
    # «Ne yapmalı»: yalnız BT'nin yapabileceği işler (bağlantı, hesap, yetki, sunucu). Uygulama hataları BT'ye iş diye
    # yazılmaz; «Bilgi için» altında sayıyla geçer.
    actions = []
    for r in still:
        if r["kind"] == "tazelik":
            steps = IB.split_steps(STALE_RECIPES.get(r["ring"], STALE_RECIPE))[1:]
            lbl = f"{RING_BY_ID.get(r['ring'], {'label': r['ring']})['label']} verisi eski"
        else:
            steps = IB.split_steps(_ring(r["ring"]).get("recipe", ""))
            lbl = f"{_ring(r['ring'])['name']} yanıt vermiyor"
        actions.append(f"{lbl}: " + " ".join(steps))
    if bt_jobs:
        actions.append("Bağlantı ya da yetki hatası veren zamanlanmış işler için (aşağıdaki liste) ilgili bağlantının "
                       "açık olduğunu ve portalın okuma hesabının kilitlenmediğini, yetkisinin durduğunu kontrol edin.")
    if not actions:
        actions.append("Yapmanız gereken bir şey yok.")
    info = ([f"{len(app_jobs)} zamanlanmış iş uygulama kaynaklı hata verdi; uygulama ekibi ilgileniyor, sizden bir işlem "
             "beklenmiyor."] if app_jobs else [])
    tables = [IB.Table(title="Bağlantılar", columns=["Bağlantı", "Kesinti", "Toplam süre"], numeric=(1, 2), rows=[
        [_ring(r["id"])["name"], dt.get(r["id"], {}).get("count", 0),
         human_minutes(dt.get(r["id"], {}).get("minutes", 0)) if dt.get(r["id"], {}).get("count") else "—"] for r in RINGS])]
    if still:
        tables.append(IB.Table(title="Şu an açık", columns=["Sorun", "Başladı", "Süre"], rows=[
            [(f"{RING_BY_ID.get(r['ring'], {'label': r['ring']})['label']} verisi eski" if r["kind"] == "tazelik"
              else _ring(r["ring"])["name"]), IB.short_dt(r["opened_at"]), human_minutes(_minutes(r["opened_at"], now))]
            for r in still]))
    if bt_jobs:
        tables.append(IB.Table(title="Bağlantı ya da yetki hatası veren işler", columns=["İş", "Son koşu", "Son hata"], rows=[
            [j["label"], IB.short_dt(_aware(j.get("lastAt"))), IB.plain(j.get("lastError") or "başarısız", 200)]
            for j in bt_jobs]))
    return IB.Notice(tone="bilgi", tag="Haftalık", subject=IB.subject("Haftalık", f"Sistem sağlığı · {period}"),
                     headline=head, what=what, impact=impact, actions=actions, tables=tables,
                     info=info, info_title=APP_INFO_TITLE,
                     link=IB.portal_link(link, "sistem-durumu"), link_label="Sistem durumunu aç", at=now, why=WHY_WEEKLY)


def weekly_text(engine: sa.engine.Engine, tenant: str, now: datetime, failing_jobs: list[dict[str, Any]]) -> tuple[str, str]:
    n = weekly_notice(engine, tenant, now, failing_jobs)
    return n.subject, IB.render_text(n)


def jobs_digest_notice(failing: list[dict[str, Any]], now: datetime, link: str = "") -> IB.Notice:
    """Günlük «hata veren zamanlanmış işler» özeti (bildirim alıcılarına, günde bir). BT'ye yalnız bağlantı, hesap,
    yetki ya da sunucu hatası iş diye yazılır; uygulama hataları «Bilgi için» altında sayıyla geçer (`run_tour` yalnız
    BT'lik hata varken gönderir)."""
    bt, app = split_jobs(failing)
    k = len(bt)
    return IB.Notice(
        tone="uyari", subject=IB.subject("Uyarı", f"Zamanlanmış işler · {k} iş bağlantı ya da yetki hatası verdi · "
                                                  f"{IB.day_month(now)}"),
        headline=f"Son 24 saatte {k} zamanlanmış iş bağlantı, hesap ya da yetki hatası yüzünden çalışamadı.",
        what=[f"{j['label']}: {IB.plain(j.get('lastError') or 'başarısız', 200)}" for j in bt],
        impact=["Bu işlerin ürettiği rapor, liste ya da veri tazelemesi son başarılı koşudaki hâliyle kalır."],
        actions=["Hatada adı geçen bağlantının açık olduğunu ve portalın okuma hesabının kilitlenmediğini, yetkisinin "
                 "durduğunu kontrol edin.",
                 "Bağlantı düzelince işin sonraki koşusu Sistem durumu → Zamanlanmış işler sekmesinde görünür."],
        info=([f"{len(app)} zamanlanmış iş uygulama kaynaklı hata verdi; uygulama ekibi ilgileniyor, sizden bir işlem "
               "beklenmiyor."] if app else []), info_title=APP_INFO_TITLE,
        tables=[IB.Table(title="Ayrıntı", columns=["İş", "Son koşu", "Sıklık"], rows=[
            [j["label"], IB.short_dt(_aware(j.get("lastAt"))), j.get("every") or "—"] for j in bt])],
        link=IB.portal_link(link, "sistem-durumu"), link_label="Zamanlanmış işleri aç", at=now,
        why="Bu adrese Sistem durumu ayarlarındaki «Kopma ve düzelme bildirimi alıcıları» listesinde olduğu için geldi.")


def jobs_digest_text(failing: list[dict[str, Any]], now: datetime) -> tuple[str, str]:
    n = jobs_digest_notice(failing, now)
    return n.subject, IB.render_text(n)


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
        "recipe": STALE_RECIPES.get(r["ring"], STALE_RECIPE) if r["kind"] == "tazelik" else ring.get("recipe", ""),
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


def draft_facts(inc: dict[str, Any]) -> list[str]:
    """Olay değerlendirmesinin olguları (olay tablosundan). Taslaktaki her sayı bunlardan birinde geçmelidir."""
    tl = inc.get("timeline") or []
    fails = sum(1 for x in tl if x["ok"] is False)
    facts = [
        f"Halka: {inc['ringLabel']}", f"Tür: {inc['kindLabel']}",
        f"Başlangıç: {local_str(_aware(inc['openedAt']))}", f"Bitiş: {local_str(_aware(inc['closedAt'])) if inc['closedAt'] else 'sürüyor'}",
        f"Süre: {human_minutes(inc['minutes'])}", f"Başarısız deneme sayısı: {fails}",
        f"İlk hata: {inc['firstError'] or '—'}", f"Son hata: {inc['lastError'] or '—'}",
        f"BT'nin kök neden notu: {inc['rootCause'] or 'yok'}",
    ]
    if inc.get("minutes") is not None and inc["minutes"] >= 60:
        facts.insert(5, f"Süre (dakika): {inc['minutes']}")
    return facts


def draft_prompt(inc: dict[str, Any]) -> list[dict[str, str]]:
    """Olay değerlendirmesi taslağı için mesaj. Sayılar olay tablosundan gelir; modelden yeni rakam istenmez."""
    system = ("Sen bir BT olay değerlendirmesi taslağı yazıyorsun. Yalnız verilen olguları kullan; yeni sayı, tarih ya da "
              "süre uydurma, olgulardaki sayıları aynen yaz (dönüştürme, toplama). Türkçe, sade, en çok 12 satır. "
              "Başlıklar: Ne oldu, Etki, Süre, Olası neden, Önerilen önlem; başlıkları numaralandırma. "
              "Kök neden notu yoksa «olası neden» için yalnız hata metninden çıkarılabileni yaz ve belirsiz olduğunu söyle.")
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(draft_facts(inc))}]


def _num_set(texts: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for t in texts:
        for n in re.findall(r"\d+(?:[.,]\d+)*", str(t or "")):
            out.add(re.sub(r"[.,]", "", n).lstrip("0") or "0")
        out |= {n.lstrip("0") or "0" for n in re.findall(r"\d+", str(t or ""))}
    return out


def foreign_numbers(text: str, facts: Iterable[str]) -> list[str]:
    """Taslakta geçip olgularda olmayan sayılar. «28.09.2026» olgusu 28, 9 ve 2026'yı da izinli kılar."""
    allowed = _num_set(facts)
    return sorted({n for n in re.findall(r"\d+(?:[.,]\d+)*", str(text or ""))
                   if (re.sub(r"[.,]", "", n).lstrip("0") or "0") not in allowed})


def rule_draft(inc: dict[str, Any]) -> str:
    """Model yoksa ya da taslağı olgularla tutmazsa: aynı olgulardan kalıpla yazılan değerlendirme taslağı."""
    tl = inc.get("timeline") or []
    fails = sum(1 for x in tl if x["ok"] is False)
    end = local_str(_aware(inc["closedAt"])) if inc.get("closedAt") else None
    cause = (inc.get("rootCause") or "").strip()
    err = screen_text(inc.get("lastError") or inc.get("firstError") or "")
    lines = [
        "Ne oldu:", f"{inc['ringLabel']} halkasında «{inc['kindLabel']}» olayı {local_str(_aware(inc['openedAt']))}'de başladı"
        + (f", {end}'de kapandı." if end else "; olay sürüyor."),
        "", "Etki:", f"Bu halkaya bağlı ekranlar ve işler olay boyunca etkilendi; başarısız deneme sayısı {fails}.",
        "", "Süre:", human_minutes(inc.get("minutes")) + ("" if end else " (sürüyor)") + ".",
        "", "Olası neden:", (f"BT'nin kök neden notu: {cause}" if cause else
                            (f"Kök neden notu yok; son hata metni: {err} — neden belirsiz, BT doğrulamalı." if err
                             else "Kök neden notu ve hata metni yok; neden belirsiz, BT doğrulamalı.")),
        "", "Önerilen önlem:", "BT kök nedeni doğrulayıp nota yazmalı; aynı halkada tekrar ederse kalıcı önlem planlanmalı.",
    ]
    return "\n".join(lines)


def guard_draft(text: str, inc: dict[str, Any]) -> tuple[str, str, list[str]]:
    """(taslak, kaynak, olgu dışı sayılar). kaynak «zeki» ya da «kural»: model metnindeki tek bir olgu dışı sayı bile
    metni bütünüyle düşürür (yarım değerlendirme yayımlanmaz), yerine kural taslağı konur. Teknoloji adı sade
    karşılığına çevrilir."""
    raw = re.sub(r"<think>.*?</think>", "", str(text or ""), flags=re.S).strip()
    if not raw:
        return rule_draft(inc), "kural", []
    bad = foreign_numbers(raw, draft_facts(inc))
    if bad:
        return rule_draft(inc), "kural", bad
    lines = []
    for ln in raw.splitlines():
        t = ln
        for rx, rep in _TECH:
            t = rx.sub(rep, t)
        lines.append(t)
    return "\n".join(lines), "zeki", []


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
        if head["ok"] is True:
            text = (f"{head['label']} yeniden yanıt veriyor; düzeldi sayılması için doğrulama sürüyor "
                    f"({st.get('resolveMin', 15)} dk kesintisiz çalışma, veri okuması, zamanlanmış iş)")
        if len(downs) > 1:
            text += f"; {len(downs) - 1} halka daha kopuk"
    elif fails:
        tone = "warn"
        text = (f"{', '.join(x['label'] for x in fails)}: son deneme başarısız "
                f"({st.get('outageMin') or 5} dk sürerse olay açılır)")
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
