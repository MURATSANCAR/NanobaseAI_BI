"""M9 Fiyatlama — dağıtımcı kataloğundan pazar fiyatı önerisi.

Bugüne kadar rakip/pazar fiyatı yalnız elle giriliyordu (`semantic_pricing_market`). Bu modül, M39'un her gün okuduğu
Başarı Dağıtım kataloğundan (`semantic_pazar_dagitim_titles`, güncel tek görüntü) kitabın kategorisindeki **TİMAŞ grubu
dışı** başlıkların liste fiyatı dağılımını verir: ortanca, çeyrekler, başlık sayısı, sayfa başına fiyat ortancası ve
aynı kümede D&R satış fiyatının D&R liste fiyatına oranı. Hepsi hem süzgeçsiz hem son iki basım yılıyla.

- Hesap `model.quantile` ile yapılır (fiyatlamanın tek hesap yeri `pricing/model.py`); burada yalnız küme kurulur.
- Öneri hesaba kendiliğinden girmez: kullanıcı ekranda tek tıkla ortancayı «Rakip ve pazar fiyatları»na ekler
  (mevcut `POST /api/v1/pricing/market`); oradan `M.recommend()`'in emsal bandına girer ve onaya giden analizle
  birlikte saklanır (onay anında yeniden hesapta da aynı değer kullanılır).
- Dağıtımcı verisi kitapçılara açılan katalogdur; okura satış ya da pazar payı değildir.
- Kategori: önce kitabın kendi Başarı kaydı (Logo barkodu ↔ stok kodu), yoksa CRM kitaplık adının Başarı üst/alt
  kategori adıyla katlanmış (büyük/küçük harf ve noktalama duyarsız) eşleşmesi, o da yoksa kullanıcının seçtiği
  Başarı kategorisi (`categories()`).
- Daraltma: sayfa ±%20 ve kapak türü, ancak daraltılmış kümede en az `DAR_MIN` başlık kalırsa uygulanır; kalmazsa
  kategori kümesi kullanılır ve ekran bunu yazar.

Kaynağa (`API_URUN_DB`), Logo'ya ve CRM'e yazılmaz; bu modül yalnız portal tablolarını okur.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import pazar_dagitim as PD
from semantic_bridge.pricing import model as M
from semantic_bridge.pricing.data import fold

#: Sayfa aralığı (emsal kitaplarla aynı: ±%20).
SAYFA_BANT = 0.20
#: Daraltma (sayfa, kapak) ancak bu kadar başlık kalırsa uygulanır; altında dağılım anlamsızlaşır.
DAR_MIN = 5
#: «Son basım yılları» süzgeci: katalog tarihinin yılı ve öncesi, bu kadar yıl.
SON_YIL = 2

F_DAGITIM = ("Dağıtımcı fiyat dağılımı: Başarı Dağıtım kataloğunun son görüntüsünde bulunan, TİMAŞ grubu dışı, liste "
             "fiyatı sıfırdan büyük başlıklar; seçilen kategori (tam yol ya da üst kategori). Kitabın sayfa sayısı "
             f"varsa ±%{round(SAYFA_BANT * 100)} sayfa aralığı, kapak türü varsa aynı kapak sınıfı (karton, sert, "
             f"fleksi, tel dikiş) ile daraltılır; daraltılmış kümede {DAR_MIN} başlıktan az kalırsa o daraltma "
             "uygulanmaz. Ortanca ve çeyrekler doğrusal ara değerle (emsal bandıyla aynı hesap); sayfa başına fiyat = "
             "liste fiyatı ÷ sayfa, sayfası bilinen başlıklarda. D&R oranı = aynı barkodun D&R satış fiyatı ÷ D&R "
             "liste fiyatı, D&R'nin son görüntüsünde bulunan ve sitelerden silinmemiş ürünlerde. Son basım yılları = "
             f"katalog tarihinin yılı ve önceki {SON_YIL - 1} yıl. Kitapçılara açılan katalog fiyatıdır; okura satış "
             "fiyatı ya da pazar payı değildir.")
F_KATEGORI = ("Kategori seçimi: önce kitabın kendi Başarı kaydı (Logo'daki barkodu ↔ stok kodu), yoksa CRM kitaplık "
              "adının Başarı üst/alt kategori adıyla büyük/küçük harf ve noktalama duyarsız eşleşmesi, o da yoksa "
              "ekranda seçilen Başarı kategorisi.")
NOT = ("Dağıtımcı kataloğundaki liste fiyatlarıdır: kitapçılara açılan fiyat, okura satış değildir. TİMAŞ grubunun "
       "kendi kitapları sayılmaz. Öneri hesaba kendiliğinden girmez; «Pazar fiyatı olarak ekle» ile eklenir.")


# ================================================================================ yardımcılar


def key(text: Optional[str]) -> str:
    """Katlanmış ad: Türkçe büyük/küçük harf duyarsız, noktalama ve fazla boşluk yok («Edebiyat / Roman» → «edebiyat roman»)."""
    return " ".join(re.sub(r"[^\w]+", " ", fold(text)).split())


def kapak_sinifi(text: Optional[str]) -> Optional[str]:
    """Kapak/cilt türü → sınıf. CRM cilt şekli («Amerikan Cilt», «Flexi Kapak Cilt», «Sert Kapak», «Tel Dikiş») ile
    Başarı'nın kapak türü («Karton Kapak», «Ciltli», «Sert Kapak», «İnce Kapak») aynı sınıfa düşer. Bilinmeyen → None."""
    k = key(text)
    if not k:
        return None
    if "fleks" in k or "flexi" in k:
        return "fleksi"
    if "amerikan" in k or "karton" in k or "ince" in k or "yumuşak" in k or "ciltsiz" in k:
        return "karton"
    if "sert" in k or "ciltli" in k or "bez" in k:
        return "sert"
    if re.search(r"\btel\b", k):
        return "tel"
    return None


