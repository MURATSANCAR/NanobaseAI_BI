"""Aşama 1 panel dosyaları (Trendyol ve Amazon TR): hakediş / hesap ekstresi (iki platform), Amazon sipariş ve iade
raporu. Trendyol sipariş ve iade dosyaları M40'ın kendi yüklemesindedir (`trendyol_import`); burada yeniden alınmaz.

Kolonlar eş anlamlılarla tanınır (`SPECS`). Eş anlamlılar platformların bilinen dışa aktarım başlıklarından (Trendyol
cari hesap ekstresi / sipariş bazlı hakediş, Amazon settlement «flat file», All Orders, Returns, Vendor PO raporu) —
**gerçek bir TİMAŞ dosyasıyla doğrulanmadı**; tanınmayan başlıkta dosya reddedilir ve ekranda hangi kolonların
beklendiği yazar (sessiz yanlış okuma yok). **Kişisel veri içeri alınmaz:** yalnız `SPECS`'te sayılan kolonlar okunur;
alıcı adı, adres, telefon, e-posta kolonlarının yalnız adı kayda «içeri alınmadı» diye düşer.

Hakediş satırı işaretli tutardır (TİMAŞ lehine +): uzun biçimde `tutar` ya da `alacak − borç`; geniş biçimde (sipariş
başına satış, komisyon, kargo… kolonları) her dolu kolon ayrı satır olur, satış +, kesinti −. Uzun biçimde tek `tutar`
kolonu varsa ve bir kesinti kaleminde dosyada hiç eksi değer yoksa o kalemin değerleri gider sayılıp eksiye çevrilir
(kayıtta yazar). Satır anahtarı içeriğin özetidir: aynı dosya yeniden yüklenirse satır çoğalmaz.

Platforma hiçbir şey gönderilmez; dosya panelden insan tarafından indirilir.
"""
from __future__ import annotations

import json
import threading
from collections import Counter
from datetime import datetime
from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge.channels import imports as I
from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import pazaryeri_model as PM
from semantic_bridge.channels import platform_common as PC
from semantic_bridge.channels import store as S

MAX_MB = I.MAX_MB
_md = sa.MetaData()

IMPORTS = sa.Table(
    "semantic_mp_imports", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("platform", sa.String(20), nullable=False),
    sa.Column("tur", sa.String(12), nullable=False),              # siparis | iade | hakedis
    sa.Column("dosya_adi", sa.String(300)),
    sa.Column("satir", sa.Integer, nullable=False),
    sa.Column("kolonlar_json", sa.Text),
    sa.Column("yukleyen", sa.String(120), nullable=False),
    sa.Column("tarih", sa.DateTime(timezone=True), nullable=False),
)

#: Amazon sipariş/iade raporu satırları (Trendyol'unkiler `semantic_trendyol_orders|claims`'te).
ORDERS = sa.Table(
    "semantic_mp_orders", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("platform", sa.String(20), primary_key=True),
    sa.Column("tur", sa.String(8), primary_key=True),             # satis | iade
    sa.Column("siparis_no", sa.String(80), primary_key=True),
    sa.Column("satir_anahtari", sa.String(80), primary_key=True),  # barkod, yoksa SKU
    sa.Column("barkod", sa.String(40)),
    sa.Column("sku", sa.String(80)),
    sa.Column("tarih", sa.DateTime),
    sa.Column("durum", sa.String(120)),
    sa.Column("adet", sa.Float),
    sa.Column("tutar", sa.Float),
    sa.Column("import_id", sa.String(32)),
    sa.Column("okuma_zamani", sa.DateTime(timezone=True), nullable=False),
)

