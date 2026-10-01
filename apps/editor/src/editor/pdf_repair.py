"""PDF metin katmanındaki yanlış harf eşlemelerinin fontun kendi verisinden onarılması (pymupdf).

Kaynak: BI tarafındaki `backend/semantic_bridge/editorial_pdf_text.py` (pypdf ile, Redaksiyon masası) ve
`editorial_desk_structure.py` (`resolve_private_letters`, ı'sız fontta küçültülmüş «l»). Editör imajı BI kodunu
içermez; aynı kurallar burada pymupdf'in nesne arayüzüyle yazıldı. İki taraf aynı kusur sınıflarını onarır:

1. **Glif adı → harf.** Fontun kodlama farkları (`/Differences`) glifin adını taşır; özel alana (PUA) eşlenmiş ya da
   okuyucunun çözemeyeceği ad Adobe Glyph List kuralıyla harfe çevrilir (`A.alt4` → `A`).
2. **İkiz glif.** CID TrueType fontta harf olmayan karaktere («‹», özel alan) eşli glifin çizimi harfe eşli bir glifle
   birebir aynıysa o harftir; özel alana eşli glif «harf + temel çizginin altında tek kontur» ise çengelli harftir
   (s → ş, c → ç). Eski tip «Türkçeleştirilmiş» font: «G‹R‹Ş» → «GİRİŞ».
3. **Noktalı I.** CID fontta «I»/«ı» diye eşlenmiş glifin çiziminde üstte ayrı yuvarlak bir işaret varsa «İ»/«i».
4. **Simge fontu** (Wingdings, Webdings, Dingbats): özel alana eşli karakter madde işaretidir («•»).
5. **Fontun verisinden çıkmayan özel alan karakteri**: kitabın kendi sözlüğü karar verir (`resolve_private_letters`).

Onarım yalnız bellekteki belge nesnesinde yapılır: font sözlüğüne yeni bir ToUnicode akışı bağlanır, dosya
kaydedilmez. Kitaba ya da fonta özel kural yoktur; fontun verisinden çıkmayan harf onarılmaz.
"""

from __future__ import annotations

import io
import logging
import re
from collections import Counter
from typing import Optional

log = logging.getLogger("editor.pdf_repair")

try:
    from fontTools.agl import AGL2UV as _AGL
    from fontTools.agl import toUnicode as _agl_to_unicode
except Exception:  # noqa: BLE001 — fontTools yoksa yalnız uniXXXX adları çözülür
    _AGL = {}
    _agl_to_unicode = None


def is_pua(ch: str) -> bool:
    o = ord(ch)
    return 0xE000 <= o <= 0xF8FF or o >= 0xF0000


def unreadable(text: str) -> int:
    return sum(1 for ch in text if is_pua(ch) or ch == "�")


def glyph_unicode(name: str) -> Optional[str]:
    """Glif adından metin (AGL: noktadan sonrası atılır, «_» bağlı harf, uniXXXX / uXXXXX)."""
    base = str(name).lstrip("/").split(".", 1)[0]
    if not base:
        return None
    out = []
    for part in base.split("_"):
        u = chr(_AGL[part]) if part in _AGL else None
        if u is None:
            m = re.fullmatch(r"uni((?:[0-9A-F]{4})+)", part)
            if m:
                u = "".join(chr(int(m.group(1)[i:i + 4], 16)) for i in range(0, len(m.group(1)), 4))
            else:
                m = re.fullmatch(r"u([0-9A-F]{4,6})", part)
                u = chr(int(m.group(1), 16)) if m and int(m.group(1), 16) <= 0x10FFFF else None
        if not u and _agl_to_unicode is not None:
            u = _agl_to_unicode(part) or None
        if not u:
            return None
        out.append(u)
    s = "".join(out)
    return s if s and not any(is_pua(c) for c in s) else None


# ---------------------------------------------------------------------------------------------- ToUnicode