KAPAK_ETIKET = {"karton": "karton kapak", "sert": "sert kapak", "fleksi": "fleksi kapak", "tel": "tel dikiş"}


def son_goruntu(engine: sa.engine.Engine, tenant: str, kaynak: str) -> Optional[date]:
    return max(PD.processed(engine, tenant, kaynak), default=None)


def _gun(d: Optional[date]) -> Optional[str]:
    return d.strftime("%d.%m.%Y") if d else None


def _sayi(n: int) -> str:
    """1234 → «1.234» (Türkçe binlik)."""
    return f"{n:,}".replace(",", ".")


def _kat_kosul(col_kat, col_ust, kategori: str):
    """«Üst>Alt» tam yol ise tam eşleşme, yalnız üst kategori ise üst kategori eşleşmesi."""
    return col_kat == kategori if ">" in kategori else col_ust == kategori


# ================================================================================ sorgular (sorgu bilgisi de bunları gösterir)


def rows_stmt(tenant: str, kategori: str, basari: date, dr: Optional[date]):
    """Kategori kümesi: Başarı'nın son görüntüsündeki TİMAŞ dışı, fiyatlı başlıklar + aynı barkodun güncel D&R satırı."""
    b, r = PD.TITLES.alias("b"), PD.TITLES.alias("r")
    on = sa.and_(r.c.tenant_id == b.c.tenant_id, r.c.kaynak == "dr", r.c.barkod == b.c.barkod,
                 r.c.son_gorulme == dr) if dr else sa.false()
    return (sa.select(b.c.barkod, b.c.fiyat, b.c.sayfa, b.c.kapak, b.c.basim_yili,
                      r.c.fiyat.label("dr_liste"), r.c.dr_fiyat, r.c.durum.label("dr_durum"))
            .select_from(b.outerjoin(r, on))
            .where(b.c.tenant_id == tenant, b.c.kaynak == "basari", b.c.timas.is_(False), b.c.fiyat > 0,
                   b.c.son_gorulme == basari, _kat_kosul(b.c.kategori, b.c.ust_kategori, kategori)))


def categories_stmt(tenant: str, basari: date):
    T = PD.TITLES.c
    return (sa.select(T.kategori, T.ust_kategori, sa.func.count().label("n"))
            .where(T.tenant_id == tenant, T.kaynak == "basari", T.timas.is_(False), T.fiyat > 0,
                   T.son_gorulme == basari, T.kategori.isnot(None))
            .group_by(T.kategori, T.ust_kategori))


def own_stmt(tenant: str, code: str):
    """Kitabın kendi Başarı kaydı: Logo barkodu (çoklu olabilir) → Başarı başlığı; en son görüleni önce."""
    T, K = PD.TITLES.c, PD.BARKOD.c
    j = PD.TITLES.join(PD.BARKOD, sa.and_(K.tenant_id == T.tenant_id, K.barkod == T.barkod))
    return (sa.select(T.barkod, T.kategori, T.ust_kategori, T.sayfa, T.kapak, T.fiyat, T.son_gorulme).select_from(j)
            .where(T.tenant_id == tenant, T.kaynak == "basari", K.stok_kodu == code, T.kategori.isnot(None))
            .order_by(T.son_gorulme.desc(), T.barkod))


# ================================================================================ hesap


