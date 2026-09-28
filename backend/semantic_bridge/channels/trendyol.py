"""M40 Trendyol mağaza yönetimi (ilk sürüm: yalnız okuma + panel dosyası yükleme).

**Kaynaklar**
- Trendyol tarafı yalnız panelden indirilen dosyalardan gelir (`trendyol_import.py`): ürün listesi, siparişler, iadeler,
  müşteri soruları, yorumlar. API'ye istek gönderilmez (`trendyol_client.py` çevrimdışı).
- Toptan satış senaryosu (TİMAŞ'ın Trendyol carisine faturaladığı) M42 kanal karnesinden okunur: cari Cari eşleme
  ekranında Trendyol'a bağlıysa karnede Trendyol satırı vardır; burada yalnız özeti gösterilir, yeniden hesaplanmaz.
- Logo (yalnız okuma, M34 okuyucularıyla aynı tanım): barkod → stok kodu (`UNITBARCODE`), depo stok bakiyesi
  (IOCODE 1,2 − 3,4; planlanan üretim girişi hariç), bugün geçerli liste fiyatı (`PRCLIST` PTYPE 2). Site fiyatı SEO
  eşitlemesinin T-soft kopyasından (T-soft'a gidilmez).

**Hesaplar kuraldır, model rakam üretmez.** Zeki AI yalnız (a) iade nedenini kapalı kümeden seçer (`QueuedLlm.choose`,
kural eşleşmezse), (b) soru/yorum yanıt taslağı yazar (gönderimi insan yapar), (c) vitrin önerisine ve haftalık özete
rakamsız gerekçe yazar. Hiçbir yere gönderim yok; öneriler portal kaydıdır (`semantic_channel_suggestions`).
"""
from __future__ import annotations

import json
import logging
import re
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import platform_common as PC
from semantic_bridge.channels import sources as src
from semantic_bridge.channels import store as S

log = logging.getLogger("semantic.channels.trendyol")

PLATFORM = "trendyol"
_md = sa.MetaData()

IMPORTS = sa.Table(
    "semantic_trendyol_imports", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("tur", sa.String(12), nullable=False),            # urun | siparis | iade | soru | yorum
    sa.Column("dosya_adi", sa.String(300)),
    sa.Column("satir", sa.Integer, nullable=False),
    sa.Column("eslesen", sa.Integer, nullable=False),            # barkodu Logo kitabına bağlanan satır
    sa.Column("kolonlar_json", sa.Text),                         # tanınan / içeri alınmayan kolon adları (değer yok)
    sa.Column("yukleyen", sa.String(120), nullable=False),
    sa.Column("tarih", sa.DateTime(timezone=True), nullable=False),
    sa.Column("hata", sa.Text),
)

#: Son yüklenen ürün listesi (liste bütünüyle değişir: panelin ürün dışa aktarımı mağazanın tamamıdır).
PRODUCTS = sa.Table(
    "semantic_trendyol_products", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("barkod", sa.String(40), primary_key=True),
    sa.Column("satici_stok_kodu", sa.String(80)),
    sa.Column("trendyol_urun_id", sa.String(80)),
    sa.Column("baslik", sa.String(400)),
    sa.Column("satisa_acik", sa.Boolean),                         # None = dosyada durum kolonu yok / tanınmadı
    sa.Column("durum_metni", sa.String(120)),
    sa.Column("stok", sa.Float),
    sa.Column("fiyat", sa.Float),                                 # Trendyol satış fiyatı (KDV dahil)
    sa.Column("piyasa_fiyati", sa.Float),
    sa.Column("kaynak", sa.String(8), nullable=False),            # excel | api
    sa.Column("import_id", sa.String(32)),
    sa.Column("okuma_zamani", sa.DateTime(timezone=True), nullable=False),
)

#: Sipariş/paket satırları; kişisel veri yok (alıcı adı, adres, telefon kolonları içeri alınmaz).
ORDERS = sa.Table(
    "semantic_trendyol_orders", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("paket_id", sa.String(80), primary_key=True),
    sa.Column("barkod", sa.String(40), primary_key=True),
    sa.Column("siparis_no", sa.String(80)),
    sa.Column("siparis_tarihi", sa.DateTime),
    sa.Column("durum", sa.String(120)),
    sa.Column("kargo_firma", sa.String(120)),
    sa.Column("kargo_durum", sa.String(120)),
    sa.Column("termin", sa.DateTime),
    sa.Column("adet", sa.Float),
    sa.Column("tutar", sa.Float),
    sa.Column("urun_adi", sa.String(400)),
    sa.Column("kaynak", sa.String(8), nullable=False),
    sa.Column("import_id", sa.String(32)),
    sa.Column("okuma_zamani", sa.DateTime(timezone=True), nullable=False),
)

CLAIMS = sa.Table(
    "semantic_trendyol_claims", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("talep_id", sa.String(80), primary_key=True),
    sa.Column("barkod", sa.String(40), primary_key=True),
    sa.Column("siparis_no", sa.String(80)),
    sa.Column("adet", sa.Float),
    sa.Column("neden_metni", sa.String(400)),
    sa.Column("aciklama_maskeli", sa.Text),
    sa.Column("neden_sinifi", sa.String(40)),
    sa.Column("olasilik", sa.Float),
    sa.Column("sinif_yontemi", sa.String(12)),                  # kural | zeki | emin-degil
    sa.Column("durum", sa.String(120)),
    sa.Column("tarih", sa.DateTime),
    sa.Column("kaynak", sa.String(8), nullable=False),
    sa.Column("import_id", sa.String(32)),
    sa.Column("okuma_zamani", sa.DateTime(timezone=True), nullable=False),
)

QUESTIONS = sa.Table(
    "semantic_trendyol_questions", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("soru_id", sa.String(80), primary_key=True),
    sa.Column("barkod", sa.String(40)),
    sa.Column("urun_adi", sa.String(400)),
    sa.Column("metin_maskeli", sa.Text),
    sa.Column("cevaplandi", sa.Boolean),                          # None = dosyada cevap/durum kolonu yok
    sa.Column("soru_tarihi", sa.DateTime),
    sa.Column("taslak", sa.Text),
    sa.Column("taslak_yazan", sa.String(120)),
    sa.Column("taslak_zamani", sa.DateTime(timezone=True)),
    sa.Column("kaynak", sa.String(8), nullable=False),
    sa.Column("import_id", sa.String(32)),
    sa.Column("okuma_zamani", sa.DateTime(timezone=True), nullable=False),
)

