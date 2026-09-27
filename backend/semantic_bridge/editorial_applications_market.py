"""Yayın Kurulu Raporu'nun veri bölümü: kategorinin benzer kitapları, ilk yıl satışları, kanal kırılımı, katalog
örtüşmesi ve raporun kendisi.

**Benzer kitap kümesi (kohort).** Başvurunun kategorisi CRM «Kitaplık»tır (`new_kitaplikBase`; 2026-09-28'de
133 kitaplık, son 48–12 ayda ilk yayını olan 2.147 kitabın 1.543'ünde dolu). Küme: aynı kitaplıkta, ilk yayını
bugünden 12 ay öncesiyle ondan 36 ay öncesi arasında olan, stok kodu dolu kitaplar. 12 ay geriden başlamanın
nedeni ilk yıl satışının tamamlanmış olmasıdır; 36 ay iş tanımındaki «son 36 ay» penceresidir.

**Satış.** Logo'nun yıllık satış görünümleri (`V_SatisRaporu_<yıl>`, Baskı Öneri raporuyla aynı kaynak ve aynı
süzgeç: 157'li kodlar ve tutarsız satırlar dışarıda). Kitabın ilk yıl satışı = ilk yayın ayı dahil 12 takvim
ayının net adedi (satış − iade). Kanal kırılımı = kümedeki kitapların son 36 ayda kanal (`KANAL`) başına net adedi.

**Senaryolar.** Kümede Logo'da satışı görülen kitapların ilk yıl net adetlerinin çeyrekleri: kötümser = 1. çeyrek
(P25), baz = ortanca (P50), iyimser = 3. çeyrek (P75). Satışı hiç görülmeyen kitap ayrıca sayılır; senaryoya
girmez (stok kodu Logo'da farklı açılmış ya da kitap dağıtıma çıkmamış olabilir; sıfır saymak baz'ı yanıltır).
İlk baskı önerisi = baz senaryonun 500'lük üst yuvarlaması. Seri önerisi = kümede ilk yıl satışı üst çeyrekte
olan kitapların en sık dizisi. Model kullanılmaz; her sayı kaynağıyla ekrana çıkar.

Sorgular sabit, gözden geçirilmiş SQL'dir (Yönetim raporlarıyla aynı yol): sohbet motorunun katalog kapısından
geçmez, onun bağlantısını meşgul etmez, salt okunur ayrı bağlantıyla koşar.
"""
from __future__ import annotations

import logging
import math
import re
import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

log = logging.getLogger("semantic.editorial_applications")

COHORT_MONTHS = 36
FIRST_YEAR_MONTHS = 12
PRINT_STEP = 500
SALES_FILTER = "s.[Malzeme/Hizmet Kodu] NOT LIKE '157%' AND s.[KDVli Tutar] <> 0"
CODE_CHUNK = 5000
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")

#: Katalog örtüşmesinde sayılmayan sık kelimeler (başlıkta anlam taşımayan bağlaç, edat, genel ad).
STOP = {
    "için", "gibi", "kadar", "daha", "çok", "olan", "olarak", "üzerine", "hakkında", "veya", "ile", "ama", "fakat",
    "bir", "iki", "bu", "şu", "o", "ve", "de", "da", "ki", "mi", "ne", "nasıl", "neden", "niçin", "hangi", "her",
    "kitap", "kitabı", "kitabım", "roman", "romanı", "öykü", "öyküler", "hikaye", "hikâye", "hikayeler", "hikâyeler",
    "cilt", "set", "seti", "yeni", "büyük", "küçük", "ilk", "son",
}


class MarketError(ValueError):
    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.status = status


def _prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise MarketError(f"CRM şeması «{schema}» geçerli bir ad değil.")
    if not sch:
        raise MarketError("CRM şeması girilmemiş; kategori ve benzer kitaplar okunamıyor.")
    return (f"{db}." if db else "") + f"{sch}."


def _guid(v: str) -> str:
    if not _GUID.match(v or ""):
        raise MarketError("Kategori kimliği geçerli değil.", 400)
    return v


def _month_index(y: int, m: int) -> int:
    return y * 12 + (m - 1)


