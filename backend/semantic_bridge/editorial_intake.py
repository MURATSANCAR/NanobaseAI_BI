"""Yazar giriş süreci: müşterinin 9 adımlık akışı (Yazar Giriş Süreci.pdf), CRM'den dinlenerek.

Adımlar CRM statüsünden değil, kanıttan çıkarılır. 2026-09-24'te canlı CRM'de (.28) ölçüldü: kurul kararı
"Kabul" olan 117 proje hâlâ "(Yeni Proje) Proje Toplantısına Hazırlanıyor" statüsünde; statü geçişlerinin
çoğu "Toplantıya hazırlanıyor → İş planı çalışıyor" diye ara adımları atlıyor. `new_projeasamasi` ve projedeki
kurul sonucu/tarih alanları hiç dolu değil. Bu yüzden:

    1 Başvuru geldi            proje kaydı var (CreatedOn)
    2 Editör ataması           new_editoru dolu
    3 Editör raporu            new_icrapor = Tamamlandı ya da portalda "Rapor bitti" işareti
    4 Proje kartı, ön sunum    statü "Yayın kuruluna hazır" ya da projeye kurul kaydı açılmış
    5 Kurul değerlendirmesi    son kurul kararı Kabul ya da statü Kurul onaylı / İş planı / Tamamlandı
    6 Yazara bilgi             portalda "Bildirdim" işareti (CRM'de karşılığı yok)
    7 Cari form ve kişi kartı  projede yazar kişi kartı (new_olasyazaryazar) dolu ya da eser katılımı var
    8 Katılımcı formu, sözleşme stok kartına eser katılımı ve sözleşme bağlı
    9 Üretim ve stok kartı     stok kartına üretim kaydı bağlı

Kurul onayı (5) gelince 1–4 geçilmiş sayılır; kanıtı olmayan adım "sonraki adımdan çıkarıldı" diye işaretlenir.
Onaydan sonraki adımların (6–9) kanıtı yalnız onaydan sonra sayılır: kişi ve stok kartı CRM'de çoğu zaman
başvuruyla birlikte açılıyor, onları erken görmek süreci ileri atlatmaz. 6'nın kendi kanıtı yoktur; 8 ya da 9
gerçekleşmişse yazara bilgi verilmiş sayılır.

Kurul "Red" ya da statü Red/İptal ise proje süreçten çıkar. Bekleme ve yeniden değerlendirme kararında proje
5. adımda kalır, karar notuyla. CRM'de ileri tarihli kurul kaydı yok; "sıradaki kurul" üretilmez.
"""
from __future__ import annotations

import logging
import re
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic.editorial_intake")

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class IntakeError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------------------------------ süreç tanımı

PHASES = (
    {"no": 1, "title": "Değerlendirme", "lead": "Dosya okunuyor", "steps": (1, 2, 3)},
    {"no": 2, "title": "Yayın kurulu", "lead": "Kurul değerlendiriyor", "steps": (4, 5)},
    {"no": 3, "title": "Yayınevine giriş", "lead": "Kurul onaylı", "steps": (6, 7, 8, 9)},
)

#: (başlık, bekleyen iş cümlesi, sorumlu). Sorumlular müşterinin PDF'indeki rollerdir.
STEPS = {
    1: ("Başvuru geldi", "Başvuru inceleniyor", "Yayın yönetmeni ve şef editör"),
    2: ("Editör ataması", "Editör atanmadı", "Yayın yönetmeni ve şef editör"),
    3: ("Editör raporu", "Editör raporu bekleniyor", "Atanan editör"),
    4: ("Proje kartı ve ön sunum", "Kurula sunum hazırlanıyor", "Yayın yönetmeni ve şef editör"),
    5: ("Yayın kurulu değerlendirmesi", "Kurul kararı bekleniyor", "Yönetim kurulu, satış müdürleri, yayın yönetmeni ve şef editör"),
    6: ("Yazara bilgi verilir", "Yazara kurul kararı bildirilecek", "Atanan editör"),
    7: ("Cari form ve kişi kartı", "Yazar kişi kartı bekleniyor", "Atanan editör ve yazar"),
    8: ("Eser katılımcı formu, tarih ve sözleşme", "Katılımcı formu ve sözleşme bekleniyor", "Yazar ve yayın yönetmeni"),
    9: ("Üretim ve stok kartı", "Üretim kaydı bekleniyor", "Proje kartı tarihli üretim ve stok kartına dönüşür"),
}

