"""CSV indiren her uca Excel (.xlsx) eşi — tek ara katman, uçlara tek tek dokunmadan (kullanıcı isteği 2026-09-29).

Kural:
- Ekrandaki «Excel» düğmesi CSV'nin adresine `bicim=xlsx` ekler. İstek aynı uçtan, aynı sayfa kapısından ve aynı
  dışa aktarma yetkisinden (`ozellik:veri.disa-aktar`) geçer; erişim kaydı da aynı yola düşer. Uç CSV (`text/csv`)
  döndürürse cevap burada Excel'e çevrilir; başka bir şey (hata, JSON, uç zaten Excel veriyorsa) olduğu gibi geçer.
- Excel'deki satırlar CSV'deki satırların birebir aynısıdır (tavan yok, satır atlanmaz, sıra değişmez). Başlık kalın,
  ilk satır sabit, süzgeç açık, kolon genişliği içeriğe göre.
- Hücre türü yalnız tartışmasız olduğunda sayı/tarih olur; kuşkulu değer metin kalır (CSV'de nasıl görünüyorsa öyle):
  · Ondalık virgül (Türkçe, «1.234,56») ile ondalık nokta («1234.56») kolon kolon ayırt edilir; kolonda yalnız
    «12.500» gibi iki türlü okunabilen değer varsa dosyanın öteki kolonlarındaki alışkanlığa bakılır, o da yoksa metin.
  · Kod/numara kolonları (başlıkta kod, no, numara, ISBN, barkod, telefon, cep, VKN, TCKN, IBAN, id…), baştaki
    sıfırlı değerler ve 12 haneden uzun tam sayılar metin kalır (Excel bunları bozar: ISBN bilimsel gösterime döner).
  · «2026-09-29», «29.09.2026» tarih; saatli olanlar tarih-saat (yazılan saat, saat dilimi çevrilmez); «%12,5» yüzde.
  · «=», «+», «-», «@» ile başlayan metin formül olarak yazılmaz (hücre metin türünde).
- İstemcide üretilen CSV'ler (pano kartı, rehber, rapor önizlemesi) `POST /api/v1/export/xlsx` ile aynı çeviriden
  geçer; kişi zaten ekranda gördüğü satırları gönderir, bildirimi istemci `export-notice` ile yapar (CSV'deki gibi).
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Any, Callable, Optional
from urllib.parse import parse_qsl, quote, unquote

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PARAM = "bicim"

_TEXT_HEAD = re.compile(
    r"(^|[\s_\-./(])(kod|kodu|code|no|nosu|numara|numarası|numarasi|isbn|barkod|barcode|ean|telefon|tel|cep|gsm|phone|"
    r"vkn|tckn|tc|vergi|iban|id|uuid|guid|posta kodu|sku)($|[\s_\-./):])", re.I)
_INT = re.compile(r"^-?\d+$")
_DOT_DEC = re.compile(r"^-?\d+\.\d+$")                      # 1234.5 / 0.1234
_TR_DEC = re.compile(r"^-?(\d{1,3}(\.\d{3})+|\d+),\d+$")     # 1.234,56 / 12,5
_GROUPED = re.compile(r"^-?\d{1,3}(\.\d{3})+$")              # 12.500 — Türkçe binlik mi, nokta ondalık mı?
_PCT = re.compile(r"^(%\s?(?P<a>-?[\d.,]+)|(?P<b>-?[\d.,]+)\s?%)$")
_ISO_D = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DT = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")
_TR_D = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})(?: (\d{2}):(\d{2})(?::(\d{2}))?)?$")


# ------------------------------------------------------------------ CSV okuma


def decode(data: bytes | str) -> str:
    if isinstance(data, str):
        return data.lstrip("﻿")
    for enc in ("utf-8-sig", "cp1254"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse(text: str) -> list[list[str]]:
    """CSV metnini satırlara böler; ayraç (; , sekme) ilk satırdan anlaşılır, Excel'in «sep=;» satırı atlanır."""
    text = text.lstrip("﻿")
    first, _, rest = text.partition("\n")
    m = re.match(r"^sep=(.)\r?$", first)
    if m:
        delim, text = m.group(1), rest
    else:
        head = first
        counts = {d: _count_outside_quotes(head, d) for d in (";", "\t", ",")}
        delim = max(counts, key=lambda d: counts[d]) if any(counts.values()) else ";"
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    return rows


def _count_outside_quotes(line: str, d: str) -> int:
    n, q = 0, False
    for ch in line:
        if ch == '"':
            q = not q
        elif ch == d and not q:
            n += 1
    return n


# ------------------------------------------------------------------ hücre türü