REVIEWS = sa.Table(
    "semantic_trendyol_reviews", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("yorum_id", sa.String(80), primary_key=True),
    sa.Column("barkod", sa.String(40)),
    sa.Column("urun_adi", sa.String(400)),
    sa.Column("puan", sa.Float),
    sa.Column("metin_maskeli", sa.Text),
    sa.Column("tarih", sa.DateTime),
    sa.Column("taslak", sa.Text),
    sa.Column("taslak_yazan", sa.String(120)),
    sa.Column("taslak_zamani", sa.DateTime(timezone=True)),
    sa.Column("kaynak", sa.String(8), nullable=False),
    sa.Column("import_id", sa.String(32)),
    sa.Column("okuma_zamani", sa.DateTime(timezone=True), nullable=False),
)

#: Logo ve site tarafı (yalnız Trendyol'da geçen kitaplar): depo stoğu, liste fiyatı, site fiyatı. Her okumada değişir.
LOGO = sa.Table(
    "semantic_trendyol_logo", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("depo_stok", sa.Float),
    sa.Column("liste_fiyati", sa.Float),
    sa.Column("liste_kdv_dahil", sa.Boolean),
    sa.Column("site_fiyati", sa.Float),
    sa.Column("site_stok", sa.Float),
)

TABLES = {"urun": PRODUCTS, "siparis": ORDERS, "iade": CLAIMS, "soru": QUESTIONS, "yorum": REVIEWS}
TYPE_LABELS = {"urun": "Ürün listesi", "siparis": "Siparişler", "iade": "İadeler", "soru": "Müşteri soruları", "yorum": "Yorumlar"}

#: İade nedeni kapalı kümesi (analiz §13) ve kural sözcükleri. Kural tek sınıfa düşerse model sorulmaz.
CLAIM_CLASSES = ["Hasarlı ürün", "Yanlış ürün", "Geç teslim", "Baskı hatası", "Vazgeçti", "Diğer"]
CLAIM_RULES: dict[str, tuple[str, ...]] = {
    "Hasarlı ürün": ("hasar", "kirik", "yirtik", "ezik", "islak", "zarar gor", "defolu", "kusurlu"),
    "Yanlış ürün": ("yanlis urun", "farkli urun", "yanlis gonder", "eksik urun", "siparis ettigim urun degil"),
    "Geç teslim": ("gec teslim", "gecikme", "teslim edilmedi", "gec geldi", "gecikti", "zamaninda"),
    "Baskı hatası": ("baski hata", "sayfa eksik", "eksik sayfa", "bos sayfa", "ters basil", "matbaa", "cilt hata", "sayfalar karis"),
    "Vazgeçti": ("vazgec", "istemiyorum", "begenmedim", "fikrim degisti", "ihtiyac kalmadi", "yanlislikla", "cayma"),
}
CLAIM_PROMPT = ("Bir yayınevinin pazar yeri mağazasına gelen iade talebi aşağıda. İadenin nedeni hangi sınıfa girer? "
                "Emin değilsen «Diğer» seç.\n\nPlatformdaki iade nedeni: {neden}\nMüşteri açıklaması (kişisel bilgi "
                "maskelendi): {aciklama}")
REPLY_PROMPT = ("Bir yayınevinin pazar yeri mağazasına gelen {tur} aşağıda. Mağaza adına kısa, nazik, Türkçe bir yanıt "
                "taslağı yaz (2–4 cümle). Stok, fiyat, indirim, kargo ya da teslim tarihi sözü verme; bilmediğin bilgiyi "
                "uydurma; müşteriden kişisel bilgi isteme; rakam yazma. Yalnız yanıt metnini yaz.\n\nKitap: {kitap}\n"
                "{tur_bas}: {metin}{puan}")
SUMMARY_PROMPT = ("Bir yayınevinin Trendyol mağazasının haftalık özeti aşağıda. E-ticaret müdürü için 5–8 cümlelik düz "
                  "Türkçe özet yaz: neye dikkat etmeli, hangi iş öne alınmalı. Rakam, yüzde ya da tutar yazma; rakamlar "
                  "zaten tabloda.\n\n{olgular}")
SHOWCASE_PROMPT = ("Bir yayınevinin Trendyol mağazası için kurala göre seçilmiş vitrin adayları aşağıda (stok derinliği ve "
                   "satış hızı). Pazarlama uzmanı için 2–4 cümlelik gerekçe yaz: neden bu kitaplar, neye dikkat etmeli. "
                   "Rakam yazma.\n\n{olgular}")

_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        S.ensure(engine)
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    """Yönetim → Platform ve kanallar (`TRENDYOL_*`). Hepsi ölçülmemiş başlangıç değeridir."""
    f = lambda k, d: PC.conf_float(conf, k, d)  # noqa: E731
    return {
        "cariAdlari": PC.name_patterns(conf("TRENDYOL_CARI_ADLARI") or "TRENDYOL,DSM GRUP"),
        "minDepo": f("TRENDYOL_MIN_DEPO_STOK", 1.0),
        "maxIndirim": f("TRENDYOL_MAX_INDIRIM", 0.35),
        "listeKdv": f("TRENDYOL_LISTE_KDV", 0.0),
        "vitrinMinStok": f("TRENDYOL_VITRIN_MIN_STOK", 50.0),
        "vitrinGun": int(f("TRENDYOL_VITRIN_GUN", 30.0)),
        "soruSaat": f("TRENDYOL_SORU_SAAT", 24.0),
        "sinifMinProb": f("TRENDYOL_SINIF_MIN_OLASILIK", 0.60),
        "sinifMinMargin": f("TRENDYOL_SINIF_MIN_FARK", 0.20),
        "modelBudgetSec": int(f("CHANNEL_MODEL_BUDGET_SEC", 600.0)),
    }


# ------------------------------------------------------------------ barkod → kitap


