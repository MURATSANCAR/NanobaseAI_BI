"""ZEKİ AI sohbetinin PDF'i: ekranda görünen turlar (soru → cevap) A4 sayfalara, sunucuda üretilir.

Projedeki tek sunucu tarafı PDF yolu `backend/nanobase_api/budget_export.py` (fpdf2 + DejaVu TTF); burada
aynı kütüphane ve aynı yazı tipi çözümü kullanılır, ikinci bir PDF altyapısı kurulmaz. Tarayıcı yazdırma
diyaloğuna bağımlılık yoktur: `GET /api/v1/editorial/ask/export.pdf?ids=…` doğrudan `application/pdf` döner.

Sayfa düzeni: A4, 18 mm yan / 22 mm üst / 20 mm alt kenar; her sayfada ince başlık şeridi (ZEKİ AI · kitap ·
tarih) ve altbilgi (Sayfa X / Y). Bir tur bir bütündür: sayfanın kalanına sığmıyorsa ama tek sayfaya sığıyorsa
yeni sayfada başlar (uzun bir tur zorunlu olarak taşar — cevap kesilmez).

Cevap metni AskBox'taki `AnswerText` ile aynı kurallarla yapılandırılır: boş satırla ayrılan bloklar; her satırı
«- » / «• » ile başlayan blok madde listesi, «1. » ile başlayan blok numaralı liste; `**kalın**` vurgular;
«s. 14» sayfa atıfları mor rozet. Karakter ağı `CharacterGraph.tsx` ile aynı deterministik halka yerleşimiyle
vektör çizilir; kitap kartlarının kapağı kart servisinden (`editorial_cards.cover`) alınır.
"""
from __future__ import annotations

import io
import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger("semantic.editorial_export")

PRODUCT = "ZEKİ AI"
NOT_FOUND = "Kitapta bulunamadı."

# ------------------------------------------------------------------ sayfa ölçüleri (mm)
PAGE_W, PAGE_H = 210.0, 297.0
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 18.0, 22.0, 20.0
CONTENT_W = PAGE_W - 2 * MARGIN_X
LINE_H = 5.6          # 10.5 pt gövde için satır yüksekliği
BUBBLE_PAD = 4.5
BUBBLE_RADIUS = 3.0

# Ekranın renkleri (canvas.css / AskBox): mor vurgu, mürekkep, soluk metin.
INK = (24, 22, 46)
MUTED = (110, 110, 135)
VIOLET = (124, 92, 255)
VIOLET_SOFT = (239, 235, 255)
CORAL = (255, 110, 120)
LINE = (226, 226, 240)
WHITE = (255, 255, 255)
AMBER_BG, AMBER_INK = (255, 247, 230), (146, 84, 8)
RED_INK = (185, 28, 28)
GRAPH_FILL = {"lead": (124, 92, 255), "family": (167, 139, 250), "other": (196, 181, 253)}

_PAGE_REF = re.compile(r"(\[?s\.\s?\d+(?:\s?[-–]\s?\d+)?\]?)")
_BOLD = re.compile(r"(\*\*[^*\n]+\*\*)")
_BULLET = re.compile(r"^\s*(?:[-*•])\s+")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+")


# ------------------------------------------------------------------ yazı tipi (budget_export ile aynı çözüm)
def _resolve_fonts() -> tuple[Optional[Path], Optional[Path]]:
    """(normal, kalın) TTF yolları; ikisi de yoksa (None, None) → Helvetica + Türkçe harf sadeleştirme.
    `PDF_FONT_REGULAR` / `PDF_FONT_BOLD` ortam değişkeni önceliklidir (imajda DejaVu yoksa başka bir TTF)."""
    env_r, env_b = os.environ.get("PDF_FONT_REGULAR", ""), os.environ.get("PDF_FONT_BOLD", "")
    if env_r and Path(env_r).is_file():
        return Path(env_r), Path(env_b) if env_b and Path(env_b).is_file() else Path(env_r)
    for regular, bold in (
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
        (Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf")),
        (Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"), Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")),
        (Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"), Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")),
        (Path("/System/Library/Fonts/Supplemental/Arial.ttf"), Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")),
    ):
        if regular.is_file():
            return regular, bold if bold.is_file() else regular
    return None, None


_TR_FOLD = str.maketrans("ıİğĞüÜşŞöÖçÇ", "iIgGuUsSoOcC")