def _num_style(values: list[str]) -> Optional[str]:
    """Kolonun sayı yazımı: 'tr' (virgül ondalık), 'dot' (nokta ondalık), 'int' (yalnız düz tam sayı), None (karar yok)."""
    tr = dot = grouped = False
    for v in values:
        if _TR_DEC.match(v):
            tr = True
        elif _DOT_DEC.match(v) and not _GROUPED.match(v):
            dot = True
        elif _GROUPED.match(v):
            grouped = True
    if tr and dot:
        return None
    if tr:
        return "tr"
    if dot:
        return "dot"
    return "grouped" if grouped else "int"


def _to_number(v: str, style: str) -> Optional[float | int]:
    neg = v.startswith("-")
    body = v[1:] if neg else v
    if _INT.match(body):
        if (len(body) > 1 and body.startswith("0")) or len(body) > 12:
            return None
        n: float | int = int(body)
    elif style == "tr" and (_TR_DEC.match(body) or _GROUPED.match(body)):
        n = float(body.replace(".", "").replace(",", "."))
        if n.is_integer() and "," not in body:
            n = int(n)
    elif style == "dot" and _DOT_DEC.match(body):
        n = float(body)
    else:
        return None
    return -n if neg else n


def _decimals(v: str, style: str) -> int:
    sep = "," if style == "tr" else "."
    if style in ("tr", "dot") and sep in v:
        return min(len(v.rsplit(sep, 1)[1]), 6)
    return 0


def _to_date(v: str) -> Optional[date | datetime]:
    try:
        if _ISO_D.match(v):
            return date.fromisoformat(v)
        m = _ISO_DT.match(v)
        if m:
            return datetime(*map(int, m.group(1).split("-")), int(m.group(2)), int(m.group(3)), int(m.group(4) or 0))
        m = _TR_D.match(v)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if m.group(4):
                return datetime(y, mo, d, int(m.group(4)), int(m.group(5)), int(m.group(6) or 0))
            return date(y, mo, d)
    except ValueError:
        return None
    return None


def _text_column(header: str) -> bool:
    h = " ".join(re.sub(r"([a-zçğıöşü])([A-ZÇĞİÖŞÜ])", r"\1 \2", header or "").split())
    return bool(_TEXT_HEAD.search(h))


def plan_columns(header: list[str], body: list[list[str]]) -> list[dict[str, Any]]:
    """Her kolon için tür kararı; dosyanın genel ondalık alışkanlığı belirsiz kolonlarda ölçü olur."""
    ncol = max([len(header)] + [len(r) for r in body]) if (header or body) else 0
    plans: list[dict[str, Any]] = []
    for i in range(ncol):
        name = header[i] if i < len(header) else ""
        vals = [r[i].strip() for r in body if i < len(r) and r[i].strip()]
        plans.append({"text": _text_column(name), "style": _num_style([v.lstrip("-") for v in vals]), "dec": 0})
    file_styles = {p["style"] for p in plans if p["style"] in ("tr", "dot")}
    file_style = file_styles.pop() if len(file_styles) == 1 else None
    for p in plans:
        if p["style"] == "grouped":
            p["style"] = "tr" if file_style == "tr" else None   # «12.500» nokta ondalık yazımda binlik ayraç olmaz
    return plans


def cell_value(v: str, plan: dict[str, Any]) -> tuple[Any, Optional[str]]:
    """(değer, sayı biçimi). Metin olarak kalan değer olduğu gibi döner."""
    s = v.strip()
    if not s:
        return None, None
    if plan["text"]:
        return v, None
    d = _to_date(s)
    if d is not None:
        return d, ("dd.mm.yyyy hh:mm" if isinstance(d, datetime) else "dd.mm.yyyy")
    style = plan["style"] or "int"
    m = _PCT.match(s)
    if m:
        raw = m.group("a") or m.group("b")
        pstyle = "tr" if "," in raw else ("dot" if "." in raw else style)
        n = _to_number(raw, pstyle)
        if n is not None:
            dec = _decimals(raw.lstrip("-"), pstyle)
            return n / 100, "0" + ("." + "0" * dec if dec else "") + "%"
        return v, None
    n = _to_number(s, style)
    if n is None:
        return v, None
    dec = _decimals(s.lstrip("-"), style)
    return n, "#,##0" + ("." + "0" * dec if dec else "")


# ------------------------------------------------------------------ Excel yazma


def sheet_title(name: str) -> str:
    base = re.sub(r"\.(csv|xlsx)$", "", name or "", flags=re.I)
    t = re.sub(r"[\[\]:*?/\\]", " ", base).strip()[:31]
    return t or "Liste"