#: Portalda elle işaretlenen adımlar: CRM'de izi yok ya da çoğu projede boş.
MARKABLE = {3: "Rapor bitti", 6: "Bildirdim"}
#: Editörün kendi işi sayılan adımlar ("Sizi bekleyen işler").
EDITOR_STEPS = (3, 6, 7)

# new_projeBase.statuscode (StringMapBase, 2026-09-24)
ST_BOARD_READY = 100000015
ST_APPROVED = (100000020, 100000019, 100000017)   # Kurul onaylı, İş planı çalışıyor, Tamamlandı
ST_REJECTED = 100000012
ST_CANCELLED = (100000009, 100000021)
# new_projeBase.new_icrapor: 1 Yok, 2 İstendi, 3 Tamamlandı
REPORT_DONE = 3
# new_yayinkurulutoplantilariBase.statuscode
DECISIONS = {1: "Kabul", 100000000: "Red", 100000001: "Bekleme", 100000002: "Yeniden değerlendirme", 100000003: None}
DEC_ACCEPT, DEC_REJECT = 1, 100000000
# new_proje öznitelik sütun numaraları (MetadataSchema.Attribute.ColumnNumber): denetim kaydının AttributeMask'i.
AUDIT_COLUMNS = {"editor": 439, "report": 55}


# ------------------------------------------------------------------------------------------------ SQL

def _prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise IntakeError(f"CRM şeması «{schema}» geçerli bir ad değil.", 503)
    if not sch:
        raise IntakeError("CRM şeması girilmemiş; süreç okunamıyor.", 503)
    return (f"{db}." if db else "") + f"{sch}."


def _since(value: str) -> str:
    v = (value or "").strip()
    if not _DAY.match(v):
        raise IntakeError(f"Süreç başlangıç tarihi «{value}» YYYY-AA-GG biçiminde değil.", 503)
    date.fromisoformat(v)
    return v


def _guid(value: str) -> str:
    if not _GUID.match(value or ""):
        raise IntakeError("Proje kimliği geçerli değil.")
    return value.lower()