#: Hakediş / hesap ekstresi satırları. `tutar` işaretli (TİMAŞ lehine +), `kalem` kuralla (pazaryeri_model.kalem).
SETTLE = sa.Table(
    "semantic_mp_settlement", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("platform", sa.String(20), primary_key=True),
    sa.Column("anahtar", sa.String(40), primary_key=True),
    sa.Column("import_id", sa.String(32)),
    sa.Column("tarih", sa.DateTime),
    sa.Column("islem_tipi", sa.String(200)),
    sa.Column("aciklama", sa.String(400)),
    sa.Column("kalem", sa.String(16), nullable=False),
    sa.Column("siparis_no", sa.String(80)),
    sa.Column("barkod", sa.String(40)),
    sa.Column("tutar", sa.Float, nullable=False),
    sa.Column("odeme_tarihi", sa.DateTime),
    sa.Column("belge_no", sa.String(80)),
    sa.Column("komisyon_orani", sa.Float),
    sa.Column("okuma_zamani", sa.DateTime(timezone=True), nullable=False),
)

TYPES: dict[str, dict[str, str]] = {
    "trendyol": {"hakedis": "Hesap ekstresi / hakediş"},
    "amazon": {"siparis": "Sipariş raporu", "iade": "İade raporu", "hakedis": "Ödeme (settlement) raporu"},
}

_SIPARIS_NO = ("amazon-order-id", "order-id", "order id", "siparis no", "siparis numarasi", "siparis id", "purchase order",
               "po", "po number", "satinalma siparisi", "satinalma siparis no")
_BARKOD = ("barkod", "barcode", "isbn", "ean", "upc", "external id", "urun barkodu")
_SKU = ("sku", "seller-sku", "msku", "merchant sku", "satici stok kodu", "stok kodu")

SPECS: dict[str, dict[str, Any]] = {
    "siparis": {
        "cols": {
            "siparis_no": _SIPARIS_NO,
            "tarih": ("purchase-date", "order date", "siparis tarihi", "tarih", "date", "order placed date"),
            "durum": ("order-status", "item-status", "status", "durum", "siparis durumu"),
            "barkod": _BARKOD,
            "sku": _SKU,
            "adet": ("quantity", "quantity-purchased", "quantity-shipped", "accepted quantity", "adet", "miktar",
                     "kabul edilen miktar"),
            "tutar": ("item-price", "tutar", "total cost", "toplam tutar", "toplam maliyet", "net tutar", "amount"),
        },
        "need": [("siparis_no",), ("barkod", "sku")],
    },
    "iade": {
        "cols": {
            "siparis_no": _SIPARIS_NO,
            "tarih": ("return-date", "return date", "iade tarihi", "tarih", "date"),
            "durum": ("status", "durum", "iade durumu", "return status"),
            "barkod": _BARKOD,
            "sku": _SKU,
            "adet": ("quantity", "adet", "iade adedi", "miktar"),
            "tutar": ("refund amount", "refunded amount", "iade tutari", "tutar", "amount"),
        },
        "need": [("siparis_no",), ("barkod", "sku")],
    },
    "hakedis": {
        "cols": {
            "tarih": ("islem tarihi", "tarih", "posted-date", "posted-date-time", "transaction date", "date/time", "date",
                      "siparis tarihi", "fis tarihi"),
            "islem_tipi": ("islem tipi", "islem turu", "hareket tipi", "transaction-type", "transaction type", "type",
                           "amount-type", "kayit tipi", "fis turu", "belge tipi"),
            "aciklama": ("aciklama", "amount-description", "description", "islem aciklamasi"),
            "siparis_no": ("siparis no", "siparis numarasi", "order-id", "order id", "order number", "paket no", "siparis id"),
            "barkod": _BARKOD,
            "tutar": ("tutar", "amount", "net tutar", "islem tutari"),
            "borc": ("borc", "borc tutari", "debt"),
            "alacak": ("alacak", "alacak tutari", "credit"),
            "toplam_odeme": ("total-amount", "odenen tutar", "odeme tutari", "transfer tutari"),
            "komisyon_orani": ("komisyon orani", "commission rate"),
            "odeme_tarihi": ("odeme tarihi", "vade tarihi", "hakedis tarihi", "deposit-date", "payment date", "odeme gunu",
                             "vade"),
            "belge_no": ("fatura no", "belge no", "fis no", "komisyon fatura no", "komisyon faturasi no", "fatura seri no",
                         "dekont no", "invoice number", "commission invoice serial number"),
            # geniş biçim (sipariş başına kalem kolonları)
            "w_satis": ("satis tutari", "brut satis", "urun tutari", "faturalanacak tutar", "brut tutar"),
            "w_komisyon": ("komisyon tutari", "komisyon", "commission amount"),
            "w_kargo": ("kargo bedeli", "kargo tutari", "kargo ucreti", "kargo kesintisi"),
            "w_hizmet": ("hizmet bedeli", "platform hizmet bedeli", "islem bedeli"),
            "w_stopaj": ("stopaj", "stopaj tutari", "e-ticaret stopaji"),
            "w_reklam": ("reklam bedeli", "reklam"),
            "w_ceza": ("ceza", "ceza tutari"),
            "w_indirim": ("indirim tutari", "kupon tutari", "satici indirimi"),
            "w_hakedis": ("hakedis", "satici hakedisi", "net hakedis", "odenecek tutar", "hakedis tutari"),
        },
        "need": [("tutar", "borc", "alacak", "toplam_odeme", "w_satis", "w_komisyon", "w_hakedis"),
                 ("tarih", "siparis_no", "odeme_tarihi")],
    },
}
WIDE = {"w_satis": "satis", "w_komisyon": "komisyon", "w_kargo": "kargo", "w_hizmet": "hizmet", "w_stopaj": "stopaj",
        "w_reklam": "reklam", "w_ceza": "ceza", "w_indirim": "indirim", "w_hakedis": "net-hakedis"}
