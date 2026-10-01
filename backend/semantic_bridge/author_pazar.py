"""M7 Yazar ilişkileri × M39 dağıtımcı kataloğu: yazar kartında «Pazarda bu yazar (dağıtımcı kataloğu)».

Kaynak: `semantic_pazar_dagitim_titles` (Başarı Dağıtım kataloğunun portalda tutulan güncel hâli, `pazar_dagitim.py`).
Yalnız Başarı'da yazar alanı var (%98 dolu); D&R kataloğunda yazar yok, orada yalnız barkodla «D&R'de de var» sayılır.
Yalnız son görüntüde bulunan başlıklar sayılır (katalogdan düşen başlık «satışta» sayılmaz).

**Eşleme iki yoldan, ikisi de ayrı gösterilir:**

1. *Barkodla doğrulanan*: yazarın CRM'de yazar rolüyle bağlı kitaplarının barkodu (`new_ean13`) ya da stok kodunun
   Logo barkodu (`semantic_pazar_dagitim_barkod`) Başarı'daki başlıkla aynı. Bu kitaplar kesin bu yazarındır.
2. *Ad eşleşmesi*: Başarı'nın yazar alanı virgül/noktalı virgül/eğik çizgi/«&» ile parçalanır, her parça katlanır
   (Türkçe harf, büyük/küçük, noktalama, «Prof. Dr.» gibi unvan atılır) ve yazarın adıyla — ya da doğrulanan
   kitaplarında Başarı'nın bu yazar için kullandığı yazımla — birebir karşılaştırılır. «Kolektif», «Komisyon»,
   «Anonim» gibi ortak adlar hiçbir zaman eşleşmez.

Ad eşleşmesi **hiçbir kayda bağlanmaz** (yazar kartına, CRM'e, sözleşmeye yazılmaz); yalnız ekranda gösterilir. Aynı ad
farklı kişi olabileceği için belirsizlik kuralla aranır ve nedeniyle ekrana yazılır (`nedenler`):
tek sözcüklük ad, barkodla hiçbir kitabın doğrulanamaması, başka yayınevindeki kitapların alanının (üst kategori)
yazarın doğrulanan kitaplarıyla hiç örtüşmemesi, TİMAŞ markasında aynı adla CRM'de bu yazara bağlı olmayan kitap.

Çıkış endeksi (dağıtımcı deposundan kitapçılara çıkış; okura satış ve pazar payı değildir) portalın gece görüntüleri
en az iki olunca `pazar_dagitim.outflow` ile aynı kuralla hesaplanır; o zamana kadar alan boştur ve nedeni yazılır.
"""
from __future__ import annotations

import re
import threading
import unicodedata
from datetime import date, timedelta
from statistics import median
from typing import Any, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import pazar_dagitim as D
from semantic_bridge.zeki_text import fold

#: Bir kişiyi göstermeyen yazar değerleri (katlanmış biçim). Bunlar ne parçalanır ne eşleşir.
ORTAK_AD = frozenset({"kolektif", "komisyon", "anonim", "derleme", "kolektif yazarlar", "cesitli yazarlar",
                      "kolektif kolektif", "ortak kitap", "kolektif komisyon"})
#: Ad karşılaştırmasında atılan unvanlar (katlanmış, noktasız).
UNVAN = frozenset({"prof", "dr", "doc", "yrd", "ogr", "gor", "uyesi", "av", "op", "uzm", "ars"})
_SPLIT = re.compile(r"[,;/&]|\s+-\s+|\s+ve\s+")
_PAREN = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_NONWORD = re.compile(r"[^0-9a-z ]+")

SATISTA = "Satışta"

NOT_EN = ("Başarı Dağıtım kataloğu dağıtımcının kitapçılara açık listesidir; okura satışı göstermez. "
          "Ad eşleşmesi yazar kaydına bağlanmaz: aynı adı taşıyan farklı kişiler olabilir.")
