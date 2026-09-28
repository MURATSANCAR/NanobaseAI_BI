"""M18 B2B satış föyü (FÖY): ayın yeni kitapları için tek sayfalık föy, CRM'den dolan alanlar, eksik alan ve fiyat /
barkod uyumsuzluğu denetimi, Zeki AI satış argümanı taslağı (yalnız CRM'de yoksa), satış onayı, aylık paket.

**Alanlar** CRM kitap kartından (yalnız okuma): ad, yazar, yayınevi, kitaplık, dizi, hedef kitle (+ yaş, sınıf), KDV
dahil fiyat, güncel barkod (`new_ean13`, yoksa güncel ISBN), sayfa, ebat, cilt, yayın günü, tanıtım metni
(`new_TantmFyMetni` → `new_tanitimfoymetni` → spot), «Bu Kitap Neden Önemli?» (`new_kitabinonecikanyanlari`, satış
argümanları), arka kapak (`new_ozet`), kapak (`new_resimurl`). Her alanın kaynağı yanında yazılır: `crm:<kolon>`, `logo`,
`zeki`, `elle`. Elle düzeltilen alan CRM yenilemesinde korunur; Zeki AI argümanı CRM'e argüman girilince CRM'inkine
bırakılır.

**Uyumsuzluk** (onaydan önce görünür; onay için gerekçeyle kabul edilir): CRM fiyatı ≠ Logo fiyatı (tolerans ayarı);
CRM'deki «Föy için taslak fiyat» ≠ KDV dahil fiyat; barkod ≠ güncel ISBN; barkodun EAN-13 denetim hanesi yanlış. Logo
fiyatı Baskı Öneri'nin fiyat tanımıyla okunur (`management/sql/baski_oneri/logo_fiyat.sql`: B2B/CRM siparişli satış
satırlarında ayın en yüksek birim fiyatı, son değişiklik) ya da ayarla Logo satış fiyat listesinden (`PRCLIST`, ihale
modülünün okuması) — hangisinin doğru karşılaştırma olduğu ölçülecek.

**Eski föy**: CRM alanlarının özeti (`crm_hash`) değişince onaylı/onaydaki föy «eski» işaretlenir; «CRM'den yenile»
yeni sürümü taslak olarak açar.

**Dış gönderim yok**: paket (birleşik PDF + zip) indirilir; e-postayla gönderim yalnız `ozellik:pazarlama.foy-gonder`
olan kişinin tıklamasıyla, onaylı föylerle ve iç dağıtım listesine gider. CRM'e yazılmaz: onaylı metinler «CRM'e
işlenecek» olarak listelenir.
"""
from __future__ import annotations

import hashlib
import logging
import re
import smtplib
import ssl
import threading
import time
import urllib.request
from datetime import date
from email.message import EmailMessage
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import guard as G
from semantic_bridge.marketing import plans as P
from semantic_bridge.marketing.sources import SourceError, _long, _s

log = logging.getLogger("semantic.marketing.foy")