def facts_sql(schema: str, since: str, project_id: Optional[str] = None) -> str:
    """Her proje için bir satır: kimlik, kişiler, statü ve adımların kanıtı (kurul, sözleşme, katılım, üretim)."""
    p = _prefix(schema)
    where = f"j.statecode = 0 AND ISNULL(j.new_projetipi, 1) IN (1, 2) AND j.CreatedOn >= '{_since(since)}'"
    if project_id:
        where = f"j.new_projeId = '{_guid(project_id)}'"
    return (
        "SELECT j.new_projeId, j.new_name, j.new_olasiyazartext, c.FullName AS yazar, j.new_olasyazaryazar,"
        " j.new_editoru, u.FullName AS editor, u.DomainName AS editor_hesap,"
        " j.statuscode, CAST(j.statuscode AS int) AS durum_kod, CAST(j.new_icrapor AS int) AS rapor_kod,"
        " j.new_olusturmakanali, j.CreatedOn, j.ModifiedOn, j.new_stakkarti, k.new_name AS kitap,"
        " j.new_projefikritekcmleile, j.new_hedeflenenbaskitarihi, j.new_nerilenyayntarihi,"
        " y.tarih AS kurul_tarihi, y.kod AS kurul_kod, y.adet AS kurul_adet, y.karar_notu,"
        " sz.ilk AS sozlesme_ilk, sz.adet AS sozlesme_adet, kt.ilk AS katilim_ilk, kt.adet AS katilim_adet,"
        " ur.ilk AS uretim_ilk"
        f" FROM {p}new_projeBase j"
        f" LEFT JOIN {p}ContactBase c ON c.ContactId = j.new_olasyazaryazar"
        f" LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = j.new_editoru"
        f" LEFT JOIN {p}new_kitapBase k ON k.new_kitapId = j.new_stakkarti"
        " LEFT JOIN (SELECT x.new_YaynKuruluToplantlarId AS pid, x.new_toplantitarihi AS tarih,"
        " CAST(x.statuscode AS int) AS kod, x.new_toplantikararnotu AS karar_notu,"
        " ROW_NUMBER() OVER (PARTITION BY x.new_YaynKuruluToplantlarId ORDER BY x.new_toplantitarihi DESC, x.CreatedOn DESC) AS sira,"
        " COUNT(*) OVER (PARTITION BY x.new_YaynKuruluToplantlarId) AS adet"
        f" FROM {p}new_yayinkurulutoplantilariBase x WHERE x.statecode = 0) y ON y.pid = j.new_projeId AND y.sira = 1"
        " LEFT JOIN (SELECT sk.new_kitapid AS kid, MIN(s.CreatedOn) AS ilk, COUNT(*) AS adet"
        f" FROM {p}new_new_sozlesme_new_kitapBase sk JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid"
        " WHERE s.statecode = 0 GROUP BY sk.new_kitapid) sz ON sz.kid = j.new_stakkarti"
        " LEFT JOIN (SELECT e.new_Kitap AS kid, MIN(e.CreatedOn) AS ilk, COUNT(*) AS adet"
        f" FROM {p}new_eserkatilimBase e WHERE e.statecode = 0 GROUP BY e.new_Kitap) kt ON kt.kid = j.new_stakkarti"
        " LEFT JOIN (SELECT r.new_kitapid AS kid, MIN(r.CreatedOn) AS ilk"
        f" FROM {p}new_UretimBase r GROUP BY r.new_kitapid) ur ON ur.kid = j.new_stakkarti"
        f" WHERE {where} ORDER BY j.CreatedOn DESC, j.new_projeId"
    )


def audit_sql(schema: str, since: str) -> str:
    """Editör ve rapor alanının son değiştiği an. Denetim kaydı katalogda yoksa köprü reddeder; o zaman
    adım tarihleri kayıtların kendi tarihlerinden gelir (bkz. `collect`)."""
    p = _prefix(schema)
    masks = " OR ".join(f"au.AttributeMask LIKE '%,{n},%'" for n in AUDIT_COLUMNS.values())
    return (
        "SELECT au.ObjectId, au.CreatedOn, au.AttributeMask"
        f" FROM {p}AuditBase au JOIN {p}new_projeBase j ON j.new_projeId = au.ObjectId"
        f" WHERE au.ObjectTypeCode = 10000 AND au.Action = 2 AND ({masks})"
        f" AND j.statecode = 0 AND j.CreatedOn >= '{_since(since)}'"
    )


def meetings_sql(schema: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT CAST(x.new_toplantitarihi AS date) AS gun, CAST(x.statuscode AS int) AS kod, COUNT(*) AS n"
        f" FROM {p}new_yayinkurulutoplantilariBase x WHERE x.statecode = 0 AND x.new_toplantitarihi IS NOT NULL"
        " GROUP BY CAST(x.new_toplantitarihi AS date), CAST(x.statuscode AS int) ORDER BY 1 DESC"
    )


