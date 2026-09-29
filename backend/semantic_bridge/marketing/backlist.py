"""M17 Backlist kitaplar için pazarlama planları: fırsat listesi (uyku endeksi), gündem, aktivasyon planı, kampanya etkisi.

**Backlist kümesi** tek tanımdır: M46'nın yürürlükteki bütçe planında `segment='backlist'` olan kitaplar (verinin son
yılı). O yıl onaylı plan yoksa yedek tanım: CRM kitap kartında ilk yayını veri sonundan en az
`MARKETING_BACKLIST_MIN_MONTHS` (12) ay önce olan «Kitap» kartları. Kümenin hangi tanımdan geldiği ekranda yazar.
157 ile başlayan ticari ürünler kitap değildir, alınmaz. **Sayı tavanı yok**: liste tamdır, toplam sayı döner.

**Bileşenler** (hepsi kodla ve SQL'le; model rakam üretmez):
- *Satış eğilimi*: son 12 **tam** ayın net adedi ÷ önceki 12 tam ay − 1. Satış satırı M46 ile aynı (Logo `STLINE`,
  faturalı, iade eksi); veri M46'nın Logo önbelleğinden, M46'da olmayan geçmiş yıllar aynı sorguyla Logo'dan okunur.
- *Stok*: Logo depo stoku (Baskı Öneri'nin sorgusu) ve tükenme süresi = stok ÷ (son 12 ay net adedi ÷ 12) ay.
- *Marj*: son 12 ayın brüt marjı, yalnız maliyeti girilmiş satırlarda (M46 tanımı: 1 − Σ adet × maliyet ÷ net ciro).
- *Tahmin*: Baskı Öneri'nin 12 aylık kitap tahmininin orta değeri (p50) toplamı.
- *Hedef sapması*: M46 yürürlükteki planında kitabın gerçekleşme oranı (ciro; cirosuz hedefte adet) ve açık sapma uyarısı.

**Uyku endeksi** = Σ (ağırlık × bileşen yüzdeliği) ÷ Σ (değeri olan bileşenlerin ağırlığı). Yüzdelik bütün backlist
içinde sıra yüzdeliğidir (0–100, eşitlerde orta sıra): eğilimde düşüş büyüdükçe, stokta tükenme süresi uzadıkça, marjda
ve tahminde değer büyüdükçe, sapmada gerçekleşme oranı düştükçe yüksek. Ağırlıkları kullanıcı değiştirir (kişisel tercih
ya da ekip varsayılanı); varsayılan eşit. Formül ekranda yazılı; her satırda bileşenler ayrı görünür.

**Gündem**: önümüzdeki N haftanın CRM özel günleri (tarih yöntemi SEO sezon takvimiyle aynı) ve bağlı kitaplar; yazarı
yeni kitap çıkaran backlist kitaplar (CRM eser katılımı); konu eşleşmesi (özel gün adı ↔ kitabın CRM anahtar kelime ve
temaları; aday çiftte Zeki AI «ilgili mi?» sorusuna kapalı kümeden cevap verir, olasılığıyla; kullanıcı onaylar). Arama
ilgisi ve haber verisi yok: kazıma yapılmaz, müşteride web taraması kapalı.

**Kampanya etkisi**: CRM kampanyası (B2B/CRM) ürünlerinin kampanya ayı(ları), önceki 3 ay ve sonraki 2 ay Logo net adedi
(ay düzeyinde). Öncesi/sonrası gösterilir; nedensellik iddia edilmez.
"""
from __future__ import annotations

import calendar
import logging
import math
import threading
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import budget as B
from semantic_bridge import budget_sources as bsrc
from semantic_bridge.hizli_bellek import Bellek
from semantic_bridge.marketing import backlist_sql as Q
from semantic_bridge.marketing import books as BK
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import guard as G
from semantic_bridge.marketing import plans as P
from semantic_bridge.marketing.sources import SourceError

log = logging.getLogger("semantic.marketing.backlist")

Runner = Callable[[str], list[dict[str, Any]]]

