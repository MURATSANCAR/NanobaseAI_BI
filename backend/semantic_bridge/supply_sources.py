"""M52 Tedarik ve baskı yönetimi: Logo ve CRM okuması (yalnız okuma).

SQL'ler `supply_sql/<kaynak>.sql` dosyalarındadır; ekrandaki «Kaynak SQL» paneli çalışan metnin aynısını gösterir.
Yer tutucular (`{firma}`, `{donem}`, `{bas}`, `{crm}` …) yalnız doğrulanmış değerlerle doldurulur.

Kaynaklar ve tanımlar:

- **Tedarikçi cari ve bakiye** — cari kodu `SUPPLY_SUPPLIER_PREFIX` (varsayılan 320) ile başlayan cariler; bakiye alacak −
  borç (SIGN 1 − SIGN 0), bu yılın firmasında yıl başından. Katalog «satici-borcu-vadesi-gecmis-fifo» ile aynı.
- **Vade satırları** — `PAYTRANS` SIGN 1; Logo'da kapama yok, FIFO yaklaşımı (en yeni satırdan geriye dağıtım) köprüde.
- **Matbaa / kağıtçı** — cari özel kodu (`CLCARD.SPECODE`; ayar, varsayılan MATBAALAR / KAĞITÇILAR — analiz varsayımı,
  yazımı `logo_cari_ozel_kod.sql` ile ölçülür) ya da «Komple Baskı Giderleri» faturası kesmiş olmak (M12 ölçümü).
- **Baskı faturası** — M12 tanımı: TRCODE 4, hizmet `730.38.381`, satır özel kodu = stok kodu.
- **Alış** — katalog «satinalma»: Σ NETTOTAL, TRCODE 1/4 (KDV dahil).
- **Üretimden giriş** — Kural 20: STLINE TRCODE 13, IOCODE 1; yalnız gerçek giriş fişi (PRODSTAT 0, M12 ölçümü).
- **CRM** — üretim kartının teknik/kağıt alanları, kağıt cinsi ve ebat adları, plan değişiklikleri.

Yıllar Logo'da ayrı firmadır (411 = 2026, 211 = 2021–2025); firma/yıl eşlemesi `budget_sources.firms_by_year`.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import budget_sources as bsrc

log = logging.getLogger("semantic.supply.sources")

SQL_DIR = Path(__file__).with_name("supply_sql")
PRINT_SERVICE = "730.38.381"   # M12 production.PRINT_SERVICE ile aynı: «Komple Baskı Giderleri»

_FIRM = re.compile(r"^[0-9]{3}$")
_PERIOD = re.compile(r"^[0-9]{2}$")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PREFIX = re.compile(r"^[0-9A-Za-z.]{1,20}$")
_CODE = re.compile(r"^[0-9A-Za-zÇĞİÖŞÜçğıöşü.\-_ /]{1,40}$")

#: CRM kağıt parçaları (kolon öneki → ekrandaki ad), `crm_kart_teknik.sql` ile aynı sırada.
PAPER_PARTS: list[tuple[str, str]] = [
    ("kapak", "Kapak"), ("icsayfabir", "İç 1"), ("icsayfaiki", "İç 2"), ("somiz", "Şömiz"), ("harita", "Harita"),
    ("afis", "Afiş"), ("yankagit", "Yan kağıt"), ("ayrac", "Ayraç"),
]

#: Plan değişikliği sebebi (CRM seçenek listesi, metadata 2026-09-09); seçenek sorgusu okunamazsa bu adlar kullanılır.
CHANGE_REASONS = {1: "Kayıt hatası", 2: "Sözleşme kaynaklı", 3: "Editör kaynaklı", 4: "Yazar kaynaklı",
                  5: "Mütercim kaynaklı", 6: "Çizer kaynaklı", 7: "Yönetim kaynaklı", 8: "Üretim kaynaklı", 9: "Diğer"}

#: (kaynak, bağlantı, başlık, açıklama) — ekrandaki kaynak paneli.
SOURCES = [
    ("logo_tedarikci_cari", "logo", "Tedarikçi carileri ve bakiye", "320 carileri, özel kod, bu yılın bakiyesi (alacak − borç)."),
    ("logo_tedarikci_vade", "logo", "Ödeme planı satırları", "PAYTRANS SIGN 1; açık tutar FIFO yaklaşımıyla köprüde."),
    ("logo_cari_ozel_kod", "logo", "Özel kod dağılımı", "Matbaa / kağıtçı özel kodunun Logo'daki yazımı."),
    ("logo_baski_faturasi", "logo", "Matbaa baskı faturaları", "Komple Baskı Giderleri satırları; özel kod = stok kodu."),
    ("logo_alis_fatura", "logo", "Alış faturaları", "Tedarikçi × ay, TRCODE 1/4, NETTOTAL (KDV dahil)."),
    ("logo_tedarikci_faturalar", "logo", "Tedarikçinin faturaları", "Tek tedarikçinin alış faturaları."),
    ("logo_kagit_alis_satir", "logo", "Kağıt alış satırları", "Kağıtçı carilerinden mal alımı: miktar, birim, tutar."),
    ("logo_uretim_giris", "logo", "Üretimden giriş", "Ay bazında basılan adet (gerçek giriş fişi)."),
    ("crm_kart_teknik", "crm", "Üretim kartı teknik alanları", "Forma, sayfa, cilt, baskı tipi, parça başına kağıt ihtiyacı."),
    ("crm_kagit_cins", "crm", "Kağıt cinsi ve ebat", "Kağıt cinsi adı, gramaj, bulk; ebat adı."),
    ("crm_secenekler", "crm", "Seçenek adları", "Ciltleme şekli, baskı tipi, plan değişikliği sebebi."),
    ("crm_plan_degisiklik", "crm", "Plan değişiklikleri", "Değişen baskı tarihi ve sebebi."),
]


class SourceError(RuntimeError):
    pass


Run = Callable[[str], list[dict[str, Any]]]


# ------------------------------------------------------------------ yardımcılar


def sql_text(source_id: str) -> str:
    return (SQL_DIR / f"{source_id}.sql").read_text(encoding="utf-8")


def fill(source_id: str, **values: str) -> str:
    """SQL dosyasını doğrulanmış değerlerle doldurur; doldurulmamış yer tutucu kalırsa hata (yarım SQL çalışmaz)."""
    text = sql_text(source_id)
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    left = re.findall(r"\{[a-z_]+\}", text)
    if left:
        raise SourceError(f"{source_id}: doldurulmamış yer tutucu {', '.join(sorted(set(left)))}")
    return text


def firm(f: str) -> str:
    if not _FIRM.match(str(f or "")):
        raise SourceError("Logo firma numarası geçersiz.")
    return str(f)


def period(p: str) -> str:
    if not _PERIOD.match(str(p or "")):
        raise SourceError("Logo dönem numarası geçersiz.")
    return str(p)


def prefix(p: str) -> str:
    p = (p or "320").strip()
    if not _PREFIX.match(p):
        raise SourceError("Tedarikçi cari kodu öneki geçersiz.")
    return p


def crm_prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise SourceError(f"CRM şeması «{schema}» geçerli bir ad değil.")
    if not sch:
        raise SourceError("CRM şeması girilmemiş; CRM okunamıyor.")
    return (f"{db}." if db else "") + f"{sch}."


def code_literal(code: str) -> str:
    """Cari kodu SQL'e yalnız doğrulanmış biçimde girer (tek tırnak kaçışı dahil)."""
    s = str(code or "").strip()
    if not _CODE.match(s):
        raise SourceError("Cari kodu geçersiz.")
    return s.replace("'", "''")


