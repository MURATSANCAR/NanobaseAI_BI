"""Editoryal süreç (M1–M8). İlk parça M6 Telif & Sözleşme: CRM'deki sözleşme portföyü.

Buradaki her sayı CRM'den okunur (`new_sozlesmeBase`, `new_sozlesmetarafiBase`, `new_new_sozlesme_new_kitapBase`). CRM'de kaydı olmayan
şey (hakediş, ödeme takvimi, satışa göre kümülatif telif) burada üretilmez; ekran o kartı göstermez.

2026-09-20'de doğrudan CRM'de ölçüldü: telif kademesi tablosu (`new_teliftanimBase`, 89 satır, son
değişiklik 2018) hiçbir sözleşmeye bağlı değil, taraf tipi 16.442 tarafın 7'sinde dolu,
`new_teliftanimtipi` hiç dolu değil; bu üçü okunmaz. `new_SozlemeninSahibi` yazar değil, sözleşmenin
Timaş tarafındaki şirkettir; hak sahibi taraf kaydındaki kişi/firmadır.

Sorgular köprünün `run_sql` yolundan geçer: yalnız SELECT, yalnız katalogdaki tablolar, CRM bağlantısı
`Timas_MSCRM.dbo.` önekinden seçilir. Parametre bağlama olmadığı için kullanıcıdan gelen tek serbest
metin (arama) `_like` ile kaçışlanır; kimlikler GUID biçimine, kodlar tamsayıya zorlanır.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")

PAGE_SIZE = 50

#: Yürürlükte sayılan durum açıklamaları (statuscode): Aktif - Sözleşme, Aktif (Proje), Aktif - Yenileme.
ACTIVE_STATUS = (100000000, 100000006, 100000007)
RENEWAL_STATUS = 100000007


class EditorialError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise EditorialError(f"CRM şeması «{schema}» geçerli bir ad değil.", 503)
    if not sch:
        raise EditorialError("CRM şeması girilmemiş; sözleşmeler okunamıyor.", 503)
    return (f"{db}." if db else "") + f"{sch}."


def _like(text: str) -> str:
    """Arama metni → LIKE kalıbı. Tek tırnak ve LIKE özel karakterleri kaçışlanır."""
    t = (text or "").strip()[:80]
    t = t.replace("'", "''")
    for ch in ("[", "%", "_"):
        t = t.replace(ch, f"[{ch}]")
    return t


def _guid(value: str) -> str:
    if not _GUID.match(value or ""):
        raise EditorialError("Sözleşme kimliği geçerli değil.")
    return value


def _where(p: str, *, q: str = "", status: Optional[int] = None, kind: Optional[int] = None,
           expiring_days: Optional[int] = None) -> str:
    parts = ["s.statecode = 0"]
    if status is not None:
        parts.append(f"s.statuscode = {int(status)}")
    if kind is not None:
        parts.append(f"s.new_SozlesmeTipi = {int(kind)}")
    if expiring_days is not None:
        parts.append(_expiring(int(expiring_days)))
    if q.strip():
        k = _like(q)
        parts.append(
            f"(s.new_name LIKE N'%{k}%' OR s.new_SozlesmeKodu LIKE N'%{k}%'"
            f" OR EXISTS (SELECT 1 FROM {p}new_new_sozlesme_new_kitapBase sk"
            f" JOIN {p}new_kitapBase k ON k.new_kitapId = sk.new_kitapid"
            f" WHERE sk.new_sozlesmeid = s.new_sozlesmeId AND k.new_name LIKE N'%{k}%')"
            f" OR EXISTS (SELECT 1 FROM {p}new_sozlesmetarafiBase t"
            f" LEFT JOIN {p}ContactBase c ON c.ContactId = t.new_kisi"
            f" LEFT JOIN {p}AccountBase a ON a.AccountId = t.new_Firma"
            f" WHERE t.new_sozlesmeid = s.new_sozlesmeId AND t.statecode = 0"
            f" AND (c.FullName LIKE N'%{k}%' OR a.Name LIKE N'%{k}%')))"
        )
    return " AND ".join(parts)


def _expiring(days: int) -> str:
    active = ", ".join(str(c) for c in ACTIVE_STATUS)
    return (
        f"s.statuscode IN ({active}) AND ISNULL(s.new_suresizsozlesme, 0) = 0"
        " AND s.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date)"
        f" AND s.new_SozlesmeBitisTarihi < DATEADD(day, {days + 1}, CAST(GETDATE() AS date))"
    )


def summary_sql(schema: str, warn_days: int) -> str:
    p = _prefix(schema)
    active = ", ".join(str(c) for c in ACTIVE_STATUS)
    return (
        "SELECT COUNT(*) AS toplam,"
        f" SUM(CASE WHEN s.statuscode IN ({active}) THEN 1 ELSE 0 END) AS yururlukte,"
        f" SUM(CASE WHEN s.statuscode = {RENEWAL_STATUS} THEN 1 ELSE 0 END) AS yenilemede,"
        f" SUM(CASE WHEN {_expiring(warn_days)} THEN 1 ELSE 0 END) AS yaklasan,"
        f" AVG(CASE WHEN s.statuscode IN ({active}) AND s.new_Telif > 0 THEN s.new_Telif END) AS ort_telif,"
        f" SUM(CASE WHEN s.statuscode IN ({active}) AND s.new_Telif > 0 THEN 1 ELSE 0 END) AS telif_dolu"
        f" FROM {p}new_sozlesmeBase s WHERE s.statecode = 0"
    )


def facet_sql(schema: str, column: str) -> str:
    """Süzgeç seçenekleri: kod, etiketi ve adedi. Etiketi köprü katalogdan yazar; yalın kolon
    etiketlenir, CAST edilmiş kopyası kod olarak kalır."""
    if column not in ("statuscode", "new_SozlesmeTipi"):
        raise EditorialError("Bilinmeyen süzgeç.")
    p = _prefix(schema)
    return (
        f"SELECT s.{column}, CAST(s.{column} AS int) AS kod, COUNT(*) AS n"
        f" FROM {p}new_sozlesmeBase s WHERE s.statecode = 0 AND s.{column} IS NOT NULL"
        f" GROUP BY s.{column} ORDER BY COUNT(*) DESC"
    )


def count_sql(schema: str, **flt: Any) -> str:
    p = _prefix(schema)
    return f"SELECT COUNT(*) AS n FROM {p}new_sozlesmeBase s WHERE {_where(p, **flt)}"


def list_sql(schema: str, page: int, *, order: str = "bitis", **flt: Any) -> str:
    p = _prefix(schema)
    by = {
        "bitis": "CASE WHEN s.new_SozlesmeBitisTarihi IS NULL THEN 1 ELSE 0 END, s.new_SozlesmeBitisTarihi, s.new_sozlesmeId",
        "yeni": "s.ModifiedOn DESC, s.new_sozlesmeId",
    }.get(order, "s.new_name, s.new_sozlesmeId")
    return (
        "SELECT s.new_sozlesmeId, s.new_name, s.new_SozlesmeKodu, s.new_SozlesmeTipi, s.new_TelifTipi,"
        " s.new_telifturu, s.new_Telif, s.new_sertkapaktelif, s.new_e_kitap_telif,"
        " s.new_SesliKitap, s.new_yurtdisitelif, s.new_sozlesmeparabirimi, s.new_sozlesmeavanstutari,"
        " s.new_SozlesmeBaslangicTarihi, s.new_SozlesmeBitisTarihi, s.new_SozlesmeSuresiYil,"
        " s.new_suresizsozlesme, s.statuscode, s.new_sozlesmestatusu, s.ModifiedOn,"
        " DATEDIFF(day, CAST(GETDATE() AS date), s.new_SozlesmeBitisTarihi) AS kalan_gun"
        f" FROM {p}new_sozlesmeBase s WHERE {_where(p, **flt)}"
        f" ORDER BY {by} OFFSET {max(0, int(page)) * PAGE_SIZE} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY"
    )


def _in(ids: list[str]) -> str:
    return ", ".join(f"'{_guid(i)}'" for i in ids)


def books_sql(schema: str, ids: list[str]) -> str:
    p = _prefix(schema)
    return (
        "SELECT sk.new_sozlesmeid, k.new_kitapId, k.new_name"
        f" FROM {p}new_new_sozlesme_new_kitapBase sk JOIN {p}new_kitapBase k ON k.new_kitapId = sk.new_kitapid"
        f" WHERE sk.new_sozlesmeid IN ({_in(ids)}) ORDER BY k.new_name"
    )


def parties_sql(schema: str, ids: list[str]) -> str:
    p = _prefix(schema)
    return (
        "SELECT t.new_sozlesmeid, c.FullName AS kisi, a.Name AS firma,"
        " t.new_Odeme, t.new_yurticiyurtdisi, t.new_aracivarmi"
        f" FROM {p}new_sozlesmetarafiBase t"
        f" LEFT JOIN {p}ContactBase c ON c.ContactId = t.new_kisi"
        f" LEFT JOIN {p}AccountBase a ON a.AccountId = t.new_Firma"
        f" WHERE t.statecode = 0 AND t.new_sozlesmeid IN ({_in(ids)})"
        " ORDER BY t.new_Odeme DESC"
    )



# ---------------------------------------------------------------------------------------------- biçim

def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    t = str(v).strip()
    return t or None


def _n(v: Any) -> Optional[float]:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _date(v: Any) -> Optional[str]:
    t = _s(v)
    return t[:10] if t else None


def _rates(r: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for key, name in (("new_Telif", "Karton kapak"), ("new_sertkapaktelif", "Sert kapak"),
                      ("new_e_kitap_telif", "E-kitap"), ("new_SesliKitap", "Sesli kitap"),
                      ("new_yurtdisitelif", "Yurtdışı")):
        n = _n(r.get(key))
        if n:
            out.append({"format": name, "percent": n})
    return out


def contract(r: dict[str, Any]) -> dict[str, Any]:
    days = _n(r.get("kalan_gun"))
    return {
        "id": _s(r.get("new_sozlesmeId")),
        "no": _s(r.get("new_name")),
        "code": _s(r.get("new_SozlesmeKodu")),
        "kind": _s(r.get("new_SozlesmeTipi")),
        "payment": _s(r.get("new_TelifTipi")),
        "basis": _s(r.get("new_telifturu")),
        "rates": _rates(r),
        "currency": _s(r.get("new_sozlesmeparabirimi")),
        "advance": _n(r.get("new_sozlesmeavanstutari")) or None,
        "start": _date(r.get("new_SozlesmeBaslangicTarihi")),
        "end": _date(r.get("new_SozlesmeBitisTarihi")),
        "years": _n(r.get("new_SozlesmeSuresiYil")),
        "openEnded": str(r.get("new_suresizsozlesme")).strip().lower() in ("1", "true", "evet"),
        "status": _s(r.get("statuscode")),
        "stage": _s(r.get("new_sozlesmestatusu")),
        "daysLeft": None if days is None else int(days),
        "modifiedOn": _s(r.get("ModifiedOn")),
        "books": [],
        "parties": [],
    }


def page(schema: str, run: Callable[[str], dict[str, Any]], page_no: int, *, order: str, **flt: Any) -> dict[str, Any]:
    """Bir sayfa sözleşme: kayıtlar, o sayfanın kitapları ve tarafları, süzgece uyan toplam sayı."""
    total = int(_n((run(count_sql(schema, **flt)).get("records") or [{}])[0].get("n")) or 0)
    res = run(list_sql(schema, page_no, order=order, **flt))
    items = [contract(r) for r in res.get("records") or []]
    by_id = {c["id"].lower(): c for c in items if c["id"]}
    if by_id:
        ids = [c["id"] for c in items if c["id"]]
        for b in run(books_sql(schema, ids)).get("records") or []:
            c = by_id.get(str(b.get("new_sozlesmeid") or "").lower())
            if c is not None and _s(b.get("new_name")):
                c["books"].append({"id": _s(b.get("new_kitapId")), "title": _s(b.get("new_name"))})
        for t in run(parties_sql(schema, ids)).get("records") or []:
            c = by_id.get(str(t.get("new_sozlesmeid") or "").lower())
            name = _s(t.get("kisi")) or _s(t.get("firma"))
            if c is not None and name:
                c["parties"].append({
                    "name": name, "share": _n(t.get("new_Odeme")),
                    "scope": _s(t.get("new_yurticiyurtdisi")),
                    "viaAgent": str(t.get("new_aracivarmi")).strip().lower() in ("1", "true", "evet"),
                })
    return {"items": items, "total": total, "page": max(0, int(page_no)), "pageSize": PAGE_SIZE, "db": _timing(res)}


def summary(schema: str, run: Callable[[str], dict[str, Any]], warn_days: int) -> dict[str, Any]:
    res = run(summary_sql(schema, warn_days))
    r = (res.get("records") or [{}])[0]
    return {
        "total": int(_n(r.get("toplam")) or 0),
        "active": int(_n(r.get("yururlukte")) or 0),
        "renewal": int(_n(r.get("yenilemede")) or 0),
        "expiring": int(_n(r.get("yaklasan")) or 0),
        "warnDays": warn_days,
        "avgRoyalty": _n(r.get("ort_telif")),
        "avgRoyaltyOver": int(_n(r.get("telif_dolu")) or 0),
        "statuses": _facet(run(facet_sql(schema, "statuscode")), "statuscode"),
        "kinds": _facet(run(facet_sql(schema, "new_SozlesmeTipi")), "new_SozlesmeTipi"),
        "db": _timing(res),
    }



def _facet(res: dict[str, Any], column: str) -> list[dict[str, Any]]:
    return [{"code": int(_n(r.get("kod")) or 0), "label": _s(r.get(column)), "count": int(_n(r.get("n")) or 0)}
            for r in res.get("records") or []]


def _timing(res: dict[str, Any]) -> dict[str, Any]:
    return {"dbMs": res.get("dbMs"), "cached": bool(res.get("cached")), "computedAt": res.get("computedAt")}