def _utf16(hexs: str) -> str:
    if len(hexs) % 4:
        hexs = hexs.rjust(len(hexs) + 4 - len(hexs) % 4, "0")
    return bytes.fromhex(hexs).decode("utf-16-be", errors="replace")


def parse_cmap(data: bytes) -> tuple[dict[int, str], int]:
    """ToUnicode CMap → ({kod: metin}, kod genişliği bayt)."""
    text = data.decode("latin-1")
    out: dict[int, str] = {}
    width = 1
    for block in re.findall(r"begincodespacerange(.*?)endcodespacerange", text, re.S):
        for a in re.findall(r"<([0-9A-Fa-f]+)>", block):
            width = max(width, len(a) // 2)
    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", block):
            out[int(src, 16)] = _utf16(dst)
    for block in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        for a, b, rest in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[[^\]]*\]|<[0-9A-Fa-f]*>)", block):
            lo, hi = int(a, 16), int(b, 16)
            if rest.startswith("["):
                for k, d in enumerate(re.findall(r"<([0-9A-Fa-f]*)>", rest)):
                    out[lo + k] = _utf16(d)
            elif hi - lo <= 0xFFFF:
                start = _utf16(rest[1:-1])
                if start:
                    for k in range(hi - lo + 1):
                        out[lo + k] = start[:-1] + chr(min(0x10FFFF, ord(start[-1]) + k))
    return out, width


