"""M42 kanal paketi: Logo ve CRM okumaları (yalnız okuma).

SQL metinleri `channels/sql/*.sql` dosyalarındadır; M34 (pazar yeri sell-in) ve M40/M41 aynı dosyaları buradan içe aktarır
(`eticaret_cari_sql`, `cari_kitap_sql`). Logo'da yıl = firma numarası; eşleme `budget_sources.firms_by_year`'dan
(`L_CAPIPERIOD`, kopya yıllar atlanır). Yıllık firma tablosu yıl süzgeciyle okunur (211 kopyası 2021–2025'i tutar).

Tanım (katalog ve M46 ile aynı): satış = faturalı (`INVOICEREF <> 0`) malzeme satırı (`LINETYPE 0`), TRCODE 7/8/9;
iade = 2/3; net ciro = Σ VATMATRAH (satış) − Σ VATMATRAH (iade) (KDV matrahı, fatura geneli iskonto dahil; dönem
fatura tarihi `INVOICE.DATE_` — karar 2026-10-01); iskonto = satır iskontosu (`LINETYPE 2`) TOTAL'i;
maliyet yalnız `OUTCOST > 0` satırlarında `AMOUNT × OUTCOST`.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

from semantic_bridge import budget_sources as bsrc
from semantic_bridge.budget_sources import Runner, SourceError, firms_by_year, runner  # noqa: F401 — dışa açık

SQL_DIR = Path(__file__).with_name("sql")
METRICS = ("satis_ciro", "iade_ciro", "satis_adet", "iade_adet", "brut_satis", "iskonto", "maliyet", "maliyetli_ciro",
           "maliyetsiz_satir", "maliyetsiz_ciro", "iade_maliyet", "iade_maliyetli_ciro")
BOOK_METRICS = ("satis_adet", "iade_adet", "satis_ciro", "iade_ciro", "maliyet", "maliyetli_ciro", "maliyetsiz_adet",
                "maliyetsiz_ciro")
#: Kanal koduyla eşlenen carilerin grup öneki (bireysel site müşterileri gibi tek tek eşlenemeyecek kadar çok cari).
KANAL_PREFIX = "#K:"
#: Bir IN listesinde en çok bu kadar değer; fazlası parçalara bölünür (hepsi okunur, sessiz kesme yok).
IN_CHUNK = 800


@lru_cache(maxsize=None)
def template(name: str) -> str:
    return (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")


def q(v: Any) -> str:
    """SQL metin sabiti (tek tırnak kaçışlı). Kullanıcı girdisi SQL'e yalnız bu yolla girer."""
    return "N'" + str(v).replace("'", "''") + "'"


def _in(values: Iterable[Any]) -> str:
    vals = [q(v) for v in dict.fromkeys(str(x) for x in values if x is not None and str(x) != "")]
    return ", ".join(vals) if vals else "NULL"


def scope_sql(specodes: Iterable[str], codes: Iterable[str]) -> str:
    """Kapsam koşulu: bu kanal kodlarından biri ya da bu cari kodlarından biri."""
    parts = []
    sp = [s for s in specodes if s]
    cd = [c for c in codes if c]
    if sp:
        parts.append(f"C.SPECODE2 IN ({_in(sp)})")
    if cd:
        parts.append(f"C.CODE IN ({_in(cd)})")
    return " OR ".join(parts) if parts else "1 = 0"


def grup_sql(kanal_mapped: Iterable[str], codes: Iterable[str]) -> str:
    """Satırın grubu: tek tek eşlenmiş cari önce kendi kodu; kanal koduyla eşlenen kanaldaki cari '#K:<kod>'."""
    km = [s for s in kanal_mapped if s]
    if not km:
        return "C.CODE"
    cd = [c for c in codes if c]
    first = f"WHEN C.CODE IN ({_in(cd)}) THEN C.CODE " if cd else ""
    return (f"CASE {first}WHEN C.SPECODE2 IN ({_in(km)}) THEN '{KANAL_PREFIX}' + LTRIM(RTRIM(C.SPECODE2)) "
            f"ELSE C.CODE END")


def _fill(name: str, **kw: Any) -> str:
    return template(name).format(**kw).strip()


