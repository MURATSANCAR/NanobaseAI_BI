"""Aşama 1 — pazar yeri satış/iade mutabakatı ve hakediş (Trendyol, Amazon TR). Kullanıcı kararı 2026-09-29.

**Ne karşılaştırılır:** panel dosyasındaki sipariş/iade satırları (Trendyol: M40 sipariş ve iade dosyaları; Amazon:
`pazaryeri_dosya` sipariş/iade raporu) ↔ Logo faturalı satış (TRCODE 7, 8, 9) ve iade (2, 3) faturaları. Hakediş
dosyası satırları (satış, iade, komisyon, kargo, hizmet bedeli, stopaj, reklam, ceza, ödeme) ↔ Logo'daki kesinti
faturası (Aşama 0'ın bulduğu yol: pazar yeri carisinden alınan hizmet faturası; ekstredeki belge numarasıyla da aranır)
ve pazar yeri carilerinin fatura dışı alacak hareketleri (tahsilat).

**Eşleme anahtarı veriden bulunur (statik alan varsayımı yok):** okuma, panel dosyalarının tarih aralığındaki (± Yönetim
ayarı `MUTABAKAT_TOLERANS_GUN`) bütün faturaların belge alanlarını (FICHENO, DOCODE, SPECODE, CYPHCODE, GENEXP1–4,
DOCTRACKINGNR) bellekte tarar; panel sipariş numarası hangi alanda geçiyorsa o fatura o siparişe bağlanır ve alan başına
isabet sayısı ekranda yazar. Alan metni portala yazılmaz (kişisel veri olabilir); yalnız eşleşen fatura kimliği, türü,
tarihi, tutarı, cari kodu ve eşleşen alanın adı yazılır. Hiçbir sipariş numarası Logo'da bulunmazsa ve pazar yeri carisi
varsa ikinci yol «barkod + gün + adet»tir (tutar karşılaştırılmaz: Logo satırı KDV hariç).

**Sınıflar:** eşleşti, tutar farkı (panel tutarı ↔ fatura NETTOTAL, KDV dahil; eşik `MUTABAKAT_TUTAR_TOLERANS`), eksik
fatura (faturası beklenen sipariş/iade Logo'da yok), fazla fatura (iptal siparişe fatura, bir siparişe birden çok
fatura ya da pazar yeri carisine kesilip panelde karşılığı olmayan fatura), bekliyor (durum henüz fatura gerektirmiyor),
iptal. Durum sınıfı panelin durum metninden kuralla.

Rakamı SQL ve dosya üretir; model kullanılmaz. Platforma, Logo'ya, CRM'e yazılmaz.
"""
from __future__ import annotations

import logging
import re
import threading
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import pazaryeri_dosya as PD
from semantic_bridge.channels import pazaryeri_model as PM
from semantic_bridge.channels import platform_common as PC
from semantic_bridge.channels import sources as src
from semantic_bridge.channels import store as S

log = logging.getLogger("semantic.channels.mutabakat")

_md = sa.MetaData()
LOGO_INV = sa.Table(
    "semantic_mp_logo_invoices", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("platform", sa.String(20), primary_key=True),
    sa.Column("firma", sa.String(8), primary_key=True),
    sa.Column("ref", sa.Integer, primary_key=True),
    sa.Column("tur", sa.Integer, nullable=False),
    sa.Column("tarih", sa.DateTime),
    sa.Column("tutar", sa.Float),                                  # NETTOTAL (KDV dahil)
    sa.Column("cari", sa.String(80)),
    sa.Column("kanal", sa.String(60)),
    sa.Column("anahtar", sa.String(80)),                           # eşleşen panel sipariş / belge numarası
    sa.Column("alan", sa.String(20)),                              # eşleşen belge alanının adı
    sa.Column("eslesme", sa.String(8), nullable=False),            # siparis | belge | cari
    sa.Column("platform_carisi", sa.Boolean, nullable=False),
)
LOGO_LINES = sa.Table(
    "semantic_mp_logo_lines", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("platform", sa.String(20), primary_key=True),
    sa.Column("firma", sa.String(8), primary_key=True),
    sa.Column("fatura_ref", sa.Integer, primary_key=True),
    sa.Column("sira", sa.Integer, primary_key=True),
    sa.Column("satir_turu", sa.Integer, nullable=False),           # 0 malzeme | 4 hizmet
    sa.Column("stok_kodu", sa.String(60)),
    sa.Column("hizmet_kodu", sa.String(60)),
    sa.Column("hizmet", sa.String(200)),
    sa.Column("adet", sa.Float),
    sa.Column("tutar", sa.Float),                                  # LINENET (KDV hariç)
)
LOGO_CASH = sa.Table(
    "semantic_mp_logo_cash", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("platform", sa.String(20), primary_key=True),
    sa.Column("cari", sa.String(80), primary_key=True),
    sa.Column("modul", sa.Integer, primary_key=True),
    sa.Column("tur", sa.Integer, primary_key=True),
    sa.Column("yon", sa.Integer, primary_key=True),
    sa.Column("tarih", sa.Date, primary_key=True),
    sa.Column("hareket", sa.Integer, nullable=False),
    sa.Column("tutar", sa.Float, nullable=False),
)