def agenda_sql(schema: str, day: str) -> str:
    if not _DAY.match(day or ""):
        raise IntakeError("Toplantı tarihi YYYY-AA-GG biçiminde olmalı.")
    date.fromisoformat(day)
    p = _prefix(schema)
    return (
        "SELECT x.new_yayinkurulutoplantilariId, x.new_YaynKuruluToplantlarId AS proje_id, CAST(x.statuscode AS int) AS kod,"
        " x.new_toplantikararnotu, x.new_yaynkurulubaskiadedi, x.new_yaynkurulufiyatonerisi, x.new_onerilenteliforani,"
        " x.new_avansbedeli, x.new_onerilenyayintarihi, j.new_name AS proje, j.new_olasiyazartext, c.FullName AS yazar,"
        " u.FullName AS editor, CAST(j.new_icrapor AS int) AS rapor_kod"
        f" FROM {p}new_yayinkurulutoplantilariBase x"
        f" LEFT JOIN {p}new_projeBase j ON j.new_projeId = x.new_YaynKuruluToplantlarId"
        f" LEFT JOIN {p}ContactBase c ON c.ContactId = j.new_olasyazaryazar"
        f" LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = j.new_editoru"
        f" WHERE x.statecode = 0 AND CAST(x.new_toplantitarihi AS date) = '{day}'"
        " ORDER BY j.new_name, x.new_yayinkurulutoplantilariId"
    )


def project_boards_sql(schema: str, project_id: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT x.new_yayinkurulutoplantilariId, x.new_toplantitarihi, CAST(x.statuscode AS int) AS kod, x.new_toplantikararnotu,"
        " x.new_yaynkurulubaskiadedi, x.new_yaynkurulufiyatonerisi, x.new_onerilenteliforani, x.new_onerilenyayintarihi"
        f" FROM {p}new_yayinkurulutoplantilariBase x"
        f" WHERE x.statecode = 0 AND x.new_YaynKuruluToplantlarId = '{_guid(project_id)}' ORDER BY x.new_toplantitarihi DESC"
    )


def opinions_sql(schema: str, project_ids: list[str]) -> str:
    p = _prefix(schema)
    ids = ", ".join(f"'{_guid(i)}'" for i in project_ids)
    return (
        "SELECT g.new_kitapprojesiid, g.new_GenelKanaat, g.new_ProjeHakkndaDierGrler, g.CreatedOn, w.FullName AS yazan"
        f" FROM {p}new_projegrBase g LEFT JOIN {p}SystemUserBase w ON w.SystemUserId = g.OwnerId"
        f" WHERE g.statecode = 0 AND g.new_kitapprojesiid IN ({ids}) ORDER BY g.CreatedOn"
    )


# ---------------------------------------------------------------------------------------------- biçim

def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    t = str(v).strip()
    return t or None


def _i(v: Any) -> Optional[int]:
    try:
        return None if v is None or v == "" else int(float(v))
    except (TypeError, ValueError):
        return None


def _day(v: Any) -> Optional[str]:
    t = _s(v)
    return t[:10] if t and _DAY.match(t[:10]) else None


def _id(v: Any) -> Optional[str]:
    t = _s(v)
    return t.lower() if t else None


def _lower(r: dict[str, Any]) -> dict[str, Any]:
    """SQL Server çıplak kolonu şemadaki yazımıyla döndürür (`new_OlasYazarYazar`); anahtarlar küçük harfle okunur."""
    return {str(k).lower(): v for k, v in r.items()}


def _account(domain: Optional[str]) -> Optional[str]:
    """CRM kullanıcı adı `TIMAS\\muratsancar` → portal oturumundaki `muratsancar`."""
    t = (domain or "").strip().lower()
    return t.rsplit("\\", 1)[-1] or None


