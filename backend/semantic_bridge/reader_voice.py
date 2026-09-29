"""Okur sesi sınıflayıcı (AI fırsatları öneri 15): site yorumları (M37), Trendyol soru ve yorumları, Trendyol iade
açıklamaları (M40) **tek ortak sınıflayıcıdan** geçer; konu kapalı kümeden seçilir.

**Konu kümesi (kapalı):** kargo / teslimat · baskı / cilt hatası · içerik · fiyat · övgü · diğer (`TOPICS`).

**Sıra (kayıt başına, gece BATCH):**
1. Metin boşsa `diger` (kural).
2. Trendyol iadesinde M40'ın kendi iade nedeni sınıfı varsa o sınıf konuya eşlenir (`CLAIM_MAP`; ikinci model çağrısı
   yok, aynı iadeye iki çelişen sınıf verilmez). İade nedeni «Diğer» ya da boşsa metin aşağıdaki adımlara gider.
3. Kural sözcükleri tek konuya düşerse o konu (kural; yalnız kargo, baskı ve fiyat — övgü/içerik sözcükle ayrılmaz).
4. Zeki AI `QueuedLlm.choose` + olasılık eşiği (`OKUR_SESI_MIN_OLASILIK`, `OKUR_SESI_MIN_FARK`). Eşik altı
   «emin-degil»: konu boş kalır, ekranda «Belirsiz».

Metin modele **maskeli** gider: M37'nin `okur.mask_text` (e-posta, telefon) ve M40'ın `platform_common.mask` (uzun
numara) birlikte uygulanır; yorumcu adı hiçbir kaynakta okunmaz. Site yorumu metni **saklanmaz** (M37 kuralı): tabloda
yalnız kayıt kimliği, ürün anahtarı, konu, olasılık ve metnin parmak izi (değişince yeniden sınıflamak için) durur.

**Baskı hatası kümesi:** son `OKUR_SESI_BASKI_GUN` günde aynı ürün anahtarında `OKUR_SESI_BASKI_ESIK` ve üstü «baskı /
cilt hatası» kaydı → üretime iç uyarı (`semantic_reader_voice_alerts`). Uyarı ekranda (okur sesi paneli, Kampüs «Bugün»
özeti üretim yetkisi olana) her zaman görünür; `OKUR_SESI_URETIM_ALICI` doluysa iç e-posta da gider (`ALERT_RECIPIENT_DOMAINS`
süzgeci), boşsa yalnız ekranda. Dışarıya hiçbir şey gönderilmez; kümeyi insan değerlendirir.

Ürün anahtarı: Logo stok kodu (Trendyol barkodu M42 eşlemesiyle, site ürünü SEO eşitlemesindeki T-soft ürün koduyla —
T-soft kodunun Logo stok koduna eşitliği **ölçülecek**); eşleşmeyen kayıt kendi kaynak anahtarıyla (`barkod:`, `tsoft:`)
ayrı sayılır.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.marketing.guard import fold

log = logging.getLogger("semantic.reader_voice")

_md = sa.MetaData()

LABELS = sa.Table(
    "semantic_reader_voice", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kaynak", sa.String(20), primary_key=True),              # site-yorum | trendyol-soru | trendyol-yorum | trendyol-iade
    sa.Column("kayit_id", sa.String(160), primary_key=True),
    sa.Column("urun_anahtar", sa.String(120), index=True),              # Logo stok kodu ya da barkod:/tsoft: anahtarı
    sa.Column("urun_adi", sa.String(400)),
    sa.Column("kayit_tarihi", sa.String(10)),                           # YYYY-MM-DD (kaynaktaki tarih; yoksa ilk görülme)
    sa.Column("konu", sa.String(12)),                                   # TOPICS anahtarı; emin-degil ise boş
    sa.Column("olasilik", sa.Float),
    sa.Column("yontem", sa.String(12), nullable=False),                 # kural | iade-nedeni | zeki | emin-degil
    sa.Column("parmak", sa.String(40), nullable=False),                 # maskeli metnin özeti (metin saklanmaz)
    sa.Column("siniflama", sa.DateTime(timezone=True), nullable=False),
)
ALERTS = sa.Table(
    "semantic_reader_voice_alerts", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("urun_anahtar", sa.String(120), primary_key=True),
    sa.Column("urun_adi", sa.String(400)),
    sa.Column("sayi", sa.Integer, nullable=False),                      # penceredeki baskı/cilt hatası kaydı
    sa.Column("kaynaklar_json", sa.Text),                               # kaynak → sayı
    sa.Column("ilk", sa.DateTime(timezone=True), nullable=False),
    sa.Column("guncelleme", sa.DateTime(timezone=True), nullable=False),
    sa.Column("durum", sa.String(10), nullable=False),                  # acik | goruldu | kapandi
    sa.Column("bildirim", sa.String(16)),                               # sent | alici_yok | failed | no_smtp
    sa.Column("bildirim_sayi", sa.Integer),                             # son bildirimdeki sayı (artınca yeniden)
    sa.Column("goren", sa.String(120)),
    sa.Column("gorulme", sa.DateTime(timezone=True)),
)
META = sa.Table(
    "semantic_reader_voice_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(80), primary_key=True),
    sa.Column("value_json", sa.Text),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

TOPICS: dict[str, str] = {
    "kargo": "Kargo / teslimat", "baski": "Baskı / cilt hatası", "icerik": "İçerik", "fiyat": "Fiyat", "ovgu": "Övgü",
    "diger": "Diğer",
}
SOURCES: dict[str, str] = {
    "site-yorum": "Site yorumu", "trendyol-soru": "Trendyol sorusu", "trendyol-yorum": "Trendyol yorumu",
    "trendyol-iade": "Trendyol iade açıklaması",
}
#: Kural sözcükleri (harf katlanmış). Yalnız tek konuya düşerse kullanılır; övgü ve içerik sözcükle ayrılmaz.
RULES: dict[str, tuple[str, ...]] = {
    "kargo": ("kargo", "teslimat", "teslim edilmedi", "gec geldi", "gec teslim", "paket hasar", "kurye", "ulasmadi",
              "siparisim gelmedi"),
    "baski": ("baski hata", "baski hatali", "sayfa eksik", "eksik sayfa", "bos sayfa", "sayfalar bos", "ters basil",
              "cilt hata", "cilt dagil", "sayfalar dagil", "sayfalar karis", "sayfa tekrar", "silik baski", "murekkep",
              "yapraklar dus", "sayfalar kopu", "sayfa yirtik geldi"),
    "fiyat": ("fiyat", "pahali", "ucuz", "indirim", "kampanya", "fiyatina gore"),
}
#: M40 iade nedeni sınıfı → konu. «Diğer» metne gider.
CLAIM_MAP: dict[str, str] = {
    "Geç teslim": "kargo", "Yanlış ürün": "kargo", "Hasarlı ürün": "kargo", "Baskı hatası": "baski", "Vazgeçti": "diger",
}
PROMPT = ("Bir yayınevine gelen okur metni aşağıda ({kaynak}). Metnin ana konusu hangisi? Kargo ya da teslimat sorunu, "
          "kitabın baskı/cilt kusuru (eksik, boş, ters basılmış sayfa, dağılan cilt), kitabın içeriği hakkında görüş ya da soru, "
          "fiyat, övgü ya da başka bir konu. Emin değilsen «Diğer» seç.\n\nKitap: {kitap}\nMetin (kişisel bilgi maskelendi): "
          "{metin}")

_ready: set[int] = set()
_lock = threading.Lock()


class VoiceError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def iso(v: Optional[datetime]) -> Optional[str]:
    v = _aware(v)
    return v.isoformat() if v else None


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    """Yönetim → admin.conf / env. Hepsi ölçülmemiş başlangıç değeridir (kör etiketleme örneğiyle ayarlanacak)."""
    def num(key: str, default: float, lo: float, hi: float) -> float:
        raw = (conf(key) or "").strip().replace(",", ".")
        try:
            return max(lo, min(hi, float(raw))) if raw else default
        except ValueError:
            return default

    return {
        "minProb": num("OKUR_SESI_MIN_OLASILIK", 0.60, 0.0, 1.0),
        "minMargin": num("OKUR_SESI_MIN_FARK", 0.20, 0.0, 1.0),
        "defectDays": int(num("OKUR_SESI_BASKI_GUN", 90, 1, 3650)),
        "defectMin": int(num("OKUR_SESI_BASKI_ESIK", 3, 1, 10_000)),
        "windowDays": int(num("OKUR_SESI_OZET_GUN", 90, 1, 3650)),
        "budgetSec": int(num("OKUR_SESI_MODEL_SURE_SN", 900, 10, 86_400)),
        "recipients": [x.strip() for x in (conf("OKUR_SESI_URETIM_ALICI") or "").replace(";", ",").split(",") if "@" in x],
    }


# ------------------------------------------------------------------ maske ve kural


def mask(text: Any) -> str:
    """İki modülün mevcut maskesi birlikte: M40 (e-posta, uzun numara) + M37 (e-posta, Türkiye telefonu)."""
    from semantic_bridge import okur as O
    from semantic_bridge.channels import platform_common as PC

    return O.mask_text(PC.mask(str(text or ""), 4000))


def fingerprint(text: str, extra: str = "") -> str:
    return hashlib.sha1(f"{extra}\n{fold(text)}".encode("utf-8")).hexdigest()


def rule_topic(text: str) -> Optional[str]:
    f = fold(text)
    hits = [k for k, ws in RULES.items() if any(w in f for w in ws)]
    return hits[0] if len(hits) == 1 else None


def day_of(v: Any) -> Optional[str]:
    """Kaynaktaki tarih → YYYY-MM-DD. «16.08.2026», ISO, datetime kabul edilir; okunamazsa None."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")[:26]).date().isoformat()
    except ValueError:
        pass
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:19], fmt).date().isoformat()
        except ValueError:
            continue
    return None