SALES, RETURNS, PURCHASE = (7, 8, 9), (2, 3), (1, 4)
FIELDS = ("ficheno", "docode", "specode", "cyphcode", "genexp1", "genexp2", "genexp3", "genexp4", "doctrackingnr")
CLASSES = {"eslesti": "Eşleşti", "tutar-farki": "Tutar farkı", "eksik-fatura": "Eksik fatura (Logo'da yok)",
           "fazla-fatura": "Fazla fatura (panelde yok)", "bekliyor": "Henüz fatura beklenmiyor", "iptal": "İptal"}
TURLER = {"satis": "Satış", "iade": "İade"}

_ready: set[int] = set()
_lock = threading.Lock()


class MutabakatError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        PD.ensure(engine)
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


def koken(platform: str) -> str:
    return f"mutabakat.{platform}"


def meta_key(platform: str) -> str:
    return f"mutabakat:{platform}"


# ------------------------------------------------------------------ anahtar


def norm(v: Any) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(v or "").upper())


def key_forms(v: Any) -> set[str]:
    """Bir numaranın karşılaştırma biçimleri: harf-rakam (ayırıcısız) ve yalnız rakam (en az 6 hane)."""
    n = norm(v)
    out = {n} if len(n) >= 6 else set()
    d = re.sub(r"\D", "", n)
    if len(d) >= 6:
        out.add(d)
    return out


def tokens(v: Any) -> set[str]:
    out: set[str] = set()
    for t in re.findall(r"[0-9A-Za-z][0-9A-Za-z\-_/.]*", str(v or "")):
        out |= key_forms(t)
    return out


# ------------------------------------------------------------------ panel tarafı


def _sinif(tur: str, text: Any) -> str:
    f = M.fold(text)
    if not f:
        return "beklenir"
    if tur == "satis":
        if re.search(r"iptal|cancel", f):
            return "iptal"
        if re.search(r"\byeni\b|hazirlan|olusturul|pending|unshipped|beklemede|onay bekl|created|awaiting", f):
            return "bekliyor"
        return "beklenir"
    if re.search(r"\bred\b|reddedil|rejected|iptal|cancel|itiraz", f):
        return "iptal"
    if re.search(r"bekl|olusturul|incelen|pending|waiting|yolda|in transit", f):
        return "bekliyor"
    return "beklenir"