FOY = sa.Table(
    "semantic_mkt_foy", C._md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("stok_kodu", sa.String(60), nullable=False, index=True),
    sa.Column("donem", sa.String(7), nullable=False),
    sa.Column("surum", sa.Integer, nullable=False, default=1),
    sa.Column("alanlar_json", sa.Text, nullable=False),
    sa.Column("eksikler_json", sa.Text),
    sa.Column("uyumsuzluk_json", sa.Text),
    sa.Column("durum", sa.String(10), nullable=False),                 # taslak | onayda | onayli
    sa.Column("eski", sa.Boolean, nullable=False, default=False),      # CRM alanları onaydan sonra değişti
    sa.Column("ay_disi", sa.Boolean, nullable=False, default=False),   # yayın günü başka aya kaydı
    sa.Column("gonderen", sa.String(120)),
    sa.Column("gonderme", sa.DateTime(timezone=True)),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onay_zamani", sa.DateTime(timezone=True)),
    sa.Column("onay_notu", sa.Text),                                   # uyumsuzluk kabulünün gerekçesi
    sa.Column("gerekce", sa.Text),                                     # geri gönderme gerekçesi
    sa.Column("pdf_yolu", sa.String(400)),                             # PDF her istekte üretilir; dosya tutulmaz (boş)
    sa.Column("crm_hash", sa.String(64)),
    sa.Column("guncelleyen", sa.String(120)),
    sa.Column("guncelleme", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("tenant_id", "stok_kodu", "donem", name="uq_semantic_mkt_foy"),
)
SENDS = sa.Table(
    "semantic_mkt_foy_sends", C._md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("donem", sa.String(7), nullable=False),
    sa.Column("alicilar", sa.Text, nullable=False),
    sa.Column("gonderen", sa.String(120), nullable=False),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
    sa.Column("dosya", sa.String(200)),
    sa.Column("adet", sa.Integer, nullable=False, default=0),
    sa.Column("sonuc", sa.String(12), nullable=False),                 # sent | no_smtp | failed | no_recipient
)

STATUSES = {"taslak": "Taslak", "onayda": "Onay bekliyor", "onayli": "Onaylı"}
#: (anahtar, ad). Sıra föy sayfasındaki sıradır.
FIELDS: list[tuple[str, str]] = [
    ("ad", "Kitap adı"), ("yazar", "Yazar"), ("yayinevi", "Yayınevi"), ("kitaplik", "Kitaplık"), ("dizi", "Dizi"),
    ("hedefKitle", "Hedef kitle"), ("fiyat", "Tavsiye edilen satış fiyatı (KDV dahil)"), ("barkod", "Barkod"),
    ("isbn", "ISBN"), ("sayfa", "Sayfa sayısı"), ("ebat", "Ebat"), ("cilt", "Cilt"), ("yayinTarihi", "Yayın tarihi"),
    ("tanitim", "Tanıtım metni"), ("argumanlar", "Neden satılır"), ("ozet", "Arka kapak metni"), ("kapak", "Kapak görseli"),
]
LABELS = dict(FIELDS)
DEFAULT_REQUIRED = "ad,yazar,hedefKitle,fiyat,barkod,tanitim,argumanlar"
#: Föy özetine giren CRM kolonları (değişince föy «eski» olur).
HASH_COLS = ("ad", "yazar", "yayinevi", "kitaplik", "dizi", "hedef_kitle", "yas_bas", "yas_bit", "siniflar", "ean13", "isbn13",
             "kdv_dahil_fiyat", "perakende_fiyat", "uzeri_fiyat", "foy_taslak_fiyat", "sayfa", "ebat", "cilt", "kapak",
             "new_TantmFyMetni", "new_tanitimfoymetni", "new_kitapspotu", "new_ozet", "new_kitabinonecikanyanlari")

_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    C.ensure(engine)
    with _lock:
        if id(engine) in _ready:
            return
        for t in (FOY, SENDS):
            t.create(engine, checkfirst=True)
        _ready.add(id(engine))


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    raw_tol = (conf("MARKETING_FOY_PRICE_TOLERANCE") or "").strip().replace(",", ".")
    try:
        tol = float(raw_tol) if raw_tol else 0.01
    except ValueError:
        tol = 0.01
    mode = (conf("MARKETING_FOY_LOGO_PRICE") or "satis").strip()
    return {
        "required": [x.strip() for x in ((conf("MARKETING_FOY_REQUIRED") or "").strip() or DEFAULT_REQUIRED).split(",")
                     if x.strip() in LABELS],
        "tolerance": max(0.0, tol),
        "logoPrice": mode if mode in ("satis", "liste", "yok") else "satis",
        "recipients": [x.strip() for x in (conf("MARKETING_FOY_RECIPIENTS") or "").replace(";", ",").split(",") if "@" in x],
        "coverBase": (conf("MARKETING_COVER_BASE_URL") or "").strip(),
    }


# ------------------------------------------------------------------ yardımcılar


def _num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        m = re.search(r"\d[\d.,]*", str(v))
        if not m:
            return None
        t = m.group(0)
        t = t.replace(".", "").replace(",", ".") if "," in t else (t.replace(".", "") if t.count(".") > 1 else t)
        try:
            n = float(t)
        except ValueError:
            return None
    return n if n > 0 else None


def digits(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def ean13_ok(code: str) -> bool:
    d = digits(code)
    if len(d) != 13:
        return False
    s = sum(int(x) * (3 if i % 2 else 1) for i, x in enumerate(d[:12]))
    return (10 - s % 10) % 10 == int(d[12])


def split_args(text: Optional[str]) -> list[str]:
    """«Bu kitap neden önemli?» metni → maddeler (satır ya da madde işaretiyle ayrılmış; tek paragrafsa cümleler)."""
    if not text:
        return []
    lines = [re.sub(r"^\s*(?:[-•*·▪–]|\d+[.)])\s*", "", x).strip() for x in str(text).splitlines()]
    lines = [x for x in lines if x]
    if len(lines) == 1:
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ«\"“])", lines[0]) if p.strip()]
        return parts
    return lines


def _f(deger: Any, kaynak: str) -> dict[str, Any]:
    return {"deger": deger, "kaynak": kaynak}


def crm_hash(raw: dict[str, Any]) -> str:
    return hashlib.sha256(C.dump({k: str(raw.get(k) if raw.get(k) is not None else "") for k in HASH_COLS}).encode()).hexdigest()


