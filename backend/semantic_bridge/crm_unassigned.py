"""CRM'de departmana atanmamış kullanıcılar: kök iş biriminde duran etkin CRM kullanıcıları, AD birimleriyle.

Yetki bağında «departman» kaynağı AD birimidir; CRM kullanıcılarının çoğu kök iş biriminde durur (2026-09-29: 151
etkin kişinin 107'si). Bu liste kimin CRM'de departmansız kaldığını, AD'de hangi birimde olduğunu gösterir.
Her gün 07:00 ve 12:00'de (`timas-crm-unassigned.timer`) Excel olarak `CRM_UNASSIGNED_TO` alıcılarına gider;
Yetkiler ekranından da indirilir. CRM'e yalnız okuma.
"""

from __future__ import annotations

import io
from collections import Counter
from datetime import datetime
from typing import Any, Callable, Optional

NO_AD = "AD'de etkin hesabı yok"


def users_sql(prefix: str) -> str:
    """Kök iş birimindeki (üst birimi olmayan) etkin, giriş yapabilen, AD hesaplı CRM kullanıcıları."""
    p = prefix
    return (f"SELECT CAST(u.SystemUserId AS nvarchar(40)) AS Id, u.FullName, u.DomainName, u.InternalEMailAddress, "
            f"u.CreatedOn, b.Name AS BirimAdi "
            f"FROM {p}SystemUserBase u JOIN {p}BusinessUnitBase b ON b.BusinessUnitId = u.BusinessUnitId "
            f"WHERE b.ParentBusinessUnitId IS NULL AND u.IsDisabled = 0 AND u.AccessMode IN (0, 1) "
            f"AND u.DomainName IS NOT NULL AND u.DomainName <> ''")


def roles_sql(prefix: str) -> str:
    # CRM sunucusunda STRING_AGG yok (SQL Server 2016 öncesi uyumluluk): roller ayrı okunup birleştirilir.
    return (f"SELECT CAST(sur.SystemUserId AS nvarchar(40)) AS Id, r.Name "
            f"FROM {prefix}SystemUserRoles sur JOIN {prefix}RoleBase r ON r.RoleId = sur.RoleId")


def build(directory: Any) -> list[dict[str, Any]]:
    """Satırlar: ad, hesap, AD birimi, e-posta, açılış, ana roller (ACTION_ dışı), bütün roller."""
    from semantic_bridge.access import _account

    p = directory._crm_prefix()
    users = directory._crm_rows(users_sql(p))
    roles: dict[str, set[str]] = {}
    for r in directory._crm_rows(roles_sql(p)):
        roles.setdefault(str(r.get("Id") or "").lower(), set()).add(str(r.get("Name") or "").strip())
    people = {x["subject"]: x for x in directory.list_people()}
    out = []
    for u in users:
        acc = _account(u.get("DomainName"))
        mine = sorted((x for x in roles.get(str(u.get("Id") or "").lower(), ()) if x), key=str.lower)
        created = u.get("CreatedOn")
        out.append({
            "name": str(u.get("FullName") or acc).strip(),
            "account": acc,
            "adUnit": (people.get(acc) or {}).get("detail") or NO_AD,
            "email": str(u.get("InternalEMailAddress") or "").strip(),
            "created": created.strftime("%Y-%m-%d") if hasattr(created, "strftime") else str(created or "")[:10],
            "mainRoles": [x for x in mine if not x.startswith("ACTION_")],
            "roles": mine,
            "crmUnit": str(u.get("BirimAdi") or "").strip(),
        })
    return sorted(out, key=lambda x: (x["adUnit"].lower(), x["name"].lower()))


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(rows),
        "byAdUnit": [{"unit": u, "count": n} for u, n in Counter(r["adUnit"] for r in rows).most_common()],
        "noAd": sum(1 for r in rows if r["adUnit"] == NO_AD),
        "noRole": sum(1 for r in rows if not r["roles"]),
    }


