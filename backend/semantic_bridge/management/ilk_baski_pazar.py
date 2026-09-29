"""M10 İlk baskı — kitap kartında «Pazardaki benzer kitaplar (dağıtımcı kataloğu)»: bağlam bilgisi.

Tahmin TİMAŞ'ın kendi Logo satışından kurulur (`ilk_baski_model`); bu modülün hiçbir sayısı tahmine, öneriye ya da
karar kaydına girmez. Ekran, aynı rafta TİMAŞ dışındaki kitapların kaçıncı baskıda olduğunu ve fiyatını yanında
gösterir.

**Küme:** Başarı Dağıtım kataloğunun son görüntüsünde (`semantic_pazar_dagitim_titles`, kaynak `basari`,
`son_gorulme` = son işlenen görüntü) aynı alt kategori (`kategori` «Üst>Alt» birebir), sayfa sayısı kitabın ±%25'i
(sayfası bilinmeyen başlık girmez; kitabın sayfası yoksa koşul uygulanmaz), TİMAŞ grubu dışı (`timas` = false).

**Kategori:** (1) kullanıcının seçtiği Başarı kategorisi; (2) kitabın kendisi Başarı'da varsa (Logo barkodu ↔ stok
kodu, `semantic_pazar_dagitim_barkod`) oradaki kategorisi; (3) CRM tür(ler)inin Başarı alt kategori adıyla harf
katlamalı birebir eşleşmesi (aynı ad birden çok üst kategoride varsa başlığı en çok olan seçilir, diğerleri aday
olarak döner); (4) hiçbiri yoksa ekran kullanıcıdan Başarı kategorisini seçmesini ister.

**Baskı dağılımı:** Başarı'nın baskı alanı («3. Baskı» → 3) ölçüttür, satış sonucu değil. Son üç basım yılı =
görüntü yılı ve önceki iki yıl. Baskısı yazılmamış başlık ayrı sayılır, oranın paydasına girmez. Başarı'nın basım yılı
katalogdaki baskının yılı olabilir: eski bir kitabın yeni baskısı da bu yıllarda görünebilir (ekran bunu yazar).

**Geçmiş isteyen alanlar:** çıkış endeksi en az iki görüntüden oluşur (`pazar_dagitim.stretch`); ilk yıl çıkış hızı
yeni başlığın ilk görüldüğü görüntüden sonra 12 ay izlenince. Görüntü birikene kadar boş döner, neden boş olduğu yazılır.
Dağıtımcı verisi kitapçılara çıkıştır, okura satış değildir.
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta
from typing import Any, Callable, Optional

import sqlalchemy as sa
from fastapi import Request

from semantic_bridge import pazar_dagitim as D
from semantic_bridge import provenance as PV
from semantic_bridge.management import ilk_baski_model as M

SAYFA_PAY = 0.25     # sayfa aralığı: kitabın sayfası ±%25
YIL_SAYISI = 3       # son üç basım yılı
ILK = 10             # en yüksek baskıdaki rakip kitap sayısı (kullanıcı isteği)

YONTEM = {"secim": "sizin seçiminiz", "kitap_kaydi": "kitabın Başarı kaydından",
          "tur_eslesmesi": "CRM türüyle eşleşti"}

F_KUME = ("Küme = Başarı Dağıtım kataloğunun son görüntüsünde aynı alt kategoride, sayfa sayısı kitabın ±%25'i içinde "
          "olan ve TİMAŞ grubundan olmayan kitaplar (sayfası yazılmamış başlık girmez).")
F_BASKI = ("Baskı dağılımı = kümeden son üç basım yılındaki kitapların Başarı kataloğundaki baskı alanına göre sayımı "
           "(1. baskı, 2. baskı, 3. ve üstü). 2. baskıya ulaşan = en az 2. baskıda olan ÷ baskısı yazılmış kitap; "
           "baskısı yazılmamış kitap ayrı sayılır, paydaya girmez.")
F_FIYAT = "Fiyat medyanı = kümedeki kitapların Başarı liste fiyatlarının ortancası (fiyatı yazılmamış kitap girmez)."
F_ILK = ("En yüksek baskıdaki kitaplar = kümede baskısı yazılmış kitaplar, baskı sayısı büyükten küçüğe, eşitse basım "
         "yılı yeniden eskiye; ilk 10.")

NOTLAR = {
    "baglam": ("Bu bölüm tahmine girmez: ilk baskı önerisi TİMAŞ'ın kendi satışından kurulur. Buradaki sayılar aynı "
               "raftaki başka yayınevlerinin kitaplarını gösterir."),
    "baski": ("Baskı sayısı Başarı kataloğundaki baskı alanıdır; satış adedi değildir. Basım yılı katalogdaki baskının "
              "yılı olabilir, eski bir kitabın yeni baskısı da son yıllarda görünebilir."),
    "cikis": ("Çıkış endeksi dağıtımcı deposundan kitapçılara çıkıştır, okura satış değildir. Kaynak geçmiş tutmaz; "
              "endeks en az iki görüntü birikince oluşur."),
    "ilkYil": ("İlk yıl çıkış hızı, yeni bir başlığın katalogda ilk görüldüğü günden sonraki 12 ayda izlenir; görüntüler "
               "biriktikçe dolacak."),
}


# ================================================================================ yardımcılar


def alt(kategori: Optional[str]) -> str:
    """«Edebiyat>Roman» → «Roman» (tek seviyeli adın kendisi)."""
    s = str(kategori or "")
    return s.split(">", 1)[1].strip() if ">" in s else s.strip()


def son_goruntu(engine: sa.engine.Engine, tenant: str) -> tuple[Optional[date], Optional[str], Optional[date]]:
    """Başarı'nın son işlenen görüntüsü: (tarih, kaynağın kendi damgası, ilk görüntü tarihi)."""
    S = D.SNAPS.c
    with engine.connect() as c:
        rows = c.execute(sa.select(S.tarih, S.kaynak_zamani).where(S.tenant_id == tenant, S.kaynak == "basari")
                         .order_by(S.tarih)).all()
    if not rows:
        return None, None, None
    return rows[-1].tarih, rows[-1].kaynak_zamani, rows[0].tarih


