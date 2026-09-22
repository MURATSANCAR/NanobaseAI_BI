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

import html
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


def _plain(v: Any) -> Optional[str]:
    """CRM zengin metin alanları HTML tutar (<p>, &uuml;); ekranda düz paragraflar gösterilir."""
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|li)>", "\n", str(v or ""))
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("\xa0", " ")
    return "\n".join(x for x in (re.sub(r"[ \t]+", " ", ln).strip() for ln in t.splitlines()) if x) or None


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


# ============================================================================== M1 Yayın Kurulu
# Kurul kararı CRM'de `new_yayinkurulutoplantilariBase` satırıdır: bir toplantı tarihinde bir proje için
# verilen karar, notu ve önerileri. Proje `new_YaynKuruluToplantlarId` ile bağlanır (adı yanıltıcı; 499
# kaydın 491'i `new_projeBase` ile eşleşir). Kurul üyelerinin görüşü `new_projegrBase`
# (`new_kitapprojesiid` → proje, yazan `OwnerId`). 2026-09-20'de ölçüldü: başvuru tablosu
# (`new_dosyabasvuruBase`, 19 satır, son kayıt 2024) kullanılmıyor; projedeki kurul tarihi alanları boş.

def _board_where(p: str, *, q: str = "", year: Optional[int] = None, decision: Optional[int] = None) -> str:
    parts = ["t.statecode = 0"]
    if year is not None:
        parts.append(f"YEAR(t.new_toplantitarihi) = {int(year)}")
    if decision is not None:
        parts.append(f"t.statuscode = {int(decision)}")
    if q.strip():
        k = _like(q)
        parts.append(f"(p.new_name LIKE N'%{k}%' OR t.new_toplantikararnotu LIKE N'%{k}%' OR u.FullName LIKE N'%{k}%')")
    return " AND ".join(parts)


def _board_from(p: str) -> str:
    return (
        f" FROM {p}new_yayinkurulutoplantilariBase t"
        f" LEFT JOIN {p}new_projeBase p ON p.new_projeId = t.new_YaynKuruluToplantlarId"
        f" LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = t.new_Editoru"
    )


def board_decisions_sql(schema: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT YEAR(t.new_toplantitarihi) AS yil, t.statuscode, CAST(t.statuscode AS int) AS kod, COUNT(*) AS n"
        f" FROM {p}new_yayinkurulutoplantilariBase t WHERE t.statecode = 0 AND t.new_toplantitarihi IS NOT NULL"
        " GROUP BY YEAR(t.new_toplantitarihi), t.statuscode ORDER BY YEAR(t.new_toplantitarihi) DESC"
    )


def board_sessions_sql(schema: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT YEAR(t.new_toplantitarihi) AS yil, COUNT(DISTINCT CAST(t.new_toplantitarihi AS date)) AS oturum,"
        " MAX(t.new_toplantitarihi) AS son"
        f" FROM {p}new_yayinkurulutoplantilariBase t WHERE t.statecode = 0 AND t.new_toplantitarihi IS NOT NULL"
        " GROUP BY YEAR(t.new_toplantitarihi) ORDER BY YEAR(t.new_toplantitarihi) DESC"
    )


def board_count_sql(schema: str, **flt: Any) -> str:
    p = _prefix(schema)
    return f"SELECT COUNT(*) AS n{_board_from(p)} WHERE {_board_where(p, **flt)}"


def board_list_sql(schema: str, page: int, **flt: Any) -> str:
    p = _prefix(schema)
    return (
        "SELECT t.new_yayinkurulutoplantilariId, t.new_toplantitarihi, t.statuscode, t.new_toplantikararnotu,"
        " t.new_onerilenteliforani, t.new_avansbedeli, t.new_Yaynkurulubaskiadedi, t.new_onerilenyayintarihi,"
        " p.new_projeId, p.new_name AS proje, u.FullName AS editor"
        f"{_board_from(p)} WHERE {_board_where(p, **flt)}"
        " ORDER BY t.new_toplantitarihi DESC, p.new_name, t.new_yayinkurulutoplantilariId"
        f" OFFSET {max(0, int(page)) * PAGE_SIZE} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY"
    )


def opinions_sql(schema: str, project_ids: list[str]) -> str:
    p = _prefix(schema)
    return (
        "SELECT g.new_kitapprojesiid, g.new_GenelKanaat, g.new_SatTahmini, g.new_lkBaskAdedinerisi, g.new_Fiyatnerisi,"
        " g.new_BaskAynerisi, g.new_ProjeHakkndaDierGrler, g.new_simnerisi, g.CreatedOn, w.FullName AS yazan"
        f" FROM {p}new_projegrBase g LEFT JOIN {p}SystemUserBase w ON w.SystemUserId = g.OwnerId"
        f" WHERE g.statecode = 0 AND g.new_kitapprojesiid IN ({_in(project_ids)}) ORDER BY g.CreatedOn"
    )