def panel_orders(engine: sa.engine.Engine, tenant: str, platform: str) -> list[dict[str, Any]]:
    """Panel siparişleri ve iadeleri, sipariş numarası başına: {no, tur, tarih, durum, sinif, adet, tutar, satirlar}."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    def add(tur: str, no: Optional[str], tarih: Optional[datetime], durum: Optional[str], barkod: Optional[str],
            sku: Optional[str], adet: Optional[float], tutar: Optional[float]) -> None:
        if not no:
            return
        g = groups.setdefault((tur, no), {"no": no, "tur": tur, "tarih": None, "durum": None, "adet": 0.0, "tutar": None, "satirlar": []})
        if tarih and (g["tarih"] is None or tarih < g["tarih"]):
            g["tarih"] = tarih
        g["durum"] = g["durum"] or durum
        g["adet"] += adet or 0.0
        if tutar is not None:
            g["tutar"] = (g["tutar"] or 0.0) + tutar
        g["satirlar"].append({"barkod": barkod, "sku": sku, "adet": adet or 0.0, "tutar": tutar})

    if platform == "trendyol":
        from semantic_bridge.channels import trendyol as T

        T.ensure(engine)
        with engine.connect() as c:
            for r in c.execute(sa.select(T.ORDERS).where(T.ORDERS.c.tenant_id == tenant)).all():
                add("satis", r.siparis_no or r.paket_id, r.siparis_tarihi, r.durum, r.barkod, None, r.adet, r.tutar)
            for r in c.execute(sa.select(T.CLAIMS).where(T.CLAIMS.c.tenant_id == tenant)).all():
                add("iade", r.siparis_no or r.talep_id, r.tarih, r.durum, r.barkod, None, r.adet, None)
    else:
        for r in PD.order_rows(engine, tenant, platform):
            add(r.tur, r.siparis_no, r.tarih, r.durum, r.barkod, r.sku, r.adet, r.tutar)
    out = list(groups.values())
    for g in out:
        g["sinif"] = _sinif(g["tur"], g["durum"])
    return out


# ------------------------------------------------------------------ Logo okuması


def refresh(engine: sa.engine.Engine, tenant: str, platform: str, logo_file: str, conf: Callable[[str], str],
            step: Callable[[str], None] = lambda s: None) -> dict[str, Any]:
    from semantic_bridge import sorgu_yakala as Y

    if platform not in PM.PLATFORMS:
        raise MutabakatError("Bilinmeyen platform.")
    ensure(engine)
    q, token = Y.baslat(engine)
    try:
        out = _read(engine, tenant, platform, logo_file, conf, step)
    finally:
        Y.bitir(token)
    Y.koken_yaz(engine, tenant, koken(platform), q)
    return out


def _dates(orders: list[dict[str, Any]], settle: list[Any]) -> list[date]:
    ds = [o["tarih"].date() for o in orders if o["tarih"]]
    for r in settle:
        for v in (r.tarih, r.odeme_tarihi):
            if v:
                ds.append(v.date())
    return ds


def _read(engine: sa.engine.Engine, tenant: str, platform: str, logo_file: str, conf: Callable[[str], str],
          step: Callable[[str], None]) -> dict[str, Any]:
    from semantic_bridge import corporate_sales_sources as CS
    from semantic_bridge import sorgu_yakala as Y

    st = PM.settings(conf)
    orders = panel_orders(engine, tenant, platform)
    settle = PD.settlement_rows(engine, tenant, platform)
    ds = _dates(orders, settle)
    if not ds:
        raise MutabakatError("Önce panel dosyası yükleyin: sipariş, iade ya da hakediş dosyası olmadan Logo'da neyin aranacağı "
                             "bilinmez.", 409)
    a = min(ds) - timedelta(days=st["toleransGun"])
    b = max(ds) + timedelta(days=st["toleransGun"] + 1)
    order_keys: dict[str, str] = {}
    for o in orders:
        for k in key_forms(o["no"]):
            order_keys.setdefault(k, o["no"])
    for r in settle:
        for k in key_forms(r.siparis_no):
            order_keys.setdefault(k, r.siparis_no)
    doc_keys: dict[str, str] = {}
    for r in settle:
        for k in key_forms(r.belge_no):
            doc_keys.setdefault(k, r.belge_no)
    run = Y.izle(src.runner(logo_file), "logo", Y.db_of(logo_file))
    step("Logo dönemleri")
    firms = src.firms_by_year(run)
    step("Pazar yeri carileri")
    cards = PM.discover(run, engine, tenant, platform, conf,
                        [firms[y] for y in range(a.year, b.year + 1) if y in firms])
    codes = set(PM.counted(cards))
    inv: list[dict[str, Any]] = []
    hits: Counter = Counter()
    for firm, x, y in CS.firm_ranges(firms, a, b):
        step(f"Faturalar {x.isoformat()} – {y.isoformat()}")
        for r in run(src._fill("mp_m_fatura", firm=firm, bas=x.isoformat(), bit=y.isoformat())):
            tur = PM._i(r.get("tur"))
            cari = PC.cell(r.get("cari"), 80)
            keys = doc_keys if tur in PURCHASE else order_keys
            found, alan = None, None
            if keys:
                for f in FIELDS:
                    common = tokens(r.get(f)) & keys.keys()
                    if common:
                        found, alan = keys[sorted(common)[0]], f
                        break
            pc = cari in codes
            if not found and not pc:
                continue
            if found:
                hits[f"{'belge' if tur in PURCHASE else 'siparis'}:{alan}"] += 1
            inv.append({"firma": firm, "ref": PM._i(r.get("ref")), "tur": tur, "tarih": PC.when(r.get("tarih")),
                        "tutar": src._f(r.get("tutar")), "cari": cari, "kanal": PC.cell(r.get("kanal"), 60) or None,
                        "anahtar": found, "alan": alan.upper() if alan else None,
                        "eslesme": ("belge" if tur in PURCHASE else "siparis") if found else "cari", "platform_carisi": pc})
    lines: list[dict[str, Any]] = []
    by_firm: dict[str, list[int]] = defaultdict(list)
    for i in inv:
        by_firm[i["firma"]].append(i["ref"])
    for firm, refs in by_firm.items():
        step("Fatura satırları")
        seq: Counter = Counter()
        for part in (refs[i:i + src.IN_CHUNK] for i in range(0, len(refs), src.IN_CHUNK)):
            for r in run(src._fill("mp_m_satir", firm=firm, refs=", ".join(str(x) for x in part))):
                ref = PM._i(r.get("fatura"))
                seq[ref] += 1
                lines.append({"firma": firm, "fatura_ref": ref, "sira": seq[ref], "satir_turu": PM._i(r.get("satir_turu")),
                              "stok_kodu": PC.cell(r.get("stok_kodu"), 60) or None, "hizmet_kodu": PC.cell(r.get("hizmet_kodu"), 60) or None,
                              "hizmet": PC.cell(r.get("hizmet"), 200) or None, "adet": src._f(r.get("adet")), "tutar": src._f(r.get("tutar"))})
    cash: list[dict[str, Any]] = []
    if codes:
        clist = sorted(codes)
        for firm, x, y in CS.firm_ranges(firms, a, b):
            step("Tahsilat hareketleri")
            for part in (clist[i:i + src.IN_CHUNK] for i in range(0, len(clist), src.IN_CHUNK)):
                for r in run(src._fill("mp_m_tahsilat", firm=firm, bas=x.isoformat(), bit=y.isoformat(), codes=src._in(part))):
                    t = PC.when(r.get("tarih"))
                    if t is None:
                        continue
                    cash.append({"cari": PC.cell(r.get("cari"), 80), "modul": PM._i(r.get("modul")), "tur": PM._i(r.get("tur")),
                                 "yon": PM._i(r.get("yon")), "tarih": t.date(), "hareket": PM._i(r.get("hareket")),
                                 "tutar": src._f(r.get("tutar"))})
    with engine.begin() as c:
        for t, rows in ((LOGO_INV, inv), (LOGO_LINES, lines), (LOGO_CASH, _merge_cash(cash))):
            c.execute(t.delete().where(t.c.tenant_id == tenant, t.c.platform == platform))
            for i in range(0, len(rows), 2000):
                c.execute(t.insert(), [{**r, "tenant_id": tenant, "platform": platform} for r in rows[i:i + 2000]])
    out = {"ok": True, "bas": a.isoformat(), "bit": (b - timedelta(days=1)).isoformat(), "toleransGun": st["toleransGun"],
           "panelSiparis": len({o["no"] for o in orders}), "anahtarSayisi": len(order_keys), "belgeAnahtari": len(doc_keys),
           "alanIsabeti": dict(hits), "fatura": len(inv), "satir": len(lines), "tahsilat": len(cash),
           "pazarYeriCarileri": [cards[c] for c in sorted(codes)]}
    S.meta_set(engine, tenant, meta_key(platform), out)
    return out


def _merge_cash(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agg: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        k = (r["cari"], r["modul"], r["tur"], r["yon"], r["tarih"])
        a = agg.setdefault(k, {**r, "hareket": 0, "tutar": 0.0})
        a["hareket"] += r["hareket"]
        a["tutar"] += r["tutar"]
    return list(agg.values())


# ------------------------------------------------------------------ eşleştirme


def _inv_view(i: Any) -> dict[str, Any]:
    return {"ref": i.ref, "firma": i.firma, "tur": i.tur, "turAd": PM.label(PM.FATURA_TURU, i.tur), "tarih": PC.iso(i.tarih),
            "tutar": i.tutar, "cari": i.cari, "alan": i.alan}


def _month(v: Optional[datetime]) -> str:
    return v.strftime("%Y-%m") if v else "tarihsiz"


def reconcile(engine: sa.engine.Engine, tenant: str, platform: str, conf: Callable[[str], str]) -> dict[str, Any]:
    """Bütün eşleştirme (her istekte portal tablolarından; Logo'ya gidilmez)."""
    ensure(engine)
    st = PM.settings(conf)
    meta = S.meta_get(engine, tenant, meta_key(platform))
    orders = panel_orders(engine, tenant, platform)
    with engine.connect() as c:
        invs = c.execute(sa.select(LOGO_INV).where(LOGO_INV.c.tenant_id == tenant, LOGO_INV.c.platform == platform)).all()
        lines = c.execute(sa.select(LOGO_LINES).where(LOGO_LINES.c.tenant_id == tenant, LOGO_LINES.c.platform == platform)).all()
    by_key: dict[str, list[Any]] = defaultdict(list)
    for i in invs:
        if i.eslesme == "siparis" and i.anahtar:
            by_key[i.anahtar].append(i)
    keyed = bool(by_key)
    has_cari = any(i.platform_carisi for i in invs)
    method = "siparis-no" if keyed else ("barkod-gun-adet" if has_cari and meta else None)
    items: list[dict[str, Any]] = []
    used: set[tuple[str, int]] = set()
    tol = st["tutarTolerans"]
    if method == "barkod-gun-adet":
        items, used = _by_barcode(engine, tenant, orders, invs, lines, st)
    else:
        for o in orders:
            want = SALES if o["tur"] == "satis" else RETURNS
            found = [i for i in by_key.get(o["no"], []) if i.tur in want]
            base = {"tur": o["tur"], "siparisNo": o["no"], "tarih": PC.iso(o["tarih"]), "durum": o["durum"], "panelAdet": o["adet"],
                    "panelTutar": round(o["tutar"], 2) if o["tutar"] is not None else None, "yontem": method}
            for i in found:
                used.add((i.firma, i.ref))
            logo = round(sum(i.tutar or 0 for i in found), 2) if found else None
            view = [_inv_view(i) for i in found]
            if o["sinif"] == "iptal":
                sinif, neden = ("fazla-fatura", "Panelde iptal edilmiş siparişe/iadeye Logo'da fatura var.") if found else ("iptal", None)
            elif not found:
                sinif = "eksik-fatura" if o["sinif"] == "beklenir" and meta else "bekliyor"
                neden = (("Logo okuması yapılmadı." if not meta else None) if o["sinif"] == "beklenir"
                         else "Panel durumu henüz fatura gerektirmiyor.")
            elif o["tutar"] is None:
                sinif, neden = "eslesti", "Panel dosyasında tutar yok; yalnız varlık karşılaştırıldı."
            elif abs(o["tutar"] - logo) <= tol:
                sinif, neden = "eslesti", ("Siparişe birden çok fatura; toplamı tutuyor." if len(found) > 1 else None)
            elif len(found) > 1 and logo > o["tutar"] + tol:
                sinif, neden = "fazla-fatura", f"Aynı siparişe {len(found)} fatura; toplam panel tutarından fazla."
            else:
                sinif, neden = "tutar-farki", None
            items.append({**base, "sinif": sinif, "neden": neden, "logoTutar": logo,
                          "fark": round(o["tutar"] - logo, 2) if o["tutar"] is not None and logo is not None else None,
                          "faturalar": view})
        if keyed or has_cari:
            for i in invs:
                if i.eslesme == "belge" or (i.firma, i.ref) in used or i.tur not in SALES + RETURNS:
                    continue
                if i.eslesme == "siparis" or i.platform_carisi:
                    items.append({"tur": "satis" if i.tur in SALES else "iade", "siparisNo": i.anahtar, "tarih": PC.iso(i.tarih),
                                  "durum": None, "panelAdet": None, "panelTutar": None, "yontem": method, "sinif": "fazla-fatura",
                                  "neden": ("Faturadaki sipariş numarasının panelde bu türde karşılığı yok." if i.anahtar
                                            else "Pazar yeri carisine kesilmiş; panel dosyalarında karşılığı bulunamadı."),
                                  "logoTutar": i.tutar, "fark": None, "faturalar": [_inv_view(i)]})
    counts = {t: {k: 0 for k in CLASSES} for t in TURLER}
    amounts = {t: {k: 0.0 for k in CLASSES} for t in TURLER}
    for x in items:
        counts[x["tur"]][x["sinif"]] += 1
        amounts[x["tur"]][x["sinif"]] += (x["panelTutar"] if x["panelTutar"] is not None else (x["logoTutar"] or 0.0))
    return {"okundu": bool(meta), "okuma": meta or None, "yontem": method, "items": items, "counts": counts,
            "amounts": {t: {k: round(v, 2) for k, v in d.items()} for t, d in amounts.items()}}


def _by_barcode(engine: sa.engine.Engine, tenant: str, orders: list[dict[str, Any]], invs: list[Any], lines: list[Any],
                st: dict[str, Any]) -> tuple[list[dict[str, Any]], set[tuple[str, int]]]:
    """İkinci yol: sipariş numarası Logo'da hiç bulunmadıysa pazar yeri carisinin fatura satırıyla barkod (→ stok kodu) +
    gün (± tolerans) + adet. Tutar karşılaştırılmaz (Logo satırı KDV hariç)."""
    with engine.connect() as c:
        bmap = {r.barkod: r.stok_kodu for r in c.execute(sa.select(S.BARCODES).where(S.BARCODES.c.tenant_id == tenant)).all()}
    inv_of = {(i.firma, i.ref): i for i in invs if i.platform_carisi and i.tur in SALES + RETURNS}
    pool: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for ln in lines:
        i = inv_of.get((ln.firma, ln.fatura_ref))
        if i is None or ln.satir_turu != 0 or not ln.stok_kodu:
            continue
        pool[("satis" if i.tur in SALES else "iade", ln.stok_kodu)].append({"inv": i, "adet": ln.adet, "used": False})
    tol = timedelta(days=st["toleransGun"])
    items: list[dict[str, Any]] = []
    used_inv: set[tuple[str, int]] = set()
    for o in orders:
        base = {"tur": o["tur"], "siparisNo": o["no"], "tarih": PC.iso(o["tarih"]), "durum": o["durum"], "panelAdet": o["adet"],
                "panelTutar": round(o["tutar"], 2) if o["tutar"] is not None else None, "yontem": "barkod-gun-adet",
                "logoTutar": None, "fark": None}
        if o["sinif"] != "beklenir":
            items.append({**base, "sinif": "iptal" if o["sinif"] == "iptal" else "bekliyor", "neden": None, "faturalar": []})
            continue
        got: list[Any] = []
        ok = True
        for s in o["satirlar"]:
            code = bmap.get(s["barkod"] or "") or s["sku"] or s["barkod"]
            cands = [p for p in pool.get((o["tur"], code or ""), []) if not p["used"] and abs(p["adet"] - s["adet"]) < 1e-6
                     and o["tarih"] is not None and p["inv"].tarih is not None and abs(p["inv"].tarih - o["tarih"]) <= tol]
            if not cands:
                ok = False
                continue
            best = min(cands, key=lambda p: abs(p["inv"].tarih - o["tarih"]))
            best["used"] = True
            got.append(best["inv"])
        for i in got:
            used_inv.add((i.firma, i.ref))
        view = [_inv_view(i) for i in {(i.firma, i.ref): i for i in got}.values()]
        if ok and got:
            items.append({**base, "sinif": "eslesti", "neden": "Barkod + gün + adet ile; tutar karşılaştırılmadı.", "faturalar": view})
        else:
            items.append({**base, "sinif": "eksik-fatura", "neden": "Pazar yeri carisinin faturalarında aynı kitap, adet ve gün yok"
                          + (" (bazı satırlar eşleşti)." if got else "."), "faturalar": view})
    for key, i in inv_of.items():
        if key in used_inv:
            continue
        items.append({"tur": "satis" if i.tur in SALES else "iade", "siparisNo": None, "tarih": PC.iso(i.tarih), "durum": None,
                      "panelAdet": None, "panelTutar": None, "yontem": "barkod-gun-adet", "sinif": "fazla-fatura",
                      "neden": "Pazar yeri carisine kesilmiş; panelde aynı kitap, adet ve gün bulunamadı.", "logoTutar": i.tutar,
                      "fark": None, "faturalar": [_inv_view(i)]})
    return items, used_inv


def overview(engine: sa.engine.Engine, tenant: str, platform: str, conf: Callable[[str], str]) -> dict[str, Any]:
    """Dönem özeti: ay başına panel ↔ Logo ve sınıf sayıları; eşleme anahtarının hangi alanda bulunduğu."""
    r = reconcile(engine, tenant, platform, conf)
    months: dict[str, dict[str, Any]] = {}
    for x in r["items"]:
        m = months.setdefault(x["tarih"][:7] if x["tarih"] else "tarihsiz", {
            "ay": x["tarih"][:7] if x["tarih"] else "tarihsiz", "panelSatis": 0, "panelSatisTutar": 0.0, "panelIade": 0,
            "logoSatisTutar": 0.0, "logoIadeTutar": 0.0, "eslesti": 0, "tutarFarki": 0, "farkToplam": 0.0, "eksik": 0,
            "eksikTutar": 0.0, "fazla": 0, "fazlaTutar": 0.0})
        if x["panelAdet"] is not None:
            if x["tur"] == "satis":
                m["panelSatis"] += 1
                m["panelSatisTutar"] += x["panelTutar"] or 0.0
            else:
                m["panelIade"] += 1
        if x["logoTutar"] is not None:
            m["logoSatisTutar" if x["tur"] == "satis" else "logoIadeTutar"] += x["logoTutar"]
        if x["sinif"] == "eslesti":
            m["eslesti"] += 1
        elif x["sinif"] == "tutar-farki":
            m["tutarFarki"] += 1
            m["farkToplam"] += x["fark"] or 0.0
        elif x["sinif"] == "eksik-fatura":
            m["eksik"] += 1
            m["eksikTutar"] += x["panelTutar"] or 0.0
        elif x["sinif"] == "fazla-fatura":
            m["fazla"] += 1
            m["fazlaTutar"] += x["logoTutar"] or 0.0
    aylik = [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in m.items()} for _, m in sorted(months.items())]
    okuma = r["okuma"] or {}
    return {"okundu": r["okundu"], "yontem": r["yontem"], "counts": r["counts"], "amounts": r["amounts"], "aylik": aylik,
            "siniflar": CLASSES, "turler": TURLER, "okuma": {k: okuma.get(k) for k in ("bas", "bit", "toleransGun", "panelSiparis",
                                                                                       "fatura", "alanIsabeti", "_at")} if okuma else None,
            "panelSiparis": len({(x["tur"], x["siparisNo"]) for x in r["items"] if x["panelAdet"] is not None})}