def stats(rows: Iterable[Any]) -> dict[str, Any]:
    """Küme özeti: liste fiyatı çeyrekleri, sayfa başına fiyat ortancası, D&R satış/liste oranı ortancası."""
    rows = list(rows)
    prices = [float(r.fiyat) for r in rows if r.fiyat and r.fiyat > 0]
    per_page = [float(r.fiyat) / r.sayfa for r in rows if r.fiyat and r.fiyat > 0 and r.sayfa and r.sayfa > 0]
    ratios = [float(r.dr_fiyat) / float(r.dr_liste) for r in rows
              if r.dr_fiyat and r.dr_liste and r.dr_fiyat > 0 and r.dr_liste > 0
              and not str(r.dr_durum or "").startswith("Site: silinmiş")]

    def rnd(v: Optional[float], n: int = 2) -> Optional[float]:
        return None if v is None else round(v, n)

    return {"n": len(prices), "p25": rnd(M.quantile(prices, 0.25)), "median": rnd(M.quantile(prices, 0.5)),
            "p75": rnd(M.quantile(prices, 0.75)),
            "perPage": {"median": rnd(M.quantile(per_page, 0.5), 3), "n": len(per_page)},
            "dr": {"ratioMedian": rnd(M.quantile(ratios, 0.5), 4), "n": len(ratios)}}


def narrow(rows: list[Any], pages: Optional[float], kapak: Optional[str]) -> tuple[list[Any], dict[str, Any]]:
    """Sayfa ±%20 ve kapak sınıfı daraltması; her biri ancak `DAR_MIN` başlık bırakırsa uygulanır."""
    cur = rows
    info: dict[str, Any] = {"sayfa": None, "sayfaAralik": None, "sayfaUygulandi": False, "kapak": None,
                            "kapakSinifi": None, "kapakUygulandi": False, "notlar": []}
    if pages and pages > 0:
        lo, hi = pages * (1 - SAYFA_BANT), pages * (1 + SAYFA_BANT)
        info["sayfa"], info["sayfaAralik"] = pages, [round(lo), round(hi)]
        cand = [r for r in cur if r.sayfa and lo <= r.sayfa <= hi]
        if len(cand) >= DAR_MIN:
            cur, info["sayfaUygulandi"] = cand, True
        else:
            info["notlar"].append(f"{round(lo)}–{round(hi)} sayfa aralığında {len(cand)} başlık var; sayfa süzgeci "
                                  "uygulanmadı.")
    sinif = kapak_sinifi(kapak)
    if kapak:
        info["kapak"], info["kapakSinifi"] = kapak, sinif
    if sinif:
        cand = [r for r in cur if kapak_sinifi(r.kapak) == sinif]
        if len(cand) >= DAR_MIN:
            cur, info["kapakUygulandi"] = cand, True
        else:
            info["notlar"].append(f"{KAPAK_ETIKET[sinif].capitalize()} {len(cand)} başlık; kapak süzgeci uygulanmadı.")
    elif kapak:
        info["notlar"].append(f"«{kapak}» kapak türü bir sınıfa bağlanamadı; kapak süzgeci uygulanmadı.")
    return cur, info