class Books:
    """Barkod → stok kodu (Logo `UNITBARCODE`, M42 tablosu) ve kitap adları; Logo/site tarafı (son okuma)."""

    def __init__(self, engine: sa.engine.Engine, tenant: str):
        with engine.connect() as c:
            self.bmap = {r.barkod: r.stok_kodu for r in c.execute(sa.select(S.BARCODES).where(S.BARCODES.c.tenant_id == tenant)).all()}
            self.logo = {r.stok_kodu: r for r in c.execute(sa.select(LOGO).where(LOGO.c.tenant_id == tenant)).all()}
        self.names = S.book_names(engine, tenant)

    def code(self, barkod: Optional[str], satici: Optional[str] = None) -> Optional[str]:
        if barkod and barkod in self.bmap:
            return self.bmap[barkod]
        for x in (barkod, satici):
            if x and (x in self.names or x in self.logo):
                return x
        return None

    def name(self, code: Optional[str], fallback: Optional[str] = None) -> str:
        return (self.names.get(code or "") or fallback or "") if code else (fallback or "")


def all_barcodes(engine: sa.engine.Engine, tenant: str) -> set[str]:
    out: set[str] = set()
    with engine.connect() as c:
        for t in (PRODUCTS, ORDERS, CLAIMS, QUESTIONS, REVIEWS):
            out |= {r[0] for r in c.execute(sa.select(t.c.barkod).where(t.c.tenant_id == tenant, t.c.barkod.isnot(None))).all() if r[0]}
    return out


def refresh_logo(engine: sa.engine.Engine, tenant: str, logo_file: str, conf: Callable[[str], str],
                 step: Callable[[str], None] = lambda s: None, today: Optional[date] = None) -> dict[str, Any]:
    """Logo'dan barkod, depo stoğu, liste fiyatı; SEO kopyasından site fiyatı. Yalnız Trendyol dosyalarında geçen kitaplar."""
    from semantic_bridge import eticaret_sources as E

    ensure(engine)
    today = today or date.today()
    st = settings(conf)
    step("Logo dönemleri")
    run = src.runner(logo_file)
    firms = src.firms_by_year(run)
    latest = firms[max(firms)]
    end = E.read_data_end(run, firms)
    step("Trendyol adlı cariler")
    S.meta_set(engine, tenant, "trendyol:cariler", {"items": PC.read_name_cariler(run, latest, st["cariAdlari"]),
                                                    "desenler": st["cariAdlari"], "firma": latest})
    step("Barkodlar")
    bc = src.read_barcodes(run, latest)
    S.replace_all(engine, tenant, S.BARCODES, [{"barkod": k, "stok_kodu": v} for k, v in bc.items()])
    with engine.connect() as c:
        satici = {r[0] for r in c.execute(sa.select(PRODUCTS.c.satici_stok_kodu).where(PRODUCTS.c.tenant_id == tenant)).all() if r[0]}
    items = set(bc.values())
    codes = {bc[b] for b in all_barcodes(engine, tenant) if b in bc} | (satici & items)
    by_code: dict[str, list[str]] = defaultdict(list)
    for b, cd in bc.items():
        if cd in codes:
            by_code[cd].append(b)
    step("Depo stoğu")
    stock = E.read_stock(run, firms) if codes else {}
    step("Liste fiyatı")
    prices = E.read_prices(run, firms, today) if codes else {}
    step("Kitap adları")
    if codes:
        S.upsert_books(engine, tenant, src.read_item_names(run, latest, set(codes)))
    step("Site fiyatı")
    site: dict[str, dict[str, Any]] = {}
    site_at = None
    try:
        s = E.read_site(engine, tenant)
        site_at = s.get("tsoftAt")
        for p in s["products"]:
            v = E.tsoft_values(p["data"])
            if v.get("barkod"):
                site[v["barkod"]] = v
    except Exception as e:  # noqa: BLE001 — site kopyası yoksa yalnız Logo
        log.info("trendyol: site kopyası okunamadı: %s", e)
    rows = []
    for cd in sorted(codes):
        pr = prices.get(cd) or {}
        sv = next((site[E.ean_key(b)] for b in by_code.get(cd, []) if E.ean_key(b) in site), None)
        rows.append({"stok_kodu": cd, "depo_stok": float(stock.get(cd, 0.0)), "liste_fiyati": pr.get("fiyat"),
                     "liste_kdv_dahil": pr.get("kdvDahil") if pr else None,
                     "site_fiyati": (sv or {}).get("indirimli") or (sv or {}).get("fiyat"), "site_stok": (sv or {}).get("stok")})
    S.replace_all(engine, tenant, LOGO, rows)
    out = {"ok": True, "firm": latest, "kitap": len(rows), "barkod": len(bc), "veriSonu": end.isoformat() if end else None,
           "siteKopyasi": S.iso(site_at) if site_at else None, "siteBagli": bool(site), "listeKdv": st["listeKdv"]}
    S.meta_set(engine, tenant, "trendyol:logo", out)
    return out


# ------------------------------------------------------------------ özet ve listeler


def _rows(engine: sa.engine.Engine, table: sa.Table, tenant: str) -> list[Any]:
    with engine.connect() as c:
        return c.execute(sa.select(table).where(table.c.tenant_id == tenant)).all()