def from_crm(raw: dict[str, Any], pub: Optional[str], pub_src: Optional[str]) -> dict[str, dict[str, Any]]:
    """CRM satırı → föy alanları (değer + kaynak). Boş alan `deger=None, kaynak=None` olarak kalır."""
    out: dict[str, dict[str, Any]] = {k: _f(None, None) for k, _ in FIELDS}  # type: ignore[arg-type]
    for key, col in (("ad", "ad"), ("yazar", "yazar"), ("yayinevi", "yayinevi"), ("kitaplik", "kitaplik"), ("dizi", "dizi"),
                     ("ebat", "ebat"), ("cilt", "cilt"), ("kapak", "kapak")):
        v = _s(raw.get(col))
        if v:
            out[key] = _f(v, "crm:" + {"ad": "new_name", "yazar": "new_yazartext", "yayinevi": "new_yayineviid",
                                       "kitaplik": "new_kitaplikid", "dizi": "new_diziid", "ebat": "new_Ebat",
                                       "cilt": "new_ciltlemesekli", "kapak": "new_resimurl"}[key])
    hk = [x for x in (_s(raw.get("hedef_kitle")),) if x]
    yb, ye = raw.get("yas_bas"), raw.get("yas_bit")
    if yb or ye:
        hk.append(f"{yb or '?'}–{ye or '?'} yaş")
    if _s(raw.get("siniflar")):
        hk.append(f"{_s(raw.get('siniflar'))} sınıf")
    if hk:
        out["hedefKitle"] = _f(" · ".join(hk), "crm:new_hedefkitle")
    for col, src in (("kdv_dahil_fiyat", "crm:new_kdvdahilfiyat"), ("uzeri_fiyat", "crm:powerbikitap.Üzeri_Fiyat"),
                     ("perakende_fiyat", "crm:new_PerakendeBirimFiyat")):
        n = _num(raw.get(col))
        if n:
            out["fiyat"] = _f(round(n, 2), src)
            break
    ean, isbn = digits(raw.get("ean13")), digits(raw.get("isbn13"))
    if ean:
        out["barkod"] = _f(ean, "crm:new_ean13")
    elif isbn:
        out["barkod"] = _f(isbn, "crm:new_isbn13")
    if isbn:
        out["isbn"] = _f(_s(raw.get("isbn13")), "crm:new_isbn13")
    n = _num(raw.get("sayfa"))
    if n:
        out["sayfa"] = _f(int(n), "crm:new_sayfasayisi")
    if pub:
        out["yayinTarihi"] = _f(pub, {"crm-kitap": "crm:new_ilkyayintarihi", "crm-proje": "crm:new_projeBase",
                                      "uretim": "crm:new_UretimBase", "elle": "elle"}.get(pub_src or "", "crm:new_ilkyayintarihi"))
    for col in ("new_TantmFyMetni", "new_tanitimfoymetni", "new_kitapspotu"):
        v = _long(raw.get(col))
        if v:
            out["tanitim"] = _f(v, "crm:" + col)
            break
    args = split_args(_long(raw.get("new_kitabinonecikanyanlari")))
    if args:
        out["argumanlar"] = _f(args, "crm:new_kitabinonecikanyanlari")
    v = _long(raw.get("new_ozet"))
    if v:
        out["ozet"] = _f(v, "crm:new_ozet")
    return out


