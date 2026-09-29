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
import json
import logging
import re
from datetime import date, datetime
from typing import Any, Callable, Optional
from urllib.parse import parse_qsl, quote, unquote

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

log = logging.getLogger("semantic.csv_excel")

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
            # «12.500» / «4.333»: dosya Türkçe yazıyorsa binlik (12500), nokta ondalık yazıyorsa ondalık (4,333); ipucu yoksa metin.
            p["style"] = file_style
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


# Excel'in kabul etmediği kontrol karakterleri (sekme, satır sonu, satır başı hariç 0x00–0x1F).
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
MAX_ROWS = 1_048_576          # Excel'in bir sayfadaki satır sınırı (başlık dahil)
MAX_CELL = 32_767             # Excel'in bir hücredeki karakter sınırı
_EPOCH = datetime(1899, 12, 30)
_BUILTIN_FMT = {"#,##0": 3, "#,##0.00": 4, "0%": 9, "0.00%": 10}
_NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
_NS_R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


class TooManyRows(ValueError):
    pass


def _esc(v: str) -> str:
    return v.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _col(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _text(v: str) -> str:
    v = _ILLEGAL.sub("", v) if _ILLEGAL.search(v) else v
    if len(v) > MAX_CELL:
        v = v[: MAX_CELL - 1] + "…"
    return v


def _num(v: float | int) -> str:
    return str(v) if isinstance(v, int) else repr(v)


def to_xlsx(data: bytes | str, title: str = "Liste") -> tuple[bytes, int]:
    """CSV → .xlsx baytları ve veri satırı sayısı (başlık hariç).

    Dosya Office Open XML biçiminde doğrudan akışla yazılır (satır içi metin, sabit biçim tablosu): 250 bin satırlık
    liste openpyxl ile ~50 sn sürüyordu (sunucuda hızlı XML altyapısı yok), bu yolla birkaç saniye. Değerler ve sayı
    biçimleri aynı karar kurallarından gelir (`cell_value`). Excel sınırları: kabul etmediği kontrol karakterleri atılır;
    32.767 karakteri aşan hücre «…» ile biter; 1.048.576 satırı aşan liste `TooManyRows` (sessiz kesme yok)."""
    import zipfile

    rows = parse(decode(data))
    header, body = (rows[0], rows[1:]) if rows else ([], [])
    if len(body) + (1 if header else 0) > MAX_ROWS:
        raise TooManyRows(f"{len(body):,} satır Excel'in sayfa sınırını (1.048.576) aşıyor; CSV'yi kullanın.".replace(",", "."))
    plans = plan_columns(header, body)
    ncol = max([len(plans)] + [len(r) for r in body]) if (header or body) else 0
    widths = [len(header[i]) if i < len(header) else 0 for i in range(ncol)]
    for row in body:
        for i, raw in enumerate(row):
            if len(raw) > widths[i]:
                widths[i] = min(len(raw), 80)
    nrows = len(body) + (1 if header else 0)
    last = f"{_col(max(ncol, 1))}{max(nrows, 1)}"
    cols = [_col(i) for i in range(1, ncol + 1)]
    fmt_ids: dict[str, int] = {}     # biçim → hücre stili sırası (0 düz, 1 başlık, 2.. biçimli)

    def style_of(fmt: str) -> int:
        if fmt not in fmt_ids:
            fmt_ids[fmt] = len(fmt_ids) + 2
        return fmt_ids[fmt]

    text_plan = {"text": True, "style": None}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as zf:
        with zf.open("xl/worksheets/sheet1.xml", "w") as fh:
            out: list[str] = []

            def flush() -> None:
                fh.write("".join(out).encode("utf-8"))
                out.clear()

            out.append(f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet {_NS} {_NS_R}>'
                       f'<dimension ref="A1:{last}"/><sheetViews><sheetView workbookViewId="0">')
            if header:
                out.append('<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                           '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>')
            out.append('</sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/>')
            if ncol:
                out.append("<cols>" + "".join(f'<col min="{i}" max="{i}" width="{max(8, min(60, w + 2))}" customWidth="1"/>'
                                              for i, w in enumerate(widths, start=1)) + "</cols>")
            out.append("<sheetData>")
            r = 0
            if header:
                r = 1
                out.append('<row r="1">' + "".join(
                    f'<c r="{cols[i]}1" t="inlineStr" s="1"><is><t xml:space="preserve">{_esc(_text(h))}</t></is></c>'
                    for i, h in enumerate(header)) + "</row>")
            for row in body:
                r += 1
                cells = []
                for i, raw in enumerate(row):
                    val, fmt = cell_value(raw, plans[i] if i < len(plans) else text_plan)
                    if val is None:
                        continue
                    ref = f"{cols[i]}{r}"
                    if isinstance(val, str):
                        cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{_esc(_text(val))}</t></is></c>')
                    elif isinstance(val, datetime):
                        cells.append(f'<c r="{ref}" s="{style_of(fmt or "dd.mm.yyyy hh:mm")}"><v>{_num((val - _EPOCH).total_seconds() / 86400)}</v></c>')
                    elif isinstance(val, date):
                        cells.append(f'<c r="{ref}" s="{style_of(fmt or "dd.mm.yyyy")}"><v>{(val - _EPOCH.date()).days}</v></c>')
                    else:
                        cells.append(f'<c r="{ref}"' + (f' s="{style_of(fmt)}"' if fmt else "") + f"><v>{_num(val)}</v></c>")
                out.append(f'<row r="{r}">' + "".join(cells) + "</row>")
                if len(out) >= 2000:
                    flush()
            out.append("</sheetData>")
            if header and ncol:
                out.append(f'<autoFilter ref="A1:{last}"/>')
            out.append('<pageMargins left="0.75" right="0.75" top="1" bottom="1" header="0.5" footer="0.5"/></worksheet>')
            flush()
        name = sheet_title(title)
        qname = "'" + name.replace("'", "''") + "'"
        defined = (f'<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'
                   f'{_esc(qname)}!$A$1:${_col(max(ncol, 1))}${max(nrows, 1)}</definedName></definedNames>') if header and ncol else ""
        zf.writestr("xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook {_NS} {_NS_R}>'
                    f'<bookViews><workbookView/></bookViews><sheets><sheet name="{_esc(name)}" sheetId="1" r:id="rId1"/></sheets>'
                    f"{defined}</workbook>")
        custom = [f for f in fmt_ids if f not in _BUILTIN_FMT]
        num_id = {f: _BUILTIN_FMT.get(f) or 164 + custom.index(f) for f in fmt_ids}
        numfmts = (f'<numFmts count="{len(custom)}">' + "".join(
            f'<numFmt numFmtId="{num_id[f]}" formatCode="{_esc(f)}"/>' for f in custom) + "</numFmts>") if custom else ""
        xfs = ['<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>',
               '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1">'
               '<alignment vertical="top" wrapText="1"/></xf>']
        xfs += [f'<xf numFmtId="{num_id[f]}" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>' for f in fmt_ids]
        font = '<sz val="11"/><name val="Calibri"/><family val="2"/>'
        zf.writestr("xl/styles.xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<styleSheet {_NS}>{numfmts}'
                    f'<fonts count="2"><font>{font}</font><font><b/>{font}</font></fonts>'
                    '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                    f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs>'
                    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        zf.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                    "</Relationships>")
        zf.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                    "</Relationships>")
        zf.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                    '<Default Extension="xml" ContentType="application/xml"/>'
                    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                    "</Types>")
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
                try:
                    body, _ = await run_in_threadpool(to_xlsx, b"".join(chunks), name)
                except Exception as e:  # noqa: BLE001 — dosya inmez, kişi nedenini görür (düz 500 değil)
                    too_many = isinstance(e, TooManyRows)
                    log.warning("excel: %s Excel'e çevrilemedi: %s", path, e)
                    msg = str(e) if too_many else "Liste Excel'e çevrilemedi; CSV'yi kullanın."
                    err = json.dumps({"detail": {"code": "EXPORT", "message": msg}}, ensure_ascii=False).encode()
                    await send({"type": "http.response.start", "status": 422 if too_many else 500,
                                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(err)).encode())]})
                    await send({"type": "http.response.body", "body": err, "more_body": False})
                    return
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
        try:
            data, _ = await run_in_threadpool(to_xlsx, text, name)
        except TooManyRows as e:
            raise HTTPException(422, detail={"code": "EXPORT", "message": str(e)}) from None
        return Response(content=data, media_type=XLSX_MEDIA, headers={"Content-Disposition": disposition(name)})

    app.add_middleware(CsvToXlsx)