def kanal_karne_sql(firm: str, year: int) -> str:
    return _fill("logo_kanal_karne", firm=firm, year=year, next=year + 1, metrics=template("_metrics").strip())


def eticaret_cari_sql(firm: str, year: int, scope: str, grup: str = "C.CODE") -> str:
    """Cari × ay sell-in (M34 pazar yeri panosu da bunu çağırır: `scope_sql(['E-TICARET'], [])`)."""
    return _fill("logo_eticaret_cari", firm=firm, year=year, next=year + 1, metrics=template("_metrics").strip(),
                 scope=scope, grup=grup)


def cari_kitap_sql(firm: str, year: int, scope: str, grup: str = "C.CODE") -> str:
    return _fill("logo_cari_kitap", firm=firm, year=year, next=year + 1, scope=scope, grup=grup)


def cari_liste_sql(firm: str, scope: str) -> str:
    return _fill("logo_cari_liste", firm=firm, scope=scope)


def barkod_sql(firm: str) -> str:
    return _fill("logo_barkod", firm=firm)


def crm_cari_sql(schema: str, refs: Iterable[Any]) -> str:
    return _fill("crm_cari", schema=schema, refs=_in(refs))


def crm_siparis_sql(schema: str, days: int) -> str:
    return _fill("crm_kanal_siparis", schema=schema, days=int(days))


def crm_hedef_sql(schema: str, yil_kodu: int) -> str:
    return _fill("crm_hedef", schema=schema, yil_kodu=int(yil_kodu))


def crm_hedef_etiket_sql(schema: str) -> str:
    return _fill("crm_hedef_etiket", schema=schema)


# ------------------------------------------------------------------ okuma


def _f(v: Any) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return x if x == x else 0.0