def last_imports(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(sa.select(IMPORTS).where(IMPORTS.c.tenant_id == tenant).order_by(IMPORTS.c.tarih.desc())).all()
    out: dict[str, Any] = {}
    for r in rows:
        if r.tur not in out:
            out[r.tur] = {"id": r.id, "dosya": r.dosya_adi, "satir": r.satir, "tarih": S.iso(r.tarih), "yukleyen": r.yukleyen}
    return out


def _gross(price: Optional[float], kdv_dahil: Optional[bool], kdv: float) -> Optional[float]:
    if price is None:
        return None
    return price if kdv_dahil or not kdv else price * (1 + kdv)


def stock_rows(engine: sa.engine.Engine, tenant: str, st: dict[str, Any]) -> list[dict[str, Any]]:
    """Ürün listesi × depo stoğu. Fark türleri:
    - `trendyolda-var-depoda-yok`: satışa açık (ya da durum bilinmiyor), Trendyol stoğu > 0, depo ≤ 0 (iptal/puan riski)
    - `depoda-var-kapali`: depo ≥ en az depo stoğu ama Trendyol'da kapalı ya da stok 0 (kaçan satış)
    - `trendyol-fazla`: Trendyol stoğu depodan fazla (depo > 0)
    - `eslesmedi`: barkod Logo'da bir kitaba bağlanamadı
    """
    b = Books(engine, tenant)
    out = []
    for r in _rows(engine, PRODUCTS, tenant):
        code = b.code(r.barkod, r.satici_stok_kodu)
        lg = b.logo.get(code) if code else None
        depo = lg.depo_stok if lg is not None else None
        ty = r.stok or 0.0
        acik = r.satisa_acik
        fark = None
        if code is None:
            fark = "eslesmedi"
        elif depo is not None:
            if acik is not False and ty > 0 and depo <= 0:
                fark = "trendyolda-var-depoda-yok"
            elif depo >= st["minDepo"] and (acik is False or ty <= 0):
                fark = "depoda-var-kapali"
            elif depo > 0 and ty > depo:
                fark = "trendyol-fazla"
        out.append({"barkod": r.barkod, "stokKodu": code, "ad": b.name(code, r.baslik), "baslik": r.baslik,
                    "satisaAcik": acik, "durum": r.durum_metni, "trendyolStok": r.stok, "depoStok": depo,
                    "fark": fark, "okundu": S.iso(r.okuma_zamani)})
    return out


STOCK_DIFFS = {"trendyolda-var-depoda-yok": "Trendyol'da satışta, depoda yok", "depoda-var-kapali": "Depoda var, Trendyol'da kapalı",
               "trendyol-fazla": "Trendyol stoğu depodan fazla", "eslesmedi": "Barkod Logo'da bulunamadı"}


def stock_diff(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], fark: str = "", q: str = "", p: int = 0) -> dict[str, Any]:
    rows = stock_rows(engine, tenant, st)
    counts = {k: sum(1 for r in rows if r["fark"] == k) for k in STOCK_DIFFS}
    sel = [r for r in rows if (r["fark"] == fark if fark else r["fark"] is not None)]
    sel = PC.search(sel, q, ("ad", "barkod", "stokKodu"))
    order = list(STOCK_DIFFS)
    sel.sort(key=lambda r: (order.index(r["fark"]) if r["fark"] in order else 9, -(r["trendyolStok"] or 0)))
    return PC.page(sel, p, counts=counts, labels=STOCK_DIFFS, urunSayisi=len(rows), logo=S.meta_get(engine, tenant, "trendyol:logo"))


PRICE_FLAGS = {"esik-alti": "Liste fiyatının eşik altında", "liste-ustu": "Liste fiyatının üstünde",
               "site-ucuz": "Sitede daha ucuz", "maliyet-alti": "Birim maliyetin altında", "liste-yok": "Liste fiyatı yok"}


def price_rows(engine: sa.engine.Engine, tenant: str, st: dict[str, Any],
               unit_costs: Optional[Callable[[list[str]], dict[str, dict[str, Any]]]] = None) -> list[dict[str, Any]]:
    """Trendyol satış fiyatı ↔ Logo liste fiyatı ↔ site fiyatı (hepsi KDV dahil kıyaslanır; liste KDV hariçse
    `TRENDYOL_LISTE_KDV` oranıyla brütlenir, oran 0 ise öyle yazar). Maliyet yalnız M9 sağlayıcısı varsa."""
    b = Books(engine, tenant)
    prods = [r for r in _rows(engine, PRODUCTS, tenant) if r.fiyat is not None]
    codes = sorted({c for c in (b.code(r.barkod, r.satici_stok_kodu) for r in prods) if c})
    costs: dict[str, dict[str, Any]] = {}
    if unit_costs is not None and codes:
        try:
            costs = unit_costs(codes) or {}
        except Exception as e:  # noqa: BLE001
            log.warning("trendyol: birim maliyet okunamadı: %s", e)
    out = []
    for r in prods:
        code = b.code(r.barkod, r.satici_stok_kodu)
        lg = b.logo.get(code) if code else None
        liste = _gross(lg.liste_fiyati, lg.liste_kdv_dahil, st["listeKdv"]) if lg is not None else None
        site = lg.site_fiyati if lg is not None else None
        ind = (1 - r.fiyat / liste) if liste else None
        flags = []
        if liste is None:
            flags.append("liste-yok")
        elif ind is not None and ind > st["maxIndirim"]:
            flags.append("esik-alti")
        elif ind is not None and ind < -0.005:
            flags.append("liste-ustu")
        if site is not None and site < r.fiyat - 0.005:
            flags.append("site-ucuz")
        cost = (costs.get(code) or {}).get("maliyet") if code else None
        if cost is not None and r.fiyat < float(cost):
            flags.append("maliyet-alti")
        out.append({"barkod": r.barkod, "stokKodu": code, "ad": b.name(code, r.baslik), "trendyolFiyat": r.fiyat,
                    "piyasaFiyat": r.piyasa_fiyati, "listeFiyat": liste, "listeKdvDahil": lg.liste_kdv_dahil if lg is not None else None,
                    "siteFiyat": site, "indirim": ind, "siteFarki": (r.fiyat - site) if site is not None else None,
                    "birimMaliyet": float(cost) if cost is not None else None, "isaret": flags})
    return out


def price_diff(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], flag: str = "", q: str = "", p: int = 0,
               unit_costs: Optional[Callable[[list[str]], dict[str, dict[str, Any]]]] = None) -> dict[str, Any]:
    rows = price_rows(engine, tenant, st, unit_costs)
    counts = {k: sum(1 for r in rows if k in r["isaret"]) for k in PRICE_FLAGS}
    sel = [r for r in rows if (flag in r["isaret"] if flag else r["isaret"])]
    sel = PC.search(sel, q, ("ad", "barkod", "stokKodu"))
    sel.sort(key=lambda r: -(r["indirim"] if r["indirim"] is not None else -9))
    return PC.page(sel, p, counts=counts, labels=PRICE_FLAGS, esik=st["maxIndirim"], listeKdv=st["listeKdv"],
                   maliyetBagli=unit_costs is not None, logo=S.meta_get(engine, tenant, "trendyol:logo"))


