"""M19 Pazarlama görsel ve metin üretimi — talep kuyruğu, varlık arşivi, iki aşamalı onay, marka kiti, yasaklı kalıp.

Portalın kendi kayıtları (CRM'e, Logo'ya, T-soft'a yazılmaz; dış kanala hiçbir şey gönderilmez — onaylı paket indirilir,
kişi kendisi yükler):

- **Talep** (`semantic_mkt_creative_requests`, kimlik `MC-<yıl>-<sıra>`): kitap (Logo/CRM stok kodu), kanal, biçimler,
  metin türleri, brief, termin, isteyen/atanan, durum. Plan bağı M15 pazarlama çekirdeğinin kayıtlarıdır: `plan_id`
  = `semantic_mkt_plans.id`, `materyal_id` = `semantic_mkt_materials.id` (verilirse kayıt var mı, materyal o plana mı
  ait diye denetlenir); `kampanya` serbest addır. Onaylı M15 planındaki görsel/metin materyali (sosyal, kapak brief'i,
  video senaryosu, influencer brief'i, e-bülten konu satırı) `open_from_material()` ile talebe dönüşür — ekrandan tek
  tıkla ya da zamanlayıcıyla kendiliğinden (`pending_materials`); aynı materyale ve plan revizyonundaki kopyasına ikinci
  talep açılmaz. Bu modül M15 tablolarını yalnız okur (plan geçmişine «içerik talebi açıldı» olayı yazılır).
- Tabloların hepsi `semantic_mkt_creative_*` önekindedir (M15 `semantic_mkt_*` tablolarıyla çakışmaz).
- **Varlık** (`semantic_mkt_creative_assets`): görsel (stüdyonun dizdiği PNG, arşivde kopyası) ya da metin (Zeki AI varyantı ya
  da elle). Sürümlüdür: düzeltme yeni satır açar (`surum`+1, `onceki_id`), eskisi `guncel=False` kalır. Onay iki
  aşamalıdır: görselde önce tasarım (`icerik.tasarim-onay`), sonra mesaj (`icerik.mesaj-onay`); metinde yalnız mesaj.
  Aynı kişi aynı varlıkta iki onayı birden veremez. Arşivde «onaylı» = `mesaj_onay` dolu, güncel, reddedilmemiş.
- Model üretimi resim içeren görsel de onaylanınca yayına hazırdır (görsel modelin ticari lisansı 2026-09-29'da alındı;
  eski `taslak_lisans` kolonu tabloda kalır, hep False yazılır, okunmaz).
- **Marka kiti** (`semantic_mkt_creative_brand`, sürümlü) ve **yasaklı kalıp** listesi (`semantic_mkt_creative_banned`).
- **İş** (`semantic_mkt_creative_jobs`): arka plan üretimleri (görsel dizimi, metin varyantları) ve durumu.

Metin denetimleri modelsizdir (kod): platform karakter sınırı, yasaklı kalıp, alıntının kaynakta birebir geçmesi,
kaynakta olmayan sayı, influencer brief'inde reklam işareti. Kanıtsız üstünlük iddiası sınıflaması (evet/hayır +
olasılık) API katmanında LLM kapısından yapılır ve buraya sonuç olarak yazılır.
"""
from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

_md = sa.MetaData()

REQUESTS = sa.Table(
    "semantic_mkt_creative_requests", _md,
    sa.Column("id", sa.String(24), primary_key=True),                      # MC-2026-0001
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("plan_id", sa.String(64), index=True),                        # M15 semantic_mkt_plans.id
    sa.Column("materyal_id", sa.String(64), index=True),                    # M15 semantic_mkt_materials.id
    sa.Column("materyal_tur", sa.String(24)),                               # M15 materyal türü (revizyon kopyası için)
    sa.Column("kampanya", sa.String(200)),                                  # serbest kampanya adı
    sa.Column("stok_kodu", sa.String(40), nullable=False, index=True),
    sa.Column("kitap_id", sa.String(40)),                                   # CRM new_kitapId
    sa.Column("kitap_adi", sa.String(300)),
    sa.Column("yazar", sa.String(300)),
    sa.Column("studio_job", sa.String(40)),
    sa.Column("studio_kind", sa.String(12)),                                # kitap | pazarlama
    sa.Column("kapak_json", sa.Text),                                       # yüklenen kapak / kaynak bilgisi
    sa.Column("kanal", sa.String(20), nullable=False),
    sa.Column("formatlar", sa.Text, nullable=False),                        # json liste
    sa.Column("metin_turleri", sa.Text, nullable=False),                    # json liste
    sa.Column("brief", sa.Text),
    sa.Column("hedef_kitle", sa.String(300)),
    sa.Column("ton", sa.String(200)),
    sa.Column("gorsel_basligi", sa.String(300)),                            # görsel üstü yazı (A varyantı)
    sa.Column("termin", sa.Date),
    sa.Column("durum", sa.String(20), nullable=False),
    sa.Column("isteyen", sa.String(120), nullable=False),
    sa.Column("isteyen_ad", sa.String(200)),
    sa.Column("atanan", sa.String(120)),
    sa.Column("etiketler", sa.Text),                                        # json liste (sezon, kampanya)
    sa.Column("not_metni", sa.Text),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
    sa.Column("guncelleme", sa.DateTime(timezone=True), nullable=False),
)
ASSETS = sa.Table(
    "semantic_mkt_creative_assets", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("request_id", sa.String(24), nullable=False, index=True),
    sa.Column("stok_kodu", sa.String(40), nullable=False, index=True),
    sa.Column("tur", sa.String(8), nullable=False),                         # gorsel | metin
    sa.Column("kanal", sa.String(20)),
    sa.Column("format", sa.String(40)),                                     # görsel: biçim anahtarı; metin: platform
    sa.Column("metin_turu", sa.String(30)),
    sa.Column("varyant", sa.String(4), nullable=False),
    sa.Column("dosya_yolu", sa.String(500)),
    sa.Column("studio_ref", sa.String(80)),                                 # <iş>/<sid>
    sa.Column("metin", sa.Text),
    sa.Column("kaynak", sa.String(24), nullable=False),                     # studio-kit | studio-marketing-job | zeki | elle
    sa.Column("taslak_lisans", sa.Boolean, nullable=False, default=False),  # eski lisans işareti: hep False, okunmaz
    sa.Column("dogrulama_json", sa.Text),
    sa.Column("ayar_json", sa.Text),                                        # görselin dizim ayarı (yeniden dizim için)
    sa.Column("genislik", sa.Integer),
    sa.Column("yukseklik", sa.Integer),
    sa.Column("sha256", sa.String(64)),
    sa.Column("surum", sa.Integer, nullable=False, default=1),
    sa.Column("onceki_id", sa.String(32)),
    sa.Column("guncel", sa.Boolean, nullable=False, default=True),
    sa.Column("tasarim_onaylayan", sa.String(120)),
    sa.Column("tasarim_onay", sa.DateTime(timezone=True)),
    sa.Column("mesaj_onaylayan", sa.String(120)),
    sa.Column("mesaj_onay", sa.DateTime(timezone=True)),
    sa.Column("red_eden", sa.String(120)),
    sa.Column("red_zaman", sa.DateTime(timezone=True)),
    sa.Column("red_notu", sa.Text),
    sa.Column("etiketler", sa.Text),
    sa.Column("kullanildi_json", sa.Text),                                  # M21/M22 bildirirse (kanal, tarih)
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
)
BRAND = sa.Table(
    "semantic_mkt_creative_brand", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("surum", sa.Integer, primary_key=True),
    sa.Column("palet_json", sa.Text),
    sa.Column("logo_dosyalari", sa.Text),                                   # json [{id, ad, dosya, tur}]
    sa.Column("yazi_tipleri_json", sa.Text),                                # json [{id, ad, dosya, lisans}]
    sa.Column("kurallar_metni", sa.Text),
    sa.Column("yukleyen", sa.String(120), nullable=False),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
)
BANNED = sa.Table(
    "semantic_mkt_creative_banned", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("kalip", sa.String(200), nullable=False),
    sa.Column("aciklama", sa.String(400)),
    sa.Column("ekleyen", sa.String(120), nullable=False),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
)
META = sa.Table(
    "semantic_mkt_creative_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("anahtar", sa.String(60), primary_key=True),
    sa.Column("deger", sa.Text),
)
JOBS = sa.Table(
    "semantic_mkt_creative_jobs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("request_id", sa.String(24), nullable=False, index=True),
    sa.Column("tur", sa.String(10), nullable=False),                        # gorsel | metin
    sa.Column("durum", sa.String(10), nullable=False),                      # suruyor | bitti | hata
    sa.Column("ilerleme_json", sa.Text),
    sa.Column("sonuc_json", sa.Text),
    sa.Column("hata", sa.Text),
    sa.Column("surec", sa.String(32)),                                      # hangi köprü süreci koşuyor
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("baslangic", sa.DateTime(timezone=True), nullable=False),
    sa.Column("bitis", sa.DateTime(timezone=True)),
)

CHANNELS = {"instagram": "Instagram", "facebook": "Facebook", "x": "X", "linkedin": "LinkedIn", "tiktok": "TikTok",
            "youtube": "YouTube", "google-ads": "Google reklamı", "meta-ads": "Meta reklamı", "site": "Web sitesi",
            "e-bulten": "E-bülten", "diger": "Diğer"}
TEXT_KINDS = {"baslik": "Başlık", "aciklama": "Açıklama", "reklam-metni": "Reklam metni",
              "video-senaryosu": "Video senaryosu", "influencer-brief": "Influencer brief'i", "hashtag": "Hashtag"}
#: Biçim anahtarı → ad (stüdyonun `marketing.TEMPLATES`'i ile aynı anahtarlar; ölçüler stüdyoda).
FORMATS = {"kare": "Kare 1080×1080", "dikey": "Dikey 1080×1920", "yatay": "Yatay 1200×628",
           "dikey-gonderi": "Dikey gönderi 1080×1350", "kare-1200": "Kare 1200×1200",
           "banner-300x250": "Reklam kutusu 300×250", "banner-728x90": "Yatay reklam 728×90",
           "banner-160x600": "Dikey reklam 160×600", "banner-320x50": "Mobil reklam 320×50",
           "site-bandi": "Site bandı 1920×600", "e-bulten": "E-bülten başlığı 600×200"}