def items(engine: sa.engine.Engine, tenant: str, platform: str, conf: Callable[[str], str], tur: str = "", sinif: str = "",
          q: str = "", p: int = 0) -> dict[str, Any]:
    r = reconcile(engine, tenant, platform, conf)
    rows = [x for x in r["items"] if (not tur or x["tur"] == tur) and (not sinif or x["sinif"] == sinif)]
    if q:
        f = M.fold(q)
        rows = [x for x in rows if f in M.fold(x["siparisNo"]) or any(f in M.fold(v["cari"]) for v in x["faturalar"])]
    order = list(CLASSES)
    rows.sort(key=lambda x: (order.index(x["sinif"]), x["tarih"] or ""), reverse=False)
    return PC.page(rows, p, siniflar=CLASSES, turler=TURLER, yontem=r["yontem"], okundu=r["okundu"])


def panel_evidence(engine: sa.engine.Engine, tenant: str, platform: str) -> Optional[dict[str, Any]]:
    """Aşama 0'a kanıt: panel sipariş numarasıyla bulunan satış faturaları — tür, cari sayısı, ay sayısı."""
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(LOGO_INV).where(LOGO_INV.c.tenant_id == tenant, LOGO_INV.c.platform == platform,
                                                   LOGO_INV.c.eslesme == "siparis", LOGO_INV.c.tur.in_(SALES))).all()
    if not rows:
        return None
    return {"eslesenFatura": len(rows), "eslesenSiparis": len({r.anahtar for r in rows}),
            "perakende": sum(1 for r in rows if r.tur == 7), "toptan": sum(1 for r in rows if r.tur == 8 and r.platform_carisi),
            "farkliCari": len({r.cari for r in rows}), "ay": len({_month(r.tarih) for r in rows})}


