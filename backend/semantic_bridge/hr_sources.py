"""İK-0 salt okunur kaynakları: CRM kullanıcı/birim/ekip tabloları ve AD. CRM'e yazılmaz.

Tablolar (prod CRM, köprünün CRM şeması `CRM_SCHEMA`, ör. `Timas_MSCRM.dbo`): `SystemUserBase`, `BusinessUnitBase`,
`TeamBase`, `TeamMembership`. Bunlar semantik katalogda olmadığı için SQL kapısından (`run_sql`) değil, M12/M32'deki gibi
kendi salt okunur bağlantısıyla okunur (`budget_sources.runner`).

Tanımlar (kabul betiği `scripts/acceptance/M55/` aynı tanımı bağımsız SQL ile sınar):

- **CRM'de etkin kullanıcı** = `IsDisabled = 0 AND AccessMode IN (0, 1)` ve `DomainName` dolu (Kampüs rehberiyle aynı:
  `people.directory_sql`). Uygulama/eşitleme hesapları (AccessMode 3, 4, 5…) çalışan sayılmaz.
- **Çalışan önerisi** = etkin kullanıcı ∩ AD'de etkin kişi hesabı (`ActiveDirectoryGuid` = `objectGUID`, yoksa hesap adı).
  AD ayarı yoksa yalnız CRM; yanıt bunu söyler. Rehberdeki «son N gün giriş» süzgeci burada **uygulanmaz**: uzun izindeki
  çalışan kayıttan düşmemeli; giriş tarihi yalnız bilgi olarak gösterilir.
- **Birim dağılımı** = `IsDisabled = 0` bütün kullanıcıların `BusinessUnitId` başına sayısı (erişim türünden bağımsız;
  analiz §14.2 kabul 2).
- **Birim yöneticisi** = `BusinessUnitBase.<HR_CRM_UNIT_MANAGER_COLUMN>` (varsayılan `new_departmanyoneticisiid`,
  doluluğu ölçülecek). Kolon yoksa okuma kolonsuz tekrarlanır ve not düşülür.
- **Ekip üyeliği** = `TeamMembership` ⨝ `TeamBase` ⨝ etkin (`IsDisabled = 0`) kullanıcı, ekip başına.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional

from semantic_bridge import budget_sources as bsrc
from semantic_bridge import people as people_mod

log = logging.getLogger("semantic_bridge.hr.sources")

SourceError = bsrc.SourceError
Runner = bsrc.Runner
runner = bsrc.runner

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not re.match(r"^[A-Za-z0-9_$-]+$", part):
            raise SourceError(f"CRM şeması «{schema}» geçerli bir ad değil.")
    if not sch:
        raise SourceError("CRM şeması girilmemiş; CRM okunamıyor.")
    return (f"{db}." if db else "") + f"{sch}."


def _guid(v: Any) -> str:
    return str(v or "").strip().strip("{}").lower()


def crm_users(run: Runner, p: str) -> list[dict[str, Any]]:
    """Devre dışı olmayan bütün CRM kullanıcıları (erişim türüyle); ayrım Python'da yapılır ki sayılar tek okumadan gelsin."""
    rows = run(
        "SELECT CAST(SystemUserId AS nvarchar(40)) AS SystemUserId, FullName, DomainName, "
        "CAST(ActiveDirectoryGuid AS nvarchar(40)) AS AdGuid, CAST(BusinessUnitId AS nvarchar(40)) AS BusinessUnitId, "
        f"AccessMode FROM {p}SystemUserBase WHERE IsDisabled = 0")
    out = []
    for r in rows:
        dn = str(r.get("DomainName") or "").strip()
        try:
            mode = int(r.get("AccessMode")) if r.get("AccessMode") is not None else None
        except (TypeError, ValueError):
            mode = None
        out.append({"id": _guid(r.get("SystemUserId")), "name": " ".join(str(r.get("FullName") or "").split()),
                    "domainName": dn, "account": people_mod.account(dn) if dn else "", "adGuid": _guid(r.get("AdGuid")),
                    "unitId": _guid(r.get("BusinessUnitId")), "accessMode": mode,
                    "interactive": mode in (0, 1) and bool(dn)})
    return out


