"""M56 salt okunur kaynakları: Logo satış temsilcisi bazında faturalı net satış, CRM sahiplik sayıları, M2 görev özeti.

Hiçbir kaynağa yazılmaz. Logo ve CRM kendi salt okunur bağlantısıyla okunur (`budget_sources.runner`); M2 görevleri köprü
veritabanında (`semantic_editorial_tasks`).

Tanımlar (kabul betiği `scripts/acceptance/M56/` aynı tanımı bağımsız SQL ile sınar):

- **Temsilci net satışı** = faturalı satırlar (`INVOICEREF <> 0`, `LINETYPE = 0`, `CANCELLED = 0`), satış `TRCODE` 7, 8, 9 `LINENET`
  eksi iade 2, 3 `LINENET`; fatura başlığındaki `SALESMANREF` → `LG_SLSMAN.CODE` (satış elemanı kartı firmadan bağımsız
  tek tablodadır; `LG_<firma>_SLSMAN` yoktur). Yıl → firma `L_CAPIPERIOD`'dan
  (`budget_sources.firms_by_year`; 2021–2025 LG_211, 2026 LG_411). Dönem iki uç dahil.
- **Temsilci alanı doluluğu** = aynı yılın satış faturalarında `SALESMANREF <> 0` oranı; düşükse sistem ölçüsü açılmaz
  (`HR_PERF_LOGO_SALES`, ölçüm sonrası kullanıcı kararı).
- **CRM sahiplik** = `new_projeBase` ve `new_sozlesmeBase`'de `OwnerId` = kişinin CRM kullanıcısı, `CreatedOn` dönem içinde.
  Bu sayı performans ölçüsü değildir; toplu kayıt servis hesabında birikebilir (analiz §6).
- **M2 görev özeti** = `semantic_editorial_tasks`'ta `editor_id` = kişinin CRM kullanıcısı; tamamlanan (`status = 'tamamlandi'`,
  `done_at` dönem içinde), bunların terminli olanı ve termininde biteni (`done_at::date <= due_date`), dönem sonunda termini
  geçmiş açık görev.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge import budget_sources as bsrc

SourceError = bsrc.SourceError

_CODE = re.compile(r"^[\w .\-/]{1,40}$", re.U)
_GUID = re.compile(r"^[0-9a-fA-F-]{36}$")


def _lit(code: str) -> str:
    code = (code or "").strip()
    if not _CODE.match(code):
        raise SourceError("Satış temsilcisi kodu geçerli değil.")
    return "N'" + code.replace("'", "''") + "'"


def _record(conn: str, title: str, text: str, desc: str) -> None:
    """Sorgu bilgisi: çalışan metin açık yakalayıcıya (hr_kaynak) yazılır; yakalayıcı yoksa iş yapmaz."""
    from semantic_bridge import hr_kaynak

    hr_kaynak.record(conn, title, text, description=desc)


def salesman_net_sql(firm: str, code: str, start: date, end: date) -> str:
    return f"""
SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net, COUNT(DISTINCT S.INVOICEREF) AS fatura,
       MAX(S.DATE_) AS son
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_01_INVOICE AS I ON I.LOGICALREF = S.INVOICEREF
JOIN dbo.LG_SLSMAN AS M ON M.LOGICALREF = I.SALESMANREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{start.isoformat()}' AND S.DATE_ < '{(end + timedelta(days=1)).isoformat()}'
  AND M.CODE = {_lit(code)}""".strip()


def salesman_fill_sql(firm: str, year: int) -> str:
    return (f"SELECT COUNT(*) AS satir, SUM(CASE WHEN SALESMANREF <> 0 THEN 1 ELSE 0 END) AS temsilcili "
            f"FROM dbo.LG_{firm}_01_INVOICE WHERE CANCELLED = 0 AND TRCODE IN (7,8,9) "
            f"AND DATE_ >= '{year}-01-01' AND DATE_ < '{year + 1}-01-01'")


def salesman_net(run: bsrc.Runner, code: str, start: date, end: date) -> dict[str, Any]:
    """Dönem yıllara bölünür; her yıl kendi firmasından okunur (yıl birleştirme çift sayması yok: yıl başına tek firma)."""
    firms = bsrc.firms_by_year(run)
    total, invoices, last = 0.0, 0, None
    years = []
    for y in range(start.year, end.year + 1):
        firm = firms.get(y)
        if not firm:
            years.append({"year": y, "firm": None, "note": "Logo'da bu yılın dönemi yok"})
            continue
        ys, ye = max(start, date(y, 1, 1)), min(end, date(y, 12, 31))
        text = salesman_net_sql(firm, code, ys, ye)
        row = (run(text) or [{}])[0]
        _record("logo", f"Logo temsilci net satışı · {y}", text,
                "Faturalı satış satırları (7, 8, 9) − iadeler (2, 3), fatura temsilcisi = hedefin ölçü kodu.")
        net = float(row.get("net") or 0)
        total += net
        invoices += int(row.get("fatura") or 0)
        d = bsrc._day(row.get("son"))
        if d and (last is None or d > last):
            last = d
        years.append({"year": y, "firm": firm, "net": round(net, 2)})
    return {"value": round(total, 2), "invoices": invoices, "lastDate": last.isoformat() if last else None, "years": years}


def salesman_fill(run: bsrc.Runner, year: int) -> dict[str, Any]:
    firm = bsrc._firm(bsrc.firms_by_year(run), year)
    text = salesman_fill_sql(firm, year)
    row = (run(text) or [{}])[0]
    _record("logo", f"Logo satış faturası temsilci alanı · {year}", text, "Satış faturalarında temsilci alanı doluluğu.")
    n, k = int(row.get("satir") or 0), int(row.get("temsilcili") or 0)
    return {"year": year, "firm": firm, "invoices": n, "withSalesman": k, "rate": (k / n) if n else None}


def crm_ownership(run: bsrc.Runner, prefix: str, systemuser_id: str, start: date, end: date) -> dict[str, int]:
    if not _GUID.match(systemuser_id or ""):
        raise SourceError("CRM kullanıcı kimliği geçerli değil.")
    rng = f"CreatedOn >= '{start.isoformat()}' AND CreatedOn < '{(end + timedelta(days=1)).isoformat()}'"
    out = {}
    for key, table in (("projects", "new_projeBase"), ("contracts", "new_sozlesmeBase")):
        text = f"SELECT COUNT(*) AS n FROM {prefix}{table} WHERE OwnerId = '{systemuser_id}' AND {rng}"
        rows = run(text)
        _record("crm", f"CRM sahiplik sayısı · {table}", text, "Dönemde oluşturulan ve sahibi çalışan olan kayıtlar.")
        out[key] = int((rows or [{}])[0].get("n") or 0)
    return out


def editorial_facts(engine: sa.engine.Engine, tenant: str, crm_id: Optional[str], start: date, end: date) -> dict[str, Any]:
    from semantic_bridge import editorial_assign as ea

    if not crm_id:
        return {"available": False, "reason": "Çalışanın CRM kullanıcısı bağlı değil."}
    t = ea.TASKS
    try:
        with engine.connect() as c:
            if not sa.inspect(c).has_table(t.name):
                return {"available": False, "reason": "Editör atama kayıtları bu kurulumda yok."}
            rows = c.execute(sa.select(t.c.status, t.c.done_at, t.c.due_date).where(
                t.c.tenant_id == tenant, sa.func.lower(t.c.editor_id) == crm_id.lower())).all()
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"Görev kayıtları okunamadı: {type(e).__name__}"}
    done = [r for r in rows if r.status == "tamamlandi" and r.done_at is not None and start <= _d(r.done_at) <= end]
    with_due = [r for r in done if r.due_date]
    on_time = [r for r in with_due if _d(r.done_at) <= r.due_date]
    open_overdue = [r for r in rows if r.status not in ("tamamlandi", "iptal") and r.due_date and r.due_date < end
                    and r.due_date >= start]
    return {"available": True, "done": len(done), "withDue": len(with_due), "onTime": len(on_time), "openOverdue": len(open_overdue),
            "source": "semantic_editorial_tasks"}


def _d(v: Any) -> date:
    return v.date() if hasattr(v, "date") else v
