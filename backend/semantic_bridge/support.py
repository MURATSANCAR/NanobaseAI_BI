"""M51 Müşteri hizmetleri ve destek yönetimi: köprü katmanı (tablolar, bağlam, Zeki AI, kalite).

Talep kaydı TİMAŞ'ın destek masasıdır (NanobaseAI Destek, `apps/destek`; kullanıcı kararı 2026-09-28). Bu modül ikinci
bir talep sistemi **değildir**: talep açmaz, masaya yazmaz; masayı REST ile okur ve yanına TİMAŞ'a özgü katmanı koyar:

- **Müşteri bağlamı**: e-posta / telefon / sipariş no / cari kodu → CRM kişi-cari eşleşmesi, sipariş ve durumu, sevkiyat,
  kargo takibi (canlı CRM .28) ve Logo'dan fatura/iade (veri sonu tarihiyle).
- **Bayi görünümü**: açık sipariş, bekleyen adet, risk limiti onayı bekleyen, son sevkiyat ve kargo, Logo bakiyesi.
- **Zeki AI**: konu + aciliyet kapalı küme seçimi (`QueuedLlm.choose`, olasılıkla; eşik altı «sınıflanamadı»), SSS
  eşleştirme (gömme servisi; yoksa kelime örtüşmesi) ve temsilcinin onaylayacağı **cevap taslağı** — rakam, tarih, numara
  modelden gelmez, yer tutucudan SQL sonucuyla dolar. Taslak hiçbir yere gönderilmez.
- **Kalite panosu**: masanın talepleri salt okunarak açık/SLA/ilk yanıt/çözüm/memnuniyet ve konu eğilimi.

Kendi tabloları (`semantic_support_*`) yalnız Zeki AI çıktısını, SSS açığı listesini, sınıf ve SLA ayarını tutar. Talep
metni köprüde saklanmaz (KVKK): sınıflama ve taslak için o anda okunur; modele giden metinde e-posta, telefon, IBAN ve
kimlik numarası maskelenir, imza ve alıntı kırpılır.
"""
from __future__ import annotations

import difflib
import json
import logging
import math
import re
import statistics
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from semantic_bridge import support_sources as src
from semantic_bridge.field_sales_sources import SourceError, day, guid, num, opt_num, text

log = logging.getLogger("semantic.support")
TZ = ZoneInfo("Europe/Istanbul")

_md = sa.MetaData()