def _fold(s: str) -> str:
    """Yalnız TTF bulunamayınca: Helvetica'nın çekirdek yazı tipi Türkçe harfleri taşımaz."""
    return s.translate(_TR_FOLD).encode("latin-1", "replace").decode("latin-1")


# ------------------------------------------------------------------ metin parçalama (AskBox.AnswerText karşılığı)
def _runs(text: str) -> list[tuple[str, str]]:
    """Satır içi parçalar: ('text'|'bold'|'page', metin). «**…**» kalın, «s. 14» sayfa rozeti (kalın içinde de)."""
    out: list[tuple[str, str]] = []
    for part in _BOLD.split(text):
        if not part:
            continue
        bold = bool(_BOLD.fullmatch(part))
        inner = part[2:-2] if bold else part
        for piece in _PAGE_REF.split(inner):
            if not piece:
                continue
            if _PAGE_REF.fullmatch(piece):
                out.append(("page", piece.replace("[", "").replace("]", "")))
            else:
                out.append(("bold" if bold else "text", piece))
    return out


def blocks(text: str) -> list[tuple[str, list[str]]]:
    """('p'|'ul'|'ol', satırlar). Ekrandaki AnswerText ile aynı bölme kuralı."""
    out: list[tuple[str, list[str]]] = []
    for block in re.split(r"\r?\n[\t ]*\r?\n", text or ""):
        block = block.strip()
        if not block:
            continue
        lines = [l.strip() for l in re.split(r"\r?\n", block) if l.strip()]
        if lines and all(_BULLET.match(l) for l in lines):
            out.append(("ul", [_BULLET.sub("", l, count=1) for l in lines]))
        elif lines and all(_NUMBERED.match(l) for l in lines):
            # Numara metinden okunur: modelin «1) … 2) …» maddeleri boş satırla ayrılınca her biri ayrı
            # blok olur; sıra numarası yeniden 1'den başlasaydı hepsi «1» görünürdü.
            out.append(("ol", [(int(re.match(r"\s*(\d+)", l).group(1)), _NUMBERED.sub("", l, count=1)) for l in lines]))
        else:
            out.append(("p", [block]))
    return out


# ------------------------------------------------------------------ grafik yerleşimi (CharacterGraph.tsx ile aynı)
GRAPH_W, GRAPH_H, GRAPH_CY, GRAPH_RING, GRAPH_MAX = 680.0, 470.0, 215.0, 150.0, 9


