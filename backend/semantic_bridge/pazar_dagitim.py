"""M39 Pazar — dağıtımcı ve perakende katalogları (Başarı Dağıtım, D&R): görüntü saklama, çıkış endeksi, eşleme.

**Kaynak (yalnız okuma):** Logo sunucusundaki `API_URUN_DB` (bağlantı: Logo bağlantı dosyası, üç parçalı ad). `zekiai`
orada yalnız `db_datareader`'dır; bu veritabanına hiçbir koşulda yazılmaz. **Yalnız müşterinin kullandığı nesneler**
(kullanıcı kararı 2026-09-29): `basari_list`, `prefix_list` ve ikisinin birleşimi olan `urun_list` görünümü.
`urun_list_BACKUP`, `LOGO_TARCIN_ITEM_LIST`, `urun_raf`, `LOGO_TO_BASARI`, `URUN_LIST_TO_LOGO` kullanılmaz.

- `basari_list`: Başarı kataloğu, güncel tek görüntü (kaynak kendi üstüne yazar). Stok = `depo_stok`.
- `prefix_list`: D&R'nin «Prefix» servisinden (dataprefix.dr.com.tr, Product/List) alınmış katalog, güncel tek görüntü.
  Alan anlamları D&R'nin servis belgesinden (Xml-Service, 2026-09-29'da kullanıcı verdi): `deleted` 1 = ürün D&R ve
  İdefix sitelerinden silinmiş (Prefix B2B'de satışı sürebilir); `sale_status_code` sitelerin durumu (0 satışa açık,
  1 stokta yok, 4 satış dışı); `available_stock` sitelerin toplam stoğu; `b2bstock` + `prefix_sale_status` (0 stokta
  yok, 1 satışa açık) Prefix B2B'nin stoğu ve durumu — belge ikisinin karıştırılmamasını söyler. Sitede 999, 500.000,
  10.000.014 gibi değerler sayım değil yer tutucudur (≥ `SITE_STOK_TAVAN` saklanmaz). Kaynak 20.000'lik sayfalarla
  okunur; `row_num` üst sınırı ile satır sayısı farkı eksik sayfayı gösterir (2026-09-25 görüntüsünde 17. sayfa yok).
- `urun_list` = `basari_list` (Tedarikci «Başarı Dağıtım») ∪ `prefix_list` (Tedarikci «Prefix»; stok = site stoğu,
  fiyat = liste fiyatı; kategori, yazar, durum, D&R fiyatı yok, marka boş). Ayrıntıyı kaybetmemek için iki tablo
  doğrudan okunur; aynı satırlardır.
- Başarı'daki `rc`, `pc`, `rn` iş verisi değildir: kaynağın bildirdiği toplam kayıt, sayfa, satır numarası.

**Saklama:** kaynak geçmiş tutmadığı için her görüntüde **yalnız değişen satır** `semantic_pazar_dagitim_obs`'a yazılır
(stok, fiyat, iskonto, durum, baskı no). Satır bir önceki stoğu da taşır; çıkış = max(0, önceki − şimdiki), giriş tersi.
Güncel hâl `semantic_pazar_dagitim_titles`'ta. Aynı kaynak tarihli görüntü ikinci kez işlenmez.

**Çıkış endeksi:** dağıtımcı deposundan perakendeye çıkış; okura satış değildir, «pazar payı» diye sunulmaz. Geçmiş
kaynakta yok: endeks bizim görüntülerimiz biriktikçe (en az iki) oluşur. Görüntü aralığında gelip giden stok görünmez;
TİMAŞ kitaplarında Logo'daki Başarı sevkiyle tutarlılığı `calibration()` her turda ölçer ve ekran gösterir.

**TİMAŞ markası:** elle liste yok. Bir marka, başlıklarının en az `PAZAR_DAGITIM_TIMAS_ORAN`'ı (varsayılan 0,8) TİMAŞ
firmalarının (`firm_scope`) güncel yıl Logo barkodunda bulunuyorsa TİMAŞ sayılır. Logo'da başka yayınevlerinin satış
için açılmış kartları da var (Tarçın); oran bunları eler.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic.pazar.dagitim")
_md = sa.MetaData()

KAYNAK = {"basari": "Başarı Dağıtım kataloğu", "dr": "D&R kataloğu"}
DB = "API_URUN_DB.dbo"

TITLES = sa.Table(
    "semantic_pazar_dagitim_titles", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kaynak", sa.String(10), primary_key=True),
    sa.Column("barkod", sa.String(20), primary_key=True),
    sa.Column("ad", sa.String(400)),
    sa.Column("yazar", sa.String(300)),
    sa.Column("cevirmen", sa.String(300)),
    sa.Column("yayinevi", sa.String(200), index=True),
    sa.Column("kategori", sa.String(300), index=True),       # Başarı «Üst>Alt», D&R «Kitap|…» yolu
    sa.Column("ust_kategori", sa.String(120), index=True),
    sa.Column("sayfa", sa.Integer),
    sa.Column("kapak", sa.String(60)),
    sa.Column("kagit", sa.String(60)),
    sa.Column("basim_yili", sa.Integer),
    sa.Column("stok", sa.Integer),                            # Başarı deposu; D&R'de Prefix B2B stoğu
    sa.Column("site_stok", sa.Integer),                       # D&R + İdefix sitelerinin stoğu (yer tutucu hariç)
    sa.Column("fiyat", sa.Float),                             # liste fiyatı
    sa.Column("iskonto", sa.Float),                           # Başarı iskontosu %
    sa.Column("dr_fiyat", sa.Float),                          # D&R satış fiyatı
    sa.Column("durum", sa.String(60)),                        # Başarı stok_durum; D&R ham «deleted/prefix/sale»
    sa.Column("baski_no", sa.Integer),
    sa.Column("timas", sa.Boolean, nullable=False, default=False),
    sa.Column("stok_kodu", sa.String(60), index=True),        # Logo ITEMS.CODE (barkod eşleşmesi)
    sa.Column("ilk_gorulme", sa.Date),
    sa.Column("son_gorulme", sa.Date),
    sa.Column("guncellendi_at", sa.DateTime(timezone=True)),
)
OBS = sa.Table(
    "semantic_pazar_dagitim_obs", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kaynak", sa.String(10), primary_key=True),
    sa.Column("barkod", sa.String(20), primary_key=True),
    sa.Column("tarih", sa.Date, primary_key=True),
    sa.Column("stok", sa.Integer),
    sa.Column("onceki_stok", sa.Integer),
    sa.Column("site_stok", sa.Integer),
    sa.Column("cikis", sa.Integer, nullable=False, default=0),
    sa.Column("giris", sa.Integer, nullable=False, default=0),
    sa.Column("fiyat", sa.Float),
    sa.Column("iskonto", sa.Float),
    sa.Column("dr_fiyat", sa.Float),
    sa.Column("durum", sa.String(60)),
    sa.Column("baski_no", sa.Integer),
    sa.Column("ilk", sa.Boolean, nullable=False, default=False),   # başlığın ilk görüldüğü görüntü
)
sa.Index("ix_pazar_dagitim_obs_tarih", OBS.c.tenant_id, OBS.c.kaynak, OBS.c.tarih)
SNAPS = sa.Table(
    "semantic_pazar_dagitim_snapshots", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kaynak", sa.String(10), primary_key=True),
    sa.Column("tarih", sa.Date, primary_key=True),
    sa.Column("kaynak_zamani", sa.String(30)),                # kaynağın kendi damgası
    sa.Column("yontem", sa.String(10), nullable=False),       # gece | elle
    sa.Column("satir", sa.Integer, nullable=False),
    sa.Column("degisen", sa.Integer, nullable=False),
    sa.Column("yeni", sa.Integer, nullable=False),
    sa.Column("kaybolan", sa.Integer, nullable=False, default=0),
    sa.Column("bildirilen", sa.Integer),                      # kaynağın bildirdiği kayıt sayısı (eksik sayfa denetimi)
    sa.Column("okundu_at", sa.DateTime(timezone=True), nullable=False),
)
BARKOD = sa.Table(
    # Logo barkod ↔ stok kodu (çoklu: aynı barkod iki kartta olabilir, ör. «0903» ve «0903B»). Her turda yenilenir.
    "semantic_pazar_dagitim_barkod", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("barkod", sa.String(20), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
)
META = sa.Table(
    "semantic_pazar_dagitim_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(60), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

#: Ekranın her yerde yazacağı notlar (rakamın ne olduğu ve ne olmadığı).
NOTLAR = {
    "endeks": ("Çıkış endeksi, dağıtımcı deposundaki stok düşüşünün toplamıdır: kitapçılara çıkış, okura satış değil. "
               "Kaynak geçmiş tutmaz; endeks portalın her gün aldığı görüntülerden oluşur. Görüntüler arasında gelip "
               "giden stok görünmediği için adet gerçeğin altındadır. Pazar payı değildir."),
    "dr": ("D&R'de iki stok var: Prefix B2B stoğu (kitapçılara toptan satış) ve D&R ile İdefix sitelerinin stoğu. Sitede "
           "999 ve üstü değerler sayım değil, gösterilmez. «Site: silinmiş» ürün sitelerden kalkmıştır, Prefix'te satışı "
           "sürebilir."),
    "timas": ("TİMAŞ grubu elle seçilmez: başlıklarının en az %80'i TİMAŞ'ın Logo'sunda kartı olan markalardır. TİMAŞ'ın "
              "dağıttığı başka şirket markaları da (ör. Mavi Kirpi, Uçan Kitap) bu gruba girer; perakendede satılan tek "
              "tük başka yayınevi kitabı girmez."),
}

F_CIKIS = ("Çıkış endeksi = ardışık iki görüntü arasında Başarı deposundaki stok düşüşü (önceki − şimdiki, sıfırın altı "
           "sayılmaz), pencere içindeki görüntülerde toplanır. 35 günden uzun aralıkta ve katalogdan çıkıp dönen başlıkta "
           "hesaplanmaz. TİMAŞ payı = TİMAŞ markalarının çıkışı ÷ kategorinin çıkışı. Kitapçılara çıkıştır, okura satış "
           "ya da pazar payı değildir.")
F_KALIBRASYON = ("Kalibrasyon = aynı pencerede TİMAŞ'ın Logo'daki Başarı carisine sevki (satış − iade, kitap bazında) ile "
                 "Başarı deposundaki çıkışın karşılaştırması: kitap bazında korelasyon ve toplam oranı (katsayı).")

#: Gözlem satırında değişimi aranan alanlar (bunlardan biri değişince satır yazılır).
WATCHED = ("stok", "site_stok", "fiyat", "iskonto", "dr_fiyat", "durum", "baski_no")
#: D&R site stoğunda bu ve üstü değer sayım değil yer tutucudur (999, 500.000, 10.000.014 görüldü).
SITE_STOK_TAVAN = 999
DR_SITE = {"0": "Satışa açık", "1": "Stokta yok", "4": "Satış dışı"}
DR_PREFIX = {"0": "Stokta yok", "1": "Satışa açık"}

_ready: set[int] = set()
_lock = threading.Lock()


class DagitimError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)   # sürüm damgası: tanım değişmediyse açılışta veritabanına sorulmaz
        _add_columns(engine)
        _ready.add(id(engine))


def _add_columns(engine: sa.engine.Engine) -> None:
    """Sonradan eklenen kolonlar (tablo önceden kurulmuşsa): yalnız ekler, hiçbir şey silmez."""
    insp = sa.inspect(engine)
    for table in (TITLES, OBS, SNAPS):
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in have:
                with engine.begin() as c:
                    c.execute(sa.text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} "
                                      f"{col.type.compile(dialect=engine.dialect)}"))


def now() -> datetime:
    return datetime.now(timezone.utc)


def _conf(key: str, default: str) -> str:
    try:
        from semantic_bridge import admin as admin_mod

        v = admin_mod.conf(key)
    except Exception:  # noqa: BLE001 — testte admin ayarı yok
        v = ""
    return v if v not in (None, "") else os.environ.get(key, default)


def settings() -> dict[str, Any]:
    def f(key: str, default: float) -> float:
        try:
            return float(str(_conf(key, str(default))).replace(",", "."))
        except ValueError:
            return default
    return {
        "timasOran": f("PAZAR_DAGITIM_TIMAS_ORAN", 0.8),
        "timasMinBaslik": int(f("PAZAR_DAGITIM_TIMAS_MIN_BASLIK", 5)),
        "basariCari": _conf("PAZAR_DAGITIM_BASARI_CARI", "12001.01.BA104"),
        "kaynaklar": [k for k in _conf("PAZAR_DAGITIM_KAYNAKLAR", "basari,dr").split(",") if k.strip() in KAYNAK],
            # İki görüntü arası bundan uzunsa (ör. zamanlayıcı aylarca durmuşsa) çıkış/giriş hesaplanmaz: uzun aralıkta
        # gelip giden stok görünmez, tek bir dev «çıkış» ay serisini bozardı.
        "aralikGun": int(f("PAZAR_DAGITIM_ARALIK_GUN", 35)),
        # Kaynağın kendi damgası bundan eskiyse ekran «N gündür yenilenmedi» uyarısını turuncu yazar.
        "bayatGun": int(f("PAZAR_DAGITIM_BAYAT_GUN", 2)),
    }


def meta_get(engine: sa.engine.Engine, tenant: str, key: str, default: Any = None) -> Any:
    import json

    with engine.connect() as c:
        r = c.execute(sa.select(META.c.value_json).where(META.c.tenant_id == tenant, META.c.key == key)).first()
    try:
        return json.loads(r[0]) if r else default
    except ValueError:
        return default


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: Any) -> None:
    import json

    raw = json.dumps(value, ensure_ascii=False, default=str)
    with engine.begin() as c:
        n = c.execute(META.update().where(META.c.tenant_id == tenant, META.c.key == key)
                      .values(value_json=raw, updated_at=now())).rowcount
        if not n:
            c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=raw, updated_at=now()))


# ================================================================================ ayrıştırma

_DIGITS = re.compile(r"\D+")
_BASKI = re.compile(r"(\d+)")


def barkod(v: Any) -> Optional[str]:
    """Yalnız rakamlar (`seo_geo.crm.ean_key` ile aynı kural); 8–14 hane değilse None."""
    d = _DIGITS.sub("", str(v or ""))
    return d if 8 <= len(d) <= 14 else None


def _txt(v: Any, n: int) -> Optional[str]:
    t = " ".join(str(v).split()) if v is not None else ""
    return t[:n] or None


def _int(v: Any) -> Optional[int]:
    try:
        return int(float(str(v).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _num(v: Any) -> Optional[float]:
    try:
        x = float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return round(x, 2)


def baski_no(v: Any) -> Optional[int]:
    """«3. Baskı» → 3; boş ya da sayısız → None."""
    m = _BASKI.search(str(v or ""))
    return int(m.group(1)) if m else None


def _day(v: Any) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v).strip()[:10]).date()
    except ValueError:
        return None


def ust(kategori: Optional[str], kaynak: str) -> Optional[str]:
    if not kategori:
        return None
    if kaynak == "dr":
        parts = [p for p in kategori.split("|") if p]
        return (parts[1] if len(parts) > 1 and parts[0] == "Kitap" else parts[0]) if parts else None
    return kategori.split(">")[0].strip() or None


def basari_row(r: dict[str, Any]) -> Optional[dict[str, Any]]:
    b = barkod(r.get("barkod"))
    if not b:
        return None
    kat = _txt(r.get("kategori"), 300)
    stok = _int(r.get("depo_stok"))
    return {"barkod": b, "ad": _txt(r.get("urun_ad"), 400), "yazar": _txt(r.get("yazar"), 300),
            "cevirmen": _txt(r.get("cevirmen"), 300), "yayinevi": _txt(r.get("marka"), 200), "kategori": kat,
            "ust_kategori": ust(kat, "basari"), "sayfa": _int(r.get("sayfasayisi")) or None,
            "kapak": _txt(r.get("kapak_turu"), 60), "kagit": _txt(r.get("kagit_cinsi"), 60),
            "basim_yili": _int(r.get("basimyili")) or None, "stok": stok if stok is not None else 0,
            "site_stok": None, "fiyat": _num(r.get("satis_fiyat")), "iskonto": _num(r.get("iskonto")), "dr_fiyat": None,
            "durum": _txt(r.get("stok_durum"), 60), "baski_no": baski_no(r.get("baski_sayisi"))}


def dr_row(r: dict[str, Any]) -> Optional[dict[str, Any]]:
    """D&R Prefix satırı (alan anlamları D&R servis belgesinden). Stok = Prefix B2B; site stoğu ayrı, yer tutucu değeri
    saklanmaz. Durum = «Site: … · Prefix: …» (silinmişse «Site: silinmiş»)."""
    b = barkod(r.get("isbn"))
    if not b:
        return None
    kat = _txt(r.get("bread_crumb"), 300)
    sil = str(r.get("deleted") or "").strip() == "1"
    site = "silinmiş" if sil else DR_SITE.get(str(r.get("sale_status_code") or "").strip(), "?")
    pre = DR_PREFIX.get(str(r.get("prefix_sale_status") or "").strip(), "?")
    ss = _int(r.get("available_stock"))
    return {"barkod": b, "ad": _txt(r.get("name"), 400), "yazar": None, "cevirmen": None,
            "yayinevi": _txt(r.get("brand_name"), 200), "kategori": kat, "ust_kategori": ust(kat, "dr"), "sayfa": None,
            "kapak": _txt(r.get("characteristic_value"), 60), "kagit": None, "basim_yili": None,
            "stok": _int(r.get("b2bstock")) or 0,
            "site_stok": None if sil or ss is None or ss >= SITE_STOK_TAVAN else ss,
            "fiyat": _num(r.get("list_price")), "iskonto": None, "dr_fiyat": _num(r.get("dr_price")),
            "durum": f"Site: {site} · Prefix: {pre}"[:60], "baski_no": None}


# ================================================================================ kaynak okuma (SQL)

Runner = Callable[[str], list[dict[str, Any]]]

BASARI_COLS = ("barkod, urun_ad, yazar, cevirmen, marka, kategori, sayfasayisi, kapak_turu, kagit_cinsi, basimyili, "
               "depo_stok, satis_fiyat, iskonto, stok_durum, baski_sayisi")
SQL_BASARI_DAMGA = f"SELECT MAX(tarih) AS t, COUNT(*) AS n, MAX(TRY_CAST(rc AS int)) AS bildirilen FROM {DB}.basari_list"
SQL_BASARI = f"SELECT {BASARI_COLS} FROM {DB}.basari_list"
SQL_DR_DAMGA = f"SELECT MAX(tarih) AS t, COUNT(*) AS n, MAX(row_num) AS bildirilen FROM {DB}.prefix_list"
SQL_DR = (f"SELECT isbn, name, brand_name, bread_crumb, characteristic_value, b2bstock, available_stock, list_price, dr_price, deleted, "
          f"prefix_sale_status, sale_status_code FROM {DB}.prefix_list")
def sql_logo_barkod(firm: str) -> str:
    return (f"SELECT B.BARCODE AS barkod, I.CODE AS stok_kodu FROM dbo.LG_{firm}_UNITBARCODE AS B "
            f"JOIN dbo.LG_{firm}_ITEMS AS I ON I.LOGICALREF = B.ITEMREF "
            f"WHERE B.BARCODE IS NOT NULL AND LTRIM(RTRIM(B.BARCODE)) <> ''")


def sql_logo_sevk(firm: str, cari: str, bas: date, son: date) -> str:
    """TİMAŞ → dağıtımcı sevk (TRCODE 8) eksi iade (3), kitap bazında. Aynı tanım belgede doğrulandı (2025, r≈0,94)."""
    c = cari.replace("'", "''")
    return (f"SELECT B.BARCODE AS barkod, SUM(CASE WHEN L.TRCODE = 8 THEN L.AMOUNT ELSE -L.AMOUNT END) AS net "
            f"FROM dbo.LG_{firm}_01_STLINE AS L JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = L.CLIENTREF "
            f"JOIN dbo.LG_{firm}_UNITBARCODE AS B ON B.ITEMREF = L.STOCKREF "
            f"WHERE C.CODE = '{c}' AND L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.TRCODE IN (3, 8) "
            f"AND L.DATE_ >= '{bas.isoformat()}' AND L.DATE_ < '{son.isoformat()}' GROUP BY B.BARCODE")


def parse(rows: Iterable[dict[str, Any]], kaynak: str) -> dict[str, dict[str, Any]]:
    fn = basari_row if kaynak == "basari" else dr_row
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        x = fn(r)
        if x is None:
            continue
        prev = out.get(x["barkod"])
        # Aynı barkod iki satırsa stoğu büyük olan (kaynakta çift kayıt nadir; 234.705 satır / 234.694 barkod)
        if prev is None or (x["stok"] or 0) > (prev["stok"] or 0):
            out[x["barkod"]] = x
    return out


# ================================================================================ görüntü işleme

#: Başlığın tanım alanları: değişirse güncel hâl yenilenir, gözlem satırı yazılmaz.
DESC = ("ad", "yazar", "cevirmen", "yayinevi", "kategori", "ust_kategori", "sayfa", "kapak", "kagit", "basim_yili")
#: Bellekteki hâl: (tanım imzası, *WATCHED, son_gorulme, stok_kodu) — 386 bin satırda sözlük yerine demet.
_SIG, _SON, _KOD = 0, 1 + len(WATCHED), 2 + len(WATCHED)


def _sig(x: Any) -> int:
    return hash(tuple(x[k] for k in DESC))


def _w(t: tuple, k: str) -> Any:
    return t[1 + WATCHED.index(k)]


def _state(engine: sa.engine.Engine, tenant: str, kaynak: str) -> dict[str, tuple]:
    T = TITLES.c
    cols = [T.barkod, *(getattr(T, k) for k in DESC), *(getattr(T, k) for k in WATCHED), T.son_gorulme, T.stok_kodu]
    out: dict[str, tuple] = {}
    with engine.connect() as c:
        for r in c.execute(sa.select(*cols).where(T.tenant_id == tenant, T.kaynak == kaynak)).mappings():
            out[r["barkod"]] = (_sig(r), *(r[k] for k in WATCHED), r["son_gorulme"], r["stok_kodu"])
    return out


def processed(engine: sa.engine.Engine, tenant: str, kaynak: str) -> dict[date, str]:
    S = SNAPS.c
    with engine.connect() as c:
        return {r.tarih: r.yontem for r in c.execute(sa.select(S.tarih, S.yontem).where(
            S.tenant_id == tenant, S.kaynak == kaynak)).all()}


_UPD_KEYS = (*DESC, *WATCHED, "stok_kodu", "son_gorulme", "guncellendi_at")


def _update_stmt(tenant: str, kaynak: str):
    T = TITLES.c
    return (TITLES.update().where(T.tenant_id == tenant, T.kaynak == kaynak, T.barkod == sa.bindparam("b_"))
            .values({k: sa.bindparam("v_" + k) for k in _UPD_KEYS}))


def apply(engine: sa.engine.Engine, tenant: str, kaynak: str, tarih: date, items: dict[str, dict[str, Any]], *,
          yontem: str, kaynak_zamani: Optional[str] = None, logo: Optional[dict[str, str]] = None,
          state: Optional[dict[str, tuple]] = None, bildirilen: Optional[int] = None) -> dict[str, Any]:
    """Bir görüntüyü işler: izlenen alanı değişen satırı gözleme yazar, güncel hâli yeniler. Görüntü tarihi son
    işlenenden eski olamaz (önceki stok yanlış kurulurdu). `state` verilirse (arşiv döngüsü) yerinde güncellenir.

    Kaynaktan düşen başlık sıfır stok sayılmaz (katalogdan çıkış satış değildir); yeniden görünürse arada ne olduğu
    bilinmediği için o görüntüde çıkış/giriş hesaplanmaz."""
    ensure(engine)
    done = processed(engine, tenant, kaynak)
    if tarih in done:
        return {"kaynak": kaynak, "tarih": tarih.isoformat(), "skipped": "bu tarihli görüntü zaten işlendi"}
    prev = max(done) if done else None
    if prev and tarih < prev:
        raise DagitimError(f"{KAYNAK[kaynak]}: {tarih} tarihli görüntü son işlenenden ({prev}) eski; önceki stok "
                           "kurulamaz.")
    st = state if state is not None else _state(engine, tenant, kaynak)
    logo = logo or {}
    uzun = prev is not None and (tarih - prev).days > settings()["aralikGun"]
    at = now()
    obs: list[dict[str, Any]] = []
    new_titles: list[dict[str, Any]] = []
    upd: list[dict[str, Any]] = []
    yeni = degisen = donen = 0
    for b, x in items.items():
        p = st.get(b)
        kod = logo.get(b)
        rest = {k: x[k] for k in WATCHED if k != "stok"}
        if p is None:
            yeni += 1
            obs.append({"tenant_id": tenant, "kaynak": kaynak, "barkod": b, "tarih": tarih, "stok": x["stok"],
                        "onceki_stok": None, "cikis": 0, "giris": 0, "ilk": prev is not None, **rest})
            new_titles.append({"tenant_id": tenant, "kaynak": kaynak, "barkod": b, "timas": False, "ilk_gorulme": tarih,
                               "son_gorulme": tarih, "stok_kodu": kod, "guncellendi_at": at,
                               **{k: x[k] for k in (*DESC, *WATCHED)}})
        else:
            geri = prev is not None and p[_SON] is not None and p[_SON] < prev
            watched = any(_w(p, k) != x[k] for k in WATCHED)
            if watched:
                degisen += 1
                o, s = _w(p, "stok"), x["stok"]
                ok = not geri and not uzun and o is not None and s is not None
                obs.append({"tenant_id": tenant, "kaynak": kaynak, "barkod": b, "tarih": tarih, "stok": s,
                            "onceki_stok": None if geri else o, "cikis": max(0, o - s) if ok else 0,
                            "giris": max(0, s - o) if ok else 0, "ilk": False, **rest})
            donen += 1 if geri else 0
            if watched or geri or p[_SIG] != _sig(x) or p[_KOD] != kod:
                upd.append({"b_": b, **{"v_" + k: x[k] for k in (*DESC, *WATCHED)}, "v_stok_kodu": kod,
                            "v_son_gorulme": tarih, "v_guncellendi_at": at})
        st[b] = (_sig(x), *(x[k] for k in WATCHED), tarih, kod)
    missing = [b for b, p in st.items() if prev is not None and p[_SON] == prev and b not in items]
    T = TITLES.c
    with engine.begin() as c:
        for i in range(0, len(obs), 5000):
            c.execute(OBS.insert(), obs[i:i + 5000])
        for i in range(0, len(new_titles), 5000):
            c.execute(TITLES.insert(), new_titles[i:i + 5000])
        stmt = _update_stmt(tenant, kaynak)
        for i in range(0, len(upd), 5000):
            c.execute(stmt, upd[i:i + 5000])
        if prev is not None:
            # Bu görüntüde de bulunan (önceki görüntüde görülmüş) başlıkların son görülmesi tek sorguda kayar;
            # düşenler geri alınır.
            c.execute(TITLES.update().where(T.tenant_id == tenant, T.kaynak == kaynak, T.son_gorulme == prev)
                      .values(son_gorulme=tarih))
            for i in range(0, len(missing), 1000):
                c.execute(TITLES.update().where(T.tenant_id == tenant, T.kaynak == kaynak,
                                                T.barkod.in_(missing[i:i + 1000])).values(son_gorulme=prev))
        c.execute(SNAPS.insert().values(tenant_id=tenant, kaynak=kaynak, tarih=tarih, kaynak_zamani=kaynak_zamani,
                                        yontem=yontem, satir=len(items), degisen=degisen, yeni=yeni,
                                        kaybolan=len(missing), bildirilen=bildirilen, okundu_at=at))
    return {"kaynak": kaynak, "tarih": tarih.isoformat(), "satir": len(items), "degisen": degisen, "yeni": yeni,
            "kaybolan": len(missing), "geriGelen": donen, "guncellenen": len(upd),
            "aralikGun": (tarih - prev).days if prev else None, "cikisHesaplandi": not uzun, "bildirilen": bildirilen}


def mark_timas(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Marka, başlıklarının `timasOran`'ı Logo'da (TİMAŞ firmaları) bulunuyorsa TİMAŞ; aynı marka iki kaynakta ayrı
    yazılsa da barkod üzerinden aynı kitaplar işaretlenir (D&R başlığı Başarı'daki TİMAŞ barkoduyla da TİMAŞ olur)."""
    stn = settings()
    T = TITLES.c
    with engine.connect() as c:
        rows = c.execute(sa.select(T.kaynak, T.yayinevi, T.barkod, T.stok_kodu).where(T.tenant_id == tenant)).all()
    per: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        k = (r.kaynak, r.yayinevi or "")
        per[k][0] += 1
        per[k][1] += 1 if r.stok_kodu else 0
    brands = {k for k, (n, m) in per.items() if n >= stn["timasMinBaslik"] and m / n >= stn["timasOran"]}
    codes = {r.barkod for r in rows if (r.kaynak, r.yayinevi or "") in brands}
    with engine.begin() as c:
        c.execute(TITLES.update().where(T.tenant_id == tenant).values(timas=False))
        flagged = 0
        ids = sorted(codes)
        for i in range(0, len(ids), 1000):
            flagged += c.execute(TITLES.update().where(T.tenant_id == tenant, T.barkod.in_(ids[i:i + 1000]))
                                 .values(timas=True)).rowcount or 0
    out = {"markalar": sorted(f"{KAYNAK[k][:6]}: {m}" for k, m in brands), "baslik": flagged}
    meta_set(engine, tenant, "timas", {**out, "oran": stn["timasOran"], "at": now().isoformat()})
    return out