#: Talep başına Zeki AI çıktısı ve temsilcinin onu nasıl kullandığı. Talep metni burada yok.
INSIGHTS = sa.Table(
    "semantic_support_insights", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("ticket_ref", sa.String(80), primary_key=True),       # masadaki talep numarası (HD Ticket.name)
    sa.Column("source", sa.String(16), nullable=False, default="destek"),   # destek | eposta (sonraki sürüm)
    sa.Column("klass", sa.String(40)),                               # emin olunmadıysa boş: «sınıflanamadı»
    sa.Column("klass_p", sa.Float),
    sa.Column("klass_margin", sa.Float),
    sa.Column("klass_guess", sa.String(40)),                         # eşik altı en olası sınıf (yalnız gösterim)
    sa.Column("klass_method", sa.String(16)),
    sa.Column("urgency", sa.String(16)),
    sa.Column("urgency_p", sa.Float),
    sa.Column("urgency_margin", sa.Float),
    sa.Column("klass_by", sa.String(120)),                           # temsilci düzelttiyse adı; «zeki» = model
    sa.Column("faq_matches_json", sa.Text),
    sa.Column("faq_best", sa.Float),
    sa.Column("contact_ref", sa.String(80)),
    sa.Column("account_ref", sa.String(80)),
    sa.Column("raised_by_hash", sa.String(64)),                      # tekrar eden talep için; adresin kendisi değil
    sa.Column("opened_on", sa.Date),
    sa.Column("draft", sa.Text),
    sa.Column("draft_facts_json", sa.Text),
    sa.Column("draft_by_model_at", sa.DateTime(timezone=True)),
    sa.Column("draft_by", sa.String(120)),
    sa.Column("final_sent", sa.Boolean),
    sa.Column("final_edit_ratio", sa.Float),
    sa.Column("outcome_by", sa.String(120)),
    sa.Column("outcome_at", sa.DateTime(timezone=True)),
    sa.Column("ticket_modified", sa.String(40)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

FAQ_GAPS = sa.Table(
    "semantic_support_faq_gaps", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("klass", sa.String(40), nullable=False),
    sa.Column("label", sa.String(200), nullable=False),
    sa.Column("ticket_count", sa.Integer, nullable=False, default=0),
    sa.Column("sample_refs_json", sa.Text),
    sa.Column("question", sa.Text),                                  # SSS sorusu (yönetici yazar/düzeltir)
    sa.Column("draft", sa.Text),                                     # SSS cevabı taslağı
    sa.Column("status", sa.String(20), nullable=False, default="aday"),   # aday | taslak | onayli | yayinlandi-elle | kapandi
    sa.Column("window_days", sa.Integer),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

#: Portal uyarısı için sınıf başına SLA ve yükseltme (masanın kendi SLA'sı varsa ekranda o kullanılır).
RULES = sa.Table(
    "semantic_support_rules", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("klass", sa.String(40), primary_key=True),
    sa.Column("sla_first_hours", sa.Float),
    sa.Column("sla_resolve_hours", sa.Float),
    sa.Column("escalate_to", sa.String(200)),
    sa.Column("exception_threshold_json", sa.Text),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

CLASSES = sa.Table(
    "semantic_support_classes", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("klass", sa.String(40), primary_key=True),
    sa.Column("label", sa.String(120), nullable=False),
    sa.Column("description", sa.Text),
    sa.Column("active", sa.Boolean, nullable=False, default=True),
    sa.Column("sort", sa.Integer, nullable=False, default=0),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

META = sa.Table(
    "semantic_support_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(60), primary_key=True),
    sa.Column("value_json", sa.Text),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

#: Kurulumda tohumlanan kapalı küme (analiz §13). Yönetici düzenler; «diğer» her zaman vardır.
SEED_CLASSES: list[tuple[str, str, str]] = [
    ("kargo-gecikmesi", "Kargo gecikmesi", "Sipariş gelmedi, kargo nerede, teslimat gecikti, takip numarası soruluyor"),
    ("hasarli-eksik", "Hasarlı / eksik ürün", "Paket hasarlı geldi, kitap eksik ya da yanlış geldi, koli eksik"),
    ("baski-icerik", "Baskı / içerik hatası", "Eksik ya da ters sayfa, cilt dağılması, baskı hatası, metinde hata"),
    ("iade-cayma", "İade / cayma", "İade etmek, cayma hakkı, değişim, para iadesi istiyor"),
    ("fatura", "Fatura", "Fatura istemi, fatura bilgisi yanlış, fatura farkı, e-arşiv"),
    ("bayi-siparis", "Bayi siparişi", "Bayi/kitapçı/kurum siparişi, açık sipariş, bekleyen adet, risk onayı, sevk durumu"),
    ("ekitap-erisim", "E-kitap / erişim", "E-kitap indirme, dijital erişim, üyelik ya da giriş sorunu"),
    ("kampanya-kupon", "Kampanya / kupon", "İndirim kodu, kampanya, kupon çalışmıyor, fiyat farkı"),
    ("diger", "Diğer", "Yukarıdakilerden hiçbiri"),
]
URGENCY = ("yüksek", "normal", "düşük")
GAP_STATES = ("aday", "taslak", "onayli", "yayinlandi-elle", "kapandi")
GAP_LABEL = {"aday": "Aday", "taslak": "Taslak", "onayli": "Onaylı", "yayinlandi-elle": "Siteye elle girildi",
             "kapandi": "Kapandı"}

_ready: set[int] = set()
_lock = threading.Lock()


class SupportError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(TZ).date()


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _j(v: Optional[str], default: Any) -> Any:
    try:
        return json.loads(v) if v else default
    except (TypeError, ValueError):
        return default


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return str(v)


def meta_get(engine: sa.engine.Engine, tenant: str, key: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(sa.select(META).where(META.c.tenant_id == tenant, META.c.key == key)).first()
    return {**_j(row.value_json, {}), "_at": _iso(row.updated_at)} if row else {}


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: dict[str, Any]) -> None:
    with engine.begin() as c:
        c.execute(META.delete().where(META.c.tenant_id == tenant, META.c.key == key))
        c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=_dump(value), updated_at=_now()))


# ------------------------------------------------------------------ ayarlar


def settings_from(conf: Callable[..., str]) -> dict[str, Any]:
    """Ayarlar ekran/ortamdan (`admin.conf`), yoksa varsayılan. Ölçülmemiş varsayımlar burada parametredir."""
    def i(key: str, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(str(conf(key, str(default)) or default))))
        except ValueError:
            return default

    def f(key: str, default: float, lo: float, hi: float) -> float:
        try:
            return max(lo, min(hi, float(str(conf(key, str(default)) or default).replace(",", "."))))
        except ValueError:
            return default

    match = [x.strip() for x in (conf("SUPPORT_CARGO_MATCH", "takip,irsaliye") or "").split(",") if x.strip()]
    return {
        "schema": (conf("CRM_SCHEMA", "Timas_MSCRM.dbo") or "").strip(),
        "destekBase": (conf("DESTEK_API_BASE", "") or "").strip(),
        "destekKey": (conf("DESTEK_API_KEY", "") or "").strip(),
        "destekSecret": (conf("DESTEK_API_SECRET", "") or "").strip(),
        "destekLink": (conf("DESTEK_PUBLIC_URL", "") or "").strip().rstrip("/"),
        "destekVerify": (conf("DESTEK_API_VERIFY_TLS", "1") or "1").strip() not in ("0", "false", "hayir", "hayır"),
        "orderDays": i("SUPPORT_ORDER_DAYS", 365, 7, 3650),
        "logoMonths": i("SUPPORT_LOGO_MONTHS", 12, 1, 60),
        "cargoMatch": [m for m in match if m in ("takip", "irsaliye")] or ["takip"],
        "classifyMinProb": f("SUPPORT_CLASSIFY_MIN_PROB", 0.70, 0.0, 1.0),
        "classifyMinMargin": f("SUPPORT_CLASSIFY_MIN_MARGIN", 0.30, 0.0, 1.0),
        "modelChars": i("SUPPORT_MODEL_TEXT_CHARS", 1500, 200, 8000),
        "faqMinEmbed": f("SUPPORT_FAQ_MIN_SCORE", 0.55, 0.0, 1.0),
        "faqMinLexical": f("SUPPORT_FAQ_MIN_LEXICAL", 0.12, 0.0, 1.0),
        "slaWarnRatio": f("SUPPORT_SLA_WARN_RATIO", 0.80, 0.1, 1.0),
        "repeatDays": i("SUPPORT_REPEAT_DAYS", 7, 1, 90),
        "gapDays": i("SUPPORT_GAP_DAYS", 30, 7, 365),
        "gapMinTickets": i("SUPPORT_GAP_MIN_TICKETS", 3, 1, 1000),
        "batchSeconds": i("SUPPORT_BATCH_SECONDS", 240, 10, 3600),
        "dealerChannels": [int(x) for x in re.split(r"[,\s]+", conf("SUPPORT_DEALER_CHANNELS", "") or "") if x.strip().isdigit()],
        "signature": (conf("SUPPORT_DRAFT_SIGNATURE", "Timaş Yayınları Müşteri Hizmetleri") or "").strip(),
    }


# ------------------------------------------------------------------ sınıflar ve kurallar


def seed_classes(engine: sa.engine.Engine, tenant: str) -> None:
    with engine.begin() as c:
        have = {r[0] for r in c.execute(sa.select(CLASSES.c.klass).where(CLASSES.c.tenant_id == tenant))}
        if have:
            return
        for n, (k, lab, desc) in enumerate(SEED_CLASSES):
            c.execute(CLASSES.insert().values(tenant_id=tenant, klass=k, label=lab, description=desc, active=True,
                                              sort=n, updated_by="kurulum", updated_at=_now()))


def list_classes(engine: sa.engine.Engine, tenant: str, active_only: bool = False) -> list[dict[str, Any]]:
    seed_classes(engine, tenant)
    q = sa.select(CLASSES).where(CLASSES.c.tenant_id == tenant)
    if active_only:
        q = q.where(CLASSES.c.active.is_(True))
    with engine.connect() as c:
        rules = {r.klass: r for r in c.execute(sa.select(RULES).where(RULES.c.tenant_id == tenant))}
        rows = c.execute(q.order_by(CLASSES.c.sort, CLASSES.c.klass)).all()
    out = []
    for r in rows:
        rule = rules.get(r.klass)
        out.append({"klass": r.klass, "label": r.label, "description": r.description or "", "active": bool(r.active),
                    "sort": r.sort, "slaFirstHours": rule.sla_first_hours if rule else None,
                    "slaResolveHours": rule.sla_resolve_hours if rule else None,
                    "escalateTo": rule.escalate_to if rule else None,
                    "exceptions": _j(rule.exception_threshold_json, {}) if rule else {},
                    "updatedBy": r.updated_by, "updatedAt": _iso(r.updated_at)})
    return out


_KLASS = re.compile(r"^[a-z0-9][a-z0-9\-]{1,38}$")


def save_class(engine: sa.engine.Engine, tenant: str, actor: str, klass: str, body: dict[str, Any]) -> dict[str, Any]:
    """Sınıf ekle/düzenle ve SLA/yükseltme kuralı. «diğer» kapatılamaz (kapalı kümenin her zaman bir çıkışı olmalı)."""
    seed_classes(engine, tenant)
    k = (klass or "").strip().lower()
    if not _KLASS.match(k):
        raise SupportError("Sınıf kodu küçük harf, rakam ve tireden oluşmalı (2–39 karakter).", 422)
    label = " ".join(str(body.get("label") or "").split())[:120]
    if not label:
        raise SupportError("Sınıf adı boş olamaz.", 422)
    active = bool(body.get("active", True))
    if k == "diger" and not active:
        raise SupportError("«Diğer» sınıfı kapatılamaz.", 422)

    def hours(key: str) -> Optional[float]:
        v = body.get(key)
        if v in (None, ""):
            return None
        try:
            h = float(str(v).replace(",", "."))
        except ValueError:
            raise SupportError("SLA süresi sayı olmalı (saat).", 422) from None
        if h <= 0 or h > 24 * 90:
            raise SupportError("SLA süresi 0 ile 2160 saat arasında olmalı.", 422)
        return h

    first, resolve = hours("slaFirstHours"), hours("slaResolveHours")
    exc = body.get("exceptions") or {}
    if not isinstance(exc, dict):
        raise SupportError("Kural dışı eşikler sözlük olmalı.", 422)
    now = _now()
    with engine.begin() as c:
        exists = c.execute(sa.select(CLASSES.c.klass).where(CLASSES.c.tenant_id == tenant, CLASSES.c.klass == k)).first()
        vals = {"label": label, "description": str(body.get("description") or "")[:1000], "active": active,
                "updated_by": actor, "updated_at": now}
        if exists:
            c.execute(CLASSES.update().where(CLASSES.c.tenant_id == tenant, CLASSES.c.klass == k).values(**vals))
        else:
            n = c.execute(sa.select(sa.func.count()).select_from(CLASSES).where(CLASSES.c.tenant_id == tenant)).scalar() or 0
            c.execute(CLASSES.insert().values(tenant_id=tenant, klass=k, sort=int(n), **vals))
        c.execute(RULES.delete().where(RULES.c.tenant_id == tenant, RULES.c.klass == k))
        if first or resolve or body.get("escalateTo") or exc:
            c.execute(RULES.insert().values(tenant_id=tenant, klass=k, sla_first_hours=first, sla_resolve_hours=resolve,
                                            escalate_to=str(body.get("escalateTo") or "")[:200] or None,
                                            exception_threshold_json=_dump(exc), updated_by=actor, updated_at=now))
    return next(x for x in list_classes(engine, tenant) if x["klass"] == k)


# ------------------------------------------------------------------ kişisel veri koruması (modele giden metin)

_IBAN = re.compile(r"\bTR\s?\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.I)
_MAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_TCKN = re.compile(r"(?<!\d)[1-9]\d{10}(?!\d)")
_PHONE = re.compile(r"(?<![\w])(?:\+?90[\s\-.]?)?\(?0?[2-5]\d{2}\)?[\s\-.]?\d{3}[\s\-.]?\d{2}[\s\-.]?\d{2}(?!\d)")
_CARD = re.compile(r"(?<!\d)(?:\d{4}[\s\-]?){3}\d{4}(?!\d)")
_SIGNOFF = re.compile(r"(?im)^\s*(--\s*$|saygılarımla|saygılarımızla|iyi çalışmalar|teşekkürler,?\s*$|sent from my|iphone'umdan gönderildi"
                      r"|adres\s*:|tel\s*:|gsm\s*:|telefon\s*:)")


def mask_personal(s: str) -> str:
    """E-posta, telefon, IBAN, kart ve 11 haneli kimlik numarası kalıplarını yer tutucuyla değiştirir."""
    s = _IBAN.sub("[IBAN]", s or "")
    s = _MAIL.sub("[e-posta]", s)
    s = _CARD.sub("[kart]", s)
    s = _TCKN.sub("[kimlik no]", s)
    return _PHONE.sub("[telefon]", s)


def model_text(subject: str, body: str, limit: int) -> str:
    """Modele giden en az metin: konu + gövdenin imza/adres satırından önceki kısmı, maskeli, `limit` karakter."""
    b = src.clean_html(body)
    m = _SIGNOFF.search(b)
    if m and m.start() > 20:
        b = b[:m.start()]
    t = mask_personal(f"Konu: {text(subject) or '-'}\n{b.strip()}")
    return t[:limit]


# ------------------------------------------------------------------ Zeki AI: konu ve aciliyet


def classify_prompt(t: str, classes: list[dict[str, Any]]) -> str:
    lines = "\n".join(f"- {c['label']}: {c['description']}" for c in classes)
    return ("Bir yayınevinin müşteri hizmetlerine gelen talep aşağıda. Talebin konusu hangi sınıfa girer?\n"
            f"Sınıflar ve anlamları:\n{lines}\n\nTalep:\n\"\"\"\n{t}\n\"\"\"")


def urgency_prompt(t: str) -> str:
    return ("Bir yayınevinin müşteri hizmetlerine gelen talep aşağıda. Aciliyeti nedir?\n"
            "yüksek: müşteri mağdur (hasarlı/eksik ürün, yanlış tahsilat, tekrar eden şikâyet, kurum/bayi siparişi durmuş), "
            "sert dil ya da süre baskısı; normal: bilgi ya da durum sorusu; düşük: öneri, teşekkür, genel bilgi.\n\n"
            f"Talep:\n\"\"\"\n{t}\n\"\"\"")


def classify(llm: Any, subject: str, body: str, classes: list[dict[str, Any]], st: dict[str, Any]) -> dict[str, Any]:
    """Konu ve aciliyet: `QueuedLlm.choose` (tek token + olasılık). Eşik altı konu `klass=None` («sınıflanamadı»),
    en olası sınıf `guess` olarak yalnız gösterilir. Model yoksa ya da cevap veremezse istisna yükselir (sonra denenir)."""
    if llm is None or not callable(getattr(llm, "choose", None)):
        raise SupportError("Zeki AI bağlı değil.", 503)
    cls = [c for c in classes if c.get("active", True)]
    if not cls:
        raise SupportError("Etkin sınıf yok.", 409)
    t = model_text(subject, body, st["modelChars"])
    by_label = {c["label"]: c["klass"] for c in cls}
    r = llm.choose(classify_prompt(t, cls), [c["label"] for c in cls])
    ok = r.choice is not None and r.confident(st["classifyMinProb"], st["classifyMinMargin"])
    u = llm.choose(urgency_prompt(t), list(URGENCY))
    return {
        "klass": by_label.get(r.choice) if ok else None, "guess": by_label.get(r.choice) if r.choice else None,
        "p": _r(r.probability), "margin": _r(r.margin), "method": r.method,
        "probs": {by_label[k]: round(float(v), 4) for k, v in (r.probs or {}).items() if k in by_label},
        "urgency": u.choice, "urgencyP": _r(u.probability), "urgencyMargin": _r(u.margin),
        "urgencyConfident": bool(u.choice and u.confident(st["classifyMinProb"], st["classifyMinMargin"])),
        "chars": len(t),
    }


def _r(v: Any) -> Optional[float]:
    return round(float(v), 4) if v is not None else None


# ------------------------------------------------------------------ SSS eşleştirme

_STOP = set("ve veya ile bir bu şu o da de mi mı mu mü ne için gibi çok daha en ama fakat ki ya hem sayın merhaba iyi günler "
            "teşekkür teşekkürler rica ederim lütfen olarak olan var yok ben biz siz sizin bizim benim".split())


def fold(s: str) -> str:
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


def tokens(s: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-zçğıöşü0-9]+", fold(s)) if len(w) > 2 and w not in _STOP}


def lexical_score(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / math.sqrt(len(ta) * len(tb))


def cosine(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


class FaqIndex:
    """SSS kaynakları: masanın yayımlanmış makaleleri, CRM bilgi bankası ve portalda onaylanan SSS maddeleri. Gömme servisi
    (`BI_EMBED_URL`) varsa benzerlik vektörle, yoksa kelime örtüşmesiyle ölçülür; yanıt hangisinin kullanıldığını söyler."""

    TTL = 900

    def __init__(self, embed: Optional[Callable[[list[str]], list[list[float]]]] = None):
        self._embed = embed
        self._lock = threading.Lock()
        self._items: list[dict[str, Any]] = []
        self._vectors: Optional[list[list[float]]] = None
        self._at = 0.0
        self._sig = ""

    def load(self, items: list[dict[str, Any]], force: bool = False) -> None:
        sig = "|".join(f"{i['source']}:{i['id']}:{len(i.get('text') or '')}" for i in items)
        with self._lock:
            if not force and sig == self._sig and time.time() - self._at < self.TTL:
                return
            vecs = None
            if self._embed and items:
                try:
                    vecs = self._embed([f"{i['title']}\n{(i.get('text') or '')[:1500]}" for i in items])
                except Exception as e:  # noqa: BLE001 — gömme servisi yoksa kelime örtüşmesi
                    log.info("support: SSS gömmesi alınamadı, kelime örtüşmesi kullanılacak: %s", e)
            self._items, self._vectors, self._sig, self._at = items, vecs, sig, time.time()

    @property
    def size(self) -> int:
        return len(self._items)

    def match(self, query: str, st: dict[str, Any], k: int = 3) -> dict[str, Any]:
        q = mask_personal(src.clean_html(query))[:2000]
        with self._lock:
            items, vecs = list(self._items), self._vectors
        if not items or not q.strip():
            return {"method": None, "matches": [], "best": None, "threshold": None}
        scored: list[tuple[float, dict[str, Any]]] = []
        method = "lexical"
        if vecs is not None and self._embed:
            try:
                qv = self._embed([q])[0]
                scored = [(cosine(qv, v), it) for v, it in zip(vecs, items)]
                method = "embedding"
            except Exception as e:  # noqa: BLE001
                log.info("support: soru gömmesi alınamadı: %s", e)
        if method == "lexical":
            scored = [(lexical_score(q, f"{it['title']} {it.get('keywords') or ''} {(it.get('text') or '')[:1500]}"), it)
                      for it in items]
        th = st["faqMinEmbed"] if method == "embedding" else st["faqMinLexical"]
        scored.sort(key=lambda x: -x[0])
        best = round(scored[0][0], 4) if scored else None
        out = [{"source": it["source"], "id": it["id"], "title": it["title"], "score": round(s, 4),
                "excerpt": (it.get("text") or "")[:280], "url": it.get("url")}
               for s, it in scored[:k] if s >= th]
        return {"method": method, "matches": out, "best": best, "threshold": th}


def faq_items(articles: list[dict[str, Any]], crm_articles: list[dict[str, Any]], approved: list[dict[str, Any]],
              destek_link: str = "") -> list[dict[str, Any]]:
    items = []
    for a in articles:
        items.append({"source": "destek", "id": str(a.get("name")), "title": text(a.get("title")) or "",
                      "text": src.clean_html(a.get("content")), "keywords": "",
                      "url": f"{destek_link}/helpdesk/kb/articles/{a.get('name')}" if destek_link else None})
    for a in crm_articles:
        items.append({"source": "crm", "id": guid(a.get("id")) or "", "title": text(a.get("baslik")) or "",
                      "text": src.clean_html(a.get("icerik")), "keywords": text(a.get("anahtar")) or "", "url": None})
    for g in approved:
        items.append({"source": "portal", "id": g["id"], "title": g.get("question") or g.get("label") or "",
                      "text": g.get("draft") or "", "keywords": g.get("label") or "", "url": None})
    return [i for i in items if i["title"] or i["text"]]


# ------------------------------------------------------------------ cevap taslağı (rakam modelden gelmez)

#: Taslakta kullanılabilecek yer tutucular: değerleri bağlam uçlarının SQL sonucundan dolar.
FACT_KEYS: dict[str, str] = {
    "musteri_adi": "müşterinin adı", "siparis_no": "sipariş numarası", "siparis_tarihi": "sipariş tarihi",
    "siparis_durumu": "siparişin CRM'deki durumu", "bekleyen_adet": "henüz gönderilmemiş adet",
    "sevk_tarihi": "sevk tarihi", "kargo_firmasi": "kargo firması", "takip_no": "kargo takip numarası",
    "takip_adresi": "kargo takip bağlantısı", "teslim_tarihi": "kargo firmasının teslim tarihi",
    "fatura_no": "fatura numarası", "fatura_tarihi": "fatura tarihi", "sss_baslik": "ilgili SSS başlığı",
}
_PH = re.compile(r"\{([a-z_]+)\}")


def facts_from_context(ctx: dict[str, Any], faq: Optional[dict[str, Any]] = None) -> dict[str, str]:
    """Bağlamın ilk (en ilgili) siparişinden taslak olguları. Değeri olmayan anahtar yazılmaz."""
    f: dict[str, str] = {}
    who = (ctx.get("match") or {}).get("contacts") or []
    if who and who[0].get("ad"):
        f["musteri_adi"] = str(who[0]["ad"])
    orders = ctx.get("orders") or []
    o = orders[0] if orders else None
    if o:
        for key, val in (("siparis_no", o.get("no")), ("siparis_tarihi", _tr_day(o.get("tarih"))),
                         ("siparis_durumu", o.get("durumAd")), ("sevk_tarihi", _tr_day(o.get("sevkTarihi"))),
                         ("kargo_firmasi", o.get("kargoFirma")), ("takip_no", o.get("takipNo")),
                         ("takip_adresi", o.get("takipUrl"))):
            if val:
                f[key] = str(val)
        if o.get("bekleyen") and o.get("acik"):
            f["bekleyen_adet"] = _int_text(o["bekleyen"])
        for c in ctx.get("cargo") or []:
            if o.get("id") in (c.get("orderIds") or []) or (o.get("takipNo") and c.get("takipNo") == o.get("takipNo")):
                if c.get("firma") and "kargo_firmasi" not in f:
                    f["kargo_firmasi"] = c["firma"]
                if c.get("takipNo") and "takip_no" not in f:
                    f["takip_no"] = c["takipNo"]
                if c.get("teslimTarihi"):
                    f["teslim_tarihi"] = c["teslimTarihi"]
                break
        for s in ctx.get("shipments") or []:
            if s.get("orderId") == o.get("id") and s.get("faturaNo"):
                f["fatura_no"] = s["faturaNo"]
                inv = s.get("logo") or {}
                if inv.get("tarih"):
                    f["fatura_tarihi"] = _tr_day(inv["tarih"])
                break
    if faq and faq.get("matches"):
        f["sss_baslik"] = faq["matches"][0]["title"]
    return f


def _tr_day(v: Any) -> Optional[str]:
    d = day(v)
    return f"{d[8:10]}.{d[5:7]}.{d[:4]}" if d else None


def _int_text(v: Any) -> str:
    n = num(v)
    return str(int(n)) if n == int(n) else str(n).replace(".", ",")


def draft_messages(t: str, klass_label: Optional[str], facts: dict[str, str], faq: Optional[dict[str, Any]],
                   signature: str) -> list[dict[str, str]]:
    keys = "\n".join(f"- {{{k}}}: {FACT_KEYS[k]}" for k in facts if k in FACT_KEYS) or "- (bu talep için olgu yok)"
    faq_text = ""
    if faq and faq.get("matches"):
        m = faq["matches"][0]
        faq_text = f"\nİlgili SSS maddesi: «{m['title']}» — {m['excerpt']}\n"
    system = ("Sen Zeki AI'sın; Timaş Yayınları müşteri hizmetleri temsilcisi için cevap taslağı yazıyorsun. Taslağı "
              "temsilci okuyup düzeltecek ve kendisi gönderecek. Kurallar: Türkçe, nazik, kısa (en çok 6 cümle). "
              "Hiçbir rakam, tarih, tutar, sipariş ya da takip numarası, firma adı yazma: bunlar gerekiyorsa YALNIZ aşağıdaki "
              "yer tutucuları süslü paranteziyle aynen yaz, başka yer tutucu uydurma. Bilmediğin şeyi söz verme; iade, "
              "ücretsiz gönderim ya da tazminat sözü verme (bu kararlar yöneticinindir). Selamla başla, imza satırı yazma.")
    user = (f"Talebin konusu: {klass_label or 'belirlenemedi'}\n{faq_text}\nKullanabileceğin yer tutucular:\n{keys}\n\n"
            f"Müşterinin talebi:\n\"\"\"\n{t}\n\"\"\"\n\nCevap taslağını yaz.")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


_SENT = re.compile(r"(?<=[.!?])\s+|\n+")
_RUN = re.compile(r"\d+")   # rakam dizisi: «48-64» talepte geçtiyse taslakta «48–64» de geçer


def fill_draft(raw: str, facts: dict[str, str], ticket_text: str, signature: str) -> dict[str, Any]:
    """Model metnindeki yer tutucuları olgularla doldurur. Olgusu olmayan yer tutucu ya da talepte/olgularda geçmeyen
    bir rakam içeren cümle düşer (model rakam uyduramaz). Düşen cümle sayısı ekranda yazılır."""
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S).strip()
    allowed = set(_RUN.findall(ticket_text or ""))
    for v in facts.values():
        allowed |= set(_RUN.findall(v))
    kept, dropped = [], []
    for part in [p.strip() for p in _SENT.split(raw) if p and p.strip()]:
        names = _PH.findall(part)
        if any(n not in facts for n in names):
            dropped.append(part)
            continue
        bare = _PH.sub("", part)
        if any(d not in allowed for d in _RUN.findall(bare)):
            dropped.append(part)
            continue
        kept.append(_PH.sub(lambda m: facts[m.group(1)], part))
    body = " ".join(kept).strip()
    if signature and body:
        body = f"{body}\n\n{signature}"
    return {"text": body, "dropped": len(dropped), "used": sorted({n for p in kept for n in _PH.findall(p)} & set(facts))}


def edit_ratio(draft: str, final: str) -> float:
    """Temsilcinin taslağı ne kadar değiştirdiği (0 = aynen, 1 = tamamen yeni). Son metin saklanmaz, yalnız oran."""
    return round(1.0 - difflib.SequenceMatcher(None, draft or "", final or "").ratio(), 4)


_ORDER_REF = re.compile(r"(?<![\w])(?:[A-ZÇĞİÖŞÜ]{1,5}[-/]?\d{4,}|\d{7,12})(?![\w])")


def order_refs(t: str) -> list[str]:
    """Talep metninde geçen olası sipariş numaraları (ör. «TS-240915»): bağlam aramasına aday, doğrulamayı CRM yapar."""
    out = []
    for m in _ORDER_REF.findall(src.clean_html(t)):
        if m not in out and not re.fullmatch(r"0?5\d{9}", m):   # cep telefonu değil
            out.append(m)
    return out[:5]


# ------------------------------------------------------------------ kalite panosu (masa verisi, salt okuma)


def _median(xs: list[float]) -> Optional[float]:
    return round(statistics.median(xs), 1) if xs else None


def sla_state(t: dict[str, Any], now: datetime, warn: float) -> Optional[str]:
    """Açık talebin SLA durumu: ilk yanıt yapılmadıysa `response_by`, yapıldıysa `resolution_by`'a göre.
    «asildi» (süre geçti ya da masa Failed dedi), «yaklasiyor» (sürenin `warn` payı doldu), «icinde», None (SLA yok)."""
    if str(t.get("agreement_status") or "") == "Failed":
        return "asildi"
    opened = src.ticket_datetime(t)
    due = src.parse_dt(t.get("resolution_by") if t.get("first_responded_on") else t.get("response_by"))
    if not due:
        return None
    if now >= due:
        return "asildi"
    if opened and due > opened and (now - opened) / (due - opened) >= warn:
        return "yaklasiyor"
    return "icinde"


def quality(tickets: list[dict[str, Any]], previous: list[dict[str, Any]], open_now: list[dict[str, Any]],
            insights: dict[str, dict[str, Any]], classes: list[dict[str, Any]], frm: date, to: date, now: datetime,
            st: dict[str, Any], *, per_agent: bool) -> dict[str, Any]:
    """Masa taleplerinden kalite göstergeleri. `tickets` = [frm, to] aralığında açılanlar, `previous` = hemen önceki eş
    uzunluktaki dönem, `open_now` = bugün açık olanların hepsi (açılış tarihinden bağımsız). Sayı tavanı yok."""
    labels = {c["klass"]: c["label"] for c in classes}
    first_min, resolve_h, ratings = [], [], []
    by_status: dict[str, int] = {}
    channel = {"portal": 0, "eposta": 0}
    resolved = 0
    for t in tickets:
        cat = str(t.get("status_category") or t.get("status") or "?")
        by_status[cat] = by_status.get(cat, 0) + 1
        channel["portal" if int(num(t.get("via_customer_portal"))) else "eposta"] += 1
        opened = src.ticket_datetime(t)
        fr = src.parse_dt(t.get("first_responded_on"))
        if opened and fr and fr >= opened:
            first_min.append((fr - opened).total_seconds() / 60)
        rd = src.parse_dt(t.get("resolution_date"))
        if opened and rd and rd >= opened:
            resolve_h.append((rd - opened).total_seconds() / 3600)
            resolved += 1
        r = src.rating_5(t.get("feedback_rating"))
        if r is not None:
            ratings.append(r)

    sla = {"asildi": 0, "yaklasiyor": 0, "icinde": 0, "yok": 0}
    agents: dict[str, int] = {}
    due_today = 0
    today_end = datetime.combine(now.date(), datetime.max.time())
    for t in open_now:
        s = sla_state(t, now, st["slaWarnRatio"]) or "yok"
        sla[s] += 1
        due = src.parse_dt(t.get("resolution_by") if t.get("first_responded_on") else t.get("response_by"))
        if due and now <= due <= today_end:
            due_today += 1
        for a in src.assignees(t) or ["(atanmamış)"]:
            agents[a] = agents.get(a, 0) + 1

    def count_classes(rows: list[dict[str, Any]]) -> dict[str, int]:
        out: dict[str, int] = {}
        for t in rows:
            ins = insights.get(str(t.get("name")))
            k = (ins or {}).get("klass") or ("siniflanamadi" if ins else "bekliyor")
            out[k] = out.get(k, 0) + 1
        return out

    cur, prev = count_classes(tickets), count_classes(previous)
    extra = {"siniflanamadi": "Sınıflanamadı", "bekliyor": "Henüz sınıflanmadı"}
    topics = sorted(({"klass": k, "label": labels.get(k) or extra.get(k, k), "count": n, "previous": prev.get(k, 0)}
                     for k, n in cur.items()), key=lambda x: (-x["count"], x["label"]))

    weeks: dict[str, dict[str, int]] = {}
    for t in tickets:
        opened = src.ticket_datetime(t)
        if not opened:
            continue
        wk = (opened.date() - timedelta(days=opened.weekday())).isoformat()
        k = (insights.get(str(t.get("name"))) or {}).get("klass") or "diger-bos"
        weeks.setdefault(wk, {})
        weeks[wk][k] = weeks[wk].get(k, 0) + 1

    # Tekrarlayan talep: aynı gönderen, aynı konu, `repeatDays` içinde ikinci kez (gönderen yalnız özetle karşılaştırılır).
    seen: dict[tuple[str, str], datetime] = {}
    repeats = 0
    for t in sorted(tickets, key=lambda x: src.ticket_datetime(x) or datetime.min):
        ins = insights.get(str(t.get("name"))) or {}
        who, k, opened = ins.get("raisedByHash"), ins.get("klass"), src.ticket_datetime(t)
        if not (who and k and opened):
            continue
        last = seen.get((who, k))
        if last and (opened - last).days <= st["repeatDays"]:
            repeats += 1
        seen[(who, k)] = opened

    classified = [insights[str(t.get("name"))] for t in tickets if str(t.get("name")) in insights]
    no_faq = sum(1 for i in classified if not i.get("faqHit"))
    drafts = [i for i in classified if i.get("finalSent") is not None]
    return {
        "window": {"from": frm.isoformat(), "to": to.isoformat()},
        "opened": len(tickets), "openedPrevious": len(previous), "resolved": resolved, "byStatus": by_status,
        "openNow": len(open_now), "sla": sla, "dueToday": due_today,
        "firstResponseMedianMin": _median(first_min), "firstResponseCount": len(first_min),
        "resolutionMedianHours": _median(resolve_h), "resolutionCount": len(resolve_h),
        "csat": round(sum(ratings) / len(ratings), 2) if ratings else None, "csatCount": len(ratings),
        "channel": channel, "topics": topics,
        "weekly": [{"week": w, "counts": weeks[w]} for w in sorted(weeks)],
        "repeat": {"count": repeats, "days": st["repeatDays"],
                   "rate": round(repeats / len(tickets), 4) if tickets else None},
        "zeki": {"classified": sum(1 for i in classified if i.get("klass")), "unsure": sum(1 for i in classified if not i.get("klass")),
                 "waiting": len(tickets) - len(classified), "corrected": sum(1 for i in classified if i.get("klassBy") not in (None, "zeki")),
                 "noFaq": no_faq, "drafts": len(drafts),
                 "sentAsIs": sum(1 for i in drafts if i.get("finalSent") and (i.get("editRatio") or 0) <= 0.1)},
        "agents": ([{"agent": a, "open": n} for a, n in sorted(agents.items(), key=lambda x: -x[1])] if per_agent else None),
    }


# ------------------------------------------------------------------ Zeki AI kayıtları


def insight_row(r: Any) -> dict[str, Any]:
    m = r._mapping
    return {"ticket": m["ticket_ref"], "klass": m["klass"], "klassP": m["klass_p"], "klassMargin": m["klass_margin"],
            "klassGuess": m["klass_guess"], "klassMethod": m["klass_method"], "klassBy": m["klass_by"],
            "urgency": m["urgency"], "urgencyP": m["urgency_p"], "faq": _j(m["faq_matches_json"], None),
            "faqHit": bool((_j(m["faq_matches_json"], {}) or {}).get("matches")),
            "contactRef": m["contact_ref"], "accountRef": m["account_ref"], "raisedByHash": m["raised_by_hash"],
            "openedOn": m["opened_on"].isoformat() if m["opened_on"] else None, "draft": m["draft"],
            "draftFacts": _j(m["draft_facts_json"], None), "draftAt": _iso(m["draft_by_model_at"]), "draftBy": m["draft_by"],
            "finalSent": m["final_sent"], "editRatio": m["final_edit_ratio"], "updatedAt": _iso(m["updated_at"])}


def get_insight(engine: sa.engine.Engine, tenant: str, ref: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(INSIGHTS).where(INSIGHTS.c.tenant_id == tenant, INSIGHTS.c.ticket_ref == ref)).first()
    return insight_row(r) if r else None


def insights_for(engine: sa.engine.Engine, tenant: str, refs: Iterable[str]) -> dict[str, dict[str, Any]]:
    refs = [str(r) for r in refs if r]
    out: dict[str, dict[str, Any]] = {}
    with engine.connect() as c:
        for i in range(0, len(refs), 500):
            for r in c.execute(sa.select(INSIGHTS).where(INSIGHTS.c.tenant_id == tenant,
                                                         INSIGHTS.c.ticket_ref.in_(refs[i:i + 500]))):
                out[r.ticket_ref] = insight_row(r)
    return out


def upsert_insight(engine: sa.engine.Engine, tenant: str, ref: str, **vals: Any) -> None:
    now = _now()
    with engine.begin() as c:
        exists = c.execute(sa.select(INSIGHTS.c.ticket_ref).where(INSIGHTS.c.tenant_id == tenant,
                                                                  INSIGHTS.c.ticket_ref == ref)).first()
        if exists:
            c.execute(INSIGHTS.update().where(INSIGHTS.c.tenant_id == tenant, INSIGHTS.c.ticket_ref == ref)
                      .values(updated_at=now, **vals))
        else:
            c.execute(INSIGHTS.insert().values(tenant_id=tenant, ticket_ref=ref, source=vals.pop("source", "destek"),
                                               created_at=now, updated_at=now, **vals))


def hash_sender(email: Any) -> Optional[str]:
    """Gönderen adresinin tuzlu olmayan kısa özeti: yalnız «aynı kişi mi» karşılaştırması için; adres saklanmaz."""
    import hashlib

    e = (text(email) or "").lower()
    return hashlib.sha256(e.encode("utf-8")).hexdigest()[:32] if e else None


def classification_values(res: dict[str, Any], faq: Optional[dict[str, Any]], ticket: dict[str, Any]) -> dict[str, Any]:
    return {"klass": res["klass"], "klass_p": res["p"], "klass_margin": res["margin"], "klass_guess": res["guess"],
            "klass_method": res["method"], "klass_by": "zeki" if res["klass"] else None, "urgency": res["urgency"],
            "urgency_p": res["urgencyP"], "urgency_margin": res["urgencyMargin"],
            "faq_matches_json": _dump(faq) if faq is not None else None,
            "faq_best": (faq or {}).get("best"), "raised_by_hash": hash_sender(ticket.get("raised_by")),
            "opened_on": src.as_date(ticket.get("opening_date")), "ticket_modified": str(ticket.get("modified") or "")[:40]}


def set_class(engine: sa.engine.Engine, tenant: str, ref: str, actor: str, klass: str, urgency: Optional[str],
              classes: list[dict[str, Any]]) -> dict[str, Any]:
    """Temsilcinin düzelttiği sınıf (M50 karnesine «değiştirilen» olarak girer)."""
    if klass not in {c["klass"] for c in classes}:
        raise SupportError("Bilinmeyen sınıf.", 422)
    if urgency is not None and urgency not in URGENCY:
        raise SupportError("Aciliyet yüksek, normal ya da düşük olmalı.", 422)
    vals: dict[str, Any] = {"klass": klass, "klass_by": actor}
    if urgency is not None:
        vals["urgency"] = urgency
    upsert_insight(engine, tenant, ref, **vals)
    return get_insight(engine, tenant, ref) or {}


def record_outcome(engine: sa.engine.Engine, tenant: str, ref: str, actor: str, sent: bool, final_text: Optional[str]) -> dict[str, Any]:
    ins = get_insight(engine, tenant, ref)
    if not ins or not ins.get("draft"):
        raise SupportError("Bu talep için taslak yok.", 404)
    ratio = edit_ratio(ins["draft"], final_text) if (sent and final_text is not None) else None
    upsert_insight(engine, tenant, ref, final_sent=bool(sent), final_edit_ratio=ratio, outcome_by=actor, outcome_at=_now())
    return get_insight(engine, tenant, ref) or {}


# ------------------------------------------------------------------ SSS açığı listesi


def gap_row(r: Any) -> dict[str, Any]:
    m = r._mapping
    return {"id": m["id"], "klass": m["klass"], "label": m["label"], "tickets": m["ticket_count"],
            "samples": _j(m["sample_refs_json"], []), "question": m["question"], "draft": m["draft"],
            "status": m["status"], "statusLabel": GAP_LABEL.get(m["status"], m["status"]), "windowDays": m["window_days"],
            "approvedBy": m["approved_by"], "approvedAt": _iso(m["approved_at"]), "updatedBy": m["updated_by"],
            "updatedAt": _iso(m["updated_at"])}


def list_gaps(engine: sa.engine.Engine, tenant: str, status: Optional[str] = None) -> list[dict[str, Any]]:
    q = sa.select(FAQ_GAPS).where(FAQ_GAPS.c.tenant_id == tenant)
    if status:
        q = q.where(FAQ_GAPS.c.status == status)
    with engine.connect() as c:
        return [gap_row(r) for r in c.execute(q.order_by(FAQ_GAPS.c.ticket_count.desc(), FAQ_GAPS.c.label))]


def approved_faq(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    return [g for g in list_gaps(engine, tenant) if g["status"] in ("onayli", "yayinlandi-elle") and g.get("draft")]


def refresh_gaps(engine: sa.engine.Engine, tenant: str, insights: list[dict[str, Any]], classes: list[dict[str, Any]],
                 st: dict[str, Any], since: date) -> dict[str, Any]:
    """Pencere içindeki taleplerde SSS eşleşmesi bulunamayanları konuya göre sayar; eşik üstündeki konu «aday» olur.
    Yöneticinin üzerinde çalıştığı (taslak/onaylı) satırın yalnız sayısı güncellenir, metnine dokunulmaz."""
    labels = {c["klass"]: c["label"] for c in classes}
    groups: dict[str, list[str]] = {}
    for i in insights:
        if i.get("klass") and not i.get("faqHit") and (i.get("openedOn") or "") >= since.isoformat():
            groups.setdefault(i["klass"], []).append(i["ticket"])
    now = _now()
    made = updated = 0
    with engine.begin() as c:
        rows = {r.klass: r for r in c.execute(sa.select(FAQ_GAPS).where(
            FAQ_GAPS.c.tenant_id == tenant, FAQ_GAPS.c.status.in_(("aday", "taslak", "onayli"))))}
        for k, refs in groups.items():
            if len(refs) < st["gapMinTickets"]:
                continue
            vals = {"ticket_count": len(refs), "sample_refs_json": _dump(sorted(refs)[-10:]),
                    "window_days": st["gapDays"], "updated_at": now}
            if k in rows:
                c.execute(FAQ_GAPS.update().where(FAQ_GAPS.c.id == rows[k].id).values(**vals))
                updated += 1
            else:
                c.execute(FAQ_GAPS.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, klass=k, label=labels.get(k, k),
                                                   status="aday", created_at=now, updated_by="zeki", **vals))
                made += 1
    return {"new": made, "updated": updated, "groups": len(groups)}


def patch_gap(engine: sa.engine.Engine, tenant: str, gid: str, actor: str, body: dict[str, Any]) -> dict[str, Any]:
    """SSS maddesi: soru/cevap düzeltme ve durum. Onaylı metin T-soft'a portaldan gönderilmez; siteye elle girilir,
    «yayinlandi-elle» ile işaretlenir."""
    with engine.connect() as c:
        r = c.execute(sa.select(FAQ_GAPS).where(FAQ_GAPS.c.tenant_id == tenant, FAQ_GAPS.c.id == gid)).first()
    if not r:
        raise SupportError("SSS maddesi bulunamadı.", 404)
    vals: dict[str, Any] = {"updated_by": actor, "updated_at": _now()}
    for key, col, lim in (("question", "question", 500), ("draft", "draft", 8000), ("label", "label", 200)):
        if key in body:
            vals[col] = str(body.get(key) or "").strip()[:lim] or None
    status = body.get("status")
    if status is not None:
        if status not in GAP_STATES:
            raise SupportError("Geçersiz durum.", 422)
        if status in ("onayli", "yayinlandi-elle"):
            q = vals.get("question", r.question)
            d = vals.get("draft", r.draft)
            if not (q and d):
                raise SupportError("Onay için soru ve cevap metni dolu olmalı.", 422)
            if status == "onayli":
                vals.update(approved_by=actor, approved_at=_now())
        vals["status"] = status
    if vals.get("label") is None and "label" in vals:
        vals.pop("label")
    with engine.begin() as c:
        c.execute(FAQ_GAPS.update().where(FAQ_GAPS.c.id == gid).values(**vals))
        r = c.execute(sa.select(FAQ_GAPS).where(FAQ_GAPS.c.id == gid)).first()
    return gap_row(r)


# ------------------------------------------------------------------ kaynak okuması (bağlantı başına)


def chunks(xs: list[Any], n: int = 400) -> Iterable[list[Any]]:
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


class Source:
    """CRM + Logo bağlantıları (okuma başına açılıp kapanır) ve destek masası istemcisi. Kargo firması adları ve CRM
    durum etiketleri 1 saat bellekte; müşteri verisi bellekte tutulmaz."""

    TTL = 3600

    def __init__(self, crm_connect: Callable[[], Any], logo_connect: Callable[[], Any],
                 destek: Callable[[dict[str, Any]], src.DestekClient]):
        self._crm, self._logo, self._destek = crm_connect, logo_connect, destek
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, Any]] = {}

    def crm(self, fn: Callable[[src.Run], Any]) -> Any:
        from semantic_bridge.field_sales import _close, _runner

        conn = self._crm()
        try:
            run = _runner(conn)
            return fn(lambda sql: src.lower_keys(run(src.guard(sql))))
        finally:
            _close(conn)

    def logo(self, fn: Callable[[src.Run], Any]) -> Any:
        from semantic_bridge.field_sales import _close, _runner

        conn = self._logo()
        try:
            run = _runner(conn)
            return fn(lambda sql: src.lower_keys(run(src.guard(sql))))
        finally:
            _close(conn)

    def destek(self, st: dict[str, Any]) -> src.DestekClient:
        return self._destek(st)

    def cached(self, key: str, fn: Callable[[], Any]) -> Any:
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < self.TTL:
                return hit[1]
        val = fn()
        with self._lock:
            self._cache[key] = (time.time(), val)
        return val

    def status_labels(self, st: dict[str, Any]) -> dict[int, str]:
        def read() -> dict[int, str]:
            try:
                rows = self.crm(lambda run: run(src.crm_order_status_sql(st["schema"])))
                return {int(num(r.get("code"))): text(r.get("label")) or "" for r in rows if text(r.get("label"))}
            except Exception as e:  # noqa: BLE001 — etiket yoksa C13 listesi
                log.info("support: CRM durum etiketleri okunamadı: %s", e)
                return {}
        return self.cached("status-labels", read)

    def cargo_firms(self, st: dict[str, Any]) -> dict[str, str]:
        return self.cached("cargo-firms", lambda: {guid(r.get("id")) or "": text(r.get("ad")) or text(r.get("kod")) or ""
                                                   for r in self.crm(lambda run: run(src.crm_cargo_firms_sql(st["schema"])))})

    def logo_calendar(self, now: date) -> dict[str, Any]:
        from semantic_bridge.field_sales import logo_calendar

        return self.cached(f"logo-cal:{now.isoformat()}", lambda: self.logo(lambda run: logo_calendar(_upper_runner(run), now)))


def _upper_runner(run: src.Run) -> src.Run:
    """`budget_sources.firms_by_year` büyük harfli anahtar bekler (L_CAPIPERIOD); `run` küçük harfe çevirdiği için ikisini
    de verir."""
    def inner(sql: str) -> list[dict[str, Any]]:
        return [{**r, **{k.upper(): v for k, v in r.items()}} for r in run(sql)]
    return inner


# ------------------------------------------------------------------ bağlam (müşteri 360)


def _needs(domains: Optional[frozenset[str]], d: str) -> bool:
    return domains is None or d in domains


def context(source: Source, st: dict[str, Any], *, email: Optional[str] = None, phone: Optional[str] = None,
            order: Optional[str] = None, account: Optional[str] = None, code: Optional[str] = None,
            domains: Optional[frozenset[str]] = None, now: Optional[date] = None,
            tickets: Optional[Callable[[str], list[dict[str, Any]]]] = None) -> dict[str, Any]:
    """Müşteri bağlamı. `domains` kişinin veri alanları (None = sınırsız): kimlik eşleşmesi `cari`, sipariş/sevkiyat/kargo
    ve fatura `satis` ister. Birden çok cari adayı çıkarsa ve `account` verilmediyse yalnız adaylar döner (temsilci seçer)."""
    now = now or today()
    if not (email or phone or order or account or code):
        raise SupportError("E-posta, telefon, sipariş numarası ya da cari seçin.", 422)
    if not _needs(domains, "cari"):
        raise SupportError("Müşteri bağlamı «Cari ve tahsilat» verisine dayanıyor; bu veri rolünüzde yok.", 403)
    schema = st["schema"]
    warnings: list[str] = []
    out: dict[str, Any] = {"asOf": now.isoformat(), "query": {"email": bool(email), "phone": bool(phone), "order": order,
                                                                "account": account, "code": code},
                           "match": {"contacts": [], "webusers": [], "accounts": []}, "needsChoice": False,
                           "orders": [], "shipments": [], "cargo": [], "invoices": [], "tickets": [],
                           "hidden": [], "warnings": warnings, "logo": None}
    acc_ids: list[str] = []
    webusers: list[str] = []
    order_rows: list[dict[str, Any]] = []

    def crm_read(run: src.Run) -> None:
        if order:
            order_rows.extend(run(src.crm_orders_sql(schema, order_no=order)))
            acc_ids.extend(a for a in (guid(r.get("account_id")) for r in order_rows) if a)
            webusers.extend(w for w in (guid(r.get("webuser_id")) for r in order_rows) if w)
        if email or phone:
            cs = run(src.crm_contacts_sql(schema, email=email, phone=phone))
            out["match"]["contacts"] = [{"id": guid(c.get("contact_id")), "ad": text(c.get("ad")),
                                         "accountId": guid(c.get("account_id")) if int(num(c.get("account_type"))) == 1 else None,
                                         "cariKodu": text(c.get("cari_kodu"))} for c in cs]
            acc_ids.extend(c["accountId"] for c in out["match"]["contacts"] if c["accountId"])
        if email:
            ws = run(src.crm_webusers_sql(schema, email))
            out["match"]["webusers"] = [{"id": guid(w.get("webuser_id")),
                                         "ad": " ".join(x for x in (text(w.get("ad")), text(w.get("soyad"))) if x) or None,
                                         "accountId": guid(w.get("account_id"))} for w in ws]
            webusers.extend(w["id"] for w in out["match"]["webusers"] if w["id"])
            acc_ids.extend(w["accountId"] for w in out["match"]["webusers"] if w["accountId"])
        ids = sorted({a for a in ([account] if account else []) + acc_ids if a})
        accs = run(src.crm_accounts_sql(schema, ids=ids, code=code, email=email if not account else None,
                                        phone=phone if not account else None)) if (ids or code or email or phone) else []
        out["match"]["accounts"] = [_account(a) for a in accs]

    source.crm(crm_read)
    cands = out["match"]["accounts"]
    if account:
        chosen = [a for a in cands if a["id"] == src.guid_or_none(account)]
        if not chosen:
            raise SupportError("Seçilen cari bulunamadı ya da etkin değil.", 404)
    elif len(cands) > 1 and not order:
        out["needsChoice"] = True
        return out
    else:
        chosen = cands[:1] if not order else [a for a in cands if a["id"] in {guid(r.get("account_id")) for r in order_rows}][:1] or cands[:1]
    out["account"] = chosen[0] if chosen else None
    if not (out["account"] or order_rows or webusers):
        warnings.append("CRM'de bu bilgilerle eşleşen kişi ya da cari bulunamadı. Okur (e-ticaret) siparişlerinin çoğu "
                        "CRM'de değildir; site siparişi okuması sonraki sürümde.")
    if not _needs(domains, "satis"):
        out["hidden"].append("Sipariş, sevkiyat, kargo ve fatura «Satış ve sipariş» verisine dayanıyor; bu veri rolünüzde yok.")
        return out

    labels = source.status_labels(st)
    firms = source.cargo_firms(st)
    acc = out["account"]
    since = now - timedelta(days=st["orderDays"])

    def crm_orders(run: src.Run) -> None:
        rows = list(order_rows)
        if not order and (acc or webusers):
            rows = run(src.crm_orders_sql(schema, accounts=[acc["id"]] if acc else [], webusers=webusers, since=since))
        orders = [src.order_row(r, labels, firms) for r in rows]
        out["orders"] = orders
        ids = [o["id"] for o in orders if o["id"]]
        ships, tracks = [], []
        for part in chunks(ids):
            ships += run(src.crm_shipments_sql(schema, part))
            tracks += run(src.crm_tracking_sql(schema, part))
        out["shipments"] = [src.shipment_row(s) for s in ships]
        track_nos = {o["takipNo"] for o in orders if o["takipNo"]} | {text(t.get("takip_no")) for t in tracks if text(t.get("takip_no"))}
        irs_nos = {text(t.get("irsaliye_no")) for t in tracks if text(t.get("irsaliye_no"))} | \
                  {s["no"] for s in out["shipments"] if s["no"]}
        order_of: dict[str, set[str]] = {}
        for o in orders:
            if o["takipNo"]:
                order_of.setdefault(o["takipNo"], set()).add(o["id"])
        for t in tracks:
            for key in (text(t.get("takip_no")), text(t.get("irsaliye_no"))):
                if key:
                    order_of.setdefault(key, set()).add(guid(t.get("order_id")) or "")
        cargo = []
        tl = sorted(track_nos) if "takip" in st["cargoMatch"] else []
        il = sorted(irs_nos) if "irsaliye" in st["cargoMatch"] else []
        for i in range(0, max(len(tl), len(il)), 400):
            if tl[i:i + 400] or il[i:i + 400]:
                cargo += run(src.crm_cargo_info_sql(schema, tl[i:i + 400], il[i:i + 400]))
        rows_c = []
        for c in cargo:
            row = src.cargo_row(c)
            row["orderIds"] = sorted({x for k in (row["takipNo"], row["irsaliyeNo"]) if k for x in order_of.get(k, set()) if x})
            rows_c.append(row)
        out["cargo"] = rows_c
        out["tracking"] = [{"orderId": guid(t.get("order_id")), "takipNo": text(t.get("takip_no")),
                            "irsaliyeNo": text(t.get("irsaliye_no")), "tarih": day(t.get("olusturma"))} for t in tracks]

    source.crm(crm_orders)
    out["summary"] = {"orders": len(out["orders"]), "open": sum(1 for o in out["orders"] if o["acik"]),
                      "risk": sum(1 for o in out["orders"] if o["riskte"]),
                      "pending": sum(num(o["bekleyen"]) for o in out["orders"] if o["acik"])}

    # Logo: carinin son faturaları/iadeleri ve sevkiyattaki fatura numaraları (veri sonu tarihiyle).
    code_ = (acc or {}).get("cariKodu") or code
    fnos = sorted({s["faturaNo"] for s in out["shipments"] if s["faturaNo"]})
    if code_ or fnos:
        try:
            out["logo"], out["invoices"], by_no = _logo_part(source, st, now, code_, fnos)
            for s in out["shipments"]:
                if s["faturaNo"] in by_no:
                    s["logo"] = by_no[s["faturaNo"]]
        except Exception as e:  # noqa: BLE001 — Logo düşse de CRM bağlamı döner
            log.warning("support: Logo okunamadı: %s", e)
            warnings.append("Logo'ya şu an ulaşılamadı; fatura ve iade bu yanıtta yok.")
    if tickets and email:
        try:
            out["tickets"] = tickets(email)
        except Exception as e:  # noqa: BLE001
            log.info("support: önceki talepler okunamadı: %s", e)
            warnings.append("Destek masasındaki önceki talepler okunamadı.")
    return out


def _account(a: dict[str, Any]) -> dict[str, Any]:
    return {"id": guid(a.get("account_id")), "unvan": text(a.get("unvan")), "cariKodu": text(a.get("cari_kodu")),
            "kanal": src.CHANNEL.get(int(num(a.get("kanal"))))}


def _logo_part(source: Source, st: dict[str, Any], now: date, code: Optional[str],
               fnos: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    cal = source.logo_calendar(now)
    firms: dict[int, str] = {int(y): f for y, f in cal["firms"].items()}
    since = src.since_months(now, st["logoMonths"])
    years = [y for y in src.years_between(since, now) if y in firms]
    invoices: list[dict[str, Any]] = []
    by_no: dict[str, dict[str, Any]] = {}

    def read(run: src.Run) -> None:
        for y in years:
            if code:
                invoices.extend(src.invoice_row(r) for r in run(src.logo_invoices_sql(firms[y], code, since)))
        if fnos:
            for f in sorted({firms[y] for y in firms}):
                for part in chunks(fnos):
                    for r in run(src.logo_invoices_by_no_sql(f, part)):
                        row = src.invoice_row(r)
                        if row["no"] and row["no"] not in by_no:
                            by_no[row["no"]] = row

    source.logo(read)
    invoices.sort(key=lambda x: (x["tarih"] or "", x["no"] or ""), reverse=True)
    meta = {"dataEnd": cal.get("dataEnd"), "since": since.isoformat(), "firms": [firms[y] for y in years],
            "note": ("Logo verisi bu tarihe kadar; sonrası için «fatura kesilmedi» denemez." if cal.get("dataEnd") else None)}
    return meta, invoices, by_no


# ------------------------------------------------------------------ bayi görünümü


def dealer(source: Source, st: dict[str, Any], account: str, *, domains: Optional[frozenset[str]] = None,
           now: Optional[date] = None) -> dict[str, Any]:
    """Bayi adına tek bakış: açık siparişler (bekleyen adet), risk onayı bekleyenler, son sevkiyat ve kargo; Logo'da son
    faturalar ve yaklaşık bakiye. Rakamlar CRM/Logo'dan; model yok."""
    now = now or today()
    if not _needs(domains, "cari"):
        raise SupportError("Bayi görünümü «Cari ve tahsilat» verisine dayanıyor; bu veri rolünüzde yok.", 403)
    aid = src.guid_or_none(account)
    if not aid:
        raise SupportError("Cari kimliği geçersiz.", 422)
    ctx = context(source, st, account=aid, domains=domains, now=now)
    if ctx.get("hidden"):
        return {**ctx, "open": [], "risk": [], "recent": []}
    orders = ctx["orders"]
    open_ = [o for o in orders if o["acik"]]
    risk = [o for o in orders if o["riskte"]]
    recent_cut = (now - timedelta(days=30)).isoformat()
    recent = [o for o in orders if (o["sevkTarihi"] or "") >= recent_cut]
    ctx["open"], ctx["risk"], ctx["recent"] = open_, risk, recent
    ctx["dealerSummary"] = {"open": len(open_), "pending": sum(num(o["bekleyen"]) for o in open_), "risk": len(risk),
                            "riskAmount": sum(num(o["tutar"]) for o in risk), "shipped30": len(recent),
                            "oldestOpen": min((o["tarih"] for o in open_ if o["tarih"]), default=None)}
    code_ = (ctx.get("account") or {}).get("cariKodu")
    if code_:
        try:
            ctx["balance"] = _balance(source, now, code_)
        except Exception as e:  # noqa: BLE001
            log.info("support: bayi bakiyesi okunamadı: %s", e)
            ctx["warnings"].append("Logo bakiyesi okunamadı.")
    return ctx


def _balance(source: Source, now: date, code: str) -> Optional[dict[str, Any]]:
    """Yıl başından bakiye ve vadesi geçen (M30'un sertifikalı FIFO yaklaşımı, tek cari)."""
    from semantic_bridge import field_sales_sources as fsrc

    cal = source.logo_calendar(now)
    f = cal["firm"]

    def read(run: src.Run) -> Optional[dict[str, Any]]:
        cl = run(src.logo_client_sql(f, code))
        if not cl:
            return None
        ref = int(num(cl[0].get("ref")))
        prefix = re.sub(r"[^0-9A-Za-z.]", "", code)[:20] or "120"
        rows = run(fsrc.aging_sql(f, cal["year"], now, prefix, clientref=ref))
        if not rows:
            return {"bakiye": 0.0, "vadesiGecmis": 0.0, "year": cal["year"], "dataEnd": cal.get("dataEnd"), "approx": True}
        r = rows[0]
        over = sum(num(r.get(k)) for k in ("k_1_30", "k_31_60", "k_61_90", "k_90p"))
        return {"bakiye": round(num(r.get("bakiye")), 2), "vadesiGecmis": round(over, 2), "k90": round(num(r.get("k_90p")), 2),
                "year": cal["year"], "dataEnd": cal.get("dataEnd"), "approx": True}

    return source.logo(read)