#: Kanala göre önerilen biçimler (talep formunda ön seçim; kişi değiştirir).
CHANNEL_FORMATS = {"instagram": ["kare", "dikey-gonderi", "dikey"], "facebook": ["kare", "yatay"],
                   "x": ["yatay"], "linkedin": ["yatay", "kare-1200"], "tiktok": ["dikey"], "youtube": ["yatay"],
                   "google-ads": ["banner-300x250", "banner-728x90", "banner-160x600", "banner-320x50"],
                   "meta-ads": ["kare", "dikey"], "site": ["site-bandi"], "e-bulten": ["e-bulten"], "diger": ["kare"]}
#: Platform karakter sınırları: {platform: {metin türü: (sınır, önerilen)}}. Varsayım (platformların yayımladığı
#: sınırlar, 2026); kurulum `MKT_CREATIVE_LIMITS_JSON` ile değiştirir. Sınırı aşan varyant üretilmez.
LIMITS: dict[str, dict[str, tuple[Optional[int], Optional[int]]]] = {
    "instagram": {"aciklama": (2200, 125), "baslik": (125, None)},
    "facebook": {"aciklama": (63206, 125), "baslik": (125, None)},
    "x": {"aciklama": (280, None), "baslik": (280, None)},
    "linkedin": {"aciklama": (3000, 150), "baslik": (200, None)},
    "tiktok": {"aciklama": (2200, 150), "baslik": (100, None)},
    "youtube": {"baslik": (100, 70), "aciklama": (5000, 157)},
    "google-ads": {"baslik": (30, None), "reklam-metni": (90, None), "aciklama": (90, None)},
    "meta-ads": {"baslik": (40, 27), "reklam-metni": (125, None), "aciklama": (30, None)},
    "site": {"baslik": (60, None), "aciklama": (160, None)},
    "e-bulten": {"baslik": (60, 45), "aciklama": (100, None)},
}
HASHTAG_MAX = {"instagram": 30, "tiktok": 10, "x": 3, "linkedin": 5, "facebook": 5, "youtube": 15}
STATES = {"talep": "Talep", "uretimde": "Üretimde", "tasarim-onayi": "Tasarım onayı", "mesaj-onayi": "Mesaj onayı",
          "onayli": "Onaylı", "reddedildi": "Reddedildi", "arsiv": "Arşiv"}
MANUAL_STATES = {"reddedildi", "arsiv"}
#: Başlangıç yasaklı kalıp listesi (kanıtsız üstünlük iddiası). Ekrandan yönetilir; ilk açılışta bir kez yazılır.
DEFAULT_BANNED = [
    ("en çok satan", "Satış sırası kanıtı (Logo) olmadan kullanılmaz."),
    ("en çok okunan", "Kanıtsız üstünlük iddiası."),
    ("türkiye'nin en", "Kanıtsız üstünlük iddiası."),
    ("dünyanın en", "Kanıtsız üstünlük iddiası."),
    ("bir numaralı", "Kanıtsız üstünlük iddiası."),
    ("1 numaralı", "Kanıtsız üstünlük iddiası."),
    ("rakipsiz", "Kanıtsız üstünlük iddiası."),
    ("en iyi kitap", "Kanıtsız üstünlük iddiası."),
    ("mutlaka okumanız gereken tek", "Kanıtsız mutlak ifade."),
    ("garantili", "Sonuç vaadi."),
]
PAGE_SIZE = 60
_ID = re.compile(r"^[0-9a-f]{32}$")
_RID = re.compile(r"^MC-[0-9]{4}-[0-9]{4,}$")
_STOCK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,39}$")
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ready: set[int] = set()
_lock = threading.Lock()
PROCESS = uuid.uuid4().hex                      # bu köprü süreci; başka süreçte «sürüyor» kalan iş yarıda kalmıştır


class CreativeError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    return v.isoformat() if isinstance(v, date) else str(v)


def _loads(v: Any, default: Any) -> Any:
    if not v:
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


def _dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def assets_dir() -> Path:
    """Onaylı ve taslak görsellerin kalıcı kopyası (köprü kullanıcısına yazılabilir olmalı)."""
    return Path(os.environ.get("MARKETING_ASSETS_DIR", "/data/nanobaseai/bi/var/marketing-assets"))


def limits(conf: Optional[Callable[[str], str]] = None) -> dict[str, dict[str, tuple[Optional[int], Optional[int]]]]:
    out = {k: dict(v) for k, v in LIMITS.items()}
    raw = (conf("MKT_CREATIVE_LIMITS_JSON") if conf else os.environ.get("MKT_CREATIVE_LIMITS_JSON", "")) or ""
    if raw.strip():
        try:
            for plat, kinds in json.loads(raw).items():
                for kind, v in kinds.items():
                    lim = v if isinstance(v, list) else [v, None]
                    out.setdefault(plat, {})[kind] = (int(lim[0]) if lim[0] else None,
                                                      int(lim[1]) if len(lim) > 1 and lim[1] else None)
        except (ValueError, TypeError, AttributeError, IndexError):
            pass
    return out


# ------------------------------------------------------------------ metin denetimleri (modelsiz)
def tr_fold(s: str) -> str:
    """Türkçe harf duyarsız karşılaştırma: İ→i, I→ı, sonra casefold; tırnak/tire birliği; boşluk tekleşir."""
    s = (s or "").replace("İ", "i").replace("I", "ı")
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("«", '"').replace("»", '"')
    s = s.replace("…", "...")
    s = re.sub(r"[–—]", "-", s)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip().casefold()


def clean_quote(q: str) -> str:
    q = re.sub(r"\s+", " ", q or "").strip()
    q = re.sub(r"^[-–—]\s*", "", q)
    return q.strip("\"'“”«»‘’ ").strip()


def in_source(quote: str, source_norm: str) -> bool:
    """Alıntı kaynakta birebir geçiyor mu (stüdyonun `marketing.in_book` normalleştirmesiyle aynı kural)."""
    q = tr_fold(clean_quote(quote))
    return len(q) >= 3 and q in source_norm


QUOTE_RX = re.compile(r"[“«\"]([^”»\"]{12,})[”»\"]")


def quotes_in(text: str) -> list[str]:
    return [clean_quote(m.group(1)) for m in QUOTE_RX.finditer(text or "")]


def hashtags(text: str) -> list[str]:
    """Metindeki etiketler; CRM `new_hastag` alanı virgül, boşluk ya da satırla ayrılmış olabilir."""
    out: list[str] = []
    for raw in re.split(r"[\s,;]+", text or ""):
        t = raw.strip().strip(".")
        if not t:
            continue
        t = "#" + t.lstrip("#")
        if re.fullmatch(r"#[0-9A-Za-zÇĞİÖŞÜçğıöşüÂÎÛâîû_]{2,60}", t) and tr_fold(t) not in {tr_fold(x) for x in out}:
            out.append(t)
    return out


def banned_hits(text: str, phrases: Iterable[str]) -> list[str]:
    t = tr_fold(text)
    hits = []
    for p in phrases:
        f = tr_fold(p)
        if not f:
            continue
        if f.startswith("re:"):
            try:
                if re.search(f[3:], t):
                    hits.append(p)
            except re.error:
                continue
        elif f in t:
            hits.append(p)
    return hits




def check_text(text: str, platform: str, kind: str, *, source_texts: Iterable[str], banned: Iterable[str],
               lim: Optional[dict] = None, claim: Optional[dict] = None) -> dict[str, Any]:
    """Bir metin varyantının denetimi. `durum`: tamam | uyari | hata. Hata (onay verilemez): platform sınırı aşımı,
    kaynakta birebir geçmeyen alıntı. Uyarı (onaycı karar verir): yasaklı kalıp, kanıtsız üstünlük iddiası (model),
    kaynakta olmayan sayı, reklam işareti olmayan influencer brief'i, önerilen uzunluğu aşan metin."""
    lim = lim if lim is not None else limits()
    body = text or ""
    n = len(body)
    hard, soft = (lim.get(platform) or {}).get(kind, (None, None))
    src = [s for s in source_texts if s]
    src_norm = tr_fold("\n".join(src))
    quotes = [{"metin": q, "bulundu": in_source(q, src_norm)} for q in quotes_in(body)]
    hits = banned_hits(body, banned)
    # Tek sayı denetçisi (`zeki_text`): kaynak metinlerde karşılığı olmayan sayılar, yazıldığı gibi.
    from semantic_bridge import zeki_text as Z

    foreign = [] if kind == "hashtag" else sorted(Z.unsupported(body, src))
    issues: list[dict[str, str]] = []
    if hard is not None and n > hard:
        issues.append({"seviye": "hata", "kod": "sinir", "mesaj": f"{n} karakter; bu platformda sınır {hard}."})
    elif soft is not None and n > soft:
        issues.append({"seviye": "uyari", "kod": "onerilen", "mesaj": f"{n} karakter; önerilen en çok {soft} (ilk "
                       "satırda kesilebilir)."})
    for q in quotes:
        if not q["bulundu"]:
            issues.append({"seviye": "hata", "kod": "alinti", "mesaj": f"Alıntı kaynakta birebir geçmiyor: “{q['metin'][:80]}”"})
    for h in hits:
        issues.append({"seviye": "uyari", "kod": "yasakli", "mesaj": f"Yasaklı kalıp: «{h}»"})
    if foreign:
        issues.append({"seviye": "uyari", "kod": "sayi", "mesaj": "Kaynakta olmayan sayı: " + ", ".join(foreign[:10])})
    if kind == "influencer-brief" and not re.search(r"reklam|iş\s*birliği|işbirliği", tr_fold(body)):
        issues.append({"seviye": "uyari", "kod": "reklam-isareti",
                       "mesaj": "İşbirliği içeriğinde reklam olduğunun belirtilmesi istenmeli (#reklam / #işbirliği)."})
    if kind == "hashtag":
        cap = HASHTAG_MAX.get(platform)
        tags = hashtags(body)
        if cap and len(tags) > cap:
            issues.append({"seviye": "hata", "kod": "sinir", "mesaj": f"{len(tags)} etiket; bu platformda en çok {cap}."})
    if claim and claim.get("karar") == "evet" and claim.get("emin"):
        issues.append({"seviye": "uyari", "kod": "iddia", "mesaj": "Kanıtsız üstünlük iddiası olabilir (Zeki AI)."})
    level = "hata" if any(i["seviye"] == "hata" for i in issues) else "uyari" if issues else "tamam"
    return {"karakter": n, "kelime": len(body.split()), "sinir": hard, "onerilen": soft, "alintilar": quotes,
            "yasakli": hits, "sayilar": foreign, "iddia": claim, "sorunlar": issues, "durum": level}


