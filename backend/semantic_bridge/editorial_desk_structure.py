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

log = logging.getLogger("semantic.editorial_desk_structure")

#: Yapı bulunamayınca bir parçanın hedef büyüklüğü (kelime). Sınır değil: parça paragraf sınırında kesilir.
PIECE_WORDS = 3000
#: Bölümlerden önceki sayfaların (kapak, künye, içindekiler) adı.
LEAD = "Bölümlerden önce"

@dataclass
class Structure:
    chapters: list[tuple[str, str]]
    source: str

    @property
    def unit(self) -> str:
        return "parca" if self.source == "pieces" else "bolum"

    def report(self) -> dict[str, Any]:
        return {"structure": self.source, "unit": self.unit}


@dataclass
class Line:
    page: int                 # 0 tabanlı PDF sayfası
    text: str
    size: float = 0.0         # karakter ağırlıklı punto (0 = bilinmiyor)
    bold: bool = False
    y: Optional[float] = None
    kind: str = "body"        # body | head | cont
    extra: dict[str, Any] = field(default_factory=dict)


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


def pdf_lines(reader: Any) -> list[Line]:
    """Sayfa sayfa satırlar ve her satırın puntosu, kalınlığı, dikey konumu (metin çıkarıcının ziyaretçisiyle)."""
    out: list[Line] = []
    for pno, page in enumerate(reader.pages):
        cur: dict[str, Any] = {"parts": [], "sizes": Counter(), "bold": 0, "chars": 0, "y": None}

        def flush(pno: int = pno, cur: dict[str, Any] = cur) -> None:
            text = re.sub(r"\s+", " ", "".join(cur["parts"])).strip()
            if text:
                size = cur["sizes"].most_common(1)[0][0] if cur["sizes"] else 0.0
                out.append(Line(pno, text, size, cur["bold"] * 2 > cur["chars"], cur["y"]))
            cur.update(parts=[], sizes=Counter(), bold=0, chars=0, y=None)

        def visit(text: Any, cm: Any, tm: Any, font: Any, font_size: Any, cur: dict[str, Any] = cur,
                  flush: Callable[[], None] = flush) -> None:
            if not text:
                return
            try:
                m = _mult([float(v) for v in tm], [float(v) for v in cm])
                size = round(abs(float(font_size or 0)) * math.hypot(m[2], m[3]) * 2) / 2
                y: Optional[float] = m[5]
            except Exception:  # noqa: BLE001 — konum okunamazsa punto bilinmiyor sayılır
                size, y = 0.0, None
            try:
                bold = bool(font is not None and _BOLD.search(str(font.get("/BaseFont") or "")))
            except Exception:  # noqa: BLE001
                bold = False
            for i, part in enumerate(str(text).split("\n")):
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

        try:
            page.extract_text(visitor_text=visit)
        except Exception as e:  # noqa: BLE001 — okunamayan sayfa atlanır, kitabın geri kalanı ayrılır
            log.warning("pdf sayfa %s okunamadı: %s", pno + 1, e)
        flush()
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


def reflow(lines: list[str]) -> str:
    """PDF'in görsel satırlarını paragrafa birleştirir: satır cümle sonuyla bitmiyorsa ve tam satır boyundaysa
    sonraki satır aynı paragraftır; satır sonu tirelemesi («keli-/me») kaldırılır; konuşma çizgisi yeni paragraftır."""
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
        ends = bool(re.search(r"[.!?…:»”\"]\s*$", last)) or len(last) < full or bool(re.match(r"^[—–-]\s", ln))
        if ends:
            out.append(buf)
            buf = ln
        elif re.search(r"[^\W\d_]-$", last) and ln[:1].islower():
            buf = buf[:-1] + ln
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


def _by_typography(lines: list[Line], thr: float) -> Optional[list[tuple[str, str]]]:
    def headish(ln: Line) -> bool:
        letters = len(_WORD.findall(ln.text))
        return ln.size >= thr and len(ln.text) <= 150 and (letters >= 1 and len(re.sub(r"\W", "", ln.text)) >= 2
                                                             or bool(re.fullmatch(r"\W*(\d{1,3}|[IVXLC]{1,7})\W*", ln.text)))
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
    units: list[tuple[str, str, int]] = []
    prev: Optional[Line] = None
    for ln in lines:
        if headish(ln) and ln.size > level + 0.25 and len(pages_of[ln.size]) < 2:
            # Bölüm puntosundan büyük ve yalnız bir sayfada geçen satır (kapaktaki kitap adı) bölüm değildir.
            units.append((ln.text, "body", ln.page))
        elif headish(ln) and ln.size >= level - 0.25:
            # Aynı sayfada aynı puntoda art arda satır: kırılmış tek başlık, boşlukla birleşir.
            if prev is not None and units and units[-1][1] == "head" and prev.page == ln.page and prev.size == ln.size:
                units[-1] = (f"{units[-1][0]} {ln.text}", "head", ln.page)
            else:
                units.append((ln.text, "head", ln.page))
        elif headish(ln):
            units.append((ln.text, "cont" if units and units[-1][1] in ("head", "cont") else "body", ln.page))
        else:
            units.append((ln.text, "body", ln.page))
        prev = ln
    chapters = assemble(units, reflow)
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


def pdf_structure(reader: Any) -> Structure:
    raw = pdf_lines(reader)
    thr = head_threshold(body_size(raw))
    lines = drop_furniture(raw, thr)
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