def xlsx(rows: list[dict[str, Any]], when: Optional[datetime] = None, *, minimal: bool = False) -> bytes:
    """Yetkiler ekranından indirilen tam liste (roller, AD birimi, e-posta) ya da `minimal=True` ile e-posta eki: yalnız
    işin gerektirdiği alanlar (ad, kullanıcı adı, CRM'de oluşturulma tarihi). E-posta kutudan kutuya dolaşır; kişisel
    alan (e-posta adresi, roller) ona konmaz, tam liste portalda yetkiyle indirilir."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Kişiler"
    if minimal:
        ws.append(["#", "Ad Soyad", "Kullanıcı adı", "CRM'de oluşturulma"])
        for i, r in enumerate(rows, 1):
            ws.append([i, r["name"], r["account"], r["created"]])
        widths = [5, 28, 22, 18]
    else:
        ws.append(["#", "Ad Soyad", "AD hesabı", "AD birimi (OU)", "E-posta", "CRM'de açılış", "CRM iş birimi",
                   "Ana CRM rolleri", "Bütün CRM rolleri"])
        for i, r in enumerate(rows, 1):
            ws.append([i, r["name"], r["account"], r["adUnit"], r["email"], r["created"], r["crmUnit"],
                       ", ".join(r["mainRoles"]) or "(rol yok)", ", ".join(r["roles"])])
        widths = [5, 26, 20, 22, 32, 13, 16, 50, 80]
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="5B3FD6")
    for col, w in zip("ABCDEFGHI", widths):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    s = wb.create_sheet("AD birimine göre")
    s.append(["AD birimi (OU)", "Kişi"])
    sm = summary(rows)
    for x in sm["byAdUnit"]:
        s.append([x["unit"], x["count"]])
    s.append(["Toplam", sm["count"]])
    s.append([])
    s.append([f"CRM'den okundu: {(when or datetime.now()).strftime('%d.%m.%Y %H:%M')}"])
    s["A1"].font = s["B1"].font = Font(bold=True)
    s.column_dimensions["A"].width = 30
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def recipients(conf: Callable[..., str]) -> tuple[list[str], list[str]]:
    """(gönderilecek, izinli alan adı dışında kaldığı için atlanan) — süzgeç uyarılarla aynı (`ALERT_RECIPIENT_DOMAINS`)."""
    to = [a.strip() for a in (conf("CRM_UNASSIGNED_TO") or "").replace(";", ",").split(",") if "@" in a]
    allowed = [d.strip().lower().lstrip("@") for d in (conf("ALERT_RECIPIENT_DOMAINS") or "").split(",") if d.strip()]
    ok = [a for a in to if not allowed or a.rsplit("@", 1)[1].lower() in allowed]
    return ok, [a for a in to if a not in ok]


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def notice(rows: list[dict[str, Any]], now: datetime, link: str = ""):
    """«[Bilgi] CRM'de departmanı olmayan 107 kullanıcı · 29 Eylül 07:00» (ic_bildirim şablonu). Gövdede kişi adı
    yok; kişi listesi ekte yalnız ad, kullanıcı adı ve oluşturulma tarihiyle."""
    from semantic_bridge import ic_bildirim as IB

    sm = summary(rows)
    n = sm["count"]
    at = now if now.tzinfo else now.replace(tzinfo=IB.LOCAL)
    actions = ["Ekteki listedeki her kişiyi CRM'de çalıştığı departmanın iş birimine taşıyın.",
               "Kişinin şirket dizinindeki birimini ve CRM rollerini portalda Yönetim → Yetkiler → «Departmansız CRM "
               "kullanıcıları» listesinden görebilirsiniz."]
    if sm["noAd"]:
        actions.insert(0, f"{sm['noAd']} kişinin şirket dizininde etkin hesabı yok (ayrılmış olabilir): bu kişilerin CRM "
                          "hesabını kapatın.")
    what = [f"CRM'de hiçbir departmana (iş birimine) atanmamış, giriş yapabilen {n} etkin kullanıcı var.",
            f"Bunların {sm['noRole']} tanesinin hiçbir CRM rolü yok; {sm['noAd']} tanesinin şirket dizininde etkin hesabı yok."]
    return IB.Notice(
        tone="bilgi", tag="Bilgi",
        subject=IB.subject("Bilgi", f"CRM'de departmanı olmayan {n} kullanıcı · {IB.short_dt(at)}"),
        headline=(f"CRM'de {n} kullanıcı hiçbir departmana atanmamış; liste ekteki Excel dosyasında." if n
                  else "CRM'de departmanı olmayan kullanıcı kalmadı."),
        what=what if n else ["Bütün etkin CRM kullanıcıları bir departmana atanmış."],
        impact=["Departmanı olmayan kullanıcı CRM'de departman bazlı yetkilerde, kayıt sahipliğinde ve departman "
                "raporlarında doğru yerde görünmez: iş birimine göre işleyen CRM yetkileri ve kayıt görünürlüğü bu kişiler "
                "için departmanlarına değil en üst birime göre işler."] if n else [],
        actions=actions if n else ["Yapmanız gereken bir şey yok."],
        tables=[IB.Table(title="Şirket dizinindeki birime göre", columns=["Birim", "Kişi"], numeric=(1,),
                         rows=[[x["unit"], x["count"]] for x in sm["byAdUnit"]])] if n else [],
        link=IB.portal_link(link, "yonetim"), link_label="Yetkileri aç", at=at,
        why="Bu adrese «Departmansız CRM kullanıcıları listesi alıcıları» ayarında olduğu için geldi; liste her gün "
            "07:00 ve 12:00'de gider. CRM'e yazılmaz, yalnız okunur.")


def send(directory: Any, conf: Callable[..., str], send_notice: Optional[Callable[..., str]] = None,
         now: Optional[datetime] = None) -> dict[str, Any]:
    """Listeyi okuyup alıcılara Excel olarak gönderir. Alıcı yoksa okumaz bile (CRM'e boşuna gidilmez).
    `send_notice(notice, to, attachments)`; varsayılanı ortak iç bildirim gönderimi (HTML + düz metin)."""
    from semantic_bridge import ic_bildirim as IB

    send_notice = send_notice or IB.send
    to, skipped = recipients(conf)
    if not to:
        return {"ok": True, "status": "no_recipient", "skipped": skipped}
    now = now or datetime.now()
    rows = build(directory)
    sm = summary(rows)
    name = f"CRM-departmansiz-kullanicilar-{now.strftime('%Y-%m-%d-%H%M')}.xlsx"
    status = send_notice(notice(rows, now, (conf("ALERT_LINK") or "").strip()), to,
                         [(name, xlsx(rows, now, minimal=True), XLSX_MIME)])
    return {"ok": status == "sent", "status": status, "to": to, "skipped": skipped, **sm}