def fact(r: dict[str, Any]) -> dict[str, Any]:
    """Bir CRM satırı → önbelleğe yazılan ham kanıt. Adım hesabı okumada yapılır (işaretler anlık)."""
    r = _lower(r)
    return {
        "id": _id(r.get("new_projeid")),
        "name": _s(r.get("new_name")),
        "author": _s(r.get("yazar")) or _s(r.get("new_olasiyazartext")),
        "authorCard": bool(_s(r.get("new_olasyazaryazar"))),
        "editor": _s(r.get("editor")) if _s(r.get("new_editoru")) else None,
        "editorAccount": _account(_s(r.get("editor_hesap"))) if _s(r.get("new_editoru")) else None,
        "status": _s(r.get("statuscode")),
        "statusCode": _i(r.get("durum_kod")),
        "reportCode": _i(r.get("rapor_kod")),
        "channel": _s(r.get("new_olusturmakanali")),
        "createdOn": _day(r.get("createdon")),
        "modifiedOn": _day(r.get("modifiedon")),
        "bookId": _id(r.get("new_stakkarti")),
        "book": _s(r.get("kitap")),
        "idea": _s(r.get("new_projefikritekcmleile")),
        "publishOn": _day(r.get("new_hedeflenenbaskitarihi")) or _day(r.get("new_nerilenyayntarihi")),
        "boardOn": _day(r.get("kurul_tarihi")),
        "boardCode": _i(r.get("kurul_kod")),
        "boardCount": _i(r.get("kurul_adet")) or 0,
        "boardNote": _s(r.get("karar_notu")),
        "contractOn": _day(r.get("sozlesme_ilk")),
        "contracts": _i(r.get("sozlesme_adet")) or 0,
        "participationOn": _day(r.get("katilim_ilk")),
        "participations": _i(r.get("katilim_adet")) or 0,
        "productionOn": _day(r.get("uretim_ilk")),
        "editorOn": None,
        "reportOn": None,
    }


def apply_audit(facts: list[dict[str, Any]], rows: Iterable[dict[str, Any]]) -> None:
    """Editör ve rapor alanının son değişim günü (denetim kaydı okunabildiyse)."""
    by_id = {f["id"]: f for f in facts}
    wanted = {str(n): key for key, n in AUDIT_COLUMNS.items()}
    for r in map(_lower, rows):
        f = by_id.get(_id(r.get("objectid")))
        on = _day(r.get("createdon"))
        if not f or not on:
            continue
        for col in (_s(r.get("attributemask")) or "").split(","):
            key = wanted.get(col)
            if key and (f.get(key + "On") or "") < on:
                f[key + "On"] = on


def collect(schema: str, since: str, fetch_all: Callable[[str], list[dict[str, Any]]]) -> dict[str, Any]:
    """Dinleyicinin bir turu: CRM'den bütün izlenen projelerin kanıtı. Denetim kaydı isteğe bağlıdır."""
    facts = [fact(r) for r in fetch_all(facts_sql(schema, since))]
    audit = True
    try:
        apply_audit(facts, fetch_all(audit_sql(schema, since)))
    except Exception as e:  # noqa: BLE001 — denetim kaydı bir ektir; yoksa tarih kayıtların kendisinden
        log.warning("intake: denetim kaydı okunamadı: %s", e)
        audit = False
    return {"since": since, "facts": facts, "audit": audit, "at": datetime.now(timezone.utc).isoformat()}


# --------------------------------------------------------------------------------------- adım hesabı

def _days(since: Optional[str], today: date) -> Optional[int]:
    if not since:
        return None
    try:
        return max(0, (today - date.fromisoformat(since)).days)
    except ValueError:
        return None


def steps_of(f: dict[str, Any], marks: dict[int, dict[str, Any]]) -> tuple[list[dict[str, Any]], Optional[str]]:
    """9 adımın durumu ve sonuç (None: sürüyor, 'red', 'iptal'). Her adım: done, on, source.

    source: 'crm' (CRM'de kanıt), 'portal' (portalda işaret), 'cikarim' (sonraki adımdan çıkarıldı)."""
    code, dec = f.get("statusCode"), f.get("boardCode")
    s: dict[int, dict[str, Any]] = {n: {"no": n, "done": False, "on": None, "source": None} for n in STEPS}

    def mark(n: int, on: Optional[str], source: str = "crm") -> None:
        s[n].update(done=True, on=on, source=source)

    mark(1, f.get("createdOn"))
    if f.get("editor"):
        mark(2, f.get("editorOn"))
    if f.get("reportCode") == REPORT_DONE:
        mark(3, f.get("reportOn"))
    elif 3 in marks:
        mark(3, marks[3]["on"], "portal")
    if code == ST_BOARD_READY or f.get("boardCount"):
        mark(4, None)
    approved = dec == DEC_ACCEPT or (code in ST_APPROVED and dec != DEC_REJECT)
    if approved:
        mark(5, f.get("boardOn"))
        for n in (2, 3, 4):
            if not s[n]["done"]:
                mark(n, None, "cikarim")
        # Kişi kartı projede bağlı değilse eser katılımındaki kişi kaydı da kartın açıldığını gösterir.
        if f.get("authorCard") or f.get("participations"):
            mark(7, f.get("participationOn") if not f.get("authorCard") else None)
        if f.get("participations") and f.get("contracts"):
            known = [d for d in (f.get("participationOn"), f.get("contractOn")) if d]
            mark(8, max(known) if known else None)
        if f.get("bookId") and f.get("productionOn"):
            mark(9, f.get("productionOn"))
        if 6 in marks:
            mark(6, marks[6]["on"], "portal")
        elif s[8]["done"] or s[9]["done"]:
            mark(6, None, "cikarim")
    elif s[4]["done"]:
        for n in (2, 3):
            if not s[n]["done"]:
                mark(n, None, "cikarim")
    if dec == DEC_REJECT or code == ST_REJECTED:
        outcome = "red"
    elif code in ST_CANCELLED:
        outcome = "iptal"
    else:
        outcome = None
    return [s[n] for n in sorted(s)], outcome