def cmap_bytes(mapping: dict[int, str], width: int) -> bytes:
    lines = ["/CIDInit /ProcSet findresource begin", "12 dict begin", "begincmap",
             "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
             "/CMapName /Adobe-Identity-UCS def", "/CMapType 2 def",
             "1 begincodespacerange", f"<{'00' * width}> <{'FF' * width}>", "endcodespacerange"]
    items = sorted((c, u) for c, u in mapping.items() if u)
    for i in range(0, len(items), 100):
        chunk = items[i:i + 100]
        lines.append(f"{len(chunk)} beginbfchar")
        for c, u in chunk:
            lines.append(f"<{c:0{width * 2}X}> <{u.encode('utf-16-be').hex().upper()}>")
        lines.append("endbfchar")
    lines += ["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]
    return "\n".join(lines).encode("latin-1")


# ---------------------------------------------------------------------------------------------- font nesnesi

def _ref(val: tuple[str, str]) -> Optional[int]:
    """xref_get_key sonucu dolaylı başvuruysa nesne numarası."""
    kind, v = val
    if kind == "xref":
        m = re.match(r"(\d+) 0 R", v)
        return int(m.group(1)) if m else None
    if kind == "array":
        m = re.match(r"\[\s*(\d+) 0 R", v)
        return int(m.group(1)) if m else None
    return None


class _Font:
    """Bir font sözlüğünün onarımda gereken alanları (pymupdf xref arayüzüyle)."""

    def __init__(self, doc, xref: int):
        self.doc, self.xref = doc, xref
        self.subtype = doc.xref_get_key(xref, "Subtype")[1]
        self.base = doc.xref_get_key(xref, "BaseFont")[1]
        self.encoding = doc.xref_get_key(xref, "Encoding")
        self._cur: Optional[tuple[dict[int, str], int]] = None

    def current(self) -> tuple[dict[int, str], int]:
        if self._cur is None:
            tu = _ref(self.doc.xref_get_key(self.xref, "ToUnicode"))
            if tu is None:
                self._cur = ({}, 1)
            else:
                try:
                    self._cur = parse_cmap(self.doc.xref_stream(tu) or b"")
                except Exception:  # noqa: BLE001 — okunamayan tablo: onarım yapılmaz
                    self._cur = ({}, 0)
        return self._cur

    def has_tounicode(self) -> bool:
        return _ref(self.doc.xref_get_key(self.xref, "ToUnicode")) is not None

    def set_cmap(self, mapping: dict[int, str], width: int) -> None:
        """Yeni ToUnicode akışı yalnız bu fonta bağlanır (paylaşılan tablo değişmez)."""
        doc = self.doc
        x = doc.get_new_xref()
        doc.update_object(x, "<<>>")
        doc.update_stream(x, cmap_bytes(mapping, width))
        doc.xref_set_key(self.xref, "ToUnicode", f"{x} 0 R")
        self._cur = (dict(mapping), width)

    def differences(self) -> dict[int, str]:
        kind, val = self.doc.xref_get_key(self.xref, "Encoding/Differences")
        if kind != "array":
            return {}
        names: dict[int, str] = {}
        code = 0
        for tok in re.findall(r"/[^\s/\[\]()<>]*|-?\d+", val):
            if tok.startswith("/"):
                names[code] = re.sub(r"#([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), tok[1:])
                code += 1
            else:
                code = int(tok)
        return names

    def cid_truetype(self) -> Optional[bytes]:
        """Identity eşlemeli CIDFontType2 ise gömülü TrueType verisi."""
        if self.subtype != "/Type0":
            return None
        doc = self.doc
        desc = _ref(doc.xref_get_key(self.xref, "DescendantFonts"))
        if desc is not None and doc.xref_object(desc, compressed=True).lstrip().startswith("["):
            desc = _ref(("array", doc.xref_object(desc, compressed=True).strip()))   # dolaylı dizi: [n 0 R]
        if desc is None:
            return None
        if doc.xref_get_key(desc, "Subtype")[1] != "/CIDFontType2":
            return None
        c2g = doc.xref_get_key(desc, "CIDToGIDMap")
        if c2g[0] != "null" and c2g[1] != "/Identity":
            return None
        ff = _ref(doc.xref_get_key(desc, "FontDescriptor/FontFile2"))
        if ff is None:
            return None
        try:
            return doc.xref_stream(ff)
        except Exception:  # noqa: BLE001
            return None


# ---------------------------------------------------------------------------------------------- 1) glif adı

def repair_by_glyph_names(font: _Font) -> int:
    """Basit fontta PUA'ya eşlenmiş ya da okuyucunun çözemeyeceği glif adı taşıyan kodlar."""
    names = font.differences()
    if not names:
        return 0
    cur, width = font.current()
    if not width:
        return 0
    new = dict(cur)
    fixed = 0
    for code, name in names.items():
        have = cur.get(code)
        if have and not any(is_pua(c) for c in have):
            continue
        if have is None and name in _AGL:
            continue                    # okuyucu bu adı kendi listesinden zaten doğru çözer
        u = glyph_unicode(name)
        if u:
            new[code] = u
            fixed += 1
    if fixed:
        font.set_cmap(new, width)
    return fixed


# ---------------------------------------------------------------------------------------------- 2) noktalı I

#: İşaret noktadır: genişliği yüksekliğinin en çok bu katı (şapka/uzatma daha geniştir) ve gövdenin bu oranından
#: kısa; gövdenin üstünde başlar (gövde yüksekliğinin %5'i kadar örtüşmeye izin).
DOT_MAX_ASPECT = 1.6
DOT_MAX_HEIGHT = 0.35
DOT_OVERLAP = 0.05


def _boxes(glyf, g) -> list[tuple[float, float, float, float]]:
    """Glifin parçaları: bileşik glifte bileşen kutuları (kaydırmayla), basit glifte kontur kutuları."""
    if g.isComposite():
        out = []
        for comp in g.components:
            if not hasattr(comp, "x") or getattr(comp, "transform", None) not in (None, [[1, 0], [0, 1]]):
                return []
            cg = glyf[comp.glyphName]
            if cg.isComposite() or not getattr(cg, "numberOfContours", 0):
                return []
            out.append((cg.xMin + comp.x, cg.yMin + comp.y, cg.xMax + comp.x, cg.yMax + comp.y))
        return out
    n = getattr(g, "numberOfContours", 0)
    if n <= 0:
        return []
    coords = g.getCoordinates(glyf)[0]
    out, start = [], 0
    for end in g.endPtsOfContours:
        pts = coords[start:end + 1]
        start = end + 1
        if pts:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            out.append((min(xs), min(ys), max(xs), max(ys)))
    return out


def has_dot_above(boxes: list[tuple[float, float, float, float]]) -> bool:
    if len(boxes) != 2:
        return False
    body, mark = sorted(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    bh = body[3] - body[1]
    mw, mh = mark[2] - mark[0], mark[3] - mark[1]
    return (bh > 0 and mh > 0 and mark[1] >= body[3] - DOT_OVERLAP * bh
            and mw <= DOT_MAX_ASPECT * mh and mh <= DOT_MAX_HEIGHT * bh)


def _ttfont(data: bytes):
    from fontTools.ttLib import TTFont
    tt = TTFont(io.BytesIO(data))
    return tt, tt["glyf"], tt.getGlyphOrder()


def repair_dotted_i(font: _Font, tt=None) -> int:
    """CID TrueType fontta «I»/«ı» diye eşlenmiş ama çiziminde üstte nokta olan glif → «İ»/«i»."""
    if not font.has_tounicode():
        return 0
    cur, width = font.current()
    targets = {c: u for c, u in cur.items() if u in ("I", "ı")}
    if not targets or not width or tt is None:
        return 0
    _, glyf, order = tt
    new = dict(cur)
    fixed = 0
    for code, u in targets.items():
        if code >= len(order):
            continue
        try:
            dotted = has_dot_above(_boxes(glyf, glyf[order[code]]))
        except Exception:  # noqa: BLE001
            dotted = False
        if dotted:
            new[code] = "İ" if u == "I" else "i"
            fixed += 1
    if fixed:
        font.set_cmap(new, width)
    return fixed


# ---------------------------------------------------------------------------------------------- 3) ikiz glif

def _contours(glyf, name: str) -> list[tuple[tuple[int, int], ...]]:
    coords, ends, _ = glyf[name].getCoordinates(glyf)
    pts = [(int(x), int(y)) for x, y in coords]
    out, start = [], 0
    for end in ends:
        out.append(tuple(pts[start:end + 1]))
        start = end + 1
    return out


_BELOW = {"s": "ş", "S": "Ş", "c": "ç", "C": "Ç"}


def repair_by_twin_glyphs(font: _Font, tt=None) -> int:
    """Harf olmayan karaktere eşli glifin çizimi harfe eşli bir glifle birebir aynıysa o harftir; özel alana eşli glif
    «harf + temel çizginin altında tek kontur» ise çengelli harftir."""
    if not font.has_tounicode() or tt is None:
        return 0
    cur, width = font.current()
    odd = {c: u for c, u in cur.items() if len(u) == 1 and not u.isalpha() and (is_pua(u) or u in "‹›�")}
    if not odd or not width:
        return 0
    ttf, glyf, order = tt
    try:
        slack = ttf["head"].unitsPerEm * 0.03
    except Exception:  # noqa: BLE001
        return 0

    def shape(code: int) -> Optional[list]:
        if code >= len(order):
            return None
        try:
            c = _contours(glyf, order[code])
        except Exception:  # noqa: BLE001
            return None
        return c or None

    by_shape: dict[tuple, str] = {}
    for c, u in cur.items():
        if len(u) == 1 and u.isalpha():
            sh = shape(c)
            if sh:
                by_shape.setdefault(tuple(sh), u)
    new = dict(cur)
    fixed = 0
    for code, u in odd.items():
        sh = shape(code)
        if not sh:
            continue
        twin = by_shape.get(tuple(sh))
        if twin:
            new[code] = twin
            fixed += 1
            continue
        if not is_pua(u) or len(sh) < 2:
            continue
        for k, extra in enumerate(sh):
            if max(p[1] for p in extra) > slack:
                continue
            base = by_shape.get(tuple(sh[:k] + sh[k + 1:]))
            if base in _BELOW:
                new[code] = _BELOW[base]
                fixed += 1
                break
    if fixed:
        font.set_cmap(new, width)
    return fixed


# ---------------------------------------------------------------------------------------------- 4) simge

_SYMBOL_FONT = re.compile(r"(?i)wingding|webding|dingbat")


def repair_symbol_font(font: _Font) -> int:
    if not _SYMBOL_FONT.search(font.base or "") or not font.has_tounicode():
        return 0
    cur, width = font.current()
    if not width:
        return 0
    new = {c: ("•" if any(is_pua(ch) for ch in u) else u) for c, u in cur.items()}
    fixed = sum(1 for c in cur if new[c] != cur[c])
    if fixed:
        font.set_cmap(new, width)
    return fixed


def has_letter(font: _Font, ch: str) -> bool:
    """Fontun harf tablosunda ya da kodlama farklarındaki glif adlarında bu harf var mı."""
    try:
        if ch in font.current()[0].values():
            return True
        return any(glyph_unicode(n) == ch for n in font.differences().values())
    except Exception:  # noqa: BLE001
        return True


# ---------------------------------------------------------------------------------------------- belge

def strip_subset(name: str) -> str:
    """«/ABCDEF+Font-Bold» → «Font-Bold» (pymupdf span'ındaki font adıyla karşılaştırmak için)."""
    return re.sub(r"^/?(?:[A-Z]{6}\+)?", "", name or "")


def font_lacks(repair: dict | None, span_font: str, key: str = "has_dotless_i") -> bool:
    """Span'ın fontu (pymupdf adı kısaltır: «IvyPrestoHeadline-SemiBo») bu harfi taşımıyor mu. Aynı adla başlayan
    bütün fontlar harfsizse evet; adı eşleşen font yoksa ya da biri harfi taşıyorsa hayır."""
    table = (repair or {}).get(key) or {}
    hits = [v for n, v in table.items() if n == span_font or (span_font and n.startswith(span_font))]
    return bool(hits) and not any(hits)


def repair_document(doc) -> dict:
    """Belgenin bütün fontlarını bellekte onarır (dosya değişmez). Aynı belgede ikinci çağrı bir şey değiştirmez.
    Dönen sözlük: onarım sayıları ve `has_dotless_i` (font adı → ı taşıyor mu; küçültülmüş «l» kuralı için)."""
    done = getattr(doc, "_editor_text_repair", None)
    if done is not None:
        return done
    stats = {"glyph_names": 0, "twin_glyphs": 0, "dotted_i": 0, "symbols": 0}
    seen: set[int] = set()
    has_i: dict[str, bool] = {}
    for pno in range(doc.page_count):
        try:
            fonts = doc.get_page_fonts(pno, full=True)
        except Exception:  # noqa: BLE001
            continue
        for f in fonts:
            xref = f[0]
            if not xref or xref in seen:
                continue
            seen.add(xref)
            try:
                font = _Font(doc, xref)
                stats["glyph_names"] += repair_by_glyph_names(font)
                tt = None
                cur, _ = font.current()
                if any(u in ("I", "ı") or (len(u) == 1 and (is_pua(u) or u in "‹›�")) for u in cur.values()):
                    data = font.cid_truetype()
                    if data:
                        try:
                            tt = _ttfont(data)
                        except Exception as e:  # noqa: BLE001 — okunamayan gömülü font: onarım yok
                            log.info("gömülü font okunamadı: %s", e)
                stats["twin_glyphs"] += repair_by_twin_glyphs(font, tt)
                stats["dotted_i"] += repair_dotted_i(font, tt)
                stats["symbols"] += repair_symbol_font(font)
                name = strip_subset(font.base)
                has_i[name] = has_i.get(name, False) or has_letter(font, "ı")
            except Exception as e:  # noqa: BLE001 — bir font okunamazsa diğerleri onarılır
                log.info("font onarımı atlandı (xref %s): %s", xref, e)
    if any(stats.values()):
        log.info("pdf metin katmanı onarıldı: %s", stats)
    out = {**stats, "has_dotless_i": has_i}
    try:
        doc._editor_text_repair = out
    except Exception:  # noqa: BLE001
        pass
    return out


# ---------------------------------------------------------------------------------------------- 5) kitabın sözlüğü

#: Fontun verisinden onarılamayan harf yerine geçen karakterler: özel alan (PUA) ve eski Mac Türkçe kodlamalı
#: fontların Latin-1 okumasında Türkçe harflerin yerine düşen işaretler (‹ İ, › ı, ¤ ğ, ⁄ Ğ). Bunlar harf sayılmaz;
#: hangi harf oldukları yalnız kitabın kendi sözlüğünden çıkarılır.
_SUBST = "‹›¤⁄"
_ODD = "-" + _SUBST
_WORD = re.compile(r"[^\W\d_]+")
_ODD_WORD = re.compile(f"(?:[^\\W\\d_]|[{_ODD}])*[{_ODD}](?:[^\\W\\d_]|[{_ODD}])*")
#: Eski «Türkçeleştirilmiş» fontların başka karakterin yerine koyduğu harfler (küçük hâlleriyle).
_TR_SPECIAL = "şğıiçöüâîû"
PUA_MIN_HITS = 2
PUA_MARGIN = 2


def _odd(ch: str) -> bool:
    return is_pua(ch) or ch in _SUBST


def tr_lower(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def tr_upper(ch: str) -> str:
    return {"i": "İ", "ı": "I"}.get(ch, ch.upper())


def private_letter_map(texts: list[str]) -> dict[str, str]:
    """Onarılamayan karakter → kitabın sözlüğünde açık farkla tutan Türkçe harf. Karakterin yerine her aday harf
    konur; oluşan kelimenin kitabın başka yerinde (bu karakterler olmadan) geçtiği kelime sayılır. Kazanan yoksa
    karakter kalır (okunamadı). Büyük/küçük hâl kitabın kendi kullanımından: karakter büyük harfli kelimelerde
    geçiyor, hiç iki küçük harf arasında geçmiyorsa büyük harftir (eski fontlarda «Ş» ve «ş» ayrı karakterlere
    düşer). Karar çıkmazsa küçük yazılır, tümü büyük harfli kelimede büyütülür."""
    tokens: dict[str, list[str]] = {}
    for t in texts:
        for w in _ODD_WORD.findall(t):
            for ch in {c for c in w if _odd(c)}:
                tokens.setdefault(ch, []).append(w)
    if not tokens:
        return {}
    vocab = Counter(tr_lower(w) for t in texts for w in _WORD.findall(t))
    chosen: dict[str, str] = {}
    for ch, words in tokens.items():
        scorable = [w for w in words if sum(_odd(c) for c in w) == 1 and len(w) >= 3]
        score = sorted(((sum(1 for w in scorable if vocab[tr_lower(w.replace(ch, cand))]), cand)
                        for cand in _TR_SPECIAL), reverse=True)
        if not (score and score[0][0] >= PUA_MIN_HITS and score[0][0] >= PUA_MARGIN * max(score[1][0], 0.5)):
            continue
        caps = lower = 0
        for w in words:
            letters = [c for c in w if c.isalpha()]
            if len(letters) >= 2 and all(c.isupper() for c in letters):
                caps += 1
            for k in (i for i, c in enumerate(w) if c == ch):
                if 0 < k < len(w) - 1 and w[k - 1].islower() and w[k + 1].islower():
                    lower += 1
        chosen[ch] = tr_upper(score[0][1]) if caps and not lower else score[0][1]
    if chosen:
        log.info("onarılamayan karakter kitabın sözlüğüyle çözüldü: %s", {hex(ord(k)): v for k, v in chosen.items()})
    return chosen


def apply_private_letters(text: str, chosen: dict[str, str]) -> str:
    if not chosen or not any(c in chosen for c in text):
        return text

    def fix(m: re.Match) -> str:
        w = m.group(0)
        letters = [c for c in w if c.isalpha()]
        caps = bool(letters) and all(c.isupper() for c in letters)
        return "".join((tr_upper(chosen[c]) if caps else chosen[c]) if c in chosen else c for c in w)
    return _ODD_WORD.sub(fix, text)