def logo_pairs(run: Runner, firms: dict[int, str]) -> set[tuple[str, str]]:
    """Güncel yılın TİMAŞ firmasındaki (barkod, stok kodu) çiftleri. Firma `firm_scope`'tan geçmiş `firms_by_year`'dan."""
    if not firms:
        return set()
    firm = firms[max(firms)]
    out: set[tuple[str, str]] = set()
    for r in run(sql_logo_barkod(firm)):
        b, k = barkod(r.get("barkod")), str(r.get("stok_kodu") or "").strip()
        if b and k:
            out.add((b, k))
    return out


def first_codes(pairs: set[tuple[str, str]]) -> dict[str, str]:
    """Barkod başına tek stok kodu (başlık satırı ve TİMAŞ markası için): sıralamada ilki, kararlı."""
    out: dict[str, str] = {}
    for b, k in sorted(pairs):
        out.setdefault(b, k)
    return out


def logo_barcodes(run: Runner, firms: dict[int, str]) -> dict[str, str]:
    return first_codes(logo_pairs(run, firms))


def store_pairs(engine: sa.engine.Engine, tenant: str, pairs: set[tuple[str, str]]) -> int:
    with engine.begin() as c:
        c.execute(BARKOD.delete().where(BARKOD.c.tenant_id == tenant))
        rows = [{"tenant_id": tenant, "barkod": b, "stok_kodu": k} for b, k in sorted(pairs)]
        for i in range(0, len(rows), 5000):
            c.execute(BARKOD.insert(), rows[i:i + 5000])
    return len(pairs)