def _shift(today: date, months: int) -> date:
    i = _month_index(today.year, today.month) - months
    return date(i // 12, i % 12 + 1, 1)


def window(today: date) -> tuple[date, date]:
    """Kümenin ilk yayın aralığı [başlangıç, bitiş): bugünden 12+36 ay öncesinin ay başı → 12 ay öncesinin ay başı."""
    return _shift(today, FIRST_YEAR_MONTHS + COHORT_MONTHS), _shift(today, FIRST_YEAR_MONTHS)


# ---------------------------------------------------------------------------------------------------- SQL

def categories_sql(schema: str) -> str:
    p = _prefix(schema)
    return (f"SELECT kl.new_kitaplikId AS id, kl.new_name AS ad, COUNT(k.new_kitapId) AS kitap"
            f" FROM {p}new_kitaplikBase kl LEFT JOIN {p}new_kitapBase k ON k.new_kitaplikid = kl.new_kitaplikId AND k.statecode = 0"
            f" WHERE kl.statecode = 0 GROUP BY kl.new_kitaplikId, kl.new_name ORDER BY kl.new_name")


def cohort_sql(schema: str, category_id: str, start: date, end: date) -> str:
    p = _prefix(schema)
    return (f"SELECT k.new_kitapId AS id, k.new_name AS ad, LTRIM(RTRIM(k.new_StokKodu)) AS kod,"
            f" CAST(k.new_ilkyayintarihi AS date) AS ilk, k.new_yazartext AS yazar, d.new_name AS dizi"
            f" FROM {p}new_kitapBase k LEFT JOIN {p}new_diziBase d ON d.new_diziId = k.new_diziid"
            f" WHERE k.statecode = 0 AND k.new_kitaplikid = '{_guid(category_id)}'"
            f" AND k.new_StokKodu IS NOT NULL AND LTRIM(RTRIM(k.new_StokKodu)) <> ''"
            f" AND k.new_ilkyayintarihi >= '{start.isoformat()}' AND k.new_ilkyayintarihi < '{end.isoformat()}'"
            f" ORDER BY k.new_ilkyayintarihi")


def sales_sql(year: int, codes: list[str]) -> str:
    rows = ", ".join("(N'" + c.replace("'", "''") + "')" for c in codes)
    return (f"SELECT s.[Malzeme/Hizmet Kodu] AS kod, s.[Yıl] AS yil, s.[Ay] AS ay, s.KANAL AS kanal,"
            f" s.Satis_Iade AS tur, SUM(s.Miktar) AS adet"
            f" FROM dbo.V_SatisRaporu_{int(year)} AS s JOIN (VALUES {rows}) AS kod(k) ON kod.k = s.[Malzeme/Hizmet Kodu]"
            f" WHERE {SALES_FILTER}"
            f" GROUP BY s.[Malzeme/Hizmet Kodu], s.[Yıl], s.[Ay], s.KANAL, s.Satis_Iade")


def sales_views_sql() -> str:
    return "SELECT name FROM sys.views WHERE name LIKE 'V[_]SatisRaporu[_]20[0-9][0-9]'"


def _words(title: str) -> list[str]:
    out: list[str] = []
    for w in re.findall(r"[0-9A-Za-zÇĞİÖŞÜçğıöşüÂâÎîÛû]+", title or ""):
        lw = w.lower().replace("i̇", "i")
        if len(lw) >= 4 and lw not in STOP and lw not in out:
            out.append(lw)
    return out


def _like(w: str) -> str:
    t = w.replace("'", "''")
    for ch in ("[", "%", "_"):
        t = t.replace(ch, f"[{ch}]")
    return t


def overlap_sql(schema: str, title: str, contact_id: Optional[str]) -> Optional[str]:
    """Başlığındaki anlamlı kelimelerden en az ikisini (tek kelimeyse onu) taşıyan CRM kitapları ve — yazar CRM'de
    bağlıysa — yazarın kendi eserleri. Satır tavanı yok: eşik anlamlı kelime sayısıyla konur."""
    p = _prefix(schema)
    words = _words(title)
    parts = []
    if words:
        score = " + ".join(f"CASE WHEN k.new_name LIKE N'%{_like(w)}%' THEN 1 ELSE 0 END" for w in words)
        need = 1 if len(words) == 1 else 2
        parts.append(f"({score}) >= {need}")
    if contact_id:
        if not _GUID.match(contact_id):
            raise MarketError("CRM kişi kimliği geçerli değil.", 400)
        parts.append(f"k.new_kitapId IN (SELECT e.new_Kitap FROM {p}new_eserkatilimBase e WHERE e.statecode = 0"
                     f" AND e.new_Katilimsaglayan = '{contact_id}')")
    if not parts:
        return None
    score = " + ".join(f"CASE WHEN k.new_name LIKE N'%{_like(w)}%' THEN 1 ELSE 0 END" for w in words) or "0"
    mine = (f"CASE WHEN k.new_kitapId IN (SELECT e.new_Kitap FROM {p}new_eserkatilimBase e WHERE e.statecode = 0"
            f" AND e.new_Katilimsaglayan = '{contact_id}') THEN 1 ELSE 0 END") if contact_id else "0"
    return (f"SELECT k.new_kitapId AS id, k.new_name AS ad, k.new_yazartext AS yazar, kl.new_name AS kitaplik,"
            f" CAST(k.new_ilkyayintarihi AS date) AS ilk, ({score}) AS puan, {mine} AS yazarin"
            f" FROM {p}new_kitapBase k LEFT JOIN {p}new_kitaplikBase kl ON kl.new_kitaplikId = k.new_kitaplikid"
            f" WHERE k.statecode = 0 AND ({' OR '.join(parts)})"
            f" ORDER BY puan DESC, ilk DESC")


def project_sql(schema: str, project_id: str) -> str:
    p = _prefix(schema)
    if not _GUID.match(project_id or ""):
        raise MarketError("CRM proje kimliği geçerli değil.", 400)
    return f"SELECT j.new_projeId AS id, j.new_name AS ad FROM {p}new_projeBase j WHERE j.new_projeId = '{project_id}'"


# --------------------------------------------------------------------------------------------- hesaplar

def _s(v: Any) -> Optional[str]:
    t = str(v).strip() if v is not None else ""
    return t or None


def _day(v: Any) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = _s(v)
    try:
        return date.fromisoformat(t[:10]) if t else None
    except ValueError:
        return None


def percentile(xs: list[float], q: float) -> Optional[float]:
    """Doğrusal ara değerli yüzdelik (numpy 'linear' ile aynı)."""
    if not xs:
        return None
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _net(tur: Any, adet: Any) -> float:
    """Satış satırı artı, iade satırı eksi. Görünüm iadeyi artı adetle verse de eksiyle verse de aynı sonuç."""
    try:
        q = float(adet or 0)
    except (TypeError, ValueError):
        return 0.0
    return -abs(q) if "iade" in str(tur or "").lower() else q


def compute(books: list[dict[str, Any]], sales: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Kohort ve satış satırlarından pazar özeti. `books`: cohort_sql satırları; `sales`: sales_sql satırları."""
    by_code: dict[str, dict[str, Any]] = {}
    for b in books:
        code = _s(b.get("kod"))
        first = _day(b.get("ilk"))
        if not code or not first:
            continue
        # Aynı stok kodu iki kartta olabilir (yeniden açılmış kart): en eski ilk yayın esas.
        cur = by_code.get(code)
        if cur is None or first < cur["first"]:
            by_code[code] = {"id": _s(b.get("id")), "title": _s(b.get("ad")), "author": _s(b.get("yazar")),
                             "series": _s(b.get("dizi")), "code": code, "first": first, "firstYear": 0.0,
                             "lines": 0, "curve": [0.0] * FIRST_YEAR_MONTHS}
    now_i = _month_index(today.year, today.month)
    last36_from = now_i - (COHORT_MONTHS - 1)
    channels: dict[str, float] = {}
    last36 = 0.0
    for r in sales:
        b = by_code.get(_s(r.get("kod")) or "")
        if b is None:
            continue
        try:
            mi = _month_index(int(r.get("yil")), int(r.get("ay")))
        except (TypeError, ValueError):
            continue
        q = _net(r.get("tur"), r.get("adet"))
        b["lines"] += 1
        k = mi - _month_index(b["first"].year, b["first"].month)
        if 0 <= k < FIRST_YEAR_MONTHS:
            b["firstYear"] += q
            b["curve"][k] += q
        if last36_from <= mi <= now_i:
            name = _s(r.get("kanal")) or "Belirtilmemiş"
            channels[name] = channels.get(name, 0.0) + q
            last36 += q
    sold = [b for b in by_code.values() if b["lines"] > 0]
    xs = [b["firstYear"] for b in sold]
    p25, p50, p75 = (percentile(xs, q) for q in (0.25, 0.5, 0.75))
    top_q = [b for b in sold if p75 is not None and b["firstYear"] >= p75]
    series: dict[str, int] = {}
    for b in top_q:
        if b["series"]:
            series[b["series"]] = series.get(b["series"], 0) + 1
    best_series = max(series.items(), key=lambda kv: (kv[1], kv[0])) if series else None
    curve = []
    for k in range(FIRST_YEAR_MONTHS):
        vals = [b["curve"][k] for b in sold]
        curve.append(round(percentile(vals, 0.5) or 0.0, 1))
    baz = p50
    rounded = int(math.ceil(baz / PRINT_STEP) * PRINT_STEP) if baz and baz > 0 else None
    books_out = sorted(({"id": b["id"], "title": b["title"], "author": b["author"], "series": b["series"], "code": b["code"],
                         "firstPublish": b["first"].isoformat(), "firstYear": round(b["firstYear"]), "sold": b["lines"] > 0}
                        for b in by_code.values()), key=lambda x: (-x["firstYear"], x["title"] or ""))
    total_ch = sum(channels.values())
    return {
        "books": len(by_code), "withSales": len(sold), "withoutSales": len(by_code) - len(sold),
        "firstYear": {"p25": _r(p25), "p50": _r(p50), "p75": _r(p75), "mean": _r(sum(xs) / len(xs)) if xs else None,
                      "min": _r(min(xs)) if xs else None, "max": _r(max(xs)) if xs else None},
        "scenarios": {"kotumser": _r(p25), "baz": _r(p50), "iyimser": _r(p75)},
        "printRun": {"suggested": rounded, "step": PRINT_STEP,
                     "basis": "Baz senaryonun (ortanca ilk yıl satışı) 500'lük üst yuvarlaması"},
        "series": {"name": best_series[0], "count": best_series[1], "of": len(top_q)} if best_series else None,
        "curve": curve,
        "channels": sorted(({"name": k, "qty": round(v), "share": round(v / total_ch * 100, 1) if total_ch else None}
                            for k, v in channels.items()), key=lambda x: -x["qty"]),
        "last36": round(last36),
        "list": books_out,
    }


def _r(v: Optional[float]) -> Optional[int]:
    return None if v is None else int(round(v))


def market(category_id: str, category_name: str, schema: str, crm: Any, logo: Any, today: date) -> dict[str, Any]:
    """Kategori için pazar özeti: CRM'den küme, Logo'dan yıl yıl satış. `crm`/`logo`: connector (execute)."""
    start, end = window(today)
    t0 = time.monotonic()
    _, books, trunc = crm.execute(cohort_sql(schema, category_id, start, end), 1_000_000)
    if trunc:
        raise MarketError("Kategori kitap listesi eksik okundu; rapor üretilmedi.")
    codes = sorted({str(b.get("kod")).strip() for b in books if _s(b.get("kod"))})
    crm_ms = int((time.monotonic() - t0) * 1000)
    sales: list[dict[str, Any]] = []
    missing: list[int] = []
    t1 = time.monotonic()
    if codes:
        _, views, _ = logo.execute(sales_views_sql(), 500)
        present = {int(str(v.get("name"))[-4:]) for v in views}
        for y in range(start.year, today.year + 1):
            if y not in present:
                missing.append(y)
                continue
            for i in range(0, len(codes), CODE_CHUNK):
                _, rows, trunc = logo.execute(sales_sql(y, codes[i:i + CODE_CHUNK]), 5_000_000)
                if trunc:
                    raise MarketError("Satış satırları eksik okundu; rapor üretilmedi.")
                sales.extend(rows)
    out = compute(books, sales, today)
    out.update(categoryId=category_id, categoryName=category_name, window={"from": start.isoformat(), "to": end.isoformat()},
               cohortMonths=COHORT_MONTHS, firstYearMonths=FIRST_YEAR_MONTHS, missingYears=missing,
               computedAt=datetime.now(timezone.utc).isoformat(), timings={"crmMs": crm_ms, "logoMs": int((time.monotonic() - t1) * 1000)},
               source="CRM kitap kartı (kitaplık, ilk yayın, stok kodu) + Logo yıllık satış görünümleri")
    return out


def overlap_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        d = _day(r.get("ilk"))
        out.append({"id": _s(r.get("id")), "title": _s(r.get("ad")), "author": _s(r.get("yazar")),
                    "category": _s(r.get("kitaplik")), "firstPublish": d.isoformat() if d else None,
                    "matches": int(r.get("puan") or 0), "ownWork": bool(int(r.get("yazarin") or 0))})
    return out


# --------------------------------------------------------------------------------------------------- rapor

def build_report(snap: dict[str, Any], mkt: Optional[dict[str, Any]], overlap: Optional[list[dict[str, Any]]],
                 author_crm: Optional[dict[str, Any]], problems: list[str], by: str) -> dict[str, Any]:
    """Yayın Kurulu Raporu (dondurulmuş): YAZAR · KİTAP · KATEGORİ · 1 yıllık satış tahmini · editör değerlendirmesi."""
    a, e = snap["app"], snap.get("evaluation")
    crm_works = None
    if author_crm:
        works = author_crm.get("works") or []
        roles: dict[str, int] = {}
        for w in works:
            roles[w.get("role") or "Belirtilmemiş"] = roles.get(w.get("role") or "Belirtilmemiş", 0) + 1
        crm_works = {"contactId": author_crm.get("id"), "name": author_crm.get("name"), "bio": author_crm.get("bio"),
                     "works": works, "roles": [{"role": k, "count": v} for k, v in sorted(roles.items(), key=lambda kv: -kv[1])],
                     "contracts": len(author_crm.get("contracts") or []), "projects": len(author_crm.get("projects") or [])}
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(), "generatedBy": by,
        "author": {"name": a["authorName"], "bio": a["authorBio"], "expertise": a["authorExpertise"],
                   "history": a["authorHistory"], "agency": a["agencyName"], "crm": crm_works},
        "book": {"no": a["no"], "title": a["title"], "summary": a["summary"], "audience": a["audienceLabel"],
                 "ageFrom": a["ageFrom"], "ageTo": a["ageTo"], "pages": a["pageEstimate"], "genre": a["genre"],
                 "series": a["series"], "publisherNote": a["publisherNote"], "channel": a["channelLabel"],
                 "receivedOn": a["receivedOn"]},
        "category": {"id": a["categoryId"], "name": a["categoryName"],
                     "seriesSuggestion": (mkt or {}).get("series"), "applicantSeries": a["series"],
                     "printRun": (mkt or {}).get("printRun")},
        "market": mkt,
        "overlap": overlap,
        "evaluation": e,
        "problems": problems,
    }


# --------------------------------------------------------------------------------------- arka plan işi

class ReportRunner:
    """Rapor hazırlığı arka planda, sırayla (Logo'ya aynı anda tek ağır okuma). İstek beklemez."""

    def __init__(self) -> None:
        self._gate = threading.Lock()

    def start(self, fn: Callable[[], None], name: str) -> None:
        def run() -> None:
            with self._gate:
                try:
                    fn()
                except Exception:  # noqa: BLE001 — fn kendi hatasını rapora yazar; buraya düşen günlüğe
                    log.exception("kurul raporu işi düştü: %s", name)
        threading.Thread(target=run, name=f"kurul-raporu-{name}", daemon=True).start()
