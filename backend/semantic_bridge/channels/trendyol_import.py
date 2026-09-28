"""M40 Trendyol panel dosyası yükleme (Excel/CSV) ve şema denetimi.

Beş tür: ürün listesi, siparişler, iadeler, müşteri soruları, yorumlar. Dosya satıcı panelinden indirilen dışa
aktarımdır; kolon adları panel sürümüne göre değişebildiği için eş anlamlılarla tanınır (`SPECS`).

**Kişisel veri içeri alınmaz:** yalnız `SPECS`'te sayılan kolonlar okunur. Alıcı adı, adres, telefon, e-posta, T.C. gibi
kolonlar hiç okunmaz; adları yükleme kaydına «içeri alınmadı» diye düşer (değerleri değil). Serbest metinli alanlar
(soru, yorum, iade açıklaması) içindeki e-posta/telefon/uzun numara maskelenir (`platform_common.mask`).

Yazma: ürün listesi bütünüyle değişir (son liste esastır); diğer türler anahtarıyla güncellenir (aynı paket/talep/soru
yeniden yüklenirse son dosya kazanır). Hiçbir satır sessizce atılmaz: anahtarı ya da zorunlu alanı boş satır sayılır ve
kayda «atlanan satır» olarak yazılır.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge.channels import imports as I
from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import platform_common as PC
from semantic_bridge.channels import store as S
from semantic_bridge.channels import trendyol as T

MAX_MB = I.MAX_MB

_BARKOD = ("barkod", "barcode", "urun barkodu", "barkod no")
_URUN_ADI = ("urun adi", "urun ismi", "urun basligi", "baslik")

#: Tür → kolon eş anlamlıları (Türkçe harfler sadeleştirilmiş, küçük harf) ve zorunlu kolon grupları.
SPECS: dict[str, dict[str, Any]] = {
    "urun": {
        "cols": {
            "barkod": _BARKOD,
            "satici_stok_kodu": ("satici stok kodu", "stok kodu", "tedarikci stok kodu", "model kodu"),
            "trendyol_urun_id": ("urun id", "icerik id", "content id", "trendyol urun kodu", "urun kodu"),
            "baslik": _URUN_ADI,
            "durum": ("urun durumu", "durum", "satis durumu", "onay durumu", "yayin durumu", "statu"),
            "stok": ("stok", "stok adedi", "urun stok adedi", "mevcut stok", "satilabilir stok"),
            "piyasa_fiyati": ("piyasa satis fiyati", "piyasa fiyati", "psf"),
            "fiyat": ("trendyol satis fiyati", "satilacak fiyat", "satis fiyati", "indirimli fiyat", "tsf", "fiyat"),
        },
        "need": [("barkod",)],
    },
    "siparis": {
        "cols": {
            "paket_no": ("paket no", "paket numarasi", "paket id", "kargo paket no"),
            "siparis_no": ("siparis numarasi", "siparis no", "siparis id"),
            "siparis_tarihi": ("siparis tarihi", "olusturma tarihi", "siparis olusturma tarihi"),
            "durum": ("siparis durumu", "paket durumu", "durum", "siparis statusu"),
            "kargo_firma": ("kargo firmasi", "kargo sirketi", "kargo firma"),
            "kargo_durum": ("kargo durumu", "teslimat durumu"),
            "termin": ("kargoya teslim edilmesi gereken tarih", "kargoya verilmesi gereken tarih", "termin tarihi",
                       "son kargolama tarihi", "termin"),
            "barkod": _BARKOD,
            "urun_adi": _URUN_ADI,
            "adet": ("adet", "miktar", "urun adedi", "satilan adet"),
            "tutar": ("faturalanacak tutar", "satis tutari", "toplam tutar", "tutar", "satir tutari"),
        },
        "need": [("paket_no", "siparis_no"), ("barkod",)],
    },
    "iade": {
        "cols": {
            "talep_id": ("iade talep no", "talep no", "talep numarasi", "iade no", "iade numarasi", "talep id"),
            "siparis_no": ("siparis numarasi", "siparis no", "paket no"),
            "barkod": _BARKOD,
            "adet": ("adet", "miktar", "iade adedi"),
            "neden": ("iade nedeni", "iade sebebi", "talep nedeni", "neden", "sebep"),
            "aciklama": ("musteri aciklamasi", "aciklama", "musteri notu", "iade aciklamasi"),
            "durum": ("iade durumu", "talep durumu", "durum"),
            "tarih": ("talep tarihi", "iade tarihi", "olusturma tarihi", "tarih"),
        },
        "need": [("barkod",), ("talep_id", "siparis_no")],
    },
    "soru": {
        "cols": {
            "soru_id": ("soru no", "soru id", "soru numarasi"),
            "barkod": _BARKOD,
            "urun_adi": _URUN_ADI,
            "metin": ("soru metni", "musteri sorusu", "soru"),
            "cevap": ("cevap metni", "cevap", "yanit", "satici cevabi"),
            "durum": ("cevap durumu", "soru durumu", "durum"),
            "tarih": ("soru tarihi", "olusturma tarihi", "tarih"),
        },
        "need": [("metin",)],
    },
    "yorum": {
        "cols": {
            "yorum_id": ("yorum id", "yorum no", "degerlendirme id"),
            "barkod": _BARKOD,
            "urun_adi": _URUN_ADI,
            "puan": ("puan", "yildiz", "degerlendirme puani", "urun puani", "yildiz sayisi"),
            "metin": ("yorum metni", "yorum", "degerlendirme"),
            "tarih": ("yorum tarihi", "degerlendirme tarihi", "tarih"),
        },
        "need": [("puan",), ("barkod", "urun_adi")],
    },
}

_OPEN = ("satista", "aktif", "onaylandi", "yayinda", "satisa acik", "acik")
_CLOSED = ("satista degil", "kapali", "pasif", "arsiv", "tukendi", "onaylanmadi", "reddedildi", "kilitli", "satisa kapali")
_ANSWERED = ("cevaplandi", "yanitlandi", "cevaplanmis")
_WAITING = ("cevaplanmadi", "bekliyor", "yanit bekliyor", "cevap bekliyor", "yanitlanmadi")


class ImportError_(ValueError):
    pass


def open_flag(text: Any) -> Optional[bool]:
    f = M.fold(text)
    if not f:
        return None
    if any(w in f for w in _CLOSED):
        return False
    if any(w in f for w in _OPEN):
        return True
    return None


def answered_flag(answer: Any, status: Any, has_answer_col: bool) -> Optional[bool]:
    if PC.cell(answer):
        return True
    f = M.fold(status)
    if f:
        if any(w in f for w in _WAITING):
            return False
        if any(w in f for w in _ANSWERED):
            return True
    return False if has_answer_col else None


def parse(tur: str, filename: str, data: bytes) -> dict[str, Any]:
    """Dosyayı okur, satırları türün alanlarına çevirir. Dönen: satırlar, tanınan/atlanan kolon adları, atlanan satır sayısı."""
    spec = SPECS.get(tur)
    if spec is None:
        raise ImportError_("Bilinmeyen dosya türü.")
    try:
        rows = I.read_rows(filename, data)
    except I.ImportError_ as e:
        raise ImportError_(str(e)) from None
    try:
        head_i, cols = PC.find_header(rows, spec["cols"], spec["need"])
    except ValueError:
        need = " ve ".join("/".join(g) for g in spec["need"])
        raise ImportError_(f"Başlık satırı bulunamadı: {T.TYPE_LABELS[tur].lower()} dosyasında şu kolonlar olmalı: {need}.") from None
    header = [PC.cell(v) for v in rows[head_i]]
    skipped, personal = PC.skipped_columns(header, set(cols.values()))
    out: list[dict[str, Any]] = []
    bad = 0
    for r in rows[head_i + 1:]:
        if not any(PC.cell(v) for v in r):
            continue                                   # boş satır: dosyanın sonu ya da ara
        g = lambda k: (r[cols[k]] if k in cols and cols[k] < len(r) else None)  # noqa: E731
        row = _row(tur, g, cols)
        if row is None:
            bad += 1
            continue
        out.append(row)
    return {"rows": out, "columns": {k: header[j] for k, j in cols.items()}, "skipped": skipped, "personal": personal, "bad": bad}


def _row(tur: str, g: Any, cols: dict[str, int]) -> Optional[dict[str, Any]]:
    bk = PC.barcode(g("barkod")) or None
    if tur == "urun":
        if not bk:
            return None
        durum = PC.cell(g("durum"), 120) or None
        return {"barkod": bk, "satici_stok_kodu": PC.cell(g("satici_stok_kodu"), 80) or None,
                "trendyol_urun_id": PC.barcode(g("trendyol_urun_id")) or None, "baslik": PC.cell(g("baslik")) or None,
                "satisa_acik": open_flag(durum), "durum_metni": durum, "stok": PC.num(g("stok")), "fiyat": PC.num(g("fiyat")),
                "piyasa_fiyati": PC.num(g("piyasa_fiyati"))}
    if tur == "siparis":
        pid = PC.barcode(g("paket_no")) or PC.barcode(g("siparis_no"))
        if not pid or not bk:
            return None
        return {"paket_id": pid, "barkod": bk, "siparis_no": PC.barcode(g("siparis_no")) or None,
                "siparis_tarihi": PC.when(g("siparis_tarihi")), "durum": PC.cell(g("durum"), 120) or None,
                "kargo_firma": PC.cell(g("kargo_firma"), 120) or None, "kargo_durum": PC.cell(g("kargo_durum"), 120) or None,
                "termin": PC.when(g("termin")), "adet": PC.num(g("adet")) if "adet" in cols else 1.0, "tutar": PC.num(g("tutar")),
                "urun_adi": PC.cell(g("urun_adi")) or None}
    if tur == "iade":
        tid = PC.barcode(g("talep_id")) or PC.barcode(g("siparis_no"))
        if not tid or not bk:
            return None
        return {"talep_id": tid, "barkod": bk, "siparis_no": PC.barcode(g("siparis_no")) or None,
                "adet": PC.num(g("adet")) if "adet" in cols else 1.0, "neden_metni": PC.cell(g("neden")) or None,
                "aciklama_maskeli": PC.mask(g("aciklama")) or None, "durum": PC.cell(g("durum"), 120) or None,
                "tarih": PC.when(g("tarih"))}
    if tur == "soru":
        metin = PC.mask(g("metin"))
        if not metin:
            return None
        tarih = PC.when(g("tarih"))
        sid = PC.barcode(g("soru_id")) or PC.key_hash(bk, tarih, metin)
        return {"soru_id": sid, "barkod": bk, "urun_adi": PC.cell(g("urun_adi")) or None, "metin_maskeli": metin,
                "cevaplandi": answered_flag(g("cevap"), g("durum"), "cevap" in cols), "soru_tarihi": tarih}
    if tur == "yorum":
        puan = PC.num(g("puan"))
        ad = PC.cell(g("urun_adi")) or None
        if puan is None or not (bk or ad):
            return None
        metin = PC.mask(g("metin")) or None
        tarih = PC.when(g("tarih"))
        yid = PC.barcode(g("yorum_id")) or PC.key_hash(bk or ad, tarih, metin, puan)
        return {"yorum_id": yid, "barkod": bk, "urun_adi": ad, "puan": puan, "metin_maskeli": metin, "tarih": tarih}
    return None


_KEYS = {"siparis": ("paket_id", "barkod"), "iade": ("talep_id", "barkod"), "soru": ("soru_id",), "yorum": ("yorum_id",)}


def store(engine: sa.engine.Engine, tenant: str, user: str, tur: str, filename: str, data: bytes) -> dict[str, Any]:
    if tur not in SPECS:
        raise ImportError_("Dosya türü seçilmeli.")
    if not data:
        raise ImportError_("Dosya boş.")
    T.ensure(engine)
    parsed = parse(tur, filename or "", data)
    if not parsed["rows"]:
        raise ImportError_("Dosyada okunacak satır yok.")
    table = T.TABLES[tur]
    iid = S.new_id()
    now = S.now()
    uniq: dict[tuple, dict[str, Any]] = {}
    keys = ("barkod",) if tur == "urun" else _KEYS[tur]
    for r in parsed["rows"]:
        uniq[tuple(r[k] for k in keys)] = {**r, "tenant_id": tenant, "kaynak": "excel", "import_id": iid, "okuma_zamani": now}
    rows = list(uniq.values())
    b = T.Books(engine, tenant)
    matched = sum(1 for r in rows if b.code(r.get("barkod"), r.get("satici_stok_kodu")))
    with engine.begin() as c:
        if tur == "urun":
            c.execute(table.delete().where(table.c.tenant_id == tenant))
        else:
            for i in range(0, len(rows), 400):
                part = rows[i:i + 400]
                if len(keys) == 1:
                    c.execute(table.delete().where(table.c.tenant_id == tenant, table.c[keys[0]].in_([r[keys[0]] for r in part])))
                else:
                    cond = sa.or_(*[sa.and_(*[table.c[k] == r[k] for k in keys]) for r in part])
                    c.execute(table.delete().where(table.c.tenant_id == tenant, cond))
        for i in range(0, len(rows), 2000):
            c.execute(table.insert(), rows[i:i + 2000])
        c.execute(T.IMPORTS.insert().values(
            id=iid, tenant_id=tenant, tur=tur, dosya_adi=(filename or "")[:300], satir=len(rows), eslesen=matched,
            kolonlar_json=json.dumps({"taninan": parsed["columns"], "atlanan": parsed["skipped"], "kisiselOlabilir": parsed["personal"],
                                      "atlananSatir": parsed["bad"], "tekrar": len(parsed["rows"]) - len(rows)}, ensure_ascii=False),
            yukleyen=user, tarih=now))
    return get(engine, tenant, iid)


def _view(r: Any) -> dict[str, Any]:
    return {"id": r.id, "tur": r.tur, "turAd": T.TYPE_LABELS.get(r.tur, r.tur), "dosya": r.dosya_adi, "satir": r.satir,
            "eslesen": r.eslesen, "kolonlar": S.jload(r.kolonlar_json, {}), "yukleyen": r.yukleyen, "tarih": S.iso(r.tarih)}


def get(engine: sa.engine.Engine, tenant: str, iid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(T.IMPORTS).where(T.IMPORTS.c.tenant_id == tenant, T.IMPORTS.c.id == iid)).first()
    if r is None:
        raise ImportError_("Yükleme bulunamadı.")
    out = _view(r)
    table = T.TABLES.get(r.tur)
    if table is not None:
        with engine.connect() as c:
            out["kalan"] = c.execute(sa.select(sa.func.count()).select_from(table)
                                     .where(table.c.tenant_id == tenant, table.c.import_id == iid)).scalar() or 0
    return out


def list_imports(engine: sa.engine.Engine, tenant: str, tur: str = "") -> list[dict[str, Any]]:
    stmt = sa.select(T.IMPORTS).where(T.IMPORTS.c.tenant_id == tenant)
    if tur:
        stmt = stmt.where(T.IMPORTS.c.tur == tur)
    with engine.connect() as c:
        return [_view(r) for r in c.execute(stmt.order_by(T.IMPORTS.c.tarih.desc())).all()]


def delete(engine: sa.engine.Engine, tenant: str, iid: str) -> dict[str, Any]:
    """Yüklemeyi ve hâlâ ona ait satırları siler (sonraki dosyanın güncellediği satırlar o dosyada kalır)."""
    out = get(engine, tenant, iid)
    table = T.TABLES.get(out["tur"])
    with engine.begin() as c:
        if table is not None:
            c.execute(table.delete().where(table.c.tenant_id == tenant, table.c.import_id == iid))
        c.execute(T.IMPORTS.delete().where(T.IMPORTS.c.tenant_id == tenant, T.IMPORTS.c.id == iid))
    return out