PERSONAL_EXTRA = ("buyer", "ship-", "recipient", "bill-", "customer")

_ready: set[int] = set()
_lock = threading.Lock()


class DosyaError(ValueError):
    pass


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        S.ensure(engine)
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _key(v: Any) -> str:
    return PC.barcode(v)[:80]


def parse(platform: str, tur: str, filename: str, data: bytes) -> dict[str, Any]:
    if tur not in TYPES.get(platform, {}):
        raise DosyaError("Bu platform için bilinmeyen dosya türü.")
    spec = SPECS[tur]
    try:
        rows = I.read_rows(filename, data)
    except I.ImportError_ as e:
        raise DosyaError(str(e)) from None
    try:
        head_i, cols = PC.find_header(rows, spec["cols"], spec["need"])
    except ValueError:
        need = " ve ".join("/".join(g) for g in spec["need"])
        raise DosyaError(f"Başlık satırı bulunamadı: {TYPES[platform][tur].lower()} dosyasında şu kolonlar olmalı: {need}. "
                         "Kolon adları gerçek bir panel dosyasıyla doğrulanacak; dosyanın başlığını bildirin.") from None
    header = [PC.cell(v) for v in rows[head_i]]
    skipped, personal = PC.skipped_columns(header, set(cols.values()))
    personal = sorted(set(personal) | {h for h in skipped if any(w in M.fold(h) for w in PERSONAL_EXTRA)})
    out: list[dict[str, Any]] = []
    bad = 0
    for r in rows[head_i + 1:]:
        if not any(PC.cell(v) for v in r):
            continue
        g = lambda k: (r[cols[k]] if k in cols and cols[k] < len(r) else None)  # noqa: E731
        got = _settle_rows(g, cols) if tur == "hakedis" else _order_row(g, cols)
        if not got:
            bad += 1
            continue
        out += got
    flipped: list[str] = []
    if tur == "hakedis" and "tutar" in cols and not ({"borc", "alacak"} & set(cols)) and not (set(WIDE) & set(cols)):
        for k in set(PM.KESINTI) | {"iade"}:
            vals = [x["tutar"] for x in out if x["kalem"] == k]
            if vals and not any(v < 0 for v in vals):
                for x in out:
                    if x["kalem"] == k:
                        x["tutar"] = -abs(x["tutar"])
                flipped.append(PM.KALEM_AD.get(k, k))
    return {"rows": out, "columns": {k: header[j] for k, j in cols.items()}, "skipped": skipped, "personal": personal,
            "bad": bad, "eksiyeCevrilen": sorted(flipped),
            "bicim": ("genis" if set(WIDE) & set(cols) else "uzun") if tur == "hakedis" else None}


