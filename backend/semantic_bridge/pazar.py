"""M39 Pazar araştırması ve rekabet analizi: rakip katalog anlık görüntüsü ve tazeliği, rakip kategori ↔ TİMAŞ
kategori eşlemesi, yayınevi × kategori fiyat/format matrisi, emsal bulma, TİMAŞ iç göstergeleri (Logo), sektör raporu
yükleme ve rakam çıkarımı, aylık yönetim özeti (DYK'ya).

**Kaynak ve yazma:** CRM'e ve Logo'ya yazılmaz. Rakip verisinin iki kaynağı var (ekranda seçilir, tazelik şeridi
seçilenin tarihini yazar): **Başarı Dağıtım kataloğu** (`pazar_dagitim` tabloları; son görüntüdeki TİMAŞ grubu dışı
başlıklar, liste fiyatı; Pazar ekranının varsayılanı) ve CRM'deki **«Rakip Kitap»** varlığı (kaynağı ve tazeliği
bilinmiyor; uçların parametresiz varsayılanı — fiyatlama ve yayın kurulu ekranları böyle çağırır). İki kaynağın ham
kategorisi aynı eşleme tablosundadır; Başarı anahtarı «basari:» önekiyle ayrılır. Dış tarama yok: bot korumalı
siteler, çok satan listeleri, sosyal medya ve arama eğilimi bu sürümde yok; pazar rakamları yalnız kullanıcının
yüklediği rapordan ve insan onayıyla gelir. Pazar büyüklüğü kaynağı yoksa «kaynak yok» yazılır, tahmin üretilmez.
TİMAŞ'ın Logo satışı sell-in'dir; «pazar payı» diye sunulmaz.

**Zeki AI (K2/K3):** kategori eşlemesi kapalı küme seçimdir (`QueuedLlm.choose`, olasılıkla); emsal sıralaması aday
başına kapalı küme («çok benzer / kısmen / benzemiyor»), gerekçe kurallıdır; rapordan rakam çıkarımında modelin verdiği
her rakam sayfanın metninde birebir aranır, bulunmayan atılır; özet taslağında her cümle bir kaynak kimliğine bağlı
olmalı ve cümledeki her sayı bağlandığı kaynağın değeriyle tutmalıdır (tutmayan cümle reddedilir). Rakamı model
üretmez; onay insandadır.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import threading
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

# Sayı yazımı tek yerde (`zeki_text.parse_number`): «12.345» hem TR binlik hem EN ondalık okunur.
from semantic_bridge.zeki_text import parse_number

log = logging.getLogger("semantic.pazar")
_md = sa.MetaData()

COMPETITORS = sa.Table(
    "semantic_pazar_competitor_books", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("crm_id", sa.String(40), primary_key=True),
    sa.Column("ad", sa.String(400), nullable=False),
    sa.Column("yayinevi", sa.String(200), index=True),
    sa.Column("yazarlar", sa.String(400)),
    sa.Column("isbn", sa.String(40)),
    sa.Column("liste_fiyat", sa.Float),
    sa.Column("sayfa", sa.Integer),
    sa.Column("cilt", sa.String(100)),
    sa.Column("kagit", sa.String(100)),
    sa.Column("baski_sayisi", sa.Integer),
    sa.Column("kategori_ham", sa.String(300), index=True),
    sa.Column("kategori_id", sa.String(40), index=True),        # onaylı eşlemeden
    sa.Column("dil", sa.String(60)),
    sa.Column("satis_adedi_ham", sa.Integer),                   # anlamı bilinmiyor; hesapta kullanılmaz
    sa.Column("satis_adedi2_ham", sa.String(60)),
    sa.Column("satis_durumu", sa.String(100)),
    sa.Column("tanitim_kisa", sa.Text),                         # ilk PAZAR_BLURB_CHARS karakter
    sa.Column("crm_created", sa.String(25)),
    sa.Column("crm_modified", sa.String(25)),
    sa.Column("kopyalandi_at", sa.DateTime(timezone=True), nullable=False),
)
OWN_BOOKS = sa.Table(
    "semantic_pazar_own_books", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("crm_id", sa.String(40), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), index=True),
    sa.Column("ad", sa.String(400), nullable=False),
    sa.Column("yazar", sa.String(400)),
    sa.Column("isbn", sa.String(40)),
    sa.Column("marka_id", sa.String(40)),
    sa.Column("marka", sa.String(200)),
    sa.Column("kitaplik_id", sa.String(40)),
    sa.Column("kitaplik", sa.String(200)),
    sa.Column("kategori_id", sa.String(40), index=True),
    sa.Column("fiyat", sa.Float),
    sa.Column("sayfa", sa.Integer),
    sa.Column("cilt", sa.String(60)),
    sa.Column("ebat", sa.String(60)),
    sa.Column("web", sa.String(300)),
    sa.Column("ilk_yayin", sa.String(10)),
    sa.Column("ozet_kisa", sa.Text),
    sa.Column("kopyalandi_at", sa.DateTime(timezone=True), nullable=False),
)
OWN_SALES = sa.Table(
    "semantic_pazar_own_sales", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("yil", sa.Integer, primary_key=True),
    sa.Column("boyut", sa.String(10), primary_key=True),        # stok | kanal
    sa.Column("anahtar", sa.String(120), primary_key=True),
    sa.Column("yayinevi", sa.String(120)),                      # Logo ITEMS.SPECODE (stok satırında)
    sa.Column("ytd_adet", sa.Float, nullable=False, default=0.0),
    sa.Column("ytd_ciro", sa.Float, nullable=False, default=0.0),
    sa.Column("adet", sa.Float, nullable=False, default=0.0),
    sa.Column("ciro", sa.Float, nullable=False, default=0.0),
)
LINKS = sa.Table(
    "semantic_pazar_links", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kitap_crm_id", sa.String(40), primary_key=True),
    sa.Column("rakip_crm_id", sa.String(40), primary_key=True),
)
CATEGORIES = sa.Table(
    "semantic_pazar_categories", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("ad", sa.String(200), nullable=False),
    sa.Column("ust_id", sa.String(40)),
    sa.Column("yol", sa.String(600)),
    sa.Column("kaynak", sa.String(10), nullable=False),         # kitaplik | agac
)
CATEGORY_MAP = sa.Table(
    "semantic_pazar_category_map", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kategori_ham", sa.String(300), primary_key=True),
    sa.Column("kayit_sayisi", sa.Integer, nullable=False, default=0),
    sa.Column("oneri_kategori_id", sa.String(40)),
    sa.Column("kategori_id", sa.String(40)),                    # onaylı karşılık
    sa.Column("olasilik", sa.Float),
    sa.Column("marj", sa.Float),
    sa.Column("yontem", sa.String(20)),                         # ad | zeki | elle
    sa.Column("durum", sa.String(12), nullable=False),          # yeni | oneri | belirsiz | onaylandi | reddedildi
    sa.Column("oneren", sa.String(120)),
    sa.Column("onerildi_at", sa.DateTime(timezone=True)),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("karar_at", sa.DateTime(timezone=True)),
    sa.Column("not_", sa.String(300)),
    sa.Column("kanit_json", sa.Text),
)
REPORTS = sa.Table(
    "semantic_pazar_reports", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("kaynak", sa.String(200), nullable=False),
    sa.Column("yil", sa.Integer),
    sa.Column("baslik", sa.String(300), nullable=False),
    sa.Column("dosya_adi", sa.String(220), nullable=False),
    sa.Column("dosya_yolu", sa.String(500), nullable=False),
    sa.Column("mime", sa.String(120), nullable=False),
    sa.Column("boyut", sa.Integer, nullable=False),
    sa.Column("sha256", sa.String(64), nullable=False),
    sa.Column("sayfa_sayisi", sa.Integer),
    sa.Column("durum", sa.String(14), nullable=False),          # yuklendi | cikariliyor | cikarildi | hata
    sa.Column("ilerleme_json", sa.Text),
    sa.Column("yukleyen", sa.String(120), nullable=False),
    sa.Column("yuklendi_at", sa.DateTime(timezone=True), nullable=False),
)
FIGURES = sa.Table(
    "semantic_pazar_report_figures", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("report_id", sa.String(32), nullable=False, index=True),
    sa.Column("gosterge", sa.String(300), nullable=False),
    sa.Column("deger", sa.Float, nullable=False),
    sa.Column("deger_metin", sa.String(60)),
    sa.Column("deger_oneri", sa.Float),                         # modelin çıkardığı (düzeltmede korunur)
    sa.Column("birim", sa.String(40)),
    sa.Column("donem", sa.String(40)),
    sa.Column("sayfa", sa.String(60), nullable=False),
    sa.Column("alinti_kisa", sa.String(300)),
    sa.Column("olcu", sa.String(20), nullable=False, default="diger"),
    sa.Column("kategori_id", sa.String(40)),
    sa.Column("yontem", sa.String(10), nullable=False),         # zeki | elle
    sa.Column("durum", sa.String(12), nullable=False),          # oneri | onaylandi | duzeltildi | reddedildi
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("karar_at", sa.DateTime(timezone=True)),
    sa.Column("not_", sa.String(300)),
    sa.Column("olusturuldu_at", sa.DateTime(timezone=True), nullable=False),
)
BRIEFS = sa.Table(
    "semantic_pazar_briefs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("donem", sa.String(7), nullable=False),           # YYYY-AA
    sa.Column("taslak_md", sa.Text, nullable=False),
    sa.Column("kaynaklar_json", sa.Text, nullable=False),
    sa.Column("durum", sa.String(14), nullable=False),          # taslak | onay_bekliyor | onaylandi
    sa.Column("yazan", sa.String(120), nullable=False),
    sa.Column("yazildi_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("guncelleyen", sa.String(120)),
    sa.Column("guncellendi_at", sa.DateTime(timezone=True)),
    sa.Column("gonderen", sa.String(120)),
    sa.Column("gonderildi_at", sa.DateTime(timezone=True)),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onaylandi_at", sa.DateTime(timezone=True)),
    sa.Column("dyk_gonderildi_at", sa.DateTime(timezone=True)),
    sa.Column("karar_notu", sa.String(500)),
)
WATCHLIST = sa.Table(
    "semantic_pazar_watchlist", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("yayinevi", sa.String(200), nullable=False),
    sa.Column("kategori_id", sa.String(40)),
    sa.Column("ekleyen", sa.String(120), nullable=False),
    sa.Column("eklendi_at", sa.DateTime(timezone=True), nullable=False),
)
META = sa.Table(
    "semantic_pazar_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(60), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

MAP_STATUS = {"yeni": "Öneri bekliyor", "oneri": "Zeki AI önerisi", "belirsiz": "Zeki AI emin değil",
              "onaylandi": "Onaylı", "reddedildi": "Karşılığı yok"}
FIGURE_STATUS = {"oneri": "Onay bekliyor", "onaylandi": "Onaylı", "duzeltildi": "Düzeltilerek onaylı",
                 "reddedildi": "Reddedildi"}
APPROVED_FIGURE = ("onaylandi", "duzeltildi")
BRIEF_STATUS = {"taslak": "Taslak", "onay_bekliyor": "Onay bekliyor", "onaylandi": "Onaylı"}
OLCU = {"pazar_ciro": "Pazar büyüklüğü (ciro)", "pazar_adet": "Pazar büyüklüğü (adet)",
        "pazar_buyume": "Pazar büyümesi (%)", "kategori_pay": "Kategorinin pazardaki payı (%)",
        "okur": "Okur ve demografi", "diger": "Diğer"}
REPORT_STATUS = {"yuklendi": "Yüklendi", "cikariliyor": "Rakamlar çıkarılıyor", "cikarildi": "Rakamlar çıkarıldı",
                 "hata": "Çıkarım yarım kaldı"}
DIMENSIONS = {"kategori": "Kategori", "yayinevi": "Yayınevi (marka)", "kanal": "Kanal"}
SELL_IN_NOTE = ("TİMAŞ rakamları Logo'daki faturalı satıştır (kitapçıya ve dağıtıcıya satış, iade düşülmüş); okura "
                "satış ya da pazar payı değildir.")
SIMILARITY = ["çok benzer", "kısmen benzer", "benzemiyor"]
BRIEF_SECTIONS = {"firsatlar": "Fırsatlar", "tehditler": "Tehditler", "aksiyonlar": "Öncelikli aksiyonlar"}
#: Rakip kaynağı: matris, rakip listesi, emsal ve kategori eşlemesi hangi katalogdan okur. Uçların varsayılanı `crm`
#: (başka ekranlar — fiyatlama, yayın kurulu — parametresiz çağırır); Pazar ekranı `basari`'yı varsayılan gönderir.
RAKIP_KAYNAK = {"basari": "Başarı Dağıtım kataloğu", "crm": "CRM rakip kayıtları"}
#: Başarı ham kategorisinin eşleme anahtarı öneki: `semantic_pazar_category_map.kategori_ham` = «basari:Üst>Alt».
#: CRM ham kategorileri öneksizdir; iki kaynağın eşlemesi aynı tabloda, birbirini ezmeden durur.
BASARI_PREFIX = "basari:"

_ready: set[int] = set()
_lock = threading.Lock()


class PazarError(ValueError):
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


# ================================================================================ küçük yardımcılar


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.isoformat()


def loads(raw: Optional[str], default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except ValueError:
        return default


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def new_id() -> str:
    return uuid.uuid4().hex


def fold(s: Any) -> str:
    """Türkçe harf farkı gözetmeyen karşılaştırma anahtarı."""
    t = str(s or "").replace("İ", "i").replace("I", "ı").lower()
    return " ".join(t.split())


def _conf(key: str, default: str) -> str:
    try:
        from semantic_bridge import admin as admin_mod

        v = admin_mod.conf(key)
    except Exception:  # noqa: BLE001 — testte admin ayarı yok
        v = ""
    return v if v not in (None, "") else os.environ.get(key, default)


def _f(key: str, default: float) -> float:
    try:
        return float(str(_conf(key, str(default))).replace(",", "."))
    except ValueError:
        return default


def settings() -> dict[str, Any]:
    """Ayarlar (ekran > ortam > varsayılan). Ölçülmemiş varsayımlar burada; kodda sabit değil."""
    return {
        "blurbChars": max(0, int(_f("PAZAR_BLURB_CHARS", 280))),
        "ownYears": max(2, int(_f("PAZAR_OWN_YEARS", 3))),
        "staleDays": max(1, int(_f("PAZAR_STALE_DAYS", 180))),
        "newDays": max(1, int(_f("PAZAR_NEW_DAYS", 365))),
        "categorySource": (_conf("PAZAR_CATEGORY_SOURCE", "auto") or "auto").strip().lower(),
        "categoryLevels": [x.strip() for x in (_conf("PAZAR_CATEGORY_LEVELS", "ana,alt") or "ana,alt").split(",") if x.strip()],
        "mapMinProb": _f("PAZAR_MAP_MIN_PROB", 0.70), "mapMinMargin": _f("PAZAR_MAP_MIN_MARGIN", 0.30),
        "batchSeconds": max(60, int(_f("PAZAR_BATCH_SECONDS", 1800))),
        "compPageTol": _f("PAZAR_COMP_PAGE_TOL", 0.25), "compPriceTol": _f("PAZAR_COMP_PRICE_TOL", 0.30),
        "compModel": max(0, int(_f("PAZAR_COMP_MODEL_CANDIDATES", 20))),
        "compEmbed": max(0, int(_f("PAZAR_COMP_EMBED_CANDIDATES", 30))),
        "extractChars": max(2000, int(_f("PAZAR_EXTRACT_PAGE_CHARS", 12000))),
        "fileMaxMb": max(1, int(_f("PAZAR_FILE_MAX_MB", 50))),
        "briefMaxSources": max(5, int(_f("PAZAR_BRIEF_MAX_SOURCES", 60))),
        "basariStaleDays": max(1, int(_f("PAZAR_BASARI_STALE_DAYS", 7))),
        "twoEyes": (_conf("PAZAR_BRIEF_TWO_EYES", "1") or "1").strip().lower() in ("1", "true", "evet", "on"),
        "recipients": [x.strip() for x in re.split(r"[,;\s]+", _conf("PAZAR_ALERT_RECIPIENTS", "") or "") if "@" in x],
    }


def files_root() -> Path:
    return Path(os.environ.get("PAZAR_DIR", "/data/nanobaseai/bi/var/pazar-raporlar"))


def meta_get(engine: sa.engine.Engine, tenant: str, key: str, default: Any = None) -> Any:
    with engine.connect() as c:
        r = c.execute(sa.select(META.c.value_json).where(META.c.tenant_id == tenant, META.c.key == key)).first()
    return loads(r[0], default) if r else default


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: Any) -> None:
    with engine.begin() as c:
        c.execute(META.delete().where(META.c.tenant_id == tenant, META.c.key == key))
        c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=dumps(value), updated_at=now()))


def percentile(values: list[float], p: float) -> Optional[float]:
    """SQL Server `PERCENTILE_CONT` ile aynı: sıralı dizide (n−1)·p konumunda doğrusal ara değer."""
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] if lo == hi else v[lo] + (v[hi] - v[lo]) * (k - lo)


def _day(v: Optional[str]) -> Optional[date]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v)[:19]).date()
    except ValueError:
        return None


def today() -> date:
    return datetime.now(timezone(timedelta(hours=3))).date()


# ================================================================================ sayılar (rakam doğrulaması)

_NUM = re.compile(r"(?<![\w.,])[-+]?\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?(?![\d])|(?<![\w.,])[-+]?\d+(?:[.,]\d+)?(?![\d])")
_SCALE = {"bin": 1e3, "milyon": 1e6, "mn": 1e6, "milyar": 1e9, "mlr": 1e9, "trilyon": 1e12}


def numbers_in(text: str) -> list[dict[str, Any]]:
    """Metindeki sayılar: yazım, olası değerler, ölçek sözcüğü (bin/milyon/milyar)."""
    out = []
    for m in _NUM.finditer(text or ""):
        tail = (text[m.end(): m.end() + 12] or "").strip().lower()
        word = re.match(r"[a-zçğıöşü]+", tail)
        scale = _SCALE.get(word.group(0), 1.0) if word else 1.0
        out.append({"text": m.group(0).strip(), "values": parse_number(m.group(0)), "scale": scale,
                    "start": m.start(), "end": m.end()})
    return out


def _page_values(text: str) -> set[float]:
    """Metindeki bütün sayı değerleri. Boşlukla binlik ayrılmış yazım («12 345») tablo sütunlarını birleştirebilir; bu
    yüzden her parça ayrıca da okunur."""
    vals: set[float] = set()
    for n in numbers_in(text):
        for v, _ in n["values"]:
            vals.add(round(v, 6))
    for tok in re.findall(r"[-+]?\d[\d.,]*\d|\d", text or ""):
        for v, _ in parse_number(tok):
            vals.add(round(v, 6))
    return vals


def to_number(v: Any) -> float:
    """Ekrandan gelen değer: sayı ya da Türkçe/İngilizce yazım («1.234,5», «12.5»). Belirsizde Türkçe yorum."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    vals = parse_number(str(v or "").strip())
    if not vals:
        raise ValueError(v)
    return vals[0][0]