def relink(engine: sa.engine.Engine, tenant: str, logo: dict[str, str]) -> int:
    """Logo barkod eşleşmesi değişmişse (yeni kart, silinen barkod) güncel hâldeki stok kodunu yeniler."""
    T = TITLES.c
    with engine.connect() as c:
        rows = c.execute(sa.select(T.kaynak, T.barkod, T.stok_kodu).where(T.tenant_id == tenant)).all()
    diff = [{"k_": r.kaynak, "b_": r.barkod, "v_": logo.get(r.barkod)} for r in rows if logo.get(r.barkod) != r.stok_kodu]
    if diff:
        stmt = TITLES.update().where(T.tenant_id == tenant, T.kaynak == sa.bindparam("k_"),
                                     T.barkod == sa.bindparam("b_")).values(stok_kodu=sa.bindparam("v_"))
        with engine.begin() as c:
            for i in range(0, len(diff), 5000):
                c.execute(stmt, diff[i:i + 5000])
    return len(diff)


def stretch(engine: sa.engine.Engine, tenant: str, kaynak: str = "basari", days: int = 365) -> Optional[tuple[date, date]]:
    """En az iki görüntüsü olan en yeni kesintisiz dizi (aralıklar `aralikGun`'ü aşmaz), en çok `days` gün: [ilk, son].
    Zamanlayıcı uzun süre durup yeniden başladıysa yeni dizi iki görüntüye ulaşana kadar önceki dizi kullanılır."""
    ds = sorted(processed(engine, tenant, kaynak))
    gap = settings()["aralikGun"]
    runs: list[list[date]] = []
    for d in ds:
        if runs and (d - runs[-1][-1]).days <= gap:
            runs[-1].append(d)
        else:
            runs.append([d])
    for run in reversed(runs):
        if len(run) < 2:
            continue
        end = run[-1]
        start = next(d for d in run if (end - d).days <= days)
        if start < end:
            return start, end
    return None