def products(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], durum: str = "", q: str = "", p: int = 0) -> dict[str, Any]:
    rows = stock_rows(engine, tenant, st)
    if durum == "acik":
        rows = [r for r in rows if r["satisaAcik"] is True]
    elif durum == "kapali":
        rows = [r for r in rows if r["satisaAcik"] is False]
    rows = PC.search(rows, q, ("ad", "barkod", "stokKodu", "baslik"))
    rows.sort(key=lambda r: M.fold(r["ad"]))
    return PC.page(rows, p)


# --- siparişler

_DONE = ("teslim edildi", "iptal", "iade", "kargoya verildi", "kargoda", "tasima durumunda", "teslim")


def _late(r: Any, now: datetime) -> bool:
    d = M.fold(" ".join(x for x in (r.durum, r.kargo_durum) if x))
    return bool(r.termin and r.termin < now and not any(w in d for w in _DONE))


def _between(v: Optional[datetime], bas: Optional[date], bit: Optional[date]) -> bool:
    if bas is None and bit is None:
        return True
    if v is None:
        return False
    return (bas is None or v.date() >= bas) and (bit is None or v.date() <= bit)


def _day(v: str) -> Optional[date]:
    if not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        raise ValueError("Tarih YYYY-AA-GG olmalı.") from None