def categories_stmt(tenant: str, tarih: date):
    T = D.TITLES.c
    return (sa.select(T.kategori, sa.func.count().label("baslik"))
            .where(T.tenant_id == tenant, T.kaynak == "basari", T.son_gorulme == tarih, T.timas.is_(False),
                   T.kategori.is_not(None))
            .group_by(T.kategori).order_by(T.kategori))


def categories(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Seçim listesi: Başarı'nın son görüntüsündeki kategoriler ve TİMAŞ dışı başlık sayıları."""
    D.ensure(engine)
    tarih, _, _ = son_goruntu(engine, tenant)
    if tarih is None:
        return {"tarih": None, "items": []}
    with engine.connect() as c:
        rows = c.execute(categories_stmt(tenant, tarih)).all()
    items = [{"kategori": r.kategori, "ust": r.kategori.split(">", 1)[0].strip(), "alt": alt(r.kategori),
              "baslik": int(r.baslik)} for r in rows if r.kategori]
    return {"tarih": tarih.isoformat(), "items": items}


def own_stmt(tenant: str, code: str, tarih: date):
    """Kitabın kendi Başarı kaydı: Logo barkodu ↔ stok kodu eşleşmesi üzerinden, son görüntüde."""
    T, K = D.TITLES.c, D.BARKOD.c
    j = D.TITLES.join(D.BARKOD, sa.and_(K.tenant_id == T.tenant_id, K.barkod == T.barkod))
    return (sa.select(T.kategori, sa.func.count().label("n")).select_from(j)
            .where(T.tenant_id == tenant, T.kaynak == "basari", K.stok_kodu == code, T.son_gorulme == tarih,
                   T.kategori.is_not(None))
            .group_by(T.kategori).order_by(sa.func.count().desc(), T.kategori))


def own_category(engine: sa.engine.Engine, tenant: str, code: str, tarih: date) -> Optional[str]:
    with engine.connect() as c:
        r = c.execute(own_stmt(tenant, code, tarih)).first()
    return r.kategori if r else None


def genre_keys(genre: Optional[str]) -> set[str]:
    """CRM tür metninin karşılaştırma anahtarları: bütünü ve virgül/noktalı virgül/eğik çizgiyle ayrılan parçaları."""
    if not genre:
        return set()
    keys = {M.norm(genre)} | set(M.parts(genre))
    return {k for k in keys if k}


def match_genre(cats: list[dict[str, Any]], genre: Optional[str]) -> list[str]:
    """Başarı alt kategori adı CRM tür(ler)inden biriyle harf katlamalı birebir aynı olan kategoriler; başlığı çok
    olan önce."""
    keys = genre_keys(genre)
    if not keys:
        return []
    hit = [c for c in cats if M.norm(c["alt"]) in keys]
    return [c["kategori"] for c in sorted(hit, key=lambda c: (-c["baslik"], c["kategori"]))]


def page_band(pages: Optional[float]) -> Optional[tuple[float, float]]:
    p = M.num(pages)
    return (p * (1 - SAYFA_PAY), p * (1 + SAYFA_PAY)) if p else None


def cluster_stmt(tenant: str, tarih: date, kategori: str, band: Optional[tuple[float, float]]):
    """Kümenin portal sorgusu (ekranda gösterilen metin bu ifadenin kendisidir)."""
    T = D.TITLES.c
    q = (sa.select(T.barkod, T.ad, T.yazar, T.yayinevi, T.sayfa, T.basim_yili, T.baski_no, T.fiyat)
         .where(T.tenant_id == tenant, T.kaynak == "basari", T.son_gorulme == tarih, T.kategori == kategori,
                T.timas.is_(False)))
    if band:
        q = q.where(T.sayfa >= band[0], T.sayfa <= band[1])
    return q.order_by(T.barkod)


def outflow_stmt(tenant: str, tarih: date, kategori: str, band: Optional[tuple[float, float]], bas: date, son: date):
    """Kümenin barkodlarındaki çıkış toplamı, pencere [bas, son): küme alt sorgu olarak aynı koşullarla."""
    O, T = D.OBS.c, D.TITLES.c
    kume = cluster_stmt(tenant, tarih, kategori, band).with_only_columns(T.barkod).order_by(None)
    return (sa.select(sa.func.coalesce(sa.func.sum(O.cikis), 0).label("cikis"))
            .where(O.tenant_id == tenant, O.kaynak == "basari", O.tarih >= bas, O.tarih < son,
                   O.barkod.in_(kume.scalar_subquery())))


def _ratio(a: int, b: int) -> Optional[float]:
    return round(a / b, 4) if b else None


def distribution(rows: list[Any], yillar: list[int]) -> dict[str, Any]:
    """Son üç basım yılındaki kitapların baskı dağılımı (toplam ve yıl yıl)."""
    def count(sub: list[Any]) -> dict[str, Any]:
        known = [r.baski_no for r in sub if r.baski_no]
        n1 = sum(1 for b in known if b == 1)
        n2 = sum(1 for b in known if b == 2)
        n3 = sum(1 for b in known if b >= 3)
        return {"baslik": len(sub), "bilinen": len(known), "bilinmeyen": len(sub) - len(known),
                "ilk": n1, "ikinci": n2, "ucVeUstu": n3,
                "ikinciyeUlasan": _ratio(n2 + n3, len(known)), "ucuncuyeUlasan": _ratio(n3, len(known))}

    sub = [r for r in rows if r.basim_yili in yillar]
    out = count(sub)
    out["yillar"] = yillar
    out["yilBazinda"] = [{"yil": y, **count([r for r in sub if r.basim_yili == y])} for y in yillar]
    return out


def top(rows: list[Any], n: int = ILK) -> list[dict[str, Any]]:
    known = [r for r in rows if r.baski_no]
    known.sort(key=lambda r: (-r.baski_no, -(r.basim_yili or 0), r.ad or "", r.barkod))
    return [{"barkod": r.barkod, "ad": r.ad, "yazar": r.yazar, "yayinevi": r.yayinevi, "basimYili": r.basim_yili,
             "baski": r.baski_no, "fiyat": r.fiyat, "sayfa": r.sayfa} for r in known[:n]]


# ================================================================================ ana hesap


def similar(engine: sa.engine.Engine, tenant: str, *, code: Optional[str] = None, pages: Optional[float] = None,
            genre: Optional[str] = None, kategori: Optional[str] = None) -> dict[str, Any]:
    """Kitabın kartındaki bölüm. `kategori` verilirse (kullanıcı seçimi) eşleme yapılmaz."""
    D.ensure(engine)
    tarih, damga, ilk_tarih = son_goruntu(engine, tenant)
    band = page_band(pages)
    base: dict[str, Any] = {
        "kaynak": {"ad": D.KAYNAK["basari"], "tarih": tarih.isoformat() if tarih else None, "kaynakZamani": damga,
                   "ilkGoruntu": ilk_tarih.isoformat() if ilk_tarih else None},
        "kosul": {"sayfa": M.num(pages), "sayfaAlt": round(band[0]) if band else None,
                  "sayfaUst": round(band[1]) if band else None, "sayfaPay": SAYFA_PAY, "timasHaric": True},
        "kategori": {"secili": None, "yontem": None, "yontemEtiket": None, "adaylar": [], "tur": genre or None},
        "notlar": NOTLAR,
    }
    if tarih is None:
        return {**base, "durum": "okunmadi"}
    cats = categories(engine, tenant)["items"]
    names = {c["kategori"] for c in cats}
    adaylar = match_genre(cats, genre)
    secili, yontem = None, None
    if kategori:
        if kategori not in names:
            return {**base, "durum": "kategori_yok", "kategori": {**base["kategori"], "adaylar": adaylar,
                                                                   "hata": "Bu kategori Başarı'nın son görüntüsünde yok."}}
        secili, yontem = kategori, "secim"
    elif code and (own := own_category(engine, tenant, code, tarih)) and own in names:
        secili, yontem = own, "kitap_kaydi"
    elif adaylar:
        secili, yontem = adaylar[0], "tur_eslesmesi"
    kat = {**base["kategori"], "secili": secili, "yontem": yontem, "yontemEtiket": YONTEM.get(yontem or ""),
           "adaylar": adaylar}
    if not secili:
        return {**base, "durum": "kategori_yok", "kategori": kat}

    with engine.connect() as c:
        rows = c.execute(cluster_stmt(tenant, tarih, secili, band)).all()
    yillar = list(range(tarih.year - YIL_SAYISI + 1, tarih.year + 1))
    fiyatlar = [r.fiyat for r in rows if r.fiyat and r.fiyat > 0]
    out = {**base, "durum": "hazir", "kategori": kat,
           "kume": {"baslik": len(rows), "fiyatli": len(fiyatlar),
                    "fiyatMedyan": round(statistics.median(fiyatlar), 2) if fiyatlar else None},
           "baskilar": distribution(rows, yillar), "enCokBasilan": top(rows)}

    win = D.stretch(engine, tenant)
    cikis: dict[str, Any] = {"toplam": None, "pencere": None, "not": NOTLAR["cikis"]}
    if win and rows:
        bas, son = win[0] + timedelta(days=1), win[1] + timedelta(days=1)
        with engine.connect() as c:
            total = int(c.execute(outflow_stmt(tenant, tarih, secili, band, bas, son)).scalar() or 0)
        cikis.update({"toplam": total, "pencere": {"bas": win[0].isoformat(), "son": win[1].isoformat()}})
    out["cikis"] = cikis
    out["ilkYilHizi"] = {"deger": None, "not": NOTLAR["ilkYil"]}
    return out


# ================================================================================ sorgu bilgisi


def kaynaklar(engine: sa.engine.Engine, tenant: str, out: dict[str, Any], code: Optional[str] = None) -> Optional[PV.Kaynaklar]:
    if out.get("durum") != "hazir":
        return None
    tarih = date.fromisoformat(out["kaynak"]["tarih"])
    kat = out["kategori"]["secili"]
    k = PV.Kaynaklar(data_end=tarih)
    g = k.sorgu("pazar.dagitim.basari", "Başarı Dağıtım kataloğu", "logo", D.SQL_BASARI,
                description="Başarı'nın güncel kataloğu; her gün okunur, yalnız değişen satır saklanır.")
    kume = k.portal("ilkbaski.pazar.kume", "Benzer kitaplar kümesi",
                    cluster_stmt(tenant, tarih, kat, page_band(out["kosul"]["sayfa"])), engine, origin=[g],
                    rows=out["kume"]["baslik"], data_end=tarih,
                    description="Aynı Başarı alt kategorisi, sayfa ±%25, TİMAŞ grubu dışı; son görüntü.")
    ins = [kume]
    if out["kategori"]["yontem"] == "kitap_kaydi" and code:
        ins.append(k.portal("ilkbaski.pazar.kitap", "Kitabın Başarı kaydı", own_stmt(tenant, code, tarih), engine,
                            origin=[g], description="Kitabın kategorisi: Logo barkodu üzerinden Başarı kaydı."))
    fk = k.hesap("pazarKume", F_KUME, ins)
    k.alanlar({"kosul": fk, "kume.baslik": fk, "kume.fiyatli": k.hesap("pazarFiyat", F_FIYAT, ins),
               "kume.fiyatMedyan": "hesap:pazarFiyat", "baskilar": k.hesap("pazarBaski", F_BASKI, ins),
               "enCokBasilan[]": k.hesap("pazarIlk", F_ILK, ins)})
    pen = (out.get("cikis") or {}).get("pencere")
    if pen:
        bas = date.fromisoformat(pen["bas"]) + timedelta(days=1)
        son = date.fromisoformat(pen["son"]) + timedelta(days=1)
        o = k.portal("ilkbaski.pazar.cikis", "Kümenin depo hareketleri",
                     outflow_stmt(tenant, tarih, kat, page_band(out["kosul"]["sayfa"]), bas, son), engine,
                     origin=[g], description="Görüntüler arası stok düşüşü (çıkış), kümenin barkodlarında.")
        k.alan("cikis", k.hesap("pazarCikis", D.F_CIKIS, [kume, o]))
    return k


# ================================================================================ uçlar


def register(app: Any, prefix: str, gate: Callable, db: Callable, book_of: Callable[[str], Any]) -> None:
    """`db()` → (engine, tenant); `book_of(kod)` → önbellekteki kitap kartı ya da None (model hazır değilse de None)."""

    @app.get(prefix + "/market")
    def fp_market(request: Request, code: str = "", pages: str = "", genre: str = "", kategori: str = "") -> dict[str, Any]:
        gate(request)
        engine, tenant = db()
        b = book_of(code) if code else None
        pg = M.num(pages) or (b.pages if b is not None else None)
        gn = genre.strip() or (b.genre_text if b is not None else "") or None
        out = similar(engine, tenant, code=code or None, pages=pg, genre=gn, kategori=kategori.strip() or None)
        return PV.bagla(out, lambda: kaynaklar(engine, tenant, out, code or None))

    @app.get(prefix + "/market/categories")
    def fp_market_categories(request: Request) -> dict[str, Any]:
        gate(request)
        engine, tenant = db()
        return categories(engine, tenant)