# ================================================================================ turlar


def sync_current(engine: sa.engine.Engine, tenant: str, run: Runner, kaynak: str, *, logo: dict[str, str],
                 step: Callable[[str], None] = lambda t: None) -> dict[str, Any]:
    damga_sql, sql = (SQL_BASARI_DAMGA, SQL_BASARI) if kaynak == "basari" else (SQL_DR_DAMGA, SQL_DR)
    d = run(damga_sql)
    stamp = str((d[0] if d else {}).get("t") or "")
    tarih = _day(stamp)
    if not tarih:
        raise DagitimError(f"{KAYNAK[kaynak]}: kaynak tarihi okunamadı.", 503)
    step(f"{KAYNAK[kaynak]} okunuyor ({tarih})")
    if tarih in processed(engine, tenant, kaynak):
        return {"kaynak": kaynak, "tarih": tarih.isoformat(), "skipped": "kaynak bu tarihten beri yenilenmedi",
                "kaynakZamani": stamp}
    items = parse(run(sql), kaynak)
    return apply(engine, tenant, kaynak, tarih, items, yontem="gece", kaynak_zamani=stamp, logo=logo,
                 bildirilen=_int((d[0] if d else {}).get("bildirilen")))


# ================================================================================ endeks ve kalibrasyon


def outflow(engine: sa.engine.Engine, tenant: str, *, kaynak: str = "basari", bas: Optional[date] = None,
            son: Optional[date] = None, by: str = "barkod", timas: Optional[bool] = None,
            limit: Optional[int] = None) -> list[dict[str, Any]]:
    """Çıkış/giriş toplamı; `by` = barkod | yayinevi | ust_kategori | kategori | ay. Tarih aralığı [bas, son)."""
    O, T = OBS.c, TITLES.c
    cond = [O.tenant_id == tenant, O.kaynak == kaynak]
    if bas:
        cond.append(O.tarih >= bas)
    if son:
        cond.append(O.tarih < son)
    j = OBS.join(TITLES, sa.and_(T.tenant_id == O.tenant_id, T.kaynak == O.kaynak, T.barkod == O.barkod))
    if timas is not None:
        cond.append(T.timas == timas)
    if by == "ay":
        key = sa.func.substr(sa.cast(O.tarih, sa.String), 1, 7).label("anahtar")
    else:
        col = {"barkod": T.barkod, "yayinevi": T.yayinevi, "ust_kategori": T.ust_kategori, "kategori": T.kategori}.get(by)
        if col is None:
            raise DagitimError("Bilinmeyen kırılım.")
        key = col.label("anahtar")
    cik, gir = sa.func.sum(O.cikis).label("cikis"), sa.func.sum(O.giris).label("giris")
    q = sa.select(key, cik, gir).select_from(j).where(*cond).group_by(key)
    q = q.order_by(key) if by == "ay" else q.order_by(cik.desc())
    if limit:
        q = q.limit(limit)
    with engine.connect() as c:
        return [{"anahtar": r.anahtar, "cikis": int(r.cikis or 0), "giris": int(r.giris or 0)} for r in c.execute(q).all()]