def _order_row(g: Any, cols: dict[str, int]) -> list[dict[str, Any]]:
    no = _key(g("siparis_no"))
    bk, sku = PC.barcode(g("barkod")) or None, PC.cell(g("sku"), 80) or None
    if not no or not (bk or sku):
        return []
    return [{"siparis_no": no, "satir_anahtari": (bk or sku or "-")[:80], "barkod": bk, "sku": sku, "tarih": PC.when(g("tarih")),
             "durum": PC.cell(g("durum"), 120) or None, "adet": PC.num(g("adet")) if "adet" in cols else 1.0,
             "tutar": PC.num(g("tutar"))}]


def _settle_rows(g: Any, cols: dict[str, int]) -> list[dict[str, Any]]:
    base = {"tarih": PC.when(g("tarih")), "islem_tipi": PC.cell(g("islem_tipi"), 200) or None,
            "aciklama": PC.mask(g("aciklama"), 400) or None, "siparis_no": _key(g("siparis_no")) or None,
            "barkod": PC.barcode(g("barkod")) or None, "odeme_tarihi": PC.when(g("odeme_tarihi")),
            "belge_no": _key(g("belge_no")) or None, "komisyon_orani": PC.num(g("komisyon_orani"))}
    wide = [k for k in WIDE if k in cols]
    out = []
    if wide:
        for k in wide:
            v = PC.num(g(k))
            if v is None or v == 0:
                continue
            kal = WIDE[k]
            signed = abs(v) if kal in ("satis", "net-hakedis") else -abs(v)
            out.append({**base, "kalem": kal, "tutar": signed, "islem_tipi": base["islem_tipi"] or PM.KALEM_AD[kal]})
        return out
    v: Optional[float] = None
    if "tutar" in cols:
        v = PC.num(g("tutar"))
    elif "borc" in cols or "alacak" in cols:
        a, b = PC.num(g("alacak")), PC.num(g("borc"))
        if a is not None or b is not None:
            v = (a or 0.0) - (b or 0.0)
    if v is None or v == 0:
        total = PC.num(g("toplam_odeme"))
        if total:
            return [{**base, "kalem": "odeme", "tutar": abs(total), "islem_tipi": base["islem_tipi"] or "Ödeme (dosya toplamı)"}]
        return []
    return [{**base, "kalem": PM.kalem(" ".join(x for x in (base["islem_tipi"], base["aciklama"]) if x)), "tutar": v}]


