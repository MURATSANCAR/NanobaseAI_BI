"""Redaksiyon: yüklenen metni kitabın kendi bölüm yapısına göre ayırmak (ZEKI-44).

Eski yol (editorial_desk.split_chapters) PDF'in her görsel satırını paragraf sayıp kısa, numaralı satırı başlık
sayıyordu: sayfa numarası («12») ve numaralı liste maddesi başlık oluyor, metin sayfa sayfa «bölüm»e bölünüyordu;
numarasız bölüm adları («Çocukluk», «Önsöz») hiç görülmüyordu. Burada kitabın kendi yapısı sırayla aranır; ilk
tutan (en az iki bölüm çıkaran) kullanılır:

  PDF : 1) içindekiler işaretleri (PDF'in yer imleri) 2) başlık tipografisi (gövde puntosundan belirgin büyük satırlar)
        3) içindekiler sayfası («Başlık …… 12» satırları; başlıklar metinde sırayla aranır) 4) «BÖLÜM 3» / «Üçüncü Bölüm»
  DOCX: 1) Word başlık düzeyi (styles.xml outlineLvl, «Heading n» / «Başlık n») 2) kalıp
  TXT/MD: 1) Markdown «#» başlıkları 2) eski kural (kısa numaralı satır, «BÖLÜM 3»)

Hiçbiri tutmazsa metin, sayfa aralığıyla anılan **parça**lara ayrılır ve ekranda «bölüm» denmez (`unit="parca"`).
PDF'te sayfa üst/alt bilgisi (sayfa kenarında tekrarlanan satır) ve tek başına sayfa numarası gövdeden atılır; görsel
satır sonları paragraf içinde birleştirilir, cümle ölçüleri satır sonunda kesilmez. Kitaba özel kural yoktur.

PDF okuma kusurları (2026-09-30, iki InDesign çıktısında ölçüldü): fontun yanlış harf eşlemesi `editorial_pdf_text`
ile onarılır; sayfa kutusunun dışındaki metin (çift sayfa düzeninde komşu sayfaya taşan yazı, sayfa dışında unutulmuş
künye kopyası) okunmaz; kenara asılan satır sonu tiresine okuyucunun eklediği boşluk atılır («birlik -» → «birlik-»);
büyük ilk harf (drop cap) kelimesine yapışır («Y» + «aşlı» → «Yaşlı»); cümlenin ortasındaki büyük puntolu süs yazısı
(«İşte zavallı tavuk, KOCA GUYUK'UN KORKUNÇ ADINI ilk defa o gün duydu.») bölüm başlığı sayılmaz.
"""
from __future__ import annotations

import io
import logging
import math
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from xml.etree import ElementTree

from semantic_bridge import editorial_pdf_text as pdf_text

log = logging.getLogger("semantic.editorial_desk_structure")

#: Yapı bulunamayınca bir parçanın hedef büyüklüğü (kelime). Sınır değil: parça paragraf sınırında kesilir.
PIECE_WORDS = 3000
#: Bölümlerden önceki sayfaların (kapak, künye, içindekiler) adı.
LEAD = "Bölümlerden önce"

@dataclass
class Structure:
    chapters: list[tuple[str, str]]
    source: str
    #: Fontun verisinden onarılamayan, metne özel alan (PUA) karakteri olarak giren harf sayısı.
    unreadable_chars: int = 0

    @property
    def unit(self) -> str:
        return "parca" if self.source == "pieces" else "bolum"

    def report(self) -> dict[str, Any]:
        out: dict[str, Any] = {"structure": self.source, "unit": self.unit}
        if self.unreadable_chars:
            out["unreadable_chars"] = self.unreadable_chars
        return out


@dataclass
class Line:
    page: int                 # 0 tabanlı PDF sayfası
    text: str
    size: float = 0.0         # karakter ağırlıklı punto (0 = bilinmiyor)
    bold: bool = False
    y: Optional[float] = None
    kind: str = "body"        # body | head | cont
    extra: dict[str, Any] = field(default_factory=dict)
    x: Optional[float] = None


# ---------------------------------------------------------------------------------------------- ortak

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def norm(s: str) -> str:
    """Karşılaştırma için: Türkçe küçük harf, harf/rakam dışı atılır, boşluk tekilleşir."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", tr_lower(s))).strip()


def _words(s: str) -> int:
    return len(_WORD.findall(s))


# Sıra sözcüğüyle ya da numarayla «bölüm/kısım» başlığı; tek başına sayı ya da «1. madde» satırı başlık sayılmaz.
_ORD = (r"birinci|ikinci|üçüncü|dördüncü|beşinci|altıncı|yedinci|sekizinci|dokuzuncu|onuncu|yirminci|otuzuncu|"
        r"kırkıncı|ellinci|on|yirmi|otuz|kırk|elli")
_CHAPTER_WORD = re.compile(
    r"^(?:(?:\d{1,3}|[ivxlc]{1,7})\s*[.\-–:]?\s*)?(?:bölüm|kısım|chapter|part)\b.{0,80}$"
    rf"|^(?:(?:{_ORD})\s+)+(?:bölüm|kısım)\b.{{0,80}}$")


def chapter_word(text: str) -> bool:
    t = tr_lower(text.strip())
    return len(t) <= 90 and bool(_CHAPTER_WORD.match(t))


def assemble(units: list[tuple[Any, ...]], join_body: Callable[[list[str]], str], lead: str = LEAD) -> list[tuple[str, str]]:
    """(metin, tür[, sayfa]) → (ad, gövde). tür: head = bölüm başlar; cont = başlığın devamı (başlıktan hemen sonra
    gelirse); body = gövde. Art arda gelen başlıklar tek ad olur («BÖLÜM 3 — Çocukluk»); sayfa biliniyorsa yalnız
    en çok iki sayfa arayla (kapaktaki kitap adı ilk bölümün adına eklenmez). Gövdesiz bölüm atılır."""
    chapters: list[tuple[str, list[str]]] = []
    last_page: Optional[int] = None
    for unit in units:
        text, kind = unit[0], unit[1]
        page = unit[2] if len(unit) > 2 else None
        near = page is None or last_page is None or page - last_page <= 2
        if kind in ("head", "cont") and chapters and not chapters[-1][1] and near:
            chapters[-1] = (f"{chapters[-1][0]} — {text}"[:300], [])
            last_page = page if page is not None else last_page
            continue
        if kind == "head":
            chapters.append((text[:300], []))
            last_page = page
        else:
            if not chapters:
                chapters.append((lead, []))
            chapters[-1][1].append(text)
    return [(t, join_body(body)) for t, body in chapters if body and join_body(body).strip()]


def pieces(paras: list[tuple[str, Optional[int]]], pdf: bool) -> list[tuple[str, str]]:
    """Yapı yoksa: paragraf sınırında ~PIECE_WORDS kelimelik parçalar; PDF'te adı sayfa aralığını söyler."""
    out: list[tuple[str, str]] = []
    buf: list[str] = []
    pages: list[int] = []
    count = 0

    def flush() -> None:
        nonlocal buf, pages, count
        if not buf:
            return
        no = len(out) + 1
        if pdf and pages:
            a, b = min(pages) + 1, max(pages) + 1
            title = f"Parça {no} · s. {a}" + (f"–{b}" if b != a else "")
        else:
            title = f"Parça {no}"
        out.append((title, "\n".join(buf)))
        buf, pages, count = [], [], 0

    for text, page in paras:
        buf.append(text)
        if page is not None:
            pages.append(page)
        count += _words(text)
        if count >= PIECE_WORDS:
            flush()
    flush()
    if len(out) == 1:
        out[0] = ("Metnin tamamı", out[0][1])
    return out