def summarize(f: dict[str, Any], marks: dict[int, dict[str, Any]], today: date, late_days: int) -> dict[str, Any]:
    """Pano kartı: bulunduğu adım, kaç gündür beklediği, gecikme, tek cümlelik durum."""
    steps, outcome = steps_of(f, marks)
    current = next((x["no"] for x in steps if not x["done"]), None)
    phase = next((ph["no"] for ph in PHASES if current in ph["steps"]), None) if current else None
    # Bekleme, bir önceki adımın bilinen bitiş gününden (yoksa başvurudan) sayılır.
    started = f.get("createdOn")
    if current:
        known = [x["on"] for x in steps if x["no"] < current and x["done"] and x["on"]]
        started = max(known) if known else started
    waiting = _days(started, today) if current and not outcome else None
    line = STEPS[current][1] if current else "Stok kartı ve üretim kaydı açıldı"
    if current == 5 and f.get("boardCode") in (100000001, 100000002):
        line = f"Kurul kararı: {DECISIONS[f['boardCode']].lower()}"
    if outcome == "red":
        line = "Kurul reddetti" if f.get("boardCode") == DEC_REJECT else "Reddedildi"
    elif outcome == "iptal":
        line = "İptal edildi"
    return {
        "id": f["id"], "name": f.get("name"), "author": f.get("author"), "editor": f.get("editor"),
        "editorAccount": f.get("editorAccount"), "bookId": f.get("bookId"),
        "step": current, "phase": phase, "done": sum(1 for x in steps if x["done"]),
        "progress": [x["done"] for x in steps], "line": line, "since": started, "waitingDays": waiting,
        "late": bool(waiting is not None and waiting > late_days), "outcome": outcome,
        "complete": current is None and not outcome, "boardOn": f.get("boardOn"),
        "modifiedOn": f.get("modifiedOn"), "createdOn": f.get("createdOn"),
    }


def _mine(item: dict[str, Any], user: str) -> bool:
    return bool(user) and (item.get("editorAccount") or "") == user.strip().lower()