# ------------------------------------------------------------------ hakediş


def hakedis(engine: sa.engine.Engine, tenant: str, platform: str, conf: Callable[[str], str], today: Optional[date] = None
            ) -> dict[str, Any]:
    ensure(engine)
    today = today or date.today()
    rows = PD.settlement_rows(engine, tenant, platform)
    meta = S.meta_get(engine, tenant, meta_key(platform))
    if not rows:
        return {"yuklendi": False, "okundu": bool(meta), "kalemAd": PM.KALEM_AD,
                "cumle": "Hakediş / hesap ekstresi dosyası yüklenmedi; kesinti ve ödeme karşılaştırması yapılamaz."}
    kalem: dict[str, dict[str, Any]] = {}
    months: dict[str, dict[str, Any]] = {}
    orders: dict[str, dict[str, Any]] = {}
    takvim: dict[str, float] = defaultdict(float)
    for r in rows:
        k = kalem.setdefault(r.kalem, {"kalem": r.kalem, "ad": PM.KALEM_AD.get(r.kalem, r.kalem), "satir": 0, "tutar": 0.0})
        k["satir"] += 1
        k["tutar"] += r.tutar
        when = r.tarih or r.odeme_tarihi
        m = months.setdefault(_month(when), {"ay": _month(when), "satis": 0.0, "iade": 0.0, "kesinti": 0.0, "odeme": 0.0,
                                             "net": 0.0, "kesintiKalem": defaultdict(float)})
        if r.kalem == "odeme":
            m["odeme"] += abs(r.tutar)
        elif r.kalem != "net-hakedis":
            m["net"] += r.tutar
            if r.kalem == "satis":
                m["satis"] += r.tutar
            elif r.kalem == "iade":
                m["iade"] += r.tutar
            elif r.kalem in PM.KESINTI:
                m["kesinti"] += -r.tutar
                m["kesintiKalem"][r.kalem] += -r.tutar
        if r.siparis_no and r.kalem not in ("odeme", "net-hakedis"):
            o = orders.setdefault(r.siparis_no, {"siparisNo": r.siparis_no, "satis": 0.0, "iade": 0.0, "kesinti": 0.0, "net": 0.0})
            o["net"] += r.tutar
            if r.kalem == "satis":
                o["satis"] += r.tutar
            elif r.kalem == "iade":
                o["iade"] += r.tutar
            elif r.kalem in PM.KESINTI:
                o["kesinti"] += -r.tutar
        if r.odeme_tarihi and r.odeme_tarihi.date() > today and r.kalem not in ("odeme", "net-hakedis"):
            takvim[r.odeme_tarihi.date().isoformat()] += r.tutar
    rec = reconcile(engine, tenant, platform, conf) if meta else None
    status = {}
    if rec:
        for x in rec["items"]:
            if x["tur"] == "satis" and x["siparisNo"]:
                status[x["siparisNo"]] = x
    missing = []
    for o in orders.values():
        if o["satis"] > 0 and rec is not None:
            x = status.get(o["siparisNo"])
            if x is None or x["sinif"] in ("eksik-fatura", "bekliyor", "iptal"):
                missing.append({**{k: round(v, 2) if isinstance(v, float) else v for k, v in o.items()},
                                "mutabakat": (x or {}).get("sinif")})
    logo = _logo_kesinti(engine, tenant, platform, meta)
    cash = _logo_cash(engine, tenant, platform, meta)
    for m in months.values():
        m["logoKesinti"] = round(logo["aylik"].get(m["ay"], 0.0), 2) if logo["bulundu"] else None
        m["logoTahsilat"] = round(cash["aylik"].get(m["ay"], 0.0), 2) if cash["bulundu"] else None
        m["kesintiKalem"] = {k: round(v, 2) for k, v in m["kesintiKalem"].items()}
        for f in ("satis", "iade", "kesinti", "odeme", "net"):
            m[f] = round(m[f], 2)
    docs = sorted({r.belge_no for r in rows if r.belge_no})
    found_docs = _found_docs(engine, tenant, platform)
    kes_total = round(sum(-v["tutar"] for k, v in kalem.items() if k in PM.KESINTI), 2)
    return {
        "yuklendi": True, "okundu": bool(meta), "kalemAd": PM.KALEM_AD,
        "kalemler": sorted(({**v, "tutar": round(v["tutar"], 2)} for v in kalem.values()), key=lambda v: v["tutar"]),
        "kesintiToplam": kes_total, "aylik": [months[k] for k in sorted(months)],
        "siparis": len(orders), "logoFaturasiYok": sorted(missing, key=lambda x: -x["satis"]),
        "logoKesinti": {k: v for k, v in logo.items() if k != "aylik"}, "logoTahsilat": {k: v for k, v in cash.items() if k != "aylik"},
        "belgeler": {"toplam": len(docs), "logodaVar": len([d for d in docs if d in found_docs]),
                     "logodaYok": [d for d in docs if d not in found_docs]},
        "odemeTakvimi": [{"tarih": k, "tutar": round(v, 2)} for k, v in sorted(takvim.items())],
    }