def board_summary(schema: str, run: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    res = run(board_decisions_sql(schema))
    years: dict[int, dict[str, Any]] = {}
    for r in res.get("records") or []:
        y = int(_n(r.get("yil")) or 0)
        row = years.setdefault(y, {"year": y, "total": 0, "sessions": 0, "last": None, "decisions": []})
        n = int(_n(r.get("n")) or 0)
        row["total"] += n
        row["decisions"].append({"code": int(_n(r.get("kod")) or 0), "label": _s(r.get("statuscode")), "count": n})
    for r in run(board_sessions_sql(schema)).get("records") or []:
        row = years.get(int(_n(r.get("yil")) or 0))
        if row is not None:
            row["sessions"] = int(_n(r.get("oturum")) or 0)
            row["last"] = _date(r.get("son"))
    for row in years.values():
        row["decisions"].sort(key=lambda d: -d["count"])
    return {"years": sorted(years.values(), key=lambda y: -y["year"]), "db": _timing(res)}


def board_page(schema: str, run: Callable[[str], dict[str, Any]], page_no: int, *, with_opinions: bool,
               **flt: Any) -> dict[str, Any]:
    total = int(_n((run(board_count_sql(schema, **flt)).get("records") or [{}])[0].get("n")) or 0)
    res = run(board_list_sql(schema, page_no, **flt))
    items = [{
        "id": _s(r.get("new_yayinkurulutoplantilariId")),
        "date": _date(r.get("new_toplantitarihi")),
        "decision": _s(r.get("statuscode")),
        "note": _s(r.get("new_toplantikararnotu")),
        "royalty": _n(r.get("new_onerilenteliforani")) or None,
        "advance": _n(r.get("new_avansbedeli")) or None,
        "printRun": _s(r.get("new_Yaynkurulubaskiadedi")),
        "publishOn": _date(r.get("new_onerilenyayintarihi")),
        "projectId": _s(r.get("new_projeId")),
        "project": _s(r.get("proje")),
        "editor": _s(r.get("editor")),
        "opinions": [],
    } for r in res.get("records") or []]
    by_project: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        if it["projectId"]:
            by_project.setdefault(it["projectId"].lower(), []).append(it)
    if by_project and with_opinions:
        ids = sorted({it["projectId"] for it in items if it["projectId"]})
        for g in run(opinions_sql(schema, ids)).get("records") or []:
            opinion = {
                "by": _s(g.get("yazan")), "verdict": _s(g.get("new_GenelKanaat")), "sales": _s(g.get("new_SatTahmini")),
                "printRun": _s(g.get("new_lkBaskAdedinerisi")), "price": _n(g.get("new_Fiyatnerisi")) or None,
                "month": _s(g.get("new_BaskAynerisi")), "text": _s(g.get("new_ProjeHakkndaDierGrler")),
                "titleIdea": _s(g.get("new_simnerisi")), "on": _date(g.get("CreatedOn")),
            }
            for it in by_project.get(str(g.get("new_kitapprojesiid") or "").lower(), []):
                it["opinions"].append(opinion)
    return {"items": items, "total": total, "page": max(0, int(page_no)), "pageSize": PAGE_SIZE,
            "opinionsVisible": with_opinions, "db": _timing(res)}


# ==================================================== M7 / M8 / M4: esere katkı verenler (rol bazlı)
# `new_eserkatilimBase` bir kitaba bir kişinin bir rolle katkısıdır: kişi `new_Katilimsaglayan` →
# ContactBase (2026-09-20: 36.323 kaydın tamamı eşleşiyor), rol `new_katilimciTipi` →
# `new_katilimcitipiBase.new_name` (Yazar, Çizer, Tercüme, Kapak Tasarım, Redaktör…), kitap `new_Kitap`.
# Yazarlar (M7), çevirmenler (M4) ve çizer/serbest çalışanlar (M8) aynı kayıttan, rol süzgeciyle okunur.
# Kapasite, puan, hız, müsaitlik CRM'de yok; üretilmez.

def _roles(names: list[str]) -> str:
    clean = [n.strip()[:60].replace("'", "''") for n in names if n and n.strip()]
    if not clean:
        raise EditorialError("En az bir rol gerekli.")
    return ", ".join(f"N'{n}'" for n in clean)


def _contrib_from(p: str, roles: list[str], q: str) -> str:
    sql = (
        f" FROM {p}new_eserkatilimBase e"
        f" JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        f" JOIN {p}ContactBase k ON k.ContactId = e.new_Katilimsaglayan"
        f" WHERE e.statecode = 0 AND t.new_name IN ({_roles(roles)})"
    )
    if q.strip():
        sql += f" AND k.FullName LIKE N'%{_like(q)}%'"
    return sql


def contributors_count_sql(schema: str, roles: list[str], q: str = "") -> str:
    p = _prefix(schema)
    return (
        "SELECT COUNT(*) AS n, SUM(x.son12) AS son12_kisi, SUM(x.eser) AS katki FROM ("
        "SELECT k.ContactId, COUNT(DISTINCT e.new_Kitap) AS eser,"
        " MAX(CASE WHEN e.CreatedOn >= DATEADD(month, -12, GETDATE()) THEN 1 ELSE 0 END) AS son12"
        f"{_contrib_from(p, roles, q)} GROUP BY k.ContactId) x"
    )


def contributors_list_sql(schema: str, roles: list[str], page: int, q: str = "", order: str = "son") -> str:
    p = _prefix(schema)
    by = {"son": "MAX(e.CreatedOn) DESC", "eser": "COUNT(DISTINCT e.new_Kitap) DESC", "ad": "k.FullName"}.get(order, "MAX(e.CreatedOn) DESC")
    return (
        "SELECT k.ContactId, k.FullName, COUNT(DISTINCT e.new_Kitap) AS eser, MAX(e.CreatedOn) AS son,"
        " COUNT(DISTINCT CASE WHEN e.CreatedOn >= DATEADD(month, -12, GETDATE()) THEN e.new_Kitap END) AS son12"
        f"{_contrib_from(p, roles, q)} GROUP BY k.ContactId, k.FullName"
        f" ORDER BY {by}, k.ContactId OFFSET {max(0, int(page)) * PAGE_SIZE} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY"
    )


def contributor_roles_sql(schema: str, ids: list[str]) -> str:
    p = _prefix(schema)
    return (
        "SELECT e.new_Katilimsaglayan, t.new_name AS rol, COUNT(DISTINCT e.new_Kitap) AS eser"
        f" FROM {p}new_eserkatilimBase e JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        f" WHERE e.statecode = 0 AND e.new_Katilimsaglayan IN ({_in(ids)})"
        " GROUP BY e.new_Katilimsaglayan, t.new_name ORDER BY COUNT(DISTINCT e.new_Kitap) DESC"
    )


def role_facet_sql(schema: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT t.new_name AS rol, COUNT(*) AS kayit, COUNT(DISTINCT e.new_Katilimsaglayan) AS kisi"
        f" FROM {p}new_eserkatilimBase e JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        " WHERE e.statecode = 0 AND e.new_Katilimsaglayan IS NOT NULL GROUP BY t.new_name ORDER BY COUNT(*) DESC"
    )


def person_sql(schema: str, contact_id: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT k.ContactId, k.FullName, k.new_kisaozgecmis, k.new_ozgecmis, k.new_yazarmi"
        f" FROM {p}ContactBase k WHERE k.ContactId = '{_guid(contact_id)}'"
    )


def person_works_sql(schema: str, contact_id: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT b.new_kitapId, b.new_name AS kitap, t.new_name AS rol, e.CreatedOn"
        f" FROM {p}new_eserkatilimBase e JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        f" LEFT JOIN {p}new_kitapBase b ON b.new_kitapId = e.new_Kitap"
        f" WHERE e.statecode = 0 AND e.new_Katilimsaglayan = '{_guid(contact_id)}' ORDER BY e.CreatedOn DESC"
    )


def person_contracts_sql(schema: str, contact_id: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT s.new_sozlesmeId, s.new_name, s.statuscode, s.new_SozlesmeBaslangicTarihi, s.new_SozlesmeBitisTarihi,"
        " s.new_Telif, t.new_Odeme"
        f" FROM {p}new_sozlesmetarafiBase t JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = t.new_sozlesmeid"
        f" WHERE t.statecode = 0 AND s.statecode = 0 AND t.new_kisi = '{_guid(contact_id)}'"
        " ORDER BY s.new_SozlesmeBitisTarihi DESC"
    )


def person_projects_sql(schema: str, contact_id: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT j.new_projeId, j.new_name, j.statuscode, j.new_icerikdurumu, j.CreatedOn, u.FullName AS editor"
        f" FROM {p}new_projeBase j LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = j.new_editoru"
        f" WHERE j.statecode = 0 AND j.new_OlasYazarYazar = '{_guid(contact_id)}' ORDER BY j.CreatedOn DESC"
    )


def contributors_page(schema: str, run: Callable[[str], dict[str, Any]], roles: list[str], page_no: int, *,
                      q: str = "", order: str = "son") -> dict[str, Any]:
    head = (run(contributors_count_sql(schema, roles, q)).get("records") or [{}])[0]
    res = run(contributors_list_sql(schema, roles, page_no, q, order))
    items = [{
        "id": _s(r.get("ContactId")), "name": _s(r.get("FullName")), "works": int(_n(r.get("eser")) or 0),
        "recentWorks": int(_n(r.get("son12")) or 0), "last": _date(r.get("son")), "roles": [],
    } for r in res.get("records") or []]
    by_id = {c["id"].lower(): c for c in items if c["id"]}
    if by_id:
        for r in run(contributor_roles_sql(schema, [c["id"] for c in items if c["id"]])).get("records") or []:
            c = by_id.get(str(r.get("new_Katilimsaglayan") or "").lower())
            if c is not None and _s(r.get("rol")):
                c["roles"].append({"role": _s(r.get("rol")), "works": int(_n(r.get("eser")) or 0)})
    return {"items": items, "total": int(_n(head.get("n")) or 0), "activePeople": int(_n(head.get("son12_kisi")) or 0),
            "contributions": int(_n(head.get("katki")) or 0), "page": max(0, int(page_no)), "pageSize": PAGE_SIZE,
            "db": _timing(res)}


def role_facets(schema: str, run: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    res = run(role_facet_sql(schema))
    return {"items": [{"role": _s(r.get("rol")), "records": int(_n(r.get("kayit")) or 0), "people": int(_n(r.get("kisi")) or 0)}
                      for r in res.get("records") or []], "db": _timing(res)}


def person(schema: str, run: Callable[[str], dict[str, Any]], contact_id: str) -> dict[str, Any]:
    head = (run(person_sql(schema, contact_id)).get("records") or [None])[0]
    if head is None:
        raise EditorialError("Kişi bulunamadı.", 404)
    works = run(person_works_sql(schema, contact_id))
    return {
        "id": _s(head.get("ContactId")), "name": _s(head.get("FullName")),
        "bio": _s(head.get("new_kisaozgecmis")) or _s(head.get("new_ozgecmis")),
        "works": [{"bookId": _s(r.get("new_kitapId")), "title": _s(r.get("kitap")), "role": _s(r.get("rol")),
                   "on": _date(r.get("CreatedOn"))} for r in works.get("records") or []],
        "contracts": [{"id": _s(r.get("new_sozlesmeId")), "no": _s(r.get("new_name")), "status": _s(r.get("statuscode")),
                       "start": _date(r.get("new_SozlesmeBaslangicTarihi")), "end": _date(r.get("new_SozlesmeBitisTarihi")),
                       "royalty": _n(r.get("new_Telif")) or None, "share": _n(r.get("new_Odeme"))}
                      for r in run(person_contracts_sql(schema, contact_id)).get("records") or []],
        "projects": [{"id": _s(r.get("new_projeId")), "name": _s(r.get("new_name")), "status": _s(r.get("statuscode")),
                      "text": _s(r.get("new_icerikdurumu")), "on": _date(r.get("CreatedOn")), "editor": _s(r.get("editor"))}
                     for r in run(person_projects_sql(schema, contact_id)).get("records") or []],
        "truncated": bool(works.get("truncated")),
        "db": _timing(works),
    }


# ============================================================================ M2 editör ve projeler
# Projenin editörü `new_projeBase.new_editoru` → SystemUserBase (2024'ten beri 2.710 projenin 1.797'sinde
# dolu), proje editörü `new_uretimeditoru`. Aşama `statuscode` (Proje Durumu). İş planı aşaması, metin
# teslim ve yayın tarihi alanları neredeyse boş; takvim ve iş yükü yüzdesi CRM'den çıkarılamaz.

def _project_where(p: str, *, q: str = "", editor: Optional[str] = None, status: Optional[int] = None,
                   since_year: Optional[int] = None) -> str:
    parts = ["j.statecode = 0"]
    if editor:
        parts.append(f"j.new_editoru = '{_guid(editor)}'")
    if status is not None:
        parts.append(f"j.statuscode = {int(status)}")
    if since_year is not None:
        parts.append(f"j.CreatedOn >= '{int(since_year):04d}-01-01'")
    if q.strip():
        k = _like(q)
        parts.append(f"(j.new_name LIKE N'%{k}%' OR j.new_olasiyazartext LIKE N'%{k}%' OR a.FullName LIKE N'%{k}%')")
    return " AND ".join(parts)


def _project_from(p: str) -> str:
    return (
        f" FROM {p}new_projeBase j"
        f" LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = j.new_editoru"
        f" LEFT JOIN {p}SystemUserBase w ON w.SystemUserId = j.new_uretimeditoru"
        f" LEFT JOIN {p}ContactBase a ON a.ContactId = j.new_OlasYazarYazar"
    )


def editors_sql(schema: str, since_year: int) -> str:
    p = _prefix(schema)
    return (
        "SELECT u.SystemUserId, u.FullName, u.IsDisabled, j.statuscode, CAST(j.statuscode AS int) AS kod, COUNT(*) AS n,"
        " MAX(j.ModifiedOn) AS son"
        f" FROM {p}new_projeBase j JOIN {p}SystemUserBase u ON u.SystemUserId = j.new_editoru"
        f" WHERE j.statecode = 0 AND j.CreatedOn >= '{int(since_year):04d}-01-01'"
        " GROUP BY u.SystemUserId, u.FullName, u.IsDisabled, j.statuscode ORDER BY u.FullName"
    )


def unassigned_sql(schema: str, since_year: int) -> str:
    p = _prefix(schema)
    return (
        "SELECT j.statuscode, CAST(j.statuscode AS int) AS kod, COUNT(*) AS n"
        f" FROM {p}new_projeBase j WHERE j.statecode = 0 AND j.new_editoru IS NULL"
        f" AND j.CreatedOn >= '{int(since_year):04d}-01-01' GROUP BY j.statuscode ORDER BY COUNT(*) DESC"
    )


def projects_count_sql(schema: str, **flt: Any) -> str:
    p = _prefix(schema)
    return f"SELECT COUNT(*) AS n{_project_from(p)} WHERE {_project_where(p, **flt)}"


def projects_list_sql(schema: str, page: int, **flt: Any) -> str:
    p = _prefix(schema)
    return (
        "SELECT j.new_projeId, j.new_name, j.statuscode, j.new_icerikdurumu, j.new_isPlaniAsamasi,"
        " j.new_tahminimetinteslimtarihi, j.CreatedOn, j.ModifiedOn, j.new_olasiyazartext,"
        " u.FullName AS editor, w.FullName AS proje_editoru, a.FullName AS yazar"
        f"{_project_from(p)} WHERE {_project_where(p, **flt)}"
        f" ORDER BY j.ModifiedOn DESC, j.new_projeId OFFSET {max(0, int(page)) * PAGE_SIZE} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY"
    )


def editors(schema: str, run: Callable[[str], dict[str, Any]], since_year: int) -> dict[str, Any]:
    res = run(editors_sql(schema, since_year))
    people: dict[str, dict[str, Any]] = {}
    statuses: dict[int, dict[str, Any]] = {}
    for r in res.get("records") or []:
        uid = _s(r.get("SystemUserId")) or ""
        code, n = int(_n(r.get("kod")) or 0), int(_n(r.get("n")) or 0)
        row = people.setdefault(uid, {"id": uid, "name": _s(r.get("FullName")), "total": 0, "last": None, "byStatus": [],
                                      "disabled": str(r.get("IsDisabled")).strip().lower() in ("1", "true", "evet")})
        row["total"] += n
        row["byStatus"].append({"code": code, "label": _s(r.get("statuscode")), "count": n})
        last = _date(r.get("son"))
        if last and (row["last"] is None or last > row["last"]):
            row["last"] = last
        st = statuses.setdefault(code, {"code": code, "label": _s(r.get("statuscode")), "count": 0})
        st["count"] += n
    for row in people.values():
        row["byStatus"].sort(key=lambda s: -s["count"])
    unassigned = [{"code": int(_n(r.get("kod")) or 0), "label": _s(r.get("statuscode")), "count": int(_n(r.get("n")) or 0)}
                  for r in run(unassigned_sql(schema, since_year)).get("records") or []]
    return {"items": sorted(people.values(), key=lambda e: -e["total"]), "sinceYear": since_year,
            "statuses": sorted(statuses.values(), key=lambda s: -s["count"]), "unassigned": unassigned,
            "truncated": bool(res.get("truncated")), "db": _timing(res)}


def projects_page(schema: str, run: Callable[[str], dict[str, Any]], page_no: int, **flt: Any) -> dict[str, Any]:
    total = int(_n((run(projects_count_sql(schema, **flt)).get("records") or [{}])[0].get("n")) or 0)
    res = run(projects_list_sql(schema, page_no, **flt))
    items = [{
        "id": _s(r.get("new_projeId")), "name": _s(r.get("new_name")), "status": _s(r.get("statuscode")),
        "text": _s(r.get("new_icerikdurumu")), "stage": _s(r.get("new_isPlaniAsamasi")),
        "textDue": _date(r.get("new_tahminimetinteslimtarihi")), "createdOn": _date(r.get("CreatedOn")),
        "modifiedOn": _date(r.get("ModifiedOn")), "author": _s(r.get("yazar")) or _s(r.get("new_olasiyazartext")),
        "editor": _s(r.get("editor")), "projectEditor": _s(r.get("proje_editoru")),
    } for r in res.get("records") or []]
    return {"items": items, "total": total, "page": max(0, int(page_no)), "pageSize": PAGE_SIZE, "db": _timing(res)}


# ================================================== Kitap araması ve kitap 360 (editoryal ana ekran)
# Ana ekrandaki arama kutusuna yazılan metin kitap adında, yazar/katılımcı adında ve proje adında aranır.
# Kitap seçilince o kitabın bütün süreçleri tek ekranda toplanır: künye, roller, sözleşmeler, proje ve
# kurul kararı, üretim. Masadaki metin/prova kayıtları köprünün kendi tablolarından, ayrı okunur.

SEARCH_KINDS = ("kitap", "proje", "kisi")


def _digits(q: str) -> str:
    return re.sub(r"[^0-9Xx]", "", q or "").upper()


def search_sql(schema: str, q: str, kind: str, page: int = 0) -> str:
    """Bir türün bir sayfası; `toplam` o türde eşleşen bütün kayıtların sayısıdır (sessiz tavan yok).
    Kitap adı üç alanda (kayıt adı, kitap adı, ürün adı) aranır; en az 5 rakamlı metin ISBN'de de aranır."""
    p = _prefix(schema)
    k = _like(q)
    if not k.strip():
        raise EditorialError("Arama metni gerekli.")
    if kind not in SEARCH_KINDS:
        raise EditorialError("Bilinmeyen arama türü.")
    off = f" OFFSET {max(0, int(page)) * PAGE_SIZE} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY"
    if kind == "kitap":
        match = [f"b.new_name LIKE N'%{k}%'", f"b.new_KitabnAd LIKE N'%{k}%'", f"b.new_urunadi LIKE N'%{k}%'"]
        d = _digits(q)
        if len(d) >= 5:
            for col in ("new_isbn13", "new_isbn", "new_ekitapisbn"):
                match.append(f"REPLACE(REPLACE(ISNULL(b.{col}, ''), '-', ''), ' ', '') LIKE '%{d}%'")
        return (
            "SELECT 'kitap' AS tur, b.new_kitapId AS id, b.new_name AS ad, b.new_isbn13 AS ek1, b.new_turlertext AS ek2,"
            " b.statuscode AS durum, b.new_ilkyayintarihi AS tarih, COUNT(*) OVER () AS toplam"
            f" FROM {p}new_kitapBase b WHERE b.statecode = 0 AND ({' OR '.join(match)})"
            f" ORDER BY b.new_name, b.new_kitapId{off}"
        )
    if kind == "proje":
        return (
            "SELECT 'proje' AS tur, j.new_projeId AS id, j.new_name AS ad, j.new_olasiyazartext AS ek1, NULL AS ek2,"
            " j.statuscode AS durum, j.CreatedOn AS tarih, COUNT(*) OVER () AS toplam"
            f" FROM {p}new_projeBase j WHERE j.statecode = 0 AND j.new_name LIKE N'%{k}%'"
            f" ORDER BY j.CreatedOn DESC, j.new_projeId{off}"
        )
    return (
        "SELECT 'kisi' AS tur, c.ContactId AS id, c.FullName AS ad, NULL AS ek1, NULL AS ek2, NULL AS durum, NULL AS tarih,"
        " COUNT(*) OVER () AS toplam"
        f" FROM {p}ContactBase c WHERE c.statecode = 0 AND c.FullName LIKE N'%{k}%'"
        f" AND EXISTS (SELECT 1 FROM {p}new_eserkatilimBase e WHERE e.new_Katilimsaglayan = c.ContactId AND e.statecode = 0)"
        f" ORDER BY c.FullName, c.ContactId{off}"
    )


def books_by_person_sql(schema: str, contact_id: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT DISTINCT b.new_kitapId AS id, b.new_name AS ad, b.new_isbn13 AS ek1, t.new_name AS ek2,"
        " b.statuscode AS durum, b.new_ilkyayintarihi AS tarih"
        f" FROM {p}new_eserkatilimBase e JOIN {p}new_kitapBase b ON b.new_kitapId = e.new_Kitap"
        f" JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        f" WHERE e.statecode = 0 AND b.statecode = 0 AND e.new_Katilimsaglayan = '{_guid(contact_id)}'"
        " ORDER BY b.new_ilkyayintarihi DESC"
    )


def book_sql(schema: str, book_id: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT b.new_kitapId, b.new_name, b.new_isbn13, b.new_isbn, b.new_ekitapisbn, b.new_sayfasayisi, b.new_Ebat,"
        " b.new_kdvdahilfiyat, b.new_PerakendeBirimFiyat, b.new_baskisayisi, b.new_baskitoplamadedi, b.new_nihaibaskiadeti,"
        " b.new_ilkyayintarihi, b.new_sonyayintarihi, b.new_baskitarihi, b.new_turlertext, b.new_rafturu, b.new_orijinaldil,"
        " b.new_telifdurum, b.new_BaskiDurumu, b.statuscode, b.new_cizerlertext, b.new_tercumelertext,"
        " b.new_projeeditor, b.new_editorunkitabaveyazaradairgorusleri, b.new_yazartext,"
        " CAST(b.new_kitaptanitimwebmetni AS nvarchar(max)) AS new_kitaptanitimwebmetni,"
        " CAST(b.new_ozet AS nvarchar(max)) AS new_ozet, CAST(b.new_kitabineskiozeti AS nvarchar(max)) AS new_kitabineskiozeti"
        f" FROM {p}new_kitapBase b WHERE b.new_kitapId = '{_guid(book_id)}'"
    )


def book_roles_sql(schema: str, book_id: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT t.new_name AS rol, c.ContactId, c.FullName AS ad, e.new_OncelikliYazar"
        f" FROM {p}new_eserkatilimBase e JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        f" JOIN {p}ContactBase c ON c.ContactId = e.new_Katilimsaglayan"
        f" WHERE e.statecode = 0 AND e.new_Kitap = '{_guid(book_id)}' ORDER BY t.new_name, c.FullName"
    )


def book_contracts_sql(schema: str, book_id: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT s.new_sozlesmeId, s.new_name, s.new_SozlesmeTipi, s.statuscode, s.new_sozlesmestatusu,"
        " s.new_SozlesmeBaslangicTarihi, s.new_SozlesmeBitisTarihi, s.new_Telif, s.new_suresizsozlesme,"
        " DATEDIFF(day, CAST(GETDATE() AS date), s.new_SozlesmeBitisTarihi) AS kalan_gun"
        f" FROM {p}new_new_sozlesme_new_kitapBase sk JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid"
        f" WHERE s.statecode = 0 AND sk.new_kitapid = '{_guid(book_id)}' ORDER BY s.new_SozlesmeBitisTarihi DESC"
    )


def _book_project(p: str, book_id: str) -> str:
    """Kitabın projesi: kitaptaki `new_projekarti` (proje kartı), projedeki karşılığı `new_stakkarti` (stok
    kartı) ya da eski `new_kitapid`. 2026-09-22'de ölçüldü: yalnız `new_kitapid` 83 kitabı projesine bağlıyordu,
    üç bağ 3.271 kitabı (kitaba ulaşan kurul kararı 1 → 230). `new_new_proje_new_kitapBase` ara tablosu kitabın
    kendi projesi değildir (bir kitabı aynı dönemin başka kitap projelerine bağlar); kullanılmaz."""
    b = _guid(book_id)
    return (f"(j.new_kitapid = '{b}' OR j.new_stakkarti = '{b}'"
            f" OR j.new_projeId = (SELECT k.new_projekarti FROM {p}new_kitapBase k WHERE k.new_kitapId = '{b}'))")


def book_projects_sql(schema: str, book_id: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT j.new_projeId, j.new_name, j.statuscode, j.new_icerikdurumu, j.new_isPlaniAsamasi,"
        " j.CreatedOn, u.FullName AS editor, CAST(j.new_ProjeFikriTekcmleile AS nvarchar(max)) AS fikir"
        f" FROM {p}new_projeBase j LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = j.new_editoru"
        f" WHERE j.statecode = 0 AND {_book_project(p, book_id)} ORDER BY j.CreatedOn DESC"
    )


def book_board_sql(schema: str, book_id: str) -> str:
    """Kurul kararı projeye bağlıdır; kitaba ancak projesi üzerinden ulaşır."""
    p = _prefix(schema)
    return (
        "SELECT t.new_yayinkurulutoplantilariId, t.new_toplantitarihi, t.statuscode, t.new_toplantikararnotu,"
        " t.new_onerilenteliforani, t.new_Yaynkurulubaskiadedi, j.new_name AS proje"
        f" FROM {p}new_projeBase j"
        f" JOIN {p}new_yayinkurulutoplantilariBase t ON t.new_YaynKuruluToplantlarId = j.new_projeId"
        f" WHERE j.statecode = 0 AND t.statecode = 0 AND {_book_project(p, book_id)}"
        " ORDER BY t.new_toplantitarihi DESC"
    )


def book_production_sql(schema: str, book_id: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT r.new_UretimId, r.CreatedOn, r.new_uretimteslimtarihi, r.new_editoryalhazirliktarihi,"
        " r.new_yazardangelenilkmetin, r.statuscode, u.FullName AS sorumlu_editor, g.FullName AS grafiker"
        f" FROM {p}new_UretimBase r"
        f" LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = r.new_SorumluEditor"
        f" LEFT JOIN {p}SystemUserBase g ON g.SystemUserId = r.new_sorumlugrafiker"
        f" WHERE r.statecode = 0 AND r.new_kitapid = '{_guid(book_id)}' ORDER BY r.CreatedOn DESC"
    )


def _hit(r: dict[str, Any], kind: Optional[str] = None) -> dict[str, Any]:
    return {"kind": kind or _s(r.get("tur")), "id": _s(r.get("id")), "title": _s(r.get("ad")),
            "note": _s(r.get("ek1")), "extra": _s(r.get("ek2")), "status": _s(r.get("durum")), "date": _date(r.get("tarih"))}


def search(schema: str, run: Callable[[str], dict[str, Any]], q: str, kind: Optional[str] = None,
           page_no: int = 0) -> dict[str, Any]:
    """Her tür için ilk sayfa ve eşleşen toplam; `kind` verilirse yalnız o türün istenen sayfası."""
    keys = {"kitap": "books", "proje": "projects", "kisi": "people"}
    out: dict[str, Any] = {"books": [], "projects": [], "people": [], "totals": {}, "query": q,
                           "page": max(0, int(page_no)), "pageSize": PAGE_SIZE}
    res: dict[str, Any] = {}
    for k in ([kind] if kind else SEARCH_KINDS):
        res = run(search_sql(schema, q, k, page_no if kind else 0))
        rows = res.get("records") or []
        out[keys[k]] = [_hit(r) for r in rows]
        out["totals"][keys[k]] = int(_n(rows[0].get("toplam")) or 0) if rows else 0
    out["db"] = _timing(res)
    return out


def person_books(schema: str, run: Callable[[str], dict[str, Any]], contact_id: str) -> dict[str, Any]:
    res = run(books_by_person_sql(schema, contact_id))
    return {"items": [_hit(r, "kitap") for r in res.get("records") or []], "truncated": bool(res.get("truncated")),
            "db": _timing(res)}


def book(schema: str, run: Callable[[str], dict[str, Any]], book_id: str) -> dict[str, Any]:
    res = run(book_sql(schema, book_id))
    head = (res.get("records") or [None])[0]
    if head is None:
        raise EditorialError("Kitap bulunamadı.", 404)
    projects = run(book_projects_sql(schema, book_id)).get("records") or []
    # Kitabın konusu: web tanıtım metni > özet > eski özet > projenin tek cümlelik fikri.
    summary, summary_from = next(((_plain(head.get(f)), f) for f in ("new_kitaptanitimwebmetni", "new_ozet", "new_kitabineskiozeti")
                                  if _plain(head.get(f))), (None, None))
    if summary is None:
        summary, summary_from = next(((_plain(r.get("fikir")), "proje") for r in projects if _plain(r.get("fikir"))), (None, None))
    roles: dict[str, list[dict[str, Any]]] = {}
    for r in run(book_roles_sql(schema, book_id)).get("records") or []:
        role = _s(r.get("rol")) or "Diğer"
        roles.setdefault(role, []).append({"id": _s(r.get("ContactId")), "name": _s(r.get("ad"))})
    return {
        "id": _s(head.get("new_kitapId")), "title": _s(head.get("new_name")),
        "isbn": _s(head.get("new_isbn13")) or _s(head.get("new_isbn")), "ebookIsbn": _s(head.get("new_ekitapisbn")),
        "pages": _n(head.get("new_sayfasayisi")), "size": _s(head.get("new_Ebat")),
        "price": _n(head.get("new_kdvdahilfiyat")) or _n(head.get("new_PerakendeBirimFiyat")),
        "printNo": _n(head.get("new_baskisayisi")), "printTotal": _n(head.get("new_baskitoplamadedi")),
        "firstPrint": _n(head.get("new_nihaibaskiadeti")),
        "firstPublished": _date(head.get("new_ilkyayintarihi")), "lastPublished": _date(head.get("new_sonyayintarihi")),
        "lastPrint": _date(head.get("new_baskitarihi")), "genres": _s(head.get("new_turlertext")),
        "shelf": _s(head.get("new_rafturu")), "originalLanguage": _s(head.get("new_orijinaldil")),
        "royaltyState": _s(head.get("new_telifdurum")), "printState": _s(head.get("new_BaskiDurumu")),
        "summary": summary, "summaryFrom": summary_from,
        "status": _s(head.get("statuscode")), "editorNote": _s(head.get("new_editorunkitabaveyazaradairgorusleri")),
        "illustratorsText": _s(head.get("new_cizerlertext")), "translatorsText": _s(head.get("new_tercumelertext")),
        "authorsText": _s(head.get("new_yazartext")),
        "roles": [{"role": k, "people": v} for k, v in sorted(roles.items())],
        "contracts": [{"id": _s(r.get("new_sozlesmeId")), "no": _s(r.get("new_name")), "kind": _s(r.get("new_SozlesmeTipi")),
                       "status": _s(r.get("statuscode")), "stage": _s(r.get("new_sozlesmestatusu")),
                       "start": _date(r.get("new_SozlesmeBaslangicTarihi")), "end": _date(r.get("new_SozlesmeBitisTarihi")),
                       "royalty": _n(r.get("new_Telif")),
                       "daysLeft": None if _n(r.get("kalan_gun")) is None else int(_n(r.get("kalan_gun")))}
                      for r in run(book_contracts_sql(schema, book_id)).get("records") or []],
        "projects": [{"id": _s(r.get("new_projeId")), "name": _s(r.get("new_name")), "status": _s(r.get("statuscode")),
                      "text": _s(r.get("new_icerikdurumu")), "stage": _s(r.get("new_isPlaniAsamasi")),
                      "on": _date(r.get("CreatedOn")), "editor": _s(r.get("editor")), "idea": _plain(r.get("fikir"))}
                     for r in projects],
        "board": [{"id": _s(r.get("new_yayinkurulutoplantilariId")), "date": _date(r.get("new_toplantitarihi")),
                   "decision": _s(r.get("statuscode")), "note": _s(r.get("new_toplantikararnotu")),
                   "royalty": _n(r.get("new_onerilenteliforani")), "printRun": _s(r.get("new_Yaynkurulubaskiadedi")),
                   "project": _s(r.get("proje"))}
                  for r in run(book_board_sql(schema, book_id)).get("records") or []],
        "production": [{"id": _s(r.get("new_UretimId")), "on": _date(r.get("CreatedOn")),
                        "delivery": _date(r.get("new_uretimteslimtarihi")), "editorial": _date(r.get("new_editoryalhazirliktarihi")),
                        "firstText": _date(r.get("new_yazardangelenilkmetin")), "status": _s(r.get("statuscode")),
                        "editor": _s(r.get("sorumlu_editor")), "designer": _s(r.get("grafiker"))}
                       for r in run(book_production_sql(schema, book_id)).get("records") or []],
        "db": _timing(res),
    }