# ---------------------------------------------------------------------------------------------- PDF: satırlar

_BOLD = re.compile(r"(?i)bold|black|heavy|semibold|demi")
_ROMAN = r"(?=[ivxlcdm])m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})"
_PAGE_NO = re.compile(rf"^[\W_]*(?:\d{{1,4}}|{_ROMAN})[\W_]*$", re.IGNORECASE)


def _mult(m: list[float], n: list[float]) -> list[float]:
    return [m[0] * n[0] + m[1] * n[2], m[0] * n[1] + m[1] * n[3],
            m[2] * n[0] + m[3] * n[2], m[2] * n[1] + m[3] * n[3],
            m[4] * n[0] + m[5] * n[2] + n[4], m[4] * n[1] + m[5] * n[3] + n[5]]


_IDENTITY = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
#: Fontunda ı olmayan başlıkta dizgici ı yerine küçültülmüş «l» basar («Bal» 28 pt + «l» 20 pt + «ğ» 28 pt = Balığ…):
#: kelimenin içinde, önceki harflerin bu oranından küçük tek «l», font ı taşımıyorsa ı'dır.
_SMALL_L = 0.85
#: Latin, Yunan, Kiril ve genel noktalama dışı yazı: harf tablosu olmayan fontun ürettiği anlamsız karakter işareti.
_NON_LATIN = re.compile(r"[\u0590-\u1fff\u2c00-\u2dff\u3000-\ud7ff\uf900-\ufaff]")
#: Sayfa kutusunun kenarından bu kadar (pt) dışarıda başlayan metin sayfada görünmez.
_BOX_SLACK = 2.0
#: Kenara asılan satır sonu tiresi ayrı metin nesnesidir; okuyucu önüne kendi boşluğunu ekler (« -»). Önceki parça
#: harfle/rakamla bitiyorsa boşluk PDF'te yoktur (yazarın boşluğu önceki parçanın sonunda olurdu).
_HANGING_HYPHEN = re.compile(r" [-\u00ad\u2010]")


def _page_box(page: Any) -> Optional[tuple[float, float, float, float]]:
    try:
        b = page.cropbox
        x0, y0, x1, y1 = (float(v) for v in (b[0], b[1], b[2], b[3]))
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
    except Exception:  # noqa: BLE001 — kutu okunamazsa konum süzgeci uygulanmaz
        return None


def reading_order(lines: list[Line], width: float) -> list[Line]:
    """Bir sayfanın satırları yukarıdan aşağıya. PDF metni çizim sırasıyla verir; InDesign bölüm başlığını ya da büyük
    ilk harfi sayfanın metninden sonra çizebilir (başlık bir önceki bölüme, ilk satırlar başlığın önüne düşüyordu).
    Konumu bilinmeyen satır varsa ya da sayfa çok sütunluysa (aynı yükseklikte, sayfa genişliğinin dörtte birinden
    uzak iki uzun satır) çizim sırası korunur. Aynı yükseklikteki satırlar çizim sırasında kalır."""
    if len(lines) < 2 or any(ln.y is None for ln in lines):
        return lines
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            if (len(a.text) > 20 and len(b.text) > 20 and a.x is not None and b.x is not None
                    and abs(a.y - b.y) < 0.5 * max(a.size, b.size, 1.0) and abs(a.x - b.x) > 0.25 * width):
                return lines
    return sorted(lines, key=lambda ln: -ln.y)


