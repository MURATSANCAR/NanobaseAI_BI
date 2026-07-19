"""Budget board-pack export — PDF + multi-sheet Excel."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from nanobase_api.budget_fx import convert_amount, list_fx_rates
from nanobase_api.budget_lines import list_commitments, list_periods
from nanobase_api.budgets import budget_summary, list_budgets

_EXPORTS_DIR = Path("/tmp/nanobase-budget-exports")

_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Budget board pack",
        "subtitle": "Fiscal year {year}",
        "meta": "Generated {generated} · {count} lines · {scenario}{currency_note}",
        "mixed_currency": "Mixed currencies — totals may be incomplete without FX.",
        "fx_missing": "{count} line(s) omitted due to missing FX rates.",
        "board_note": "Board pack export — read-only snapshot.",
        "kpi_allocated": "Allocated",
        "kpi_actual": "Actual",
        "kpi_remaining": "Remaining",
        "kpi_watch": "Watch",
        "section_by_kind": "By kind",
        "section_lines": "Budget lines",
        "empty": "No budget lines for this filter.",
        "col_name": "Name",
        "col_kind": "Kind",
        "col_cc": "Cost center",
        "col_currency": "Currency",
        "col_allocated": "Allocated",
        "col_committed": "Committed",
        "col_actual": "Actual",
        "col_remaining": "Remaining",
        "col_used": "Used %",
        "col_health": "Health",
        "col_status": "Status",
        "col_description": "Description",
        "col_amount": "Amount",
        "col_due": "Due",
        "col_month": "M{month}",
        "kind_opex": "OPEX",
        "kind_capex": "CAPEX",
        "kind_other": "Other",
        "health_ok": "OK",
        "health_watch": "Watch",
        "health_over": "Over",
        "health_na": "—",
        "sheet_summary": "Summary",
        "sheet_lines": "Lines",
        "sheet_kinds": "By kind",
        "sheet_monthly": "Monthly",
        "sheet_commitments": "Commitments",
        "sheet_scenario": "Scenario: {scenario}",
    },
    "tr": {
        "title": "Bütçe yönetim paketi",
        "subtitle": "Mali yıl {year}",
        "meta": "Oluşturulma {generated} · {count} kalem · {scenario}{currency_note}",
        "mixed_currency": "Karma para birimleri — FX olmadan toplamlar eksik olabilir.",
        "fx_missing": "{count} kalem eksik kur nedeniyle atlandı.",
        "board_note": "Yönetim paketi dışa aktarımı — salt okunur anlık görüntü.",
        "kpi_allocated": "Planlanan",
        "kpi_actual": "Gerçekleşen",
        "kpi_remaining": "Kalan",
        "kpi_watch": "İzleme",
        "section_by_kind": "Türe göre",
        "section_lines": "Bütçe kalemleri",
        "empty": "Bu filtre için bütçe kalemi yok.",
        "col_name": "Kalem",
        "col_kind": "Tür",
        "col_cc": "Maliyet merkezi",
        "col_currency": "Para birimi",
        "col_allocated": "Planlanan",
        "col_committed": "Taahhüt",
        "col_actual": "Gerçekleşen",
        "col_remaining": "Kalan",
        "col_used": "Kullanım %",
        "col_health": "Durum",
        "col_status": "Statü",
        "col_description": "Açıklama",
        "col_amount": "Tutar",
        "col_due": "Vade",
        "col_month": "A{month}",
        "kind_opex": "OPEX",
        "kind_capex": "CAPEX",
        "kind_other": "Diğer",
        "health_ok": "İyi",
        "health_watch": "İzle",
        "health_over": "Aşım",
        "health_na": "—",
        "sheet_summary": "Özet",
        "sheet_lines": "Kalemler",
        "sheet_kinds": "Türler",
        "sheet_monthly": "Aylık",
        "sheet_commitments": "Taahhütler",
        "sheet_scenario": "Senaryo: {scenario}",
    },
}


def _exports_dir() -> Path:
    _EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return _EXPORTS_DIR


def _export_path(ext: str) -> Path:
    name = f"budget-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.{ext}"
    return _exports_dir() / name


def _norm_locale(locale: str | None) -> str:
    loc = (locale or "en").strip().lower()[:2] or "en"
    return loc if loc in _LABELS else "en"


def _label(locale: str, key: str, **kwargs: Any) -> str:
    tpl = _LABELS.get(locale, _LABELS["en"]).get(key) or _LABELS["en"].get(key) or key
    try:
        return tpl.format(**kwargs)
    except Exception:
        return tpl


def _money(n: Any) -> str:
    try:
        return f"{float(n):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _health_label(locale: str, health: str | None) -> str:
    if health == "ok":
        return _label(locale, "health_ok")
    if health == "watch":
        return _label(locale, "health_watch")
    if health == "over":
        return _label(locale, "health_over")
    return _label(locale, "health_na")


def _kind_label(locale: str, kind: str) -> str:
    k = (kind or "other").lower()
    if k == "opex":
        return _label(locale, "kind_opex")
    if k == "capex":
        return _label(locale, "kind_capex")
    return _label(locale, "kind_other")


def _norm_scenario(scenario: str | None) -> str:
    s = (scenario or "base").strip().lower() or "base"
    if s not in ("base", "optimistic", "pessimistic"):
        return "base"
    return s


def display_budget_lines(
    engine: Engine,
    *,
    fiscal_year: int,
    tenant_id: str | None,
    scenario: str = "base",
    reporting_currency: str | None = None,
) -> list[dict[str, Any]]:
    """Scenario-filtered lines; when reporting_currency set, FX-convert or omit missing rates."""
    scen = _norm_scenario(scenario)
    tid = str(tenant_id or "default")
    items = list_budgets(engine, fiscal_year=fiscal_year, scenario=scen, tenant_id=tid)
    report_ccy = (reporting_currency or "").strip().upper() or None
    if not report_ccy:
        return items

    rates = list_fx_rates(engine, tenant_id=tid)
    out: list[dict[str, Any]] = []
    for item in items:
        ccy = str(item.get("currency") or "TRY").upper()
        allocated = float(item.get("allocated") or 0)
        committed = float(item.get("committed") or 0)
        actual = (
            float(item.get("actual"))
            if item.get("actual") is not None and not item.get("actual_error")
            else None
        )
        remaining = item.get("remaining")
        remaining_n = float(remaining) if remaining is not None else None

        a = convert_amount(allocated, from_currency=ccy, to_currency=report_ccy, rates=rates)
        c = convert_amount(committed, from_currency=ccy, to_currency=report_ccy, rates=rates)
        act = (
            convert_amount(actual, from_currency=ccy, to_currency=report_ccy, rates=rates)
            if actual is not None
            else None
        )
        rem = (
            convert_amount(remaining_n, from_currency=ccy, to_currency=report_ccy, rates=rates)
            if remaining_n is not None
            else None
        )
        if a is None or c is None or (actual is not None and act is None):
            continue
        row = dict(item)
        row["allocated"] = a
        row["committed"] = c
        row["actual"] = act
        row["remaining"] = rem
        row["currency"] = report_ccy
        out.append(row)
    return out


def build_budget_pdf(
    engine: Engine,
    *,
    fiscal_year: int,
    locale: str | None = None,
    tenant_id: str | None = None,
    scenario: str = "base",
    reporting_currency: str | None = None,
) -> Path:
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise ValueError("bi_budget_export_pdf_unavailable") from exc

    loc = _norm_locale(locale)
    scen = _norm_scenario(scenario)
    tid = str(tenant_id or "default")
    report_ccy = (reporting_currency or "").strip().upper() or None
    items = display_budget_lines(
        engine,
        fiscal_year=fiscal_year,
        tenant_id=tid,
        scenario=scen,
        reporting_currency=report_ccy,
    )
    summary = budget_summary(
        engine,
        fiscal_year=fiscal_year,
        tenant_id=tid,
        scenario=scen,
        reporting_currency=report_ccy,
    )
    totals = summary.get("totals") or {}
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    currency_note = f" · {report_ccy}" if report_ccy else ""

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    # Prefer Unicode TTF so TR labels / envelope names render; fall back to latinized Helvetica.
    font_family = "Helvetica"
    regular = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    bold = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    if not regular.is_file():
        regular = Path("/usr/share/fonts/dejavu/DejaVuSans.ttf")
        bold = Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf")
    if regular.is_file():
        try:
            pdf.add_font("DejaVu", "", str(regular))
            pdf.add_font("DejaVu", "B", str(bold if bold.is_file() else regular))
            font_family = "DejaVu"
        except Exception:
            font_family = "Helvetica"

    def _txt(value: Any) -> str:
        s = str(value or "")
        if font_family != "Helvetica":
            return s
        return (
            s.replace("ı", "i")
            .replace("İ", "I")
            .replace("ğ", "g")
            .replace("Ğ", "G")
            .replace("ü", "u")
            .replace("Ü", "U")
            .replace("ş", "s")
            .replace("Ş", "S")
            .replace("ö", "o")
            .replace("Ö", "O")
            .replace("ç", "c")
            .replace("Ç", "C")
            .replace("·", "-")
            .encode("latin-1", "replace")
            .decode("latin-1")
        )

    pdf.set_font(font_family, "B", 16)
    pdf.cell(0, 10, _txt(_label(loc, "title")), ln=True)
    pdf.set_font(font_family, size=11)
    pdf.cell(0, 8, _txt(_label(loc, "subtitle", year=fiscal_year)), ln=True)
    pdf.set_font(font_family, size=9)
    pdf.multi_cell(
        0,
        5,
        _txt(
            _label(
                loc,
                "meta",
                generated=generated,
                count=len(items),
                scenario=scen,
                currency_note=currency_note,
            )
        ),
    )
    pdf.ln(2)

    if summary.get("mixed_currency"):
        pdf.multi_cell(0, 5, _txt(_label(loc, "mixed_currency")))
    fx_missing = summary.get("fx_missing") or []
    if fx_missing:
        pdf.multi_cell(0, 5, _txt(_label(loc, "fx_missing", count=len(fx_missing))))

    for key, val in (
        ("kpi_allocated", totals.get("allocated")),
        ("kpi_actual", totals.get("actual")),
        ("kpi_remaining", totals.get("remaining")),
        ("kpi_watch", summary.get("budget_watch_count") or 0),
    ):
        pdf.set_font(font_family, size=10)
        pdf.cell(50, 6, _txt(_label(loc, key)), border=0)
        pdf.cell(0, 6, _txt(_money(val) if key != "kpi_watch" else str(int(val or 0))), ln=True)

    pdf.ln(4)
    pdf.set_font(font_family, "B", 12)
    pdf.cell(0, 8, _txt(_label(loc, "section_lines")), ln=True)
    pdf.set_font(font_family, "B", 8)
    headers = [
        _label(loc, "col_name"),
        _label(loc, "col_kind"),
        _label(loc, "col_allocated"),
        _label(loc, "col_actual"),
        _label(loc, "col_health"),
    ]
    widths = [70, 25, 30, 30, 25]
    for h, w in zip(headers, widths):
        pdf.cell(w, 6, _txt(h)[:20], border=1)
    pdf.ln()
    pdf.set_font(font_family, size=8)
    if not items:
        pdf.cell(0, 6, _txt(_label(loc, "empty")), ln=True)
    else:
        for b in items[:80]:
            vals = [
                str(b.get("name") or "")[:36],
                _kind_label(loc, str(b.get("kind") or "")),
                _money(b.get("allocated")),
                _money(b.get("actual")),
                _health_label(loc, b.get("health")),
            ]
            for v, w in zip(vals, widths):
                pdf.cell(w, 6, _txt(v)[:40], border=1)
            pdf.ln()

    path = _export_path("pdf")
    out = pdf.output()
    path.write_bytes(bytes(out) if not isinstance(out, (bytes, bytearray)) else bytes(out))
    return path


def build_budget_xlsx(
    engine: Engine,
    *,
    fiscal_year: int,
    locale: str | None = None,
    tenant_id: str | None = None,
    scenario: str = "base",
    reporting_currency: str | None = None,
) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    loc = _norm_locale(locale)
    scen = _norm_scenario(scenario)
    tid = str(tenant_id or "default")
    report_ccy = (reporting_currency or "").strip().upper() or None
    items = display_budget_lines(
        engine,
        fiscal_year=fiscal_year,
        tenant_id=tid,
        scenario=scen,
        reporting_currency=report_ccy,
    )
    summary = budget_summary(
        engine,
        fiscal_year=fiscal_year,
        tenant_id=tid,
        scenario=scen,
        reporting_currency=report_ccy,
    )
    totals = summary.get("totals") or {}

    wb = Workbook()
    ws = wb.active
    ws.title = _label(loc, "sheet_summary")[:31]
    navy = PatternFill("solid", fgColor="0F172A")
    white = Font(bold=True, color="FFFFFF", size=14)
    ws["A1"] = _label(loc, "title")
    ws["A1"].fill = navy
    ws["A1"].font = white
    ws.merge_cells("A1:D1")
    ws["A2"] = _label(loc, "subtitle", year=fiscal_year)
    ws["A3"] = _label(loc, "sheet_scenario", scenario=scen)
    if report_ccy:
        ws["B3"] = report_ccy
    if summary.get("mixed_currency"):
        ws["A4"] = _label(loc, "mixed_currency")
    fx_missing = summary.get("fx_missing") or []
    if fx_missing:
        ws["A4"] = _label(loc, "fx_missing", count=len(fx_missing))
    ws["A5"] = _label(loc, "kpi_allocated")
    ws["B5"] = float(totals.get("allocated") or 0) if totals.get("allocated") is not None else None
    ws["A6"] = _label(loc, "kpi_actual")
    ws["B6"] = float(totals.get("actual") or 0) if totals.get("actual") is not None else None
    ws["A7"] = _label(loc, "kpi_remaining")
    ws["B7"] = float(totals.get("remaining") or 0) if totals.get("remaining") is not None else None
    ws["A8"] = _label(loc, "kpi_watch")
    ws["B8"] = int(summary.get("budget_watch_count") or 0)
    ws["A9"] = _label(loc, "board_note")
    ws.merge_cells("A9:D9")
    ws["A9"].alignment = Alignment(wrap_text=True)
    for r in range(5, 8):
        if ws[f"B{r}"].value is not None:
            ws[f"B{r}"].number_format = "#,##0"

    lines = wb.create_sheet(_label(loc, "sheet_lines")[:31])
    headers = [
        _label(loc, "col_name"),
        _label(loc, "col_cc"),
        _label(loc, "col_kind"),
        _label(loc, "col_currency"),
        _label(loc, "col_allocated"),
        _label(loc, "col_committed"),
        _label(loc, "col_actual"),
        _label(loc, "col_remaining"),
        _label(loc, "col_used"),
        _label(loc, "col_health"),
        _label(loc, "col_status"),
    ]
    for ci, h in enumerate(headers, start=1):
        cell = lines.cell(1, ci, h)
        cell.fill = navy
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(wrap_text=True)
    lines.freeze_panes = "A2"
    for ri, b in enumerate(items, start=2):
        vals = [
            b.get("name"),
            b.get("cost_center"),
            _kind_label(loc, str(b.get("kind") or "")),
            b.get("currency") or report_ccy or "TRY",
            float(b.get("allocated") or 0),
            float(b.get("committed") or 0),
            float(b.get("actual") or 0) if b.get("actual") is not None else None,
            float(b.get("remaining") or 0) if b.get("remaining") is not None else None,
            float(b.get("used_pct") or 0) if b.get("used_pct") is not None else None,
            _health_label(loc, b.get("health")),
            b.get("status"),
        ]
        for ci, v in enumerate(vals, start=1):
            cell = lines.cell(ri, ci, v)
            if ci in (5, 6, 7, 8) and isinstance(v, (int, float)):
                cell.number_format = "#,##0"
            if ci == 9 and isinstance(v, (int, float)):
                cell.number_format = "0.0"
        health = b.get("health")
        fill = None
        if health == "over":
            fill = PatternFill("solid", fgColor="FEE2E2")
        elif health == "watch":
            fill = PatternFill("solid", fgColor="FEF3C7")
        elif health == "ok":
            fill = PatternFill("solid", fgColor="D1FAE5")
        if fill:
            lines.cell(ri, 10).fill = fill

    for i in range(1, 12):
        lines.column_dimensions[get_column_letter(i)].width = 14
    lines.column_dimensions["A"].width = 28

    kinds = wb.create_sheet(_label(loc, "sheet_kinds")[:31])
    kinds.append(
        [
            _label(loc, "col_kind"),
            _label(loc, "col_allocated"),
            _label(loc, "col_actual"),
            _label(loc, "col_remaining"),
            "#",
        ]
    )
    for cell in kinds[1]:
        cell.fill = navy
        cell.font = Font(bold=True, color="FFFFFF")
    by_kind = summary.get("by_kind") or {}
    for kind in ("opex", "capex", "other"):
        bucket = by_kind.get(kind) or {}
        kinds.append(
            [
                _kind_label(loc, kind),
                float(bucket.get("allocated") or 0),
                float(bucket.get("actual") or 0),
                float(bucket.get("remaining") or 0),
                int(bucket.get("count") or 0),
            ]
        )

    monthly = wb.create_sheet(_label(loc, "sheet_monthly")[:31])
    month_headers = [_label(loc, "col_name"), _label(loc, "col_kind")] + [
        _label(loc, "col_month", month=i) for i in range(1, 13)
    ]
    monthly.append(month_headers)
    for cell in monthly[1]:
        cell.fill = navy
        cell.font = Font(bold=True, color="FFFFFF")
    try:
        for b in items:
            periods = list_periods(engine, str(b.get("id")), tenant_id=tid)
            by_idx = {int(p.get("period_index") or 0): p for p in periods}
            monthly.append(
                [
                    b.get("name"),
                    _kind_label(loc, str(b.get("kind") or "")),
                    *[float((by_idx.get(i) or {}).get("allocated") or 0) for i in range(1, 13)],
                ]
            )
    except Exception:
        pass

    commits = wb.create_sheet(_label(loc, "sheet_commitments")[:31])
    commits.append(
        [
            _label(loc, "col_name"),
            _label(loc, "col_kind"),
            _label(loc, "col_cc"),
            _label(loc, "col_description"),
            _label(loc, "col_amount"),
            _label(loc, "col_currency"),
            _label(loc, "col_status"),
            _label(loc, "col_due"),
            "ID",
        ]
    )
    for cell in commits[1]:
        cell.fill = navy
        cell.font = Font(bold=True, color="FFFFFF")
    try:
        for b in items:
            for c in list_commitments(engine, str(b.get("id")), tenant_id=tid):
                commits.append(
                    [
                        b.get("name"),
                        _kind_label(loc, str(b.get("kind") or "")),
                        b.get("cost_center") or "",
                        c.get("description") or "",
                        float(c.get("amount") or 0),
                        c.get("currency") or b.get("currency") or report_ccy or "TRY",
                        c.get("status") or "",
                        c.get("due_date") or "",
                        c.get("id") or "",
                    ]
                )
    except Exception:
        pass

    path = _export_path("xlsx")
    wb.save(path)
    return path


def export_budget_board_pack(
    engine: Engine,
    *,
    format: str,
    fiscal_year: int,
    locale: str | None = None,
    tenant_id: str | None = None,
    scenario: str = "base",
    reporting_currency: str | None = None,
) -> Path:
    fmt = (format or "pdf").lower().strip()
    if fmt == "xlsx":
        return build_budget_xlsx(
            engine,
            fiscal_year=fiscal_year,
            locale=locale,
            tenant_id=tenant_id,
            scenario=scenario,
            reporting_currency=reporting_currency,
        )
    if fmt == "pdf":
        return build_budget_pdf(
            engine,
            fiscal_year=fiscal_year,
            locale=locale,
            tenant_id=tenant_id,
            scenario=scenario,
            reporting_currency=reporting_currency,
        )
    raise ValueError("bi_budget_export_format_invalid")