def _found_docs(engine: sa.engine.Engine, tenant: str, platform: str) -> set[str]:
    with engine.connect() as c:
        return {r[0] for r in c.execute(sa.select(LOGO_INV.c.anahtar).where(LOGO_INV.c.tenant_id == tenant, LOGO_INV.c.platform == platform,
                                                                               LOGO_INV.c.eslesme == "belge")).all() if r[0]}


def _logo_kesinti(engine: sa.engine.Engine, tenant: str, platform: str, meta: dict[str, Any]) -> dict[str, Any]:
    if not meta:
        return {"bulundu": False, "aylik": {}, "cumle": "Logo okuması yapılmadı; kesinti Logo'da aranmadı."}
    with engine.connect() as c:
        rows = c.execute(sa.select(LOGO_LINES, LOGO_INV.c.tarih, LOGO_INV.c.tur.label("fatura_turu"))
                         .select_from(LOGO_LINES.join(LOGO_INV, sa.and_(LOGO_INV.c.tenant_id == LOGO_LINES.c.tenant_id,
                                                                        LOGO_INV.c.platform == LOGO_LINES.c.platform,
                                                                        LOGO_INV.c.firma == LOGO_LINES.c.firma,
                                                                        LOGO_INV.c.ref == LOGO_LINES.c.fatura_ref)))
                         .where(LOGO_LINES.c.tenant_id == tenant, LOGO_LINES.c.platform == platform, LOGO_LINES.c.satir_turu == 4,
                                LOGO_INV.c.tur.in_(PURCHASE))).all()
    if not rows:
        why = ("bu platforma bağlanan cari bulunamadı ve ekstredeki belge numaraları Logo faturasında yok"
               if not meta.get("pazarYeriCarileri") else "pazar yeri carilerinden alınan hizmet faturası yok ve ekstredeki belge "
               "numaraları Logo faturasında bulunmadı")
        return {"bulundu": False, "aylik": {}, "kalemler": [], "cumle": f"Kesinti Logo'da bulunamadı: {why}. Uydurulmaz; kesinti "
                "cari bağı olmayan muhasebe fişiyle giriyor olabilir."}
    aylik: dict[str, float] = defaultdict(float)
    kal: dict[str, dict[str, Any]] = {}
    for r in rows:
        k = PM.kesinti_kalem(r.hizmet)
        a = kal.setdefault(k, {"kalem": k, "ad": PM.KALEM_AD.get(k, k), "satir": 0, "tutar": 0.0})
        a["satir"] += 1
        a["tutar"] += r.tutar or 0.0
        aylik[_month(r.tarih)] += r.tutar or 0.0
    total = sum(v["tutar"] for v in kal.values())
    return {"bulundu": True, "aylik": dict(aylik), "kalemler": sorted(({**v, "tutar": round(v["tutar"], 2)} for v in kal.values()),
                                                                      key=lambda v: -v["tutar"]),
            "toplam": round(total, 2), "cumle": "Logo'da platformdan alınan hizmet faturalarının hizmet satırları (KDV hariç)."}