def board(snapshot: dict[str, Any], marks: dict[str, dict[int, dict[str, Any]]], user: str, *,
          today: date, late_days: int, everyone: bool = False) -> dict[str, Any]:
    """Süreç panosu: bütün projelerin kartı, evre sayıları ve bekleyen işler. Yönetici (`everyone`) bütün
    editörlerin bekleyen işini görür; editör yalnız kendisininkini."""
    items = [summarize(f, marks.get(f["id"], {}), today, late_days) for f in snapshot.get("facts") or []]
    running = [x for x in items if x["step"] and not x["outcome"]]
    # En uzun bekleyen önde; gecikenler bu sayede sütunun başına çıkar.
    running.sort(key=lambda x: (-(x["waitingDays"] or 0), x["name"] or ""))
    phases = [dict(title=ph["title"], no=ph["no"], lead=ph["lead"], steps=[{"no": n, "title": STEPS[n][0]} for n in ph["steps"]],
                   count=sum(1 for x in running if x["phase"] == ph["no"]),
                   late=sum(1 for x in running if x["phase"] == ph["no"] and x["late"])) for ph in PHASES]
    mine_todo = [x for x in running if (everyone or _mine(x, user)) and x["step"] in EDITOR_STEPS]
    last_board = max((f.get("boardOn") for f in snapshot.get("facts") or [] if f.get("boardOn")), default=None)
    for x in items:
        x["mine"] = _mine(x, user)
        x.pop("editorAccount", None)
    return {
        "since": snapshot.get("since"), "at": snapshot.get("at"), "audit": snapshot.get("audit", False),
        "lateDays": late_days, "phases": phases, "items": running,
        "completed": sorted((x for x in items if x["complete"]), key=lambda x: x["modifiedOn"] or "", reverse=True),
        "closed": sorted((x for x in items if x["outcome"]), key=lambda x: x["modifiedOn"] or "", reverse=True),
        "todo": mine_todo, "todoScope": "all" if everyone else "mine", "lastBoard": last_board,
        "steps": [{"no": n, "title": t, "waiting": w, "owner": o, "markable": MARKABLE.get(n)} for n, (t, w, o) in STEPS.items()],
    }


def detail(f: dict[str, Any], marks: dict[int, dict[str, Any]], user: str, *, today: date, late_days: int,
           boards: list[dict[str, Any]], opinions: Optional[list[dict[str, Any]]], can_mark: bool) -> dict[str, Any]:
    steps, outcome = steps_of(f, marks)
    card = summarize(f, marks, today, late_days)
    out_steps = []
    for x in steps:
        title, waiting, owner = STEPS[x["no"]]
        m = marks.get(x["no"])
        out_steps.append(dict(x, title=title, owner=owner, waiting=waiting,
                              markable=MARKABLE.get(x["no"]),
                              markedBy=m.get("display") if m else None, marked=bool(m)))
    return {
        **{k: v for k, v in card.items() if k != "editorAccount"},
        "mine": _mine(card, user), "canMark": can_mark, "outcome": outcome, "steps": out_steps,
        "phases": [{"no": ph["no"], "title": ph["title"], "steps": list(ph["steps"])} for ph in PHASES],
        "channel": f.get("channel"), "status": f.get("status"), "idea": f.get("idea"), "book": f.get("book"),
        "publishOn": f.get("publishOn"), "contracts": f.get("contracts"), "participations": f.get("participations"),
        "boards": boards, "opinions": opinions, "opinionsVisible": opinions is not None,
    }


def board_row(r: dict[str, Any]) -> dict[str, Any]:
    r = _lower(r)
    code = _i(r.get("kod"))
    return {
        "id": _id(r.get("new_yayinkurulutoplantilariid")), "date": _day(r.get("new_toplantitarihi")),
        "decisionCode": code, "decision": DECISIONS.get(code) if code is not None else None,
        "note": _s(r.get("new_toplantikararnotu")), "printRun": _s(r.get("new_yaynkurulubaskiadedi")),
        "price": _s(r.get("new_yaynkurulufiyatonerisi")), "royalty": _s(r.get("new_onerilenteliforani")),
        "publishOn": _day(r.get("new_onerilenyayintarihi")),
    }


def opinion_row(r: dict[str, Any]) -> dict[str, Any]:
    r = _lower(r)
    return {"projectId": _id(r.get("new_kitapprojesiid")), "by": _s(r.get("yazan")), "verdict": _s(r.get("new_genelkanaat")),
            "text": _s(r.get("new_projehakkndadiergrler")), "on": _day(r.get("createdon"))}