# ------------------------------------------------------------------ sınıflama


def classify(engine: sa.engine.Engine, tenant: str, items: Iterable[dict[str, Any]], llm: Any, st: dict[str, Any], *,
             force: bool = False, clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """`items`: {kaynak, id, anahtar, ad, tarih, metin, iadeSinifi?}. Metni (parmak izi) değişmemiş kayıt yeniden
    sınıflanmaz; süre dolarsa kalan sonraki gece sürer (sessiz tavan yok, `kalan` raporlanır)."""
    ensure(engine)
    t0 = clock()
    out: dict[str, Any] = {"kural": 0, "iadeNedeni": 0, "zeki": 0, "eminDegil": 0, "degismedi": 0, "kalan": 0, "atlandi": None}
    with engine.connect() as c:
        known = {(r.kaynak, r.kayit_id): r.parmak for r in c.execute(
            sa.select(LABELS.c.kaynak, LABELS.c.kayit_id, LABELS.c.parmak).where(LABELS.c.tenant_id == tenant))}
    for it in items:
        src = str(it.get("kaynak") or "")
        if src not in SOURCES:
            continue
        rid = str(it.get("id") or "")[:160]
        if not rid:
            continue
        text = mask(it.get("metin"))
        claim = str(it.get("iadeSinifi") or "")
        fp = fingerprint(text, claim)
        if not force and known.get((src, rid)) == fp:
            out["degismedi"] += 1
            continue
        vals: dict[str, Any]
        mapped = CLAIM_MAP.get(claim) if src == "trendyol-iade" else None
        rule = rule_topic(text) if text.strip() else None
        if mapped:
            vals = {"konu": mapped, "olasilik": None, "yontem": "iade-nedeni"}
            out["iadeNedeni"] += 1
        elif not text.strip():
            vals = {"konu": "diger", "olasilik": None, "yontem": "kural"}
            out["kural"] += 1
        elif rule:
            vals = {"konu": rule, "olasilik": None, "yontem": "kural"}
            out["kural"] += 1
        elif llm is None or not hasattr(llm, "choose"):
            out["atlandi"] = "model tanımlı değil"
            out["kalan"] += 1
            continue
        elif clock() - t0 > st["budgetSec"]:
            out["kalan"] += 1
            continue
        else:
            prompt = PROMPT.format(kaynak=SOURCES[src], kitap=str(it.get("ad") or "—")[:200], metin=text[:1500])
            try:
                ch = llm.choose(prompt, list(TOPICS.values()))
            except Exception as e:  # noqa: BLE001 — model düştüyse kalan sonraki geceye
                log.warning("okur sesi: sınıf alınamadı: %s", e)
                out["atlandi"] = "model cevap vermedi"
                out["kalan"] += 1
                continue
            key = next((k for k, v in TOPICS.items() if v == ch.choice), None)
            if key and ch.confident(st["minProb"], min_margin=st["minMargin"]):
                vals = {"konu": key, "olasilik": ch.probability, "yontem": "zeki"}
                out["zeki"] += 1
            else:
                vals = {"konu": None, "olasilik": ch.probability, "yontem": "emin-degil"}
                out["eminDegil"] += 1
        row = {"tenant_id": tenant, "kaynak": src, "kayit_id": rid, "urun_anahtar": str(it.get("anahtar") or "")[:120] or None,
               "urun_adi": str(it.get("ad") or "")[:400] or None, "kayit_tarihi": day_of(it.get("tarih")) or now().date().isoformat(),
               "parmak": fp, "siniflama": now(), **vals}
        with engine.begin() as c:
            c.execute(LABELS.delete().where(LABELS.c.tenant_id == tenant, LABELS.c.kaynak == src, LABELS.c.kayit_id == rid))
            c.execute(LABELS.insert().values(**row))
    return out


def labels_stmt(tenant: str, kaynak: str):
    return sa.select(LABELS).where(LABELS.c.tenant_id == tenant, LABELS.c.kaynak == kaynak)


def summary_since(st: dict[str, Any], today: Optional[date] = None) -> str:
    return ((today or now().date()) - timedelta(days=st["windowDays"])).isoformat()


def summary_stmt(tenant: str, since: str):
    """Pencere içindeki etiketlerin kaynak × konu sayısı."""
    return sa.select(LABELS.c.kaynak, LABELS.c.konu, sa.func.count().label("sayi")).where(
        LABELS.c.tenant_id == tenant, LABELS.c.kayit_tarihi >= since).group_by(LABELS.c.kaynak, LABELS.c.konu)


def clusters_stmt(tenant: str, since: str):
    """Pencere içinde ürün anahtarı olan «baskı / cilt hatası» etiketleri."""
    return sa.select(LABELS.c.urun_anahtar, LABELS.c.urun_adi, LABELS.c.kaynak).where(
        LABELS.c.tenant_id == tenant, LABELS.c.konu == "baski", LABELS.c.kayit_tarihi >= since,
        LABELS.c.urun_anahtar.isnot(None))


def alerts_stmt(tenant: str, open_only: bool = False):
    q = sa.select(ALERTS).where(ALERTS.c.tenant_id == tenant)
    return q.where(ALERTS.c.durum == "acik") if open_only else q


def meta_stmt(tenant: str, key: str):
    return sa.select(META).where(META.c.tenant_id == tenant, META.c.key == key)


def labels(engine: sa.engine.Engine, tenant: str, kaynak: str) -> dict[str, dict[str, Any]]:
    """Kayıt kimliği → konu (ekrandaki çip)."""
    ensure(engine)
    if kaynak not in SOURCES:
        raise VoiceError("Bilinmeyen kaynak.")
    with engine.connect() as c:
        rows = c.execute(labels_stmt(tenant, kaynak)).all()
    return {r.kayit_id: {"konu": r.konu, "konuAdi": TOPICS.get(r.konu or "", "Belirsiz"), "olasilik": r.olasilik,
                         "yontem": r.yontem} for r in rows}


# ------------------------------------------------------------------ özet ve baskı hatası kümesi


def summary(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], today: Optional[date] = None) -> dict[str, Any]:
    """Son `windowDays` gün: kaynak × konu sayıları (belirsiz ayrı). Rakam SQL'den; model yok."""
    ensure(engine)
    today = today or now().date()
    since = summary_since(st, today)
    with engine.connect() as c:
        rows = c.execute(summary_stmt(tenant, since)).all()
    table: dict[str, dict[str, int]] = {s: {**{k: 0 for k in TOPICS}, "belirsiz": 0} for s in SOURCES}
    for src, konu, n in rows:
        if src in table:
            table[src][konu or "belirsiz"] = table[src].get(konu or "belirsiz", 0) + int(n)
    total = {k: sum(v[k] for v in table.values()) for k in (*TOPICS, "belirsiz")}
    return {"bas": since, "bit": today.isoformat(), "gun": st["windowDays"], "kaynakKonu": table, "toplam": total,
            "konular": TOPICS, "kaynakAdlari": SOURCES}