def match_categories(name: Optional[str], cats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ad → Başarı kategorisi adayları: alt kategori adı birebir (3), üst kategori adı birebir (2), birinin içinde
    geçme (1; en az 4 harf). Sıra: puan, sonra başlık sayısı."""
    k = key(name)
    if not k:
        return []
    out = []
    for c in cats:
        a, u = key(c.get("alt")), key(c.get("ust"))
        if c.get("alt") is not None and a == k:
            score = 3
        elif c.get("alt") is None and u == k:
            score = 2
        elif len(k) >= 4 and ((c.get("alt") is not None and a and (k in a or a in k))
                              or (c.get("alt") is None and u and (k in u or u in k))):
            score = 1
        else:
            continue
        out.append({**c, "puan": score})
    out.sort(key=lambda c: (-c["puan"], -c["n"], c["kategori"]))
    return out


def categories(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Seçilebilir Başarı kategorileri (TİMAŞ dışı, fiyatlı başlık sayısıyla): önce üst kategori, altında tam yollar."""
    PD.ensure(engine)
    tb = son_goruntu(engine, tenant, "basari")
    if not tb:
        return {"tarih": None, "items": [], "not": NOT}
    with engine.connect() as c:
        rows = c.execute(categories_stmt(tenant, tb)).all()
    ust: dict[str, int] = {}
    items: list[dict[str, Any]] = []
    for r in rows:
        u = r.ust_kategori or r.kategori
        ust[u] = ust.get(u, 0) + int(r.n)
        if ">" in r.kategori:
            items.append({"kategori": r.kategori, "ust": u, "alt": r.kategori.split(">", 1)[1].strip(), "n": int(r.n)})
    items += [{"kategori": u, "ust": u, "alt": None, "n": n} for u, n in ust.items()]
    items.sort(key=lambda x: (key(x["ust"]), x["alt"] is not None, key(x["alt"])))
    return {"tarih": tb.isoformat(), "items": items, "not": NOT}


def resolve(engine: sa.engine.Engine, tenant: str, *, code: Optional[str], library: Optional[str],
            secim: Optional[str], cats: list[dict[str, Any]]) -> dict[str, Any]:
    """Kitabın Başarı kategorisi: seçim → kendi kaydı → kitaplık adı eşleşmesi → yok."""
    own = None
    if code:
        with engine.connect() as c:
            r = c.execute(own_stmt(tenant, code)).first()
        if r:
            own = {"barkod": r.barkod, "kategori": r.kategori, "sayfa": r.sayfa, "kapak": r.kapak, "fiyat": r.fiyat,
                   "son": r.son_gorulme.isoformat() if r.son_gorulme else None}
    adaylar = match_categories(library, cats) if library else []
    if secim:
        yol, sec, aciklama = "secim", secim, "Seçtiğiniz Başarı kategorisi."
    elif own:
        yol, sec, aciklama = "kendi", own["kategori"], "Kitabın Başarı kataloğundaki kendi kategorisi."
    elif adaylar:
        yol, sec = "ad", adaylar[0]["kategori"]
        aciklama = f"CRM kitaplık adı «{library}» Başarı kategorisiyle ad üzerinden eşleşti; doğru değilse değiştirin."
    else:
        yol, sec = "yok", None
        aciklama = ("Kitabın Başarı kaydı yok ve kitaplık adı bir Başarı kategorisiyle eşleşmedi; listeden kategori "
                    "seçin.")
    return {"secili": sec, "yol": yol, "aciklama": aciklama, "kendi": own, "kitaplik": library,
            "adaylar": adaylar}


def suggest(engine: sa.engine.Engine, tenant: str, *, code: Optional[str] = None, kategori: Optional[str] = None,
            library: Optional[str] = None, pages: Optional[float] = None, kapak: Optional[str] = None) -> dict[str, Any]:
    """Kitap (ya da seçilen kategori) için dağıtımcı fiyat dağılımı: süzgeçsiz ve son basım yıllarıyla."""
    PD.ensure(engine)
    tb, td = son_goruntu(engine, tenant, "basari"), son_goruntu(engine, tenant, "dr")
    base: dict[str, Any] = {"kaynak": {"basari": tb.isoformat() if tb else None, "dr": td.isoformat() if td else None,
                                       "basariEtiket": PD.KAYNAK["basari"], "drEtiket": PD.KAYNAK["dr"]},
                            "not": NOT, "hazir": bool(tb), "kod": code or None}
    if not tb:
        return {**base, "kategori": None, "kume": 0, "suzgec": None, "tum": None, "sonYillar": None, "etiket": None,
                "mesaj": "Başarı Dağıtım kataloğu henüz okunmadı; ilk görüntü alınınca öneri burada görünür."}
    cats = categories(engine, tenant)["items"]
    kat = resolve(engine, tenant, code=code, library=library, secim=kategori, cats=cats)
    if kat["kendi"] and not pages:
        pages = kat["kendi"]["sayfa"]
    if kat["kendi"] and not kapak:
        kapak = kat["kendi"]["kapak"]
    if not kat["secili"]:
        return {**base, "kategori": kat, "kume": 0, "suzgec": None, "tum": None, "sonYillar": None, "etiket": None,
                "mesaj": kat["aciklama"]}
    with engine.connect() as c:
        rows = c.execute(rows_stmt(tenant, kat["secili"], tb, td)).all()
    cur, info = narrow(rows, pages, kapak)
    years = [tb.year - i for i in range(SON_YIL)]
    tum = stats(cur)
    son = stats(r for r in cur if r.basim_yili in years)
    etiket = f"Dağıtımcı kataloğundan ({_sayi(tum['n'])} başlık, {_gun(tb)})"
    mesaj = None if tum["n"] else "Bu kategoride TİMAŞ dışı fiyatlı başlık yok; başka bir kategori seçin."
    return {**base, "kategori": kat, "kume": len(rows), "suzgec": info, "tum": tum,
            "sonYillar": {"yillar": years, **son}, "etiket": etiket, "mesaj": mesaj}