def value_in_text(value_text: str, text: str) -> Optional[float]:
    """Modelin verdiği değer sayfa metninde birebir geçiyor mu. Geçiyorsa değer (metindeki yazımın tek anlamlı
    yorumu), geçmiyorsa None."""
    page = _page_values(text)
    for v, _ in parse_number(str(value_text).strip()):
        if round(v, 6) in page:
            return v
    return None


def unsupported_numbers(text: str, values: Iterable[Any]) -> list[str]:
    """Cümledeki, bağlandığı kaynakların hiçbir değeriyle (yuvarlama payıyla) tutmayan sayılar. Yıllar (1900–2100) ve
    kaynak kimliğindeki numara ([K3]) sayılmaz. Denetim: `zeki_text` (tek sayı denetçisi); değerler sayı ya da dönem
    yazımı gibi metin olabilir."""
    from semantic_bridge import zeki_text as Z

    body = re.sub(r"\[K\d+\]", " ", text or "")
    return Z.unsupported(body, [v for v in values if v is not None], free_years=True)


def fmt_tr(v: Optional[float], dec: int = 0) -> str:
    if v is None:
        return "—"
    s = f"{abs(v):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if v < 0 else "") + s


# ================================================================================ kategoriler


def h1_categories(engine: sa.engine.Engine, tenant: str, levels: list[str]) -> Optional[dict[str, Any]]:
    """Yürürlükteki H1 kategori ağacından kategori listesi (seçilen düzeyler) ve kitap → kategori. Ağaç yoksa None."""
    try:
        from semantic_bridge import categories as C

        C.ensure(engine)
        tree = C.in_force(engine, tenant)
        if not tree:
            return None
        ctx = C.tree_ctx(engine, tree)
        keep = {nid for nid, n in ctx.nodes.items() if n.get("level") in levels and ctx.active(nid)}
        if not keep:
            return None
        cats = []
        for nid in keep:
            parent = next((a for a in ctx.ancestors(nid) if a in keep), None)
            cats.append({"id": nid, "ad": ctx.nodes[nid]["name"], "ust_id": parent, "yol": ctx.path(nid), "kaynak": "agac"})
        P = C.PROFILES.c
        with engine.connect() as c:
            rows = c.execute(sa.select(P.book_id, P.node_id, P.resolved_node_id).where(P.tenant_id == tenant)).all()
        book_cat = {}
        for r in rows:
            nid = r.node_id or r.resolved_node_id
            chain = [nid, *ctx.ancestors(nid)] if nid else []
            hit = next((x for x in chain if x in keep), None)
            if hit:
                book_cat[str(r.book_id).upper()] = hit
        return {"categories": cats, "bookCat": book_cat, "tree": {"id": tree["id"], "version": tree.get("version")}}
    except Exception as e:  # noqa: BLE001 — ağaç okunamazsa kitaplığa düşülür, nedeni meta'ya yazılır
        log.info("pazar: H1 ağacı okunamadı: %s", e)
        return None


class CatIndex:
    """Kategori listesinin bellekteki hâli: yol, alt kategoriler, kök."""

    def __init__(self, rows: list[dict[str, Any]]):
        self.nodes = {r["id"]: r for r in rows}
        self.children: dict[Optional[str], list[str]] = defaultdict(list)
        for r in rows:
            self.children[r.get("ust_id")].append(r["id"])

    def path(self, cid: Optional[str]) -> Optional[str]:
        n = self.nodes.get(cid or "")
        return (n.get("yol") or n.get("ad")) if n else None

    def subtree(self, cid: str) -> set[str]:
        out, stack = {cid}, list(self.children.get(cid, []))
        while stack:
            x = stack.pop()
            if x not in out:
                out.add(x)
                stack.extend(self.children.get(x, []))
        return out

    def root(self, cid: Optional[str]) -> Optional[str]:
        seen = set()
        cur = cid
        while cur and cur in self.nodes and self.nodes[cur].get("ust_id") and cur not in seen:
            seen.add(cur)
            cur = self.nodes[cur]["ust_id"]
        return cur if cur in self.nodes else None

    def items(self) -> list[dict[str, Any]]:
        return sorted(({"id": k, "ad": v["ad"], "ustId": v.get("ust_id"), "yol": self.path(k), "kaynak": v["kaynak"]}
                       for k, v in self.nodes.items()), key=lambda x: fold(x["yol"]))


def categories(engine: sa.engine.Engine, tenant: str) -> CatIndex:
    with engine.connect() as c:
        rows = c.execute(sa.select(CATEGORIES).where(CATEGORIES.c.tenant_id == tenant)).mappings().all()
    return CatIndex([dict(r) for r in rows])


# ================================================================================ anlık görüntü