def store(engine: sa.engine.Engine, tenant: str, user: str, platform: str, tur: str, filename: str, data: bytes) -> dict[str, Any]:
    if not data:
        raise DosyaError("Dosya boş.")
    ensure(engine)
    parsed = parse(platform, tur, filename or "", data)
    if not parsed["rows"]:
        raise DosyaError("Dosyada okunacak satır yok.")
    iid, now = S.new_id(), S.now()
    if tur == "hakedis":
        seen: Counter = Counter()
        rows = []
        for r in parsed["rows"]:
            sig = (r["tarih"], r["islem_tipi"], r["aciklama"], r["siparis_no"], r["barkod"], round(r["tutar"], 2), r["odeme_tarihi"],
                   r["belge_no"], r["kalem"])
            seen[sig] += 1
            rows.append({**r, "tenant_id": tenant, "platform": platform, "anahtar": PC.key_hash(platform, *sig, seen[sig]),
                         "import_id": iid, "okuma_zamani": now})
        table, keys = SETTLE, ("anahtar",)
    else:
        uniq: dict[tuple, dict[str, Any]] = {}
        for r in parsed["rows"]:
            uniq[(r["siparis_no"], r["satir_anahtari"])] = {**r, "tenant_id": tenant, "platform": platform,
                                                             "tur": "satis" if tur == "siparis" else "iade", "import_id": iid,
                                                             "okuma_zamani": now}
        rows = list(uniq.values())
        table, keys = ORDERS, ("tur", "siparis_no", "satir_anahtari")
    with engine.begin() as c:
        for i in range(0, len(rows), 400):
            part = rows[i:i + 400]
            cond = sa.or_(*[sa.and_(*[table.c[k] == r[k] for k in keys]) for r in part])
            c.execute(table.delete().where(table.c.tenant_id == tenant, table.c.platform == platform, cond))
        for i in range(0, len(rows), 2000):
            c.execute(table.insert(), rows[i:i + 2000])
        c.execute(IMPORTS.insert().values(
            id=iid, tenant_id=tenant, platform=platform, tur=tur, dosya_adi=(filename or "")[:300], satir=len(rows),
            kolonlar_json=json.dumps({"taninan": parsed["columns"], "atlanan": parsed["skipped"], "kisiselOlabilir": parsed["personal"],
                                      "atlananSatir": parsed["bad"], "eksiyeCevrilen": parsed["eksiyeCevrilen"],
                                      "bicim": parsed["bicim"]}, ensure_ascii=False),
            yukleyen=user, tarih=now))
    return get(engine, tenant, platform, iid)


def _view(r: Any) -> dict[str, Any]:
    return {"id": r.id, "platform": r.platform, "tur": r.tur, "turAd": TYPES.get(r.platform, {}).get(r.tur, r.tur),
            "dosya": r.dosya_adi, "satir": r.satir, "kolonlar": S.jload(r.kolonlar_json, {}), "yukleyen": r.yukleyen,
            "tarih": S.iso(r.tarih)}


def get(engine: sa.engine.Engine, tenant: str, platform: str, iid: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(IMPORTS).where(IMPORTS.c.tenant_id == tenant, IMPORTS.c.platform == platform, IMPORTS.c.id == iid)).first()
    if r is None:
        raise DosyaError("Yükleme bulunamadı.")
    return _view(r)


def list_imports(engine: sa.engine.Engine, tenant: str, platform: str) -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(IMPORTS).where(IMPORTS.c.tenant_id == tenant, IMPORTS.c.platform == platform)
                         .order_by(IMPORTS.c.tarih.desc())).all()
    return [_view(r) for r in rows]


def delete(engine: sa.engine.Engine, tenant: str, platform: str, iid: str) -> dict[str, Any]:
    out = get(engine, tenant, platform, iid)
    table = SETTLE if out["tur"] == "hakedis" else ORDERS
    with engine.begin() as c:
        c.execute(table.delete().where(table.c.tenant_id == tenant, table.c.platform == platform, table.c.import_id == iid))
        c.execute(IMPORTS.delete().where(IMPORTS.c.tenant_id == tenant, IMPORTS.c.id == iid))
    return out


def settlement_rows(engine: sa.engine.Engine, tenant: str, platform: str) -> list[Any]:
    ensure(engine)
    with engine.connect() as c:
        return c.execute(sa.select(SETTLE).where(SETTLE.c.tenant_id == tenant, SETTLE.c.platform == platform)).all()


def order_rows(engine: sa.engine.Engine, tenant: str, platform: str) -> list[Any]:
    ensure(engine)
    with engine.connect() as c:
        return c.execute(sa.select(ORDERS).where(ORDERS.c.tenant_id == tenant, ORDERS.c.platform == platform)).all()


def when_of(v: Any) -> Optional[datetime]:
    return v if isinstance(v, datetime) else PC.when(v)