def calibration(engine: sa.engine.Engine, tenant: str, run: Runner, firms: dict[int, str], *, bas: date,
                son: date) -> dict[str, Any]:
    """Aynı aralıkta TİMAŞ'ın Logo'daki dağıtımcı sevki ↔ arşiv/görüntü stok hareketi (kitap bazında korelasyon ve
    toplam oranı). Yıl başına firma; aralık iki yıla yayılırsa her yıl kendi firmasından okunur."""
    cari = settings()["basariCari"]
    logo: dict[str, float] = defaultdict(float)
    for y in range(bas.year, son.year + 1):
        f = firms.get(y)
        if not f:
            continue
        a, b = max(bas, date(y, 1, 1)), min(son, date(y + 1, 1, 1))
        if a >= b:
            continue
        for r in run(sql_logo_sevk(f, cari, a, b)):
            k = barkod(r.get("barkod"))
            if k:
                logo[k] += float(r.get("net") or 0)
    # Görüntü t'deki gözlem (t_önceki, t] arasındaki hareketi taşır: pencere (bas, son] ↔ Logo [bas, son).
    ours = {r["anahtar"]: r for r in outflow(engine, tenant, bas=bas + timedelta(days=1), son=son + timedelta(days=1),
                                             by="barkod", timas=True)}
    pairs = [(logo[k], float(v["cikis"]), float(v["giris"])) for k, v in ours.items() if k in logo]
    out = {"bas": bas.isoformat(), "son": son.isoformat(), "cari": cari, "eslesen": len(pairs),
           "logoNet": round(sum(p[0] for p in pairs)), "cikis": round(sum(p[1] for p in pairs)),
           "giris": round(sum(p[2] for p in pairs)), "korelasyonCikis": _corr([p[0] for p in pairs], [p[1] for p in pairs]),
           "korelasyonGiris": _corr([p[0] for p in pairs], [p[2] for p in pairs])}
    out["katsayi"] = round(out["logoNet"] / out["cikis"], 2) if out["cikis"] else None
    return out


def _corr(x: list[float], y: list[float]) -> Optional[float]:
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sx = sum((a - mx) ** 2 for a in x) ** 0.5
    sy = sum((b - my) ** 2 for b in y) ** 0.5
    if not sx or not sy:
        return None
    return round(sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy), 3)


# ================================================================================ durum