def meetings(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_day: dict[str, dict[str, Any]] = {}
    for r in map(_lower, rows):
        day = _day(r.get("gun"))
        if not day:
            continue
        m = by_day.setdefault(day, {"date": day, "total": 0, "accepted": 0, "rejected": 0, "revisit": 0, "pending": 0})
        n, code = _i(r.get("n")) or 0, _i(r.get("kod"))
        m["total"] += n
        key = {DEC_ACCEPT: "accepted", DEC_REJECT: "rejected", 100000002: "revisit"}.get(code, "pending")
        m[key] += n
    return sorted(by_day.values(), key=lambda m: m["date"], reverse=True)


def agenda(rows: Iterable[dict[str, Any]], opinions: Optional[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    by_project: dict[str, list[dict[str, Any]]] = {}
    for o in opinions or []:
        by_project.setdefault(o["projectId"] or "", []).append({k: v for k, v in o.items() if k != "projectId"})
    out = []
    for r in map(_lower, rows):
        code, pid = _i(r.get("kod")), _id(r.get("proje_id"))
        ops = by_project.get(pid or "", []) if opinions is not None else None
        out.append({
            "id": _id(r.get("new_yayinkurulutoplantilariid")), "projectId": pid, "project": _s(r.get("proje")),
            "author": _s(r.get("yazar")) or _s(r.get("new_olasiyazartext")), "editor": _s(r.get("editor")),
            "report": _i(r.get("rapor_kod")) == REPORT_DONE, "decisionCode": code,
            "decision": DECISIONS.get(code) if code is not None else None, "note": _s(r.get("new_toplantikararnotu")),
            "printRun": _s(r.get("new_yaynkurulubaskiadedi")), "price": _s(r.get("new_yaynkurulufiyatonerisi")),
            "royalty": _s(r.get("new_onerilenteliforani")), "advance": _s(r.get("new_avansbedeli")),
            "publishOn": _day(r.get("new_onerilenyayintarihi")),
            "opinions": ops, "opinionCount": len(ops) if ops is not None else None,
        })
    return out


# ------------------------------------------------------------------------------- portal işaretleri

_md = sa.MetaData()
MARKS = sa.Table(
    "semantic_editorial_intake_marks", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("project_id", sa.String(40), nullable=False),
    sa.Column("step", sa.Integer, nullable=False),
    sa.Column("username", sa.String(120), nullable=False),
    sa.Column("display", sa.String(200)),
    sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("tenant_id", "project_id", "step", name="uq_editorial_intake_mark"),
)
_lock = threading.Lock()
_ready: set[int] = set()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def all_marks(engine: sa.engine.Engine, tenant: str, project_id: Optional[str] = None) -> dict[str, dict[int, dict[str, Any]]]:
    q = sa.select(MARKS).where(MARKS.c.tenant_id == tenant)
    if project_id:
        q = q.where(MARKS.c.project_id == _guid(project_id))
    out: dict[str, dict[int, dict[str, Any]]] = {}
    with engine.connect() as c:
        for m in c.execute(q):
            out.setdefault(m.project_id, {})[m.step] = {
                "on": m.marked_at.date().isoformat() if m.marked_at else None, "by": m.username, "display": m.display or m.username}
    return out


def set_mark(engine: sa.engine.Engine, tenant: str, project_id: str, step: int, user: str, display: str) -> None:
    if step not in MARKABLE:
        raise IntakeError("Bu adım portaldan işaretlenmez; CRM'den okunur.")
    pid = _guid(project_id)
    with engine.begin() as c:
        exists = c.execute(sa.select(MARKS.c.id).where(MARKS.c.tenant_id == tenant, MARKS.c.project_id == pid,
                                                        MARKS.c.step == step)).first()
        if exists:
            return
        c.execute(MARKS.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, project_id=pid, step=step,
                                        username=user[:120], display=(display or user)[:200],
                                        marked_at=datetime.now(timezone.utc)))


def clear_mark(engine: sa.engine.Engine, tenant: str, project_id: str, step: int) -> bool:
    if step not in MARKABLE:
        raise IntakeError("Bu adım portaldan işaretlenmez; CRM'den okunur.")
    with engine.begin() as c:
        return c.execute(MARKS.delete().where(MARKS.c.tenant_id == tenant, MARKS.c.project_id == _guid(project_id),
                                              MARKS.c.step == step)).rowcount > 0