def to_xlsx(data: bytes | str, title: str = "Liste") -> tuple[bytes, int]:
    """CSV → .xlsx baytları ve veri satırı sayısı (başlık hariç)."""
    from openpyxl import Workbook
    from openpyxl.cell.cell import TYPE_STRING
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    rows = parse(decode(data))
    header, body = (rows[0], rows[1:]) if rows else ([], [])
    plans = plan_columns(header, body)
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title(title)
    widths = [len(h) for h in header] + [0] * max(0, len(plans) - len(header))
    if header:
        ws.append(header)
        for c in ws[1]:
            c.font = Font(bold=True)
            c.alignment = Alignment(vertical="top", wrap_text=True)
    for r_i, row in enumerate(body, start=2 if header else 1):
        for c_i, raw in enumerate(row, start=1):
            plan = plans[c_i - 1] if c_i - 1 < len(plans) else {"text": True, "style": None}
            val, fmt = cell_value(raw, plan)
            if val is None:
                continue
            cell = ws.cell(row=r_i, column=c_i, value=val)
            if isinstance(val, str):
                cell.data_type = TYPE_STRING   # «=…» formül olarak çalışmaz
            if fmt:
                cell.number_format = fmt
            if c_i - 1 < len(widths):
                widths[c_i - 1] = max(widths[c_i - 1], min(len(raw), 80))
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(8, min(60, w + 2))
    if header:
        ws.freeze_panes = "A2"
        if plans:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(plans))}{max(1, len(body) + 1)}"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), len(body)


# ------------------------------------------------------------------ ara katman


def xlsx_name(disposition: str, fallback: str) -> str:
    """Content-Disposition'daki CSV adı → .xlsx adı (filename* öncelikli)."""
    m = re.search(r"filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)", disposition or "")
    name = unquote(m.group(1).strip().strip('"')) if m else ""
    if not name:
        m = re.search(r'filename\s*=\s*"([^"]+)"', disposition or "") or re.search(r"filename\s*=\s*([^;]+)", disposition or "")
        name = m.group(1).strip() if m else ""
    name = name or fallback or "liste.csv"
    return re.sub(r"\.csv$", "", name, flags=re.I) + ".xlsx"


def disposition(name: str) -> str:
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    ascii_name = name.translate(tr).encode("ascii", "ignore").decode() or "liste.xlsx"
    ascii_name = ascii_name.replace('"', "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


def _header_text(v: bytes) -> str:
    try:
        return v.decode("utf-8")
    except UnicodeDecodeError:
        return v.decode("latin-1")


def wants_xlsx(query_string: bytes) -> bool:
    try:
        return any(k == PARAM and v.strip().lower() == "xlsx" for k, v in parse_qsl(query_string.decode("latin-1")))
    except Exception:  # noqa: BLE001
        return False


class CsvToXlsx:
    """Saf ASGI ara katman: `bicim=xlsx` isteğinde CSV cevabını Excel'e çevirir; öteki her şey dokunulmadan geçer."""

    def __init__(self, app: Callable[..., Any]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        if scope.get("type") != "http" or not wants_xlsx(scope.get("query_string") or b""):
            await self.app(scope, receive, send)
            return
        start: dict[str, Any] = {}
        chunks: list[bytes] = []
        passthrough = False

        async def capture(message: dict[str, Any]) -> None:
            nonlocal passthrough
            if message["type"] == "http.response.start":
                ctype = dict((k.lower(), v) for k, v in message.get("headers") or []).get(b"content-type", b"")
                if message.get("status") != 200 or not ctype.lower().startswith(b"text/csv"):
                    passthrough = True
                    await send(message)
                    return
                start.update(message)
                return
            if passthrough:
                await send(message)
                return
            if message["type"] == "http.response.body":
                chunks.append(message.get("body") or b"")
                if message.get("more_body"):
                    return
                headers = [(k, v) for k, v in start.get("headers") or []]
                disp = next((_header_text(v) for k, v in headers if k.lower() == b"content-disposition"), "")
                path = scope.get("path") or ""
                name = xlsx_name(disp, path.rsplit("/", 1)[-1])
                body, _ = await run_in_threadpool(to_xlsx, b"".join(chunks), name)
                keep = [(k, v) for k, v in headers if k.lower() not in (b"content-type", b"content-length", b"content-disposition")]
                keep += [(b"content-type", XLSX_MEDIA.encode()), (b"content-length", str(len(body)).encode()),
                         (b"content-disposition", disposition(name).encode("latin-1"))]
                await send({"type": "http.response.start", "status": 200, "headers": keep})
                await send({"type": "http.response.body", "body": body, "more_body": False})

        await self.app(scope, receive, capture)


def register(app: Any) -> None:
    """Ara katmanı en dışa kurar ve istemcide üretilen CSV'ler için çeviri ucunu açar."""

    @app.post("/api/v1/export/xlsx")
    async def export_xlsx(request: Request) -> Response:
        body = await request.json()
        text = body.get("csv") if isinstance(body, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(400, detail={"code": "EXPORT", "message": "Dönüştürülecek tablo boş."})
        name = xlsx_name("", str(body.get("filename") or "liste.csv"))
        data, _ = await run_in_threadpool(to_xlsx, text, name)
        return Response(content=data, media_type=XLSX_MEDIA, headers={"Content-Disposition": disposition(name)})

    app.add_middleware(CsvToXlsx)