def apply_snapshot(engine: sa.engine.Engine, tenant: str, *, competitors: list[dict[str, Any]],
                   own_books: list[dict[str, Any]], links: list[tuple[str, str]], kitaplik: list[dict[str, Any]],
                   own_sales: Optional[dict[str, Any]], actor: str, errors: Optional[dict[str, str]] = None,
                   okuma: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """CRM ve Logo okumasını köprünün tablolarına yazar (tam yenileme). Onaylı kategori eşlemesi korunur; kategori
    listesi değiştiyse karşılığı kalmayan onaylar «yeni»ye döner ve notu yazılır."""
    st = settings()
    at = now()
    src = st["categorySource"]
    h1 = h1_categories(engine, tenant, st["categoryLevels"]) if src in ("auto", "agac") else None
    if src == "agac" and h1 is None:
        cat_note = "Yürürlükte kategori ağacı yok; CRM Kitaplık listesi kullanıldı."
    else:
        cat_note = None
    if h1:
        cats, book_cat, cat_kind = h1["categories"], h1["bookCat"], "agac"
    else:
        cats = [{"id": k["id"], "ad": k["ad"], "ust_id": None, "yol": k["ad"], "kaynak": "kitaplik"} for k in kitaplik]
        book_cat, cat_kind = {}, "kitaplik"
    cat_ids = {c["id"] for c in cats}

    raw_counts = Counter(c["kategori_ham"] for c in competitors if c.get("kategori_ham"))
    with engine.begin() as c:
        c.execute(CATEGORIES.delete().where(CATEGORIES.c.tenant_id == tenant))
        if cats:
            c.execute(CATEGORIES.insert(), [{"tenant_id": tenant, **x} for x in cats])
        existing = {r.kategori_ham: r for r in c.execute(sa.select(CATEGORY_MAP).where(CATEGORY_MAP.c.tenant_id == tenant)).all()}
        reset = 0
        for ham, n in raw_counts.items():
            r = existing.get(ham)
            if r is None:
                c.execute(CATEGORY_MAP.insert().values(tenant_id=tenant, kategori_ham=ham, kayit_sayisi=n, durum="yeni"))
                continue
            vals: dict[str, Any] = {"kayit_sayisi": n}
            gone = (r.kategori_id and r.kategori_id not in cat_ids) or (r.oneri_kategori_id and r.oneri_kategori_id not in cat_ids)
            if gone:
                vals.update(kategori_id=None, oneri_kategori_id=None, durum="yeni", olasilik=None, marj=None,
                            not_="Kategori listesi değişti; önceki karşılık listede yok.")
                reset += 1
            c.execute(CATEGORY_MAP.update().where(CATEGORY_MAP.c.tenant_id == tenant, CATEGORY_MAP.c.kategori_ham == ham).values(**vals))
        for ham in set(existing) - set(raw_counts):
            if ham.startswith(BASARI_PREFIX):
                # Başarı eşlemesinin sayısı Başarı kataloğundan (`sync_basari_categories`); yalnız kategori listesi
                # değiştiyse karşılığı kalmayan öneri/onay «yeni»ye döner.
                r = existing[ham]
                if (r.kategori_id and r.kategori_id not in cat_ids) or (r.oneri_kategori_id and r.oneri_kategori_id not in cat_ids):
                    c.execute(CATEGORY_MAP.update().where(CATEGORY_MAP.c.tenant_id == tenant, CATEGORY_MAP.c.kategori_ham == ham)
                              .values(kategori_id=None, oneri_kategori_id=None, durum="yeni", olasilik=None, marj=None,
                                      not_="Kategori listesi değişti; önceki karşılık listede yok."))
                    reset += 1
                continue
            c.execute(CATEGORY_MAP.update().where(CATEGORY_MAP.c.tenant_id == tenant, CATEGORY_MAP.c.kategori_ham == ham)
                      .values(kayit_sayisi=0))
        approved = {r.kategori_ham: r.kategori_id for r in c.execute(
            sa.select(CATEGORY_MAP.c.kategori_ham, CATEGORY_MAP.c.kategori_id).where(
                CATEGORY_MAP.c.tenant_id == tenant, CATEGORY_MAP.c.durum == "onaylandi")).all()}
        c.execute(COMPETITORS.delete().where(COMPETITORS.c.tenant_id == tenant))
        batch = [{"tenant_id": tenant, **x, "kategori_id": approved.get(x.get("kategori_ham") or ""), "kopyalandi_at": at}
                 for x in competitors]
        for i in range(0, len(batch), 2000):
            c.execute(COMPETITORS.insert(), batch[i:i + 2000])
        c.execute(OWN_BOOKS.delete().where(OWN_BOOKS.c.tenant_id == tenant))
        own = []
        for b in own_books:
            kid = book_cat.get(b["crm_id"]) if cat_kind == "agac" else (b.get("kitaplik_id") if b.get("kitaplik_id") in cat_ids else None)
            own.append({"tenant_id": tenant, **b, "kategori_id": kid, "kopyalandi_at": at})
        for i in range(0, len(own), 2000):
            c.execute(OWN_BOOKS.insert(), own[i:i + 2000])
        c.execute(LINKS.delete().where(LINKS.c.tenant_id == tenant))
        uniq = sorted(set(links))
        if uniq:
            c.execute(LINKS.insert(), [{"tenant_id": tenant, "kitap_crm_id": k, "rakip_crm_id": r} for k, r in uniq])
        if own_sales is not None:
            c.execute(OWN_SALES.delete().where(OWN_SALES.c.tenant_id == tenant))
            rows = [{"tenant_id": tenant, **r} for r in own_sales["rows"]]
            for i in range(0, len(rows), 2000):
                c.execute(OWN_SALES.insert(), rows[i:i + 2000])
    prev = meta_get(engine, tenant, "snapshot", {}) or {}
    info = {"at": iso(at), "by": actor, "competitors": len(competitors), "ownBooks": len(own_books), "links": len(uniq),
            "categories": len(cats), "categorySource": cat_kind, "categoryNote": cat_note,
            "h1Tree": (h1 or {}).get("tree"), "rawCategories": len(raw_counts), "mappingReset": reset,
            "ownSales": ({k: v for k, v in own_sales.items() if k != "rows"} | {"rows": len(own_sales["rows"])})
            if own_sales is not None else prev.get("ownSales"),
            "ownSalesAt": iso(at) if own_sales is not None else prev.get("ownSalesAt"), "errors": errors or {},
            # Sorgu bilgisi: CRM okumasının şeması ve tanıtım kesimi (asıl SQL bunlarla yeniden kurulur).
            "okuma": okuma or prev.get("okuma")}
    meta_set(engine, tenant, "snapshot", info)
    return info


# ================================================================================ Başarı Dağıtım kataloğu (ikinci rakip kaynağı)
#
# Başarı'nın güncel kataloğu `pazar_dagitim` tablolarındadır (her gün okunur, yalnız değişen satır saklanır). Rakip
# olarak yalnız son görüntüde bulunan ve TİMAŞ grubu dışındaki başlıklar alınır (`timas` bayrağı Logo barkod oranıyla,
# `pazar_dagitim.mark_timas`). Başarı'nın «Üst>Alt» kategorisi CRM ham kategorisiyle aynı eşleme hattından geçer
# (ad eşleşmesi → Zeki AI önerisi → insan kararı); anahtar «basari:» önekiyle ayrılır. Portal Başarı tablolarına yazmaz.


def check_kaynak(kaynak: Optional[str]) -> str:
    k = (kaynak or "crm").strip().lower()
    if k not in RAKIP_KAYNAK:
        raise PazarError("Rakip kaynağı «basari» ya da «crm» olmalı.")
    return k


def map_key(kaynak: str, ham: str) -> str:
    """Eşleme tablosundaki anahtar (kolon 300 karakter)."""
    return (BASARI_PREFIX + ham)[:300] if kaynak == "basari" else ham


def split_key(key: str) -> tuple[str, str]:
    """Eşleme anahtarı → (kaynak, ekranda görünen ham kategori)."""
    return ("basari", key[len(BASARI_PREFIX):]) if key.startswith(BASARI_PREFIX) else ("crm", key)


def _key_cond(kaynak: str) -> Any:
    like = CATEGORY_MAP.c.kategori_ham.like(BASARI_PREFIX + "%")
    return like if kaynak == "basari" else sa.not_(like)


def _dagitim(engine: sa.engine.Engine) -> Any:
    from semantic_bridge import pazar_dagitim as D

    D.ensure(engine)
    return D


def _basari_cond(D: Any, tenant: str, tarih: date) -> list[Any]:
    T = D.TITLES.c
    return [T.tenant_id == tenant, T.kaynak == "basari", T.timas.is_(False), T.son_gorulme == tarih]


def basari_catalog(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Başarı kataloğunun portaldaki son görüntüsü: kaynağın kendi tarihi, portalın okuduğu an, ilk görüntü, görüntü
    sayısı ve rakip olarak kullanılan (TİMAŞ grubu dışı) başlık sayısı. Okunmadıysa `tarih` None."""
    D = _dagitim(engine)
    S = D.SNAPS.c
    with engine.connect() as c:
        last = c.execute(sa.select(S.tarih, S.okundu_at, S.satir).where(S.tenant_id == tenant, S.kaynak == "basari")
                         .order_by(S.tarih.desc()).limit(1)).first()
        first, n_snap = c.execute(sa.select(sa.func.min(S.tarih), sa.func.count()).where(
            S.tenant_id == tenant, S.kaynak == "basari")).first()
        n = c.execute(sa.select(sa.func.count()).select_from(D.TITLES).where(
            *_basari_cond(D, tenant, last.tarih))).scalar() if last else 0
    return {"kaynak": "basari", "ad": RAKIP_KAYNAK["basari"], "tarih": last.tarih.isoformat() if last else None,
            "okundu": iso(last.okundu_at) if last else None, "satir": int(last.satir) if last else None,
            "ilk": first.isoformat() if first else None, "goruntu": int(n_snap or 0), "rakip": int(n or 0)}


def rakip_sources(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    """Ekrandaki kaynak seçicinin satırları: Başarı (kataloğun kendi tarihi) ve CRM (portalın okuduğu gün)."""
    b = basari_catalog(engine, tenant)
    snap = meta_get(engine, tenant, "snapshot", {}) or {}
    with engine.connect() as c:
        n = c.execute(sa.select(sa.func.count()).select_from(COMPETITORS).where(COMPETITORS.c.tenant_id == tenant)).scalar() or 0
    return [{"kaynak": "basari", "ad": RAKIP_KAYNAK["basari"], "tarih": b["tarih"], "kayit": b["rakip"], "hazir": bool(b["tarih"])},
            {"kaynak": "crm", "ad": RAKIP_KAYNAK["crm"], "tarih": (snap.get("at") or "")[:10] or None, "kayit": int(n),
             "hazir": bool(n)}]


def sync_basari_categories(engine: sa.engine.Engine, tenant: str, *, force: bool = False) -> dict[str, Any]:
    """Başarı'nın ham kategorilerini (TİMAŞ dışı, son görüntü) eşleme tablosuna yazar: yeni kategori «yeni» durumla
    girer, var olanın kayıt sayısı yenilenir, katalogdan düşenin sayısı 0 olur (kararı silinmez). Aynı görüntü ve aynı
    dağıtımcı turu için ikinci kez çalışmaz (`force` hariç). Onaylı eşleme korunur."""
    D = _dagitim(engine)
    cat = basari_catalog(engine, tenant)
    if not cat["tarih"]:
        return {"skipped": "Başarı Dağıtım kataloğu henüz okunmadı."}
    run = D.meta_get(engine, tenant, "last_run", {}) or {}
    sig = f"{cat['tarih']}|{run.get('at') or ''}"
    prev = meta_get(engine, tenant, "basari_map", {}) or {}
    if not force and prev.get("imza") == sig:
        return prev
    T = D.TITLES.c
    counts: Counter = Counter()
    with engine.connect() as c:
        for k, n in c.execute(sa.select(T.kategori, sa.func.count()).where(
                *_basari_cond(D, tenant, date.fromisoformat(cat["tarih"])), T.kategori.isnot(None)).group_by(T.kategori)).all():
            if k and str(k).strip():
                counts[map_key("basari", str(k))] += int(n)
    M = CATEGORY_MAP.c
    with engine.begin() as c:
        existing = {r.kategori_ham: int(r.kayit_sayisi or 0) for r in c.execute(
            sa.select(M.kategori_ham, M.kayit_sayisi).where(M.tenant_id == tenant, _key_cond("basari"))).all()}
        new = [{"tenant_id": tenant, "kategori_ham": k, "kayit_sayisi": n, "durum": "yeni"}
               for k, n in counts.items() if k not in existing]
        for i in range(0, len(new), 1000):
            c.execute(CATEGORY_MAP.insert(), new[i:i + 1000])
        for k, n in counts.items():
            if k in existing and existing[k] != n:
                c.execute(CATEGORY_MAP.update().where(M.tenant_id == tenant, M.kategori_ham == k).values(kayit_sayisi=n))
        for k in set(existing) - set(counts):
            if existing[k]:
                c.execute(CATEGORY_MAP.update().where(M.tenant_id == tenant, M.kategori_ham == k).values(kayit_sayisi=0))
    info = {"imza": sig, "tarih": cat["tarih"], "kategori": len(counts), "kayit": sum(counts.values()), "yeni": len(new),
            "at": iso(now())}
    meta_set(engine, tenant, "basari_map", info)
    return info


def _approved_maps(c: Any, tenant: str) -> dict[str, tuple[Optional[str], Optional[str], str]]:
    """Eşleme anahtarı → (onaylı kategori, öneri, durum)."""
    M = CATEGORY_MAP.c
    return {r.kategori_ham: (r.kategori_id, r.oneri_kategori_id, r.durum) for r in c.execute(
        sa.select(M.kategori_ham, M.kategori_id, M.oneri_kategori_id, M.durum).where(M.tenant_id == tenant)).all()}


def _basari_rows(engine: sa.engine.Engine, tenant: str, *cond: Any) -> tuple[list[Any], dict[str, Any]]:
    """Başarı rakip başlıkları (son görüntü, TİMAŞ dışı) ve katalog bilgisi. Katalog okunmadıysa 409."""
    cat = basari_catalog(engine, tenant)
    if not cat["tarih"]:
        raise PazarError("Başarı Dağıtım kataloğu henüz okunmadı; «CRM rakip kayıtları» kaynağını seçin ya da "
                         "dağıtımcı kataloglarının okunmasını bekleyin.", 409)
    D = _dagitim(engine)
    T = D.TITLES.c
    with engine.connect() as c:
        rows = c.execute(sa.select(T.barkod, T.ad, T.yazar, T.yayinevi, T.kategori, T.sayfa, T.kapak, T.kagit, T.basim_yili,
                                   T.stok, T.fiyat, T.durum, T.baski_no, T.ilk_gorulme)
                         .where(*_basari_cond(D, tenant, date.fromisoformat(cat["tarih"])), *cond)
                         .order_by(T.ilk_gorulme.desc(), T.ad)).all()
    return rows, cat


def _basari_new_since(cat: dict[str, Any], new_days: int) -> Optional[str]:
    """Başarı'da «son N günde eklenen» = kataloğa ilk görüntüden SONRA giren başlık (ilk görüntüdekilerin giriş günü
    bilinmez). Tek görüntü varsa bilinmez: None (ekranda «—»)."""
    if cat["goruntu"] < 2 or not cat["ilk"]:
        return None
    since = today() - timedelta(days=new_days)
    first_next = date.fromisoformat(cat["ilk"]) + timedelta(days=1)
    return max(since, first_next).isoformat()


# ================================================================================ tazelik


def freshness(engine: sa.engine.Engine, tenant: str, kaynak: str = "crm") -> dict[str, Any]:
    if check_kaynak(kaynak) == "basari":
        return basari_freshness(engine, tenant)
    st = settings()
    C = COMPETITORS.c
    with engine.connect() as c:
        n, cmin, cmax, mmax = c.execute(sa.select(sa.func.count(), sa.func.min(C.crm_created), sa.func.max(C.crm_created),
                                                  sa.func.max(C.crm_modified)).where(C.tenant_id == tenant)).first()
        years = c.execute(sa.select(sa.func.substr(C.crm_created, 1, 4).label("y"), sa.func.count()).where(
            C.tenant_id == tenant).group_by(sa.func.substr(C.crm_created, 1, 4))).all()
        nlinks = c.execute(sa.select(sa.func.count()).select_from(LINKS).where(LINKS.c.tenant_id == tenant)).scalar() or 0
    last = max([x for x in (cmax, mmax) if x] or [None]) if (cmax or mmax) else None
    age = (today() - _day(last)).days if _day(last) else None
    snap = meta_get(engine, tenant, "snapshot", {}) or {}
    return {"records": int(n or 0), "firstCreated": cmin, "lastCreated": cmax, "lastModified": mmax, "lastChange": last,
            "ageDays": age, "staleDays": st["staleDays"], "stale": age is not None and age > st["staleDays"],
            "byYear": sorted(({"yil": y or "?", "kayit": k} for y, k in years), key=lambda x: x["yil"]),
            "crmLinks": nlinks, "snapshotAt": snap.get("at"), "ownSalesAt": snap.get("ownSalesAt"),
            "dataEnd": (snap.get("ownSales") or {}).get("dataEnd"),
            "note": "Rakip kitap verisinin kaynağı ve toplanma yöntemi CRM'de kayıtlı değil; «satış adedi» alanlarının "
                    "anlamı bilinmediği için hiçbir hesapta kullanılmaz.",
            "kaynak": "crm", "kaynakAd": RAKIP_KAYNAK["crm"]}


def basari_freshness(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Başarı kataloğunun tazeliği: kataloğun kendi tarihi (kaynak kendi üstüne yazar, geçmiş tutmaz), portalın okuduğu
    an, rakip olarak kullanılan başlık sayısı. Eşik `PAZAR_BASARI_STALE_DAYS` (katalog her gün okunur)."""
    st = settings()
    b = basari_catalog(engine, tenant)
    d = _day(b["tarih"])
    age = (today() - d).days if d else None
    return {"kaynak": "basari", "kaynakAd": RAKIP_KAYNAK["basari"], "records": b["rakip"], "katalogTarihi": b["tarih"],
            "firstCreated": b["ilk"], "lastCreated": None, "lastModified": None, "lastChange": b["tarih"],
            "ageDays": age, "staleDays": st["basariStaleDays"], "stale": age is not None and age > st["basariStaleDays"],
            "byYear": [], "crmLinks": 0, "snapshotAt": b["okundu"], "goruntu": b["goruntu"], "katalogSatir": b["satir"],
            "ownSalesAt": None, "dataEnd": None,
            "note": "Başarı Dağıtım kataloğu her gün okunur; rakip olarak TİMAŞ grubu dışındaki başlıklar kullanılır. "
                    "Fiyat kataloğun liste fiyatıdır; stok dağıtımcı deposudur, okura satış değildir."}


# ================================================================================ kategori eşlemesi


def _map_out(r: Any, idx: CatIndex, samples: Optional[list[str]] = None) -> dict[str, Any]:
    m = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
    kaynak, ad = split_key(m["kategori_ham"])
    return {"ham": m["kategori_ham"], "ad": ad, "kaynak": kaynak, "kaynakAd": RAKIP_KAYNAK[kaynak],
            "kayit": m["kayit_sayisi"], "durum": m["durum"], "durumAd": MAP_STATUS.get(m["durum"]),
            "oneriId": m["oneri_kategori_id"], "oneriYol": idx.path(m["oneri_kategori_id"]),
            "kategoriId": m["kategori_id"], "kategoriYol": idx.path(m["kategori_id"]), "olasilik": m["olasilik"],
            "marj": m["marj"], "yontem": m["yontem"], "oneren": m["oneren"], "onaylayan": m["onaylayan"],
            "kararAt": iso(m["karar_at"]), "not": m["not_"], "kanit": loads(m.get("kanit_json"), None),
            **({"ornekler": samples} if samples is not None else {})}


def _basari_samples(engine: sa.engine.Engine, tenant: str, keys: list[str], n: int = 3) -> dict[str, list[str]]:
    """Başarı ham kategorisindeki örnek başlıklar (son görüntü, TİMAŞ dışı)."""
    out: dict[str, list[str]] = {}
    if not keys:
        return out
    cat = basari_catalog(engine, tenant)
    if not cat["tarih"]:
        return out
    D = _dagitim(engine)
    T = D.TITLES.c
    cond = _basari_cond(D, tenant, date.fromisoformat(cat["tarih"]))
    with engine.connect() as c:
        for k in keys:
            out[k] = [r[0] for r in c.execute(sa.select(T.ad).where(*cond, T.kategori == split_key(k)[1], T.ad.isnot(None))
                                              .order_by(T.ad).limit(n)).all()]
    return out


def category_map(engine: sa.engine.Engine, tenant: str, *, durum: str = "", q: str = "", page: int = 0,
                 page_size: int = 50, kaynak: str = "") -> dict[str, Any]:
    """Eşleme listesi. `kaynak` boşsa iki kaynak birlikte; «crm» ya da «basari» ise sayaçlar ve kapsam da o kaynağın."""
    M = CATEGORY_MAP.c
    base = [M.tenant_id == tenant, M.kayit_sayisi > 0]
    if kaynak:
        base.append(_key_cond(check_kaynak(kaynak)))
    cond = list(base)
    if durum:
        cond.append(M.durum.in_([d for d in durum.split(",") if d in MAP_STATUS]))
    idx = categories(engine, tenant)
    with engine.connect() as c:
        rows = c.execute(sa.select(CATEGORY_MAP).where(*cond).order_by(M.kayit_sayisi.desc(), M.kategori_ham)).all()
        if q:
            f = fold(q)
            rows = [r for r in rows if f in fold(split_key(r.kategori_ham)[1])]
        counts = dict(c.execute(sa.select(M.durum, sa.func.count()).where(*base).group_by(M.durum)).all())
        recs = dict(c.execute(sa.select(M.durum, sa.func.sum(M.kayit_sayisi)).where(*base).group_by(M.durum)).all())
        chunk = rows[page * page_size:(page + 1) * page_size]
        samples: dict[str, list[str]] = defaultdict(list)
        crm_keys = [x.kategori_ham for x in chunk if not x.kategori_ham.startswith(BASARI_PREFIX)]
        if crm_keys:
            for r in c.execute(sa.select(COMPETITORS.c.kategori_ham, COMPETITORS.c.ad).where(
                    COMPETITORS.c.tenant_id == tenant, COMPETITORS.c.kategori_ham.in_(crm_keys))
                    .order_by(COMPETITORS.c.crm_created.desc())).all():
                if len(samples[r.kategori_ham]) < 3:
                    samples[r.kategori_ham].append(r.ad)
    samples.update(_basari_samples(engine, tenant, [x.kategori_ham for x in chunk if x.kategori_ham.startswith(BASARI_PREFIX)]))
    total_recs = sum(float(v or 0) for v in recs.values())
    return {"items": [_map_out(r, idx, samples.get(r.kategori_ham, [])) for r in chunk], "total": len(rows), "page": page,
            "pageSize": page_size, "counts": {k: int(v) for k, v in counts.items()},
            "coverage": {"records": int(total_recs), "approved": int(recs.get("onaylandi") or 0),
                         "noMatch": int(recs.get("reddedildi") or 0)},
            "kaynak": kaynak or None, "kaynakAd": RAKIP_KAYNAK.get(kaynak) if kaynak else None,
            "categories": idx.items(), "statusLabels": MAP_STATUS}


def to_suggest(engine: sa.engine.Engine, tenant: str, hams: Optional[list[str]] = None, kaynak: str = "") -> list[str]:
    """Öneri sırası: öneri bekleyen ham kategoriler, kayıt sayısı büyükten küçüğe (`kaynak` verilirse yalnız o kaynak)."""
    M = CATEGORY_MAP.c
    cond = [M.tenant_id == tenant, M.kayit_sayisi > 0]
    cond.append(M.kategori_ham.in_(hams) if hams else M.durum == "yeni")
    if kaynak:
        cond.append(_key_cond(check_kaynak(kaynak)))
    with engine.connect() as c:
        return [r[0] for r in c.execute(sa.select(M.kategori_ham).where(*cond).order_by(M.kayit_sayisi.desc())).all()]


def suggest_mapping(engine: sa.engine.Engine, tenant: str, hams: list[str], choose: Optional[Callable[[str, list[str]], Any]],
                    actor: str, budget_sec: float) -> dict[str, Any]:
    """Ham kategoriye TİMAŞ kategorisi önerir. Önce ad eşleşmesi (kurallı; yine insan onaylar), sonra Zeki AI kapalı
    küme seçimi (olasılıkla). Emin olunmayan «belirsiz»e düşer; model hiç cevap vermezse iş durur, sıra korunur."""
    import time as _t

    st = settings()
    idx = categories(engine, tenant)
    if not idx.nodes:
        raise PazarError("Kategori listesi boş; önce kaynakları yenileyin.", 409)
    by_name: dict[str, list[str]] = defaultdict(list)
    for cid, n in idx.nodes.items():
        by_name[fold(n["ad"])].append(cid)
    paths = {idx.path(cid): cid for cid in idx.nodes}
    options = sorted(paths, key=fold)
    t0 = _t.monotonic()
    done, stopped, calls = Counter(), None, 0
    for ham in hams:
        if _t.monotonic() - t0 > budget_sec:
            stopped = "süre bütçesi doldu"
            break
        kaynak, raw = split_key(ham)
        segs = [s for s in re.split(r"\s*(?:>|/|;|,|\|)\s*", raw) if s.strip()]
        hit = by_name.get(fold(raw)) or (by_name.get(fold(segs[-1])) if segs else None)
        vals: dict[str, Any] = {"oneren": actor, "onerildi_at": now()}
        if hit and len(hit) == 1:
            vals.update(oneri_kategori_id=hit[0], olasilik=1.0, marj=1.0, yontem="ad", durum="oneri",
                        kanit_json=dumps({"yontem": "ad eşleşmesi"}))
        elif choose is None:
            stopped = "Zeki AI bu kurulumda tanımlı değil; yalnız ad eşleşmeleri önerildi."
            continue
        else:
            if kaynak == "basari":
                ex = _basari_samples(engine, tenant, [ham]).get(ham, [])
                head = ("Bir kitap dağıtımcısının kataloğundaki kategori (üst kategori > alt kategori) aşağıda. TİMAŞ'ın "
                        "kategori listesinde hangisine karşılık gelir? Tam karşılık yoksa en yakın geniş kategoriyi seç.\n\n")
            else:
                with engine.connect() as c:
                    ex = [r[0] for r in c.execute(sa.select(COMPETITORS.c.ad).where(
                        COMPETITORS.c.tenant_id == tenant, COMPETITORS.c.kategori_ham == ham).limit(3)).all()]
                head = ("Bir rakip yayınevinin kitap kaydındaki kategori adı aşağıda. TİMAŞ'ın kategori listesinde "
                        "hangisine karşılık gelir? Tam karşılık yoksa en yakın geniş kategoriyi seç.\n\n")
            prompt = (head + f"Rakip kategori: «{raw}»\n"
                      + (("Bu kategorideki örnek kitaplar: " + "; ".join(f"«{x}»" for x in ex) + "\n") if ex else ""))
            try:
                r = choose(prompt, options)
            except Exception as e:  # noqa: BLE001 — model kesintisi: bu tur durur
                stopped = f"Zeki AI cevap vermedi: {str(e)[:160]}"
                break
            calls += int(getattr(r, "calls", 1) or 1)
            best = paths.get(getattr(r, "choice", None) or "")
            probs = getattr(r, "probs", None) or {}
            top = sorted(probs.items(), key=lambda kv: -kv[1])[:3]
            ok = bool(best) and r.confident(st["mapMinProb"], min_margin=st["mapMinMargin"])
            vals.update(oneri_kategori_id=best, olasilik=getattr(r, "probability", None), marj=getattr(r, "margin", None),
                        yontem="zeki", durum="oneri" if ok else "belirsiz",
                        kanit_json=dumps({"yontem": getattr(r, "method", None), "adaylar": [[k, round(v, 4)] for k, v in top]}))
        with engine.begin() as c:
            c.execute(CATEGORY_MAP.update().where(CATEGORY_MAP.c.tenant_id == tenant, CATEGORY_MAP.c.kategori_ham == ham,
                                                  CATEGORY_MAP.c.durum.in_(("yeni", "oneri", "belirsiz"))).values(**vals))
        done[vals.get("durum", "atlandi")] += 1
    return {"queued": len(hams), "done": dict(done), "remaining": len(hams) - sum(done.values()), "stopped": stopped,
            "modelCalls": calls}


def decide_mapping(engine: sa.engine.Engine, tenant: str, actor: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Eşleme kararı (toplu): `onayla` (öneri ya da verilen kategori), `duzelt` (kategori şart), `reddet` (TİMAŞ
    kategorisinde karşılığı yok). Rakip kayıtlarının kategorisi hemen güncellenir."""
    idx = categories(engine, tenant)
    out, errors = [], []
    with engine.begin() as c:
        for it in items:
            ham = str(it.get("ham") or "").strip()
            karar = str(it.get("karar") or "")
            r = c.execute(sa.select(CATEGORY_MAP).where(CATEGORY_MAP.c.tenant_id == tenant, CATEGORY_MAP.c.kategori_ham == ham)).first()
            if r is None:
                errors.append({"ham": ham, "neden": "Ham kategori bulunamadı."})
                continue
            kid = it.get("kategoriId") or None
            if karar == "onayla":
                kid = kid or r.oneri_kategori_id
                durum, yontem = "onaylandi", r.yontem if not it.get("kategoriId") else "elle"
            elif karar == "duzelt":
                durum, yontem = "onaylandi", "elle"
            elif karar == "reddet":
                kid, durum, yontem = None, "reddedildi", r.yontem
            else:
                errors.append({"ham": ham, "neden": "Karar onayla, duzelt ya da reddet olmalı."})
                continue
            if durum == "onaylandi" and (not kid or kid not in idx.nodes):
                errors.append({"ham": ham, "neden": "Geçerli bir TİMAŞ kategorisi seçilmedi."})
                continue
            c.execute(CATEGORY_MAP.update().where(CATEGORY_MAP.c.tenant_id == tenant, CATEGORY_MAP.c.kategori_ham == ham).values(
                kategori_id=kid, durum=durum, yontem=yontem, onaylayan=actor, karar_at=now(),
                not_=(str(it.get("not") or "")[:300] or None)))
            c.execute(COMPETITORS.update().where(COMPETITORS.c.tenant_id == tenant, COMPETITORS.c.kategori_ham == ham)
                      .values(kategori_id=kid))
            out.append({"ham": ham, "durum": durum, "kategoriId": kid, "kategoriYol": idx.path(kid)})
    if not out and errors:
        raise PazarError(errors[0]["neden"])
    return {"decided": out, "errors": errors}


# ================================================================================ matris ve rakip listesi


def _effective_cat(kid: Optional[str], key: Optional[str], maps: dict[str, Any], include_suggested: bool) -> Optional[str]:
    """Rakip kaydının TİMAŞ kategorisi: onaylı eşleme; istenirse onay bekleyen öneri. `maps`: anahtar → (onaylı, öneri,
    durum) (`_approved_maps`)."""
    m = maps.get(key or "") if key else None
    if kid:
        return kid
    if m is not None and m[2] == "onaylandi" and m[0]:
        return m[0]
    if include_suggested and m is not None and m[2] == "oneri":
        return m[1]
    return None


def _stats(books: list[dict[str, Any]], new_since: Optional[str]) -> dict[str, Any]:
    prices = [b["fiyat"] for b in books if b.get("fiyat") and b["fiyat"] > 0]
    pages = [float(b["sayfa"]) for b in books if b.get("sayfa") and b["sayfa"] > 0]
    ppp = [b["fiyat"] / b["sayfa"] for b in books if b.get("fiyat") and b["fiyat"] > 0 and b.get("sayfa") and b["sayfa"] > 0]
    cilt = Counter(b.get("cilt") for b in books if b.get("cilt"))
    return {"kitap": len(books), "fiyatli": len(prices), "medyan": percentile(prices, 0.5), "q1": percentile(prices, 0.25),
            "q3": percentile(prices, 0.75), "min": min(prices) if prices else None, "max": max(prices) if prices else None,
            "sayfaMedyan": percentile(pages, 0.5), "sayfaBasiMedyan": percentile(ppp, 0.5),
            "yeni": sum(1 for b in books if new_since and (b.get("created") or "") >= new_since) if new_since else None,
            "cilt": [{"ad": k, "kitap": v} for k, v in cilt.most_common(3)]}


def _rakip_matrix_rows(engine: sa.engine.Engine, tenant: str, kaynak: str) -> tuple[list[tuple], Optional[dict[str, Any]]]:
    """Matrisin rakip satırları: (yayınevi, fiyat, sayfa, cilt, eklenme günü, onaylı kategori, eşleme anahtarı)."""
    if kaynak == "basari":
        rows, cat = _basari_rows(engine, tenant)
        return [(r.yayinevi, r.fiyat, r.sayfa, r.kapak, r.ilk_gorulme.isoformat() if r.ilk_gorulme else "", None,
                 map_key("basari", r.kategori) if r.kategori else None) for r in rows], cat
    Cc = COMPETITORS.c
    with engine.connect() as c:
        comp = c.execute(sa.select(Cc.yayinevi, Cc.liste_fiyat, Cc.sayfa, Cc.cilt, Cc.crm_created, Cc.kategori_id,
                                   Cc.kategori_ham).where(Cc.tenant_id == tenant)).all()
    return [(r.yayinevi, r.liste_fiyat, r.sayfa, r.cilt, (r.crm_created or "")[:10], r.kategori_id, r.kategori_ham)
            for r in comp], None


def matrix(engine: sa.engine.Engine, tenant: str, *, kategori: str = "", include_suggested: bool = False,
           sayfa_min: Optional[int] = None, sayfa_max: Optional[int] = None, yayinevi_q: str = "",
           watch_only: bool = False, kaynak: str = "crm") -> dict[str, Any]:
    """Yayınevi × (seçili kategori) fiyat, sayfa ve format özeti; TİMAŞ satırları (marka ve toplam) aynı ölçülerle.
    Medyan ve çeyrekler SQL Server `PERCENTILE_CONT` ile aynı yöntemle; fiyatı 0/boş kayıt fiyat ölçüsüne girmez.
    `kaynak`: «crm» (CRM rakip kayıtları) ya da «basari» (Başarı kataloğu, TİMAŞ grubu dışı başlıklar, liste fiyatı)."""
    kaynak = check_kaynak(kaynak)
    st = settings()
    idx = categories(engine, tenant)
    allowed = idx.subtree(kategori) if kategori else None
    if kategori and kategori not in idx.nodes:
        raise PazarError("Kategori listede yok.", 404)
    comp, cat = _rakip_matrix_rows(engine, tenant, kaynak)
    own_since = (today() - timedelta(days=st["newDays"])).isoformat()
    new_since = _basari_new_since(cat, st["newDays"]) if cat else own_since
    with engine.connect() as c:
        maps = _approved_maps(c, tenant)
        own = c.execute(sa.select(OWN_BOOKS.c.marka, OWN_BOOKS.c.fiyat, OWN_BOOKS.c.sayfa, OWN_BOOKS.c.cilt,
                                  OWN_BOOKS.c.ilk_yayin, OWN_BOOKS.c.kategori_id).where(OWN_BOOKS.c.tenant_id == tenant)).all()
        watch = c.execute(sa.select(WATCHLIST).where(WATCHLIST.c.tenant_id == tenant)).all()
    watched = {fold(w.yayinevi) for w in watch if not w.kategori_id or (kategori and w.kategori_id in (allowed or set()))}

    def page_ok(p: Optional[int]) -> bool:
        if sayfa_min is None and sayfa_max is None:
            return True
        if not p:
            return False
        return (sayfa_min is None or p >= sayfa_min) and (sayfa_max is None or p <= sayfa_max)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmapped = 0
    for yayinevi, fiyat, sayfa, cilt, created, kid, key in comp:
        if allowed is not None:
            cat_id = _effective_cat(kid, key, maps, include_suggested)
            if not cat_id:
                unmapped += 1
                continue
            if cat_id not in allowed:
                continue
        if not page_ok(sayfa):
            continue
        groups[yayinevi or "(yayınevi yok)"].append({"fiyat": fiyat, "sayfa": sayfa, "cilt": cilt, "created": created})
    rows = []
    f = fold(yayinevi_q)
    for name, books in groups.items():
        if f and f not in fold(name):
            continue
        w = fold(name) in watched
        if watch_only and not w:
            continue
        rows.append({"yayinevi": name, "own": False, "watched": w, **_stats(books, new_since)})
    rows.sort(key=lambda x: (-x["kitap"], fold(x["yayinevi"])))
    own_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in own:
        if allowed is not None and (not r.kategori_id or r.kategori_id not in allowed):
            continue
        if not page_ok(r.sayfa):
            continue
        b = {"fiyat": r.fiyat, "sayfa": r.sayfa, "cilt": r.cilt, "created": r.ilk_yayin or ""}
        own_groups[r.marka or "(marka yok)"].append(b)
    all_own = [b for v in own_groups.values() for b in v]
    own_rows = [{"yayinevi": "TİMAŞ (tümü)", "own": True, "total": True, "watched": False, **_stats(all_own, own_since)}]
    own_rows += sorted(({"yayinevi": k, "own": True, "watched": False, **_stats(v, own_since)} for k, v in own_groups.items()),
                       key=lambda x: -x["kitap"])
    all_comp = [b for v in groups.values() for b in v]
    comp_prices = sorted(b["fiyat"] for b in all_comp if b.get("fiyat") and b["fiyat"] > 0)
    own_med = own_rows[0]["medyan"]
    position = (sum(1 for p in comp_prices if p < own_med) / len(comp_prices)) if (own_med is not None and comp_prices) else None
    rakip_fiyat = ("rakip fiyatı Başarı Dağıtım kataloğundaki liste fiyatıdır (TİMAŞ grubu dışındaki başlıklar)"
                   if kaynak == "basari" else "rakip fiyatı CRM «Rakip Kitap» kaydındaki liste fiyatıdır")
    return {"kaynak": kaynak, "kaynakAd": RAKIP_KAYNAK[kaynak], "katalogTarihi": cat["tarih"] if cat else None,
            "kategori": {"id": kategori, "yol": idx.path(kategori)} if kategori else None,
            "includeSuggested": include_suggested, "sayfa": {"min": sayfa_min, "max": sayfa_max},
            "rakipOzet": {"yayinevi": len(groups), **_stats(all_comp, new_since)}, "timas": own_rows, "rows": rows,
            "timasKonum": position, "eslenmemis": unmapped if allowed is not None else None,
            "newDays": st["newDays"],
            "yeniNot": ("Başarı'da «son günlerde eklenen», kataloğa portalın ilk görüntüsünden sonra giren başlıktır; "
                        + ("tek görüntü olduğu için henüz bilinmiyor." if new_since is None else f"{new_since} ve sonrası."))
            if kaynak == "basari" else None,
            "note": f"TİMAŞ fiyatı CRM'deki KDV dahil fiyattır; {rakip_fiyat}. "
                    "Kategori süzgecinde yalnız eşlemesi onaylı rakip kayıtlar sayılır"
                    + (" (önerilenler de dahil edildi)." if include_suggested else ".")}


def matrix_csv(m: dict[str, Any]) -> bytes:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Yayınevi", "TİMAŞ", "Kitap", "Fiyatlı", "Medyan fiyat", "Alt çeyrek", "Üst çeyrek", "En düşük",
                "En yüksek", "Medyan sayfa", "Sayfa başı medyan", f"Son {m['newDays']} günde eklenen"])
    for r in m["timas"] + m["rows"]:
        w.writerow([r["yayinevi"], "evet" if r["own"] else "", r["kitap"], r["fiyatli"],
                    *(fmt_tr(r[k], 2) if r[k] is not None else "" for k in ("medyan", "q1", "q3", "min", "max")),
                    fmt_tr(r["sayfaMedyan"], 0) if r["sayfaMedyan"] is not None else "",
                    fmt_tr(r["sayfaBasiMedyan"], 3) if r["sayfaBasiMedyan"] is not None else "", r["yeni"] if r["yeni"] is not None else ""])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _basari_competitors(engine: sa.engine.Engine, tenant: str, idx: CatIndex, *, yayinevi: str, kategori: str, q: str,
                        durum: str, page: int, page_size: int) -> dict[str, Any]:
    D = _dagitim(engine)
    T = D.TITLES.c
    rows, cat = _basari_rows(engine, tenant, *([T.yayinevi == yayinevi] if yayinevi else []))
    with engine.connect() as c:
        maps = _approved_maps(c, tenant)

    def kid(r: Any) -> Optional[str]:
        m = maps.get(map_key("basari", r.kategori)) if r.kategori else None
        return m[0] if m is not None and m[2] == "onaylandi" else None

    if kategori:
        allowed = idx.subtree(kategori)
        rows = [r for r in rows if kid(r) in allowed]
    if durum == "eslenmemis":
        rows = [r for r in rows if not kid(r)]
    if q:
        f = fold(q)
        rows = [r for r in rows if f in fold(r.ad) or f in fold(r.yazar) or f in r.barkod]
    chunk = rows[page * page_size:(page + 1) * page_size]
    items = []
    for r in chunk:
        k = kid(r)
        items.append({"crmId": r.barkod, "kaynak": "basari", "ad": r.ad, "yayinevi": r.yayinevi, "yazarlar": r.yazar,
                      "isbn": r.barkod, "fiyat": r.fiyat, "sayfa": r.sayfa, "cilt": r.kapak, "kagit": r.kagit,
                      "baski": r.baski_no, "dil": None, "kategoriHam": r.kategori, "kategoriId": k, "kategoriYol": idx.path(k),
                      "satisDurumu": r.durum, "satisAdediHam": None, "satisAdedi2Ham": None,
                      "olusturma": r.ilk_gorulme.isoformat() if r.ilk_gorulme else None, "degisme": None,
                      "emsalBagi": False, "stok": r.stok, "basimYili": r.basim_yili})
    return {"items": items, "total": len(rows), "page": page, "pageSize": page_size, "kaynak": "basari",
            "kaynakAd": RAKIP_KAYNAK["basari"], "katalogTarihi": cat["tarih"]}


def competitors(engine: sa.engine.Engine, tenant: str, *, yayinevi: str = "", kategori: str = "", q: str = "",
                durum: str = "", page: int = 0, page_size: int = 50, kaynak: str = "crm") -> dict[str, Any]:
    idx = categories(engine, tenant)
    if check_kaynak(kaynak) == "basari":
        return _basari_competitors(engine, tenant, idx, yayinevi=yayinevi, kategori=kategori, q=q, durum=durum, page=page,
                                   page_size=page_size)
    Cc = COMPETITORS.c
    cond = [Cc.tenant_id == tenant]
    if yayinevi:
        cond.append(Cc.yayinevi == yayinevi)
    if kategori:
        cond.append(Cc.kategori_id.in_(sorted(idx.subtree(kategori))))
    if durum == "eslenmemis":
        cond.append(Cc.kategori_id.is_(None))
    with engine.connect() as c:
        stmt = sa.select(COMPETITORS).where(*cond).order_by(Cc.crm_created.desc(), Cc.ad)
        rows = c.execute(stmt).all()
        link_ids = {r[0] for r in c.execute(sa.select(LINKS.c.rakip_crm_id).where(LINKS.c.tenant_id == tenant)).all()}
    if q:
        f = fold(q)
        rows = [r for r in rows if f in fold(r.ad) or f in fold(r.yazarlar) or f in fold(r.isbn)]
    chunk = rows[page * page_size:(page + 1) * page_size]
    return {"items": [{"crmId": r.crm_id, "ad": r.ad, "yayinevi": r.yayinevi, "yazarlar": r.yazarlar, "isbn": r.isbn,
                       "fiyat": r.liste_fiyat, "sayfa": r.sayfa, "cilt": r.cilt, "kagit": r.kagit, "baski": r.baski_sayisi,
                       "dil": r.dil, "kategoriHam": r.kategori_ham, "kategoriId": r.kategori_id,
                       "kategoriYol": idx.path(r.kategori_id), "satisDurumu": r.satis_durumu,
                       "satisAdediHam": r.satis_adedi_ham, "satisAdedi2Ham": r.satis_adedi2_ham,
                       "olusturma": r.crm_created, "degisme": r.crm_modified, "emsalBagi": r.crm_id in link_ids}
                      for r in chunk],
            "total": len(rows), "page": page, "pageSize": page_size, "kaynak": "crm", "kaynakAd": RAKIP_KAYNAK["crm"]}


def publishers(engine: sa.engine.Engine, tenant: str, kaynak: str = "crm") -> list[dict[str, Any]]:
    if check_kaynak(kaynak) == "basari":
        cat = basari_catalog(engine, tenant)
        if not cat["tarih"]:
            return []
        D = _dagitim(engine)
        T = D.TITLES.c
        with engine.connect() as c:
            rows = c.execute(sa.select(T.yayinevi, sa.func.count()).where(
                *_basari_cond(D, tenant, date.fromisoformat(cat["tarih"])), T.yayinevi.isnot(None)).group_by(T.yayinevi)).all()
        return sorted(({"ad": r[0], "kitap": int(r[1])} for r in rows), key=lambda x: (-x["kitap"], fold(x["ad"])))
    with engine.connect() as c:
        rows = c.execute(sa.select(COMPETITORS.c.yayinevi, sa.func.count()).where(
            COMPETITORS.c.tenant_id == tenant, COMPETITORS.c.yayinevi.isnot(None)).group_by(COMPETITORS.c.yayinevi)).all()
    return sorted(({"ad": r[0], "kitap": int(r[1])} for r in rows), key=lambda x: (-x["kitap"], fold(x["ad"])))


# ================================================================================ emsal


_STOP = set("ve ile bir bu şu için gibi daha çok en de da ki ne mi mu mü kitap kitabı kitabın ya ya da olarak olan "
            "her hem ama fakat veya the and of a an to in on for".split())


STEM = 6   # Türkçe ekler için kaba kök: sözcüğün ilk 6 harfi («alışkanlıkların» ≈ «alışkanlık»)


def words(text: Any) -> list[str]:
    return [w for w in re.findall(r"[a-zçğıöşüâîû0-9]+", fold(text)) if len(w) >= 3 and w not in _STOP]


def tokens(text: Any) -> list[str]:
    return [w[:STEM] for w in words(text)]


def comparables(engine: sa.engine.Engine, tenant: str, body: dict[str, Any],
                choose: Optional[Callable[[str, list[str]], Any]],
                neighbors: Optional[Callable[[Optional[str], str, int], dict[str, Any]]] = None) -> dict[str, Any]:
    """Emsal bul: kurallı süzgeç (kategori, sayfa ±, fiyat ±) → sözcük örtüşmesiyle sıralama (idf) → ilk N aday Zeki
    AI'ya «çok / kısmen / benzemiyor» diye sorulur. Gerekçe kurallıdır (aynı kategori, sayfa farkı, fiyat farkı, ortak
    sözcükler); model yalnız benzerlik sınıfını verir. TİMAŞ kitabından başlanırsa CRM'deki emsal bağları da işaretlenir.

    `neighbors(crmKitapId, q, n)` (ortak yapı taşı 5, kitap benzerliği dizini) verilirse TİMAŞ kitaplarında aday kümesi
    genişler: ortak sözcüğü olmasa da özeti anlamca yakın ilk `compEmbed` kitap kurallı süzgeçten geçerse havuza girer.
    Sıra iki sıralamanın birleşimidir (karşılıklı sıra toplamı, k=60): sözcük sırası ve anlam sırası; puan ekrana
    yazılmaz. Dizin yoksa davranış eskisiyle aynıdır."""
    st = settings()
    idx = categories(engine, tenant)
    kaynak = check_kaynak(str(body.get("kaynak") or "crm"))
    q = str(body.get("q") or "").strip()
    base_id = str(body.get("crmKitapId") or "").strip().upper() or None
    kategori = str(body.get("kategoriId") or "").strip() or None
    sayfa = body.get("sayfa")
    fiyat = body.get("fiyat")
    base = None
    with engine.connect() as c:
        if base_id:
            base = c.execute(sa.select(OWN_BOOKS).where(OWN_BOOKS.c.tenant_id == tenant, OWN_BOOKS.c.crm_id == base_id)).first()
            if base is None:
                raise PazarError("TİMAŞ kitabı bulunamadı.", 404)
            q = q or " ".join(x for x in (base.ad, base.ozet_kisa or "") if x)
            kategori = kategori or base.kategori_id
            sayfa = sayfa or base.sayfa
            fiyat = fiyat or base.fiyat
        if not q:
            raise PazarError("Kitap adı, konu ya da bir TİMAŞ kitabı girin.")
        comp = c.execute(sa.select(COMPETITORS).where(COMPETITORS.c.tenant_id == tenant)).all() if kaynak == "crm" else []
        own = c.execute(sa.select(OWN_BOOKS).where(OWN_BOOKS.c.tenant_id == tenant)).all()
        # CRM emsal bağı CRM rakip kaydına bağlıdır; Başarı kaynağında yoktur.
        linked = {r.rakip_crm_id for r in c.execute(sa.select(LINKS.c.rakip_crm_id).where(
            LINKS.c.tenant_id == tenant, LINKS.c.kitap_crm_id == base_id)).all()} if base_id and kaynak == "crm" else set()
        maps = _approved_maps(c, tenant) if kaynak == "basari" else {}
        sales = defaultdict(lambda: {"adet": 0.0, "ciro": 0.0})
        last_year = c.execute(sa.select(sa.func.max(OWN_SALES.c.yil)).where(OWN_SALES.c.tenant_id == tenant)).scalar()
        if last_year:
            for r in c.execute(sa.select(OWN_SALES.c.anahtar, OWN_SALES.c.ytd_adet, OWN_SALES.c.ytd_ciro).where(
                    OWN_SALES.c.tenant_id == tenant, OWN_SALES.c.boyut == "stok", OWN_SALES.c.yil == last_year)).all():
                sales[r.anahtar] = {"adet": r.ytd_adet, "ciro": r.ytd_ciro}
    allowed = idx.subtree(kategori) if kategori and kategori in idx.nodes else None
    sayfa = int(sayfa) if sayfa else None
    fiyat = float(fiyat) if fiyat else None
    qtok = set(tokens(q))
    shown = {w[:STEM]: w for w in reversed(words(q))}          # kökün sorgudaki yazımı (gerekçede görünür)

    def rule_ok(cat: Optional[str], p: Optional[int], price: Optional[float]) -> bool:
        if allowed is not None and (not cat or cat not in allowed):
            return False
        if sayfa and (not p or abs(p - sayfa) > sayfa * st["compPageTol"]):
            return False
        if fiyat and (not price or abs(price - fiyat) > fiyat * st["compPriceTol"]):
            return False
        return True

    emb_rank: dict[str, int] = {}
    emb_note: Optional[str] = None
    if neighbors is not None and st["compEmbed"] > 0:
        try:
            res = neighbors(base_id, q, st["compEmbed"])
            emb_rank = {str(x.get("kitapId") or "").upper(): int(x["sira"]) for x in res.get("items") or [] if x.get("kitapId")}
            if not res.get("hazir"):
                emb_note = res.get("not")
        except Exception as e:  # noqa: BLE001 — dizin yoksa sözcük sırası kalır
            emb_note = f"Anlam benzerliği okunamadı: {str(e)[:160]}"
    pool: list[dict[str, Any]] = []
    cat_info = None
    if kaynak == "basari":
        brows, cat_info = _basari_rows(engine, tenant)
        for r in brows:
            m = maps.get(map_key("basari", r.kategori)) if r.kategori else None
            kid = m[0] if m is not None and m[2] == "onaylandi" else None
            if rule_ok(kid, r.sayfa, r.fiyat):
                pool.append({"tur": "rakip", "kaynak": "basari", "id": r.barkod, "ad": r.ad, "yazar": r.yazar,
                             "yayinevi": r.yayinevi, "kategoriId": kid, "kategoriHam": r.kategori, "sayfa": r.sayfa,
                             "fiyat": r.fiyat, "metin": None, "crmEmsal": False, "basimYili": r.basim_yili,
                             "tok": set(tokens(f"{r.ad} {r.kategori or ''}"))})
    for r in comp:
        if rule_ok(r.kategori_id, r.sayfa, r.liste_fiyat) or r.crm_id in linked:
            pool.append({"tur": "rakip", "id": r.crm_id, "ad": r.ad, "yazar": r.yazarlar, "yayinevi": r.yayinevi,
                         "kategoriId": r.kategori_id, "kategoriHam": r.kategori_ham, "sayfa": r.sayfa, "fiyat": r.liste_fiyat,
                         "metin": r.tanitim_kisa, "crmEmsal": r.crm_id in linked,
                         "tok": set(tokens(f"{r.ad} {r.kategori_ham or ''} {r.tanitim_kisa or ''}"))})
    for r in own:
        if base_id and r.crm_id == base_id:
            continue
        if rule_ok(r.kategori_id, r.sayfa, r.fiyat):
            pool.append({"tur": "timas", "id": r.crm_id, "ad": r.ad, "yazar": r.yazar, "yayinevi": r.marka,
                         "kategoriId": r.kategori_id, "kategoriHam": r.kitaplik, "sayfa": r.sayfa, "fiyat": r.fiyat,
                         "metin": r.ozet_kisa, "stokKodu": r.stok_kodu, "satis": sales.get(r.stok_kodu or "") if r.stok_kodu else None,
                         "ilkYayin": r.ilk_yayin, "crmEmsal": False, "anlamSira": emb_rank.get(str(r.crm_id).upper()),
                         "tok": set(tokens(f"{r.ad} {r.kitaplik or ''} {r.ozet_kisa or ''}"))})
    df = Counter(t for p in pool for t in p["tok"])
    n = max(1, len(pool))
    for p in pool:
        common = qtok & p["tok"]
        p["skor"] = sum(math.log(1 + n / df[t]) for t in common)
        p["ortak"] = sorted(common, key=lambda t: df[t])[:6]
    cands = [p for p in pool if p["skor"] > 0 or p["crmEmsal"] or p.get("anlamSira")]
    word_rank = {id(p): i for i, p in enumerate(sorted((p for p in cands if p["skor"] > 0),
                                                       key=lambda p: (-p["skor"], fold(p["ad"]))), start=1)}

    def fused(p: dict[str, Any]) -> float:
        w = word_rank.get(id(p))
        return (1.0 / (60 + w) if w else 0.0) + (1.0 / (60 + p["anlamSira"]) if p.get("anlamSira") else 0.0)

    ranked = sorted(cands, key=lambda p: (-p["crmEmsal"], -fused(p), fold(p["ad"])))
    model_n = min(st["compModel"], len(ranked)) if choose else 0
    stopped = None
    for p in ranked[:model_n]:
        prompt = ("Yayın kurulu yeni bir kitap için emsal arıyor. Aday kitap, aranan kitapla KONU olarak ne kadar benzer?\n\n"
                  f"Aranan: {q[:600]}\n\nAday: «{p['ad']}»" + (f" — {p['yazar']}" if p.get("yazar") else "")
                  + (f"\nKategori: {p['kategoriHam']}" if p.get("kategoriHam") else "")
                  + (f"\nKısa tanıtım: {p['metin']}" if p.get("metin") else ""))
        try:
            r = choose(prompt, SIMILARITY)
        except Exception as e:  # noqa: BLE001 — kalan adaylar kurallı sırayla kalır
            stopped = f"Zeki AI cevap vermedi: {str(e)[:160]}"
            break
        probs = getattr(r, "probs", None) or ({r.choice: 1.0} if getattr(r, "choice", None) else {})
        p["zeki"] = {"sinif": getattr(r, "choice", None), "olasilik": getattr(r, "probability", None),
                     "puan": round(probs.get(SIMILARITY[0], 0.0) + 0.5 * probs.get(SIMILARITY[1], 0.0), 4)}
    judged = [p for p in ranked if p.get("zeki")]
    rest = [p for p in ranked if not p.get("zeki")]
    judged.sort(key=lambda p: (-p["crmEmsal"], p["zeki"]["sinif"] == SIMILARITY[2], -p["zeki"]["puan"], -p["skor"]))
    out = [p for p in judged if p["zeki"]["sinif"] != SIMILARITY[2] or p["crmEmsal"]] + rest
    dropped = [p for p in judged if p["zeki"]["sinif"] == SIMILARITY[2] and not p["crmEmsal"]]

    def why(p: dict[str, Any]) -> list[str]:
        g = []
        if p["crmEmsal"]:
            g.append("CRM'de bu kitabın emsali olarak kayıtlı")
        if allowed is not None and p.get("kategoriId"):
            g.append(f"aynı kategori ({idx.path(p['kategoriId'])})")
        if sayfa and p.get("sayfa"):
            g.append(f"sayfa {p['sayfa']} ({'+' if p['sayfa'] >= sayfa else ''}{round((p['sayfa'] - sayfa) / sayfa * 100)}%)")
        if fiyat and p.get("fiyat"):
            g.append(f"fiyat {fmt_tr(p['fiyat'], 2)} ₺ ({'+' if p['fiyat'] >= fiyat else ''}{round((p['fiyat'] - fiyat) / fiyat * 100)}%)")
        if p["ortak"]:
            g.append("ortak sözcükler: " + ", ".join(shown.get(t, t) for t in p["ortak"]))
        if p.get("anlamSira"):
            g.append(f"özeti anlamca yakın ({p['anlamSira']}. sırada)")
        if p.get("zeki"):
            z = p["zeki"]
            g.append(f"Zeki AI: {z['sinif']}" + (f" (%{round((z['olasilik'] or 0) * 100)})" if z.get("olasilik") is not None else ""))
        return g

    def row(p: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in p.items() if k not in ("tok", "metin", "ortak")} | {
            "kategoriYol": idx.path(p.get("kategoriId")), "gerekce": why(p)}

    return {"query": {"q": q[:600], "crmKitapId": base_id, "kategoriId": kategori, "kategoriYol": idx.path(kategori),
                      "sayfa": sayfa, "fiyat": fiyat, "base": {"ad": base.ad, "stokKodu": base.stok_kodu} if base else None},
            "rakip": [row(p) for p in out if p["tur"] == "rakip"], "timas": [row(p) for p in out if p["tur"] == "timas"],
            "counts": {"havuz": len(pool), "sozcukEslesen": len(word_rank), "adayToplam": len(ranked), "zekiOkudu": len(judged),
                       "zekiBenzemiyor": len(dropped), "crmEmsal": len(linked),
                       "anlamAday": len(emb_rank), "anlamEklenen": sum(1 for p in ranked if p.get("anlamSira") and not p["skor"])},
            "anlamNot": emb_note, "kaynak": kaynak, "kaynakAd": RAKIP_KAYNAK[kaynak],
            "katalogTarihi": cat_info["tarih"] if cat_info else None,
            "salesYear": last_year, "stopped": stopped,
            "note": (f"Zeki AI ilk {len(judged)} adayı okudu; kalan {len(rest)} aday ortak sözcük puanıyla sıralı."
                     if choose else "Zeki AI bu kurulumda tanımlı değil; adaylar ortak sözcük puanıyla sıralı.")}


def own_books(engine: sa.engine.Engine, tenant: str, q: str, limit: int = 20) -> list[dict[str, Any]]:
    """TİMAŞ kitabı arama (emsal ekranının «kitaptan başla» seçicisi). Sonuç sayısı `limit` ile sınırlı ve ekrana yazılır."""
    f = fold(q)
    if len(f) < 2:
        return []
    with engine.connect() as c:
        rows = c.execute(sa.select(OWN_BOOKS.c.crm_id, OWN_BOOKS.c.ad, OWN_BOOKS.c.yazar, OWN_BOOKS.c.stok_kodu,
                                   OWN_BOOKS.c.marka).where(OWN_BOOKS.c.tenant_id == tenant)).all()
    hits = [r for r in rows if f in fold(r.ad) or f in fold(r.yazar) or f == fold(r.stok_kodu)]
    hits.sort(key=lambda r: (not fold(r.ad).startswith(f), fold(r.ad)))
    return [{"crmId": r.crm_id, "ad": r.ad, "yazar": r.yazar, "stokKodu": r.stok_kodu, "marka": r.marka} for r in hits[:limit]]


# ================================================================================ TİMAŞ iç göstergeleri


def own_market(engine: sa.engine.Engine, tenant: str, boyut: str = "kategori", yil: Optional[int] = None) -> dict[str, Any]:
    """TİMAŞ'ın kategori / yayınevi / kanal kırılımında aynı dönem (1 Ocak – veri sonu) büyümesi ve TİMAŞ içindeki
    payı. Kategori = kitabın (stok kodu → CRM) kategorisinin kökü; eşleşmeyen «(kategorisiz)». Sell-in'dir."""
    if boyut not in DIMENSIONS:
        raise PazarError("Boyut kategori, yayinevi ya da kanal olmalı.")
    snap = meta_get(engine, tenant, "snapshot", {}) or {}
    end = (snap.get("ownSales") or {}).get("dataEnd")
    idx = categories(engine, tenant)
    S = OWN_SALES.c
    with engine.connect() as c:
        years = sorted({r[0] for r in c.execute(sa.select(S.yil).where(S.tenant_id == tenant).distinct()).all()})
        if not years:
            return {"boyut": boyut, "yil": None, "years": [], "rows": [], "total": None, "dataEnd": end, "note": SELL_IN_NOTE,
                    "empty": "Logo satışı henüz okunmadı."}
        yil = yil if yil in years else years[-1]
        want = [yil, yil - 1]
        rows = c.execute(sa.select(OWN_SALES).where(S.tenant_id == tenant, S.yil.in_(want),
                                                    S.boyut == ("kanal" if boyut == "kanal" else "stok"))).all()
        cat_of = {}
        if boyut == "kategori":
            cat_of = {r.stok_kodu: r.kategori_id for r in c.execute(sa.select(OWN_BOOKS.c.stok_kodu, OWN_BOOKS.c.kategori_id).where(
                OWN_BOOKS.c.tenant_id == tenant, OWN_BOOKS.c.stok_kodu.isnot(None))).all()}
    agg: dict[str, dict[int, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: {"ytd_ciro": 0.0, "ytd_adet": 0.0, "ciro": 0.0, "adet": 0.0}))
    for r in rows:
        if boyut == "kanal":
            key = r.anahtar
        elif boyut == "yayinevi":
            key = r.yayinevi or "(boş)"
        else:
            key = idx.root(cat_of.get(r.anahtar)) or "__yok__"
        a = agg[key][r.yil]
        for k in ("ytd_ciro", "ytd_adet", "ciro", "adet"):
            a[k] += float(getattr(r, k) or 0)

    def growth(cur: float, prev: float) -> Optional[float]:
        return (cur / prev - 1.0) if prev and prev > 0 else None

    tot = {y: {k: sum(agg[key][y][k] for key in agg) for k in ("ytd_ciro", "ytd_adet", "ciro", "adet")} for y in want}
    out = []
    for key, byy in agg.items():
        cur, prev = byy[yil], byy[yil - 1]
        label = ("(kategorisiz)" if key == "__yok__" else idx.path(key) or key) if boyut == "kategori" else key
        out.append({"anahtar": key, "ad": label, "ytdCiro": cur["ytd_ciro"], "oncekiYtdCiro": prev["ytd_ciro"],
                    "ciroBuyume": growth(cur["ytd_ciro"], prev["ytd_ciro"]), "ytdAdet": cur["ytd_adet"],
                    "oncekiYtdAdet": prev["ytd_adet"], "adetBuyume": growth(cur["ytd_adet"], prev["ytd_adet"]),
                    "yilCiro": cur["ciro"], "oncekiYilCiro": prev["ciro"],
                    "pay": (cur["ytd_ciro"] / tot[yil]["ytd_ciro"]) if tot[yil]["ytd_ciro"] else None})
    out.sort(key=lambda x: -x["ytdCiro"])
    t_cur, t_prev = tot[yil], tot[yil - 1]
    endd = _day(end)
    period = {"yil": yil, "baslangic": f"{yil}-01-01",
              "bitis": (date(yil, endd.month, min(endd.day, 28 if endd.month == 2 else endd.day)).isoformat() if endd else None)}
    return {"boyut": boyut, "boyutAd": DIMENSIONS[boyut], "yil": yil, "years": years, "rows": out, "dataEnd": end, "period": period,
            "total": {"ytdCiro": t_cur["ytd_ciro"], "oncekiYtdCiro": t_prev["ytd_ciro"], "ciroBuyume": growth(t_cur["ytd_ciro"], t_prev["ytd_ciro"]),
                      "ytdAdet": t_cur["ytd_adet"], "oncekiYtdAdet": t_prev["ytd_adet"], "adetBuyume": growth(t_cur["ytd_adet"], t_prev["ytd_adet"]),
                      "yilCiro": t_cur["ciro"], "oncekiYilCiro": t_prev["ciro"]},
            "missingPrev": (yil - 1) not in years, "note": SELL_IN_NOTE}


# ================================================================================ sektör raporları


def _report_out(r: Any, counts: Optional[dict[str, int]] = None) -> dict[str, Any]:
    return {"id": r.id, "kaynak": r.kaynak, "yil": r.yil, "baslik": r.baslik, "dosyaAdi": r.dosya_adi, "mime": r.mime,
            "boyut": r.boyut, "sayfaSayisi": r.sayfa_sayisi, "durum": r.durum, "durumAd": REPORT_STATUS.get(r.durum),
            "ilerleme": loads(r.ilerleme_json, None), "yukleyen": r.yukleyen, "yuklendiAt": iso(r.yuklendi_at),
            **({"rakam": counts} if counts is not None else {})}


def add_report(engine: sa.engine.Engine, tenant: str, user: str, filename: str, data: bytes, meta: dict[str, Any],
               pages_of: Callable[[str, bytes], list[dict[str, Any]]]) -> dict[str, Any]:
    from semantic_bridge import pazar_sources as src

    st = settings()
    name = re.sub(r"[\\/\x00-\x1f]", "_", (filename or "").strip())[:200]
    ext = src.ext_of(name)
    if ext not in src.ALLOWED:
        raise PazarError("Rapor PDF, Excel (.xlsx), CSV ya da metin olmalı.")
    if not data:
        raise PazarError("Dosya boş.")
    if len(data) > st["fileMaxMb"] * 1024 * 1024:
        raise PazarError(f"Dosya {st['fileMaxMb']} MB sınırını aşıyor.", 413)
    magic = src.MAGIC.get(ext)
    if magic and not any(data.startswith(m) for m in magic):
        raise PazarError("Dosyanın içeriği uzantısıyla uyuşmuyor.")
    kaynak = str(meta.get("kaynak") or "").strip()[:200]
    baslik = str(meta.get("baslik") or "").strip()[:300] or name
    if not kaynak:
        raise PazarError("Raporun kaynağı (yayımlayan kurum) girilmeli.")
    yil = meta.get("yil")
    try:
        yil = int(yil) if yil not in (None, "") else None
    except (TypeError, ValueError):
        raise PazarError("Yıl sayı olmalı.") from None
    digest = hashlib.sha256(data).hexdigest()
    with engine.connect() as c:
        dup = c.execute(sa.select(REPORTS.c.baslik).where(REPORTS.c.tenant_id == tenant, REPORTS.c.sha256 == digest)).first()
    if dup:
        raise PazarError(f"Bu dosya zaten yüklü: «{dup.baslik}».", 409)
    pages = pages_of(name, data)
    rid = new_id()
    path = files_root() / tenant / f"{rid}.{ext}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as e:
        log.error("pazar raporu yazılamadı (%s): %s", path, e)
        raise PazarError("Dosya sunucuya kaydedilemedi; yöneticiye bildirin.", 503) from e
    empty = sum(1 for p in pages if not (p["metin"] or "").strip())
    with engine.begin() as c:
        c.execute(REPORTS.insert().values(id=rid, tenant_id=tenant, kaynak=kaynak, yil=yil, baslik=baslik, dosya_adi=name,
                                          dosya_yolu=str(path), mime=src.ALLOWED[ext], boyut=len(data), sha256=digest,
                                          sayfa_sayisi=len(pages), durum="yuklendi",
                                          ilerleme_json=dumps({"metinsizSayfa": empty}), yukleyen=user, yuklendi_at=now()))
    return get_report(engine, tenant, rid)


def _report_row(c: Any, tenant: str, rid: str) -> Any:
    r = c.execute(sa.select(REPORTS).where(REPORTS.c.tenant_id == tenant, REPORTS.c.id == rid)).first()
    if r is None:
        raise PazarError("Rapor bulunamadı.", 404)
    return r


def _figure_counts(c: Any, tenant: str, ids: list[str]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = defaultdict(dict)
    if ids:
        for rid, d, n in c.execute(sa.select(FIGURES.c.report_id, FIGURES.c.durum, sa.func.count()).where(
                FIGURES.c.tenant_id == tenant, FIGURES.c.report_id.in_(ids)).group_by(FIGURES.c.report_id, FIGURES.c.durum)).all():
            out[rid][d] = int(n)
    return out


def get_report(engine: sa.engine.Engine, tenant: str, rid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _report_row(c, tenant, rid)
        return _report_out(r, _figure_counts(c, tenant, [rid]).get(rid, {}))


def list_reports(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(sa.select(REPORTS).where(REPORTS.c.tenant_id == tenant).order_by(REPORTS.c.yuklendi_at.desc())).all()
        counts = _figure_counts(c, tenant, [r.id for r in rows])
    return {"items": [_report_out(r, counts.get(r.id, {})) for r in rows], "statusLabels": REPORT_STATUS,
            "figureStatus": FIGURE_STATUS, "olcu": OLCU}


def report_file(engine: sa.engine.Engine, tenant: str, rid: str) -> tuple[str, str, str]:
    with engine.connect() as c:
        r = _report_row(c, tenant, rid)
    if not Path(r.dosya_yolu).exists():
        raise PazarError("Dosya sunucuda bulunamadı.", 404)
    return r.dosya_yolu, r.dosya_adi, r.mime


def _cited_figures(engine: sa.engine.Engine, tenant: str) -> set[str]:
    out: set[str] = set()
    with engine.connect() as c:
        for (raw,) in c.execute(sa.select(BRIEFS.c.kaynaklar_json).where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.durum == "onaylandi")).all():
            for s in (loads(raw, {}) or {}).get("kaynaklar", []):
                if s.get("tur") == "dis" and s.get("ref"):
                    out.add(str(s["ref"]))
    return out


def delete_report(engine: sa.engine.Engine, tenant: str, rid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _report_row(c, tenant, rid)
        fids = {x[0] for x in c.execute(sa.select(FIGURES.c.id).where(FIGURES.c.report_id == rid)).all()}
    if r.durum == "cikariliyor":
        raise PazarError("Rakam çıkarımı sürüyor; bitince silin.", 409)
    if fids & _cited_figures(engine, tenant):
        raise PazarError("Bu raporun rakamları onaylı bir yönetim özetinde kaynak olarak geçiyor; silinemez.", 409)
    with engine.begin() as c:
        c.execute(FIGURES.delete().where(FIGURES.c.report_id == rid))
        c.execute(REPORTS.delete().where(REPORTS.c.id == rid))
    Path(r.dosya_yolu).unlink(missing_ok=True)
    return {"id": rid, "baslik": r.baslik, "rakam": len(fids)}


def set_report_state(engine: sa.engine.Engine, tenant: str, rid: str, durum: str, ilerleme: dict[str, Any]) -> None:
    with engine.begin() as c:
        c.execute(REPORTS.update().where(REPORTS.c.tenant_id == tenant, REPORTS.c.id == rid).values(
            durum=durum, ilerleme_json=dumps(ilerleme)))


EXTRACT_SYSTEM = (
    "Sen bir sektör raporundan rakam çıkaran yardımcısın. Yalnız verilen sayfa metninde AÇIKÇA yazan rakamları al; "
    "hesaplama, tahmin, yuvarlama yapma. Cevap yalnız JSON dizi: "
    '[{"gosterge": "kısa ad", "deger": "metinde yazdığı gibi sayı", "birim": "adet|₺|%|milyon ₺|…", '
    '"donem": "yıl ya da dönem", "alinti": "rakamın geçtiği en çok 200 karakterlik cümle parçası", '
    '"olcu": "pazar_ciro|pazar_adet|pazar_buyume|kategori_pay|okur|diger"}]. '
    "Sayfada önemli rakam yoksa [] yaz. Açıklama yazma.")


def _chunks(text: str, size: int) -> list[str]:
    if len(text) <= size:
        return [text]
    out, cur = [], ""
    for line in text.splitlines():
        if len(cur) + len(line) + 1 > size and cur:
            out.append(cur)
            cur = ""
        while len(line) > size:
            out.append(line[:size])
            line = line[size:]
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return out


def parse_json_list(raw: str) -> list[dict[str, Any]]:
    t = (raw or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.MULTILINE).strip()
    a, b = t.find("["), t.rfind("]")
    if a < 0 or b <= a:
        return []
    try:
        v = json.loads(t[a:b + 1])
    except ValueError:
        return []
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _near(text: str, value_text: str, width: int = 160) -> Optional[str]:
    flat = " ".join((text or "").split())
    for n in numbers_in(flat):
        if any(round(v, 6) in {round(x, 6) for x, _ in parse_number(value_text)} for v, _ in n["values"]):
            a = max(0, n["start"] - width // 2)
            return ("…" if a else "") + flat[a:n["end"] + width // 2].strip() + ("…" if n["end"] + width // 2 < len(flat) else "")
    return None


def extract_page(page: dict[str, Any], chat: Callable[[list[dict[str, str]]], str], chunk_chars: int) -> dict[str, Any]:
    """Bir sayfanın rakamları. Modelin her rakamı sayfa metninde aranır; bulunmayan atılır (`dropped`). Alıntı
    sayfada geçmiyorsa metinden rakamın çevresi alınır."""
    text = page["metin"] or ""
    if not text.strip():
        return {"figures": [], "dropped": 0, "empty": True}
    figs, dropped, seen = [], 0, set()
    for part in _chunks(text, chunk_chars):
        raw = chat([{"role": "system", "content": EXTRACT_SYSTEM},
                    {"role": "user", "content": f"Sayfa {page['sayfa']} metni:\n\n{part}"}])
        for x in parse_json_list(raw):
            vt = str(x.get("deger") or "").strip()
            gost = " ".join(str(x.get("gosterge") or "").split())[:300]
            if not vt or not gost:
                dropped += 1
                continue
            v = value_in_text(vt, part)
            if v is None:
                dropped += 1
                continue
            key = (fold(gost), round(v, 6))
            if key in seen:
                continue
            seen.add(key)
            quote = " ".join(str(x.get("alinti") or "").split())[:300]
            if not quote or fold(quote) not in fold(" ".join(part.split())):
                quote = _near(part, vt)
            olcu = str(x.get("olcu") or "diger")
            figs.append({"gosterge": gost, "deger": v, "deger_metin": vt[:60], "birim": (str(x.get("birim") or "").strip()[:40] or None),
                         "donem": (str(x.get("donem") or "").strip()[:40] or None), "alinti_kisa": (quote or "")[:300] or None,
                         "olcu": olcu if olcu in OLCU else "diger"})
    return {"figures": figs, "dropped": dropped, "empty": False}


def store_figures(engine: sa.engine.Engine, tenant: str, rid: str, sayfa: str, figs: list[dict[str, Any]]) -> int:
    """Sayfanın önerilerini yazar. Aynı sayfada aynı gösterge ve değerde karar verilmiş rakam varsa tekrar yazılmaz."""
    with engine.begin() as c:
        have = {(fold(r.gosterge), round(r.deger_oneri if r.deger_oneri is not None else r.deger, 6)) for r in c.execute(
            sa.select(FIGURES.c.gosterge, FIGURES.c.deger, FIGURES.c.deger_oneri).where(
                FIGURES.c.report_id == rid, FIGURES.c.sayfa == sayfa)).all()}
        n = 0
        for f in figs:
            if (fold(f["gosterge"]), round(f["deger"], 6)) in have:
                continue
            c.execute(FIGURES.insert().values(id=new_id(), tenant_id=tenant, report_id=rid, sayfa=sayfa, deger_oneri=f["deger"],
                                              yontem="zeki", durum="oneri", olusturuldu_at=now(), **f))
            n += 1
    return n


def clear_pending(engine: sa.engine.Engine, tenant: str, rid: str) -> int:
    with engine.begin() as c:
        return c.execute(FIGURES.delete().where(FIGURES.c.tenant_id == tenant, FIGURES.c.report_id == rid,
                                                FIGURES.c.durum == "oneri")).rowcount or 0


def _figure_out(r: Any, idx: Optional[CatIndex] = None) -> dict[str, Any]:
    return {"id": r.id, "raporId": r.report_id, "gosterge": r.gosterge, "deger": r.deger, "degerMetin": r.deger_metin,
            "degerOneri": r.deger_oneri, "birim": r.birim, "donem": r.donem, "sayfa": r.sayfa, "alinti": r.alinti_kisa,
            "olcu": r.olcu, "olcuAd": OLCU.get(r.olcu), "kategoriId": r.kategori_id,
            "kategoriYol": idx.path(r.kategori_id) if idx else None, "yontem": r.yontem, "durum": r.durum,
            "durumAd": FIGURE_STATUS.get(r.durum), "onaylayan": r.onaylayan, "kararAt": iso(r.karar_at), "not": r.not_}


def figures(engine: sa.engine.Engine, tenant: str, rid: str) -> dict[str, Any]:
    idx = categories(engine, tenant)
    with engine.connect() as c:
        rep = _report_row(c, tenant, rid)
        rows = c.execute(sa.select(FIGURES).where(FIGURES.c.tenant_id == tenant, FIGURES.c.report_id == rid)).all()

    def page_key(s: str) -> tuple:
        return (0, int(s)) if str(s).isdigit() else (1, str(s))

    rows = sorted(rows, key=lambda r: (page_key(r.sayfa), r.olusturuldu_at))
    # Ortak belge okuma: taranmış sayfadan (OCR) okunan rakam ekranda «OCR» etiketi ve sayfanın güveniyle görünür.
    prog = loads(rep.ilerleme_json, {}) or {}
    ocr = {str(k): v for k, v in (prog.get("ocrGuven") or {}).items()}
    items = []
    for r in rows:
        f = _figure_out(r, idx)
        if str(r.sayfa) in ocr:
            f.update(okuma="ocr", guven=ocr[str(r.sayfa)])
        items.append(f)
    return {"report": _report_out(rep), "items": items, "olcu": OLCU,
            "statusLabels": FIGURE_STATUS, "categories": idx.items()}


def _valid_olcu_cat(engine: sa.engine.Engine, tenant: str, body: dict[str, Any]) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if "olcu" in body:
        o = str(body.get("olcu") or "diger")
        if o not in OLCU:
            raise PazarError("Ölçü türü geçersiz.")
        vals["olcu"] = o
    if "kategoriId" in body:
        k = body.get("kategoriId") or None
        if k and k not in categories(engine, tenant).nodes:
            raise PazarError("Kategori listede yok.")
        vals["kategori_id"] = k
    for key, col, n in (("birim", "birim", 40), ("donem", "donem", 40), ("gosterge", "gosterge", 300)):
        if key in body:
            v = " ".join(str(body.get(key) or "").split())[:n]
            if key == "gosterge" and not v:
                raise PazarError("Gösterge adı boş olamaz.")
            vals[col] = v or None
    return vals


def decide_figure(engine: sa.engine.Engine, tenant: str, actor: str, fid: str, body: dict[str, Any]) -> dict[str, Any]:
    karar = str(body.get("karar") or "")
    if karar not in ("onaylandi", "duzeltildi", "reddedildi", "oneri"):
        raise PazarError("Karar onaylandi, duzeltildi, reddedildi ya da oneri (geri al) olmalı.")
    with engine.connect() as c:
        r = c.execute(sa.select(FIGURES).where(FIGURES.c.tenant_id == tenant, FIGURES.c.id == fid)).first()
    if r is None:
        raise PazarError("Rakam bulunamadı.", 404)
    if r.durum in APPROVED_FIGURE and karar != r.durum and fid in _cited_figures(engine, tenant):
        raise PazarError("Bu rakam onaylı bir yönetim özetinde kaynak; kararı değiştirilemez.", 409)
    vals = _valid_olcu_cat(engine, tenant, body)
    if karar == "duzeltildi":
        try:
            v = to_number(body.get("deger"))
        except (TypeError, ValueError):
            raise PazarError("Düzeltilen değer sayı olmalı.") from None
        vals.update(deger=v, deger_metin=str(body.get("deger"))[:60])
    elif karar in ("onaylandi", "oneri") and r.deger_oneri is not None:
        vals.update(deger=r.deger_oneri)
    note = str(body.get("not") or "").strip()[:300] or None
    if karar == "reddedildi" and not note and r.yontem == "elle":
        note = None
    vals.update(durum=karar, onaylayan=None if karar == "oneri" else actor, karar_at=None if karar == "oneri" else now(), not_=note)
    with engine.begin() as c:
        c.execute(FIGURES.update().where(FIGURES.c.id == fid).values(**vals))
        r = c.execute(sa.select(FIGURES).where(FIGURES.c.id == fid)).first()
    return _figure_out(r, categories(engine, tenant))


def add_figure(engine: sa.engine.Engine, tenant: str, actor: str, rid: str, body: dict[str, Any]) -> dict[str, Any]:
    """Elle girilen rakam (Zeki AI'ın kaçırdığı ya da Excel tablosu): sayfa şart, girilen kişinin onayıyla yazılır."""
    with engine.connect() as c:
        _report_row(c, tenant, rid)
    sayfa = " ".join(str(body.get("sayfa") or "").split())[:60]
    if not sayfa:
        raise PazarError("Rakamın geçtiği sayfa girilmeli.")
    try:
        v = to_number(body.get("deger"))
    except (TypeError, ValueError):
        raise PazarError("Değer sayı olmalı.") from None
    vals = _valid_olcu_cat(engine, tenant, {**body, "gosterge": body.get("gosterge") or ""})
    fid = new_id()
    with engine.begin() as c:
        c.execute(FIGURES.insert().values(id=fid, tenant_id=tenant, report_id=rid, sayfa=sayfa, deger=v,
                                          deger_metin=str(body.get("deger"))[:60], yontem="elle", durum="onaylandi",
                                          onaylayan=actor, karar_at=now(), olusturuldu_at=now(),
                                          alinti_kisa=(" ".join(str(body.get("alinti") or "").split())[:300] or None),
                                          **{"olcu": "diger", **vals}))
        r = c.execute(sa.select(FIGURES).where(FIGURES.c.id == fid)).first()
    return _figure_out(r, categories(engine, tenant))


def approved_figures(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    idx = categories(engine, tenant)
    with engine.connect() as c:
        rows = c.execute(sa.select(FIGURES, REPORTS.c.baslik, REPORTS.c.kaynak, REPORTS.c.yil).join(
            REPORTS, REPORTS.c.id == FIGURES.c.report_id).where(FIGURES.c.tenant_id == tenant,
                                                               FIGURES.c.durum.in_(APPROVED_FIGURE))
            .order_by(REPORTS.c.yil.desc(), REPORTS.c.yuklendi_at.desc(), FIGURES.c.olusturuldu_at)).all()
    return [{**_figure_out(r, idx), "rapor": r.baslik, "raporKaynak": r.kaynak, "raporYil": r.yil} for r in rows]


# ================================================================================ izlenen rakipler


def watchlist(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    idx = categories(engine, tenant)
    with engine.connect() as c:
        rows = c.execute(sa.select(WATCHLIST).where(WATCHLIST.c.tenant_id == tenant).order_by(WATCHLIST.c.yayinevi)).all()
    return {"items": [{"id": r.id, "yayinevi": r.yayinevi, "kategoriId": r.kategori_id, "kategoriYol": idx.path(r.kategori_id),
                       "ekleyen": r.ekleyen, "eklendiAt": iso(r.eklendi_at)} for r in rows]}


def add_watch(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any]) -> dict[str, Any]:
    y = " ".join(str(body.get("yayinevi") or "").split())[:200]
    if not y:
        raise PazarError("Yayınevi adı girilmeli.")
    k = body.get("kategoriId") or None
    if k and k not in categories(engine, tenant).nodes:
        raise PazarError("Kategori listede yok.")
    with engine.connect() as c:
        dup = c.execute(sa.select(WATCHLIST.c.id).where(WATCHLIST.c.tenant_id == tenant, WATCHLIST.c.yayinevi == y,
                                                        (WATCHLIST.c.kategori_id == k) if k else WATCHLIST.c.kategori_id.is_(None))).first()
    if dup:
        raise PazarError("Bu yayınevi zaten izleniyor.", 409)
    wid = new_id()
    with engine.begin() as c:
        c.execute(WATCHLIST.insert().values(id=wid, tenant_id=tenant, yayinevi=y, kategori_id=k, ekleyen=actor, eklendi_at=now()))
    return {"id": wid, "yayinevi": y, "kategoriId": k}


def delete_watch(engine: sa.engine.Engine, tenant: str, wid: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = c.execute(sa.select(WATCHLIST).where(WATCHLIST.c.tenant_id == tenant, WATCHLIST.c.id == wid)).first()
        if r is None:
            raise PazarError("Kayıt bulunamadı.", 404)
        c.execute(WATCHLIST.delete().where(WATCHLIST.c.id == wid))
    return {"id": wid, "yayinevi": r.yayinevi}


# ================================================================================ yönetim özeti

MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def donem_label(donem: str) -> str:
    y, m = donem.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def valid_donem(donem: Optional[str]) -> str:
    if not donem:
        t = today().replace(day=1) - timedelta(days=1)
        return f"{t.year}-{t.month:02d}"
    if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", donem):
        raise PazarError("Dönem YYYY-AA biçiminde olmalı.")
    return donem


def brief_sources(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Özetin kaynakları, sabit sırayla: TİMAŞ toplam, kategori, kanal (Logo, aynı dönem); onaylı rapor rakamları;
    izlenen rakiplerin fiyat konumu; rakip verisinin yaşı. `PAZAR_BRIEF_MAX_SOURCES`'ı aşan kaynak modele verilmez
    ve kaç tanesinin dışarıda kaldığı kayda yazılır."""
    st = settings()
    out: list[dict[str, Any]] = []

    def add(tur: str, baslik: str, deger: Optional[float], birim: str, donem: str, kaynak: str, ref: Optional[str] = None) -> None:
        if deger is None:
            return
        out.append({"tur": tur, "baslik": baslik, "deger": round(float(deger), 4), "birim": birim, "donem": donem,
                    "kaynak": kaynak, "ref": ref})

    lo = "Logo faturalı satış (sell-in)"
    for boyut in ("kategori", "kanal"):
        m = own_market(engine, tenant, boyut)
        if not m.get("rows"):
            continue
        per = m["period"]
        span = f"1 Ocak – {per['bitis'][8:10]}.{per['bitis'][5:7]} {m['yil']}" if per.get("bitis") else str(m["yil"])
        if boyut == "kategori":
            t = m["total"]
            add("ic", "TİMAŞ net ciro", t["ytdCiro"], "₺", span, lo)
            if t["ciroBuyume"] is not None:
                add("ic", "TİMAŞ net ciro büyümesi (önceki yılın aynı dönemine göre)", t["ciroBuyume"] * 100, "%", span, lo)
            if t["adetBuyume"] is not None:
                add("ic", "TİMAŞ net adet büyümesi (önceki yılın aynı dönemine göre)", t["adetBuyume"] * 100, "%", span, lo)
        for r in m["rows"]:
            if r["ytdCiro"] <= 0:
                continue
            add("ic", f"{m['boyutAd']}: {r['ad']} — net ciro", r["ytdCiro"], "₺", span, lo)
            if r["ciroBuyume"] is not None:
                add("ic", f"{m['boyutAd']}: {r['ad']} — net ciro büyümesi", r["ciroBuyume"] * 100, "%", span, lo)
    for f in approved_figures(engine, tenant):
        add("dis", f["gosterge"] + (f" ({f['kategoriYol']})" if f.get("kategoriYol") else ""), f["deger"], f.get("birim") or "",
            f.get("donem") or str(f.get("raporYil") or ""), f"{f['raporKaynak']} — {f['rapor']}, sayfa {f['sayfa']}", f["id"])
    wl = watchlist(engine, tenant)["items"]
    for w in wl:
        if not w.get("kategoriId"):
            continue
        try:
            mx = matrix(engine, tenant, kategori=w["kategoriId"])
        except PazarError:          # izlenen kategori listeden düştüyse kaynak olmaz
            continue
        row = next((r for r in mx["rows"] if fold(r["yayinevi"]) == fold(w["yayinevi"])), None)
        if row and row["medyan"] is not None:
            add("rakip", f"{w['yayinevi']} — {w['kategoriYol']} medyan liste fiyatı", row["medyan"], "₺", "CRM rakip kaydı",
                "CRM «Rakip Kitap»")
        own = mx["timas"][0]
        if own["medyan"] is not None:
            add("rakip", f"TİMAŞ — {w['kategoriYol']} medyan fiyat (KDV dahil)", own["medyan"], "₺", "CRM kitap kartı",
                "CRM kitap kartı")
    fr = freshness(engine, tenant)
    add("tazelik", "Rakip kitap verisinin son güncellemesinden bu yana geçen gün", fr["ageDays"], "gün",
        fr.get("lastChange") or "", "CRM «Rakip Kitap» kayıt tarihleri")
    # Aynı başlık iki kez girmesin (izlenen iki kayıt aynı kategoriyi ister).
    seen, uniq = set(), []
    for s in out:
        k = (s["baslik"], s["deger"])
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    # Öncelik: dış rakamlar ve toplamlar önce kalsın diye kesme sırası: tazelik, toplam, dış, rakip, kalan iç.
    order = {"tazelik": 0, "dis": 2, "rakip": 3}
    ranked = sorted(enumerate(uniq), key=lambda x: (0 if x[1]["baslik"].startswith("TİMAŞ net") else order.get(x[1]["tur"], 4), x[0]))
    kept = [s for _, s in ranked[:st["briefMaxSources"]]]
    for i, s in enumerate(kept, 1):
        s["id"] = f"K{i}"
        s["degerMetin"] = _fmt_source(s)
    return {"kaynaklar": kept, "disarida": max(0, len(uniq) - len(kept)), "dis": sum(1 for s in kept if s["tur"] == "dis")}


def _fmt_source(s: dict[str, Any]) -> str:
    v = s["deger"]
    if s["birim"] == "%":
        return f"%{fmt_tr(v, 1)}"
    if s["birim"] == "₺":
        return f"{fmt_tr(v, 0)} ₺"
    dec = 0 if float(v).is_integer() else 2
    return f"{fmt_tr(v, dec)} {s['birim']}".strip()


BRIEF_SYSTEM = (
    "Sen TİMAŞ yönetim kurulu için aylık pazar özeti taslağı yazan yardımcısın. Yalnız verilen kaynaklardaki bilgiyi "
    "kullan. Kurallar: (1) her cümle en az bir kaynak kimliğine (K1, K2…) bağlanır; (2) cümlede geçen her sayı bağlandığı "
    "kaynaktaki değerle aynı olmalı (yuvarlayabilirsin, hesaplama yapma, yeni sayı üretme); (3) TİMAŞ'ın Logo satışı "
    "kitapçıya satıştır, pazar payı diye yazma; (4) kaynak yoksa tahmin yazma. Cevap yalnız JSON: "
    '{"firsatlar": [{"metin": "…", "kaynaklar": ["K1"]}], "tehditler": [...], "aksiyonlar": [...]}. '
    "Her bölümde en çok üç madde. Türkçe, kısa, somut cümleler.")


def _prompt_sources(src: list[dict[str, Any]]) -> str:
    return "\n".join(f"{s['id']}: {s['baslik']} = {s['degerMetin']} ({s['donem']}; kaynak: {s['kaynak']})" for s in src)


def check_sentence(text: str, cited: list[str], by_id: dict[str, dict[str, Any]]) -> Optional[str]:
    """Cümle kabul edilebilir mi: kaynak kimliği var ve bilinen; sayıların hepsi bağlandığı kaynaklarla tutuyor."""
    ids = [c for c in cited if c in by_id]
    if not ids:
        return "kaynağa bağlı değil"
    vals: list[Any] = [by_id[i]["deger"] for i in ids]
    for i in ids:     # dönem yazımındaki gün/ay/yıl sayıları («1 Ocak – 17.08 2026») da kaynağın parçasıdır
        vals.append(str(by_id[i].get("donem") or ""))
    bad = unsupported_numbers(text, vals)
    if bad:
        return "kaynakta olmayan sayı: " + ", ".join(bad)
    return None


def render_brief(donem: str, sections: dict[str, list[dict[str, Any]]], src: list[dict[str, Any]], disarida: int) -> str:
    lines = [f"# Pazar özeti — {donem_label(donem)}", ""]
    for key, title in BRIEF_SECTIONS.items():
        lines.append(f"## {title}")
        items = sections.get(key) or []
        if not items:
            lines.append("- (Kaynağa bağlı madde yok.)" if key != "aksiyonlar" else "- (Önerilen aksiyon yok.)")
        for it in items:
            lines.append(f"- {it['metin'].strip()} " + " ".join(f"[{c}]" for c in it["kaynaklar"]))
        lines.append("")
    lines.append("## Kaynaklar")
    for s in src:
        lines.append(f"- [{s['id']}] {s['baslik']}: {s['degerMetin']} ({s['donem']}) — {s['kaynak']}")
    if disarida:
        lines.append(f"- Kaynak sınırı nedeniyle {disarida} kaynak taslağa verilmedi (ayar: en çok kaynak sayısı).")
    if not any(s["tur"] == "dis" for s in src):
        lines.append("- Pazar büyüklüğü: kaynak yok (onaylı sektör raporu rakamı yok).")
    lines.append("")
    lines.append(f"_{SELL_IN_NOTE}_")
    return "\n".join(lines)


_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")


def check_brief(md: str, src: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Onay denetimi: Fırsatlar / Tehditler / Aksiyonlar bölümlerindeki her madde en az bir kaynağa ([Kn]) bağlı ve
    içindeki her sayı bağlandığı kaynakla tutuyor. Yer tutucu («(… yok.)») madde sayılmaz."""
    by_id = {s["id"]: s for s in src}
    titles = {v: k for k, v in BRIEF_SECTIONS.items()}
    section, problems = None, []
    for no, line in enumerate((md or "").splitlines(), 1):
        h = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        if h:
            section = titles.get(h.group(1).strip())
            continue
        if section is None:
            continue
        b = _BULLET.match(line)
        text = (b.group(1) if b else line).strip()
        if not text or re.fullmatch(r"\(.*yok\.\)", text) or text.startswith("_"):
            continue
        cited = re.findall(r"\[(K\d+)\]", text)
        err = check_sentence(text, cited, by_id)
        if err:
            problems.append({"satir": no, "metin": text[:200], "neden": err})
    return problems


def _brief_out(r: Any) -> dict[str, Any]:
    k = loads(r.kaynaklar_json, {}) or {}
    return {"id": r.id, "donem": r.donem, "donemAd": donem_label(r.donem), "taslak": r.taslak_md, "kaynaklar": k.get("kaynaklar", []),
            "reddedilen": k.get("reddedilen", []), "disarida": k.get("disarida", 0), "durum": r.durum,
            "durumAd": BRIEF_STATUS.get(r.durum), "yazan": r.yazan, "yazildiAt": iso(r.yazildi_at), "guncelleyen": r.guncelleyen,
            "guncellendiAt": iso(r.guncellendi_at), "gonderen": r.gonderen, "gonderildiAt": iso(r.gonderildi_at),
            "onaylayan": r.onaylayan, "onaylandiAt": iso(r.onaylandi_at), "dykGonderildiAt": iso(r.dyk_gonderildi_at),
            "kararNotu": r.karar_notu, "sorunlar": check_brief(r.taslak_md, k.get("kaynaklar", []))}


def draft_brief(engine: sa.engine.Engine, tenant: str, actor: str, donem: Optional[str],
                chat: Optional[Callable[[list[dict[str, str]]], str]]) -> dict[str, Any]:
    donem = valid_donem(donem)
    with engine.connect() as c:
        cur = c.execute(sa.select(BRIEFS).where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.donem == donem)).first()
    if cur is not None and cur.durum == "onaylandi":
        raise PazarError(f"{donem_label(donem)} özeti onaylı; yeni taslak yazılamaz.", 409)
    pack = brief_sources(engine, tenant)
    src = pack["kaynaklar"]
    if not src:
        raise PazarError("Özet için kaynak yok: önce kaynakları yenileyin (Logo satışı) ya da rapor rakamı onaylayın.", 409)
    if chat is None:
        raise PazarError("Zeki AI bu kurulumda tanımlı değil; taslak elle yazılabilir.", 503)
    raw = chat([{"role": "system", "content": BRIEF_SYSTEM},
                {"role": "user", "content": f"Dönem: {donem_label(donem)}\n\nKaynaklar:\n{_prompt_sources(src)}"}])
    t = (raw or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.MULTILINE).strip()
    a, b = t.find("{"), t.rfind("}")
    try:
        data = json.loads(t[a:b + 1]) if a >= 0 and b > a else {}
    except ValueError:
        data = {}
    by_id = {s["id"]: s for s in src}
    sections: dict[str, list[dict[str, Any]]] = {}
    rejected = []
    for key in BRIEF_SECTIONS:
        keep = []
        for it in (data.get(key) or []) if isinstance(data, dict) else []:
            if not isinstance(it, dict):
                continue
            text = " ".join(str(it.get("metin") or "").split())[:600]
            cited = [str(x).strip().upper() for x in (it.get("kaynaklar") or []) if str(x).strip()]
            if not text:
                continue
            err = check_sentence(text, cited, by_id)
            if err:
                rejected.append({"bolum": BRIEF_SECTIONS[key], "metin": text, "neden": err})
                continue
            keep.append({"metin": re.sub(r"\s*\[K\d+\]", "", text), "kaynaklar": [c for c in cited if c in by_id]})
        sections[key] = keep
    md = render_brief(donem, sections, src, pack["disarida"])
    k = dumps({"kaynaklar": src, "reddedilen": rejected, "disarida": pack["disarida"]})
    with engine.begin() as c:
        if cur is not None:
            c.execute(BRIEFS.update().where(BRIEFS.c.id == cur.id).values(
                taslak_md=md, kaynaklar_json=k, durum="taslak", yazan=actor, yazildi_at=now(), guncelleyen=None,
                guncellendi_at=None, gonderen=None, gonderildi_at=None, karar_notu=None))
            bid = cur.id
        else:
            bid = new_id()
            c.execute(BRIEFS.insert().values(id=bid, tenant_id=tenant, donem=donem, taslak_md=md, kaynaklar_json=k,
                                             durum="taslak", yazan=actor, yazildi_at=now()))
    return get_brief(engine, tenant, bid)


def _brief_row(c: Any, tenant: str, bid: str) -> Any:
    r = c.execute(sa.select(BRIEFS).where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.id == bid)).first()
    if r is None:
        raise PazarError("Özet bulunamadı.", 404)
    return r


def get_brief(engine: sa.engine.Engine, tenant: str, bid: str) -> dict[str, Any]:
    with engine.connect() as c:
        return _brief_out(_brief_row(c, tenant, bid))


def brief_by_donem(engine: sa.engine.Engine, tenant: str, donem: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(BRIEFS).where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.donem == valid_donem(donem))).first()
    return _brief_out(r) if r else None


def list_briefs(engine: sa.engine.Engine, tenant: str, durum: str = "") -> dict[str, Any]:
    cond = [BRIEFS.c.tenant_id == tenant]
    if durum:
        cond.append(BRIEFS.c.durum == durum)
    with engine.connect() as c:
        rows = c.execute(sa.select(BRIEFS).where(*cond).order_by(BRIEFS.c.donem.desc())).all()
    return {"items": [{k: v for k, v in _brief_out(r).items() if k not in ("taslak", "kaynaklar", "reddedilen")} for r in rows],
            "statusLabels": BRIEF_STATUS}


def update_brief(engine: sa.engine.Engine, tenant: str, actor: str, bid: str, md: str) -> dict[str, Any]:
    md = str(md or "")
    if not md.strip():
        raise PazarError("Özet boş olamaz.")
    if len(md) > 60000:
        raise PazarError("Özet çok uzun (60.000 karakter).")
    with engine.begin() as c:
        r = _brief_row(c, tenant, bid)
        if r.durum == "onaylandi":
            raise PazarError("Onaylı özet değiştirilemez.", 409)
        c.execute(BRIEFS.update().where(BRIEFS.c.id == bid).values(taslak_md=md, durum="taslak", guncelleyen=actor,
                                                                   guncellendi_at=now(), gonderen=None, gonderildi_at=None))
    return get_brief(engine, tenant, bid)


def submit_brief(engine: sa.engine.Engine, tenant: str, actor: str, bid: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _brief_row(c, tenant, bid)
        if r.durum != "taslak":
            raise PazarError("Yalnız taslak onaya gönderilir.", 409)
        problems = check_brief(r.taslak_md, (loads(r.kaynaklar_json, {}) or {}).get("kaynaklar", []))
        if problems:
            raise PazarError(f"{len(problems)} madde kaynağa bağlı değil ya da kaynakta olmayan sayı içeriyor; önce düzeltin.", 422)
        c.execute(BRIEFS.update().where(BRIEFS.c.id == bid).values(durum="onay_bekliyor", gonderen=actor, gonderildi_at=now(),
                                                                   karar_notu=None))
    return get_brief(engine, tenant, bid)


def decide_brief(engine: sa.engine.Engine, tenant: str, actor: str, bid: str, approve: bool, note: Optional[str]) -> dict[str, Any]:
    st = settings()
    with engine.begin() as c:
        r = _brief_row(c, tenant, bid)
        if r.durum != "onay_bekliyor":
            raise PazarError("Özet onay beklemiyor.", 409)
        if st["twoEyes"] and actor.lower() in {x.lower() for x in (r.gonderen, r.yazan, r.guncelleyen) if x}:
            raise PazarError("Özeti yazan ya da onaya gönderen onaylayamaz.", 409)
        if approve:
            problems = check_brief(r.taslak_md, (loads(r.kaynaklar_json, {}) or {}).get("kaynaklar", []))
            if problems:
                raise PazarError("Özette kaynağa bağlı olmayan madde var; onaylanamaz.", 422)
            c.execute(BRIEFS.update().where(BRIEFS.c.id == bid).values(durum="onaylandi", onaylayan=actor, onaylandi_at=now(),
                                                                       dyk_gonderildi_at=now(), karar_notu=(note or None)))
        else:
            if not (note or "").strip():
                raise PazarError("Geri gönderme gerekçesi yazılmalı.")
            c.execute(BRIEFS.update().where(BRIEFS.c.id == bid).values(durum="taslak", karar_notu=note.strip()[:500]))
    return get_brief(engine, tenant, bid)


def approved_brief(engine: sa.engine.Engine, tenant: str) -> Optional[dict[str, Any]]:
    """DYK sözleşmesi: son onaylı özet (dönem en yeni)."""
    with engine.connect() as c:
        r = c.execute(sa.select(BRIEFS).where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.durum == "onaylandi")
                      .order_by(BRIEFS.c.donem.desc())).first()
    return _brief_out(r) if r else None


def due_brief_donem(engine: sa.engine.Engine, tenant: str, on: Optional[date] = None) -> Optional[str]:
    """Zamanlayıcı: ayın ilk haftasındaysak ve geçen ayın özeti hiç yazılmadıysa o dönem."""
    d = on or today()
    if d.day > 7:
        return None
    prev = d.replace(day=1) - timedelta(days=1)
    donem = f"{prev.year}-{prev.month:02d}"
    with engine.connect() as c:
        hit = c.execute(sa.select(BRIEFS.c.id).where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.donem == donem)).first()
    return None if hit else donem


# ================================================================================ özet ekranı


def overview(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    fr = freshness(engine, tenant)
    with engine.connect() as c:
        own_n = c.execute(sa.select(sa.func.count()).select_from(OWN_BOOKS).where(OWN_BOOKS.c.tenant_id == tenant)).scalar() or 0
        pub_n = c.execute(sa.select(sa.func.count(sa.distinct(COMPETITORS.c.yayinevi))).where(
            COMPETITORS.c.tenant_id == tenant)).scalar() or 0
        pending_figs = c.execute(sa.select(sa.func.count()).select_from(FIGURES).where(
            FIGURES.c.tenant_id == tenant, FIGURES.c.durum == "oneri")).scalar() or 0
        waiting = c.execute(sa.select(BRIEFS).where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.durum != "onaylandi")
                            .order_by(BRIEFS.c.donem.desc())).first()
        wl = c.execute(sa.select(sa.func.count()).select_from(WATCHLIST).where(WATCHLIST.c.tenant_id == tenant)).scalar() or 0
    cmap = category_map(engine, tenant, page_size=0, kaynak="crm")
    bmap = category_map(engine, tenant, page_size=0, kaynak="basari")
    figs = approved_figures(engine, tenant)
    snap = meta_get(engine, tenant, "snapshot", {}) or {}
    return {"freshness": fr, "snapshot": snap, "ownBooks": own_n, "publishers": pub_n,
            "mapping": {"counts": cmap["counts"], "coverage": cmap["coverage"]},
            "mappingBasari": {"counts": bmap["counts"], "coverage": bmap["coverage"]},
            "own": own_market(engine, tenant, "kategori"), "figures": figs, "pendingFigures": pending_figs,
            "brief": approved_brief(engine, tenant),
            "pendingBrief": {k: v for k, v in _brief_out(waiting).items() if k in ("id", "donem", "donemAd", "durum", "durumAd", "yazan")}
            if waiting else None,
            "watchlist": wl, "lastRun": meta_get(engine, tenant, "last_run", None),
            "disTarama": "Dış kaynak taraması yok: rakip verisi CRM'den, pazar rakamları yüklenen ve onaylanan raporlardan gelir.",
            "note": SELL_IN_NOTE}