def _s(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _metric_row(r: dict[str, Any], names: Iterable[str]) -> dict[str, float]:
    return {k: _f(r.get(k)) for k in names}


def read_kanal(run: Runner, firms: dict[int, str], year: int) -> list[dict[str, Any]]:
    firm = bsrc._firm(firms, year)
    out = []
    for r in run(kanal_karne_sql(firm, year)):
        out.append({"yil": year, "ay": int(r["ay"]), "kanal": _s(r.get("kanal"))[:60] or "#YOK", **_metric_row(r, METRICS)})
    return out


def dagitimci_cari() -> Optional[str]:
    """Başarı Dağıtım'ın Logo cari kodu (M39 ayarı `PAZAR_DAGITIM_BASARI_CARI`). Kanal karnesinde dağıtımcıya satış
    (sell-in) bu cariden, e-ticaret kapsamından ayrı okunur; platform toplamlarına girmez."""
    try:
        from semantic_bridge import pazar_dagitim as PD

        return (PD.settings().get("basariCari") or "").strip() or None
    except Exception:  # noqa: BLE001 — ayar okunamazsa dağıtımcı satırı okunmaz
        return None


def read_dagitimci(run: Runner, firms: dict[int, str], year: int, code: str) -> list[dict[str, Any]]:
    """Dağıtımcı carisinin ay satırları: karnedeki cari × ay sorgusunun aynısı, kapsam yalnız bu cari."""
    return [{"ay": r["ay"], **{k: r[k] for k in METRICS}} for r in read_cari(run, firms, year, scope_sql([], [code]), "C.CODE")]


def read_cari(run: Runner, firms: dict[int, str], year: int, scope: str, grup: str) -> list[dict[str, Any]]:
    firm = bsrc._firm(firms, year)
    out = []
    for r in run(eticaret_cari_sql(firm, year, scope, grup)):
        g = _s(r.get("grup"))
        if not g:
            continue
        out.append({"yil": year, "ay": int(r["ay"]), "grup": g[:80], **_metric_row(r, METRICS)})
    return out


def read_books(run: Runner, firms: dict[int, str], year: int, scope: str, grup: str) -> list[dict[str, Any]]:
    firm = bsrc._firm(firms, year)
    out = []
    for r in run(cari_kitap_sql(firm, year, scope, grup)):
        g, code = _s(r.get("grup")), _s(r.get("stok_kodu"))
        if not g or not code:
            continue
        out.append({"yil": year, "ay": int(r["ay"]), "grup": g[:80], "stok_kodu": code[:60], **_metric_row(r, BOOK_METRICS)})
    return out


def read_cariler(run: Runner, firm: str, scope: str) -> list[dict[str, Any]]:
    out = []
    for r in run(cari_liste_sql(firm, scope)):
        code = _s(r.get("cari_kodu"))
        if code:
            out.append({"cari_kodu": code[:80], "unvan": _s(r.get("unvan"))[:300] or None, "kanal": _s(r.get("kanal"))[:60] or None,
                        "ref": int(r["ref"]) if r.get("ref") is not None else None, "firma": firm})
    return out


def read_item_names(run: Runner, firm: str, codes: Optional[set[str]] = None) -> dict[str, str]:
    out = {}
    for r in run(bsrc.item_names_sql(firm)):
        code = _s(r.get("stok_kodu"))
        if code and (codes is None or code in codes):
            out[code] = _s(r.get("ad"))[:400]
    return out


def read_barcodes(run: Runner, firm: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in run(barkod_sql(firm)):
        b, code = _s(r.get("barkod")).replace(" ", ""), _s(r.get("stok_kodu"))
        if b and code and b not in out:
            out[b[:40]] = code[:60]
    return out


def _digits(v: Any) -> Optional[int]:
    d = "".join(ch for ch in str(v or "") if ch.isdigit())
    return int(d) if d else None


def read_crm_accounts(run: Runner, schema: str, refs: Iterable[int]) -> dict[int, dict[str, Any]]:
    """Logo LOGICALREF → CRM cari (ad, firma kanalı, özel kod 2). Parçalar halinde; hepsi okunur."""
    want = sorted({int(x) for x in refs if x is not None})
    out: dict[int, dict[str, Any]] = {}
    for i in range(0, len(want), IN_CHUNK):
        part = want[i:i + IN_CHUNK]
        for r in run(crm_cari_sql(schema, [str(x) for x in part])):
            ref = _digits(r.get("logicalref"))
            if ref is None or ref in out:
                continue
            out[ref] = {"crm_id": _s(r.get("crm_id")) or None, "ad": _s(r.get("ad")) or None,
                        "firma_kanal": r.get("firma_kanal"), "ozel_kod2": r.get("ozel_kod2")}
    return out


def read_crm_orders(run: Runner, schema: str, days: int) -> dict[str, Any]:
    """Sipariş tipi → sayı (toplam) ve Logo ref → tip → sayı."""
    total: dict[str, int] = {}
    by_ref: dict[str, dict[str, int]] = {}
    for r in run(crm_siparis_sql(schema, days)):
        tip = str(r.get("tip")) if r.get("tip") is not None else "bos"
        n = int(r.get("sayi") or 0)
        total[tip] = total.get(tip, 0) + n
        ref = _digits(r.get("logicalref"))
        if ref is not None:
            by_ref.setdefault(str(ref), {})
            by_ref[str(ref)][tip] = by_ref[str(ref)].get(tip, 0) + n
    return {"days": int(days), "byType": total, "byRef": by_ref}


_YEAR = re.compile(r"(19|20)\d{2}")


def read_target_labels(run: Runner, schema: str) -> dict[str, dict[str, str]]:
    """new_yil kodu → yıl, new_bolge kodu → ad. Aynı kod iki etiket alırsa yılda dört haneli yıl içeren kazanır."""
    years: dict[str, str] = {}
    regions: dict[str, str] = {}
    for r in run(crm_hedef_etiket_sql(schema)):
        kod, ad, alan = str(r.get("kod")), _s(r.get("ad")), str(r.get("alan") or "")
        if alan == "new_yil":
            m = _YEAR.search(ad)
            if m and (kod not in years or not _YEAR.search(years[kod])):
                years[kod] = m.group(0)
        elif alan == "new_bolge" and ad and kod not in regions:
            regions[kod] = ad
    return {"years": years, "regions": regions}


def read_targets(run: Runner, schema: str, yil_kodu: int) -> list[dict[str, Any]]:
    out = []
    for r in run(crm_hedef_sql(schema, yil_kodu)):
        if r.get("bolge") is None:
            continue
        out.append({"bolge": str(r["bolge"]), "satir": int(r.get("satir") or 0), "toplam": _f(r.get("toplam")),
                    "aylar": [_f(r.get(f"m{i}")) for i in range(1, 13)]})
    return out