def orders(engine: sa.engine.Engine, tenant: str, durum: str = "", bas: str = "", bit: str = "", q: str = "", p: int = 0,
           now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or datetime.now()
    b = Books(engine, tenant)
    a, z = _day(bas), _day(bit)
    rows = [r for r in _rows(engine, ORDERS, tenant) if _between(r.siparis_tarihi, a, z)]
    by_status: dict[str, dict[str, float]] = defaultdict(lambda: {"paket": 0, "adet": 0.0, "tutar": 0.0})
    packs: dict[str, set[str]] = defaultdict(set)
    books: dict[str, dict[str, Any]] = {}
    items = []
    late = 0
    for r in rows:
        k = r.durum or "Belirtilmemiş"
        packs[k].add(r.paket_id)
        by_status[k]["adet"] += r.adet or 0
        by_status[k]["tutar"] += r.tutar or 0
        code = b.code(r.barkod)
        g = code or f"barkod:{r.barkod}"
        bk = books.setdefault(g, {"stokKodu": code, "barkod": r.barkod, "ad": b.name(code, r.urun_adi), "adet": 0.0, "tutar": 0.0, "paket": 0})
        bk["adet"] += r.adet or 0
        bk["tutar"] += r.tutar or 0
        bk["paket"] += 1
        is_late = _late(r, now)
        late += is_late
        items.append({"paketId": r.paket_id, "siparisNo": r.siparis_no, "tarih": PC.iso(r.siparis_tarihi), "durum": r.durum,
                      "kargoFirma": r.kargo_firma, "kargoDurum": r.kargo_durum, "termin": PC.iso(r.termin), "gecikti": is_late,
                      "barkod": r.barkod, "stokKodu": code, "ad": b.name(code, r.urun_adi), "adet": r.adet, "tutar": r.tutar})
    for k in by_status:
        by_status[k]["paket"] = len(packs[k])
    if durum == "geciken":
        items = [x for x in items if x["gecikti"]]
    elif durum:
        items = [x for x in items if (x["durum"] or "Belirtilmemiş") == durum]
    items = PC.search(items, q, ("ad", "barkod", "paketId", "siparisNo"))
    items.sort(key=lambda x: x["tarih"] or "", reverse=True)
    top = sorted(books.values(), key=lambda x: -x["adet"])
    return PC.page(items, p, durumlar=dict(sorted(by_status.items(), key=lambda kv: -kv[1]["paket"])), geciken=late,
                   paketSayisi=len({r.paket_id for r in rows}), adet=sum(r.adet or 0 for r in rows),
                   tutar=round(sum(r.tutar or 0 for r in rows), 2), kitaplar=top, aralik=_range(rows, "siparis_tarihi"))


def _range(rows: list[Any], col: str) -> dict[str, Optional[str]]:
    ds = [getattr(r, col) for r in rows if getattr(r, col)]
    return {"bas": PC.iso(min(ds)) if ds else None, "bit": PC.iso(max(ds)) if ds else None}


# --- iadeler


def rule_class(text: str) -> Optional[str]:
    f = M.fold(text)
    hits = [k for k, ws in CLAIM_RULES.items() if any(w in f for w in ws)]
    return hits[0] if len(hits) == 1 else None


def claims(engine: sa.engine.Engine, tenant: str, bas: str = "", bit: str = "", sinif: str = "", q: str = "", p: int = 0) -> dict[str, Any]:
    b = Books(engine, tenant)
    a, z = _day(bas), _day(bit)
    rows = [r for r in _rows(engine, CLAIMS, tenant) if _between(r.tarih, a, z)]
    sold: dict[str, float] = defaultdict(float)
    for o in _rows(engine, ORDERS, tenant):
        if _between(o.siparis_tarihi, a, z):
            sold[o.barkod] += o.adet or 0
    by_class: dict[str, dict[str, float]] = defaultdict(lambda: {"talep": 0, "adet": 0.0})
    by_book: dict[str, dict[str, Any]] = {}
    items = []
    for r in rows:
        cls = r.neden_sinifi or "Sınıflanmadı"
        by_class[cls]["talep"] += 1
        by_class[cls]["adet"] += r.adet or 1
        code = b.code(r.barkod)
        bk = by_book.setdefault(r.barkod, {"barkod": r.barkod, "stokKodu": code, "ad": b.name(code), "iadeAdet": 0.0,
                                            "satisAdet": sold.get(r.barkod, 0.0), "siniflar": defaultdict(int)})
        bk["iadeAdet"] += r.adet or 1
        bk["siniflar"][cls] += 1
        items.append({"talepId": r.talep_id, "barkod": r.barkod, "stokKodu": code, "ad": b.name(code), "adet": r.adet,
                      "neden": r.neden_metni, "aciklama": r.aciklama_maskeli, "sinif": r.neden_sinifi, "olasilik": r.olasilik,
                      "yontem": r.sinif_yontemi, "durum": r.durum, "tarih": PC.iso(r.tarih)})
    books = []
    for bk in by_book.values():
        bk["siniflar"] = dict(bk["siniflar"])
        bk["oran"] = (bk["iadeAdet"] / bk["satisAdet"]) if bk["satisAdet"] else None
        books.append(bk)
    books.sort(key=lambda x: -x["iadeAdet"])
    if sinif:
        items = [x for x in items if (x["sinif"] or "Sınıflanmadı") == sinif]
    items = PC.search(items, q, ("ad", "barkod", "talepId", "neden"))
    items.sort(key=lambda x: x["tarih"] or "", reverse=True)
    return PC.page(items, p, siniflar=dict(sorted(by_class.items(), key=lambda kv: -kv[1]["talep"])), kitaplar=books,
                   sinifsiz=sum(1 for r in rows if not r.neden_sinifi), aralik=_range(rows, "tarih"), kume=CLAIM_CLASSES)


def classify_claims(engine: sa.engine.Engine, tenant: str, llm: Any, st: dict[str, Any], *, budget_sec: Optional[int] = None,
                    force: bool = False) -> dict[str, Any]:
    """Sınıfsız iadeler: önce kural (tek sınıf), sonra Zeki AI kapalı küme; eşik altı «emin-degil» (sınıf boş kalır).
    Süre dolarsa kalan sonraki tura (kayıp yok)."""
    import time

    budget = st["modelBudgetSec"] if budget_sec is None else budget_sec
    t0 = time.monotonic()
    out = {"kural": 0, "zeki": 0, "eminDegil": 0, "kalan": 0, "atlandi": None}
    with engine.connect() as c:
        stmt = sa.select(CLAIMS).where(CLAIMS.c.tenant_id == tenant)
        if not force:
            stmt = stmt.where(CLAIMS.c.sinif_yontemi.is_(None))
        rows = c.execute(stmt).all()
    for r in rows:
        text = " ".join(x for x in (r.neden_metni, r.aciklama_maskeli) if x)
        cls = rule_class(text)
        vals: dict[str, Any]
        if cls:
            vals = {"neden_sinifi": cls, "olasilik": None, "sinif_yontemi": "kural"}
            out["kural"] += 1
        elif not text.strip():
            vals = {"neden_sinifi": "Diğer", "olasilik": None, "sinif_yontemi": "kural"}
            out["kural"] += 1
        elif llm is None or not hasattr(llm, "choose"):
            out["atlandi"] = "model tanımlı değil"
            out["kalan"] += 1
            continue
        elif time.monotonic() - t0 > budget:
            out["kalan"] += 1
            continue
        else:
            try:
                ch = llm.choose(CLAIM_PROMPT.format(neden=r.neden_metni or "-", aciklama=(r.aciklama_maskeli or "-")[:1200]), CLAIM_CLASSES)
            except Exception as e:  # noqa: BLE001
                log.warning("trendyol: iade sınıfı alınamadı: %s", e)
                out["atlandi"] = "model cevap vermedi"
                out["kalan"] += 1
                continue
            if ch.choice and ch.confident(st["sinifMinProb"], min_margin=st["sinifMinMargin"]):
                vals = {"neden_sinifi": ch.choice, "olasilik": ch.probability, "sinif_yontemi": "zeki"}
                out["zeki"] += 1
            else:
                vals = {"neden_sinifi": None, "olasilik": ch.probability, "sinif_yontemi": "emin-degil"}
                out["eminDegil"] += 1
        with engine.begin() as c:
            c.execute(CLAIMS.update().where(CLAIMS.c.tenant_id == tenant, CLAIMS.c.talep_id == r.talep_id, CLAIMS.c.barkod == r.barkod)
                      .values(**vals))
    return out


# --- sorular ve yorumlar


def questions(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], cevapsiz: bool = False, q: str = "", p: int = 0,
              now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or datetime.now()
    b = Books(engine, tenant)
    rows = _rows(engine, QUESTIONS, tenant)
    items = []
    for r in rows:
        code = b.code(r.barkod)
        age = (now - r.soru_tarihi).total_seconds() / 3600 if r.soru_tarihi else None
        items.append({"id": r.soru_id, "barkod": r.barkod, "stokKodu": code, "ad": b.name(code, r.urun_adi), "metin": r.metin_maskeli,
                      "cevaplandi": r.cevaplandi, "tarih": PC.iso(r.soru_tarihi), "saat": round(age, 1) if age is not None else None,
                      "gecikti": bool(r.cevaplandi is False and age is not None and age > st["soruSaat"]),
                      "taslak": r.taslak, "taslakYazan": r.taslak_yazan, "taslakZamani": S.iso(r.taslak_zamani)})
    unanswered = sum(1 for x in items if x["cevaplandi"] is False)
    if cevapsiz:
        items = [x for x in items if x["cevaplandi"] is not True]
    items = PC.search(items, q, ("ad", "barkod", "metin"))
    items.sort(key=lambda x: (x["cevaplandi"] is True, -(x["saat"] or 0)))
    return PC.page(items, p, cevapsiz=unanswered, geciken=sum(1 for x in items if x["gecikti"]), toplam=len(rows),
                   bilinmeyen=sum(1 for r in rows if r.cevaplandi is None), esikSaat=st["soruSaat"])


def reviews(engine: sa.engine.Engine, tenant: str, max_puan: Optional[float] = None, q: str = "", p: int = 0) -> dict[str, Any]:
    b = Books(engine, tenant)
    rows = _rows(engine, REVIEWS, tenant)
    by_book: dict[str, dict[str, Any]] = {}
    items = []
    for r in rows:
        code = b.code(r.barkod)
        g = code or r.barkod or f"ad:{M.fold(r.urun_adi)}"
        bk = by_book.setdefault(g, {"stokKodu": code, "barkod": r.barkod, "ad": b.name(code, r.urun_adi), "yorum": 0, "toplam": 0.0,
                                    "dusuk": 0})
        if r.puan is not None:
            bk["yorum"] += 1
            bk["toplam"] += r.puan
            bk["dusuk"] += r.puan <= 3
        items.append({"id": r.yorum_id, "barkod": r.barkod, "stokKodu": code, "ad": b.name(code, r.urun_adi), "puan": r.puan,
                      "metin": r.metin_maskeli, "tarih": PC.iso(r.tarih), "taslak": r.taslak, "taslakYazan": r.taslak_yazan,
                      "taslakZamani": S.iso(r.taslak_zamani)})
    books = []
    for bk in by_book.values():
        bk["ortalama"] = round(bk.pop("toplam") / bk["yorum"], 2) if bk["yorum"] else None
        books.append(bk)
    books.sort(key=lambda x: (x["ortalama"] if x["ortalama"] is not None else 9, -x["yorum"]))
    if max_puan is not None:
        items = [x for x in items if x["puan"] is not None and x["puan"] <= max_puan]
    items = PC.search(items, q, ("ad", "barkod", "metin"))
    items.sort(key=lambda x: (x["puan"] if x["puan"] is not None else 9, x["tarih"] or ""))
    scored = [r.puan for r in rows if r.puan is not None]
    return PC.page(items, p, kitaplar=books, ortalama=round(sum(scored) / len(scored), 2) if scored else None,
                   dusuk=sum(1 for x in scored if x <= 3), toplam=len(rows))


class DraftError(ValueError):
    pass


def draft_reply(engine: sa.engine.Engine, tenant: str, user: str, llm: Any, kind: str, rid: str) -> dict[str, Any]:
    """Soru ya da yorum için yanıt taslağı. Platforma gönderilmez; kişi kopyalar ve panelden kendisi yanıtlar."""
    from semantic_bridge.marketing import guard

    table, idcol = (QUESTIONS, QUESTIONS.c.soru_id) if kind == "soru" else (REVIEWS, REVIEWS.c.yorum_id)
    with engine.connect() as c:
        r = c.execute(sa.select(table).where(table.c.tenant_id == tenant, idcol == rid)).first()
    if r is None:
        raise DraftError("Kayıt bulunamadı.")
    if not (r.metin_maskeli or "").strip():
        raise DraftError("Metni boş bir kayda taslak yazılmaz.")
    if llm is None:
        raise DraftError("Zeki AI şu an kullanılamıyor.")
    b = Books(engine, tenant)
    code = b.code(r.barkod)
    title = b.name(code, r.urun_adi) or "—"
    puan = f"\nPuan: {r.puan:g} / 5" if kind == "yorum" and getattr(r, "puan", None) is not None else ""
    prompt = REPLY_PROMPT.format(tur="müşteri sorusu" if kind == "soru" else "ürün yorumu", tur_bas="Soru" if kind == "soru" else "Yorum",
                                 kitap=title, metin=r.metin_maskeli[:1500], puan=puan)
    text = (llm.chat([{"role": "user", "content": prompt}], max_tokens=260, temperature=0.3) or "").strip()
    checked = guard.check(text, sources=[r.metin_maskeli, title])
    clean = checked["metin"]
    if not clean:
        raise DraftError("Zeki AI'ın taslağı denetimden geçmedi; yeniden deneyin.")
    with engine.begin() as c:
        c.execute(table.update().where(table.c.tenant_id == tenant, idcol == rid)
                  .values(taslak=clean, taslak_yazan=user, taslak_zamani=S.now()))
    return {"id": rid, "taslak": clean, "dusen": checked["dusenSayisi"], "taslakYazan": user}


# ------------------------------------------------------------------ vitrin önerisi


def _velocity(engine: sa.engine.Engine, tenant: str, b: Books, days: int) -> tuple[dict[str, float], Optional[str]]:
    """Kitap → son `days` günde Trendyol sipariş adedi (iptal durumları hariç). Pencere verideki son sipariş gününe
    göre (dosya eskiyse bugüne göre sıfır çıkmasın)."""
    rows = _rows(engine, ORDERS, tenant)
    ds = [r.siparis_tarihi for r in rows if r.siparis_tarihi]
    if not ds:
        return {}, None
    end = max(ds)
    start = end - timedelta(days=days)
    out: dict[str, float] = defaultdict(float)
    for r in rows:
        if r.siparis_tarihi and r.siparis_tarihi > start and "iptal" not in M.fold(r.durum):
            code = b.code(r.barkod)
            if code:
                out[code] += r.adet or 0
    return dict(out), end.date().isoformat()


def showcase_rows(engine: sa.engine.Engine, tenant: str, st: dict[str, Any]) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Vitrin adayı: depo stoğu ≥ `TRENDYOL_VITRIN_MIN_STOK` ve son `TRENDYOL_VITRIN_GUN` günde Trendyol'da satmış kitap;
    sıra = satış hızı × stoğun kaç haftayı karşıladığı (derin stoklu hızlı kitap önde). Trendyol'da kapalı olan işaretlenir."""
    b = Books(engine, tenant)
    vel, end = _velocity(engine, tenant, b, st["vitrinGun"])
    prods: dict[str, Any] = {}
    for r in _rows(engine, PRODUCTS, tenant):
        code = b.code(r.barkod, r.satici_stok_kodu)
        if code:
            prods[code] = r
    rows = []
    for code, v in vel.items():
        lg = b.logo.get(code)
        depo = lg.depo_stok if lg is not None else None
        if depo is None or depo < st["vitrinMinStok"] or v <= 0:
            continue
        weekly = v / max(1.0, st["vitrinGun"] / 7)
        cover = depo / weekly if weekly else None
        pr = prods.get(code)
        rows.append({"stokKodu": code, "ad": b.name(code), "satis": v, "haftalik": round(weekly, 2), "depoStok": depo,
                     "karsilamaHafta": round(cover, 1) if cover is not None else None,
                     "puan": round(weekly * min(cover or 0, 26), 2),
                     "trendyolAcik": pr.satisa_acik if pr is not None else None, "trendyolStok": pr.stok if pr is not None else None})
    rows.sort(key=lambda x: -x["puan"])
    return rows, end


def showcase(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], q: str = "", p: int = 0) -> dict[str, Any]:
    rows, end = showcase_rows(engine, tenant, st)
    return PC.page(PC.search(rows, q, ("ad", "stokKodu")), p, pencereGun=st["vitrinGun"], veriSonu=end, minStok=st["vitrinMinStok"])