def pdf_lines(reader: Any) -> list[Line]:
    """Sayfa sayfa satırlar ve her satırın puntosu, kalınlığı, dikey konumu (metin çıkarıcının ziyaretçisiyle).
    Başlangıcı sayfa kutusunun dışında kalan metin ve aynı konuma ikinci kez basılan aynı metin (dolgu + kontur)
    atlanır; konumu olmayan parça (okuyucunun kendi eklediği boşluk ve satır sonu) süzülmez."""
    out: list[Line] = []
    for pno, page in enumerate(reader.pages):
        cur: dict[str, Any] = {"parts": [], "sizes": Counter(), "bold": 0, "chars": 0, "y": None, "x": None}
        box = _page_box(page)
        printed: set[tuple[str, float, float]] = set()
        unmapped: dict[int, bool] = {}
        no_i: dict[int, bool] = {}
        first = len(out)

        def flush(pno: int = pno, cur: dict[str, Any] = cur) -> None:
            text = re.sub(r"\s+", " ", "".join(cur["parts"])).strip()
            if text:
                size = cur["sizes"].most_common(1)[0][0] if cur["sizes"] else 0.0
                out.append(Line(pno, text, size, cur["bold"] * 2 > cur["chars"], cur["y"], x=cur["x"]))
            cur.update(parts=[], sizes=Counter(), bold=0, chars=0, y=None, x=None, last_size=None)

        def visit(text: Any, cm: Any, tm: Any, font: Any, font_size: Any, cur: dict[str, Any] = cur,
                  flush: Callable[[], None] = flush) -> None:
            if not text:
                return
            text = str(text)
            try:
                m = _mult([float(v) for v in tm], [float(v) for v in cm])
                size = round(abs(float(font_size or 0)) * math.hypot(m[2], m[3]) * 2) / 2
                y: Optional[float] = m[5]
                placed = any(abs(a - b) > 1e-9 for a, b in zip(m, _IDENTITY))
            except Exception:  # noqa: BLE001 — konum okunamazsa punto bilinmiyor sayılır
                size, y, placed = 0.0, None, False
            if placed and box is not None and text.strip() and not (
                    box[0] - _BOX_SLACK <= m[4] <= box[2] + _BOX_SLACK and box[1] - _BOX_SLACK <= m[5] <= box[3] + _BOX_SLACK):
                text = "\n" * text.count("\n")       # sayfada görünmeyen metin; satır sonları korunur
                if not text:
                    return
            if placed and text.strip():
                key = (text.strip(), round(m[4], 1), round(m[5], 1))
                if key in printed:
                    text = "\n" * text.count("\n")
                    if not text:
                        return
                printed.add(key)
            if _HANGING_HYPHEN.fullmatch(text) and re.search(r"[^\W_]$", "".join(cur["parts"])):
                text = text[1:]
            if font is not None:
                if id(font) not in unmapped:
                    unmapped[id(font)] = pdf_text.no_text_mapping(font)
                if unmapped[id(font)] and _NON_LATIN.search(text):
                    # harf tablosu olmayan CID font: okuyucu glif numarasını harf sanmış, okunamadı yazılır
                    text = re.sub(r"[^\s]", "\ufffd", text)
            if (text in ("l", " l") and size and cur.get("last_size") and size <= _SMALL_L * cur["last_size"]
                    and re.search(r"[^\W\d_]$", "".join(cur["parts"])) and font is not None):
                if id(font) not in no_i:
                    no_i[id(font)] = pdf_text.lacks_letter(font, "ı")
                if no_i[id(font)]:
                    text = "ı"                # ı'sı olmayan fontta dizgicinin küçültülmüş «l»si (okuyucu boşluğu atılır)
            elif text.strip() and size:
                cur["last_size"] = size
            try:
                bold = bool(font is not None and _BOLD.search(str(font.get("/BaseFont") or "")))
            except Exception:  # noqa: BLE001
                bold = False
            for i, part in enumerate(text.split("\n")):
                if i:
                    flush()
                cur["parts"].append(part)
                n = len(part.strip())
                if n:
                    if size:
                        cur["sizes"][size] += n
                    cur["chars"] += n
                    if bold:
                        cur["bold"] += n
                    if cur["y"] is None:
                        cur["y"] = y
                        cur["x"] = m[4] if y is not None else None

        try:
            page.extract_text(visitor_text=visit)
        except Exception as e:  # noqa: BLE001 — okunamayan sayfa atlanır, kitabın geri kalanı ayrılır
            log.warning("pdf sayfa %s okunamadı: %s", pno + 1, e)
        flush()
        rotated = False
        try:
            rotated = int(page.get("/Rotate", 0) or 0) % 360 != 0
        except Exception:  # noqa: BLE001
            pass
        if not rotated and box is not None:
            out[first:] = reading_order(out[first:], box[2] - box[0])
    return out


def body_size(lines: list[Line]) -> float:
    c: Counter = Counter()
    for ln in lines:
        if ln.size:
            c[ln.size] += len(ln.text)
    return c.most_common(1)[0][0] if c else 0.0


def head_threshold(body: float) -> float:
    return max(body * 1.15, body + 1.0) if body else float("inf")


def drop_furniture(lines: list[Line], thr: float) -> list[Line]:
    """Sayfa kenarındaki (ilk/son iki satır) tekrar eden üst/alt bilgi ve tek başına sayfa numarası atılır.
    Başlık puntosundaki satıra dokunulmaz (bölüm başlığı sayfanın ilk satırıdır)."""
    by_page: dict[int, list[int]] = {}
    for i, ln in enumerate(lines):
        by_page.setdefault(ln.page, []).append(i)
    edges: set[int] = set()
    for idx in by_page.values():
        edges.update(idx[:2] + idx[-2:])
    key = lambda t: re.sub(r"\d+", "#", norm(t))  # noqa: E731
    seen: Counter = Counter()
    for i in edges:
        if len(lines[i].text) <= 90:
            seen[key(lines[i].text)] += 1
    out = []
    for i, ln in enumerate(lines):
        if i in edges and ln.size < thr:
            if _PAGE_NO.match(ln.text) or (len(ln.text) <= 90 and seen[key(ln.text)] >= 3):
                continue
        out.append(ln)
    return out


_DROP_CAP = re.compile(r"[“\"‘'«(]?[A-ZÇĞİÖŞÜÂÎÛ]")