# ------------------------------------------------------------------ doğrulama yardımcıları
def _rid(v: Any) -> str:
    s = str(v or "").strip()
    if not _RID.match(s):
        raise CreativeError("Talep bulunamadı.", 404)
    return s


def _aid(v: Any) -> str:
    s = str(v or "").strip()
    if not _ID.match(s):
        raise CreativeError("Varlık bulunamadı.", 404)
    return s


def _stock(v: Any) -> str:
    s = str(v or "").strip()
    if not _STOCK.match(s):
        raise CreativeError("Stok kodu geçerli değil.")
    return s


def _day(v: Any, label: str) -> Optional[date]:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise CreativeError(f"{label} YYYY-AA-GG biçiminde olmalı.") from None


def _short(v: Any, n: int) -> Optional[str]:
    s = re.sub(r"\s+", " ", str(v or "")).strip()
    return s[:n] or None


def _list(v: Any, allowed: dict[str, str], label: str) -> list[str]:
    if v in (None, ""):
        return []
    if not isinstance(v, list):
        raise CreativeError(f"{label} liste olmalı.")
    out = []
    for x in v:
        x = str(x)
        if x not in allowed:
            raise CreativeError(f"Bilinmeyen {label.lower()}: {x}")
        if x not in out:
            out.append(x)
    return out


def _tags(v: Any) -> list[str]:
    if v in (None, ""):
        return []
    items = v if isinstance(v, list) else str(v).split(",")
    out: list[str] = []
    for x in items:
        t = _short(x, 80)
        if t and t not in out:
            out.append(t)
    return out


# ------------------------------------------------------------------ talepler
def _next_id(conn, tenant: str, year: int) -> str:
    rows = conn.execute(sa.select(REQUESTS.c.id).where(REQUESTS.c.tenant_id == tenant,
                                                       REQUESTS.c.id.like(f"MC-{year}-%"))).scalars().all()
    top = max((int(r.rsplit("-", 1)[1]) for r in rows if r.rsplit("-", 1)[1].isdigit()), default=0)
    return f"MC-{year}-{top + 1:04d}"