ROWS = sa.Table(
    "semantic_mkt_backlist", C._md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("kitap_id", sa.String(40)),
    sa.Column("ad", sa.String(400)),
    sa.Column("yazar", sa.String(300)),
    sa.Column("yayinevi", sa.String(200)),
    sa.Column("kitaplik", sa.String(200)),
    sa.Column("hedef_kitle", sa.String(120)),
    sa.Column("ilk_yayin", sa.String(10)),
    sa.Column("adet_son12", sa.Float, nullable=False, default=0.0),
    sa.Column("adet_onceki12", sa.Float, nullable=False, default=0.0),
    sa.Column("degisim", sa.Float),                                    # son12 ÷ önceki12 − 1; önceki 0 ise boş
    sa.Column("ciro_son12", sa.Float, nullable=False, default=0.0),
    sa.Column("marj", sa.Float),
    sa.Column("stok", sa.Float),
    sa.Column("tukenme_ay", sa.Float),                                 # sonsuz: satış yok, stok var
    sa.Column("tahmin12_p50", sa.Float),
    sa.Column("m46_durum", sa.String(12)),                             # iyi | izle | sapma | baslamadi | None (hedef yok)
    sa.Column("m46_oran", sa.Float),
    sa.Column("m46_hedef_adet", sa.Float),
    sa.Column("m46_hedef_ciro", sa.Float),
    sa.Column("sapma_acik", sa.Boolean, nullable=False, default=False),
    sa.Column("sapma_acik_tutar", sa.Float),                           # açık uyarının beklenen − gerçekleşen cirosu
    sa.Column("ozel_gunler", sa.Text),                                 # json: bağlı özel günler, sıradaki tarihleriyle
    sa.Column("dijital", sa.Text),                                     # json: e-kitap stok kodu / ISBN
    sa.Column("detay_json", sa.Text),                                  # json: satış durumu, yaş/sınıf, türler, kapak
    sa.Column("bilesen_json", sa.Text, nullable=False),                # json: bileşen ham değerleri ve yüzdelikleri
    sa.Column("endeks_varsayilan", sa.Float),
    sa.Column("kume", sa.String(12), nullable=False),                  # m46 | crm
    sa.Column("veri_sonu", sa.String(10)),
    sa.Column("asof", sa.DateTime(timezone=True), nullable=False),
)
SERIES = sa.Table(
    "semantic_mkt_backlist_series", C._md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("yil_ay", sa.String(7), primary_key=True),               # YYYY-MM (son 36 tam ay; sıfır aylar yazılmaz)
    sa.Column("net_adet", sa.Float, nullable=False),
    sa.Column("net_ciro", sa.Float, nullable=False),
)
#: M46'nın önbelleğinde olmayan geçmiş yılların Logo satışı (aynı sorgu, aynı kolonlar; haftada bir tazelenir).
PAST = sa.Table(
    "semantic_mkt_backlist_sales", C._md,
    sa.Column("year", sa.Integer, primary_key=True),
    sa.Column("month", sa.Integer, primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("adet", sa.Float, nullable=False),
    sa.Column("ciro", sa.Float, nullable=False),
    sa.Column("maliyet", sa.Float, nullable=False),
    sa.Column("maliyetli_ciro", sa.Float, nullable=False),
)
EFFECTS = sa.Table(
    "semantic_mkt_campaign_effect", C._md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kampanya_id", sa.String(40), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("kampanya_adi", sa.String(400)),
    sa.Column("tip", sa.Integer),
    sa.Column("mecra", sa.Integer),
    sa.Column("baslangic", sa.String(10)),
    sa.Column("bitis", sa.String(10)),
    sa.Column("ek_iskonto", sa.Float),
    sa.Column("net_iskonto", sa.Float),
    sa.Column("planlanan_ciro", sa.Float),
    sa.Column("gerceklesen_ciro", sa.Float),
    sa.Column("once3_adet", sa.Float),
    sa.Column("kampanya_adet", sa.Float),
    sa.Column("sonra2_adet", sa.Float),
    sa.Column("kapsam", sa.String(12), nullable=False),                # tam | suruyor | veri-yok
    sa.Column("backlist", sa.Boolean, nullable=False, default=False),
    sa.Column("asof", sa.DateTime(timezone=True), nullable=False),
)
MATCHES = sa.Table(
    "semantic_mkt_matches", C._md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("stok_kodu", sa.String(60), nullable=False),
    sa.Column("tur", sa.String(12), nullable=False),                   # ozel-gun | yazar-yeni | konu
    sa.Column("anahtar", sa.String(80), nullable=False),               # özel gün id | yeni kitabın stok kodu
    sa.Column("etiket", sa.String(400)),                               # özel gün adı | yeni kitabın adı
    sa.Column("tarih", sa.String(10)),
    sa.Column("bitis", sa.String(10)),
    sa.Column("kaynak", sa.String(16), nullable=False),                # crm | zeki
    sa.Column("skor", sa.Float),                                       # model olasılığı (yalnız konu)
    sa.Column("marj", sa.Float),
    sa.Column("onay", sa.String(10)),                                  # konu: bekliyor | kabul | red; CRM bağında boş
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onay_zamani", sa.DateTime(timezone=True)),
    sa.Column("detay_json", sa.Text),
    sa.Column("asof", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("tenant_id", "stok_kodu", "tur", "anahtar", name="uq_semantic_mkt_matches"),
)

#: (anahtar, ad, açıklama). Sıra ekrandaki sıradır.
COMPONENTS: list[tuple[str, str, str]] = [
    ("egilim", "Satış eğilimi", "Son 12 tam ayın net adedi önceki 12 aya göre ne kadar düştüyse o kadar yüksek."),
    ("stok", "Stok", "Depo stoku kaç ay yeterse (tükenme süresi) o kadar yüksek; stoku olmayan kitap en altta."),
    ("marj", "Marj", "Son 12 ayın brüt marjı (maliyeti girilmiş satırlar) yüksekse yüksek."),
    ("tahmin", "Tahmin", "Önümüzdeki 12 ayın Zeki AI satış tahmini (orta değer) yüksekse yüksek."),
    ("sapma", "Hedef sapması", "Bu yılın satış hedefinde gerçekleşme oranı düştükçe yüksek; hedefi olmayan kitapta boş."),
]
KEYS = [c[0] for c in COMPONENTS]
DEFAULT_WEIGHTS = {k: 1.0 for k in KEYS}
FORMULA = ("Uyku endeksi = Σ (ağırlık × bileşen yüzdeliği) ÷ Σ (değeri olan bileşenlerin ağırlığı). Yüzdelik, kitabın "
           "o bileşende bütün backlist içindeki sırasıdır (0–100; eşit değerlerde orta sıra). Değeri olmayan bileşen "
           "(ör. hedefi ya da maliyeti olmayan kitap) hesaba girmez, kalan ağırlıklar ölçeklenir.")
SORTS = {"oncelik": "Öncelik (açık sapma üstte, sonra endeks)", "endeks": "Uyku endeksi", "egilim": "Satış düşüşü",
         "stok": "Tükenme süresi", "marj": "Marj", "tahmin": "Tahmin", "sapma": "Hedef sapması", "ciro": "Son 12 ay ciro",
         "adet": "Son 12 ay adet", "ad": "Kitap adı"}
M46_STATES = {"iyi": "İyi", "izle": "İzle", "sapma": "Sapma", "baslamadi": "Başlamadı", "yok": "Hedef yok"}
MATCH_TYPES = {"ozel-gun": "Özel gün", "yazar-yeni": "Yazarın yeni kitabı", "konu": "Konu eşleşmesi"}
TOPIC_CHOICES = ["İlgili", "İlgisiz", "Belirsiz"]
CAMPAIGN_MEDIA = {1: "CRM", 2: "B2B", 3: "CRM ve B2B"}
PAGE_SIZE = 100

#: Backlist aktivasyonunun içerik türleri (çekirdeğin materyal akışı: taslak → editoryal → pazarlama onayı). CRM
#: kitap kartında karşılıkları yok; çok kitaplı planda CRM alanı eşlemesi yanıltıcı olurdu.
MATERIALS: dict[str, tuple[str, Optional[str]]] = {
    "yeniden-kesfet": ("«Neden şimdi oku» gönderileri", None),
    "e-bulten-bolum": ("E-bülten bölümü (yeniden keşfedin)", None),
    "toplu-alim-mektubu": ("Okul / kütüphane toplu alım mektubu", None),
}
for _k, _v in MATERIALS.items():
    C.MATERIALS_KINDS.setdefault(_k, _v)

MATERIAL_PROMPTS = {
    "yeniden-kesfet": "Bu kitaplar için «neden şimdi okumalı» temalı üç ayrı sosyal medya gönderisi yaz; her birinin başına "
                      "platform adını koy: Instagram, X, Facebook. Gündem kancası verildiyse (özel gün, yazarın yeni kitabı) "
                      "gönderiyi ona bağla. Instagram gönderisinin sonuna konuya uygun birkaç etiket ekle (etiketlerde sayı "
                      "kullanma).",
    "e-bulten-bolum": "E-bültende «Yeniden keşfedin» bölümü yaz: iki cümlelik giriş, sonra her kitap için ayrı paragrafta "
                      "kitabın adı ve iki cümlelik tanıtım. Gündem kancası verildiyse girişte kullan.",
    "toplu-alim-mektubu": "Okul ve kütüphanelere gönderilecek toplu alım teklif mektubu taslağı yaz: hitap, bir paragraf "
                          "giriş, her kitabın hedef okuru ve konusu, sınıfta ya da kütüphanede kullanım fikri, iletişim "
                          "cümlesi. Fiyat, iskonto, adet ya da tarih yazma; teklif şartlarını satış ekibi ekler.",
}

#: Aktivasyon planı takvim şablonu: (başlangıca göre gün, iş, kanal, materyal türü). Dış gönderim insanındır.
TASKS: list[tuple[int, str, Optional[str], Optional[str]]] = [
    (-28, "Kitapların stok ve baskı durumunu Baskı Öneri'de kontrol et", None, None),
    (-21, "Planı onaya gönder", None, None),
    (-21, "«Neden şimdi oku» gönderilerini onayla", "sosyal-medya", "yeniden-kesfet"),
    (-14, "Kampanyayı «CRM'e işlenecek» listesinden CRM'e işle (işlemi ekip yapar)", "satis-kampanyasi", None),
    (-14, "E-bülten bölümünü onayla", "dijital", "e-bulten-bolum"),
    (-10, "Okul / kütüphane mektubunu onayla (hedef kitle uygunsa)", "satis-kampanyasi", "toplu-alim-mektubu"),
    (0, "Aktivasyon başlangıcı: onaylı gönderileri yayımla (yayını ekip yapar)", "sosyal-medya", "yeniden-kesfet"),
    (30, "İlk ay: Etki sekmesinde öncesi/sonrası satışı değerlendir", None, None),
    (90, "Üçüncü ay: kitaplar fırsat listesinde nereye geldi", None, None),
]

_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    BK.ensure(engine)
    with _lock:
        if id(engine) in _ready:
            return
        for t in (ROWS, SERIES, PAST, EFFECTS, MATCHES):
            t.create(engine, checkfirst=True)
        _ready.add(id(engine))


# ------------------------------------------------------------------ ayarlar


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    def num(key: str, default: float) -> float:
        raw = (conf(key) or "").strip().replace(",", ".")
        try:
            v = float(raw) if raw else default
        except ValueError:
            return default
        return v if math.isfinite(v) and v >= 0 else default

    return {
        "minMonths": int(num("MARKETING_BACKLIST_MIN_MONTHS", 12)),
        "agendaWeeks": max(1, int(num("MARKETING_BACKLIST_AGENDA_WEEKS", 8))),
        "remindWeeks": max(1, int(num("MARKETING_BACKLIST_REMIND_WEEKS", 6))),
        "topicWeeks": max(1, int(num("MARKETING_BACKLIST_TOPIC_WEEKS", 12))),
        "campaignYears": max(1, int(num("MARKETING_BACKLIST_CAMPAIGN_YEARS", 3))),
        "digestMin": num("MARKETING_BACKLIST_DIGEST_MIN", 70.0),
        "authorRole": (conf("MARKETING_BACKLIST_AUTHOR_ROLE") or "").strip() or "Yazar",
    }


def parse_weights(v: Any) -> dict[str, float]:
    """`egilim:1,stok:2,…` ya da sözlük → bileşen ağırlıkları. Tanınmayan anahtar yok sayılır, eksik anahtar 0 değil
    varsayılandır (1). Eksi ya da sayı olmayan değer hata; hepsi sıfırsa hata."""
    out = dict(DEFAULT_WEIGHTS)
    if v in (None, "", {}):
        return out
    items: Iterable[tuple[str, Any]]
    if isinstance(v, dict):
        items = v.items()
    else:
        items = [tuple(p.split(":", 1)) if ":" in p else (p, "") for p in str(v).split(",") if p.strip()]  # type: ignore[misc]
    for k, raw in items:
        k = str(k).strip()
        if k not in out:
            continue
        try:
            n = float(str(raw).replace(",", "."))
        except ValueError:
            raise C.MarketingError(f"«{k}» ağırlığı sayı olmalı.") from None
        if not math.isfinite(n) or n < 0:
            raise C.MarketingError(f"«{k}» ağırlığı eksi olamaz.")
        out[k] = n
    if sum(out.values()) <= 0:
        raise C.MarketingError("En az bir bileşenin ağırlığı sıfırdan büyük olmalı.")
    return out


def weights_text(w: dict[str, float]) -> str:
    return ",".join(f"{k}:{w.get(k, 1.0):g}" for k in KEYS)


# ------------------------------------------------------------------ saf hesaplar


def windows(end: date) -> dict[str, int]:
    """Ay dizinleri (yıl × 12 + ay − 1). Son tam ay: veri sonu ayın son günü değilse bir önceki ay."""
    last_day = calendar.monthrange(end.year, end.month)[1]
    lf = B.month_index(end.year, end.month) - (0 if end.day == last_day else 1)
    return {"lastFull": lf, "son12": lf - 11, "onceki12": lf - 23, "seri": lf - 35}


def ym(i: int) -> str:
    y, m = B.from_index(i)
    return f"{y:04d}-{m:02d}"


def month_label(i: int) -> str:
    y, m = B.from_index(i)
    return f"{B.AY[m - 1]} {y}"


def percentiles(values: dict[str, Optional[float]]) -> dict[str, Optional[float]]:
    """Sıra yüzdeliği 0–100: (küçük olanların sayısı + eşitlerin yarısı) ÷ n × 100. Boş değer boş kalır."""
    have = sorted((v, k) for k, v in values.items() if v is not None and not (isinstance(v, float) and math.isnan(v)))
    n = len(have)
    out: dict[str, Optional[float]] = {k: None for k in values}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and have[j + 1][0] == have[i][0]:
            j += 1
        p = round((i + (j - i + 1) / 2) / n * 100, 2)
        for x in range(i, j + 1):
            out[have[x][1]] = p
        i = j + 1
    return out


def index_of(pcts: dict[str, Optional[float]], w: dict[str, float]) -> Optional[float]:
    num = den = 0.0
    for k in KEYS:
        p = pcts.get(k)
        wk = w.get(k, 0.0)
        if p is None or wk <= 0:
            continue
        num += wk * p
        den += wk
    return round(num / den, 1) if den > 0 else None


def component_raw(r: dict[str, Any]) -> dict[str, Optional[float]]:
    """Yüzdeliğe giren ham değerler (yön: büyük = fırsat)."""
    stok = r.get("stok")
    if stok is None:
        s = None
    elif stok <= 0:
        s = 0.0
    else:
        s = r.get("tukenme_ay") if r.get("tukenme_ay") is not None else math.inf
    oran = r.get("m46_oran")
    return {"egilim": None if r.get("degisim") is None else -r["degisim"], "stok": s, "marj": r.get("marj"),
            "tahmin": r.get("tahmin12_p50"), "sapma": None if oran is None else 1 - oran}


def tukenme(stok: Optional[float], adet12: float) -> Optional[float]:
    if stok is None or stok <= 0:
        return 0.0 if stok is not None else None
    if adet12 <= 0:
        return None  # sonsuz: bileşende en yüksek sıra, ekranda «satış yok»
    return round(stok / (adet12 / 12), 1)


def change(son: float, onceki: float) -> Optional[float]:
    return round(son / onceki - 1, 4) if onceki > 0 else None


# ------------------------------------------------------------------ kaynak okuma yardımcıları


class Sources:
    """Logo ve CRM okumaları. Bağlantı ilk gerektiğinde kurulur (M46 önbelleği yetiyorsa Logo'ya hiç gidilmez)."""

    def __init__(self, logo_file: Callable[[], str], crm_run: Callable[[], Runner], schema: Callable[[], str]):
        self._logo_file = logo_file
        self._crm_run = crm_run
        self.schema = schema
        self._logo: Optional[Runner] = None
        self._firms: Optional[dict[int, str]] = None

    def logo(self) -> Runner:
        if self._logo is None:
            try:
                self._logo = bsrc.runner(self._logo_file())
            except bsrc.SourceError as e:
                raise SourceError(f"Logo okunamıyor: {e}") from None
        return self._logo

    def firms(self) -> dict[int, str]:
        if self._firms is None:
            try:
                self._firms = bsrc.firms_by_year(self.logo())
            except bsrc.SourceError as e:
                raise SourceError(f"Logo dönemleri okunamadı: {e}") from None
        return self._firms

    def logo_sql(self, sql: str) -> list[dict[str, Any]]:
        try:
            return self.logo()(sql)
        except bsrc.SourceError as e:
            raise SourceError(f"Logo: {e}") from None

    def crm(self, sql: str) -> list[dict[str, Any]]:
        try:
            return self._crm_run()(sql)
        except (bsrc.SourceError, SourceError) as e:
            raise SourceError(f"CRM: {e}") from None

    def sales(self, year: int) -> list[dict[str, Any]]:
        try:
            return bsrc.read_sales(self.logo(), self.firms(), year)
        except bsrc.SourceError as e:
            raise SourceError(f"Logo {year} satışı: {e}") from None


# Okuma ifadeleri ayrı kurulur: aynı ifade hem çalıştırılır hem sorgu bilgisinde gösterilir (kaynak_backlist.py).


def past_stmt(year: int):
    return sa.select(PAST).where(PAST.c.year == year)


def rows_stmt(tenant: str):
    return sa.select(ROWS).where(ROWS.c.tenant_id == tenant)


def rows_in_stmt(tenant: str, codes: Iterable[str]):
    return sa.select(ROWS).where(ROWS.c.tenant_id == tenant, ROWS.c.stok_kodu.in_(list(codes) or [""]))


def version_stmt(tenant: str):
    """Kitap satırlarının sürümü: satır sayısı ve en son yazım anı (gece hesabı bütün satırları aynı `asof` ile yazar)."""
    return sa.select(sa.func.count(), sa.func.max(ROWS.c.asof)).where(ROWS.c.tenant_id == tenant)


def row_stmt(tenant: str, code: str):
    return sa.select(ROWS).where(ROWS.c.tenant_id == tenant, ROWS.c.stok_kodu == code)


def series_stmt(tenant: str, code: str):
    return sa.select(SERIES).where(SERIES.c.tenant_id == tenant, SERIES.c.stok_kodu == code)


def series_in_stmt(tenant: str, codes: Iterable[str]):
    return sa.select(SERIES).where(SERIES.c.tenant_id == tenant, SERIES.c.stok_kodu.in_(list(codes) or [""]))


def effects_code_stmt(tenant: str, code: str):
    return (sa.select(EFFECTS).where(EFFECTS.c.tenant_id == tenant, EFFECTS.c.stok_kodu == code)
            .order_by(EFFECTS.c.baslangic.desc()))


def matches_code_stmt(tenant: str, code: str):
    return sa.select(MATCHES).where(MATCHES.c.tenant_id == tenant, MATCHES.c.stok_kodu == code).order_by(MATCHES.c.tarih)


def matches_stmt(tenant: str):
    return sa.select(MATCHES).where(MATCHES.c.tenant_id == tenant)


def effects_stmt(tenant: str, yil: Optional[int] = None, only_backlist: bool = False):
    cond = [EFFECTS.c.tenant_id == tenant]
    if yil:
        cond.append(EFFECTS.c.baslangic.like(f"{int(yil)}-%"))
    if only_backlist:
        cond.append(EFFECTS.c.backlist.is_(True))
    return sa.select(EFFECTS).where(*cond).order_by(EFFECTS.c.baslangic.desc(), EFFECTS.c.kampanya_id)


def _year_sales(engine: sa.engine.Engine, tenant: str, src: Sources, year: int, *, refresh_past: bool,
                notes: list[str]) -> tuple[Optional[list[Any]], str]:
    """Bir yılın kitap × ay satışı. M46 önbelleğinde varsa oradan (saatlik tazelenir); yoksa bu modülün geçmiş yıl
    önbelleğinden (haftada bir ya da hiç okunmadıysa Logo'dan, aynı sorgu). Okunamazsa (None, neden)."""
    if B.meta_get(engine, f"sales:{year}").get("_at"):
        with engine.connect() as c:
            return c.execute(sa.select(B.SALES).where(B.SALES.c.year == year)).all(), "m46"
    key = f"backlist-sales:{year}"
    have = C.meta_get(engine, tenant, key)
    if refresh_past or not have.get("_at"):
        try:
            rows = src.sales(year)
        except SourceError as e:
            if have.get("_at"):
                notes.append(f"{year} satışı Logo'dan tazelenemedi ({e}); {have.get('_at', '')[:10]} tarihli okuma kullanıldı.")
            else:
                return None, str(e)
        else:
            with engine.begin() as c:
                c.execute(PAST.delete().where(PAST.c.year == year))
                for i in range(0, len(rows), 5000):
                    c.execute(PAST.insert(), [{k: r[k] for k in ("year", "month", "stok_kodu", "adet", "ciro", "maliyet",
                                                                   "maliyetli_ciro")} for r in rows[i:i + 5000]])
            firm = None
            try:
                firm = src.firms().get(year)
            except SourceError:
                firm = None
            C.meta_set(engine, tenant, key, {"rows": len(rows), "ciro": round(sum(r["ciro"] for r in rows), 2), "firm": firm})
    with engine.connect() as c:
        return c.execute(past_stmt(year)).all(), "logo"


def _special_days(rows: list[dict[str, Any]], today: date) -> dict[str, dict[str, Any]]:
    """CRM özel günleri → sıradaki gerçekleşme (bugün süren dahil) ve geçen yılki gerçekleşme."""
    from semantic_bridge.seo_geo import seasons as S

    out: dict[str, dict[str, Any]] = {}
    for d in rows:
        did = str(d.get("id") or "").lower()
        if not did:
            continue
        tarih = bsrc._day(d.get("tarih"))
        how = S.resolve({"name": d.get("ad"), "weekFrom": d.get("hafta1"), "weekTo": d.get("hafta2"),
                         "fixedDate": f"{tarih.month:02d}-{tarih.day:02d}" if tarih and tarih.year >= 1950 else None})
        if how["method"] == "unknown":
            out[did] = {"id": did, "ad": bsrc._clean(d.get("ad")), "baslangic": None, "bitis": None, "yontem": how.get("why"),
                        "kesinlik": how.get("precision"), "gecenYil": None}
            continue
        nxt = S.next_occurrence(how, today)
        prev = S.previous_occurrence(how, nxt[0]) if nxt else None
        out[did] = {"id": did, "ad": bsrc._clean(d.get("ad")), "baslangic": nxt[0].isoformat() if nxt else None,
                    "bitis": nxt[1].isoformat() if nxt else None, "yontem": how.get("why"), "kesinlik": how.get("precision"),
                    "gecenYil": prev[0].isoformat() if prev else None}
    return out


def _deviations(engine: sa.engine.Engine, tenant: str, year: int) -> dict[str, dict[str, Any]]:
    """M46 açık kitap uyarıları (bütün sayfalar)."""
    out: dict[str, dict[str, Any]] = {}
    page = 0
    while True:
        d = B.deviations(engine, tenant, year, status="acik", kind="satis", scope="kitap", page=page)
        for a in d["items"]:
            out[a["key"]] = a
        if (page + 1) * d["pageSize"] >= d["total"] or not d["items"]:
            break
        page += 1
    return out


# ------------------------------------------------------------------ gece hesabı


def build(engine: sa.engine.Engine, tenant: str, src: Sources, st: dict[str, Any], *, refresh_past: bool = False,
          today: Optional[date] = None) -> dict[str, Any]:
    """Backlist kümesi + bileşenler + 36 ay seri + kampanya etkisi + CRM eşleşmeleri → tablolar (tek işlemde yenilenir;
    hata olursa eski görüntü kalır)."""
    ensure(engine)
    P.budget_ready(engine)
    today = today or C.today()
    t0 = C.now()
    notes: list[str] = []
    end = B.data_end(engine)
    if end is None:
        raise C.MarketingError("Logo satış verisinin sonu bilinmiyor: önce Bütçe ekranında gerçekleşme okunmalı.", 409)
    w = windows(end)
    info = B._book_info(engine)
    if not info:
        raise C.MarketingError("Kitap kartları henüz okunmadı (Bütçe → gerçekleşmeyi yenile).", 409)

    # 1) küme
    year = end.year
    tg = B.approved_targets(engine, tenant, year, segment="backlist", with_actuals=True)
    targets: dict[str, dict[str, Any]] = {}
    trade = 0
    if tg.get("plan"):
        kume = "m46"
        for it in tg["items"]:
            if B._is_trade(it["stokKodu"]):
                trade += 1
                continue
            targets[it["stokKodu"]] = it
        codes = sorted(targets)
        kume_info = {"kaynak": "m46", "planId": tg["plan"]["id"], "surum": tg["plan"]["version"], "yil": year,
                     "ad": f"{year} bütçe planı (sürüm {tg['plan']['version']}) backlist segmenti", "haric157": trade}
    else:
        kume = "crm"
        cut_y, cut_m = B.from_index(B.month_index(end.year, end.month) - st["minMonths"])
        cutoff = date(cut_y, cut_m, min(end.day, calendar.monthrange(cut_y, cut_m)[1])).isoformat()
        no_date = 0
        codes = []
        for code, b in info.items():
            if B._is_trade(code):
                trade += 1
                continue
            if not b.get("ilk_yayin"):
                no_date += 1
                continue
            if b["ilk_yayin"] <= cutoff:
                codes.append(code)
        codes.sort()
        kume_info = {"kaynak": "crm", "yil": year, "haric157": trade, "ilkYayinYok": no_date, "esik": cutoff,
                     "ad": f"{year} için onaylı bütçe planı yok: CRM'de ilk yayını {cutoff} ya da öncesi olan kitaplar"}
        notes.append(f"{year} yılının onaylı bütçe planı yok; küme CRM ilk yayın tarihinden kuruldu. İlk yayın tarihi "
                     f"olmayan {no_date} kart kümeye alınmadı.")
    want = set(codes)

    # 2) satış: seri, 12/12 ay, marj; kampanya etkisi için kampanya penceresi
    camp_since = date(today.year - st["campaignYears"], 1, 1)
    first_idx = min(w["seri"], B.month_index(camp_since.year, camp_since.month) - 3)
    years = list(range(B.from_index(first_idx)[0], B.from_index(w["lastFull"])[0] + 1))
    need_trend = set(range(B.from_index(w["onceki12"])[0], B.from_index(w["lastFull"])[0] + 1))
    sales: dict[str, dict[int, list[float]]] = defaultdict(dict)
    year_src: dict[str, str] = {}
    for y in years:
        rows, how = _year_sales(engine, tenant, src, y, refresh_past=refresh_past, notes=notes)
        if rows is None:
            if y in need_trend:
                raise SourceError(f"{y} satışı okunamadı, eğilim hesaplanamaz: {how}")
            notes.append(f"{y} satışı okunamadı ({how}); o yılın ayları seride ve kampanya etkisinde boş.")
            year_src[str(y)] = "yok"
            continue
        year_src[str(y)] = how
        for r in rows:
            i = B.month_index(r.year, r.month)
            cur = sales[r.stok_kodu].get(i)
            if cur is None:
                sales[r.stok_kodu][i] = [r.adet, r.ciro, r.maliyet, r.maliyetli_ciro]
            else:
                for k, v in enumerate((r.adet, r.ciro, r.maliyet, r.maliyetli_ciro)):
                    cur[k] += v
    loaded = {B.month_index(int(y), m) for y, s in year_src.items() if s != "yok" for m in range(1, 13)}

    def window_sum(code: str, a: int, b: int, k: int = 0) -> float:
        m = sales.get(code) or {}
        return float(sum(v[k] for i, v in m.items() if a <= i <= b))

    # 3) stok, tahmin, M46 durumu, CRM
    stock_rows = src.logo_sql(Q.logo_stock_sql())
    stock = {str(r.get("stok_kodu") or "").strip(): float(r.get("depo_stok") or 0) for r in stock_rows if r.get("stok_kodu")}
    fc = bsrc.read_forecast()
    if not fc:
        notes.append("Zeki AI satış tahmini önbellekte yok; tahmin bileşeni boş.")
    devs = _deviations(engine, tenant, year) if tg.get("plan") else {}
    schema = src.schema()
    crm_books: dict[str, dict[str, Any]] = {}
    for r in src.crm(Q.crm_books_sql(schema)):
        code = str(r.get("stok_kodu") or "").strip()
        if code and code not in crm_books:
            crm_books[code] = r
    days = _special_days(src.crm(Q.crm_days_sql(schema)), today)
    links: dict[str, list[str]] = defaultdict(list)
    for r in src.crm(Q.crm_day_links_sql(schema)):
        code = str(r.get("stok_kodu") or "").strip()
        did = str(r.get("gun_id") or "").lower()
        if code in want and did in days and did not in links[code]:
            links[code].append(did)
    frm, to = today - timedelta(days=30), today + timedelta(weeks=st["agendaWeeks"])
    author_rows = src.crm(Q.crm_author_new_sql(schema, frm, to, st["authorRole"]))
    campaigns = src.crm(Q.crm_campaigns_sql(schema, camp_since))
    # Çalışan metinler (sorgu bilgisi: tabloyu dolduran asıl CRM/Logo sorguları)
    ran_sql = {"stok": Q.logo_stock_sql(), "crmKitap": Q.crm_books_sql(schema), "crmGun": Q.crm_days_sql(schema),
               "crmGunBag": Q.crm_day_links_sql(schema), "crmYazar": Q.crm_author_new_sql(schema, frm, to, st["authorRole"]),
               "crmKampanya": Q.crm_campaigns_sql(schema, camp_since)}

    # 4) satırlar
    rows_out: list[dict[str, Any]] = []
    raw: dict[str, dict[str, Optional[float]]] = {k: {} for k in KEYS}
    for code in codes:
        b = info.get(code) or {}
        t = targets.get(code) or {}
        g = t.get("gerceklesme") or {}
        hedef = t.get("hedef") or {}
        son = window_sum(code, w["son12"], w["lastFull"])
        onc = window_sum(code, w["onceki12"], w["son12"] - 1)
        ciro = window_sum(code, w["son12"], w["lastFull"], 1)
        mal = window_sum(code, w["son12"], w["lastFull"], 2)
        malc = window_sum(code, w["son12"], w["lastFull"], 3)
        st_ = stock.get(code)
        oran = None
        if g:
            oran = g.get("oranCiro") if (hedef.get("ciro") or 0) > 0 else g.get("oranAdet")
        dv = devs.get(code)
        cb = crm_books.get(code) or {}
        gunler = sorted((days[d] for d in links.get(code, [])), key=lambda d: (d["baslangic"] or "9999", d["ad"] or ""))
        fcv = B._forecast_total(fc, code) if fc else None
        r = {
            "stok_kodu": code, "kitap_id": (bsrc._clean(cb.get("kitap_id")) or "").lower() or None,
            "ad": b.get("ad") or t.get("ad"), "yazar": b.get("yazar"), "yayinevi": b.get("yayinevi") or t.get("yayinevi"),
            "kitaplik": b.get("kitaplik") or t.get("kitaplik"), "hedef_kitle": bsrc._clean(cb.get("hedef_kitle")),
            "ilk_yayin": b.get("ilk_yayin") or t.get("ilkYayin"), "adet_son12": round(son, 2), "adet_onceki12": round(onc, 2),
            "degisim": change(son, onc), "ciro_son12": round(ciro, 2), "marj": B._margin(mal, malc),
            "stok": st_, "tukenme_ay": tukenme(st_, son), "tahmin12_p50": None if fcv is None else round(fcv, 1),
            "m46_durum": (g.get("durum") if g else ("yok" if not t else "baslamadi")) if kume == "m46" else None,
            "m46_oran": oran, "m46_hedef_adet": hedef.get("adet"), "m46_hedef_ciro": hedef.get("ciro"),
            "sapma_acik": dv is not None, "sapma_acik_tutar": dv.get("gap") if dv else None,
            "ozel_gunler": C.dump(gunler), "dijital": C.dump({"ekitapStokKodu": bsrc._clean(cb.get("ekitap_stok")),
                                                              "ekitapIsbn": bsrc._clean(cb.get("ekitap_isbn"))}),
            "detay_json": C.dump({"satisDurumu": cb.get("satis_durumu"), "yaslar": bsrc._clean(cb.get("yaslar")),
                                  "siniflar": bsrc._clean(cb.get("siniflar")), "turler": bsrc._clean(cb.get("turler")),
                                  "kapak": bsrc._clean(cb.get("kapak")), "statu": b.get("statu"), "crmKarti": bool(cb)}),
        }
        for k, v in component_raw(r).items():
            raw[k][code] = v
        rows_out.append(r)
    pct = {k: percentiles(raw[k]) for k in KEYS}
    asof = C.now()
    for r in rows_out:
        code = r["stok_kodu"]
        p = {k: pct[k][code] for k in KEYS}
        rv = {k: raw[k][code] for k in KEYS}
        r["bilesen_json"] = C.dump({"yuzdelik": p, "ham": {k: (None if v is None else ("inf" if v == math.inf else v))
                                                          for k, v in rv.items()}})
        r["endeks_varsayilan"] = index_of(p, DEFAULT_WEIGHTS)
        r["kume"] = kume
        r["veri_sonu"] = end.isoformat()
        r["asof"] = asof
        r["tenant_id"] = tenant

    series = []
    for code in codes:
        for i, v in (sales.get(code) or {}).items():
            if w["seri"] <= i <= w["lastFull"] and (v[0] or v[1]):
                series.append({"tenant_id": tenant, "stok_kodu": code, "yil_ay": ym(i), "net_adet": round(v[0], 2),
                               "net_ciro": round(v[1], 2)})

    # 5) kampanya etkisi (ay düzeyi): önceki 3 ay, kampanya ayları, sonraki 2 ay
    effects: dict[tuple[str, str], dict[str, Any]] = {}
    for r in campaigns:
        cid = (bsrc._clean(r.get("id")) or "").lower()
        code = str(r.get("stok_kodu") or "").strip()
        a, z = bsrc._day(r.get("baslangic")), bsrc._day(r.get("bitis")) or bsrc._day(r.get("baslangic"))
        if not cid or not code or a is None or (cid, code) in effects:
            continue
        z = max(a, z)
        s, e = B.month_index(a.year, a.month), B.month_index(z.year, z.month)
        need_before = set(range(s - 3, s))
        need_camp = set(range(s, e + 1))
        need_after = set(range(e + 1, e + 3))

        def total(idx: set[int]) -> Optional[float]:
            if not idx or not idx <= loaded or max(idx) > w["lastFull"]:
                return None
            return round(sum((sales.get(code) or {}).get(i, [0.0])[0] for i in idx), 2)

        once, kamp, sonra = total(need_before), total(need_camp), total(need_after)
        kapsam = "tam" if None not in (once, kamp, sonra) else ("suruyor" if once is not None and max(need_after) > w["lastFull"]
                                                                  else "veri-yok")
        effects[(cid, code)] = {
            "tenant_id": tenant, "kampanya_id": cid, "stok_kodu": code[:60], "kampanya_adi": bsrc._clean(r.get("ad")),
            "tip": r.get("tip"), "mecra": r.get("mecra"), "baslangic": a.isoformat(), "bitis": z.isoformat(),
            "ek_iskonto": bsrc._num(r.get("ek_iskonto")), "net_iskonto": bsrc._num(r.get("net_iskonto")),
            "planlanan_ciro": bsrc._num(r.get("planlanan_ciro")), "gerceklesen_ciro": bsrc._num(r.get("gerceklesen_ciro")),
            "once3_adet": once, "kampanya_adet": kamp, "sonra2_adet": sonra, "kapsam": kapsam, "backlist": code in want,
            "asof": asof}

    # 6) CRM eşleşmeleri (özel gün bağı, yazarın yeni kitabı); konu eşleşmeleri korunur
    matches: list[dict[str, Any]] = []
    for code, ids in links.items():
        for did in ids:
            d = days[did]
            matches.append({"stok_kodu": code, "tur": "ozel-gun", "anahtar": did[:80], "etiket": (d["ad"] or "")[:400],
                            "tarih": d["baslangic"], "bitis": d["bitis"], "kaynak": "crm",
                            "detay_json": C.dump({"yontem": d["yontem"], "kesinlik": d["kesinlik"], "gecenYil": d["gecenYil"]})})
    seen_author: set[tuple[str, str]] = set()
    for r in author_rows:
        code = str(r.get("stok_kodu") or "").strip()
        new = str(r.get("yeni_stok") or "").strip()
        if code not in want or not new or code == new or (code, new) in seen_author:
            continue
        seen_author.add((code, new))
        nd = bsrc._day(r.get("yeni_tarih"))
        matches.append({"stok_kodu": code, "tur": "yazar-yeni", "anahtar": new[:80], "etiket": (bsrc._clean(r.get("yeni_ad")) or new)[:400],
                        "tarih": nd.isoformat() if nd else None, "bitis": None, "kaynak": "crm",
                        "detay_json": C.dump({"yazar": bsrc._clean(r.get("yazar"))})})

    with engine.begin() as c:
        c.execute(ROWS.delete().where(ROWS.c.tenant_id == tenant))
        for i in range(0, len(rows_out), 2000):
            c.execute(ROWS.insert(), rows_out[i:i + 2000])
        c.execute(SERIES.delete().where(SERIES.c.tenant_id == tenant))
        for i in range(0, len(series), 5000):
            c.execute(SERIES.insert(), series[i:i + 5000])
        c.execute(EFFECTS.delete().where(EFFECTS.c.tenant_id == tenant))
        vals = list(effects.values())
        for i in range(0, len(vals), 2000):
            c.execute(EFFECTS.insert(), vals[i:i + 2000])
        c.execute(MATCHES.delete().where(MATCHES.c.tenant_id == tenant, MATCHES.c.tur.in_(("ozel-gun", "yazar-yeni"))))
        for m in matches:
            c.execute(MATCHES.insert().values(id=C._uid(), tenant_id=tenant, skor=None, marj=None, onay=None, onaylayan=None,
                                              onay_zamani=None, asof=asof, **m))
    ms = int((C.now() - t0).total_seconds() * 1000)
    meta = {"tarih": today.isoformat(), "veriSonu": end.isoformat(), "sonTamAy": ym(w["lastFull"]),
            "sonTamAyAdi": month_label(w["lastFull"]), "son12": [ym(w["son12"]), ym(w["lastFull"])],
            "onceki12": [ym(w["onceki12"]), ym(w["son12"] - 1)], "seri": [ym(w["seri"]), ym(w["lastFull"])],
            "kume": {**kume_info, "sayi": len(codes)}, "yillar": year_src, "stokSatir": len(stock),
            "tahmin": {"baslangic": fc.get("start"), "guncelleme": fc.get("updatedAt")} if fc else None,
            "sapmaAcik": sum(1 for r in rows_out if r["sapma_acik"]), "kampanya": len({k[0] for k in effects}),
            "eslesme": {"ozel-gun": sum(1 for m in matches if m["tur"] == "ozel-gun"),
                        "yazar-yeni": sum(1 for m in matches if m["tur"] == "yazar-yeni")},
            "sureMs": ms, "notlar": notes, "sql": ran_sql, "hedefYil": year if tg.get("plan") else None}
    C.meta_set(engine, tenant, "backlist", meta)
    return meta


# ------------------------------------------------------------------ okuma: liste


def _row_dict(r: Any, w: dict[str, float]) -> dict[str, Any]:
    comp = C.loads(r.bilesen_json, {})
    p = comp.get("yuzdelik") or {}
    ham = comp.get("ham") or {}
    det = C.loads(r.detay_json, {})
    return {
        "stokKodu": r.stok_kodu, "kitapId": r.kitap_id, "ad": r.ad, "yazar": r.yazar, "yayinevi": r.yayinevi,
        "kitaplik": r.kitaplik, "hedefKitle": r.hedef_kitle, "ilkYayin": r.ilk_yayin, "kapak": det.get("kapak"),
        "adetSon12": r.adet_son12, "adetOnceki12": r.adet_onceki12, "degisim": r.degisim, "ciroSon12": r.ciro_son12,
        "marj": r.marj, "stok": r.stok, "tukenmeAy": r.tukenme_ay,
        "satisYok": r.stok is not None and r.stok > 0 and r.tukenme_ay is None,
        "tahmin12": r.tahmin12_p50, "m46": {"durum": r.m46_durum, "durumAdi": M46_STATES.get(r.m46_durum or "", None),
                                           "oran": r.m46_oran, "hedefAdet": r.m46_hedef_adet, "hedefCiro": r.m46_hedef_ciro,
                                           "sapmaAcik": bool(r.sapma_acik), "acikTutar": r.sapma_acik_tutar},
        "ozelGunler": C.loads(r.ozel_gunler, []), "dijital": C.loads(r.dijital, {}), "detay": det,
        "bilesen": {k: {"yuzdelik": p.get(k), "ham": ham.get(k)} for k in KEYS},
        "endeks": index_of(p, w), "endeksVarsayilan": r.endeks_varsayilan, "kume": r.kume,
    }


def _sort_key(sirala: str) -> Callable[[dict[str, Any]], Any]:
    def neg(v: Optional[float]) -> float:
        return -v if v is not None else math.inf

    if sirala == "endeks":
        return lambda x: (neg(x["endeks"]), x["stokKodu"])
    if sirala == "ad":
        return lambda x: (G.fold(x["ad"] or x["stokKodu"]), x["stokKodu"])
    if sirala in KEYS:
        return lambda x: (neg(x["bilesen"][sirala]["yuzdelik"]), neg(x["endeks"]), x["stokKodu"])
    if sirala == "ciro":
        return lambda x: (neg(x["ciroSon12"]), x["stokKodu"])
    if sirala == "adet":
        return lambda x: (neg(x["adetSon12"]), x["stokKodu"])
    return lambda x: (0 if x["m46"]["sapmaAcik"] else 1, neg(x["endeks"]), x["stokKodu"])


def _upcoming(gunler: list[dict[str, Any]], today: date, weeks: int) -> list[dict[str, Any]]:
    lim = (today + timedelta(weeks=weeks)).isoformat()
    t = today.isoformat()
    return [g for g in gunler if g.get("baslangic") and (g.get("bitis") or g["baslangic"]) >= t and g["baslangic"] <= lim]


#: Liste ucunun ağır parçası (2026-09-29 hız işi): bütün kitap satırlarını okuyup her satırın dört JSON kolonunu
#: ayrıştırmak her istekte (sıralama, süzgeç, sayfa, arama değişince de) baştan yapılıyordu. Satırlar yalnız gece
#: hesabında (`build`) değişir; ağırlıktan, bugünden ve planlardan bağımsız ayrıştırılmış hâl burada süreç içinde tutulur.
#: Her istekte tablo sürümü (`version_stmt`: satır sayısı + en son yazım anı) okunur; değiştiyse beklenerek yeniden okunur,
#: yani bellekteki değer her zaman tablonun şimdiki hâlidir («Verileri yenile» de aynı denetimden geçer). Endeks
#: (ağırlığa bağlı), yaklaşan özel günler (bugüne bağlı) ve planlar (gün içinde değişir) her istekte hesaplanır/okunur.
#: Zaman pencereleri yalnız tablonun elle düzeltildiği (sürümü değiştirmeyen) durumda güvenlik ağıdır.
_TABAN = Bellek("pazarlama.backlist.satirlar", taze=900, bayat=86400, en_cok=32)


def _surum(engine: sa.engine.Engine, tenant: str) -> tuple[int, Optional[str]]:
    with engine.connect() as c:
        n, at = c.execute(version_stmt(tenant)).one()
    return int(n or 0), (None if at is None else str(at))


def _taban_oku(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Satırlar bir kez okunur ve ayrıştırılır. Sürüm satırlardan ÖNCE okunur: arada gece hesabı yazarsa değer eski
    sürümle etiketlenir, sonraki istek farkı görüp yeniden okur (tersi eski satırı yeni sürümle saklardı)."""
    surum = _surum(engine, tenant)
    with engine.connect() as c:
        rows = c.execute(rows_stmt(tenant)).all()
    satirlar: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for r in rows:
        x = _row_dict(r, DEFAULT_WEIGHTS)
        p = {k: x["bilesen"][k]["yuzdelik"] for k in KEYS}   # _row_dict'teki endeksin girdisi (yüzdelikler)
        ara = G.fold(" ".join(str(v or "") for v in (x["ad"], x["yazar"], x["stokKodu"], x["yayinevi"])))
        satirlar.append((x, p, ara))
    items = [s[0] for s in satirlar]
    facets = {"yayinevleri": sorted({x["yayinevi"] for x in items if x["yayinevi"]}, key=G.fold),
              "kitapliklar": sorted({x["kitaplik"] for x in items if x["kitaplik"]}, key=G.fold),
              "hedefKitleler": sorted({x["hedefKitle"] for x in items if x["hedefKitle"]}, key=G.fold)}
    return {"surum": surum, "satirlar": satirlar, "facets": facets}


def _taban(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    anahtar = (id(engine), tenant)
    surum = _surum(engine, tenant)
    t = _TABAN.al(anahtar, lambda: _taban_oku(engine, tenant))
    if t["surum"] != surum:
        t = _TABAN.al(anahtar, lambda: _taban_oku(engine, tenant), zorla=True)
    return t


def isit(engine: sa.engine.Engine, tenant: str) -> None:
    """Gece hesabından sonra listeyi beklemeden arkada hazırlar (ilk açan kişi okumayı beklemesin)."""
    _TABAN.isit((id(engine), tenant), lambda: _taban_oku(engine, tenant))


def list_rows(engine: sa.engine.Engine, tenant: str, *, weights: dict[str, float], sirala: str = "oncelik", yon: str = "",
              yayinevi: str = "", kitaplik: str = "", hedef_kitle: str = "", m46: str = "", stokta: bool = False,
              ozel_gun: str = "", plan: str = "", q: str = "", page: int = 0, page_size: int = PAGE_SIZE,
              agenda_weeks: int = 8, today: Optional[date] = None) -> dict[str, Any]:
    """Süzülmüş, sıralanmış, sayfalı liste; `total` süzgeç sonrası, `hepsi` kümenin tamamı (tavan yok).

    Satırların ayrıştırılmış hâli `_taban`dan gelir (tablo sürümüyle denetlenen süreç içi bellek). Dönen satırlar
    üst düzeyde yeni sözlüktür; iç içe alanlar (m46, bilesen, ozelGunler, dijital, detay) bellekle paylaşılır — onları
    değiştiren çağıran kopyalamalıdır (`backlist_api.hide_money` yeni sözlük kurar)."""
    ensure(engine)
    today = today or C.today()
    taban = _taban(engine, tenant)
    items: list[dict[str, Any]] = []
    folds: list[str] = []
    for base, p, ara in taban["satirlar"]:
        x = dict(base)
        x["endeks"] = index_of(p, weights)
        items.append(x)
        folds.append(ara)
    in_plan = BK.by_codes(engine, tenant, kind="backlist")
    facets = {k: list(v) for k, v in taban["facets"].items()}
    days: dict[str, dict[str, Any]] = {}
    for x in items:
        x["yaklasanGunler"] = _upcoming(x["ozelGunler"], today, agenda_weeks) if x["ozelGunler"] else []
        for g in x["yaklasanGunler"]:
            days.setdefault(g["id"], {"id": g["id"], "ad": g["ad"], "baslangic": g["baslangic"], "kitap": 0})["kitap"] += 1
        x["planlar"] = in_plan.get(x["stokKodu"], [])
    qf = G.fold(q)
    out = []
    for x, fx in zip(items, folds):
        if yayinevi and x["yayinevi"] != yayinevi:
            continue
        if kitaplik and x["kitaplik"] != kitaplik:
            continue
        if hedef_kitle and x["hedefKitle"] != hedef_kitle:
            continue
        if m46:
            want = set(m46.split(","))
            state = "acik" if x["m46"]["sapmaAcik"] else None
            if not ({x["m46"]["durum"] or "yok", state} & want):
                continue
        if stokta and not (x["stok"] or 0) > 0:
            continue
        if ozel_gun == "yakin" and not x["yaklasanGunler"]:
            continue
        if ozel_gun and ozel_gun != "yakin" and not any(g["id"] == ozel_gun for g in x["ozelGunler"]):
            continue
        if plan == "yok" and x["planlar"]:
            continue
        if plan == "var" and not x["planlar"]:
            continue
        if qf and qf not in fx:
            continue
        out.append(x)
    out.sort(key=_sort_key(sirala if sirala in SORTS else "oncelik"))
    if yon == "artan":
        out.reverse()
    page = max(0, int(page))
    return {"items": out[page * page_size:(page + 1) * page_size], "total": len(out), "hepsi": len(items), "page": page,
            "pageSize": page_size, "facets": facets,
            "gunler": sorted(days.values(), key=lambda d: (d["baslangic"] or "", d["ad"] or "")),
            "kpi": {"sapmaAcik": sum(1 for x in items if x["m46"]["sapmaAcik"]),
                    "stokta": sum(1 for x in items if (x["stok"] or 0) > 0),
                    "yakinGun": sum(1 for x in items if x["yaklasanGunler"]),
                    "planli": sum(1 for x in items if x["planlar"])}}


def all_rows(engine: sa.engine.Engine, tenant: str, weights: dict[str, float], **filters: Any) -> list[dict[str, Any]]:
    """Süzgeçli listenin tamamı (dışa aktarım ve özet için; sayfa yok)."""
    first = list_rows(engine, tenant, weights=weights, page=0, page_size=10**9, **filters)
    return first["items"]


def rows_by_code(engine: sa.engine.Engine, tenant: str, codes: Iterable[str]) -> dict[str, dict[str, Any]]:
    want = [x for x in codes if x]
    if not want:
        return {}
    with engine.connect() as c:
        rows = c.execute(sa.select(ROWS).where(ROWS.c.tenant_id == tenant, ROWS.c.stok_kodu.in_(want))).all()
    return {r.stok_kodu: _row_dict(r, DEFAULT_WEIGHTS) for r in rows}


# ------------------------------------------------------------------ fırsat kartı


def suggest_actions(x: dict[str, Any], matches: list[dict[str, Any]], today: date, agenda_weeks: int) -> list[dict[str, str]]:
    """Kural tabanlı eylem adayları ve gerekçesi (karar insanda; fiyat/promosyon yalnız aday)."""
    out: list[dict[str, str]] = []
    stok = x.get("stok")
    if stok is not None and stok <= 0:
        return [{"eylem": "Fırsat değil: stok yok", "gerekce": "Depo stoku sıfır; önce baskı kararı (Baskı Öneri)."}]
    if x["m46"]["sapmaAcik"]:
        out.append({"eylem": "Öncelikli aktivasyon", "gerekce": "Bu yılın satış hedefinde açık sapma uyarısı var."})
    for g in _upcoming(x.get("ozelGunler") or [], today, agenda_weeks):
        out.append({"eylem": f"Özel gün kampanyası: {g['ad']}", "gerekce": f"CRM'de kitaba bağlı; sıradaki tarih {g['baslangic']}."})
    for m in matches:
        if m["tur"] == "yazar-yeni":
            out.append({"eylem": "«Aynı yazardan» kampanyası", "gerekce": f"Yazarın yeni kitabı: {m['etiket']} ({m.get('tarih') or 'tarih yok'})."})
        elif m["tur"] == "konu" and m.get("onay") == "kabul":
            out.append({"eylem": f"Konu kampanyası: {m['etiket']}", "gerekce": "Konu eşleşmesi onaylandı."})
    if (x.get("hedefKitle") or "") in ("Çocuk", "Genç") and (stok or 0) > 0:
        out.append({"eylem": "Okul / kütüphane toplu alım teklifi", "gerekce": f"Hedef kitle {x['hedefKitle']}, stokta."})
    d = x.get("degisim")
    tk = x.get("tukenmeAy")
    if d is not None and d < 0 and (tk is None or tk >= 12) and (stok or 0) > 0:
        out.append({"eylem": "Fiyat / promosyon adayı (karar fiyatlama ve e-ticaret ekibinde)",
                    "gerekce": "Satış düşüyor ve stok bir yıldan uzun yetiyor."})
    if not (x.get("dijital") or {}).get("ekitapStokKodu") and not (x.get("dijital") or {}).get("ekitapIsbn"):
        out.append({"eylem": "Dijital format adayı", "gerekce": "Kitap kartında e-kitap stok kodu ya da ISBN yok; dijital hak "
                                                              "sözleşmeden ayrıca kontrol edilmeli."})
    return out


def detail(engine: sa.engine.Engine, tenant: str, code: str, st: dict[str, Any], weights: dict[str, float],
           today: Optional[date] = None) -> dict[str, Any]:
    ensure(engine)
    today = today or C.today()
    with engine.connect() as c:
        r = c.execute(row_stmt(tenant, code)).first()
        if not r:
            raise C.MarketingError("Kitap backlist listesinde yok.", 404)
        ser = c.execute(series_stmt(tenant, code)).all()
        eff = c.execute(effects_code_stmt(tenant, code)).all()
        mts = c.execute(matches_code_stmt(tenant, code)).all()
    x = _row_dict(r, weights)
    meta = C.meta_get(engine, tenant, "backlist")
    seri_rng = meta.get("seri") or []
    by = {s.yil_ay: s for s in ser}
    months = []
    if len(seri_rng) == 2:
        a = B.month_index(int(seri_rng[0][:4]), int(seri_rng[0][5:7]))
        b_ = B.month_index(int(seri_rng[1][:4]), int(seri_rng[1][5:7]))
        for i in range(a, b_ + 1):
            s = by.get(ym(i))
            months.append({"ay": ym(i), "adet": s.net_adet if s else 0.0, "ciro": s.net_ciro if s else 0.0})
    matches = [match_dict(m) for m in mts]
    x.update({"seri": months, "kampanyalar": [effect_dict(e) for e in eff], "eslesmeler": matches,
              "planlar": BK.by_codes(engine, tenant, [code]).get(code, []),
              "eylemler": suggest_actions(x, matches, today, st["agendaWeeks"]), "veriSonu": r.veri_sonu,
              "asof": C.iso(r.asof)})
    return x


def match_dict(m: Any) -> dict[str, Any]:
    return {"id": m.id, "stokKodu": m.stok_kodu, "tur": m.tur, "turAdi": MATCH_TYPES.get(m.tur, m.tur), "anahtar": m.anahtar,
            "etiket": m.etiket, "tarih": m.tarih, "bitis": m.bitis, "kaynak": m.kaynak, "skor": m.skor, "marj": m.marj,
            "onay": m.onay, "onaylayan": m.onaylayan, "onayZamani": C.iso(m.onay_zamani), "detay": C.loads(m.detay_json, {})}


def effect_dict(e: Any) -> dict[str, Any]:
    def ratio(a: Optional[float], b: Optional[float]) -> Optional[float]:
        return round(a / b - 1, 4) if a is not None and b else None

    months = None
    if e.baslangic and e.bitis:
        a, z = date.fromisoformat(e.baslangic), date.fromisoformat(e.bitis)
        months = (z.year - a.year) * 12 + z.month - a.month + 1
    per_month = None if e.kampanya_adet is None or not months else e.kampanya_adet / months
    before = None if e.once3_adet is None else e.once3_adet / 3
    return {"kampanyaId": e.kampanya_id, "stokKodu": e.stok_kodu, "ad": e.kampanya_adi, "mecra": CAMPAIGN_MEDIA.get(e.mecra or 0),
            "baslangic": e.baslangic, "bitis": e.bitis, "ekIskonto": e.ek_iskonto, "netIskonto": e.net_iskonto,
            "planlananCiro": e.planlanan_ciro, "gerceklesenCiro": e.gerceklesen_ciro, "once3": e.once3_adet,
            "kampanya": e.kampanya_adet, "sonra2": e.sonra2_adet, "kampanyaAyi": months, "kapsam": e.kapsam,
            "aylikDegisim": ratio(per_month, before), "backlist": bool(e.backlist)}


# ------------------------------------------------------------------ gündem


def agenda(engine: sa.engine.Engine, tenant: str, weeks: int, *, today: Optional[date] = None) -> dict[str, Any]:
    """Önümüzdeki `weeks` haftanın özel günleri (bağlı backlist kitapları: stok, geçen yıl aynı ay satışı, planı),
    yazarı yeni kitap çıkaran kitaplar ve konu eşleşmeleri (onay durumuyla). Kitap listeleri tamdır."""
    ensure(engine)
    today = today or C.today()
    lim = (today + timedelta(weeks=weeks)).isoformat()
    t = today.isoformat()
    with engine.connect() as c:
        mts = c.execute(matches_stmt(tenant)).all()
        codes = sorted({m.stok_kodu for m in mts})
        rows = {r.stok_kodu: r for r in c.execute(rows_in_stmt(tenant, codes)).all()}
        ser = c.execute(series_in_stmt(tenant, codes)).all()
    sales = {(s.stok_kodu, s.yil_ay): s.net_adet for s in ser}
    plans = BK.by_codes(engine, tenant, codes, kind="backlist")

    def book(code: str, ref: Optional[str]) -> dict[str, Any]:
        r = rows.get(code)
        last = None
        if ref:
            d = date.fromisoformat(ref)
            last = sales.get((code, f"{d.year:04d}-{d.month:02d}"), 0.0)
        return {"stokKodu": code, "ad": r.ad if r else code, "yazar": r.yazar if r else None, "stok": r.stok if r else None,
                "tukenmeAy": r.tukenme_ay if r else None, "gecenYilAyAdet": last, "planlar": plans.get(code, []),
                "sapmaAcik": bool(r.sapma_acik) if r else False}

    days: dict[str, dict[str, Any]] = {}
    authors: dict[str, dict[str, Any]] = {}
    topics: list[dict[str, Any]] = []
    for m in mts:
        if m.tur == "ozel-gun":
            if not m.tarih or (m.bitis or m.tarih) < t or m.tarih > lim:
                continue
            det = C.loads(m.detay_json, {})
            d = days.setdefault(m.anahtar, {"id": m.anahtar, "ad": m.etiket, "baslangic": m.tarih, "bitis": m.bitis,
                                            "kalanGun": (date.fromisoformat(m.tarih) - today).days, "yontem": det.get("yontem"),
                                            "kesinlik": det.get("kesinlik"), "gecenYil": det.get("gecenYil"), "kitaplar": []})
            d["kitaplar"].append(book(m.stok_kodu, det.get("gecenYil")))
        elif m.tur == "yazar-yeni":
            det = C.loads(m.detay_json, {})
            a = authors.setdefault(m.anahtar, {"stokKodu": m.anahtar, "ad": m.etiket, "tarih": m.tarih, "yazar": det.get("yazar"),
                                               "kitaplar": []})
            a["kitaplar"].append(book(m.stok_kodu, None))
        elif m.tur == "konu":
            if m.tarih and (m.bitis or m.tarih) < t:
                continue
            topics.append({**match_dict(m), "kitap": book(m.stok_kodu, None)})
    for d in days.values():
        d["kitaplar"].sort(key=lambda b: (-(b["gecenYilAyAdet"] or 0), b["stokKodu"]))
        d["stokta"] = sum(1 for b in d["kitaplar"] if (b["stok"] or 0) > 0)
        d["aktivasyonsuz"] = sum(1 for b in d["kitaplar"] if (b["stok"] or 0) > 0 and not b["planlar"])
    topics.sort(key=lambda x: ({"bekliyor": 0, "kabul": 1, "red": 2}.get(x["onay"] or "", 3), x.get("tarih") or "", -(x["skor"] or 0)))
    return {"hafta": weeks, "bugun": t, "gunler": sorted(days.values(), key=lambda d: (d["baslangic"], d["ad"] or "")),
            "yazarlar": sorted(authors.values(), key=lambda a: (a["tarih"] or "", a["ad"] or "")), "konular": topics}


def effects(engine: sa.engine.Engine, tenant: str, yil: Optional[int] = None, *, only_backlist: bool = False) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(effects_stmt(tenant, yil, only_backlist)).all()
        years = sorted({int(r[0][:4]) for r in c.execute(sa.select(EFFECTS.c.baslangic).where(EFFECTS.c.tenant_id == tenant)
                                                                  .distinct()).all() if r[0]}, reverse=True)
    names = rows_by_code(engine, tenant, {r.stok_kodu for r in rows})
    camps: dict[str, dict[str, Any]] = {}
    for r in rows:
        e = effect_dict(r)
        e["kitapAdi"] = (names.get(r.stok_kodu) or {}).get("ad")
        c_ = camps.setdefault(r.kampanya_id, {"kampanyaId": r.kampanya_id, "ad": r.kampanya_adi, "mecra": e["mecra"],
                                              "baslangic": r.baslangic, "bitis": r.bitis, "ekIskonto": r.ek_iskonto,
                                              "netIskonto": r.net_iskonto, "planlananCiro": r.planlanan_ciro,
                                              "gerceklesenCiro": r.gerceklesen_ciro, "kampanyaAyi": e["kampanyaAyi"],
                                              "urunler": [], "once3": 0.0, "kampanya": 0.0, "sonra2": 0.0, "tam": True})
        c_["urunler"].append(e)
        for k in ("once3", "kampanya", "sonra2"):
            if e[k] is None:
                c_["tam"] = False
            else:
                c_[k] += e[k]
    out = []
    for c_ in camps.values():
        months = c_["kampanyaAyi"] or 1
        c_["aylikDegisim"] = round((c_["kampanya"] / months) / (c_["once3"] / 3) - 1, 4) if c_["tam"] and c_["once3"] else None
        c_["backlistUrun"] = sum(1 for u in c_["urunler"] if u["backlist"])
        out.append(c_)
    return {"items": out, "total": len(out), "yillar": years,
            "not": "Ay düzeyinde öncesi/sonrası: kampanya başlangıç ayından önceki 3 ay, kampanya ayları, bitişten sonraki 2 ay "
                   "Logo net adedi. Nedensellik iddiası değildir; aynı dönemde başka etkenler de olabilir."}


# ------------------------------------------------------------------ konu eşleşmesi (Zeki AI)


def _stem_match(a: str, b: str) -> bool:
    """Türkçe ek için iki yönlü önek: «öğretmen» ↔ «öğretmenler» (kısa olan en az 4 harf)."""
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and long_.startswith(short)


def topic_candidates(rows: dict[str, dict[str, Any]], topics: dict[str, list[str]], days: dict[str, dict[str, Any]],
                     linked: set[tuple[str, str]], done: set[tuple[str, str]]) -> list[tuple[str, str, list[str]]]:
    """(stok kodu, özel gün id, eşleşen anahtar) adayları: gün adının anahtar kelimeleri kitabın CRM anahtar kelime/tema/
    tür metninde geçiyor (kelime kökü iki yönlü önekle), kitap stokta, CRM'de bu güne zaten bağlı değil, daha önce sorulmamış. Aday sayısı kesilmez."""
    from semantic_bridge.seo_geo import seasons as S

    out = []
    kws = {did: S.keywords(d.get("ad") or "") for did, d in days.items()}
    for code, words in topics.items():
        r = rows.get(code)
        if not r or not (r.get("stok") or 0) > 0:
            continue
        toks = S.tokens(" ".join(words))
        if not toks:
            continue
        for did, kw_list in kws.items():
            if (code, did) in linked or (code, did) in done:
                continue
            hit = [" ".join(kw) for kw in kw_list if all(any(_stem_match(q, k) for q in toks) for k in kw)]
            if hit:
                out.append((code, did, hit))
    return out


def match_topics(engine: sa.engine.Engine, tenant: str, src: Sources, llm: Any, st: dict[str, Any], mkt: dict[str, Any],
                 *, today: Optional[date] = None) -> dict[str, Any]:
    """Haftalık (BATCH): önümüzdeki `topicWeeks` haftanın özel günleri × backlist kitaplarının konusu. Model kapalı küme
    karar verir; «İlgili» ve «Belirsiz» onaya düşer, emin «İlgisiz» kaydedilir ve bir daha sorulmaz."""
    ensure(engine)
    today = today or C.today()
    if llm is None or not hasattr(llm, "choose"):
        return {"atlandi": "Zeki AI modeli bu kurulumda bağlı değil."}
    schema = src.schema()
    days = {k: v for k, v in _special_days(src.crm(Q.crm_days_sql(schema)), today).items()
            if v["baslangic"] and v["baslangic"] <= (today + timedelta(weeks=st["topicWeeks"])).isoformat()}
    topics: dict[str, list[str]] = defaultdict(list)
    for r in src.crm(Q.crm_topics_sql(schema)):
        code = str(r.get("stok_kodu") or "").strip()
        if code and r.get("kelime"):
            topics[code].append(str(r["kelime"]))
    with engine.connect() as c:
        rows = {r.stok_kodu: {"stok": r.stok, "ad": r.ad, "yazar": r.yazar, "hedef": r.hedef_kitle,
                              "turler": C.loads(r.detay_json, {}).get("turler")}
                for r in c.execute(sa.select(ROWS).where(ROWS.c.tenant_id == tenant)).all()}
        mts = c.execute(sa.select(MATCHES.c.stok_kodu, MATCHES.c.tur, MATCHES.c.anahtar).where(MATCHES.c.tenant_id == tenant)).all()
    for code, r in rows.items():
        if r.get("turler"):
            topics[code].append(r["turler"])
    linked = {(m.stok_kodu, m.anahtar) for m in mts if m.tur == "ozel-gun"}
    done = {(m.stok_kodu, m.anahtar) for m in mts if m.tur == "konu"}
    cands = topic_candidates(rows, topics, days, linked, done)
    counts = {"aday": len(cands), "ilgili": 0, "belirsiz": 0, "ilgisiz": 0}
    for code, did, hit in cands:
        r, d = rows[code], days[did]
        q = (f"Özel gün: {d['ad']} ({d['baslangic']}).\nKitap: {r['ad']} · yazar {r['yazar'] or '—'} · hedef kitle "
             f"{r['hedef'] or '—'}\nKitabın CRM'deki konu etiketleri: {', '.join(sorted(set(topics[code])))[:1500]}\n\n"
             "Bu kitap, bu özel gün için yapılacak bir pazarlama kampanyasında konusu gereği önerilebilir mi?")
        ch = llm.choose(q, TOPIC_CHOICES)
        ok = ch.confident(mkt["minProb"], mkt["minMargin"])
        karar = ch.choice if ok else "Belirsiz"
        onay = "red" if karar == "İlgisiz" else "bekliyor"
        counts[{"İlgili": "ilgili", "İlgisiz": "ilgisiz"}.get(karar or "", "belirsiz")] += 1
        with engine.begin() as c:
            c.execute(MATCHES.insert().values(
                id=C._uid(), tenant_id=tenant, stok_kodu=code, tur="konu", anahtar=did[:80], etiket=(d["ad"] or "")[:400],
                tarih=d["baslangic"], bitis=d["bitis"], kaynak="zeki", skor=ch.probability, marj=ch.margin, onay=onay,
                onaylayan="Zeki AI" if onay == "red" else None, onay_zamani=C.now() if onay == "red" else None,
                detay_json=C.dump({"anahtar": hit, "karar": karar, "modelSecimi": ch.choice, "yontem": ch.method}), asof=C.now()))
    return counts


def decide_match(engine: sa.engine.Engine, tenant: str, user: str, mid: str, karar: str) -> dict[str, Any]:
    if karar not in ("kabul", "red"):
        raise C.MarketingError("Karar kabul ya da red olmalı.")
    with engine.begin() as c:
        m = c.execute(sa.select(MATCHES).where(MATCHES.c.tenant_id == tenant, MATCHES.c.id == str(mid)[:32])).first()
        if not m:
            raise C.MarketingError("Eşleşme bulunamadı.", 404)
        if m.tur != "konu":
            raise C.MarketingError("CRM'deki bağ burada değiştirilmez; yalnız Zeki AI konu eşleşmesi onaylanır.", 409)
        c.execute(MATCHES.update().where(MATCHES.c.id == m.id).values(onay=karar, onaylayan=user, onay_zamani=C.now()))
        m = c.execute(sa.select(MATCHES).where(MATCHES.c.id == m.id)).one()
    return match_dict(m)


# ------------------------------------------------------------------ aktivasyon planı


def _anchor(rows: dict[str, dict[str, Any]], today: date, weeks: int) -> tuple[str, Optional[str]]:
    """Aktivasyon başlangıcı: kitaplara bağlı en yakın özel gün (N hafta içinde), yoksa iki hafta sonrası."""
    near = sorted((g["baslangic"], g["ad"]) for x in rows.values() for g in _upcoming(x.get("ozelGunler") or [], today, weeks)
                  if g["baslangic"] >= today.isoformat())
    if near:
        return near[0][0], near[0][1]
    return (today + timedelta(days=14)).isoformat(), None


def book_reason(x: dict[str, Any]) -> str:
    parts = [f"Uyku endeksi {x['endeksVarsayilan']:.0f}" if x.get("endeksVarsayilan") is not None else "Endeks yok"]
    if x.get("degisim") is not None:
        parts.append(f"satış {x['degisim'] * 100:+.0f}%".replace(".", ","))
    if x.get("tukenmeAy") is not None:
        parts.append(f"stok {x['tukenmeAy']:.0f} ay yeter")
    elif x.get("satisYok"):
        parts.append("stok var, son 12 ayda satış yok")
    if x["m46"]["sapmaAcik"]:
        parts.append("hedefte açık sapma")
    return " · ".join(parts)


def create_activation(engine: sa.engine.Engine, tenant: str, user: str, crm: Any, mkt: dict[str, Any], st: dict[str, Any],
                      body: dict[str, Any], *, today: Optional[date] = None) -> str:
    """Seçilen backlist kitapları için aktivasyon planı taslağı: kitaplar (rol, gerekçe), başlangıç günü, bütçe çerçevesi
    (M15 kuralı: oran × kitapların yıllık hedef cirosu), kanal payı (kitapların CRM pazarlama harcaması, yoksa şirket
    geneli), takvim şablonu ve özel gün işleri. Zeki AI metinleri ayrıca istenir."""
    ensure(engine)
    today = today or C.today()
    items = BK.clean(body.get("kitaplar"))
    rows = rows_by_code(engine, tenant, [x["stok_kodu"] for x in items])
    missing = [x["stok_kodu"] for x in items if x["stok_kodu"] not in rows]
    if missing:
        raise C.MarketingError("Backlist listesinde olmayan kitap: " + ", ".join(missing[:20]) + (" …" if len(missing) > 20 else ""))
    anchor = C.day(body.get("baslangic"), "Başlangıç") if body.get("baslangic") else None
    day_name = None
    if not anchor:
        anchor, day_name = _anchor(rows, today, st["agendaWeeks"])
    first = rows[items[0]["stok_kodu"]]
    title = C.one_line(body.get("baslik"), 400) or (
        (f"{first['ad'] or first['stokKodu']}" if len(items) == 1 else f"{len(items)} kitap")
        + (f" · {day_name}" if day_name else "") + " · backlist aktivasyonu")
    tot_adet = sum((rows[x["stok_kodu"]]["m46"]["hedefAdet"] or 0) for x in items)
    tot_ciro = sum((rows[x["stok_kodu"]]["m46"]["hedefCiro"] or 0) for x in items)
    meta = C.meta_get(engine, tenant, "backlist")
    kume = meta.get("kume") or {}
    hedef = {"year": kume.get("yil"), "planId": kume.get("planId"), "version": kume.get("surum"), "kitap": len(items),
             "adet": round(tot_adet, 2) if tot_adet else None, "ciro": round(tot_ciro, 2) if tot_ciro else None,
             "sapmaAcik": sum(1 for x in items if rows[x["stok_kodu"]]["m46"]["sapmaAcik"]),
             "acikTutar": round(sum(rows[x["stok_kodu"]]["m46"]["acikTutar"] or 0 for x in items), 2),
             "not": None if kume.get("planId") else "Onaylı bütçe planı yok; hedef boş."}
    pid = C.create_plan(engine, tenant, user, kind="backlist", baslik=title,
                        stok_kodu=items[0]["stok_kodu"] if len(items) == 1 else None,
                        crm_kitap_id=first.get("kitapId") if len(items) == 1 else None, yayin_tarihi=anchor,
                        yayin_kaynagi="elle", hedef=hedef, sahip=C.one_line(body.get("sahip"), 120) or user)
    for x in items:
        r = rows[x["stok_kodu"]]
        x["ad"] = x.get("ad") or r["ad"]
        x["gerekce"] = x.get("gerekce") or book_reason(r)
    BK.put(engine, tenant, user, pid, items, system=True)
    frame = P.budget_frame(engine, {"crmButce": None, "hedef": {"ciro": tot_ciro or None}}, mkt)
    if frame.get("gerekce"):
        frame["gerekce"] = (frame["gerekce"].replace("Kitabın hedef cirosu", "Plandaki kitapların bu yılki hedef cirosu toplamı")
                            .replace("kitabın yürürlükte onaylı satış hedefi yok", "plandaki kitapların onaylı satış hedefi yok"))
    try:
        shares = P.channel_shares(crm, [x["stok_kodu"] for x in items], mkt)
    except SourceError as e:
        shares = {"paylar": {}, "taban": {"kaynak": None, "hata": str(e)}}
    lines = P.suggest_lines(frame, shares, anchor)
    if lines:
        C.put_suggested_lines(engine, tenant, user, pid, lines)
    C.set_fields(engine, pid, butce_cerceve=frame.get("tutar"), butce_cerceve_json=C.dump(frame),
                 zeki_json=C.dump({"eylemler": {x["stok_kodu"]: suggest_actions(rows[x["stok_kodu"]], [], today, st["agendaWeeks"])
                                                for x in items},
                                   "paylar": shares, "cerceve": frame, "baslangicKaynagi": day_name or "elle ya da iki hafta sonrası"}))
    tasks = template_tasks(anchor, rows, today)
    if tasks:
        C.replace_tasks(engine, tenant, user, pid, tasks, system=True)
    return pid


def template_tasks(anchor: str, rows: dict[str, dict[str, Any]], today: date) -> list[dict[str, Any]]:
    p = date.fromisoformat(anchor)
    out = [{"gunFarki": g, "tarih": (p + timedelta(days=g)).isoformat(), "is": is_, "kanal": k, "materyalTur": m,
            "durum": "bekliyor", "kaynak": "sablon"} for g, is_, k, m in TASKS]
    seen: set[tuple[str, str]] = set()
    for x in rows.values():
        for g in x.get("ozelGunler") or []:
            b = g.get("baslangic")
            if not b or (g["ad"], b) in seen or not (p - timedelta(days=30) <= date.fromisoformat(b) <= p + timedelta(days=120)):
                continue
            seen.add((g["ad"], b))
            out.append({"tarih": b, "gunFarki": (date.fromisoformat(b) - p).days,
                        "is": f"Özel gün: {g['ad']} — kitaplarla ilgili paylaşımı hazırla", "kanal": "sosyal-medya",
                        "materyalTur": "yeniden-kesfet", "durum": "bekliyor", "kaynak": "ozel-gun"})
    return sorted(out, key=lambda x: x["tarih"])


def activations(engine: sa.engine.Engine, tenant: str, *, durum: str = "", include_archive: bool = False) -> dict[str, Any]:
    heads = C.list_plans(engine, tenant, kind="backlist", durum=durum, include_archive=include_archive)
    for h in heads:
        h["kitaplar"] = BK.of(engine, h["id"])
        h["lines"] = C.plan_full(engine, tenant, h["id"])["lines"]      # «CRM'e işlenecek kampanya» bitiş günü için
    heads.sort(key=lambda h: (h["yayinTarihi"] or "", h["id"]), reverse=True)
    return {"items": heads, "total": len(heads)}


# ------------------------------------------------------------------ Zeki AI içerik taslağı


def _brief(books_: list[dict[str, Any]], details: dict[str, Optional[dict[str, Any]]], budget: int = 14000) -> tuple[str, list[str]]:
    """Kitap bilgisi ve CRM metinleri; her kitabın metni eşit paya kırpılır (liste kesilmez). Dönen: metin, kaynaklar."""
    per = max(400, budget // max(1, len(books_)))
    parts, sources = [], []
    for b in books_:
        d = details.get(b["stokKodu"]) or {}
        head = [f"Kitap: {d.get('ad') or b.get('ad') or b['stokKodu']}", f"Yazar: {d.get('yazar') or '—'}",
                f"Yayınevi: {d.get('yayinevi') or '—'}", f"Kitaplık: {d.get('kitaplik') or '—'}",
                f"Hedef kitle: {d.get('hedefKitle') or '—'}", f"Türler: {d.get('turler') or '—'}"]
        sources += [x for x in (d.get("ad") or b.get("ad"), d.get("yazar"), d.get("yayinevi"), d.get("kitaplik"),
                                d.get("hedefKitle"), d.get("turler")) if x]
        texts = []
        for field in ("new_ozet", "new_kitapspotu", "new_kitabinenonemlicumlesi", "new_alintlar", "new_kitabinonecikanyanlari"):
            t = (d.get("metinler") or {}).get(field)
            if t:
                texts.append(t)
                sources.append(t)
        body = "\n".join(texts)[:per]
        parts.append(" · ".join(head) + (f"\n{body}" if body else ""))
    return "\n\n".join(parts), sources


def facts_for(plan: dict[str, Any], rows: dict[str, dict[str, Any]], matches: list[dict[str, Any]]) -> list[str]:
    """Modele verilen olgular (metinde geçebilecek sayılar yalnız bunlar): başlangıç günü, özel gün tarihleri, hedef yaş."""
    f = []
    if plan.get("yayinTarihi"):
        f.append(f"Kampanya başlangıcı: {P._tr_day(plan['yayinTarihi'])}")
    seen = set()
    for x in rows.values():
        for g in x.get("ozelGunler") or []:
            if g.get("baslangic") and g["ad"] not in seen:
                seen.add(g["ad"])
                f.append(f"Özel gün: {g['ad']} — {P._tr_day(g['baslangic'])}")
        yas = (x.get("detay") or {}).get("yaslar")
        if yas:
            f.append(f"{x['ad']} yaş aralığı: {yas}")
    for m in matches:
        if m["tur"] == "yazar-yeni":
            f.append(f"Yazarın yeni kitabı: {m['etiket']}" + (f" ({P._tr_day(m['tarih'])})" if m.get("tarih") else ""))
    return f


def draft(llm: Any, plan: dict[str, Any], books_: list[dict[str, Any]], rows: dict[str, dict[str, Any]],
          details: dict[str, Optional[dict[str, Any]]], matches: list[dict[str, Any]], tur: str,
          mkt: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if tur not in MATERIAL_PROMPTS:
        raise C.MarketingError("Bu tür için backlist taslağı yazılmaz.")
    brief, sources = _brief(books_, details)
    facts = facts_for(plan, rows, matches)
    hooks = [m for m in facts if m.startswith(("Özel gün", "Yazarın yeni kitabı"))]
    prompt = (f"{MATERIAL_PROMPTS[tur]}\n\nGündem kancası: " + ("; ".join(hooks) if hooks else "yok") +
              "\n\nOlgu listesi (yazabileceğin sayılar yalnız bunlar):\n" + ("\n".join(facts) or "—") +
              f"\n\nKitaplar ve CRM'deki metinleri:\n{brief}")
    raw = P._chat(llm, prompt, 2200)
    res = G.check(raw, sources + [m["etiket"] for m in matches if m.get("etiket")], facts, mkt.get("claims") or ())
    return res["metin"], {"dusen": res["dusen"], "sayac": res["sayac"], "dusenSayisi": res["dusenSayisi"], "tur": tur}


# ------------------------------------------------------------------ bildirimler


def first_workday(d: date) -> bool:
    """Ayın ilk iş günü (Pazartesi–Cuma; resmî tatil takvimi yok)."""
    first = date(d.year, d.month, 1)
    while first.weekday() >= 5:
        first += timedelta(days=1)
    return d == first


def digest_month(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], link: str) -> Optional[str]:
    """Aylık «bu ayın fırsatları»: eşik üstü kitapların tamamının sayısı (liste ekranda; e-postada sayı ve bağlantı)."""
    items = all_rows(engine, tenant, DEFAULT_WEIGHTS)
    if not items:
        return None
    meta = C.meta_get(engine, tenant, "backlist")
    over = [x for x in items if (x["endeks"] or 0) >= st["digestMin"] and (x["stok"] or 0) > 0]
    dev = [x for x in items if x["m46"]["sapmaAcik"]]
    near = [x for x in items if x["yaklasanGunler"]]
    lines = [f"Backlist fırsatları ({C.today().strftime('%m.%Y')}; Logo verisi {meta.get('veriSonu') or '—'} tarihine kadar):", "",
             f"- Backlist'te {len(items)} kitap; stokta ve uyku endeksi {st['digestMin']:g} ve üstü: {len(over)} kitap.",
             f"- Satış hedefinde açık sapma uyarısı olan: {len(dev)} kitap.",
             f"- Önümüzdeki {st['agendaWeeks']} haftada özel günü olan: {len(near)} kitap.", "",
             f"Liste ve bileşenler: {link}" if link else "Liste: Pazarlama › Planlama › Backlist"]
    return "\n".join(lines)


def remind_days(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], *, today: Optional[date] = None) -> list[dict[str, Any]]:
    """Başlangıcına `remindWeeks` hafta ya da daha az kalan, daha önce hatırlatılmamış özel günler: bağlı, stoklu ve
    backlist planı olmayan kitap sayısıyla."""
    today = today or C.today()
    ag = agenda(engine, tenant, st["remindWeeks"], today=today)
    out = []
    for d in ag["gunler"]:
        key = f"backlist-remind:{d['id']}:{d['baslangic']}"
        if d["aktivasyonsuz"] and not C.meta_get(engine, tenant, key).get("_at"):
            out.append({**d, "_key": key})
    return out