def merge(old: dict[str, dict[str, Any]], new: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """CRM tazelemesi: elle alan korunur; Zeki AI alanı CRM boşsa korunur, CRM dolunca CRM'inki gelir."""
    out = dict(new)
    for k, v in (old or {}).items():
        src = (v or {}).get("kaynak") or ""
        if src == "elle":
            out[k] = v
        elif src == "zeki" and not (new.get(k) or {}).get("deger"):
            out[k] = v
    return out


def _empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or (isinstance(v, str) and not v.strip())


def missing(fields: dict[str, dict[str, Any]], required: list[str]) -> list[str]:
    return [k for k in required if _empty((fields.get(k) or {}).get("deger"))]


def mismatches(fields: dict[str, dict[str, Any]], raw: dict[str, Any], logo: Optional[dict[str, Any]], tol: float,
               logo_note: Optional[str] = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    price = (fields.get("fiyat") or {}).get("deger")
    crm_price = _num(raw.get("kdv_dahil_fiyat"))
    if logo and logo.get("fiyat") and crm_price and abs(float(logo["fiyat"]) - crm_price) > tol:
        out.append({"tur": "fiyat-logo", "ad": "CRM fiyatı Logo fiyatından farklı", "crm": crm_price, "logo": logo["fiyat"],
                    "not": logo.get("kaynak")})
    draft = _num(raw.get("foy_taslak_fiyat"))
    if draft and crm_price and abs(draft - crm_price) > tol:
        out.append({"tur": "fiyat-taslak", "ad": "Föy için taslak fiyat KDV dahil fiyattan farklı", "crm": crm_price,
                    "taslak": draft, "not": "CRM kitap kartı: «Föy İçin Taslak Fiyat» ve «KDV Dahil Fiyat»"})
    uz = _num(raw.get("uzeri_fiyat"))
    if uz and crm_price and abs(uz - crm_price) > tol:
        out.append({"tur": "fiyat-uzeri", "ad": "Raporlama görünümündeki kapak fiyatı KDV dahil fiyattan farklı",
                    "crm": crm_price, "uzeri": uz})
    if price is not None and crm_price is None and (fields.get("fiyat") or {}).get("kaynak") == "elle":
        out.append({"tur": "fiyat-elle", "ad": "Fiyat elle girildi; CRM kitap kartında KDV dahil fiyat boş", "elle": price})
    ean, isbn = digits(raw.get("ean13")), digits(raw.get("isbn13"))
    if ean and isbn and len(isbn) == 13 and ean != isbn:
        out.append({"tur": "barkod-isbn", "ad": "Barkod güncel ISBN ile aynı değil", "barkod": ean, "isbn": isbn})
    bc = digits((fields.get("barkod") or {}).get("deger"))
    if bc and not ean13_ok(bc):
        out.append({"tur": "barkod-gecersiz", "ad": "Barkod geçerli bir EAN-13 değil (hane sayısı ya da denetim hanesi)", "barkod": bc})
    if logo_note:
        out.append({"tur": "logo-okunamadi", "ad": "Logo fiyatı okunamadı; fiyat karşılaştırması yapılmadı", "not": logo_note,
                    "bilgi": True})
    return out


def blocking(mm: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [x for x in mm if not x.get("bilgi")]


# ------------------------------------------------------------------ Logo fiyatı


class LogoPrices:
    """Stok kodu → Logo fiyatı. `satis`: Baskı Öneri fiyat tanımı (satış satırı), `liste`: Logo satış fiyat listesi,
    `yok`: okunmaz. Sonuç 10 dakika bellekte."""

    TTL = 600

    def __init__(self, runner: Callable[[], Callable[[str], list[dict[str, Any]]]]):
        self.runner = runner
        self._cache: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        #: Stok kodu → o kodun fiyatını getiren okumada çalışmış Logo SQL metinleri, satır, süre ve an (sorgu bilgisi).
        self.executed: dict[str, list[dict[str, Any]]] = {}

    def _run(self) -> tuple[Callable[[str], list[dict[str, Any]]], list[dict[str, Any]]]:
        """Çalışan her SQL'i (metin, satır, süre, an) kaydeden koşucu."""
        base = self.runner()
        runs: list[dict[str, Any]] = []

        def run(sql: str) -> list[dict[str, Any]]:
            t0 = time.monotonic()
            rows = base(sql)
            runs.append({"sql": sql, "rows": len(rows), "dbMs": int((time.monotonic() - t0) * 1000), "at": C.iso(C.now())})
            return rows
        return run, runs

    def runs_for(self, codes: Iterable[str]) -> list[dict[str, Any]]:
        """Bu kodların fiyatını getiren okumaların çalışmış SQL'leri (tekrarsız, okunma sırasıyla)."""
        seen: dict[str, dict[str, Any]] = {}
        with self._lock:
            for k in codes:
                for r in self.executed.get(k) or []:
                    seen.setdefault(r["sql"], r)
        return list(seen.values())

    def read(self, codes: Iterable[str], mode: str, fresh: bool = False) -> tuple[dict[str, dict[str, Any]], Optional[str]]:
        want = tuple(sorted({c for c in codes if c}))
        if mode == "yok":
            return {}, "Logo fiyat karşılaştırması kapalı (Yönetim → Pazarlama planları)."
        if not want:
            return {}, None
        key = (mode, want)
        with self._lock:
            hit = self._cache.get(key)
        if hit and not fresh and time.monotonic() - hit[0] < self.TTL:
            return hit[1]
        try:
            run, runs = self._run()      # bağlantı yoksa hata burada: eskisi gibi «fiyat okunamadı» notuna düşer
            val = (self._sales(want, run) if mode == "satis" else self._list(want, run)), None
        except (SourceError, RuntimeError) as e:
            return {}, str(e)[:300]
        with self._lock:
            self._cache[key] = (time.monotonic(), val)
            for k in want:
                self.executed[k] = runs
        return val

    def _sales(self, codes: tuple[str, ...], run: Callable[[str], list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
        from semantic_bridge import management as M
        from semantic_bridge.marketing.sources import _values

        text = M.sql_text("baski-oneri", "logo_fiyat")
        anchor = "    WHERE s.[Satır Türü] = N'Malzeme'"
        if anchor not in text:
            raise SourceError("Logo fiyat sorgusunun biçimi değişmiş; föy fiyat karşılaştırması yapılamadı.")
        views = run("SELECT name FROM sys.views WHERE name LIKE 'V[_]SatisRaporu[_]20[0-9][0-9]'")
        existing = {int(str(r["name"])[-4:]) for r in views}
        out: dict[str, dict[str, Any]] = {}
        for i in range(0, len(codes), 500):
            part = list(codes[i:i + 500])
            sql = text.replace(anchor, f"    JOIN (VALUES {_values(part)}) AS kod(k) ON kod.k = s.[Malzeme/Hizmet Kodu]\n{anchor}")
            sql, _missing = M.expand_sales(sql, date.today(), existing)
            for r in run(sql):
                k = _s(r.get("stok_kodu"))
                n = _num(r.get("birim_fiyat"))
                if k and n:
                    d = r.get("son_fiyat_degisikligi")
                    out[k] = {"fiyat": round(n, 2), "tarih": str(d)[:10] if d else None,
                              "kaynak": "Logo satış satırı: B2B/CRM siparişli satışta ayın en yüksek birim fiyatı (Baskı Öneri tanımı)"}
        return out

    def _list(self, codes: tuple[str, ...], run: Callable[[str], list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
        from semantic_bridge import tenders_sources as TS

        out = {}
        for k, v in TS.read_prices(run, codes).items():
            if v.get("fiyat"):
                out[k] = {"fiyat": round(float(v["fiyat"]), 2), "kaynak": f"Logo satış fiyat listesi ({v.get('liste')})"}
        return out


# ------------------------------------------------------------------ okuma / yazma


def _dict(r: Any, required: list[str]) -> dict[str, Any]:
    fields = C.loads(r.alanlar_json, {})
    mm = C.loads(r.uyumsuzluk_json, [])
    return {"id": r.id, "stokKodu": r.stok_kodu, "donem": r.donem, "surum": r.surum, "durum": r.durum,
            "durumAdi": STATUSES.get(r.durum, r.durum), "eski": bool(r.eski), "ayDisi": bool(r.ay_disi),
            "alanlar": [{"key": k, "ad": LABELS[k], **(fields.get(k) or {"deger": None, "kaynak": None})} for k, _ in FIELDS],
            "eksikler": C.loads(r.eksikler_json, []), "uyumsuzluk": mm, "engelleyen": len(blocking(mm)),
            "gonderen": r.gonderen, "gonderme": C.iso(r.gonderme), "onaylayan": r.onaylayan, "onayZamani": C.iso(r.onay_zamani),
            "onayNotu": r.onay_notu, "gerekce": r.gerekce, "guncelleyen": r.guncelleyen, "guncelleme": C.iso(r.guncelleme),
            "zorunlu": required}


def row_stmt(tenant: str, stok: str, donem: Optional[str] = None):
    """Tek föy okuması (aynı ifade sorgu bilgisinde gösterilir)."""
    q = sa.select(FOY).where(FOY.c.tenant_id == tenant, FOY.c.stok_kodu == str(stok)[:60])
    if donem:
        q = q.where(FOY.c.donem == donem)
    return q.order_by(FOY.c.ay_disi, FOY.c.donem.desc())


def get_row(c: Any, tenant: str, stok: str, donem: Optional[str] = None, *, lock: bool = False) -> Any:
    q = row_stmt(tenant, stok, donem)
    if lock and c.engine.dialect.name == "postgresql":
        q = q.with_for_update()
    return c.execute(q).first()


def get(engine: sa.engine.Engine, tenant: str, stok: str, required: list[str], donem: Optional[str] = None) -> dict[str, Any]:
    with engine.connect() as c:
        r = get_row(c, tenant, stok, donem)
    if not r:
        raise C.MarketingError("Bu kitabın föyü yok; föyler ay listesinden açılır.", 404)
    return _dict(r, required)


def upsert_from_crm(engine: sa.engine.Engine, tenant: str, stok: str, donem: str, raw: dict[str, Any], pub: Optional[str],
                    pub_src: Optional[str], logo: Optional[dict[str, Any]], logo_note: Optional[str], fst: dict[str, Any],
                    user: str = "sistem", *, force: bool = False) -> str:
    """Föy yoksa açar; taslaksa CRM'den tazeler; onayda/onaylıysa CRM değişince «eski» işaretler (`force`: yeni sürümü
    taslak olarak açar — «CRM'den yenile»). Dönen: yapılan iş (acildi | tazelendi | eski | ayni | yenilendi)."""
    h = crm_hash(raw)
    new = from_crm(raw, pub, pub_src)
    t = C.now()
    with engine.begin() as c:
        r = get_row(c, tenant, stok, donem, lock=True)
        if r is None:
            fields = new
            c.execute(FOY.insert().values(
                id=C._uid(), tenant_id=tenant, stok_kodu=stok, donem=donem, surum=1, alanlar_json=C.dump(fields),
                eksikler_json=C.dump(missing(fields, fst["required"])),
                uyumsuzluk_json=C.dump(mismatches(fields, raw, logo, fst["tolerance"], logo_note)), durum="taslak", eski=False,
                ay_disi=False, crm_hash=h, guncelleyen=user, guncelleme=t))
            return "acildi"
        if r.durum == "taslak" or force:
            fields = merge(C.loads(r.alanlar_json, {}), new)
            vals: dict[str, Any] = {"alanlar_json": C.dump(fields), "eksikler_json": C.dump(missing(fields, fst["required"])),
                                    "uyumsuzluk_json": C.dump(mismatches(fields, raw, logo, fst["tolerance"], logo_note)),
                                    "crm_hash": h, "eski": False, "ay_disi": False}
            if r.durum != "taslak":
                vals.update(durum="taslak", surum=r.surum + 1, onaylayan=None, onay_zamani=None, onay_notu=None, gonderen=None,
                            gonderme=None, guncelleyen=user, guncelleme=t)
            elif r.crm_hash != h:
                vals.update(guncelleme=t)
            c.execute(FOY.update().where(FOY.c.id == r.id).values(**vals))
            return "yenilendi" if r.durum != "taslak" else ("tazelendi" if r.crm_hash != h else "ayni")
        if r.crm_hash != h and not r.eski:
            c.execute(FOY.update().where(FOY.c.id == r.id).values(eski=True, ay_disi=False))
            return "eski"
        if r.ay_disi:
            c.execute(FOY.update().where(FOY.c.id == r.id).values(ay_disi=False))
        return "ayni"


def mark_out_of_month(engine: sa.engine.Engine, tenant: str, donem: str, codes: set[str]) -> int:
    """Dönemin föyü olup yayın günü artık o aya düşmeyen kitaplar: «ay dışı» (silinmez)."""
    with engine.begin() as c:
        rows = c.execute(sa.select(FOY.c.id, FOY.c.stok_kodu).where(FOY.c.tenant_id == tenant, FOY.c.donem == donem)).all()
        n = 0
        for r in rows:
            if r.stok_kodu not in codes:
                c.execute(FOY.update().where(FOY.c.id == r.id).values(ay_disi=True))
                n += 1
    return n


def month_stmt(tenant: str, donem: str, durum: str = ""):
    """Dönemin föyleri (aynı ifade sorgu bilgisinde gösterilir)."""
    cond = [FOY.c.tenant_id == tenant, FOY.c.donem == donem]
    if durum in STATUSES:
        cond.append(FOY.c.durum == durum)
    return sa.select(FOY).where(*cond).order_by(FOY.c.ay_disi, FOY.c.stok_kodu)


def list_month(engine: sa.engine.Engine, tenant: str, donem: str, required: list[str], durum: str = "") -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(month_stmt(tenant, donem, durum)).all()
    return [_dict(r, required) for r in rows]


def _clean_value(key: str, v: Any) -> Any:
    if key == "fiyat":
        n = C.number(v, "Fiyat", allow_none=True)
        return None if n is None else round(n, 2)
    if key == "sayfa":
        n = C.number(v, "Sayfa sayısı", allow_none=True)
        return None if n is None else int(n)
    if key == "argumanlar":
        if isinstance(v, list):
            return [C.one_line(x, 600) for x in v if C.one_line(x, 600)]
        return split_args(C.text(v, 6000))
    if key == "yayinTarihi":
        return C.day(v, "Yayın tarihi")
    if key == "barkod":
        d = digits(v)
        return d or None
    if key in ("tanitim", "ozet"):
        return C.text(v, 8000)
    return C.one_line(v, 400)


def update(engine: sa.engine.Engine, tenant: str, user: str, stok: str, donem: str, body: dict[str, Any], fst: dict[str, Any],
           raw: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Alan düzeltmesi: `alanlar` {anahtar: değer} (null = CRM'e dön). Onaylı föy düzenlenirse yeni sürüm taslak olur."""
    changes = body.get("alanlar")
    if not isinstance(changes, dict) or not changes:
        raise C.MarketingError("Değiştirilecek alan yok.")
    for k in changes:
        if k not in LABELS:
            raise C.MarketingError(f"Föy alanı tanınmıyor: {k}.")
    with engine.begin() as c:
        r = get_row(c, tenant, stok, donem, lock=True)
        if not r:
            raise C.MarketingError("Föy bulunamadı.", 404)
        fields = C.loads(r.alanlar_json, {})
        crm_fields = from_crm(raw, fields.get("yayinTarihi", {}).get("deger"), None) if raw else {}
        for k, v in changes.items():
            val = _clean_value(k, v)
            if _empty(val):
                fields[k] = crm_fields.get(k) or {"deger": None, "kaynak": None}
            else:
                fields[k] = {"deger": val, "kaynak": "elle", "kim": user}
        vals: dict[str, Any] = {"alanlar_json": C.dump(fields), "eksikler_json": C.dump(missing(fields, fst["required"])),
                                "guncelleyen": user, "guncelleme": C.now()}
        if raw is not None:
            prev_logo = next((x for x in C.loads(r.uyumsuzluk_json, []) if x.get("tur") == "fiyat-logo"), None)
            logo = {"fiyat": prev_logo["logo"], "kaynak": prev_logo.get("not")} if prev_logo else None
            vals["uyumsuzluk_json"] = C.dump(mismatches(fields, raw, logo, fst["tolerance"]))
        if r.durum != "taslak":
            vals.update(durum="taslak", surum=r.surum + (1 if r.durum == "onayli" else 0), onaylayan=None, onay_zamani=None,
                        onay_notu=None, gonderen=None, gonderme=None)
        c.execute(FOY.update().where(FOY.c.id == r.id).values(**vals))
        rid = r.id
    with engine.connect() as c:
        return _dict(c.execute(sa.select(FOY).where(FOY.c.id == rid)).one(), fst["required"])


def submit(engine: sa.engine.Engine, tenant: str, user: str, stok: str, donem: str, fst: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        r = get_row(c, tenant, stok, donem, lock=True)
        if not r:
            raise C.MarketingError("Föy bulunamadı.", 404)
        if r.durum != "taslak":
            raise C.MarketingError("Yalnız taslak föy onaya gönderilir.", 409)
        eks = C.loads(r.eksikler_json, [])
        if eks:
            raise C.MarketingError("Eksik alanlar var: " + ", ".join(LABELS.get(k, k) for k in eks) + ".", 409)
        c.execute(FOY.update().where(FOY.c.id == r.id).values(durum="onayda", gonderen=user, gonderme=C.now(), gerekce=None))
        rid = r.id
    with engine.connect() as c:
        return _dict(c.execute(sa.select(FOY).where(FOY.c.id == rid)).one(), fst["required"])


def decide(engine: sa.engine.Engine, tenant: str, user: str, stok: str, donem: str, approve: bool, body: dict[str, Any],
           fst: dict[str, Any]) -> dict[str, Any]:
    """Satış onayı. Onaya gönderen ya da son düzelten kişi onaylayamaz (iki göz). Eksik alanlı föy onaylanmaz;
    uyumsuzluk varsa onay yalnız gerekçeyle (`kabul` + `not`)."""
    note = C.text(body.get("not") or body.get("note"), 4000)
    with engine.begin() as c:
        r = get_row(c, tenant, stok, donem, lock=True)
        if not r:
            raise C.MarketingError("Föy bulunamadı.", 404)
        if r.durum == "onayli":
            raise C.MarketingError("Föy zaten onaylı.", 409)
        me = user.lower()
        if me in {(r.gonderen or "").lower(), (r.guncelleyen or "").lower()} - {"", "sistem"}:
            raise C.MarketingError("Föyü hazırlayan ya da onaya gönderen kişi onaylayamaz; başka bir yetkili onaylamalı.", 409)
        if not approve:
            if not note:
                raise C.MarketingError("Geri gönderme gerekçesi yazın.")
            c.execute(FOY.update().where(FOY.c.id == r.id).values(durum="taslak", gerekce=note, gonderen=None, gonderme=None))
        else:
            eks = C.loads(r.eksikler_json, [])
            if eks:
                raise C.MarketingError("Eksik alanlı föy onaylanmaz: " + ", ".join(LABELS.get(k, k) for k in eks) + ".", 409)
            mm = blocking(C.loads(r.uyumsuzluk_json, []))
            if mm and not (body.get("kabul") and note):
                raise C.MarketingError("Föyde uyumsuzluk var (" + "; ".join(x["ad"] for x in mm) + "). Düzeltin ya da "
                                       "gerekçe yazarak kabul edin.", 409)
            c.execute(FOY.update().where(FOY.c.id == r.id).values(durum="onayli", onaylayan=user, onay_zamani=C.now(),
                                                                  onay_notu=note, eski=False, gerekce=None))
        rid = r.id
    with engine.connect() as c:
        return _dict(c.execute(sa.select(FOY).where(FOY.c.id == rid)).one(), fst["required"])


def set_args(engine: sa.engine.Engine, tenant: str, stok: str, donem: str, args: list[str], fst: dict[str, Any],
             meta: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        r = get_row(c, tenant, stok, donem, lock=True)
        if not r:
            raise C.MarketingError("Föy bulunamadı.", 404)
        fields = C.loads(r.alanlar_json, {})
        cur = fields.get("argumanlar") or {}
        if (cur.get("kaynak") or "").startswith("crm:") and cur.get("deger"):
            raise C.MarketingError("CRM'de «Bu kitap neden önemli?» dolu; argüman oradan geliyor.", 409)
        fields["argumanlar"] = {"deger": args, "kaynak": "zeki", **meta}
        vals: dict[str, Any] = {"alanlar_json": C.dump(fields), "eksikler_json": C.dump(missing(fields, fst["required"])),
                                "guncelleme": C.now()}
        if r.durum != "taslak":
            vals.update(durum="taslak", surum=r.surum + (1 if r.durum == "onayli" else 0), onaylayan=None, onay_zamani=None,
                        gonderen=None, gonderme=None)
        c.execute(FOY.update().where(FOY.c.id == r.id).values(**vals))
        rid = r.id
    with engine.connect() as c:
        return _dict(c.execute(sa.select(FOY).where(FOY.c.id == rid)).one(), fst["required"])


def draft_args(llm: Any, foy: dict[str, Any], raw: dict[str, Any], st: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """CRM'de «Bu kitap neden önemli?» boşsa üç kısa satış argümanı. Yalnız CRM metinlerine dayanır; denetimden geçmeyen
    cümle düşer."""
    f = {a["key"]: a.get("deger") for a in foy["alanlar"]}
    sources = [x for x in (_long(raw.get("new_TantmFyMetni")), _long(raw.get("new_tanitimfoymetni")), _long(raw.get("new_kitapspotu")),
                           _long(raw.get("new_ozet")), _long(raw.get("new_editorunkitabaveyazaradairgorusleri")),
                           f.get("ad"), f.get("yazar"), f.get("kitaplik"), f.get("hedefKitle")) if x]
    facts = []
    if f.get("fiyat"):
        facts.append(f"Fiyat: {f['fiyat']:g} TL")
    if f.get("sayfa"):
        facts.append(f"Sayfa: {f['sayfa']}")
    prompt = ("Bayiye kitap satan saha temsilcisi için bu kitabın «neden satılır» üç kısa satış argümanını yaz. Her argüman "
              "tek cümle, ayrı satırda, başında «- » olsun. Yalnız verilen metinlere dayan; kitap hakkında bilgi ekleme.\n\n"
              "Olgu listesi (yazabileceğin sayılar yalnız bunlar):\n" + ("\n".join(facts) or "—") + "\n\nKitap bilgisi:\n"
              + "\n\n".join(str(x)[:4000] for x in sources))
    raw_text = str(llm.chat([{"role": "system", "content": P.SYSTEM}, {"role": "user", "content": prompt}], max_tokens=500) or "")
    res = G.check(raw_text, sources, facts, st.get("claims") or ())
    args = split_args(res["metin"])
    return args, {"dusenSayisi": res["dusenSayisi"], "dusen": res["dusen"], "zaman": C.iso(C.now())}


# ------------------------------------------------------------------ kapak görseli


_covers: dict[str, tuple[float, Optional[bytes]]] = {}


def cover_bytes(base: str, rel: Optional[str]) -> Optional[bytes]:
    """CRM kapak yolu (`new_resimurl`, göreli) + Yönetim ayarındaki adres. Adres girilmemişse ya da görsel okunamazsa
    None: föyde «kapak görseli yok» kutusu çıkar. Yalnız okuma (GET); 1 saat bellekte."""
    if not rel:
        return None
    url = rel if rel.lower().startswith(("http://", "https://")) else (f"{base.rstrip('/')}/{rel.lstrip('/')}" if base else "")
    if not url.lower().startswith(("http://", "https://")):
        return None
    hit = _covers.get(url)
    if hit and time.monotonic() - hit[0] < 3600:
        return hit[1]
    data: Optional[bytes] = None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ZEKI-foy"}), timeout=6) as res:  # noqa: S310
            if (res.headers.get_content_type() or "").startswith("image/"):
                data = res.read(8_000_000)
    except Exception as e:  # noqa: BLE001 — kapaksız föy de çıkar
        log.info("föy kapak okunamadı (%s): %s", url, e)
    _covers[url] = (time.monotonic(), data)
    return data


# ------------------------------------------------------------------ gönderim


def send_mail(subject: str, text: str, to: list[str], attachments: list[tuple[str, bytes, str]]) -> str:
    """İç dağıtım listesine ekli e-posta (yalnız kişinin tıklamasıyla). SMTP ayarı yoksa `no_smtp`."""
    from semantic_bridge.alerts import smtp_settings

    if not to:
        return "no_recipient"
    cfg = smtp_settings()
    if not cfg:
        return "no_smtp"
    try:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, cfg["sender"], ", ".join(to)
        msg.set_content(text)
        for name, body, mime in attachments:
            main, _, sub = mime.partition("/")
            msg.add_attachment(body, maintype=main, subtype=sub, filename=name)
        ctx = ssl.create_default_context()
        server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=30, context=ctx) if cfg["ssl"]
                  else smtplib.SMTP(cfg["host"], cfg["port"], timeout=30))
        with server as s:
            if not cfg["ssl"] and cfg["starttls"]:
                s.starttls(context=ctx)
            if cfg["user"]:
                s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
        return "sent"
    except Exception as e:  # noqa: BLE001
        log.warning("föy paketi gönderilemedi: %s", e)
        return "failed"


def record_send(engine: sa.engine.Engine, tenant: str, donem: str, to: list[str], user: str, dosya: str, adet: int, sonuc: str) -> dict[str, Any]:
    sid = C._uid()
    with engine.begin() as c:
        c.execute(SENDS.insert().values(id=sid, tenant_id=tenant, donem=donem, alicilar=", ".join(to), gonderen=user,
                                        zaman=C.now(), dosya=dosya, adet=adet, sonuc=sonuc))
    return {"id": sid, "sonuc": sonuc, "alici": len(to), "adet": adet}


def sends_stmt(tenant: str, donem: str):
    return sa.select(SENDS).where(SENDS.c.tenant_id == tenant, SENDS.c.donem == donem).order_by(SENDS.c.zaman.desc())


def sends_of(engine: sa.engine.Engine, tenant: str, donem: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sends_stmt(tenant, donem)).all()
    return [{"id": r.id, "alicilar": r.alicilar, "gonderen": r.gonderen, "zaman": C.iso(r.zaman), "dosya": r.dosya, "adet": r.adet,
             "sonuc": r.sonuc} for r in rows]


def crm_todo(foy: dict[str, Any]) -> list[dict[str, Any]]:
    """Onaylı föyde elle ya da Zeki AI ile gelen metin: CRM kitap kartına elle işlenecek (bu modül CRM'e yazmaz)."""
    target = {"tanitim": "new_TantmFyMetni", "argumanlar": "new_kitabinonecikanyanlari", "fiyat": "new_kdvdahilfiyat",
              "barkod": "new_ean13", "hedefKitle": "new_hedefkitle", "ozet": "new_ozet"}
    out = []
    for a in foy["alanlar"]:
        if a["key"] in target and a.get("kaynak") in ("elle", "zeki") and not _empty(a.get("deger")):
            v = a["deger"]
            out.append({"alan": target[a["key"]], "ad": a["ad"], "deger": "\n".join(v) if isinstance(v, list) else v,
                        "kaynak": a["kaynak"]})
    return out