def status(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    ensure(engine)
    S, T = SNAPS.c, TITLES.c
    with engine.connect() as c:
        snaps = c.execute(sa.select(S.kaynak, S.tarih, S.yontem, S.satir, S.degisen, S.yeni, S.kaybolan, S.kaynak_zamani,
                                    S.okundu_at, S.bildirilen).where(S.tenant_id == tenant).order_by(S.kaynak, S.tarih)).all()
        counts = c.execute(sa.select(T.kaynak, sa.func.count(), sa.func.sum(sa.cast(T.timas, sa.Integer)),
                                     sa.func.count(T.stok_kodu)).where(T.tenant_id == tenant).group_by(T.kaynak)).all()
        nobs = c.execute(sa.select(sa.func.count()).select_from(OBS).where(OBS.c.tenant_id == tenant)).scalar() or 0
    per: dict[str, Any] = {}
    for k in KAYNAK:
        mine = [s for s in snaps if s.kaynak == k]
        cnt = next((x for x in counts if x[0] == k), None)
        per[k] = {"ad": KAYNAK[k], "goruntu": len(mine),
                  "ilk": mine[0].tarih.isoformat() if mine else None, "son": mine[-1].tarih.isoformat() if mine else None,
                  "sonOkuma": mine[-1].okundu_at.isoformat() if mine else None,
                  "sonKaynakZamani": mine[-1].kaynak_zamani if mine else None,
                  "baslik": int(cnt[1]) if cnt else 0, "timas": int(cnt[2] or 0) if cnt else 0,
                  "logodaEslesen": int(cnt[3] or 0) if cnt else 0,
                  "sonGoruntuler": [{"tarih": s.tarih.isoformat(), "yontem": s.yontem, "satir": s.satir,
                                     "degisen": s.degisen, "yeni": s.yeni, "kaybolan": s.kaybolan,
                                     "bildirilen": s.bildirilen,
                                     "eksik": max(0, s.bildirilen - s.satir) if s.bildirilen else None} for s in mine[-5:]]}
    return {"kaynaklar": per, "gozlem": int(nobs),
            "timas": meta_get(engine, tenant, "timas"), "kalibrasyon": meta_get(engine, tenant, "kalibrasyon"),
            "sonTur": meta_get(engine, tenant, "last_run")}


def run_all(engine: sa.engine.Engine, tenant: str, run: Runner, firms: dict[int, str], *,
            step: Callable[[str], None] = lambda t: None) -> dict[str, Any]:
    """Tam tur: Logo barkodları → güncel Başarı ve D&R görüntüleri → stok kodu → TİMAŞ markası → kalibrasyon."""
    ensure(engine)
    stn = settings()
    out: dict[str, Any] = {"at": now().isoformat()}
    step("Logo barkodları okunuyor")
    pairs = logo_pairs(run, firms)
    logo = first_codes(pairs)
    out["logoBarkod"] = store_pairs(engine, tenant, pairs)
    for k in stn["kaynaklar"]:
        try:
            out[k] = sync_current(engine, tenant, run, k, logo=logo, step=step)
        except Exception as e:  # noqa: BLE001 — bir kaynak düşerse diğeri işlenir, hata turda görünür
            log.warning("pazar dagitim %s okunamadı: %s", k, e)
            out[k] = {"error": str(e)[:300]}
    step("Logo eşleşmesi ve TİMAŞ markaları")
    out["relink"] = relink(engine, tenant, logo)
    out["timas"] = mark_timas(engine, tenant)
    win = stretch(engine, tenant)
    if win:
        step("Kalibrasyon (Logo sevki ↔ stok hareketi)")
        try:
            kal = calibration(engine, tenant, run, firms, bas=win[0], son=win[1])
            meta_set(engine, tenant, "kalibrasyon", {**kal, "at": now().isoformat()})
            out["kalibrasyon"] = kal
        except Exception as e:  # noqa: BLE001
            out["kalibrasyon"] = {"error": str(e)[:300]}
    meta_set(engine, tenant, "last_run", out)
    return out


def freshness(engine: sa.engine.Engine, tenant: str, today: Optional[date] = None) -> dict[str, Any]:
    """Kaynak başına son görüntünün kaynak damgası ve yaşı (gün). Ekran her yerde «… kataloğu GG.AA.YYYY tarihli» yazar;
    yaş `bayatGun`'ü aşarsa «N gündür yenilenmedi» uyarısı. Damga kaynağın kendi `tarih` kolonudur, okuma saatimiz değil."""
    S = SNAPS.c
    with engine.connect() as c:
        rows = c.execute(sa.select(S.kaynak, sa.func.max(S.tarih)).where(S.tenant_id == tenant).group_by(S.kaynak)).all()
    last = {k: d for k, d in rows}
    t = today or datetime.now(timezone.utc).date()
    lim = settings()["bayatGun"]
    out: dict[str, Any] = {}
    for k in KAYNAK:
        d = last.get(k)
        yas = (t - d).days if d else None
        out[k] = {"ad": KAYNAK[k], "tarih": d.isoformat() if d else None, "yasGun": yas,
                  "bayat": yas is not None and yas > lim}
    out["bayatGun"] = lim
    return out


# ================================================================================ stok ekranlarına bağlantı

#: Stok satırındaki işaret: TİMAŞ'ta stok varken dağıtımcının kitapçıya gösterdiği durum.
ISARET = {"baskisi_yok": "Başarı'da baskısı yok görünüyor", "tukendi": "Başarı deposunda tükenmiş"}
KAPALI_DURUM = ("Baskısı Yok", "Temin Edilemiyor")


def _durum_since(engine: sa.engine.Engine, tenant: str, current: dict[str, Optional[str]]) -> dict[str, date]:
    """Barkodun bugünkü durumu hangi görüntüden beri aynı. Gözlem yalnız değişimde yazıldığı için satırlar yeniden
    eskiye yürünür; durumu farklı ilk satırda durulur."""
    O = OBS.c
    out: dict[str, date] = {}
    stop: set[str] = set()
    codes = sorted(current)
    with engine.connect() as c:
        for i in range(0, len(codes), 1000):
            rows = c.execute(sa.select(O.barkod, O.tarih, O.durum).where(
                O.tenant_id == tenant, O.kaynak == "basari", O.barkod.in_(codes[i:i + 1000]))
                .order_by(O.barkod, O.tarih.desc())).all()
            for r in rows:
                if r.barkod in stop:
                    continue
                if r.durum == current[r.barkod]:
                    out[r.barkod] = r.tarih
                else:
                    stop.add(r.barkod)
    return out


def attach_stock(engine: sa.engine.Engine, tenant: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Stok modelinin kitap satırlarına (`stokKodu`, `bakiye`) dağıtımcı ve perakende bilgisini ekler: Başarı durumu,
    deposu, fiyatı, durumun başladığı görüntü, çıkış endeksi (son kesintisiz dizi); D&R B2B stoğu ve fiyatları; işaret.
    Tablolar yoksa ya da boşsa satırlar `dagitim: None` alır, ekran «bu kaynak henüz okunmadı» der."""
    ensure(engine)
    T, K = TITLES.c, BARKOD.c
    j = TITLES.join(BARKOD, sa.and_(K.tenant_id == T.tenant_id, K.barkod == T.barkod))
    with engine.connect() as c:
        rows = c.execute(sa.select(T.kaynak, T.barkod, K.stok_kodu, T.stok, T.site_stok, T.fiyat, T.iskonto, T.dr_fiyat,
                                   T.durum, T.son_gorulme, T.timas).select_from(j).where(T.tenant_id == tenant)).all()
    win = stretch(engine, tenant)
    cik: dict[str, int] = {}
    if win:
        cik = {r["anahtar"]: r["cikis"] for r in outflow(engine, tenant, bas=win[0] + timedelta(days=1),
                                                          son=win[1] + timedelta(days=1), by="barkod", timas=True)}
    last = {k: max(processed(engine, tenant, k), default=None) for k in KAYNAK}
    by_code: dict[str, dict[str, Any]] = defaultdict(dict)
    for r in rows:
        # Aynı stok kodunun birden çok barkodu olabilir: son görüntüde bulunan, sonra stoğu büyük olan seçilir.
        cur = by_code[r.stok_kodu].get(r.kaynak)
        fresh = r.son_gorulme == last.get(r.kaynak)
        if cur is None or (fresh and not cur["_fresh"]) or (fresh == cur["_fresh"] and (r.stok or 0) > (cur["stok"] or 0)):
            by_code[r.stok_kodu][r.kaynak] = {"_fresh": fresh, "barkod": r.barkod, "stok": r.stok, "siteStok": r.site_stok,
                                              "fiyat": r.fiyat, "timas": bool(r.timas),
                                              "iskonto": r.iskonto, "drFiyat": r.dr_fiyat, "durum": r.durum,
                                              "son": r.son_gorulme.isoformat() if r.son_gorulme else None,
                                              "katalogda": fresh}
    closed = {v["basari"]["barkod"]: v["basari"]["durum"] for v in by_code.values()
              if v.get("basari") and v["basari"]["katalogda"]}
    since = _durum_since(engine, tenant, closed) if closed else {}
    counts = Counter()
    for it in items:
        d = by_code.get(it.get("stokKodu"))
        if not d:
            it["dagitim"] = None
            continue
        b, r = d.get("basari"), d.get("dr")
        out: dict[str, Any] = {"basari": None, "dr": None, "isaret": None}
        if b:
            out["basari"] = {"barkod": b["barkod"], "katalogda": b["katalogda"], "durum": b["durum"], "stok": b["stok"],
                             "fiyat": b["fiyat"], "iskonto": b["iskonto"], "son": b["son"],
                             "durumTarihi": since[b["barkod"]].isoformat() if b["barkod"] in since else None,
                             "cikis": cik.get(b["barkod"]) if win else None}
        if r:
            out["dr"] = {"barkod": r["barkod"], "katalogda": r["katalogda"], "stok": r["stok"], "siteStok": r["siteStok"],
                         "durum": r["durum"], "fiyat": r["fiyat"], "drFiyat": r["drFiyat"], "son": r["son"]}
        bakiye = float(it.get("bakiye") or 0)
        # İşaret yalnız TİMAŞ markalarında: Logo'da kartı olan başka yayınevi kitabı (perakende) satış kaybı değildir.
        if b and b["katalogda"] and b["timas"] and bakiye > 0:
            if b["durum"] in KAPALI_DURUM:
                out["isaret"] = "baskisi_yok"
            elif (b["stok"] or 0) <= 0 and b["durum"] == "Satışta":
                out["isaret"] = "tukendi"
        if out["isaret"]:
            counts[out["isaret"]] += 1
            out["isaretEtiket"] = ISARET[out["isaret"]]
        it["dagitim"] = out
    return {"pencere": {"bas": win[0].isoformat(), "son": win[1].isoformat()} if win else None,
            "sonGoruntu": {k: v.isoformat() if v else None for k, v in last.items()}, "isaretler": dict(counts),
            "tazelik": freshness(engine, tenant),
            "etiketler": ISARET, "not": NOTLAR["endeks"]}


# ================================================================================ Pazar özeti (dağıtımcı nabzı)

TIMAS_TOP = 15


def summary(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Pazar › Özet paneli: son kesintisiz görüntü dizisinde üst kategori başına çıkış endeksi ve TİMAŞ payı, yayınevi
    sıralaması (ilk 15 + dışında kalan TİMAŞ markaları sıralarıyla), aylık seri, kalibrasyon. Yalnız Başarı (D&R tek
    görüntü; hareketi görüntü biriktikçe gelir)."""
    ensure(engine)
    win = stretch(engine, tenant)
    last = {k: max(processed(engine, tenant, k), default=None) for k in KAYNAK}
    base = {"sonGoruntu": {k: v.isoformat() if v else None for k, v in last.items()}, "not": NOTLAR["endeks"],
            "tazelik": freshness(engine, tenant),
            "timasNot": NOTLAR["timas"],
            "kalibrasyon": meta_get(engine, tenant, "kalibrasyon")}
    if not win:
        return {**base, "pencere": None, "kategoriler": [], "yayinevleri": [], "aylar": []}
    bas, son = win[0] + timedelta(days=1), win[1] + timedelta(days=1)
    tum = {r["anahtar"]: r["cikis"] for r in outflow(engine, tenant, bas=bas, son=son, by="ust_kategori")}
    tim = {r["anahtar"]: r["cikis"] for r in outflow(engine, tenant, bas=bas, son=son, by="ust_kategori", timas=True)}
    toplam = sum(tum.values())
    kats = [{"kategori": k or "Kategorisiz", "cikis": v, "timasCikis": tim.get(k, 0),
             "timasPay": round(100.0 * tim.get(k, 0) / v, 1) if v else None,
             "kategoriPay": round(100.0 * v / toplam, 1) if toplam else None}
            for k, v in sorted(tum.items(), key=lambda x: -x[1]) if v][:12]
    pubs = outflow(engine, tenant, bas=bas, son=son, by="yayinevi")
    T = TITLES.c
    with engine.connect() as c:
        tmarka = {r[0] for r in c.execute(sa.select(T.yayinevi).where(T.tenant_id == tenant, T.kaynak == "basari",
                                                                       T.timas.is_(True)).distinct()).all()}
    yay = []
    for i, r in enumerate(pubs, 1):
        if r["cikis"] <= 0:
            break
        if i <= TIMAS_TOP or r["anahtar"] in tmarka:
            yay.append({"sira": i, "yayinevi": r["anahtar"], "cikis": r["cikis"], "timas": r["anahtar"] in tmarka,
                        "pay": round(100.0 * r["cikis"] / toplam, 1) if toplam else None})
    ay_t = {r["anahtar"]: r["cikis"] for r in outflow(engine, tenant, bas=bas, son=son, by="ay", timas=True)}
    aylar = [{"ay": r["anahtar"], "cikis": r["cikis"], "timasCikis": ay_t.get(r["anahtar"], 0)}
             for r in outflow(engine, tenant, bas=bas, son=son, by="ay")]
    return {**base, "pencere": {"bas": win[0].isoformat(), "son": win[1].isoformat()}, "toplam": toplam,
            "timasMarkalar": sorted(m for m in tmarka if m),
            "timasToplam": sum(tim.values()), "kategoriler": kats, "yayinevleri": yay, "aylar": aylar}


def summary_stmt(tenant: str, bas: date, son: date):
    """Özetin okuduğu portal sorgusu (sorgu bilgisi için): pencere içindeki gözlemler ve başlık bilgisi."""
    O, T = OBS.c, TITLES.c
    j = OBS.join(TITLES, sa.and_(T.tenant_id == O.tenant_id, T.kaynak == O.kaynak, T.barkod == O.barkod))
    return (sa.select(T.ust_kategori, T.yayinevi, T.timas, sa.func.substr(sa.cast(O.tarih, sa.String), 1, 7).label("ay"),
                      sa.func.sum(O.cikis).label("cikis")).select_from(j)
            .where(O.tenant_id == tenant, O.kaynak == "basari", O.tarih >= bas, O.tarih < son)
            .group_by(T.ust_kategori, T.yayinevi, T.timas, sa.func.substr(sa.cast(O.tarih, sa.String), 1, 7)))


# ================================================================================ kanal karnesi, kampanya, e-ticaret

F_KANAL_STOK = ("Kanalda bekleyen stok = son görüntüde TİMAŞ grubu başlıkların Başarı deposundaki stok toplamı; D&R'de "
                "Prefix B2B stoğu (kitapçılara toptan) ve D&R + İdefix sitelerinin stoğu ayrı toplanır (sitede 999 ve üstü "
                "yer tutucu değer sayım değildir, toplama girmez). Kanaldan çıkış = seçilen dönemdeki ardışık görüntüler "
                "arasında Başarı deposundaki TİMAŞ stok düşüşünün toplamı; en az iki görüntü gerekir. Kitapçılara çıkıştır, "
                "okura satış değildir.")
F_DR_FIYAT = ("D&R satış fiyatı ve D&R liste fiyatı D&R kataloğunun son görüntüsünden, barkod eşleşmesiyle (stok kodunun "
              "Logo barkodu ya da kitabın EAN'ı). D&R indirimi = 1 − D&R satış fiyatı ÷ D&R liste fiyatı.")


def last_snapshots(engine: sa.engine.Engine, tenant: str) -> dict[str, Optional[date]]:
    return {k: max(processed(engine, tenant, k), default=None) for k in KAYNAK}


def kanal_stok(engine: sa.engine.Engine, tenant: str, *, bas: Optional[date] = None,
               son: Optional[date] = None) -> dict[str, Any]:
    """Kanal karnesi: TİMAŞ grubu başlıkların dağıtımcıda (Başarı deposu) ve perakendede (D&R Prefix B2B, D&R + İdefix
    siteleri) bekleyen stoğu, son görüntü. Başarı'dan çıkış [bas, son] gün aralığına düşen görüntülerden; kesintisiz dizi
    (en az iki görüntü) yoksa `cikis` None ve `cikisNot` nedenini söyler. Zaman serisi kaynakta yok."""
    ensure(engine)
    last = last_snapshots(engine, tenant)
    T = TITLES.c
    out: dict[str, Any] = {"sonGoruntu": {k: v.isoformat() if v else None for k, v in last.items()},
                           "not": NOTLAR["endeks"], "timasNot": NOTLAR["timas"], "drNot": NOTLAR["dr"]}
    with engine.connect() as c:
        for k in KAYNAK:
            d = last[k]
            if d is None:
                out[k] = None
                continue
            r = c.execute(sa.select(
                sa.func.count(), sa.func.sum(T.stok), sa.func.sum(sa.case((T.stok > 0, 1), else_=0)),
                sa.func.sum(T.site_stok), sa.func.count(T.site_stok), sa.func.sum(sa.case((T.site_stok > 0, 1), else_=0)))
                .where(T.tenant_id == tenant, T.kaynak == k, T.timas.is_(True), T.son_gorulme == d)).one()
            e = {"tarih": d.isoformat(), "baslik": int(r[0] or 0), "stok": int(r[1] or 0), "stokluBaslik": int(r[2] or 0)}
            if k == "dr":
                e.update(siteStok=int(r[3] or 0), siteStokBilinen=int(r[4] or 0), siteStokluBaslik=int(r[5] or 0))
            out[k] = e
    out["cikis"], out["cikisNot"] = None, None
    if out["basari"] is None:
        out["cikisNot"] = "Başarı kataloğu henüz okunmadı."
        return out
    win = stretch(engine, tenant)
    if not win:
        out["cikisNot"] = (f"Kanaldan çıkış en az iki günlük görüntü birikince hesaplanır; şu an yalnız "
                           f"{last['basari'].strftime('%d.%m.%Y')} görüntüsü var. Kaynak geçmiş tutmaz.")
        return out
    # Görüntü t'deki gözlem (önceki görüntü, t] arasındaki hareketi taşır; ilk görüntünün gözlemi hareket değildir.
    a, b = win[0] + timedelta(days=1), win[1] + timedelta(days=1)
    if bas:
        a = max(a, bas)
    if son:
        b = min(b, son + timedelta(days=1))
    if a >= b:
        out["cikisNot"] = (f"Seçilen dönemde ardışık görüntü yok (görüntüler {win[0].strftime('%d.%m.%Y')}–"
                           f"{win[1].strftime('%d.%m.%Y')}).")
        return out
    aylar = outflow(engine, tenant, bas=a, son=b, by="ay", timas=True)
    out["cikis"] = {"bas": a.isoformat(), "son": (b - timedelta(days=1)).isoformat(),
                    "cikis": sum(x["cikis"] for x in aylar), "giris": sum(x["giris"] for x in aylar), "aylar": aylar}
    return out


def _dr_info(r: Any, last: Optional[date]) -> dict[str, Any]:
    fiyat, drf = r.fiyat, r.dr_fiyat
    ind = round(1 - float(drf) / float(fiyat), 4) if fiyat and drf and fiyat > 0 and drf > 0 else None
    return {"barkod": r.barkod, "fiyat": fiyat, "drFiyat": drf, "indirim": ind, "durum": r.durum,
            "siteSatista": str(r.durum or "").startswith("Site: Satışa açık"), "stok": r.stok, "siteStok": r.site_stok,
            "timas": bool(r.timas), "katalogda": last is not None and r.son_gorulme == last,
            "son": r.son_gorulme.isoformat() if r.son_gorulme else None}


def _dr_rank(x: dict[str, Any]) -> tuple:
    """Aynı anahtara birden çok D&R satırı düşerse: son görüntüde olan, sonra satış fiyatı dolu, sonra stoğu büyük."""
    return (x["katalogda"], x["drFiyat"] is not None, x["stok"] or 0)


def dr_fiyatlari(engine: sa.engine.Engine, tenant: str, *, codes: Iterable[str] = (),
                 eans: Iterable[str] = ()) -> dict[str, Any]:
    """Stok kodu (Logo barkod tablosu üzerinden) ve EAN → D&R fiyat bilgisi (son görüntü): liste, satış fiyatı, indirim,
    site durumu, TİMAŞ grubu mu. D&R kataloğu hiç okunmadıysa sözlükler boş, `tarih` None."""
    ensure(engine)
    last = last_snapshots(engine, tenant)["dr"]
    by_code: dict[str, dict[str, Any]] = {}
    by_ean: dict[str, dict[str, Any]] = {}
    if last is None:
        return {"kod": by_code, "ean": by_ean, "tarih": None}
    T, K = TITLES.c, BARKOD.c
    cols = (T.barkod, T.fiyat, T.dr_fiyat, T.durum, T.stok, T.site_stok, T.timas, T.son_gorulme)
    code_list = sorted({str(c) for c in codes if c})
    ean_list = sorted({b for b in (barkod(e) for e in eans) if b})
    j = TITLES.join(BARKOD, sa.and_(K.tenant_id == T.tenant_id, K.barkod == T.barkod))
    with engine.connect() as c:
        for i in range(0, len(code_list), 900):
            for r in c.execute(sa.select(K.stok_kodu, *cols).select_from(j).where(
                    T.tenant_id == tenant, T.kaynak == "dr", K.stok_kodu.in_(code_list[i:i + 900]))).all():
                x = _dr_info(r, last)
                cur = by_code.get(r.stok_kodu)
                if cur is None or _dr_rank(x) > _dr_rank(cur):
                    by_code[r.stok_kodu] = x
        for i in range(0, len(ean_list), 900):
            for r in c.execute(sa.select(*cols).where(T.tenant_id == tenant, T.kaynak == "dr",
                                                      T.barkod.in_(ean_list[i:i + 900]))).all():
                by_ean[r.barkod] = _dr_info(r, last)
    return {"kod": by_code, "ean": by_ean, "tarih": last.isoformat()}


def dr_timas(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """E-ticaret farkları için: TİMAŞ grubu D&R başlıkları, barkod → fiyat bilgisi (son görüntüde olanlar). D&R kataloğu
    hiç okunmadıysa `tarih` None (fark türü o turda hesaplanmaz)."""
    ensure(engine)
    last = last_snapshots(engine, tenant)["dr"]
    if last is None:
        return {"ean": {}, "tarih": None}
    T = TITLES.c
    with engine.connect() as c:
        rows = c.execute(sa.select(T.barkod, T.fiyat, T.dr_fiyat, T.durum, T.stok, T.site_stok, T.timas, T.son_gorulme)
                         .where(T.tenant_id == tenant, T.kaynak == "dr", T.timas.is_(True), T.son_gorulme == last)).all()
    return {"ean": {r.barkod: _dr_info(r, last) for r in rows}, "tarih": last.isoformat()}


#: «D&R zaten indirimde» uyarısının alt sınırı (yuvarlama kuruşu indirim sayılmasın diye %1).
DR_INDIRIM_ESIK = 0.01


def dr_uyari(info: Optional[dict[str, Any]]) -> Optional[str]:
    """«D&R zaten %X indirimde»: kitap son D&R görüntüsünde, sitede satışa açık ve indirim en az %1 ise."""
    if not info or not info.get("katalogda") or not info.get("siteSatista"):
        return None
    ind = info.get("indirim")
    if ind is None or ind < DR_INDIRIM_ESIK:
        return None
    return f"D&R zaten %{round(ind * 100):.0f} indirimde"