def _logo_cash(engine: sa.engine.Engine, tenant: str, platform: str, meta: dict[str, Any]) -> dict[str, Any]:
    if not meta:
        return {"bulundu": False, "aylik": {}, "cumle": "Logo okuması yapılmadı; tahsilat Logo'da aranmadı."}
    with engine.connect() as c:
        rows = c.execute(sa.select(LOGO_CASH).where(LOGO_CASH.c.tenant_id == tenant, LOGO_CASH.c.platform == platform)).all()
    if not meta.get("pazarYeriCarileri"):
        return {"bulundu": False, "aylik": {}, "hareketler": [], "cumle": "Tahsilat Logo'da aranamadı: bu platforma bağlanan cari bulunamadı."}
    alacak = [r for r in rows if r.yon == 1]
    if not alacak:
        return {"bulundu": False, "aylik": {}, "hareketler": [], "cumle": "Pazar yeri carilerinde bu dönemde fatura dışı alacak hareketi yok."}
    aylik: dict[str, float] = defaultdict(float)
    agg: dict[tuple[int, int], dict[str, Any]] = {}
    for r in alacak:
        aylik[r.tarih.strftime("%Y-%m")] += r.tutar
        a = agg.setdefault((r.modul, r.tur), {"modulAd": PM.label(PM.MODUL, r.modul), "turAd": PM.label(PM.CARI_HAREKET, r.tur),
                                              "hareket": 0, "tutar": 0.0})
        a["hareket"] += r.hareket
        a["tutar"] += r.tutar
    return {"bulundu": True, "aylik": dict(aylik), "hareketler": sorted(({**v, "tutar": round(v["tutar"], 2)} for v in agg.values()),
                                                                        key=lambda v: -v["tutar"]),
            "toplam": round(sum(aylik.values()), 2), "cumle": "Pazar yeri carilerinin fatura dışı alacak hareketleri (tahsilat, virman, dekont)."}