def crm_units(run: Runner, p: str, manager_column: str) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Etkin iş birimleri. Dönen: (birimler, not). Yönetici kolonu okunamazsa kolonsuz tekrar okunur."""
    note = None
    col = manager_column if _NAME.match(manager_column or "") else ""
    base = ("SELECT CAST(BusinessUnitId AS nvarchar(40)) AS BusinessUnitId, Name, "
            "CAST(ParentBusinessUnitId AS nvarchar(40)) AS ParentId{mgr} FROM " + p + "BusinessUnitBase WHERE IsDisabled = 0")
    rows: list[dict[str, Any]]
    if col:
        try:
            rows = run(base.format(mgr=f", CAST({col} AS nvarchar(40)) AS ManagerId"))
        except SourceError as e:
            note = f"Birim yöneticisi kolonu ({col}) okunamadı; yönetici boş bırakıldı. ({e})"
            rows = run(base.format(mgr=""))
    else:
        note = "Birim yöneticisi kolonu ayarlanmamış; yönetici boş bırakıldı."
        rows = run(base.format(mgr=""))
    out = [{"id": _guid(r.get("BusinessUnitId")), "name": " ".join(str(r.get("Name") or "").split()),
            "parentId": _guid(r.get("ParentId")) or None, "managerId": _guid(r.get("ManagerId")) or None} for r in rows]
    return out, note


def crm_team_members(run: Runner, p: str) -> list[dict[str, Any]]:
    rows = run(
        "SELECT CAST(t.TeamId AS nvarchar(40)) AS TeamId, t.Name AS TeamName, CAST(m.SystemUserId AS nvarchar(40)) AS UserId "
        f"FROM {p}TeamMembership m JOIN {p}TeamBase t ON t.TeamId = m.TeamId "
        f"JOIN {p}SystemUserBase u ON u.SystemUserId = m.SystemUserId WHERE u.IsDisabled = 0")
    return [{"teamId": _guid(r.get("TeamId")), "team": " ".join(str(r.get("TeamName") or "").split()),
             "userId": _guid(r.get("UserId"))} for r in rows]


def sync_preview(users: list[dict[str, Any]], units: list[dict[str, Any]], teams: list[dict[str, Any]],
                 ad: Optional[dict[str, dict[str, Any]]], stored_employees: list[dict[str, Any]],
                 stored_units: list[dict[str, Any]], notes: Optional[list[str]] = None) -> dict[str, Any]:
    """CRM ∩ AD → çalışan ve birim önerisi; kayıttaki durumla karşılaştırma. Hiçbir şey yazmaz.

    Dönen `stats` kabul betiğinin karşılaştırdığı sayılardır."""
    notes = list(notes or [])
    unit_name = {u["id"]: u["name"] for u in units}
    interactive = [u for u in users if u["interactive"]]
    matched: list[dict[str, Any]] = []
    for u in interactive:
        rec = None
        if ad is not None:
            rec = (ad.get("guid:" + u["adGuid"]) if u["adGuid"] else None) or ad.get(u["account"])
            if rec is None:
                continue                                   # AD'de yok ya da devre dışı: çalışan önerilmez
        src = {"display_name": "crm", "unit_id": "crm", "username": "ad" if rec else "crm", "ad_guid": "crm"}
        matched.append({"crmSystemUserId": u["id"], "displayName": u["name"] or u["account"],
                        "username": (rec or {}).get("account") or u["account"], "adGuid": u["adGuid"] or None,
                        "crmBusinessUnitId": u["unitId"] or None, "unitName": unit_name.get(u["unitId"], ""),
                        "lastLogon": (rec or {}).get("lastLogon").isoformat() if (rec or {}).get("lastLogon") else None,
                        "source": src})
    if ad is None:
        notes.append("AD ayarı yok ya da okunamadı: öneri yalnız CRM'deki etkin kullanıcılardan; ayrılmış kişiler ayıklanmadı.")

    by_crm = {e["crmSystemUserId"]: e for e in stored_employees if e.get("crmSystemUserId")}
    stored_unit_by_crm = {u["crmBusinessUnitId"]: u for u in stored_units if u.get("crmBusinessUnitId")}
    employees = []
    for m in matched:
        cur = by_crm.get(m["crmSystemUserId"])
        if cur is None:
            employees.append({**m, "action": "yeni", "changes": {}})
            continue
        manual = {k for k, v in (cur.get("source") or {}).items() if v == "ik"}
        want_unit = (stored_unit_by_crm.get(m["crmBusinessUnitId"] or "") or {}).get("id")
        changes = {}
        for api, col, new in (("displayName", "display_name", m["displayName"]), ("username", "username", m["username"]),
                              ("unitId", "unit_id", want_unit)):
            if col in manual or new is None and api == "unitId":
                continue
            if (cur.get(api) or None) != (new or None):
                changes[api] = {"once": cur.get(api), "sonra": new}
        if cur.get("status") != "aktif" and "status" not in manual:
            changes["status"] = {"once": cur.get("status"), "sonra": "aktif"}
        employees.append({**m, "id": cur["id"], "action": "degisti" if changes else "ayni", "changes": changes})
    seen = {m["crmSystemUserId"] for m in matched}
    departed = [{"id": e["id"], "displayName": e["displayName"], "username": e.get("username"), "unitName": e.get("unitName")}
                for e in stored_employees
                if e.get("crmSystemUserId") and e["crmSystemUserId"] not in seen and e.get("status") == "aktif"
                and "status" not in {k for k, v in (e.get("source") or {}).items() if v == "ik"}]

    enabled_by_unit: dict[str, int] = {}
    for u in users:
        enabled_by_unit[u["unitId"]] = enabled_by_unit.get(u["unitId"], 0) + 1
    unit_rows = []
    for u in units:
        cur = stored_unit_by_crm.get(u["id"])
        action = "yeni" if cur is None else ("degisti" if cur["name"] != u["name"] else "ayni")
        unit_rows.append({"crmBusinessUnitId": u["id"], "name": u["name"], "crmParentId": u["parentId"],
                          "crmManagerId": u["managerId"], "action": action, "enabledUsers": enabled_by_unit.get(u["id"], 0),
                          "employees": sum(1 for m in matched if m["crmBusinessUnitId"] == u["id"])})
    team_counts: dict[str, dict[str, Any]] = {}
    for t in teams:
        row = team_counts.setdefault(t["teamId"], {"teamId": t["teamId"], "team": t["team"], "members": 0})
        row["members"] += 1
    return {
        "employees": employees,
        "departed": departed,
        "units": unit_rows,
        "teams": sorted(team_counts.values(), key=lambda x: (-x["members"], x["team"].casefold())),
        "stats": {
            "crmEnabled": len(users),
            "crmInteractive": len(interactive),
            "adChecked": ad is not None,
            "matched": len(matched),
            "units": len(units),
            "unitsWithManager": sum(1 for u in units if u["managerId"]),
            "new": sum(1 for e in employees if e["action"] == "yeni"),
            "changed": sum(1 for e in employees if e["action"] == "degisti"),
            "departed": len(departed),
            "unitsNew": sum(1 for u in unit_rows if u["action"] == "yeni"),
        },
        "notes": notes,
    }


def read_preview(crm_file: str, schema: str, manager_column: str, ad_conf: dict[str, str],
                 stored_employees: list[dict[str, Any]], stored_units: list[dict[str, Any]],
                 ad_reader: Optional[Callable[[dict[str, str]], Optional[dict[str, dict[str, Any]]]]] = None) -> dict[str, Any]:
    """CRM + AD'yi okuyup öneriyi kurar. CRM okunamazsa SourceError; AD okunamazsa not düşülür, CRM ile devam edilir."""
    from semantic_bridge import hr_kaynak

    run = hr_kaynak.recording("crm", "CRM kullanıcı, birim ve ekip okuması", runner(crm_file))   # sorgu bilgisi
    p = prefix(schema)
    users = crm_users(run, p)
    units, note = crm_units(run, p, manager_column)
    teams = crm_team_members(run, p)
    notes = [note] if note else []
    ad = None
    try:
        ad = (ad_reader or people_mod.ad_people)(ad_conf)
    except Exception as e:  # noqa: BLE001
        log.warning("hr: AD okunamadı: %s", e)
        notes.append("AD okunamadı; öneri yalnız CRM'den.")
    return sync_preview(users, units, teams, ad, stored_employees, stored_units, notes)