def join_drop_caps(lines: list[Line], body: float) -> list[Line]:
    """Tek büyük harften (ve isteğe bağlı açılış tırnağından) oluşan satır, aynı sayfada küçük harfle başlayan satırın
    ilk harfidir: «Y» + «aşlı balıkçı» → «Yaşlı balıkçı». Büyük harf birkaç satır boyunca iner: konum biliniyorsa
    taban çizgisinden harf boyu kadar yukarıdaki en üst satır, bilinmiyorsa bir sonraki satır. Gövde puntosunda tek
    harf (sözlükteki «A» ara başlığı, «O» zamiri) ve büyük harfle başlayan satıra yapıştırma yoktur."""
    def lower_start(ln: Line) -> bool:
        return ln.text[:1].isalpha() and ln.text[:1].islower()

    drop: set[int] = set()
    prefix: dict[int, str] = {}
    for i, ln in enumerate(lines):
        big = not ln.size or not body or ln.size >= body * 1.3
        if not big or not _DROP_CAP.fullmatch(ln.text):
            continue
        target: Optional[int] = None
        if ln.y is not None and ln.size:
            near = [k for k, o in enumerate(lines) if k != i and k not in prefix and o.page == ln.page and o.y is not None
                    and ln.y - 2 <= o.y <= ln.y + ln.size * 1.2 and lower_start(o)
                    and (ln.x is None or o.x is None or o.x >= ln.x)]
            target = max(near, key=lambda k: lines[k].y) if near else None
        if target is None and i + 1 < len(lines) and lines[i + 1].page == ln.page and lower_start(lines[i + 1]):
            target = i + 1
        if target is not None:
            drop.add(i)
            prefix[target] = ln.text
    out: list[Line] = []
    for k, ln in enumerate(lines):
        if k in drop:
            continue
        if k in prefix:
            ln = Line(ln.page, prefix[k] + ln.text, ln.size, ln.bold, ln.y, ln.kind, dict(ln.extra), ln.x)
        out.append(ln)
    return out