def showcase_suggest(engine: sa.engine.Engine, tenant: str, user: str, st: dict[str, Any], codes: list[str], llm: Any,
                     note: Optional[str]) -> dict[str, Any]:
    from semantic_bridge.marketing import guard

    if not codes:
        raise DraftError("Vitrin önerisi için en az bir kitap seçilmeli.")
    allrows = {r["stokKodu"]: r for r in showcase_rows(engine, tenant, st)[0]}
    picked = [allrows[c] for c in dict.fromkeys(codes) if c in allrows]
    if not picked:
        raise DraftError("Seçilen kitaplar vitrin adayları arasında değil.")
    gerekce = None
    if llm is not None:
        facts = "\n".join(f"- {r['ad']}: depo derin, satış hızı {'yüksek' if r['puan'] >= picked[0]['puan'] / 2 else 'orta'}"
                          + ("; Trendyol'da kapalı" if r["trendyolAcik"] is False else "") for r in picked)
        try:
            text = llm.chat([{"role": "user", "content": SHOWCASE_PROMPT.format(olgular=facts)}], max_tokens=220, temperature=0.2) or ""
            gerekce = guard.check(re.sub(r"[^\n]*\d[^\n]*\n?", "", text), sources=[facts])["metin"] or None
        except Exception as e:  # noqa: BLE001
            log.warning("trendyol: vitrin gerekçesi yazılamadı: %s", e)
    title = f"Trendyol vitrin önerisi: {len(picked)} kitap"
    return S.suggestion_add(engine, tenant, user, PLATFORM, "vitrin", title,
                            {"kitaplar": picked, "not": note, "pencereGun": st["vitrinGun"], "minStok": st["vitrinMinStok"]}, gerekce)