def clusters(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], today: Optional[date] = None) -> list[dict[str, Any]]:
    """Aynı ürün anahtarında pencere içinde eşik ve üstü baskı/cilt hatası kaydı."""
    ensure(engine)
    today = today or now().date()
    since = (today - timedelta(days=st["defectDays"])).isoformat()
    with engine.connect() as c:
        rows = c.execute(clusters_stmt(tenant, since)).all()
    by: dict[str, dict[str, Any]] = {}
    for key, name, src in rows:
        b = by.setdefault(key, {"anahtar": key, "ad": None, "sayi": 0, "kaynaklar": defaultdict(int)})
        b["ad"] = b["ad"] or name
        b["sayi"] += 1
        b["kaynaklar"][src] += 1
    out = [{**b, "kaynaklar": dict(b["kaynaklar"])} for b in by.values() if b["sayi"] >= st["defectMin"]]
    out.sort(key=lambda x: (-x["sayi"], x["anahtar"]))
    return out


def sync_alerts(engine: sa.engine.Engine, tenant: str, found: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Kümeleri uyarı tablosuna yansıtır: yeni → açık; sayısı artan «görüldü»/«kapandı» uyarı yeniden açılır; eşiğin
    altına inen açık uyarı kendiliğinden kapanır (kayıt silinmez)."""
    import json

    ensure(engine)
    t = now()
    res: dict[str, list[str]] = {"yeni": [], "artan": [], "kapanan": []}
    seen = {f["anahtar"] for f in found}
    with engine.begin() as c:
        cur = {r.urun_anahtar: r for r in c.execute(sa.select(ALERTS).where(ALERTS.c.tenant_id == tenant))}
        for f in found:
            k = f["anahtar"]
            vals = {"urun_adi": f.get("ad"), "sayi": f["sayi"], "kaynaklar_json": json.dumps(f["kaynaklar"], ensure_ascii=False),
                    "guncelleme": t}
            r = cur.get(k)
            if r is None:
                c.execute(ALERTS.insert().values(tenant_id=tenant, urun_anahtar=k, ilk=t, durum="acik", **vals))
                res["yeni"].append(k)
            else:
                if f["sayi"] > int(r.sayi or 0) and r.durum != "acik":
                    vals.update(durum="acik", goren=None, gorulme=None)
                    res["artan"].append(k)
                elif f["sayi"] > int(r.sayi or 0):
                    res["artan"].append(k)
                c.execute(ALERTS.update().where(ALERTS.c.tenant_id == tenant, ALERTS.c.urun_anahtar == k).values(**vals))
        for k, r in cur.items():
            if k not in seen and r.durum != "kapandi":
                c.execute(ALERTS.update().where(ALERTS.c.tenant_id == tenant, ALERTS.c.urun_anahtar == k)
                          .values(durum="kapandi", guncelleme=t))
                res["kapanan"].append(k)
    return res


def _alert(r: Any) -> dict[str, Any]:
    import json

    try:
        srcs = json.loads(r.kaynaklar_json or "{}")
    except ValueError:
        srcs = {}
    return {"anahtar": r.urun_anahtar, "ad": r.urun_adi, "sayi": r.sayi, "kaynaklar": srcs, "ilk": iso(r.ilk),
            "guncelleme": iso(r.guncelleme), "durum": r.durum, "bildirim": r.bildirim, "bildirimSayi": r.bildirim_sayi,
            "goren": r.goren, "gorulme": iso(r.gorulme)}


def alerts(engine: sa.engine.Engine, tenant: str, *, open_only: bool = False) -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(alerts_stmt(tenant, open_only)).all()
    order = {"acik": 0, "goruldu": 1, "kapandi": 2}
    return sorted((_alert(r) for r in rows), key=lambda a: (order.get(a["durum"], 3), -int(a["sayi"] or 0), a["anahtar"]))


def mark_seen(engine: sa.engine.Engine, tenant: str, user: str, key: str) -> dict[str, Any]:
    ensure(engine)
    with engine.begin() as c:
        r = c.execute(sa.select(ALERTS).where(ALERTS.c.tenant_id == tenant, ALERTS.c.urun_anahtar == key)).first()
        if r is None:
            raise VoiceError("Uyarı bulunamadı.", 404)
        if r.durum == "acik":
            c.execute(ALERTS.update().where(ALERTS.c.tenant_id == tenant, ALERTS.c.urun_anahtar == key)
                      .values(durum="goruldu", goren=user, gorulme=now()))
        r = c.execute(sa.select(ALERTS).where(ALERTS.c.tenant_id == tenant, ALERTS.c.urun_anahtar == key)).first()
    return _alert(r)


def due_notifications(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    """Bildirilmemiş ya da son bildirimden sonra sayısı artmış açık uyarılar."""
    return [a for a in alerts(engine, tenant, open_only=True) if a["bildirimSayi"] is None or a["sayi"] > a["bildirimSayi"]]


def notify_text(items: list[dict[str, Any]], st: dict[str, Any], link: str = "") -> str:
    """İç e-posta metni (kural; rakamlar tablodan)."""
    lines = ["Okur sesi · baskı / cilt hatası kümesi (iç uyarı)", "",
             f"Son {st['defectDays']} günde aynı kitap için en az {st['defectMin']} okur metni baskı ya da cilt kusurundan söz ediyor:", ""]
    for a in items:
        src = ", ".join(f"{SOURCES.get(k, k)} {v}" for k, v in sorted(a["kaynaklar"].items()))
        lines.append(f"• {a['ad'] or a['anahtar']} ({a['anahtar']}): {a['sayi']} kayıt — {src}")
    lines += ["", "Konu kuralla ya da Zeki AI ile sınıflandı; kümeyi baskı/üretim sorumlusu değerlendirir."]
    if link:
        lines += ["", f"Ekran: {link}"]
    lines.append("Bu ileti yalnız iç alıcılara gider; okura ya da matbaaya hiçbir şey gönderilmez.")
    return "\n".join(lines)


def record_notification(engine: sa.engine.Engine, tenant: str, items: list[dict[str, Any]], status: str) -> None:
    with engine.begin() as c:
        for a in items:
            vals: dict[str, Any] = {"bildirim": status}
            if status == "sent":
                vals["bildirim_sayi"] = a["sayi"]
            c.execute(ALERTS.update().where(ALERTS.c.tenant_id == tenant, ALERTS.c.urun_anahtar == a["anahtar"]).values(**vals))


# ------------------------------------------------------------------ meta


def meta_get(engine: sa.engine.Engine, tenant: str, key: str) -> dict[str, Any]:
    import json

    ensure(engine)
    with engine.connect() as c:
        r = c.execute(meta_stmt(tenant, key)).first()
    if r is None:
        return {}
    try:
        return {**json.loads(r.value_json or "{}"), "_at": iso(r.updated_at)}
    except ValueError:
        return {}


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: dict[str, Any]) -> None:
    import json

    ensure(engine)
    with engine.begin() as c:
        c.execute(META.delete().where(META.c.tenant_id == tenant, META.c.key == key))
        c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=json.dumps(value, ensure_ascii=False, default=str),
                                       updated_at=now()))


# ------------------------------------------------------------------ kaynaklar (yalnız okuma)


def trendyol_items(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    """M40 tablolarındaki (panel dosyasından gelen, zaten maskeli) soru, yorum ve iade satırları."""
    from semantic_bridge.channels import trendyol as T

    T.ensure(engine)
    b = T.Books(engine, tenant)
    out: list[dict[str, Any]] = []

    def key(barkod: Optional[str], code: Optional[str]) -> Optional[str]:
        return code or (f"barkod:{barkod}" if barkod else None)

    for r in T._rows(engine, T.QUESTIONS, tenant):
        code = b.code(r.barkod)
        out.append({"kaynak": "trendyol-soru", "id": r.soru_id, "anahtar": key(r.barkod, code), "ad": b.name(code, r.urun_adi),
                    "tarih": r.soru_tarihi, "metin": r.metin_maskeli})
    for r in T._rows(engine, T.REVIEWS, tenant):
        code = b.code(r.barkod)
        out.append({"kaynak": "trendyol-yorum", "id": r.yorum_id, "anahtar": key(r.barkod, code), "ad": b.name(code, r.urun_adi),
                    "tarih": r.tarih, "metin": r.metin_maskeli})
    for r in T._rows(engine, T.CLAIMS, tenant):
        code = b.code(r.barkod)
        out.append({"kaynak": "trendyol-iade", "id": f"{r.talep_id}:{r.barkod}", "anahtar": key(r.barkod, code),
                    "ad": b.name(code), "tarih": r.tarih,
                    "metin": " ".join(x for x in (r.neden_metni, r.aciklama_maskeli) if x), "iadeSinifi": r.neden_sinifi})
    return out


def site_items(engine: sa.engine.Engine, tenant: str, comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """M37 site yorumları (anlık okuma; metin bellekte kalır, tabloya yazılmaz). Ürün kodu ve adı SEO eşitlemesinden."""
    ids = sorted({str(c.get("productId")) for c in comments if c.get("productId")})
    prods: dict[str, tuple[Optional[str], Optional[str]]] = {}
    if ids:
        try:
            from semantic_bridge.seo_geo.store import PRODUCTS

            with engine.connect() as c:
                for i in range(0, len(ids), 500):
                    part = ids[i:i + 500]
                    for pid, code, name in c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.code, PRODUCTS.c.name)
                                                     .where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.product_id.in_(part))):
                        prods[str(pid)] = (code, name)
        except Exception as e:  # noqa: BLE001 — SEO deposu yoksa anahtar tsoft: kalır
            log.warning("okur sesi: ürün kodları okunamadı: %s", e)
    out = []
    for cm in comments:
        pid = str(cm.get("productId") or "")
        code, name = prods.get(pid, (None, None))
        text = " ".join(x for x in (cm.get("baslik"), cm.get("metin")) if x)
        out.append({"kaynak": "site-yorum", "id": cm.get("id"), "anahtar": (code or (f"tsoft:{pid}" if pid else None)),
                    "ad": name or cm.get("urun"), "tarih": cm.get("tarih"), "metin": text})
    return out