def graph_layout(graph: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Düğüm konumları viewBox (680×470) biriminde; merkez «lead», kalanlar halkada, r = 9 + 25·√(count/max)."""
    nodes = [n for n in (graph or {}).get("nodes") or [] if n.get("name")]
    top = sorted(nodes, key=lambda n: (-(1 if n.get("role") == "lead" else 0), -int(n.get("count") or 0)))[:GRAPH_MAX]
    if len(top) < 2:
        return None
    max_count = max(max(int(n.get("count") or 0) for n in top), 1)
    shown = {n["name"] for n in top}
    links = [e for e in (graph.get("edges") or []) if e.get("a") in shown and e.get("b") in shown and e["a"] != e["b"]]
    max_w = max([float(e.get("weight") or 0) for e in links] + [1.0])
    pos: dict[str, dict[str, Any]] = {}
    cx = GRAPH_W / 2
    for i, n in enumerate(top):
        r = 9 + 25 * math.sqrt(int(n.get("count") or 0) / max_count)
        if i == 0:
            pos[n["name"]] = {"x": cx, "y": GRAPH_CY, "r": r, "role": n.get("role") or "lead", "count": int(n.get("count") or 0)}
        else:
            a = -math.pi / 2 + ((i - 1) * 2 * math.pi) / (len(top) - 1)
            pos[n["name"]] = {"x": cx + GRAPH_RING * math.cos(a), "y": GRAPH_CY + GRAPH_RING * math.sin(a), "r": r,
                              "role": n.get("role") or "other", "count": int(n.get("count") or 0)}
    return {"order": [n["name"] for n in top], "pos": pos, "links": links, "max_w": max_w}


# ------------------------------------------------------------------ PDF
def _local_now() -> datetime:
    try:
        off = float(os.environ.get("ALERT_TZ_OFFSET_HOURS", "3"))
    except ValueError:
        off = 3.0
    return datetime.now(timezone(timedelta(hours=off)))


def _stamp(iso: Optional[str], tz: timezone) -> str:
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(tz).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return iso[:16].replace("T", " ")


def _uniq_titles(turns: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for t in turns:
        title = (t.get("bookTitle") or "").strip()
        if title and title not in seen:
            seen.append(title)
    return seen


def build(turns: list[dict[str, Any]], *, user: str = "", book_title: Optional[str] = None,
          cover: Optional[Callable[[str], tuple[bytes, str]]] = None, now: Optional[datetime] = None) -> bytes:
    """`turns`: `editorial_books.one` çıktıları (ekran sırası). `cover(book_id) -> (bytes, mime)` kart kapağı;
    None ya da hata → «Kapak mevcut değil» kutusu. PDF baytlarını döner."""
    try:
        from fpdf import FPDF
    except ImportError as e:  # pragma: no cover - imajda fpdf2 yoksa
        raise RuntimeError("PDF üretici (fpdf2) sunucuda kurulu değil.") from e

    now = now or _local_now()
    tz = now.tzinfo or timezone.utc
    titles = _uniq_titles(turns)
    heading_book = (book_title or "").strip() or (titles[0] if len(titles) == 1 else ("Okunmuş kitaplar" if turns else ""))
    header_line = " · ".join(x for x in (PRODUCT, heading_book, now.strftime("%d.%m.%Y %H:%M")) if x)

    regular, bold = _resolve_fonts()
    unicode_font = regular is not None
    fam = "ZekiSans" if unicode_font else "Helvetica"
    T = (lambda s: s) if unicode_font else _fold

    class ChatPdf(FPDF):
        def header(self) -> None:
            self.set_font(fam, "B", 8.5)
            self.set_text_color(*VIOLET)
            self.set_xy(MARGIN_X, 9)
            self.cell(CONTENT_W * 0.55, 5, T(header_line), align="L")
            self.set_font(fam, "", 8)
            self.set_text_color(*MUTED)
            self.cell(CONTENT_W * 0.45, 5, T(f"Sohbet dışa aktarımı{' · ' + user if user else ''}"), align="R")
            self.set_draw_color(*VIOLET)
            self.set_line_width(0.5)
            self.line(MARGIN_X, 15.5, PAGE_W - MARGIN_X, 15.5)
            self.set_y(MARGIN_TOP)
            self.set_text_color(*INK)

        def footer(self) -> None:
            self.set_y(-14)
            self.set_draw_color(*LINE)
            self.set_line_width(0.3)
            self.line(MARGIN_X, self.get_y(), PAGE_W - MARGIN_X, self.get_y())
            self.set_y(-11)
            self.set_font(fam, "", 8)
            self.set_text_color(*MUTED)
            self.cell(CONTENT_W / 2, 6, T("Cevaplar kitabın metninden, sayfa numarasıyla gelir."), align="L")
            self.cell(CONTENT_W / 2, 6, T(f"Sayfa {self.page_no()} / {{nb}}"), align="R")

    pdf = ChatPdf(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.set_title(f"{PRODUCT} sohbeti" + (f" — {heading_book}" if heading_book else ""))
    pdf.set_author(PRODUCT)
    pdf.set_creator(PRODUCT)
    pdf.set_lang("tr")
    pdf.set_margins(MARGIN_X, MARGIN_TOP, MARGIN_X)
    pdf.set_auto_page_break(auto=True, margin=MARGIN_BOTTOM)
    if unicode_font:
        pdf.add_font(fam, "", str(regular))
        pdf.add_font(fam, "B", str(bold or regular))
    pdf.add_page()
    _title_block(pdf, fam, T, heading_book, titles, len(turns), now, user)

    for t in turns:
        _turn(pdf, fam, T, t, tz, cover)

    out = pdf.output()
    return bytes(out)


# ------------------------------------------------------------------ parçalar
def _rounded(pdf: Any, x: float, y: float, w: float, h: float, fill: tuple[int, int, int],
             stroke: Optional[tuple[int, int, int]] = None, r: float = BUBBLE_RADIUS) -> None:
    pdf.set_fill_color(*fill)
    style = "DF" if stroke else "F"
    if stroke:
        pdf.set_draw_color(*stroke)
        pdf.set_line_width(0.3)
    try:
        pdf.rect(x, y, w, h, style=style, round_corners=True, corner_radius=r)
    except TypeError:  # eski fpdf2: köşesiz
        pdf.rect(x, y, w, h, style=style)


def _title_block(pdf: Any, fam: str, T: Callable[[str], str], heading_book: str, titles: list[str],
                 count: int, now: datetime, user: str) -> None:
    y = pdf.get_y()
    _rounded(pdf, MARGIN_X, y, CONTENT_W, 30, VIOLET_SOFT, r=4)
    # Küre: ekrandaki «Z» rozetinin baskı karşılığı.
    pdf.set_fill_color(*VIOLET)
    pdf.ellipse(MARGIN_X + 5, y + 6, 18, 18, style="F")
    pdf.set_font(fam, "B", 12)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(MARGIN_X + 5, y + 6)
    pdf.cell(18, 18, "Z", align="C")
    pdf.set_xy(MARGIN_X + 28, y + 6)
    pdf.set_font(fam, "B", 17)
    pdf.set_text_color(*INK)
    pdf.cell(CONTENT_W - 33, 8, T(f"{PRODUCT} sohbeti"), align="L")
    pdf.set_xy(MARGIN_X + 28, y + 14.5)
    pdf.set_font(fam, "", 10)
    pdf.set_text_color(*VIOLET)
    sub = f"«{heading_book}»" if heading_book and heading_book != "Okunmuş kitaplar" else "Okunmuş kitaplarla sohbet"
    if len(titles) > 1 and heading_book == "Okunmuş kitaplar":
        sub = "Kitaplar: " + ", ".join(f"«{t}»" for t in titles)
    pdf.cell(CONTENT_W - 33, 6, T(sub), align="L")
    pdf.set_xy(MARGIN_X + 28, y + 21)
    pdf.set_font(fam, "", 8.5)
    pdf.set_text_color(*MUTED)
    meta = f"{now.strftime('%d.%m.%Y %H:%M')} · {count} soru" + (f" · {user}" if user else "")
    pdf.cell(CONTENT_W - 33, 5, T(meta), align="L")
    pdf.set_y(y + 36)


def _fits_here(pdf: Any, render: Callable[[Any], None]) -> tuple[bool, Optional[float]]:
    """Kuru çizim: içerik bulunduğu yerden sayfa sonuna sığıyor mu, sığıyorsa kaç mm? Kayıt geri sarılır;
    `offset_rendering` çıkışta durumu geri aldığı için bitiş y'si blok içinde okunur. Ölçüm yoksa (eski fpdf2)
    (True, None): akış olduğu gibi devam eder."""
    measure = getattr(pdf, "offset_rendering", None)
    if measure is None:
        return True, None
    try:
        with measure() as d:
            y0, p0 = d.get_y(), d.page
            render(d)
            y1, p1 = d.get_y(), d.page
        fits = not bool(getattr(d, "page_break_triggered", False))
        return fits, (y1 - y0) if (fits and p1 == p0) else None
    except Exception as e:  # noqa: BLE001 - ölçüm başarısızsa akış bozulmaz
        log.debug("measure skipped: %s", e)
        return True, None


def _fits_fresh_page(pdf: Any, render: Callable[[Any], None]) -> bool:
    """Yeni bir sayfanın başından başlasa tek sayfaya sığar mı?"""
    measure = getattr(pdf, "offset_rendering", None)
    if measure is None:
        return False
    try:
        with measure() as d:
            d.add_page()
            p0 = d.page
            render(d)
            y1, p1 = d.get_y(), d.page
        return p1 == p0 and y1 <= float(pdf.page_break_trigger)
    except Exception as e:  # noqa: BLE001
        log.debug("fresh-page measure skipped: %s", e)
        return False


def _turn(pdf: Any, fam: str, T: Callable[[str], str], t: dict[str, Any], tz: timezone,
          cover: Optional[Callable[[str], tuple[bytes, str]]]) -> None:
    """Bir tur (soru + cevap) bütündür: sayfanın kalanına sığmıyor ama tek sayfaya sığıyorsa yeni sayfada başlar.
    Tek sayfaya da sığmayan tur olduğu yerden akar (cevap kesilmez)."""
    covers = _covers(t, cover)
    render = lambda p: _turn_body(p, fam, T, t, tz, covers)
    fits, _h = _fits_here(pdf, render)
    if not fits and pdf.get_y() > MARGIN_TOP + 1 and _fits_fresh_page(pdf, render):
        pdf.add_page()
    render(pdf)


def _covers(t: dict[str, Any], cover: Optional[Callable[[str], tuple[bytes, str]]]) -> dict[str, bytes]:
    """Kart kapakları bir kez çekilir (ölçüm ve çizim aynı baytları kullanır)."""
    out: dict[str, bytes] = {}
    if cover is None:
        return out
    for card in t.get("cards") or []:
        if not card.get("cover") or not card.get("id"):
            continue
        try:
            data, _mime = cover(str(card["id"]))
            out[str(card["id"])] = data
        except Exception as e:  # noqa: BLE001 - kapak yoksa kart yine girer
            log.info("cover skipped for %s: %s", card.get("id"), e)
    return out


def _turn_body(pdf: Any, fam: str, T: Callable[[str], str], t: dict[str, Any], tz: timezone,
               covers: dict[str, bytes]) -> None:
    # --- soru (sağda, mor dolgu, beyaz metin — ekrandaki balon)
    q = (t.get("question") or "").strip()
    pdf.set_font(fam, "", 10.5)
    qw = min(CONTENT_W * 0.78, max(pdf.get_string_width(T(q)) + 2 * BUBBLE_PAD + 2, 40))
    qx = PAGE_W - MARGIN_X - qw
    lines = pdf.multi_cell(qw - 2 * BUBBLE_PAD, LINE_H, T(q), dry_run=True, output="LINES")
    qh = len(lines) * LINE_H + 2 * BUBBLE_PAD
    if pdf.get_y() + qh > PAGE_H - MARGIN_BOTTOM:
        pdf.add_page()
    y = pdf.get_y()
    _rounded(pdf, qx, y, qw, qh, VIOLET, r=3.5)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(qx + BUBBLE_PAD, y + BUBBLE_PAD)
    pdf.multi_cell(qw - 2 * BUBBLE_PAD, LINE_H, T(q), align="L")
    pdf.set_y(y + qh + 1.2)
    meta = " · ".join(x for x in ((f"«{t['bookTitle']}»" if t.get("bookTitle") else ""), _stamp(t.get("createdAt"), tz)) if x)
    if meta:
        pdf.set_font(fam, "", 8)
        pdf.set_text_color(*MUTED)
        pdf.set_x(MARGIN_X)
        pdf.cell(CONTENT_W, 4, T(meta), align="R")
        pdf.ln(4)
    pdf.ln(2.5)

    # --- cevap (solda, beyaz kutu, ince çerçeve)
    status = t.get("status")
    answer = (t.get("answer") or "").strip()
    not_found = bool(t.get("notFound"))
    live = status in ("bekliyor", "calisiyor")
    ax, aw = MARGIN_X, CONTENT_W * 0.86
    y0 = pdf.get_y()
    # Kutu arka planı bilinmeyen yükseklikte: içerik önce kuru çizilir, sığıyorsa kutu çizilip içerik yazılır.
    # Sayfayı aşan cevap kutusuz akar (arka plan sonradan çizilirse metnin üstüne biner).
    content = lambda p: _answer_content(p, fam, T, t, answer, not_found, live, ax, aw, covers)
    fits, box_h = _fits_here(pdf, content)
    if fits and box_h is not None:
        _rounded(pdf, ax, y0, aw, box_h + BUBBLE_PAD, AMBER_BG if not_found else WHITE, LINE, r=3.5)
    pdf.set_xy(ax, y0)
    content(pdf)
    pdf.set_y(pdf.get_y() + (BUBBLE_PAD if fits and box_h is not None else 0))
    el = t.get("elapsedMs")
    if el and not live:
        pdf.set_font(fam, "", 8)
        pdf.set_text_color(*MUTED)
        pdf.set_x(ax)
        pdf.cell(aw, 4, T(f"{PRODUCT} {round(int(el) / 1000)} sn'de cevapladı"), align="L")
        pdf.ln(4)
    pdf.ln(6)


def _answer_content(pdf: Any, fam: str, T: Callable[[str], str], t: dict[str, Any], answer: str, not_found: bool,
                    live: bool, ax: float, aw: float, covers: dict[str, bytes]) -> None:
    inner_x, inner_w = ax + BUBBLE_PAD, aw - 2 * BUBBLE_PAD
    pdf.set_xy(inner_x, pdf.get_y() + BUBBLE_PAD)
    pdf.set_font(fam, "B", 8)
    pdf.set_text_color(*VIOLET)
    pdf.cell(inner_w, 4, T(PRODUCT), align="L")
    pdf.ln(5)
    if live:
        _paragraph(pdf, fam, T, "Cevap henüz hazırlanıyordu; bu dışa aktarımda yer almadı.", inner_x, inner_w, MUTED)
        return
    if not answer:
        err = (t.get("error") or f"{PRODUCT} şu an bu soruyu cevaplayamadı.").strip()
        _paragraph(pdf, fam, T, err, inner_x, inner_w, RED_INK)
        return
    graph = t.get("graph")
    if graph and not not_found:
        lay = graph_layout(graph)
        if lay:
            _graph(pdf, fam, T, lay, inner_x, inner_w)
    ink = AMBER_INK if not_found else INK
    for kind, lines in blocks(answer):
        if kind == "p":
            _paragraph(pdf, fam, T, lines[0], inner_x, inner_w, ink)
        else:
            for item in lines:
                num, line = (None, item) if kind == "ul" else item
                _list_item(pdf, fam, T, line, inner_x, inner_w, ink, num)
            pdf.ln(1.5)
    for card in t.get("cards") or []:
        _card(pdf, fam, T, card, inner_x, inner_w, covers.get(str(card.get("id") or "")))
    if t.get("cardError"):
        _paragraph(pdf, fam, T, str(t["cardError"]), inner_x, inner_w, AMBER_INK)


def _flow(pdf: Any, fam: str, T: Callable[[str], str], text: str, left: float, width: float, ink: tuple[int, int, int],
          size: float = 10.5) -> None:
    """Satır içi akış: normal / kalın / sayfa rozeti parçaları `write` ile sarılır; taşan satır `left`ten devam eder."""
    right_margin = PAGE_W - (left + width)
    prev_l, prev_r = pdf.l_margin, pdf.r_margin
    pdf.set_left_margin(left)
    pdf.set_right_margin(right_margin)
    pdf.set_x(left)
    for kind, piece in _runs(text):
        if kind == "page":
            _page_badge(pdf, fam, T, piece, left, width, size)
            continue
        pdf.set_font(fam, "B" if kind == "bold" else "", size)
        pdf.set_text_color(*ink)
        pdf.write(LINE_H, T(piece))
    pdf.ln(LINE_H)
    pdf.set_left_margin(prev_l)
    pdf.set_right_margin(prev_r)


def _page_badge(pdf: Any, fam: str, T: Callable[[str], str], label: str, left: float, width: float, size: float) -> None:
    """«s. 14» rozeti: mor, kalın, açık mor zeminli; satır sonuna sığmıyorsa alt satıra iner."""
    pdf.set_font(fam, "B", size - 1.5)
    w = pdf.get_string_width(T(label)) + 2.0
    # `write` kullanılabilir genişlikten 2·c_margin düşer; aynı payla ölçülmezse rozet iki satıra bölünür.
    if pdf.get_x() + w + 2 * float(getattr(pdf, "c_margin", 1.0)) > left + width:
        pdf.ln(LINE_H)
        pdf.set_x(left)
    # Rozet bölünmez: satır sayfanın altına sığmıyorsa `write` kırmadan önce yeni sayfaya geçilir
    # (yoksa kırılan yazı eski y'ye döner ve boş bir sayfa kalır).
    if pdf.get_y() + LINE_H > float(pdf.page_break_trigger):
        pdf.add_page()
        pdf.set_x(left)
    x, y = pdf.get_x(), pdf.get_y()
    _rounded(pdf, x, y + 0.9, w, LINE_H - 1.6, VIOLET_SOFT, r=1.2)
    pdf.set_text_color(*VIOLET)
    pdf.set_xy(x + 1.0, y)
    pdf.write(LINE_H, T(label))
    if pdf.get_y() == y:
        pdf.set_xy(x + w + 0.3, y)
    # (yine de sarıldıysa imleç `write`in bıraktığı yerde kalır; eski y'ye dönmek boş sayfa bırakır)


def _paragraph(pdf: Any, fam: str, T: Callable[[str], str], text: str, left: float, width: float,
               ink: tuple[int, int, int]) -> None:
    _flow(pdf, fam, T, text, left, width, ink)
    pdf.ln(2.2)


def _list_item(pdf: Any, fam: str, T: Callable[[str], str], text: str, left: float, width: float,
               ink: tuple[int, int, int], number: Optional[int]) -> None:
    indent = 7.0
    if pdf.get_y() + LINE_H > PAGE_H - MARGIN_BOTTOM:
        pdf.add_page()
    y = pdf.get_y()
    if number is None:
        pdf.set_fill_color(*VIOLET)
        pdf.ellipse(left + 1.6, y + LINE_H / 2 - 0.8, 1.6, 1.6, style="F")
    else:
        pdf.set_fill_color(*VIOLET_SOFT)
        pdf.ellipse(left, y + 0.6, 4.4, 4.4, style="F")
        pdf.set_font(fam, "B", 7.5)
        pdf.set_text_color(*VIOLET)
        pdf.set_xy(left, y + 0.6)
        pdf.cell(4.4, 4.4, str(number), align="C")
    pdf.set_xy(left + indent, y)
    _flow(pdf, fam, T, text, left + indent, width - indent, ink)
    pdf.ln(0.6)


def _graph(pdf: Any, fam: str, T: Callable[[str], str], lay: dict[str, Any], left: float, width: float) -> None:
    """Karakter ağı: viewBox 680×470 → kutunun genişliğine (en çok 150 mm) ölçeklenir; etiket boyları ve
    aralıkları da aynı ölçekle (SVG'de 12.5 px ad, 11 px olay sayısı) — düğümle etiket üst üste binmez."""
    gw = min(width, 150.0)
    s = gw / GRAPH_W
    pt = s * 72 / 25.4  # 1 viewBox birimi (px) → punto
    name_pt, count_pt = max(6.5, 12.5 * pt), max(5.8, 11 * pt)
    gh = GRAPH_H * s + 8  # altta açıklama satırı
    if pdf.get_y() + gh > PAGE_H - MARGIN_BOTTOM:
        pdf.add_page()
    x0, y0 = left + (width - gw) / 2, pdf.get_y()
    _rounded(pdf, x0 - 2, y0, gw + 4, gh, (250, 249, 255), (232, 228, 250), r=3)
    pos, links = lay["pos"], lay["links"]
    max_w = lay["max_w"]
    pdf.set_draw_color(*VIOLET)
    for e in links:
        p, q = pos[e["a"]], pos[e["b"]]
        k = float(e.get("weight") or 0) / max_w
        pdf.set_line_width((1 + k * 4) * s * 0.9)
        try:
            with pdf.local_context(stroke_opacity=0.18 + 0.32 * k):
                pdf.line(x0 + p["x"] * s, y0 + p["y"] * s, x0 + q["x"] * s, y0 + q["y"] * s)
        except Exception:  # noqa: BLE001 - eski fpdf2: saydamlıksız
            pdf.line(x0 + p["x"] * s, y0 + p["y"] * s, x0 + q["x"] * s, y0 + q["y"] * s)
    for name in lay["order"]:
        p = pos[name]
        cx, cy, r = x0 + p["x"] * s, y0 + p["y"] * s, p["r"] * s
        pdf.set_fill_color(*GRAPH_FILL.get(p["role"], GRAPH_FILL["other"]))
        pdf.ellipse(cx - r, cy - r, 2 * r, 2 * r, style="F")
        # Etiket düğümün dışına bakar: alt yarıdakiler altta, üst yarıdakiler üstte (SVG: y ± r ± 7/15, 21/29).
        below = p["y"] > GRAPH_CY + 20
        ty = cy + r + 15 * s if below else cy - r - 7 * s
        ty2 = cy + r + 29 * s if below else cy - r - 21 * s
        pdf.set_font(fam, "B", name_pt)
        pdf.set_text_color(*INK)
        pdf.text(cx - pdf.get_string_width(T(name)) / 2, ty, T(name))
        pdf.set_font(fam, "", count_pt)
        pdf.set_text_color(*MUTED)
        lbl = f"{p['count']} olay"
        pdf.text(cx - pdf.get_string_width(T(lbl)) / 2, ty2, T(lbl))
    # açıklama
    ly = y0 + GRAPH_H * s + 3.2
    pdf.set_font(fam, "", 7.5)
    pdf.set_text_color(*MUTED)
    lx = x0 + 2
    for role, label in (("lead", "başkarakter"), ("family", "yakın")):
        pdf.set_fill_color(*GRAPH_FILL[role])
        pdf.ellipse(lx, ly - 0.2, 2.4, 2.4, style="F")
        pdf.text(lx + 3.4, ly + 1.9, T(label))
        lx += 3.4 + pdf.get_string_width(T(label)) + 5
    pdf.text(lx, ly + 1.9, T("çizgi kalınlığı = ortak olay"))
    pdf.set_y(y0 + gh + 3)


def _card(pdf: Any, fam: str, T: Callable[[str], str], card: dict[str, Any], left: float, width: float,
          cover_bytes: Optional[bytes]) -> None:
    """Kitap kartı: kapak (2:3) solda, başlık + yazar + özet cümleleri sağda. Ekrandaki BookCard'ın karşılığı."""
    publisher = card.get("publisher") or {}
    title = (publisher.get("title") or card.get("title") or "").strip()
    authors = card.get("authors") or []
    cover_w, cover_h, pad = 26.0, 39.0, 3.5
    text_x = left + pad + cover_w + pad
    text_w = width - (text_x - left) - pad
    summary = card.get("summary") or []
    # Yükseklik: özet satırlarına göre; kapak yüksekliğinden az olmaz.
    pdf.set_font(fam, "", 9.5)
    est = 12.0  # başlık + yazar
    for sent in summary:
        line = str(sent.get("text") or "") + ((" (s. " + ", ".join(str(p) for p in sent.get("pages") or []) + ")") if sent.get("pages") else "")
        est += len(pdf.multi_cell(text_w, 4.8, T(line), dry_run=True, output="LINES")) * 4.8 + 1
    if not summary:
        est += 2 * 4.8
    h = max(cover_h + 2 * pad, est + 2 * pad)
    if pdf.get_y() + h > PAGE_H - MARGIN_BOTTOM:
        pdf.add_page()
    y0 = pdf.get_y()
    _rounded(pdf, left, y0, width, h, WHITE, LINE, r=3)
    # kapak
    cx, cy = left + pad, y0 + pad
    drawn = False
    if cover_bytes:
        try:
            pdf.image(io.BytesIO(cover_bytes), x=cx, y=cy, w=cover_w, h=cover_h, keep_aspect_ratio=True)
            drawn = True
        except Exception as e:  # noqa: BLE001 - biçim okunamadıysa yer tutucu
            log.info("cover image skipped: %s", e)
    if not drawn:
        _rounded(pdf, cx, cy, cover_w, cover_h, (241, 241, 247), r=2)
        pdf.set_font(fam, "", 7)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(cx, cy + cover_h / 2 - 4)
        pdf.multi_cell(cover_w, 3.6, T("Kapak\nmevcut değil"), align="C")
    # metin
    pdf.set_xy(text_x, y0 + pad)
    pdf.set_font(fam, "B", 11)
    pdf.set_text_color(*INK)
    pdf.multi_cell(text_w, 5.2, T(title), align="L")
    pdf.set_x(text_x)
    pdf.set_font(fam, "", 8.5)
    pdf.set_text_color(*MUTED)
    by = ", ".join(authors) if authors else "Yazar bilgisi henüz doğrulanmadı."
    if card.get("authorsSource") == "CRM":
        by += " (yayınevi kaydı)"
    pdf.multi_cell(text_w, 4.2, T(by), align="L")
    pdf.ln(1.2)
    pdf.set_font(fam, "", 9.5)
    pdf.set_text_color(*INK)
    if summary:
        for sent in summary:
            pages = sent.get("pages") or []
            pdf.set_x(text_x)
            pdf.multi_cell(text_w, 4.8, T(str(sent.get("text") or "") + ((" (s. " + ", ".join(str(p) for p in pages) + ")") if pages else "")), align="L")
            pdf.ln(0.8)
    elif publisher.get("summary"):
        pdf.set_x(text_x)
        pdf.set_font(fam, "B", 8)
        pdf.set_text_color(*MUTED)
        pdf.cell(text_w, 4, T("Yayınevinin tanıtımı (CRM)"))
        pdf.ln(4.4)
        pdf.set_font(fam, "", 9.5)
        pdf.set_text_color(*INK)
        pdf.set_x(text_x)
        pdf.multi_cell(text_w, 4.8, T(str(publisher["summary"])), align="L")
    else:
        pdf.set_x(text_x)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(text_w, 4.8, T("Güncel kitap özeti henüz hazır değil."), align="L")
    pdf.set_y(y0 + h + 3)


def file_name(now: Optional[datetime] = None) -> str:
    return f"zeki-ai-sohbet-{(now or _local_now()).strftime('%Y-%m-%d')}.pdf"