F_ESLEME = ("Eşleme: (1) barkodla doğrulanan = yazarın CRM'de yazar rolüyle bağlı kitaplarının barkodu ya da stok "
            "kodunun Logo barkodu Başarı'daki başlıkla aynı; (2) ad eşleşmesi = Başarı'nın yazar alanı virgül, noktalı "
            "virgül, eğik çizgi, «&», « - » ve « ve » ile parçalanır, her parça harf farkı, noktalama ve unvan atılarak "
            "yazarın adıyla (ya da doğrulanan kitaplarında Başarı'nın kullandığı yazımla) birebir karşılaştırılır; "
            "«Kolektif», «Komisyon», «Anonim» eşleşmez. Yalnız son görüntüde bulunan başlıklar sayılır. TİMAŞ = TİMAŞ "
            "grubu markası (başlıklarının en az %80'i TİMAŞ'ın Logo'sunda kartı olan marka). Satışta / baskısı yok = "
            "Başarı'nın stok durumu; en yüksek baskı = baskı sayısının en büyüğü; fiyat = liste fiyatı (en düşük, orta "
            "değer, en yüksek). D&R'de de var = aynı barkod D&R kataloğunun son görüntüsünde.")

_lock = threading.Lock()
#: (motor, kiracı) → (son görüntü, başlık sayısı, katlanmış ad → ham yazar değerleri)
_INDEX: dict[tuple[int, str], tuple[Optional[date], int, dict[str, set[str]]]] = {}


# ================================================================================ ad katlama


def name_key(s: Any) -> str:
    """Karşılaştırma anahtarı: Türkçe harf katlama, parantez içi ve noktalama atılır, unvanlar düşer."""
    t = unicodedata.normalize("NFKD", fold(_PAREN.sub(" ", str(s or ""))))
    t = _NONWORD.sub(" ", "".join(ch for ch in t if not unicodedata.combining(ch)))
    return " ".join(w for w in t.split() if w not in UNVAN)


def split_authors(raw: Any) -> list[str]:
    """Başarı yazar alanındaki kişiler (katlanmış). Ortak adlar ve boş parçalar düşer."""
    whole = name_key(raw)
    if not whole or whole in ORTAK_AD:
        return []
    out: list[str] = []
    for part in _SPLIT.split(fold(_PAREN.sub(" ", str(raw or "")))):
        k = name_key(part)
        if k and k not in ORTAK_AD and k not in out:
            out.append(k)
    return out


def _last(engine: sa.engine.Engine, tenant: str, kaynak: str) -> Optional[date]:
    return max(D.processed(engine, tenant, kaynak), default=None)


def author_index(engine: sa.engine.Engine, tenant: str) -> tuple[Optional[date], dict[str, set[str]]]:
    """Son Başarı görüntüsündeki farklı yazar değerlerinin dizini: katlanmış kişi adı → ham değerler. Görüntü tarihi
    ve başlık sayısı değişince yeniden kurulur (gece turundan sonra ilk istekte)."""
    last = _last(engine, tenant, "basari")
    T = D.TITLES.c
    if last is None:
        return None, {}
    with engine.connect() as c:
        n = int(c.execute(sa.select(sa.func.count()).select_from(D.TITLES).where(
            T.tenant_id == tenant, T.kaynak == "basari", T.son_gorulme == last)).scalar() or 0)
    key = (id(engine), tenant)
    with _lock:
        hit = _INDEX.get(key)
        if hit and hit[0] == last and hit[1] == n:
            return last, hit[2]
    idx: dict[str, set[str]] = {}
    with engine.connect() as c:
        for (raw,) in c.execute(sa.select(T.yazar).where(
                T.tenant_id == tenant, T.kaynak == "basari", T.son_gorulme == last, T.yazar.isnot(None)).distinct()):
            for k in split_authors(raw):
                idx.setdefault(k, set()).add(raw)
    with _lock:
        _INDEX[key] = (last, n, idx)
    return last, idx


# ================================================================================ sorgular (sorgu bilgisi de bunları gösterir)

_COLS = ("barkod", "ad", "yazar", "yayinevi", "ust_kategori", "durum", "baski_no", "fiyat", "basim_yili", "stok", "timas")


def verified_stmt(tenant: str, last: date, eans: Iterable[str], codes: Iterable[str]):
    """Barkodla doğrulanan başlıklar: CRM barkodu ya da stok kodunun Logo barkodu."""
    T, K = D.TITLES.c, D.BARKOD.c
    eans, codes = sorted(set(eans)), sorted(set(codes))
    cond = [T.barkod.in_(eans)] if eans else []
    if codes:
        cond.append(T.barkod.in_(sa.select(K.barkod).where(K.tenant_id == tenant, K.stok_kodu.in_(codes))))
    return (sa.select(*(getattr(T, c) for c in _COLS)).where(
        T.tenant_id == tenant, T.kaynak == "basari", T.son_gorulme == last, sa.or_(*cond) if cond else sa.false()))