def values_rows(codes: Iterable[str]) -> str:
    rows = [f"(N'{code_literal(c)}')" for c in sorted({str(c).strip() for c in codes if str(c or '').strip()})]
    if not rows:
        raise SourceError("Kod listesi boş.")
    return ", ".join(rows)


def lower_keys(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{str(k).lower(): v for k, v in r.items()} for r in rows]


def num(v: Any) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return 0.0
    return n if n == n else 0.0


def opt_num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def text(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def day(v: Any) -> Optional[date]:
    """Logo tarihleri saatsizdir; 1900 ve öncesi Logo'nun «boş» değeridir."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        d = v.date()
    elif isinstance(v, date):
        d = v
    else:
        try:
            d = date.fromisoformat(str(v).strip()[:10])
        except ValueError:
            return None
    return None if d.year < 1901 else d


def guid(v: Any) -> Optional[str]:
    s = text(v)
    return s.lower() if s else None


def specodes(raw: str) -> list[str]:
    """Ayardaki özel kod listesi: virgül ya da noktalı virgülle; büyük/küçük harf korunur (Logo yazımı)."""
    return [x.strip() for x in re.split(r"[;,]", raw or "") if x.strip()]


# ------------------------------------------------------------------ yıl → firma


def firms_for(run: Run) -> dict[int, str]:
    try:
        return bsrc.firms_by_year(run)
    except Exception as e:  # noqa: BLE001
        raise SourceError(f"Logo dönemleri okunamadı: {str(e)[:200]}") from None


def firms_between(firms: dict[int, str], start: date, end: date) -> list[str]:
    """Aralığa düşen yılların firmaları (aynı firma birden çok yılı tutabilir: 211 = 2021–2025)."""
    out: list[str] = []
    for y in range(start.year, end.year + 1):
        f = firms.get(y)
        if f and f not in out:
            out.append(f)
    return out


def current_firm(firms: dict[int, str], today: date) -> tuple[str, int]:
    """Bu yılın firması; yoksa en son yılın (uyarıyla)."""
    if today.year in firms:
        return firms[today.year], today.year
    if not firms:
        raise SourceError("Logo'da tanımlı dönem yok.")
    y = max(firms)
    return firms[y], y


# ------------------------------------------------------------------ Logo okuma


def read_suppliers(run: Run, f: str, year: int, prefix_: str) -> list[dict[str, Any]]:
    sql = fill("logo_tedarikci_cari", firma=firm(f), donem=period("01"), yil_basi=f"{int(year)}-01-01", on_ek=prefix(prefix_))
    out = []
    for r in lower_keys(run(sql)):
        out.append({"ref": int(r["ref"]), "kod": text(r.get("kod")) or "", "unvan": text(r.get("unvan")) or "",
                    "ozelKod": text(r.get("ozel_kod")), "bakiye": round(num(r.get("bakiye")), 2)})
    return out


def read_plan_lines(run: Run, f: str, year: int, prefix_: str) -> list[dict[str, Any]]:
    sql = fill("logo_tedarikci_vade", firma=firm(f), donem=period("01"), yil_basi=f"{int(year)}-01-01", on_ek=prefix(prefix_))
    out = []
    for r in lower_keys(run(sql)):
        out.append({"ref": int(r["ref"]), "satir": int(r.get("satir") or 0), "vade": day(r.get("vade")),
                    "tutar": num(r.get("tutar")), "kumulatif": num(r.get("kumulatif")),
                    "faturaNo": text(r.get("fatura_no")), "faturaTarihi": day(r.get("fatura_tarihi"))})
    return out


def read_specode_counts(run: Run, f: str, prefix_: str) -> list[dict[str, Any]]:
    sql = fill("logo_cari_ozel_kod", firma=firm(f), on_ek=prefix(prefix_))
    return [{"ozelKod": text(r.get("ozel_kod")), "cari": int(num(r.get("cari")))} for r in lower_keys(run(sql))]


def read_print_invoices(run: Run, firms: list[str], since: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in firms:
        sql = fill("logo_baski_faturasi", firma=firm(f), donem=period("01"), baski_hizmeti=PRINT_SERVICE, bas=since.isoformat())
        for r in lower_keys(run(sql)):
            out.append({"firma": f, "faturaRef": int(r.get("fatura_ref") or 0), "satirRef": int(r.get("satir_ref") or 0),
                        "tarih": r.get("tarih"), "no": text(r.get("no")), "cariKod": text(r.get("cari_kod")),
                        "cari": text(r.get("cari")), "stok": text(r.get("stok")), "adet": num(r.get("adet")),
                        "tutar": num(r.get("tutar"))})
    return out


def read_purchases(run: Run, firms: list[str], since: date, prefix_: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in firms:
        sql = fill("logo_alis_fatura", firma=firm(f), donem=period("01"), on_ek=prefix(prefix_), bas=since.isoformat())
        for r in lower_keys(run(sql)):
            out.append({"cariKod": text(r.get("cari_kod")) or "", "yil": int(r["yil"]), "ay": int(r["ay"]),
                        "tur": int(r.get("tur") or 0), "fatura": int(num(r.get("fatura"))),
                        "tutar": round(num(r.get("tutar")), 2), "kdv": round(num(r.get("kdv")), 2)})
    return out


def read_supplier_invoices(run: Run, firms: list[str], code: str, since: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in firms:
        sql = fill("logo_tedarikci_faturalar", firma=firm(f), donem=period("01"), cari_kod=code_literal(code), bas=since.isoformat())
        for r in lower_keys(run(sql)):
            d = day(r.get("tarih"))
            out.append({"tarih": d.isoformat() if d else None, "no": text(r.get("no")), "tur": int(r.get("tur") or 0),
                        "tutar": round(num(r.get("tutar")), 2), "kdv": round(num(r.get("kdv")), 2),
                        "aciklama": text(r.get("aciklama"))})
    out.sort(key=lambda x: x["tarih"] or "", reverse=True)
    return out


def read_paper_purchases(run: Run, firms: list[str], codes: list[str], since: date) -> list[dict[str, Any]]:
    if not codes:
        return []
    kodlar = values_rows(codes)
    out: list[dict[str, Any]] = []
    for f in firms:
        sql = fill("logo_kagit_alis_satir", firma=firm(f), donem=period("01"), kodlar=kodlar, bas=since.isoformat())
        for r in lower_keys(run(sql)):
            out.append({"tarih": day(r.get("tarih")), "cariKod": text(r.get("cari_kod")), "kod": text(r.get("malzeme_kod")) or "",
                        "ad": text(r.get("malzeme")) or "", "birim": text(r.get("birim")) or "",
                        "miktar": num(r.get("miktar")), "tutar": num(r.get("tutar"))})
    return out


def read_production_receipts(run: Run, firms: list[str], since: date) -> dict[str, dict[str, float]]:
    """«YYYY-AA» → {adet, fis}; aynı ay iki firmada görünürse toplanır (firmalar yıl bazında ayrık)."""
    out: dict[str, dict[str, float]] = {}
    for f in firms:
        sql = fill("logo_uretim_giris", firma=firm(f), donem=period("01"), bas=since.isoformat())
        for r in lower_keys(run(sql)):
            key = f"{int(r['yil']):04d}-{int(r['ay']):02d}"
            cur = out.setdefault(key, {"adet": 0.0, "fis": 0.0})
            cur["adet"] += num(r.get("adet"))
            cur["fis"] += num(r.get("fis"))
    return out


def read_data_end(run: Run, firms: dict[int, str]) -> Optional[date]:
    try:
        return bsrc.read_data_end(run, firms)
    except Exception as e:  # noqa: BLE001 — veri sonu yalnız bilgi amaçlı
        log.info("supply: Logo veri sonu okunamadı: %s", e)
        return None


# ------------------------------------------------------------------ CRM okuma


def read_card_tech(run: Run, schema: str, since: date) -> dict[str, dict[str, Any]]:
    """Kart kimliği (küçük harf) → teknik alanlar + parça başına kağıt."""
    sql = fill("crm_kart_teknik", crm=crm_prefix(schema), bas=since.isoformat())
    out: dict[str, dict[str, Any]] = {}
    for r in lower_keys(run(sql)):
        cid = guid(r.get("id"))
        if not cid:
            continue
        parts = []
        for key, label in PAPER_PARTS:
            net, brut, top = opt_num(r.get(f"{key}_net")), opt_num(r.get(f"{key}_brut")), opt_num(r.get(f"{key}_toplam"))
            cins, ebat = guid(r.get(f"{key}_cins")), guid(r.get(f"{key}_ebat"))
            if (net or brut or top) or cins:
                parts.append({"part": key, "label": label, "net": net, "brut": brut, "toplam": top, "cins": cins, "ebat": ebat})
        out[cid] = {"forma": opt_num(r.get("forma")), "sayfa": opt_num(r.get("sayfa")),
                    "cilt": int(r["cilt"]) if r.get("cilt") is not None else None,
                    "baskiTipi": int(r["baski_tipi"]) if r.get("baski_tipi") is not None else None,
                    "kitapEbat": guid(r.get("kitap_ebat")), "toplamMaliyet": opt_num(r.get("toplam_maliyet")),
                    "paketMaliyet": opt_num(r.get("paket_maliyet")), "parts": parts}
    return out


def read_paper_names(run: Run, schema: str) -> dict[str, dict[str, Any]]:
    """Kimlik → {tur: cins|ebat, ad, gramaj, bulk, sira}."""
    sql = fill("crm_kagit_cins", crm=crm_prefix(schema))
    out: dict[str, dict[str, Any]] = {}
    for r in lower_keys(run(sql)):
        i = guid(r.get("id"))
        if i:
            out[i] = {"tur": text(r.get("tur")), "ad": text(r.get("ad")) or "", "gramaj": opt_num(r.get("gramaj")),
                      "bulk": opt_num(r.get("bulk")), "sira": opt_num(r.get("sira"))}
    return out


def read_options(run: Run, schema: str) -> dict[str, dict[int, str]]:
    sql = fill("crm_secenekler", crm=crm_prefix(schema))
    out: dict[str, dict[int, str]] = {}
    for r in lower_keys(run(sql)):
        try:
            out.setdefault(str(r["attr"]).lower(), {})[int(r["code"])] = str(r["label"])
        except (TypeError, ValueError, KeyError):
            continue
    return out


def read_plan_changes(run: Run, schema: str, since: date) -> list[dict[str, Any]]:
    sql = fill("crm_plan_degisiklik", crm=crm_prefix(schema), bas=since.isoformat())
    out = []
    for r in lower_keys(run(sql)):
        out.append({"id": guid(r.get("id")), "kart": guid(r.get("kart_id")), "yeni": r.get("yeni_tarih"),
                    "sebep": int(r["sebep"]) if r.get("sebep") is not None else None, "tarih": r.get("tarih")})
    return out


# ------------------------------------------------------------------ çalıştırıcı


def runner(path: str) -> Run:
    """Bağlantı dosyası için salt okunur sorgu çalıştırıcı (M46 ile aynı: hata düz cümle, sessiz kesme yok)."""
    try:
        run = bsrc.runner(path)
    except bsrc.SourceError as e:
        raise SourceError(str(e)) from None

    def wrapped(sql: str) -> list[dict[str, Any]]:
        try:
            return run(sql)
        except bsrc.SourceError as e:
            raise SourceError(str(e)) from None

    return wrapped


def window_start(today: date, months: int) -> date:
    """`months` ay önceki ayın ilk günü."""
    y, m = divmod(today.month - 1 - months, 12)
    return date(today.year + y, m + 1, 1)


def days_between(a: Optional[date], b: Optional[date]) -> Optional[int]:
    return (b - a).days if a and b else None