def reflow(lines: list[str]) -> str:
    """PDF'in görsel satırlarını paragrafa birleştirir: satır cümle sonuyla bitmiyorsa ve tam satır boyundaysa
    sonraki satır aynı paragraftır; satır sonu tirelemesi («keli-/me») kaldırılır; konuşma çizgisi yeni paragraftır.
    Küçük harfle süren satır kısa satırdan sonra da aynı cümledir (dar sütun, resmin yanına dökülen metin: satırların
    hepsi kısa); heceleme tiresi satır boyundan önce denetlenir («kal-» + «kanı»)."""
    if not lines:
        return ""
    lens = sorted(len(x) for x in lines)
    full = lens[len(lens) // 2] * 0.6 if lens else 0
    out: list[str] = []
    buf, last = "", ""
    for ln in lines:
        if not buf:
            buf = last = ln
            continue
        lower_next = ln[:1].isalpha() and ln[:1].islower()
        dialog = bool(re.match(r"^[—–-]\s", ln))
        closed = bool(re.search(r"[.!?…:»”\"]\s*$", last))
        if lower_next and re.search(r"[^\W\d_][-\u00ad\u2010]$", last):
            buf = buf[:-1] + ln
        elif closed or dialog or (len(last) < full and not lower_next):
            out.append(buf)
            buf = ln
        else:
            buf = f"{buf} {ln}"
        last = ln
    if buf:
        out.append(buf)
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------- PDF: yöntemler

def _flat_outline(reader: Any) -> list[tuple[int, str, int, Optional[float], bool]]:
    """(derinlik, ad, sayfa, üst konum, çocuğu var mı) — sayfası bulunamayan işaret atlanır."""
    out: list[tuple[int, str, int, Optional[float], bool]] = []

    def walk(items: list[Any], depth: int) -> None:
        for i, it in enumerate(items):
            if isinstance(it, list):
                walk(it, depth + 1)
                continue
            try:
                page = reader.get_destination_page_number(it)
                title = str(it.title or "").strip()
                top = it.top
                top_f = float(top) if top is not None else None
            except Exception:  # noqa: BLE001
                continue
            has_kids = i + 1 < len(items) and isinstance(items[i + 1], list)
            if page is not None and page >= 0 and title:
                out.append((depth, title, int(page), top_f, has_kids))

    try:
        walk(list(reader.outline or []), 0)
    except Exception as e:  # noqa: BLE001 — bozuk içindekiler ağacı: diğer yöntemlere geçilir
        log.info("pdf outline okunamadı: %s", e)
        return []
    return out


def _outline_level(items: list[tuple[int, str, int, Optional[float], bool]]) -> list[tuple[str, int, Optional[float]]]:
    """Bölüm düzeyi: en üst düzey (iki ve üstü işaret); üstte tek işaret (kitabın adı) varsa bir alt düzey. Üst düzey
    işaretlerin çoğu alt işaret taşıyor ve alt düzey yaprak ise (kısım → bölüm) iki düzey birlikte sınırdır."""
    if not items:
        return []
    depths = Counter(d for d, *_ in items)
    level = min(depths)
    while depths.get(level, 0) < 2 and depths.get(level + 1, 0) >= 2:
        level += 1
    top = [it for it in items if it[0] == level]
    below = [it for it in items if it[0] == level + 1]
    use = {level}
    if top and below and sum(1 for it in top if it[4]) * 2 >= len(top) and sum(1 for it in below if not it[4]) * 5 >= len(below) * 4:
        use.add(level + 1)
    return [(t, p, y) for d, t, p, y, _ in items if d in use]


def _by_outline(reader: Any, lines: list[Line]) -> Optional[list[tuple[str, str]]]:
    marks = _outline_level(_flat_outline(reader))
    if len(marks) < 2:
        return None
    starts: dict[int, str] = {}
    last = -1
    for title, page, top in sorted(marks, key=lambda m: (m[1], -(m[2] or 0))):
        want = norm(title)
        cand = [i for i in range(len(lines)) if lines[i].page in (page, page + 1) and i > last]
        hit = next((i for i in cand if want and (norm(lines[i].text) == want or
                                                 (len(want) >= 6 and norm(lines[i].text).startswith(want[:40])))), None)
        if hit is None and top is not None:
            hit = next((i for i in cand if lines[i].page == page and lines[i].y is not None and lines[i].y <= top + 2), None)
        if hit is None:
            hit = next((i for i in cand if lines[i].page >= page), None)
        if hit is None:
            continue
        starts[hit] = title
        last = hit
    if len(starts) < 2:
        return None
    units: list[tuple[str, str]] = []
    for i, ln in enumerate(lines):
        if i in starts:
            units.append((starts[i], "head"))
            if norm(ln.text) == norm(starts[i]):
                continue            # başlık satırı adın kendisi; gövdeye tekrar girmesin
        units.append((ln.text, "body"))
    return assemble(units, reflow)


def _first_letter(text: str) -> str:
    return next((c for c in text if c.isalpha()), "")


_SENTENCE_END = re.compile(r"[.!?…:»”\"’')\]]\s*$")


def in_sentence(run: list[Line], prev: Optional[Line], nxt: Optional[Line]) -> bool:
    """Büyük puntolu satır dizisi cümlenin parçası mı (resimli kitapta vurgu yazısı): önceki satır cümleyi bitirmeden
    kalmış ve dizi ya da ardından gelen satır (en çok bir sayfa ötede) küçük harfle sürüyor, ya da dizi virgülle bitip
    küçük harfle sürüyor. Bölüm başlığı cümlenin ortasında durmaz. Tek başına virgül kanıt değildir («BAHAR GELMİŞ, /
    DÜNYA DÜMDÜZ OYSA» iki satırlık başlık); küçük harfle başlamak da değildir («birinci bölüm BABAM VE YILDIZ
    SARAYI»); önceki bölüm cümleyle bittiyse küçük harfle başlayan gövde başlığı süs yazısı yapmaz. Dizinin kendi
    içinde virgülden sonra küçük harfle süren satır da cümledir."""
    open_before = prev is not None and run[0].page - prev.page <= 1 and not _SENTENCE_END.search(prev.text)
    lower_after = nxt is not None and nxt.page - run[-1].page <= 1 and _first_letter(nxt.text).islower()
    if open_before and (lower_after or _first_letter(run[0].text).islower()):
        return True
    # dizinin içinde virgülle biten satırı küçük harfle süren satır izliyor («Taş yuvarlandı, / yuvarlandı, / …»)
    if any(re.search(r"[,;]\s*$", a.text) and _first_letter(b.text).islower() for a, b in zip(run, run[1:])):
        return True
    return bool(re.search(r"[,;]\s*$", run[-1].text)) and lower_after


def _by_typography(lines: list[Line], thr: float) -> Optional[list[tuple[str, str]]]:
    def big_line(ln: Line) -> bool:
        letters = len(_WORD.findall(ln.text))
        if re.match(r"[—–-]\s", ln.text):
            return False                 # konuşma çizgisiyle başlayan satır (büyük puntolu diyalog) başlık değildir
        return ln.size >= thr and len(ln.text) <= 150 and (letters >= 1 and len(re.sub(r"\W", "", ln.text)) >= 2
                                                             or bool(re.fullmatch(r"\W*(\d{1,3}|[IVXLC]{1,7})\W*", ln.text)))
    inline: set[int] = set()
    i = 0
    while i < len(lines):
        if not big_line(lines[i]):
            i += 1
            continue
        j = i
        while j < len(lines) and big_line(lines[j]):
            j += 1
        if in_sentence(lines[i:j], lines[i - 1] if i else None, lines[j] if j < len(lines) else None):
            inline.update(range(i, j))
        i = j
    ids = {id(lines[k]) for k in inline}

    def headish(ln: Line) -> bool:
        return big_line(ln) and id(ln) not in ids
    big = [ln for ln in lines if headish(ln)]
    if not big:
        return None
    pages_of: dict[float, set[int]] = {}
    for ln in big:
        pages_of.setdefault(ln.size, set()).add(ln.page)
    sizes = sorted(pages_of, reverse=True)
    level = next((s for s in sizes if len(pages_of[s]) >= 3), None) or next((s for s in sizes if len(pages_of[s]) >= 2), None)
    if level is None:
        return None
    units: list[tuple[str, str, int, float]] = []
    # Bölüm puntosundan küçük başlık satırı bölüm satırının hemen üstünde durabilir («OSMANLI MERKEZ VE TAŞRA» /
    # «BÖLÜM 1» / «MÜLKÎ-MALÎ İDARESİNDE»): aynı sayfada başlık gelirse onun devamıdır, gelmezse gövdedir.
    pre: list[Line] = []

    def flush_pre() -> None:
        units.extend((p.text, "body", p.page, p.size) for p in pre)
        pre.clear()

    above: list[Line] = []               # başlığın üstündeki satırlar: başlık satırları bitince devam olarak eklenir
    prev: Optional[Line] = None
    prev_head = False
    for ln in lines:
        head_line = headish(ln) and ln.size >= level - 0.25 and not (ln.size > level + 0.25 and len(pages_of[ln.size]) < 2)
        if not (head_line and prev_head and prev is not None and prev.page == ln.page and prev.size == ln.size):
            units.extend((p.text, "cont", p.page, p.size) for p in above)
            above.clear()
        if headish(ln) and ln.size > level + 0.25 and len(pages_of[ln.size]) < 2:
            # Bölüm puntosundan büyük ve yalnız bir sayfada geçen satır (kapaktaki kitap adı) bölüm değildir.
            flush_pre()
            units.append((ln.text, "body", ln.page, ln.size))
        elif head_line:
            # Aynı sayfada aynı puntoda art arda satır: kırılmış tek başlık, boşlukla birleşir.
            if prev_head and prev is not None and prev.page == ln.page and prev.size == ln.size:
                units[-1] = (f"{units[-1][0]} {ln.text}", "head", ln.page, ln.size)
            else:
                above = [p for p in pre if p.page == ln.page]
                pre[:] = [p for p in pre if p.page != ln.page]
                flush_pre()
                units.append((ln.text, "head", ln.page, ln.size))
        elif headish(ln) and (_first_letter(ln.text).islower() or re.match(r"[“\"‘'«—–-]", ln.text)):
            # küçük harfle, tırnakla ya da konuşma çizgisiyle başlayan büyük satır başlığın devamı değildir
            # (konuşma balonu, büyük puntolu alıntı)
            flush_pre()
            units.append((ln.text, "body", ln.page, ln.size))
        elif headish(ln) and units and units[-1][1] in ("head", "cont") and not pre:
            units.append((ln.text, "cont", ln.page, ln.size))
        elif headish(ln):
            if pre and pre[-1].page != ln.page:
                flush_pre()
            pre.append(ln)
        else:
            flush_pre()
            units.append((ln.text, "body", ln.page, ln.size))
        prev, prev_head = ln, head_line
    units.extend((p.text, "cont", p.page, p.size) for p in above)
    flush_pre()
    merged: list[tuple[str, str, int, float]] = []
    for u in units:                      # aynı sayfada aynı puntoda art arda devam satırları tek ad parçası
        if merged and u[1] == "cont" and merged[-1][1] == "cont" and merged[-1][2:] == u[2:]:
            merged[-1] = (f"{merged[-1][0]} {u[0]}", "cont", u[2], u[3])
        else:
            merged.append(u)
    chapters = assemble(merged, reflow)
    pages = len({ln.page for ln in lines})
    if len(chapters) < 2 or (pages >= 20 and len(chapters) > pages * 0.8):
        return None                     # neredeyse her sayfa «bölüm»: tipografi bölüm değil sayfa düzeni söylüyor
    return chapters


_TOC = re.compile(r"^(?P<t>\S.{1,150}?)\s*(?:(?:[.·…_]\s*){2,}|\s{2,}|\s)(?P<p>\d{1,4})$")


def _by_toc(lines: list[Line]) -> Optional[list[tuple[str, str]]]:
    """İçindekiler sayfası: art arda en az 3 «Başlık …… 12» satırı (sayfa numaraları çoğunlukla artan); başlıklar
    metinde, içindekiler sayfaları dışında, sırayla tek başına satır olarak aranır."""
    if not lines:
        return None
    n_pages = max(ln.page for ln in lines) + 1
    zone = {p for p in range(n_pages) if p < max(3, n_pages * 0.25) or p >= n_pages * 0.9}
    best: list[tuple[int, str, int]] = []
    run: list[tuple[int, str, int]] = []
    misses = 0
    for i, ln in enumerate(lines):
        m = _TOC.match(ln.text) if ln.page in zone else None
        if m and _words(m.group("t")) >= 1:
            if run and ln.page - lines[run[-1][0]].page > 1:
                best = run if len(run) > len(best) else best
                run = []
            run.append((i, m.group("t").strip(" .·…_"), int(m.group("p"))))
            misses = 0
            continue
        # Kırılmış uzun başlık ya da «İçindekiler» satırı dizini bozmasın: üç eşleşmeyen satıra kadar dizi sürer.
        misses += 1
        if misses >= 3 or ln.page not in zone:
            best = run if len(run) > len(best) else best
            run, misses = [], 0
    best = run if len(run) > len(best) else best
    if len(best) < 3:
        return None
    nums = [p for _, _, p in best]
    if sum(1 for a, b in zip(nums, nums[1:]) if b >= a) < 0.8 * (len(nums) - 1):
        return None
    toc_pages = {lines[i].page for i, _, _ in best}
    starts: dict[int, str] = {}
    pos = 0
    for _, title, _ in best:
        want = norm(title)
        if not want:
            continue
        for j in range(pos, len(lines)):
            if lines[j].page in toc_pages:
                continue
            got = norm(lines[j].text)
            if got == want or (len(want) >= 6 and got.startswith(want) and len(got) <= len(want) + 20):
                starts[j] = title
                pos = j + 1
                break
    if len(starts) < 2:
        return None
    units = [(starts[i], "head") if i in starts else (ln.text, "body") for i, ln in enumerate(lines)
             if not (i not in starts and ln.page in toc_pages and _TOC.match(ln.text))]
    return assemble(units, reflow)


def _by_pattern(lines: list[Line]) -> Optional[list[tuple[str, str]]]:
    units = [(ln.text, "head" if chapter_word(ln.text) else "body") for ln in lines]
    if sum(1 for _, k in units if k == "head") < 2:
        return None
    out = assemble(units, reflow)
    return out if len(out) >= 2 else None


_SPACED_HYPHEN_END = re.compile(r"([^\W\d_]+) [-\u00ad\u2010]$")
_MID_DASH = re.compile(r"[^\W\d_] [-\u2010] [^\W\d_]")


def mend_spaced_hyphens(lines: list[Line]) -> list[Line]:
    """Satır «med -» diye bitip sonraki «yada» diye küçük harfle sürüyorsa tire ya satır sonu hecelemesidir (okuyucu
    kenara asılan tirenin önüne boşluk koymuş) ya da gerçek konuşma/ara çizgisidir («kısmının - masrafların»). Konum
    ayırt etmez; kitabın kendi yazımı eder: kitap satır ortasında boşluklu çizgi («kelime - kelime») kullanmıyorsa satır
    sonundakiler hecelemedir. Kullanıyorsa kitabın sözlüğüne bakılır (parçaların kendisi sayılmaz): birleşik hâl
    kitapta geçiyorsa heceleme («şaşkın»); geçmiyor ve iki parça da kelimeyse çizgi; değilse heceleme.
    Heceleme ise boşluk atılır, satır birleşirken tire düşer."""
    pairs = [(a, b, m) for a, b in zip(lines, lines[1:])
             if (m := _SPACED_HYPHEN_END.search(a.text)) and 0 <= b.page - a.page <= 1
             and b.text[:1].isalpha() and b.text[:1].islower()]
    if not pairs:
        return lines
    uses_dash = sum(1 for ln in lines if _MID_DASH.search(ln.text)) * 10 >= len(pairs)
    vocab: Counter = Counter()
    if uses_dash:                        # hece parçaları sözlüğe girmez: tireyle biten satırın son, sonrakinin ilk kelimesi
        cut_last = {id(a) for a in lines if re.search(r"[-\u00ad\u2010]$", a.text)}
        cut_first = {id(b) for a, b in zip(lines, lines[1:]) if id(a) in cut_last}
        for ln in lines:
            words = _WORD.findall(ln.text)
            if id(ln) in cut_last and words:
                words = words[:-1]
            if id(ln) in cut_first and words:
                words = words[1:]
            vocab.update(tr_lower(w) for w in words)
    for a, b, m in pairs:
        right = _WORD.match(b.text)
        if uses_dash and right:
            left_w, right_w = tr_lower(m.group(1)), tr_lower(right.group(0))
            if not vocab[left_w + right_w] and vocab[left_w] >= 1 and vocab[right_w] >= 1:
                continue                 # birleşik hâli kitapta yok, iki parça da kelime: ara çizgisi
        a.text = a.text[:m.end(1)] + "-"
    return lines


_PUA_WORD = re.compile(r"(?:[^\W\d_]|[\ue000-\uf8ff])*[\ue000-\uf8ff](?:[^\W\d_]|[\ue000-\uf8ff])*")
#: Eski «Türkçeleştirilmiş» fontların başka karakterin yerine koyduğu harfler (küçük hâlleriyle).
_TR_SPECIAL = "şğıiçöüâîû"
#: Bir özel alan karakterinin harfe çevrilmesi için en az bu kadar kelimede tutması ve ikinci adayın en az bu katı olması.
PUA_MIN_HITS = 2
PUA_MARGIN = 2


def resolve_private_letters(lines: list[Line]) -> list[Line]:
    """Fontun verisinden onarılamayan özel alan karakteri, eski tip Türkçe fontta bir Türkçe harfin yerini tutar
    («A?k», «Dönü?ür» — ? özel alan karakteri). Kitabın kendi sözlüğü karar verir: karakterin yerine her aday harf konur, oluşan
    kelimenin kitabın başka yerinde (özel karaktersiz) geçtiği kelime sayılır; açık farkla kazanan harf yazılır (büyük
    harfli kelimede büyük hâli). Kazanan yoksa karakter kalır ve okunamadı sayılır."""
    tokens: dict[str, list[str]] = {}
    for ln in lines:
        for w in _PUA_WORD.findall(ln.text):
            for ch in {c for c in w if pdf_text.is_pua(c)}:
                tokens.setdefault(ch, []).append(w)
    if not tokens:
        return lines
    vocab = Counter(tr_lower(w) for ln in lines for w in _WORD.findall(ln.text))
    upper = {"i": "İ", "ı": "I"}
    chosen: dict[str, str] = {}
    for ch, words in tokens.items():
        scorable = [w for w in words if sum(pdf_text.is_pua(c) for c in w) == 1 and len(w) >= 3]
        score = sorted(((sum(1 for w in scorable if vocab[tr_lower(w.replace(ch, cand))]), cand) for cand in _TR_SPECIAL),
                       reverse=True)
        if score and score[0][0] >= PUA_MIN_HITS and score[0][0] >= PUA_MARGIN * max(score[1][0], 0.5):
            chosen[ch] = score[0][1]
    if not chosen:
        return lines

    def fix(m: re.Match) -> str:
        w = m.group(0)
        letters = [c for c in w if c.isalpha()]
        caps = bool(letters) and all(c.isupper() for c in letters)
        return "".join((upper.get(chosen[c], chosen[c].upper()) if caps else chosen[c]) if c in chosen else c for c in w)

    for ln in lines:
        if any(c in chosen for c in ln.text):
            ln.text = _PUA_WORD.sub(fix, ln.text)
    log.info("özel alan karakteri kitabın sözlüğüyle çözüldü: %s", {hex(ord(k)): v for k, v in chosen.items()})
    return lines


def pdf_structure(reader: Any) -> Structure:
    pdf_text.repair_reader(reader)
    raw = pdf_lines(reader)
    body = body_size(raw)
    thr = head_threshold(body)
    lines = resolve_private_letters(mend_spaced_hyphens(join_drop_caps(drop_furniture(raw, thr), body)))
    bad = sum(pdf_text.unreadable(ln.text) for ln in lines)
    if bad:
        log.warning("pdf metninde onarılamayan %s karakter kaldı", bad)
    st = _pdf_split(reader, lines, thr)
    st.unreadable_chars = bad
    return st


def _pdf_split(reader: Any, lines: list[Line], thr: float) -> Structure:
    for source, fn in (("outline", lambda: _by_outline(reader, lines)), ("typography", lambda: _by_typography(lines, thr)),
                       ("toc", lambda: _by_toc(lines)), ("pattern", lambda: _by_pattern(lines))):
        try:
            got = fn()
        except Exception as e:  # noqa: BLE001 — bir yöntemin hatası diğerlerini durdurmaz
            log.warning("pdf bölümleme (%s) düştü: %s", source, e)
            got = None
        if got and len(got) >= 2:
            return Structure(got, source)
    # Parça: satırlar sayfa sayfa paragrafa birleştirilir, sayfa bilgisi ada gider.
    paras: list[tuple[str, Optional[int]]] = []
    by_page: dict[int, list[str]] = {}
    for ln in lines:
        by_page.setdefault(ln.page, []).append(ln.text)
    for page in sorted(by_page):
        for p in reflow(by_page[page]).split("\n"):
            if p.strip():
                paras.append((p, page))
    return Structure(pieces(paras, pdf=True), "pieces")


# ---------------------------------------------------------------------------------------------- DOCX

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_HEAD_NAME = re.compile(r"(?i)^(?:heading|başlık|baslik|balk)\s*(\d)$")
_TITLE_NAME = re.compile(r"(?i)^(?:title|konu başlığı|kitap başlığı)$")


def _docx_style_levels(z: zipfile.ZipFile) -> dict[str, Optional[int]]:
    """styleId → ana hat düzeyi (0 = Başlık 1; -1 = belge başlığı; None = gövde). Miras (basedOn) izlenir."""
    try:
        root = ElementTree.fromstring(z.read("word/styles.xml"))
    except (KeyError, ElementTree.ParseError):
        return {}
    own: dict[str, Optional[int]] = {}
    based: dict[str, str] = {}
    for st in root.iter(f"{_W}style"):
        sid = st.get(f"{_W}styleId") or ""
        name_el = st.find(f"{_W}name")
        name = (name_el.get(f"{_W}val") if name_el is not None else "") or ""
        lvl_el = st.find(f"{_W}pPr/{_W}outlineLvl")
        lvl: Optional[int] = None
        if lvl_el is not None and str(lvl_el.get(f"{_W}val") or "").isdigit():
            v = int(lvl_el.get(f"{_W}val"))
            lvl = v if v < 9 else None
        else:
            m = _HEAD_NAME.match(name) or _HEAD_NAME.match(sid)
            if m:
                lvl = int(m.group(1)) - 1
            elif _TITLE_NAME.match(name) or sid.lower() == "title":
                lvl = -1
        own[sid] = lvl
        b = st.find(f"{_W}basedOn")
        if b is not None and b.get(f"{_W}val"):
            based[sid] = b.get(f"{_W}val")
    out: dict[str, Optional[int]] = {}
    for sid in own:
        cur, lvl, hops = sid, own[sid], 0
        while lvl is None and cur in based and hops < 10:
            cur = based[cur]
            lvl = own.get(cur)
            hops += 1
        out[sid] = lvl
    return out


def docx_leveled(z: zipfile.ZipFile) -> list[tuple[str, Optional[int]]]:
    try:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    except KeyError as e:
        raise ValueError("word/document.xml yok") from e
    levels = _docx_style_levels(z)
    out: list[tuple[str, Optional[int]]] = []
    for p in root.iter(f"{_W}p"):
        text = "".join(t.text or "" for t in p.iter(f"{_W}t")).strip()
        if not text:
            continue
        lvl: Optional[int] = None
        direct = p.find(f"{_W}pPr/{_W}outlineLvl")
        if direct is not None and str(direct.get(f"{_W}val") or "").isdigit():
            v = int(direct.get(f"{_W}val"))
            lvl = v if v < 9 else None
        else:
            style = p.find(f"{_W}pPr/{_W}pStyle")
            sid = (style.get(f"{_W}val") if style is not None else "") or ""
            lvl = levels.get(sid)
            if lvl is None and sid:
                m = _HEAD_NAME.match(sid)
                lvl = int(m.group(1)) - 1 if m else (-1 if sid.lower() == "title" else None)
        out.append((text, lvl))
    return out


def _by_levels(paras: list[tuple[str, Optional[int]]]) -> Optional[list[tuple[str, str]]]:
    """Bölüm düzeyi: en az iki kez geçen en üst başlık düzeyi (tek «Başlık 1» kitabın adıdır, gövdede kalır). Daha
    üst düzeyde birden çok geçen başlık da sınırdır (kısım); daha alt düzey, başlıktan hemen sonra geliyorsa adın devamı, yoksa gövde (alt başlık)."""
    counts = Counter(lvl for _, lvl in paras if lvl is not None)
    level = next((lvl for lvl in sorted(counts) if counts[lvl] >= 2), None)
    if level is None:
        return None
    units: list[tuple[str, str]] = []
    for text, lvl in paras:
        if lvl is not None and lvl < level and counts[lvl] < 2:
            units.append((text, "body"))        # bir kez geçen üst düzey (kitabın adı) bölüm değildir
        elif lvl is not None and lvl <= level:
            units.append((text, "head"))
        elif lvl is not None and units and units[-1][1] in ("head", "cont"):
            units.append((text, "cont"))
        else:
            units.append((text, "body"))
    out = assemble(units, lambda b: "\n".join(b))
    return out if len(out) >= 2 else None


def docx_structure(data: Any) -> Structure:
    """`data`: bayt ya da dosya yolu."""
    src = io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
    with zipfile.ZipFile(src) as z:
        paras = docx_leveled(z)
    got = _by_levels(paras)
    if got:
        return Structure(got, "styles")
    units = [(t, "head" if chapter_word(t) else "body") for t, _ in paras]
    if sum(1 for _, k in units if k == "head") >= 2:
        out = assemble(units, lambda b: "\n".join(b))
        if len(out) >= 2:
            return Structure(out, "pattern")
    return Structure(pieces([(t, None) for t, _ in paras], pdf=False), "pieces")


# ---------------------------------------------------------------------------------------------- TXT / MD

_MD_HEAD = re.compile(r"^(#{1,6})\s+(\S.*?)\s*#*\s*$")


def text_structure(text: str, old_heading: "re.Pattern[str]") -> Structure:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    md = [(m.group(2), len(m.group(1))) if (m := _MD_HEAD.match(ln)) else (ln, None) for ln in lines]
    if sum(1 for _, lvl in md if lvl is not None) >= 2:
        got = _by_levels(md)
        if got:
            return Structure(got, "markdown")
    units = [(ln, "head" if len(ln) <= 90 and old_heading.match(ln) else "body") for ln in lines]
    if sum(1 for _, k in units if k == "head") >= 1:
        out = assemble(units, lambda b: "\n".join(b), lead="Giriş")
        if len(out) >= 2 or (out and out[0][0] != "Giriş"):
            return Structure(out, "pattern")
    return Structure(pieces([(ln, None) for ln in lines], pdf=False), "pieces")