def create_request(engine, tenant: str, user: str, display: Optional[str], body: dict[str, Any],
                   book: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Elle ya da plandan talep. `book`: CRM'den okunan kitap (ad, yazar, kitap_id); yoksa gövdedeki ad kullanılır."""
    stok = _stock(body.get("stokKodu") or body.get("stok_kodu"))
    kanal = str(body.get("kanal") or "")
    if kanal not in CHANNELS:
        raise CreativeError("Kanal seçin.")
    formats = _list(body.get("formatlar"), {**FORMATS, **{k: k for k in _extra_formats()}}, "Biçim")
    kinds = _list(body.get("metinTurleri") or body.get("metin_turleri"), TEXT_KINDS, "Metin türü")
    if not formats and not kinds:
        formats = list(CHANNEL_FORMATS.get(kanal, ["kare"]))
    title = (book or {}).get("ad") or _short(body.get("kitapAdi"), 300)
    if not title:
        raise CreativeError("Kitap bulunamadı; stok kodunu kontrol edin.", 404)
    now = _now()
    plan_id, mat_id, mat_tur = m15_link(engine, tenant, body.get("planId"), body.get("materyalId"))
    row = {"tenant_id": tenant, "plan_id": plan_id, "materyal_id": mat_id, "materyal_tur": mat_tur,
           "kampanya": _short(body.get("kampanya"), 200), "stok_kodu": stok, "kitap_id": (book or {}).get("kitap_id"),
           "kitap_adi": title[:300], "yazar": ((book or {}).get("yazar") or _short(body.get("yazar"), 300) or None),
           "studio_job": None, "studio_kind": None, "kapak_json": None, "kanal": kanal, "formatlar": _dumps(formats),
           "metin_turleri": _dumps(kinds), "brief": (str(body.get("brief") or "").strip()[:8000] or None),
           "hedef_kitle": _short(body.get("hedefKitle"), 300), "ton": _short(body.get("ton"), 200),
           "gorsel_basligi": _short(body.get("gorselBasligi"), 300), "termin": _day(body.get("termin"), "Termin"),
           "durum": "talep", "isteyen": user, "isteyen_ad": _short(display, 200), "atanan": _short(body.get("atanan"), 120),
           "etiketler": _dumps(_tags(body.get("etiketler"))), "not_metni": None, "olusturma": now, "guncelleme": now}
    job = str(body.get("studioJob") or "").strip()
    if job:
        if not re.fullmatch(r"[0-9]{14}[0-9a-f]{6}", job):
            raise CreativeError("Stüdyo işi geçerli değil.")
        row.update(studio_job=job, studio_kind="kitap")
    year = now.astimezone(timezone(timedelta(hours=3))).year
    for _ in range(20):                    # iki kişi aynı anda açarsa sıra çakışır: yeniden dene
        try:
            with engine.begin() as c:
                rid = _next_id(c, tenant, year)
                c.execute(REQUESTS.insert().values(id=rid, **row))
            return get_request(engine, tenant, rid)
        except sa.exc.IntegrityError:
            continue
    raise CreativeError("Talep numarası alınamadı; yeniden deneyin.", 409)


def _extra_formats() -> list[str]:
    raw = os.environ.get("EDITOR_MARKETING_EXTRA_FORMATS", "").strip()
    try:
        return [k for k in json.loads(raw)] if raw else []
    except (ValueError, TypeError):
        return []


# ------------------------------------------------------------------ M15 plan bağı
#: M15 materyal türü → M19 talebi (kanal, görsel biçimleri, metin türleri). Föy, arka kapak ve basın bülteni M15'in
#: kendi metin materyalleridir (görsel/metin üretimi istemez); talep açmaz.
MATERIAL_MAP: dict[str, dict[str, Any]] = {
    "sosyal": {"kanal": "instagram", "formatlar": ["kare", "dikey-gonderi", "dikey"], "metin": ["aciklama", "hashtag"]},
    "kapak-brief": {"kanal": "diger", "formatlar": ["kare", "dikey", "yatay"], "metin": []},
    "video-senaryo": {"kanal": "youtube", "formatlar": [], "metin": ["video-senaryosu"]},
    "influencer-brief": {"kanal": "instagram", "formatlar": [], "metin": ["influencer-brief"]},
    "e-bulten-konu": {"kanal": "e-bulten", "formatlar": ["e-bulten"], "metin": ["baslik"]},
}


def _m15():
    from semantic_bridge.marketing import core as mcore
    return mcore


def m15_link(engine, tenant: str, plan_id: Any, materyal_id: Any) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Talebin M15 bağı: kimlikler M15 kaydı olmalı; materyal verildiyse planı materyalden gelir (ikisi çelişemez).
    Dönen: (plan_id, materyal_id, materyal_tur)."""
    pid, mid = _short(plan_id, 64), _short(materyal_id, 64)
    if not pid and not mid:
        return None, None, None
    mc = _m15()
    mc.ensure(engine)
    if mid:
        try:
            mat, plan = mc.material_row(engine, tenant, mid)
        except mc.MarketingError:
            raise CreativeError("Pazarlama planında bu materyal yok.", 404) from None
        if pid and pid != plan["id"]:
            raise CreativeError("Materyal bu plana ait değil.")
        return plan["id"], mat["id"], mat["tur"]
    with engine.connect() as c:
        ok = c.execute(sa.select(mc.PLANS.c.id).where(mc.PLANS.c.tenant_id == tenant, mc.PLANS.c.id == pid)).scalar()
    if not ok:
        raise CreativeError("Pazarlama planı bulunamadı.", 404)
    return pid, None, None


def _material_due(c, mc, plan: dict[str, Any], mat: dict[str, Any]) -> Optional[str]:
    """Materyalin termini: takvimde bu materyale (yoksa bu türe) bağlı en erken iş, yoksa planın yayın günü."""
    for cond in (mc.TASKS.c.materyal_id == mat["id"], mc.TASKS.c.materyal_tur == mat["tur"]):
        d = c.execute(sa.select(sa.func.min(mc.TASKS.c.tarih)).where(mc.TASKS.c.plan_id == plan["id"], cond,
                                                                        mc.TASKS.c.tarih.is_not(None))).scalar()
        if d:
            return str(d)[:10]
    return (plan.get("yayinTarihi") or None) and str(plan["yayinTarihi"])[:10]


def _already(c, tenant: str, plan: dict[str, Any], mat: dict[str, Any]) -> Optional[str]:
    """Bu materyal (ya da plan revizyonundan önceki sürümdeki aynı türü) için açılmış talep."""
    old = c.execute(sa.select(REQUESTS.c.id).where(REQUESTS.c.tenant_id == tenant, REQUESTS.c.materyal_id == mat["id"])).scalar()
    if old or not plan.get("oncekiId"):
        return old
    return c.execute(sa.select(REQUESTS.c.id).where(REQUESTS.c.tenant_id == tenant, REQUESTS.c.plan_id == plan["oncekiId"],
                                                    REQUESTS.c.materyal_tur == mat["tur"])).scalar()


def open_from_material(engine, tenant: str, user: str, material_id: str,
                       book: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """M15 kancası: plandaki görsel/metin materyalinden talep. Brief materyalin metni, termin takvimden, kampanya planın
    adı. Aynı materyal (ya da revizyondaki kopyası) için ikinci talep açılmaz; varsa o döner. `book`: CRM kitap kartı
    (ad, yazar, kitap_id); yoksa planın başlığı kitap adı olur."""
    mc = _m15()
    mc.ensure(engine)
    try:
        mat, plan = mc.material_row(engine, tenant, str(material_id or ""))
    except mc.MarketingError:
        raise CreativeError("Pazarlama planında bu materyal yok.", 404) from None
    spec = MATERIAL_MAP.get(mat["tur"])
    if spec is None:
        raise CreativeError(f"«{mat['turAdi']}» görsel/metin talebi açmaz; pazarlama planında yazılır.")
    stok = mat.get("stokKodu") or plan.get("stokKodu")
    if not stok:
        raise CreativeError("Planın kitabı (stok kodu) yok; talep açılamaz.")
    with engine.connect() as c:
        old = _already(c, tenant, plan, mat)
        due = _material_due(c, mc, plan, mat)
    if old:
        return get_request(engine, tenant, old)
    brief = f"{mat['turAdi']} — «{plan['baslik']}» pazarlama planı ({plan['id']}).\n\n{mat.get('metin') or ''}"
    body = {"stokKodu": stok, "kanal": spec["kanal"], "formatlar": spec["formatlar"], "metinTurleri": spec["metin"],
            "brief": brief[:8000], "termin": due, "kampanya": plan["baslik"], "planId": plan["id"], "materyalId": mat["id"],
            "kitapAdi": plan["baslik"]}
    out = create_request(engine, tenant, user, None, body, book)
    try:                                    # plan geçmişinde görünsün (M15 olay kaydı; plan değişmez)
        with engine.begin() as c:
            mc.event(c, plan["id"], user, "icerik-talebi", None, {"talep": out["id"], "materyal": mat["id"], "tur": mat["tur"]})
    except Exception:  # noqa: BLE001 — olay kaydı yan bilgidir
        pass
    return out


def pending_stmt(tenant: str):
    """Onaylı planların görsel/metin materyalleri (aynı ifade sorgu bilgisinde gösterilir)."""
    mc = _m15()
    return (sa.select(mc.MATERIALS, mc.PLANS.c.baslik, mc.PLANS.c.onceki_id, mc.PLANS.c.yayin_tarihi,
                      mc.PLANS.c.stok_kodu.label("plan_stok"))
            .join(mc.PLANS, mc.PLANS.c.id == mc.MATERIALS.c.plan_id)
            .where(mc.PLANS.c.tenant_id == tenant, mc.PLANS.c.durum == "onayli", mc.MATERIALS.c.tur.in_(list(MATERIAL_MAP))))


def pending_materials(engine, tenant: str) -> list[dict[str, Any]]:
    """Onaylı M15 planlarında henüz talebe dönüşmemiş görsel/metin materyalleri (termine göre)."""
    mc = _m15()
    mc.ensure(engine)
    out = []
    with engine.connect() as c:
        rows = c.execute(pending_stmt(tenant)).mappings().all()
        for r in rows:
            plan = {"id": r["plan_id"], "baslik": r["baslik"], "oncekiId": r["onceki_id"], "yayinTarihi": r["yayin_tarihi"]}
            mat = {"id": r["id"], "tur": r["tur"]}
            if _already(c, tenant, plan, mat):
                continue
            out.append({"materyalId": r["id"], "planId": r["plan_id"], "planAdi": r["baslik"], "tur": r["tur"],
                        "turAdi": mc.MATERIALS_KINDS.get(r["tur"], (r["tur"], None))[0],
                        "stokKodu": r["stok_kodu"] or r["plan_stok"], "termin": _material_due(c, mc, plan, mat),
                        "metin": (r["metin"] or "")[:300], "kanal": MATERIAL_MAP[r["tur"]]["kanal"]})
    out.sort(key=lambda x: (x["termin"] or "9999", x["planId"]))
    return out


def _request_view(r: dict[str, Any], counts: Optional[dict[str, int]] = None) -> dict[str, Any]:
    return {"id": r["id"], "planId": r["plan_id"], "materyalId": r["materyal_id"], "materyalTur": r["materyal_tur"],
            "kampanya": r["kampanya"],
            "stokKodu": r["stok_kodu"], "kitapId": r["kitap_id"], "kitapAdi": r["kitap_adi"], "yazar": r["yazar"],
            "studioJob": r["studio_job"], "studioKind": r["studio_kind"], "kapak": _loads(r["kapak_json"], None),
            "kanal": r["kanal"], "kanalAdi": CHANNELS.get(r["kanal"], r["kanal"]),
            "formatlar": _loads(r["formatlar"], []), "metinTurleri": _loads(r["metin_turleri"], []),
            "brief": r["brief"], "hedefKitle": r["hedef_kitle"], "ton": r["ton"], "gorselBasligi": r["gorsel_basligi"],
            "termin": _iso(r["termin"]), "durum": r["durum"], "durumAdi": STATES.get(r["durum"], r["durum"]),
            "isteyen": r["isteyen"], "isteyenAd": r["isteyen_ad"], "atanan": r["atanan"],
            "etiketler": _loads(r["etiketler"], []), "not": r["not_metni"],
            "olusturma": _iso(r["olusturma"]), "guncelleme": _iso(r["guncelleme"]), "sayilar": counts or {}}


def counts_stmt(tenant: str, ids: list[str]):
    """Taleplerin güncel varlıkları: görsel / metin, onaylı, bekleyen, reddedilen sayısı buradan."""
    return (sa.select(ASSETS.c.request_id, ASSETS.c.tur, ASSETS.c.tasarim_onay, ASSETS.c.mesaj_onay,
                      ASSETS.c.red_zaman)
            .where(ASSETS.c.tenant_id == tenant, ASSETS.c.request_id.in_(ids), ASSETS.c.guncel.is_(True)))


def _counts(conn, tenant: str, ids: list[str]) -> dict[str, dict[str, int]]:
    if not ids:
        return {}
    rows = conn.execute(counts_stmt(tenant, ids)).mappings().all()
    out: dict[str, dict[str, int]] = {}
    for a in rows:
        c = out.setdefault(a["request_id"], {"gorsel": 0, "metin": 0, "onayli": 0, "bekleyen": 0, "reddedilen": 0})
        c[a["tur"]] += 1
        if a["red_zaman"] is not None:
            c["reddedilen"] += 1
        elif a["mesaj_onay"] is not None:
            c["onayli"] += 1
        else:
            c["bekleyen"] += 1
    return out


def requests_stmt(tenant: str, *, durum: str = "", kanal: str = "", stok: str = "", atanan: str = "", q: str = ""):
    """Talep listesinin süzgeçli okuması (sayfa ve sıra `list_requests`'te eklenir)."""
    st = sa.select(REQUESTS).where(REQUESTS.c.tenant_id == tenant)
    if durum:
        st = st.where(REQUESTS.c.durum.in_([d for d in durum.split(",") if d in STATES]))
    if kanal:
        st = st.where(REQUESTS.c.kanal == kanal)
    if stok:
        st = st.where(REQUESTS.c.stok_kodu == stok)
    if atanan:
        st = st.where(REQUESTS.c.atanan == atanan)
    if q.strip():
        like = f"%{q.strip()}%"
        st = st.where(sa.or_(REQUESTS.c.kitap_adi.ilike(like), REQUESTS.c.stok_kodu.ilike(like),
                             REQUESTS.c.kampanya.ilike(like), REQUESTS.c.id.ilike(like)))
    return st


def requests_page_stmt(st: Any, page: int):
    return (st.order_by(REQUESTS.c.termin.is_(None), REQUESTS.c.termin, REQUESTS.c.olusturma.desc())
            .offset(max(0, int(page)) * PAGE_SIZE).limit(PAGE_SIZE))


def list_requests(engine, tenant: str, *, durum: str = "", kanal: str = "", stok: str = "", atanan: str = "",
                  q: str = "", page: int = 0) -> dict[str, Any]:
    st = requests_stmt(tenant, durum=durum, kanal=kanal, stok=stok, atanan=atanan, q=q)
    page = max(0, int(page))
    with engine.connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(st.subquery())).scalar() or 0
        rows = c.execute(requests_page_stmt(st, page)).mappings().all()
        counts = _counts(c, tenant, [r["id"] for r in rows])
    return {"items": [_request_view(dict(r), counts.get(r["id"])) for r in rows], "total": int(total), "page": page,
            "pageSize": PAGE_SIZE}


def request_stmt(tenant: str, rid: str):
    return sa.select(REQUESTS).where(REQUESTS.c.tenant_id == tenant, REQUESTS.c.id == rid)


def _row(conn, tenant: str, rid: str) -> dict[str, Any]:
    r = conn.execute(request_stmt(tenant, rid)).mappings().first()
    if r is None:
        raise CreativeError("Talep bulunamadı.", 404)
    return dict(r)


def get_request(engine, tenant: str, rid: str) -> dict[str, Any]:
    rid = _rid(rid)
    with engine.connect() as c:
        r = _row(c, tenant, rid)
        counts = _counts(c, tenant, [rid])
    return _request_view(r, counts.get(rid))


PATCHABLE = {"kanal", "formatlar", "metinTurleri", "brief", "hedefKitle", "ton", "gorselBasligi", "termin", "atanan",
             "etiketler", "kampanya", "planId", "materyalId", "durum", "not", "studioJob"}


def update_request(engine, tenant: str, rid: str, body: dict[str, Any]) -> dict[str, Any]:
    rid = _rid(rid)
    unknown = set(body) - PATCHABLE
    if unknown:
        raise CreativeError("Değiştirilemeyen alan: " + ", ".join(sorted(unknown)))
    vals: dict[str, Any] = {}
    if "kanal" in body:
        if body["kanal"] not in CHANNELS:
            raise CreativeError("Kanal seçin.")
        vals["kanal"] = body["kanal"]
    if "formatlar" in body:
        vals["formatlar"] = _dumps(_list(body["formatlar"], {**FORMATS, **{k: k for k in _extra_formats()}}, "Biçim"))
    if "metinTurleri" in body:
        vals["metin_turleri"] = _dumps(_list(body["metinTurleri"], TEXT_KINDS, "Metin türü"))
    for k, col, n in (("hedefKitle", "hedef_kitle", 300), ("ton", "ton", 200), ("gorselBasligi", "gorsel_basligi", 300),
                      ("atanan", "atanan", 120), ("kampanya", "kampanya", 200)):
        if k in body:
            vals[col] = _short(body[k], n)
    if "planId" in body or "materyalId" in body:
        pid, mid, mtur = m15_link(engine, tenant, body.get("planId"), body.get("materyalId"))
        vals.update(plan_id=pid, materyal_id=mid, materyal_tur=mtur)
    if "brief" in body:
        vals["brief"] = str(body["brief"] or "").strip()[:8000] or None
    if "not" in body:
        vals["not_metni"] = str(body["not"] or "").strip()[:4000] or None
    if "termin" in body:
        vals["termin"] = _day(body["termin"], "Termin")
    if "etiketler" in body:
        vals["etiketler"] = _dumps(_tags(body["etiketler"]))
    if "studioJob" in body:
        job = str(body["studioJob"] or "").strip()
        if job and not re.fullmatch(r"[0-9]{14}[0-9a-f]{6}", job):
            raise CreativeError("Stüdyo işi geçerli değil.")
        vals.update(studio_job=job or None, studio_kind="kitap" if job else None)
    with engine.begin() as c:
        cur = _row(c, tenant, rid)
        if "durum" in body:
            d = str(body["durum"] or "")
            if d in MANUAL_STATES:
                vals["durum"] = d
            elif d == "yeniden" and cur["durum"] in MANUAL_STATES:
                vals["durum"] = "talep"                      # arşivden/retten geri: durum varlıklardan yeniden hesaplanır
            else:
                raise CreativeError("Durum yalnız «reddedildi», «arsiv» ya da «yeniden» yapılabilir; diğerleri onaydan gelir.")
        if vals:
            c.execute(REQUESTS.update().where(REQUESTS.c.tenant_id == tenant, REQUESTS.c.id == rid)
                      .values(**vals, guncelleme=_now()))
        if vals.get("durum") == "talep":
            _refresh_status(c, tenant, rid)
    return get_request(engine, tenant, rid)


def set_studio(engine, tenant: str, rid: str, job: str, kind: str, cover: Optional[dict] = None) -> None:
    vals: dict[str, Any] = {"studio_job": job, "studio_kind": kind, "guncelleme": _now()}
    if cover is not None:
        vals["kapak_json"] = _dumps(cover)
    with engine.begin() as c:
        c.execute(REQUESTS.update().where(REQUESTS.c.tenant_id == tenant, REQUESTS.c.id == _rid(rid)).values(**vals))


def set_cover(engine, tenant: str, rid: str, cover: Optional[dict]) -> None:
    with engine.begin() as c:
        c.execute(REQUESTS.update().where(REQUESTS.c.tenant_id == tenant, REQUESTS.c.id == _rid(rid))
                  .values(kapak_json=_dumps(cover) if cover else None, guncelleme=_now()))


def _refresh_status(conn, tenant: str, rid: str) -> str:
    """Talep durumu varlıklardan: elle verilen «reddedildi/arşiv» korunur. Güncel ve reddedilmemiş varlık yoksa
    talep/üretimde kalır; tasarım onayı eksik görsel varsa «tasarım onayı», mesaj onayı eksik varsa «mesaj onayı»,
    hepsi onaylıysa «onaylı»."""
    cur = _row(conn, tenant, rid)
    if cur["durum"] in MANUAL_STATES:
        return cur["durum"]
    rows = conn.execute(sa.select(ASSETS.c.tur, ASSETS.c.tasarim_onay, ASSETS.c.mesaj_onay)
                        .where(ASSETS.c.tenant_id == tenant, ASSETS.c.request_id == rid, ASSETS.c.guncel.is_(True),
                               ASSETS.c.red_zaman.is_(None))).mappings().all()
    running = conn.execute(sa.select(sa.func.count()).select_from(JOBS).where(
        JOBS.c.tenant_id == tenant, JOBS.c.request_id == rid, JOBS.c.durum == "suruyor")).scalar() or 0
    if not rows:
        new = "uretimde" if running or cur["durum"] == "uretimde" else "talep"
    elif any(r["tur"] == "gorsel" and r["tasarim_onay"] is None for r in rows):
        new = "tasarim-onayi"
    elif any(r["mesaj_onay"] is None for r in rows):
        new = "mesaj-onayi"
    else:
        new = "onayli"
    if new != cur["durum"]:
        conn.execute(REQUESTS.update().where(REQUESTS.c.tenant_id == tenant, REQUESTS.c.id == rid)
                     .values(durum=new, guncelleme=_now()))
    return new


def refresh_status(engine, tenant: str, rid: str) -> str:
    with engine.begin() as c:
        return _refresh_status(c, tenant, _rid(rid))


def mark_producing(engine, tenant: str, rid: str) -> None:
    with engine.begin() as c:
        cur = _row(c, tenant, rid)
        if cur["durum"] == "talep":
            c.execute(REQUESTS.update().where(REQUESTS.c.tenant_id == tenant, REQUESTS.c.id == rid)
                      .values(durum="uretimde", guncelleme=_now()))


# ------------------------------------------------------------------ varlıklar
def _slug(s: str) -> str:
    s = (s or "").replace("İ", "i").replace("I", "ı").casefold()
    s = s.translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "kitap"


def file_name(a: dict[str, Any], title: Optional[str]) -> str:
    """İndirilen ad: `kitap-adi_bicim_1080x1080_A_v2.png` (metinde `…_platform_tur_A_v1.txt`)."""
    if a["tur"] == "gorsel":
        fmt = re.sub(r"-\d+x\d+$", "", a.get("format") or "gorsel")
        return f"{_slug(title or '')}_{fmt}_{a.get('genislik')}x{a.get('yukseklik')}_{a['varyant']}_v{a['surum']}.png"
    return f"{_slug(title or '')}_{a.get('format') or 'metin'}_{a.get('metinTuru') or 'metin'}_{a['varyant']}_v{a['surum']}.txt"


def _asset_view(a: dict[str, Any], title: Optional[str] = None) -> dict[str, Any]:
    approved = a["mesaj_onay"] is not None and a["red_zaman"] is None and bool(a["guncel"])
    v = {"id": a["id"], "requestId": a["request_id"], "stokKodu": a["stok_kodu"], "tur": a["tur"], "kanal": a["kanal"],
         "format": a["format"], "formatAdi": FORMATS.get(a["format"] or "", a["format"]) if a["tur"] == "gorsel"
         else CHANNELS.get(a["format"] or "", a["format"]), "metinTuru": a["metin_turu"],
         "metinTuruAdi": TEXT_KINDS.get(a["metin_turu"] or "", a["metin_turu"]), "varyant": a["varyant"],
         "metin": a["metin"], "kaynak": a["kaynak"],
         "dogrulama": _loads(a["dogrulama_json"], None), "ayar": _loads(a["ayar_json"], None),
         "genislik": a["genislik"], "yukseklik": a["yukseklik"], "sha256": a["sha256"], "surum": a["surum"],
         "oncekiId": a["onceki_id"], "guncel": bool(a["guncel"]), "studioRef": a["studio_ref"],
         "tasarimOnay": {"by": a["tasarim_onaylayan"], "at": _iso(a["tasarim_onay"])} if a["tasarim_onay"] else None,
         "mesajOnay": {"by": a["mesaj_onaylayan"], "at": _iso(a["mesaj_onay"])} if a["mesaj_onay"] else None,
         "red": {"by": a["red_eden"], "at": _iso(a["red_zaman"]), "not": a["red_notu"]} if a["red_zaman"] else None,
         "etiketler": _loads(a["etiketler"], []), "kullanildi": _loads(a["kullanildi_json"], []),
         "olusturan": a["olusturan"], "olusturma": _iso(a["olusturma"]), "onayli": approved,
         "yayinaHazir": approved}
    v["dosyaAdi"] = file_name(v, title)
    return v


def add_asset(engine, tenant: str, user: str, rid: str, *, tur: str, varyant: str, kaynak: str,
              fmt: Optional[str] = None, metin_turu: Optional[str] = None, metin: Optional[str] = None,
              dosya: Optional[bytes] = None, studio_ref: Optional[str] = None,
              dogrulama: Optional[dict] = None, ayar: Optional[dict] = None, size: Optional[tuple[int, int]] = None,
              onceki: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Yeni varlık (ya da `onceki`nin yeni sürümü). Görsel dosyası `assets_dir()/<id>.png` olarak saklanır."""
    import hashlib
    rid = _rid(rid)
    aid = uuid.uuid4().hex
    path = None
    sha = None
    if dosya is not None:
        d = assets_dir()
        try:
            d.mkdir(parents=True, exist_ok=True)
            path = d / f"{aid}.png"
            path.write_bytes(dosya)
        except OSError as e:
            raise CreativeError("Görsel arşive yazılamadı (MARKETING_ASSETS_DIR köprü kullanıcısına açık olmalı).", 503) from e
        sha = hashlib.sha256(dosya).hexdigest()
    with engine.begin() as c:
        req = _row(c, tenant, rid)
        if onceki is not None:
            c.execute(ASSETS.update().where(ASSETS.c.tenant_id == tenant, ASSETS.c.id == onceki["id"])
                      .values(guncel=False))
        c.execute(ASSETS.insert().values(
            id=aid, tenant_id=tenant, request_id=rid, stok_kodu=req["stok_kodu"], tur=tur, kanal=req["kanal"],
            format=fmt, metin_turu=metin_turu, varyant=varyant, dosya_yolu=str(path) if path else None,
            studio_ref=studio_ref, metin=metin, kaynak=kaynak, taslak_lisans=False,
            dogrulama_json=_dumps(dogrulama) if dogrulama is not None else None,
            ayar_json=_dumps(ayar) if ayar is not None else None, genislik=size[0] if size else None,
            yukseklik=size[1] if size else None, sha256=sha, surum=(onceki["surum"] + 1) if onceki else 1,
            onceki_id=onceki["id"] if onceki else None, guncel=True,
            etiketler=_dumps(_loads(req["etiketler"], []) + ([req["kampanya"]] if req["kampanya"] else [])),
            olusturan=user, olusturma=_now()))
        _refresh_status(c, tenant, rid)
        a = c.execute(sa.select(ASSETS).where(ASSETS.c.id == aid)).mappings().first()
    return _asset_view(dict(a), req["kitap_adi"])


def next_variant(engine, tenant: str, rid: str, tur: str, metin_turu: Optional[str] = None) -> Iterable[str]:
    """Kullanılmamış varyant harfleri (A, B, …, Z, AA, …) — bu talepteki aynı tür varlıkların harflerinden sonra."""
    with engine.connect() as c:
        st = sa.select(ASSETS.c.varyant).where(ASSETS.c.tenant_id == tenant, ASSETS.c.request_id == _rid(rid),
                                               ASSETS.c.tur == tur)
        if metin_turu:
            st = st.where(ASSETS.c.metin_turu == metin_turu)
        used = set(c.execute(st).scalars().all())
    i = 0
    while True:
        n, s = i, ""
        while True:
            s = chr(65 + n % 26) + s
            n = n // 26 - 1
            if n < 0:
                break
        i += 1
        if s not in used:
            yield s


def _asset(conn, tenant: str, aid: str) -> dict[str, Any]:
    a = conn.execute(sa.select(ASSETS).where(ASSETS.c.tenant_id == tenant, ASSETS.c.id == _aid(aid))).mappings().first()
    if a is None:
        raise CreativeError("Varlık bulunamadı.", 404)
    return dict(a)


def get_asset(engine, tenant: str, aid: str) -> dict[str, Any]:
    with engine.connect() as c:
        a = _asset(c, tenant, aid)
        title = c.execute(sa.select(REQUESTS.c.kitap_adi).where(REQUESTS.c.id == a["request_id"])).scalar()
    return _asset_view(a, title)


def asset_row(engine, tenant: str, aid: str) -> dict[str, Any]:
    with engine.connect() as c:
        return _asset(c, tenant, aid)


def assets_stmt(tenant: str, rid: str, history: bool = False):
    st = sa.select(ASSETS).where(ASSETS.c.tenant_id == tenant, ASSETS.c.request_id == rid)
    if not history:
        st = st.where(ASSETS.c.guncel.is_(True))
    return st.order_by(ASSETS.c.tur, ASSETS.c.varyant, ASSETS.c.format, ASSETS.c.surum.desc())


def jobs_stmt(tenant: str, rid: str):
    return sa.select(JOBS).where(JOBS.c.tenant_id == tenant, JOBS.c.request_id == rid).order_by(JOBS.c.baslangic.desc())


def request_assets(engine, tenant: str, rid: str, history: bool = False) -> list[dict[str, Any]]:
    rid = _rid(rid)
    with engine.connect() as c:
        title = _row(c, tenant, rid)["kitap_adi"]
        rows = c.execute(assets_stmt(tenant, rid, history)).mappings().all()
    return [_asset_view(dict(a), title) for a in rows]


def versions(engine, tenant: str, aid: str) -> list[dict[str, Any]]:
    """Varlığın sürüm zinciri (en yenisi başta)."""
    out = []
    with engine.connect() as c:
        a = _asset(c, tenant, aid)
        title = c.execute(sa.select(REQUESTS.c.kitap_adi).where(REQUESTS.c.id == a["request_id"])).scalar()
        # ileri: bu sürümü öncesi sayan yenileri
        cur = a
        while True:
            nxt = c.execute(sa.select(ASSETS).where(ASSETS.c.tenant_id == tenant, ASSETS.c.onceki_id == cur["id"])
                            ).mappings().first()
            if nxt is None:
                break
            cur = dict(nxt)
        while cur is not None:
            out.append(_asset_view(cur, title))
            prev = cur["onceki_id"]
            cur = dict(_asset(c, tenant, prev)) if prev else None
    return out


def revise_text(engine, tenant: str, user: str, aid: str, text: str, *, source_texts: list[str], banned: list[str],
                lim: dict) -> dict[str, Any]:
    text = str(text or "").strip()
    if not text:
        raise CreativeError("Metin boş olamaz.")
    if len(text) > 20000:
        raise CreativeError("Metin çok uzun.")
    a = asset_row(engine, tenant, aid)
    if a["tur"] != "metin":
        raise CreativeError("Görselin düzeltmesi yeniden dizimle yapılır.")
    if not a["guncel"]:
        raise CreativeError("Bu eski bir sürüm; güncel sürümü düzeltin.", 409)
    chk = check_text(text, a["format"] or "", a["metin_turu"] or "", source_texts=source_texts, banned=banned, lim=lim)
    return add_asset(engine, tenant, user, a["request_id"], tur="metin", varyant=a["varyant"], kaynak="elle",
                     fmt=a["format"], metin_turu=a["metin_turu"], metin=text, dogrulama=chk, onceki=a)


def approve(engine, tenant: str, user: str, aid: str, level: str) -> dict[str, Any]:
    """`level`: tasarim | mesaj. Yetki API'de denetlenir; burada iş kuralları: aynı kişi iki onayı veremez, görselde
    önce tasarım, hatalı (sınır/alıntı) metin onaylanmaz, eski sürüm ve reddedilen onaylanmaz."""
    if level not in ("tasarim", "mesaj"):
        raise CreativeError("Onay seviyesi: tasarim ya da mesaj.")
    with engine.begin() as c:
        a = _asset(c, tenant, aid)
        if not a["guncel"]:
            raise CreativeError("Bu eski bir sürüm; güncel sürümü onaylayın.", 409)
        if a["red_zaman"] is not None:
            raise CreativeError("Reddedilen varlık onaylanamaz; önce yeni sürüm açın.", 409)
        if level == "tasarim":
            if a["tur"] != "gorsel":
                raise CreativeError("Metin varlığında tasarım onayı yok; mesaj onayı verin.")
            if a["mesaj_onaylayan"] and a["mesaj_onaylayan"].lower() == user.lower():
                raise CreativeError("Aynı kişi tasarım ve mesaj onayını birlikte veremez.", 409)
            vals = {"tasarim_onaylayan": user, "tasarim_onay": _now()}
        else:
            if a["tur"] == "gorsel" and a["tasarim_onay"] is None:
                raise CreativeError("Önce tasarım onayı gerekli.", 409)
            if a["tasarim_onaylayan"] and a["tasarim_onaylayan"].lower() == user.lower():
                raise CreativeError("Aynı kişi tasarım ve mesaj onayını birlikte veremez.", 409)
            chk = _loads(a["dogrulama_json"], {}) or {}
            if chk.get("durum") == "hata":
                raise CreativeError("Metinde düzeltilmesi gereken sorun var (sınır ya da alıntı); önce düzeltin.", 409)
            vals = {"mesaj_onaylayan": user, "mesaj_onay": _now()}
        c.execute(ASSETS.update().where(ASSETS.c.id == a["id"]).values(**vals))
        _refresh_status(c, tenant, a["request_id"])
    return get_asset(engine, tenant, aid)


def withdraw(engine, tenant: str, user: str, aid: str, level: str) -> dict[str, Any]:
    """Onayı geri alma (yalnız veren ya da yönetici; API denetler). Mesaj onayı kalkmadan tasarım onayı kalkmaz."""
    with engine.begin() as c:
        a = _asset(c, tenant, aid)
        if level == "tasarim":
            if a["mesaj_onay"] is not None:
                raise CreativeError("Önce mesaj onayı geri alınmalı.", 409)
            vals = {"tasarim_onaylayan": None, "tasarim_onay": None}
        elif level == "mesaj":
            vals = {"mesaj_onaylayan": None, "mesaj_onay": None}
        else:
            raise CreativeError("Onay seviyesi: tasarim ya da mesaj.")
        c.execute(ASSETS.update().where(ASSETS.c.id == a["id"]).values(**vals))
        _refresh_status(c, tenant, a["request_id"])
    return get_asset(engine, tenant, aid)


def reject(engine, tenant: str, user: str, aid: str, note: str) -> dict[str, Any]:
    note = str(note or "").strip()
    if not note:
        raise CreativeError("Ret nedeni yazın.")
    with engine.begin() as c:
        a = _asset(c, tenant, aid)
        if not a["guncel"]:
            raise CreativeError("Bu eski bir sürüm.", 409)
        c.execute(ASSETS.update().where(ASSETS.c.id == a["id"]).values(
            red_eden=user, red_zaman=_now(), red_notu=note[:2000], mesaj_onaylayan=None, mesaj_onay=None))
        _refresh_status(c, tenant, a["request_id"])
    return get_asset(engine, tenant, aid)


def mark_used(engine, tenant: str, aid: str, kanal: str, when: Optional[str], by: str) -> dict[str, Any]:
    """M21/M22 bildirimi: onaylı varlık hangi kanalda kullanıldı (A/B kaydı)."""
    with engine.begin() as c:
        a = _asset(c, tenant, aid)
        if a["mesaj_onay"] is None:
            raise CreativeError("Yalnız onaylı varlığın kullanımı kaydedilir.", 409)
        used = _loads(a["kullanildi_json"], [])
        used.append({"kanal": _short(kanal, 40) or a["kanal"], "tarih": _short(when, 20), "by": by, "at": _iso(_now())})
        c.execute(ASSETS.update().where(ASSETS.c.id == a["id"]).values(kullanildi_json=_dumps(used)))
    return get_asset(engine, tenant, aid)


def archive_stmt(tenant: str, *, stok: str = "", etiket: str = "", kanal: str = "", fmt: str = "", tur: str = "",
                 durum: str = "onayli", q: str = "", since: str = "", until: str = "") -> tuple[Any, Any]:
    """Arşivin süzgeçli okuması ve sıralama kolonu (aynı ifade sorgu bilgisinde gösterilir)."""
    st = (sa.select(ASSETS, REQUESTS.c.kitap_adi, REQUESTS.c.yazar, REQUESTS.c.kampanya)
          .join(REQUESTS, sa.and_(REQUESTS.c.id == ASSETS.c.request_id, REQUESTS.c.tenant_id == ASSETS.c.tenant_id))
          .where(ASSETS.c.tenant_id == tenant, ASSETS.c.guncel.is_(True)))
    if durum == "onayli":
        st = st.where(ASSETS.c.mesaj_onay.is_not(None), ASSETS.c.red_zaman.is_(None))
    elif durum == "bekleyen":
        st = st.where(ASSETS.c.mesaj_onay.is_(None), ASSETS.c.red_zaman.is_(None))
    elif durum == "reddedilen":
        st = st.where(ASSETS.c.red_zaman.is_not(None))
    if stok:
        st = st.where(ASSETS.c.stok_kodu == stok)
    if kanal:
        st = st.where(ASSETS.c.kanal == kanal)
    if fmt:
        st = st.where(ASSETS.c.format == fmt)
    if tur in ("gorsel", "metin"):
        st = st.where(ASSETS.c.tur == tur)
    if etiket:
        st = st.where(sa.or_(ASSETS.c.etiketler.ilike(f"%{json.dumps(etiket, ensure_ascii=False)}%"),
                             REQUESTS.c.kampanya == etiket))
    if q.strip():
        like = f"%{q.strip()}%"
        st = st.where(sa.or_(REQUESTS.c.kitap_adi.ilike(like), ASSETS.c.stok_kodu.ilike(like), ASSETS.c.metin.ilike(like),
                             REQUESTS.c.kampanya.ilike(like)))
    col = ASSETS.c.mesaj_onay if durum == "onayli" else ASSETS.c.olusturma
    if since:
        d = _day(since, "Başlangıç")
        st = st.where(col >= datetime(d.year, d.month, d.day, tzinfo=timezone.utc) - timedelta(hours=3))
    if until:
        d = _day(until, "Bitiş") + timedelta(days=1)
        st = st.where(col < datetime(d.year, d.month, d.day, tzinfo=timezone.utc) - timedelta(hours=3))
    return st, col


def archive(engine, tenant: str, *, stok: str = "", etiket: str = "", kanal: str = "", fmt: str = "", tur: str = "",
            durum: str = "onayli", q: str = "", since: str = "", until: str = "", page: int = 0) -> dict[str, Any]:
    """Arşiv (tavansız, sayfalı). `durum`: onayli | bekleyen | reddedilen | hepsi (yalnız güncel sürümler)."""
    st, col = archive_stmt(tenant, stok=stok, etiket=etiket, kanal=kanal, fmt=fmt, tur=tur, durum=durum, q=q,
                           since=since, until=until)
    page = max(0, int(page))
    with engine.connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(st.subquery())).scalar() or 0
        rows = c.execute(st.order_by(col.desc(), ASSETS.c.id).offset(page * PAGE_SIZE).limit(PAGE_SIZE)).mappings().all()
    items = []
    for r in rows:
        v = _asset_view(dict(r), r["kitap_adi"])
        v.update(kitapAdi=r["kitap_adi"], yazar=r["yazar"], kampanya=r["kampanya"])
        items.append(v)
    return {"items": items, "total": int(total), "page": page, "pageSize": PAGE_SIZE}


def approved_for_zip(engine, tenant: str, rid: str) -> tuple[str, list[dict[str, Any]]]:
    rid = _rid(rid)
    with engine.connect() as c:
        req = _row(c, tenant, rid)
        rows = c.execute(sa.select(ASSETS).where(ASSETS.c.tenant_id == tenant, ASSETS.c.request_id == rid,
                                                 ASSETS.c.guncel.is_(True), ASSETS.c.mesaj_onay.is_not(None),
                                                 ASSETS.c.red_zaman.is_(None))
                         .order_by(ASSETS.c.tur, ASSETS.c.varyant, ASSETS.c.format)).mappings().all()
    return req["kitap_adi"], [dict(r) for r in rows]


def build_zip(title: str, rows: list[dict[str, Any]]) -> bytes:
    """Yayına hazır paket: onaylı görseller (PNG) ve metinler (TXT), düzenli adlarla. Lisans taslağı varsa OKUYUN."""
    import io
    import zipfile
    if not rows:
        raise CreativeError("İndirilecek onaylı varlık yok.", 409)
    buf = io.BytesIO()
    names: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r in rows:
            v = _asset_view(r, title)
            name = v["dosyaAdi"]
            if name in names:
                name = name.replace(".", f"-{r['id'][:6]}.", 1)
            names.add(name)
            if r["tur"] == "gorsel":
                p = Path(r["dosya_yolu"] or "")
                if not p.is_file():
                    continue
                z.write(p, name)
            else:
                z.writestr(name, (r["metin"] or "") + "\n")
    return buf.getvalue()


def contract_assets(engine, tenant: str, *, stok: str = "", kanal: str = "", page: int = 0) -> dict[str, Any]:
    """M21/M22/M24'ün okuduğu sözleşme: onaylı ve yayına hazır varlıklar."""
    out = archive(engine, tenant, stok=stok, kanal=kanal, durum="onayli", page=page)
    keep = ("id", "requestId", "stokKodu", "kitapAdi", "tur", "kanal", "format", "metinTuru", "varyant", "metin",
            "genislik", "yukseklik", "surum", "yayinaHazir", "dosyaAdi", "mesajOnay", "etiketler")
    return {**out, "items": [{k: v.get(k) for k in keep} for v in out["items"]]}


# ------------------------------------------------------------------ işler
def start_job(engine, tenant: str, rid: str, tur: str, user: str) -> str:
    """Aynı talepte aynı türde süren iş varsa 409. Başka süreçte «sürüyor» kalan (köprü yeniden başladı) iş hata olur."""
    rid = _rid(rid)
    jid = uuid.uuid4().hex
    with engine.begin() as c:
        _row(c, tenant, rid)
        c.execute(JOBS.update().where(JOBS.c.tenant_id == tenant, JOBS.c.durum == "suruyor", JOBS.c.surec != PROCESS)
                  .values(durum="hata", hata="Üretim yarıda kaldı (servis yeniden başladı); yeniden başlatın.",
                          bitis=_now()))
        busy = c.execute(sa.select(JOBS.c.id).where(JOBS.c.tenant_id == tenant, JOBS.c.request_id == rid,
                                                    JOBS.c.tur == tur, JOBS.c.durum == "suruyor")).scalar()
        if busy:
            raise CreativeError("Bu talepte aynı üretim zaten sürüyor.", 409)
        c.execute(JOBS.insert().values(id=jid, tenant_id=tenant, request_id=rid, tur=tur, durum="suruyor",
                                       ilerleme_json=_dumps([0, 0]), surec=PROCESS, olusturan=user, baslangic=_now()))
    return jid


def job_progress(engine, jid: str, n: int, total: int, step: str = "") -> None:
    with engine.begin() as c:
        c.execute(JOBS.update().where(JOBS.c.id == jid).values(ilerleme_json=_dumps([n, total, step])))


def finish_job(engine, tenant: str, jid: str, result: Optional[dict] = None, error: Optional[str] = None) -> None:
    with engine.begin() as c:
        rid = c.execute(sa.select(JOBS.c.request_id).where(JOBS.c.id == jid)).scalar()
        c.execute(JOBS.update().where(JOBS.c.id == jid).values(
            durum="hata" if error else "bitti", hata=(error or None), sonuc_json=_dumps(result or {}), bitis=_now()))
        if rid:
            _refresh_status(c, tenant, rid)


def jobs_of(engine, tenant: str, rid: str) -> list[dict[str, Any]]:
    rid = _rid(rid)
    with engine.connect() as c:
        rows = c.execute(jobs_stmt(tenant, rid)).mappings().all()
    out = []
    for j in rows:
        running = j["durum"] == "suruyor" and j["surec"] != PROCESS
        out.append({"id": j["id"], "tur": j["tur"], "durum": "hata" if running else j["durum"],
                    "ilerleme": _loads(j["ilerleme_json"], None), "sonuc": _loads(j["sonuc_json"], None),
                    "hata": "Üretim yarıda kaldı (servis yeniden başladı); yeniden başlatın." if running else j["hata"],
                    "olusturan": j["olusturan"], "baslangic": _iso(j["baslangic"]), "bitis": _iso(j["bitis"])})
    return out


# ------------------------------------------------------------------ marka kiti ve yasaklı kalıplar
def brand(engine, tenant: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(BRAND).where(BRAND.c.tenant_id == tenant).order_by(BRAND.c.surum.desc())).mappings().first()
    if r is None:
        return {"surum": 0, "palet": [], "logolar": [], "yaziTipleri": [], "kurallar": "", "yukleyen": None, "zaman": None}
    return {"surum": r["surum"], "palet": _loads(r["palet_json"], []), "logolar": _loads(r["logo_dosyalari"], []),
            "yaziTipleri": _loads(r["yazi_tipleri_json"], []), "kurallar": r["kurallar_metni"] or "",
            "yukleyen": r["yukleyen"], "zaman": _iso(r["zaman"])}


def save_brand(engine, tenant: str, user: str, body: dict[str, Any], new_files: Iterable[dict] = ()) -> dict[str, Any]:
    """Yeni sürüm yazar (eskiler geçmişte kalır). Dosya listeleri yalnız yüklenmiş dosyaları içerebilir."""
    cur = brand(engine, tenant)
    pal = body.get("palet", cur["palet"])
    if not isinstance(pal, list) or any(not _HEX.match(str(x)) for x in pal):
        raise CreativeError("Palet #RRGGBB renklerinden oluşmalı.")
    logos = body.get("logolar", cur["logolar"])
    fonts = body.get("yaziTipleri", cur["yaziTipleri"])
    files = {f["id"] for f in cur["logolar"] + cur["yaziTipleri"]} | {f.get("id") for f in new_files}
    for f in list(logos) + list(fonts):
        if not isinstance(f, dict) or f.get("id") not in files:
            raise CreativeError("Dosya listesi yalnız yüklenen dosyaları içerebilir.")
    for f in fonts:
        f["lisans"] = _short(f.get("lisans"), 400)
    rules = str(body.get("kurallar", cur["kurallar"]) or "").strip()[:8000]
    with engine.begin() as c:
        c.execute(BRAND.insert().values(tenant_id=tenant, surum=cur["surum"] + 1,
                                        palet_json=_dumps([str(x).upper() for x in dict.fromkeys(pal)]),
                                        logo_dosyalari=_dumps(logos), yazi_tipleri_json=_dumps(fonts),
                                        kurallar_metni=rules, yukleyen=user, zaman=_now()))
    return brand(engine, tenant)


BRAND_FILE_EXT = {"logo": {".png", ".svg", ".jpg", ".jpeg", ".webp"}, "font": {".ttf", ".otf", ".woff", ".woff2"}}
BRAND_FILE_MAX = 20 * 1024 * 1024


def add_brand_file(engine, tenant: str, user: str, kind: str, filename: str, data: bytes,
                   license_note: str = "") -> dict[str, Any]:
    if kind not in BRAND_FILE_EXT:
        raise CreativeError("Dosya türü: logo ya da font.")
    name = Path(str(filename or "")).name[:120]
    ext = Path(name).suffix.lower()
    if ext not in BRAND_FILE_EXT[kind]:
        raise CreativeError(f"{'Logo' if kind == 'logo' else 'Yazı tipi'} dosyası uzantısı: " + ", ".join(sorted(BRAND_FILE_EXT[kind])))
    if not data or len(data) > BRAND_FILE_MAX:
        raise CreativeError("Dosya boş ya da 20 MB'tan büyük.", 413 if data else 400)
    if kind == "font" and not _short(license_note, 400):
        raise CreativeError("Yazı tipinin kullanım lisansını not edin (sunucuda kullanım izni).")
    fid = uuid.uuid4().hex
    d = assets_dir() / "marka"
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{fid}{ext}").write_bytes(data)
    except OSError as e:
        raise CreativeError("Dosya arşive yazılamadı.", 503) from e
    item = {"id": fid, "ad": name, "dosya": f"{fid}{ext}", "tur": kind, "boyut": len(data), "yukleyen": user,
            "zaman": _iso(_now())}
    if kind == "font":
        item["lisans"] = _short(license_note, 400)
    cur = brand(engine, tenant)
    key = "logolar" if kind == "logo" else "yaziTipleri"
    return save_brand(engine, tenant, user, {key: cur[key] + [item]}, [item])


def brand_file(engine, tenant: str, fid: str) -> tuple[Path, str]:
    if not _ID.match(fid or ""):
        raise CreativeError("Dosya bulunamadı.", 404)
    b = brand(engine, tenant)
    for f in b["logolar"] + b["yaziTipleri"]:
        if f["id"] == fid:
            p = assets_dir() / "marka" / f["dosya"]
            if p.is_file():
                return p, f["ad"]
    raise CreativeError("Dosya bulunamadı.", 404)


def banned_phrases(engine, tenant: str) -> list[dict[str, Any]]:
    """Liste; ilk açılışta başlangıç listesi bir kez yazılır (kişi sonra hepsini silerse geri gelmez)."""
    with engine.begin() as c:
        seeded = c.execute(sa.select(META.c.deger).where(META.c.tenant_id == tenant,
                                                         META.c.anahtar == "yasakli_tohum")).scalar()
        if seeded is None:
            if not c.execute(sa.select(sa.func.count()).select_from(BANNED).where(BANNED.c.tenant_id == tenant)).scalar():
                for k, why in DEFAULT_BANNED:
                    c.execute(BANNED.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, kalip=k, aciklama=why,
                                                     ekleyen="sistem", zaman=_now()))
            c.execute(META.insert().values(tenant_id=tenant, anahtar="yasakli_tohum", deger=_iso(_now())))
        rows = c.execute(sa.select(BANNED).where(BANNED.c.tenant_id == tenant).order_by(BANNED.c.kalip)).mappings().all()
    return [{"id": r["id"], "kalip": r["kalip"], "aciklama": r["aciklama"], "ekleyen": r["ekleyen"],
             "zaman": _iso(r["zaman"])} for r in rows]


def save_banned(engine, tenant: str, user: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Listenin tamamı gelir (ekran düzenler); eklenen/silinen farkı yazılır. Boş liste = hiç yasaklı kalıp yok."""
    if not isinstance(items, list):
        raise CreativeError("Liste bekleniyor.")
    clean: dict[str, dict[str, Any]] = {}
    for it in items:
        k = _short((it or {}).get("kalip"), 200)
        if not k:
            continue
        if tr_fold(k).startswith("re:"):
            try:
                re.compile(tr_fold(k)[3:])
            except re.error:
                raise CreativeError(f"Düzenli ifade geçersiz: {k}") from None
        clean[tr_fold(k)] = {"kalip": k, "aciklama": _short((it or {}).get("aciklama"), 400)}
    banned_phrases(engine, tenant)                 # ilk açılış tohumu yazılmış olsun
    with engine.begin() as c:
        rows = c.execute(sa.select(BANNED).where(BANNED.c.tenant_id == tenant)).mappings().all()
        have = {tr_fold(r["kalip"]): r for r in rows}
        for key, r in have.items():
            if key not in clean:
                c.execute(BANNED.delete().where(BANNED.c.id == r["id"]))
            elif (clean[key]["aciklama"] or None) != (r["aciklama"] or None):
                c.execute(BANNED.update().where(BANNED.c.id == r["id"]).values(aciklama=clean[key]["aciklama"]))
        for key, it in clean.items():
            if key not in have:
                c.execute(BANNED.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, kalip=it["kalip"],
                                                 aciklama=it["aciklama"], ekleyen=user, zaman=_now()))
    return banned_phrases(engine, tenant)


def meta_get(engine, tenant: str, key: str) -> Optional[str]:
    with engine.connect() as c:
        return c.execute(sa.select(META.c.deger).where(META.c.tenant_id == tenant, META.c.anahtar == key)).scalar()


def meta_set(engine, tenant: str, key: str, value: str) -> None:
    with engine.begin() as c:
        cond = (META.c.tenant_id == tenant, META.c.anahtar == key)
        if c.execute(sa.select(META.c.anahtar).where(*cond)).first():
            c.execute(META.update().where(*cond).values(deger=value))
        else:
            c.execute(META.insert().values(tenant_id=tenant, anahtar=key, deger=value))


# ------------------------------------------------------------------ özet ve günlük bildirim
def summary_stmts(tenant: str, user: str, since: datetime, soon: date) -> dict[str, Any]:
    """Özet sayaçlarının okumaları (aynı ifadeler sorgu bilgisinde gösterilir)."""
    base = sa.select(sa.func.count()).select_from(ASSETS).where(
        ASSETS.c.tenant_id == tenant, ASSETS.c.guncel.is_(True), ASSETS.c.red_zaman.is_(None))
    return {
        "yeni": sa.select(sa.func.count()).select_from(REQUESTS).where(REQUESTS.c.tenant_id == tenant, REQUESTS.c.olusturma >= since),
        "termin": sa.select(REQUESTS.c.id, REQUESTS.c.kitap_adi, REQUESTS.c.termin, REQUESTS.c.isteyen, REQUESTS.c.atanan,
                            REQUESTS.c.durum).where(
            REQUESTS.c.tenant_id == tenant, REQUESTS.c.termin.is_not(None), REQUESTS.c.termin <= soon,
            REQUESTS.c.durum.not_in(["onayli", "reddedildi", "arsiv"])).order_by(REQUESTS.c.termin),
        "tasarim": base.where(ASSETS.c.tur == "gorsel", ASSETS.c.tasarim_onay.is_(None)),
        "mesaj": base.where(ASSETS.c.mesaj_onay.is_(None), sa.or_(ASSETS.c.tur == "metin", ASSETS.c.tasarim_onay.is_not(None)),
                            sa.or_(ASSETS.c.tasarim_onaylayan.is_(None), ASSETS.c.tasarim_onaylayan != user)),
        "bana": sa.select(sa.func.count()).select_from(REQUESTS).where(
            REQUESTS.c.tenant_id == tenant, REQUESTS.c.atanan == user, REQUESTS.c.durum.not_in(["onayli", "reddedildi", "arsiv"])),
    }


def summary(engine, tenant: str, user: str, can_design: bool, can_message: bool, today: date,
            trace: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Rozet ve günlük özet: kişinin onay kuyruğu, yeni talepler (son 24 saat), terminine 2 gün kalan onaysız talepler.
    `trace` verilirse kullanılan an ve gün (sorgu bilgisinde aynı ifade için) yazılır."""
    since = _now() - timedelta(days=1)
    soon = today + timedelta(days=2)
    if trace is not None:
        trace.update(since=since, soon=soon)
    q = summary_stmts(tenant, user, since, soon)
    with engine.connect() as c:
        new = c.execute(q["yeni"]).scalar() or 0
        due = c.execute(q["termin"]).mappings().all()
        design = c.execute(q["tasarim"]).scalar() or 0
        message = c.execute(q["mesaj"]).scalar() or 0
        mine = c.execute(q["bana"]).scalar() or 0
    return {"yeniTalep": int(new), "tasarimBekleyen": int(design) if can_design else None,
            "mesajBekleyen": int(message) if can_message else None, "bana": int(mine),
            "terminiYaklasan": [{"id": r["id"], "kitapAdi": r["kitap_adi"], "termin": _iso(r["termin"]),
                                 "isteyen": r["isteyen"], "atanan": r["atanan"], "durum": r["durum"]} for r in due]}