def by_name_stmt(tenant: str, last: date, raws: Iterable[str]):
    T = D.TITLES.c
    return sa.select(*(getattr(T, c) for c in _COLS)).where(
        T.tenant_id == tenant, T.kaynak == "basari", T.son_gorulme == last, T.yazar.in_(sorted(set(raws))))


def dr_stmt(tenant: str, last: date, barkods: Iterable[str]):
    T = D.TITLES.c
    return sa.select(T.barkod).where(T.tenant_id == tenant, T.kaynak == "dr", T.son_gorulme == last,
                                      T.barkod.in_(sorted(set(barkods))))


def _rows(engine: sa.engine.Engine, stmt) -> list[dict[str, Any]]:
    with engine.connect() as c:
        return [dict(r) for r in c.execute(stmt).mappings().all()]


def _chunks(xs: list[str], n: int = 900) -> Iterable[list[str]]:
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


# ================================================================================ hesap


def _ean(v: Any) -> Optional[str]:
    return D.barkod(v)


def book_keys(books: Iterable[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """CRM kitap satırlarından (author_growth / author_snapshots biçimi) barkodlar ve stok kodları."""
    eans: set[str] = set()
    codes: set[str] = set()
    for b in books or []:
        e = _ean(b.get("new_ean13"))
        if e:
            eans.add(e)
        for k in ("new_StokKodu", "new_EKitapStokKodu"):
            v = str(b.get(k) or "").strip()
            if v:
                codes.add(v)
    return eans, codes


def market(engine: sa.engine.Engine, tenant: str, name: str, *, books: Optional[list[dict[str, Any]]] = None,
           today: Optional[date] = None) -> dict[str, Any]:
    """Yazarın Başarı kataloğundaki görünümü. `books` None = yazarın kitap listesi okunamadı (yalnız ad eşleşmesi).
    Dönen `_sorgular` sorgu bilgisi içindir, uç onu cevaptan çıkarır."""
    D.ensure(engine)
    last, idx = author_index(engine, tenant)
    snap = _snapshot(engine, tenant, "basari", last)
    base: dict[str, Any] = {"kaynak": D.KAYNAK["basari"], "tarih": last.isoformat() if last else None,
                            "kaynakZamani": snap, "ad": name, "not": NOT_EN}
    if last is None:
        return {**base, "okundu": False, "kitaplar": [], "belirsiz": False, "nedenler": [], "adlar": [],
                "_sorgular": {}}
    key = name_key(name)
    eans, codes = book_keys(books or [])
    stmts: dict[str, Any] = {}
    verified: dict[str, dict[str, Any]] = {}
    if eans or codes:
        st = verified_stmt(tenant, last, eans, codes)
        stmts["dogrulanan"] = st
        verified = {r["barkod"]: r for r in _rows(engine, st)}
    # Başarı'nın bu yazar için kullandığı yazım: doğrulanan kitaplardaki parçalardan adla sözcük paylaşanlar.
    toks = set(key.split())
    keys: set[str] = {key} if key and key not in ORTAK_AD else set()
    for r in verified.values():
        for part in split_authors(r.get("yazar")):
            if toks & set(part.split()) and len(part.split()) >= 2:
                keys.add(part)
    raws = sorted({raw for k in keys for raw in idx.get(k, ())})
    named: dict[str, dict[str, Any]] = {}
    if raws:
        stmts["ad"] = by_name_stmt(tenant, last, raws)
        for part in _chunks(raws):
            for r in _rows(engine, by_name_stmt(tenant, last, part)):
                named[r["barkod"]] = r
    items: dict[str, dict[str, Any]] = {}
    for b, r in {**named, **verified}.items():
        items[b] = {**r, "dogrulandi": b in verified}
    dr_have: set[str] = set()
    if items:
        dr_last = _last(engine, tenant, "dr")
        if dr_last:
            stmts["dr"] = dr_stmt(tenant, dr_last, list(items))
            for part in _chunks(sorted(items)):
                dr_have |= {r["barkod"] for r in _rows(engine, dr_stmt(tenant, dr_last, part))}
    cik, pencere = _outflow(engine, tenant, list(items))
    nedenler = reasons(key, books, list(items.values()))
    kitaplar = sorted(
        ({"barkod": r["barkod"], "ad": r["ad"], "yayinevi": r["yayinevi"], "ustKategori": r["ust_kategori"],
          "durum": r["durum"], "baskiNo": r["baski_no"], "fiyat": r["fiyat"], "basimYili": r["basim_yili"],
          "timas": bool(r["timas"]), "dogrulandi": r["dogrulandi"], "drde": r["barkod"] in dr_have,
          "cikis": cik.get(r["barkod"]) if pencere else None} for r in items.values()),
        key=lambda x: (not x["timas"], not x["dogrulandi"], -(x["baskiNo"] or 0), x["ad"] or ""))
    adlar = sorted({raw for k in keys for raw in idx.get(k, ())} & {r.get("yazar") for r in items.values()})
    return {**base, "okundu": True, "kitaplar": kitaplar, "adlar": adlar, "belirsiz": bool(nedenler),
            "nedenler": nedenler, "dogrulanan": len(verified), "kitapListesi": books is not None,
            "timas": group([x for x in kitaplar if x["timas"]]), "diger": group([x for x in kitaplar if not x["timas"]]),
            "yayinevleri": publishers(kitaplar), "enYuksekBaski": top_edition(kitaplar),
            "fiyat": price_range(kitaplar), "drdeOlan": sum(1 for x in kitaplar if x["drde"]),
            "cikis": ({"bas": pencere[0].isoformat(), "son": pencere[1].isoformat(),
                       "timas": sum(x["cikis"] or 0 for x in kitaplar if x["timas"]),
                       "diger": sum(x["cikis"] or 0 for x in kitaplar if not x["timas"])} if pencere else None),
            "cikisNot": None if pencere else ("Çıkış endeksi, portalın dağıtımcı kataloğundan aldığı günlük görüntüler "
                                              "en az iki olunca görünür; kaynak geçmiş tutmaz."),
            "_sorgular": stmts}


def group(xs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kitap": len(xs), "satista": sum(1 for x in xs if x["durum"] == SATISTA),
            "baskisiYok": sum(1 for x in xs if x["durum"] in D.KAPALI_DURUM),
            "diger": sum(1 for x in xs if x["durum"] != SATISTA and x["durum"] not in D.KAPALI_DURUM),
            "dogrulanan": sum(1 for x in xs if x["dogrulandi"])}


def publishers(xs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by: dict[str, dict[str, Any]] = {}
    for x in xs:
        p = x["yayinevi"] or "Yayınevi yazılmamış"
        g = by.setdefault(p, {"yayinevi": p, "kitap": 0, "satista": 0, "timas": x["timas"]})
        g["kitap"] += 1
        g["satista"] += 1 if x["durum"] == SATISTA else 0
    return sorted(by.values(), key=lambda g: (not g["timas"], -g["kitap"], g["yayinevi"]))


def top_edition(xs: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    best = max((x for x in xs if x["baskiNo"]), key=lambda x: x["baskiNo"], default=None)
    return {"baski": best["baskiNo"], "ad": best["ad"], "yayinevi": best["yayinevi"]} if best else None


def price_range(xs: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    ps = sorted(float(x["fiyat"]) for x in xs if x["fiyat"] and x["fiyat"] > 0)
    if not ps:
        return None
    return {"enDusuk": ps[0], "orta": round(median(ps), 2), "enYuksek": ps[-1], "kitap": len(ps)}


def reasons(key: str, books: Optional[list[dict[str, Any]]], items: list[dict[str, Any]]) -> list[str]:
    """Ad eşleşmesinin neden belirsiz olabileceği (boş = belirsizlik bulunmadı). Yalnız ad eşleşmesi olan başlık
    varken anlamlıdır; hepsi barkodla doğrulanmışsa belirsizlik yoktur."""
    named = [x for x in items if not x["dogrulandi"]]
    if not named:
        return []
    out: list[str] = []
    if len(key.split()) < 2:
        out.append("Ad tek sözcük; aynı adı taşıyan başka yazarlar olabilir.")
    ver = [x for x in items if x["dogrulandi"]]
    if not ver:
        out.append("Yazarın kitap listesi okunamadı; eşleşme yalnız ada dayanıyor." if books is None else
                   "Yazarın TİMAŞ kitaplarından hiçbiri Başarı kataloğunda barkodla bulunamadı; eşleşme yalnız ada "
                   "dayanıyor.")
    else:
        ours = {x["ust_kategori"] for x in ver if x["ust_kategori"]}
        theirs = {x["ust_kategori"] for x in named if not x["timas"] and x["ust_kategori"]}
        if ours and theirs and not ours & theirs:
            out.append(f"Başka yayınevlerindeki kitapların alanı ({', '.join(sorted(theirs))}) yazarın TİMAŞ'taki "
                       f"kitaplarının alanıyla ({', '.join(sorted(ours))}) örtüşmüyor; aynı adı taşıyan başka biri "
                       "olabilir.")
    stray = [x for x in named if x["timas"]]
    if stray:
        out.append(f"TİMAŞ markalarında bu adla {len(stray)} kitap CRM'de bu yazara bağlı değil; kayıt eksiği ya da "
                   "aynı adı taşıyan başka bir yazar olabilir.")
    return out


def _outflow(engine: sa.engine.Engine, tenant: str, barkods: list[str]) -> tuple[dict[str, int], Optional[tuple[date, date]]]:
    """Başlık başına çıkış endeksi, son kesintisiz görüntü dizisinde (pazar_dagitim ile aynı kural ve pencere)."""
    win = D.stretch(engine, tenant)
    if not win or not barkods:
        return {}, win
    O = D.OBS.c
    want = set(barkods)
    out: dict[str, int] = {}
    bas, son = win[0] + timedelta(days=1), win[1] + timedelta(days=1)
    with engine.connect() as c:
        for part in _chunks(sorted(want)):
            for b, v in c.execute(sa.select(O.barkod, sa.func.sum(O.cikis)).where(
                    O.tenant_id == tenant, O.kaynak == "basari", O.tarih >= bas, O.tarih < son,
                    O.barkod.in_(part)).group_by(O.barkod)).all():
                out[b] = int(v or 0)
    return out, win


def _snapshot(engine: sa.engine.Engine, tenant: str, kaynak: str, tarih: Optional[date]) -> Optional[str]:
    if tarih is None:
        return None
    S = D.SNAPS.c
    with engine.connect() as c:
        v = c.execute(sa.select(S.kaynak_zamani).where(S.tenant_id == tenant, S.kaynak == kaynak, S.tarih == tarih)).scalar()
    return str(v) if v else None


# ================================================================================ sorgu bilgisi


def kaynaklar(engine: sa.engine.Engine, tenant: str, out: dict[str, Any], stmts: dict[str, Any]):
    """Her rakamın kaynağı: portal tablosundan okunan başlıklar (koşan ifade) ve eşleme kuralı."""
    from semantic_bridge import provenance as P

    k = P.Kaynaklar(data_end=out.get("tarih"))
    g = k.sorgu("yazar.pazar.basari", "Başarı Dağıtım kataloğu", "logo", D.SQL_BASARI,
                description="Her gün okunur, portalda yalnız değişen satır saklanır; bu ekran son görüntüyü okur.")
    ins: list[str] = []
    titles = {"dogrulanan": "Barkodla doğrulanan kitaplar", "ad": "Ad eşleşmesiyle bulunan kitaplar",
              "dr": "D&R kataloğunda da olanlar"}
    for tag, st in stmts.items():
        ins.append(k.portal(f"yazar.pazar.{tag}", titles.get(tag, tag), st, engine, origin=[g],
                            description="Dağıtımcı kataloğunun portaldaki güncel hâli, son görüntü."))
    if not ins:
        ins = [g]
    ref = k.hesap("yazarPazar", F_ESLEME, ins)
    fields = {"kitaplar[]": ref, "timas": ref, "diger": ref, "yayinevleri[]": ref, "enYuksekBaski": ref, "fiyat": ref,
              "drdeOlan": ref, "dogrulanan": ref}
    if out.get("cikis"):
        fields["cikis"] = k.hesap("cikis", D.F_CIKIS, ins)
    k.alanlar(fields)
    return k