# ------------------------------------------------------------------ haftalık rapor


def weekly(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], bitis: str = "", llm: Any = None,
           now: Optional[datetime] = None) -> dict[str, Any]:
    """Son 7 gün (bitiş verilmezse verideki son sipariş/iade/soru günü). Rakamlar tablolardan; Zeki AI yalnız rakamsız özet."""
    from semantic_bridge.marketing import guard

    now = now or datetime.now()
    end = _day(bitis)
    if end is None:
        ds = [x for t, col in ((ORDERS, "siparis_tarihi"), (CLAIMS, "tarih"), (QUESTIONS, "soru_tarihi"))
              for x in (getattr(r, col) for r in _rows(engine, t, tenant)) if x]
        end = max(ds).date() if ds else now.date()
    start = end - timedelta(days=6)
    a, z = start.isoformat(), end.isoformat()
    o = orders(engine, tenant, bas=a, bit=z, now=now)
    cl = claims(engine, tenant, bas=a, bit=z)
    qs = questions(engine, tenant, st, now=now)
    rv = reviews(engine, tenant)
    week_reviews = [r for r in _rows(engine, REVIEWS, tenant) if r.tarih and a <= r.tarih.date().isoformat() <= z]
    sd = stock_diff(engine, tenant, st)
    out = {
        "bas": a, "bit": z,
        "siparis": {"paket": o["paketSayisi"], "adet": o["adet"], "tutar": o["tutar"], "geciken": o["geciken"],
                    "kitaplar": o["kitaplar"][:20]},
        "iade": {"talep": sum(v["talep"] for v in cl["siniflar"].values()), "siniflar": cl["siniflar"], "kitaplar": cl["kitaplar"][:20]},
        "soru": {"cevapsiz": qs["cevapsiz"], "geciken": qs["geciken"]},
        "yorum": {"hafta": len(week_reviews), "dusuk": sum(1 for r in week_reviews if r.puan is not None and r.puan <= 3), "ortalama": rv["ortalama"]},
        "stokFarki": sd["counts"], "yuklemeler": last_imports(engine, tenant), "ozet": None,
    }
    if llm is not None:
        facts = (f"Paket sayısı {out['siparis']['paket']}, geciken paket {out['siparis']['geciken']}. İade talebi {out['iade']['talep']}; "
                 f"iade sınıfları: {', '.join(k for k in cl['siniflar'])}. Cevapsız soru {qs['cevapsiz']}. Düşük puanlı yorum "
                 f"{out['yorum']['dusuk']}. Stok farkı: " + ", ".join(f"{STOCK_DIFFS[k]} {v}" for k, v in sd["counts"].items() if v))
        try:
            text = llm.chat([{"role": "user", "content": SUMMARY_PROMPT.format(olgular=facts)}], max_tokens=320, temperature=0.2) or ""
            out["ozet"] = guard.check(re.sub(r"[^\n]*\d[^\n]*\n?", "", text), sources=[facts])["metin"] or None
        except Exception as e:  # noqa: BLE001
            log.warning("trendyol: haftalık özet yazılamadı: %s", e)
    return out


def overview(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], wholesale: Optional[dict[str, Any]], now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or datetime.now()
    sd = stock_diff(engine, tenant, st)
    qs = questions(engine, tenant, st, now=now)
    rv = reviews(engine, tenant)
    o = orders(engine, tenant, now=now)
    with engine.connect() as c:
        n_prod = c.execute(sa.select(sa.func.count()).select_from(PRODUCTS).where(PRODUCTS.c.tenant_id == tenant)).scalar() or 0
        n_open = c.execute(sa.select(sa.func.count()).select_from(PRODUCTS).where(PRODUCTS.c.tenant_id == tenant,
                                                                                  PRODUCTS.c.satisa_acik.is_(True))).scalar() or 0
    return {"toptan": wholesale, "yuklemeler": last_imports(engine, tenant), "urun": {"toplam": n_prod, "satistaAcik": n_open},
            "stokFarki": sd["counts"], "stokFarkiEtiket": STOCK_DIFFS, "soru": {"cevapsiz": qs["cevapsiz"], "geciken": qs["geciken"]},
            "yorum": {"ortalama": rv["ortalama"], "dusuk": rv["dusuk"], "toplam": rv["toplam"]},
            "siparis": {"paket": o["paketSayisi"], "geciken": o["geciken"], "aralik": o["aralik"]},
            "logo": S.meta_get(engine, tenant, "trendyol:logo")}
