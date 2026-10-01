"""Redaksiyon: PDF metin katmanındaki yanlış harf eşlemelerinin fontun kendi verisinden onarılması.

InDesign çıktılarında iki kusur ölçüldü (2026-09-30, «Altın Kalpli Balıkçı», «Bir Canavar Gördüm Sanki»):

1. **Süslü harf → özel alan (PUA) karakteri.** Başlık fontunun alternatif glifleri (`A.alt4`, `Idotaccent.alt2`)
   ToUnicode tablosunda U+E000…U+F8FF'e eşlenmiş; «BALIKÇI TİGİ» metne «B…K…İ…» diye giriyor. ToUnicode'u olmayan
   fontta da okuyucu bilmediği glif adını olduğu gibi yazıyor («/quoteleft.alt2»). Fontun kodlama farkları
   (`/Differences`) glifin adını taşır; Adobe Glyph List kuralıyla ad noktadan önceki kısmına indirgenir
   (`A.alt4` → `A`) ve harf oradan okunur.
2. **Noktalı büyük İ → «I».** Glif adı olmayan (CID) fontta İ glifi ToUnicode'da «I» yazılmış («FİLİN» → «FILIN»).
   Fontun kendi çizimi kanıttır: glif, gövdenin üstünde ayrı, yaklaşık yuvarlak bir işaret taşıyorsa noktalıdır
   (I → İ, ı → i). Şapka (Î) geniş olduğu için noktadan ayrılır; yalnız «I» ve «ı» eşlemesine dokunulur.

3. **Eski tip «Türkçeleştirilmiş» font** (2026-09-30, 26 kitaplık kabul seti): Ş/İ/ş harfleri başka karakterlerin
   yerine konmuş («G‹R‹» + özel alan karakteri = GİRİŞ). Aynı fontta doğru eşlenmiş ikizi varsa çizim birebir aynıdır → ikizin harfi;
   yoksa çizim «harf + altta tek parça» ise çengelli harftir (s → ş, c → ç).
4. **Simge fontu** (Wingdings, Webdings, Dingbats): madde işaretleri özel alana eşli; metinde «•» olur.
5. **Harf tablosu olmayan CID font** (ToUnicode yok, Identity kodlama): kod glif numarasıdır, harf değildir; okuyucu
   anlamsız harf üretir («在哪里» → «ࡏ䬟ཬ»). Bu metin okunamadı («�») sayılır (`no_text_mapping`).

Onarım yalnız bellekteki okuyucu nesnesinde yapılır (dosya değişmez); kitaba ya da fonta özel kural yoktur. Fontun
verisinden çıkmayan harf onarılmaz, özel alan karakteri olarak kalır ve sayılır (`unreadable_chars`).
"""
from __future__ import annotations

import io
import logging
import re
from typing import Any, Optional

log = logging.getLogger("semantic.editorial_pdf_text")

try:  # pypdf'in kendi glif listesi (Adobe Glyph List, «/A» → «A»)
    from pypdf._codecs.adobe_glyphs import adobe_glyphs as _AGL
except Exception:  # noqa: BLE001 — sürüm farkı: yalnız uniXXXX adları çözülür
    _AGL = {}


def is_pua(ch: str) -> bool:
    o = ord(ch)
    return 0xE000 <= o <= 0xF8FF or o >= 0xF0000


def unreadable(text: str) -> int:
    return sum(1 for ch in text if is_pua(ch) or ch == "\ufffd")


def glyph_unicode(name: str) -> Optional[str]:
    """Glif adından metin (AGL: noktadan sonrası atılır, «_» bağlı harf, uniXXXX / uXXXXX)."""
    base = str(name).lstrip("/").split(".", 1)[0]
    if not base:
        return None
    out = []
    for part in base.split("_"):
        u = _AGL.get("/" + part)
        if u is None:
            m = re.fullmatch(r"uni((?:[0-9A-F]{4})+)", part)
            if m:
                u = "".join(chr(int(m.group(1)[i:i + 4], 16)) for i in range(0, len(m.group(1)), 4))
            else:
                m = re.fullmatch(r"u([0-9A-F]{4,6})", part)
                u = chr(int(m.group(1), 16)) if m and int(m.group(1), 16) <= 0x10FFFF else None
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


def _set_cmap(font: Any, mapping: dict[int, str], width: int) -> None:
    from pypdf.generic import DecodedStreamObject, NameObject
    s = DecodedStreamObject()
    s.set_data(cmap_bytes(mapping, width))
    font[NameObject("/ToUnicode")] = s


def _current(font: Any) -> tuple[dict[int, str], int]:
    tu = font.get("/ToUnicode")
    if tu is None:
        return {}, 1
    try:
        return parse_cmap(tu.get_object().get_data())
    except Exception:  # noqa: BLE001 — okunamayan tablo: onarım yapılmaz
        return {}, 0


# ---------------------------------------------------------------------------------------------- 1) glif adı

def _differences(font: Any) -> dict[int, str]:
    enc = _obj(font.get("/Encoding"))
    if not hasattr(enc, "get") or enc.get("/Differences") is None:
        return {}
    names: dict[int, str] = {}
    code = 0
    for x in enc["/Differences"]:
        x = x.get_object() if hasattr(x, "get_object") else x
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            code = int(x)
        else:
            names[code] = str(x)
            code += 1
    return names


def repair_by_glyph_names(font: Any) -> int:
    """Basit fontta (Type1/TrueType) PUA'ya eşlenmiş ya da okuyucunun çözemeyeceği glif adı taşıyan kodlar."""
    names = _differences(font)
    if not names:
        return 0
    cur, width = _current(font)
    if not width:
        return 0
    new = dict(cur)
    fixed = 0
    for code, name in names.items():
        have = cur.get(code)
        if have and not any(is_pua(c) for c in have):
            continue
        if have is None and "/" + name.lstrip("/") in _AGL:
            continue                    # okuyucu bu adı kendi listesinden zaten doğru çözer
        u = glyph_unicode(name)
        if u:
            new[code] = u
            fixed += 1
    if fixed:
        _set_cmap(font, new, width)
    return fixed


# ---------------------------------------------------------------------------------------------- 2) noktalı I

#: İşaret noktadır: genişliği yüksekliğinin en çok bu katı (şapka/uzatma daha geniştir) ve gövdenin bu oranından
#: kısa; gövdenin üstünde başlar (gövde yüksekliğinin %5'i kadar örtüşmeye izin).
DOT_MAX_ASPECT = 1.6
DOT_MAX_HEIGHT = 0.35
DOT_OVERLAP = 0.05


def _boxes(glyf: Any, g: Any) -> list[tuple[float, float, float, float]]:
    """Glifin parçaları: bileşik glifte bileşen kutuları (kaydırmayla), basit glifte kontur kutuları."""
    if g.isComposite():
        out = []
        for comp in g.components:
            if not hasattr(comp, "x") or getattr(comp, "transform", None) not in (None, [[1, 0], [0, 1]]):
                return []               # nokta eşlemeli ya da ölçekli bileşen: konum güvenilir değil
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


def repair_dotted_i(font: Any) -> int:
    """CID TrueType fontta «I»/«ı» diye eşlenmiş ama çiziminde üstte nokta olan glif → «İ»/«i»."""
    if str(font.get("/Subtype")) != "/Type0" or font.get("/ToUnicode") is None:
        return 0
    try:
        desc = font["/DescendantFonts"][0].get_object()
    except Exception:  # noqa: BLE001
        return 0
    if str(desc.get("/Subtype")) != "/CIDFontType2" or str(desc.get("/CIDToGIDMap", "/Identity")) != "/Identity":
        return 0
    fd = _obj(desc.get("/FontDescriptor"))
    ff = fd.get("/FontFile2") if fd is not None else None
    if ff is None:
        return 0
    cur, width = _current(font)
    targets = {c: u for c, u in cur.items() if u in ("I", "ı")}
    if not targets or not width:
        return 0
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        log.info("fontTools kurulu değil: noktalı I onarımı atlandı")
        return 0
    try:
        tt = TTFont(io.BytesIO(ff.get_object().get_data()))
        glyf, order = tt["glyf"], tt.getGlyphOrder()
    except Exception as e:  # noqa: BLE001 — okunamayan gömülü font: onarım yok
        log.info("gömülü font okunamadı: %s", e)
        return 0
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
        _set_cmap(font, new, width)
    return fixed


# ---------------------------------------------------------------------------------------------- 3) ikiz glif

def _contours(glyf: Any, name: str) -> list[tuple[tuple[int, int], ...]]:
    """Glifin konturları (bileşik glif açılmış hâliyle), her biri nokta dizisi."""
    coords, ends, _ = glyf[name].getCoordinates(glyf)
    pts = [(int(x), int(y)) for x, y in coords]
    out, start = [], 0
    for end in ends:
        out.append(tuple(pts[start:end + 1]))
        start = end + 1
    return out


_BELOW = {"s": "ş", "S": "Ş", "c": "ç", "C": "Ç"}


def repair_by_twin_glyphs(font: Any) -> int:
    """CID TrueType font: harf olmayan (özel alan, «‹» gibi) karaktere eşli glifin çizimi, harfe eşli bir glifle
    birebir aynıysa o harftir; özel alana eşli glif «harf + temel çizginin altında tek kontur» ise çengelli harftir."""
    if str(font.get("/Subtype")) != "/Type0" or font.get("/ToUnicode") is None:
        return 0
    try:
        desc = font["/DescendantFonts"][0].get_object()
    except Exception:  # noqa: BLE001
        return 0
    if str(desc.get("/Subtype")) != "/CIDFontType2" or str(desc.get("/CIDToGIDMap", "/Identity")) != "/Identity":
        return 0
    fd = _obj(desc.get("/FontDescriptor"))
    ff = fd.get("/FontFile2") if fd is not None else None
    if ff is None:
        return 0
    cur, width = _current(font)
    odd = {c: u for c, u in cur.items() if len(u) == 1 and not u.isalpha() and (is_pua(u) or u in "‹›\ufffd")}
    if not odd or not width:
        return 0
    try:
        from fontTools.ttLib import TTFont
        tt = TTFont(io.BytesIO(ff.get_object().get_data()))
        glyf, order = tt["glyf"], tt.getGlyphOrder()
        slack = tt["head"].unitsPerEm * 0.03       # çengelin tepesi harfin tabanına biraz girebilir
    except Exception as e:  # noqa: BLE001
        log.info("ikiz glif denetimi atlandı: %s", e)
        return 0

    def shape(code: int) -> Optional[list]:
        if code >= len(order):
            return None
        try:
            c = _contours(glyf, order[code])
        except Exception:  # noqa: BLE001
            return None
        return c or None

    letters = {c: u for c, u in cur.items() if len(u) == 1 and u.isalpha()}
    by_shape: dict[tuple, str] = {}
    for c, u in letters.items():
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
        for k, extra in enumerate(sh):          # bir kontur çıkınca bir harfin çizimi kalıyor mu, çıkan altta mı
            if max(p[1] for p in extra) > slack:
                continue
            base = by_shape.get(tuple(sh[:k] + sh[k + 1:]))
            if base in _BELOW:
                new[code] = _BELOW[base]
                fixed += 1
                break
    if fixed:
        _set_cmap(font, new, width)
    return fixed


# ---------------------------------------------------------------------------------------------- 4) simge, 5) tablosuz

_SYMBOL_FONT = re.compile(r"(?i)wingding|webding|dingbat")


def repair_symbol_font(font: Any) -> int:
    """Simge fontunun özel alana eşli karakterleri madde işaretidir: «•»."""
    if not _SYMBOL_FONT.search(str(font.get("/BaseFont") or "")):
        return 0
    cur, width = _current(font)
    if not width:
        return 0
    new = {c: ("•" if any(is_pua(ch) for ch in u) else u) for c, u in cur.items()}
    fixed = sum(1 for c in cur if new[c] != cur[c])
    if fixed:
        _set_cmap(font, new, width)
    return fixed


def lacks_letter(font: Any, ch: str) -> bool:
    """Fontun harf tablosunda ya da kodlama farklarındaki glif adlarında bu harf yok mu."""
    try:
        cur, _ = _current(font)
        if ch in cur.values():
            return False
        return not any(glyph_unicode(n) == ch for n in _differences(font).values())
    except Exception:  # noqa: BLE001
        return False


def no_text_mapping(font: Any) -> bool:
    """Type0 font, Identity kodlama, ToUnicode yok: kodlar glif numarasıdır, metin çıkarılamaz."""
    try:
        return (str(font.get("/Subtype")) == "/Type0" and font.get("/ToUnicode") is None
                and str(font.get("/Encoding")) in ("/Identity-H", "/Identity-V"))
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------------------------- okuyucu

def _obj(x: Any) -> Any:
    return x.get_object() if x is not None and hasattr(x, "get_object") else x


def _fonts(res: Any, seen: set):
    """Kaynak sözlüğündeki fontlar; form nesnelerinin (XObject) içindekiler de."""
    if res is None:
        return
    res = res.get_object()
    for ref in (_obj(res.get("/Font")) or {}).values():
        key = getattr(ref, "idnum", None)
        font = ref.get_object()
        key = key if key is not None else id(font)
        if key not in seen:
            seen.add(key)
            yield font
    for ref in (_obj(res.get("/XObject")) or {}).values():
        key = getattr(ref, "idnum", None)
        xo = ref.get_object()
        if key is not None and ("x", key) in seen:
            continue
        seen.add(("x", key) if key is not None else id(xo))
        if str(xo.get("/Subtype")) == "/Form":
            yield from _fonts(xo.get("/Resources"), seen)


def repair_reader(reader: Any) -> dict[str, int]:
    """Okuyucunun bütün fontlarını yerinde onarır. Aynı okuyucuda ikinci çağrı bir şey değiştirmez."""
    if getattr(reader, "_zeki_text_repaired", None) is not None:
        return reader._zeki_text_repaired
    stats = {"glyph_names": 0, "dotted_i": 0, "twin_glyphs": 0, "symbols": 0}
    seen: set = set()
    for page in reader.pages:
        try:
            for font in _fonts(page.get("/Resources"), seen):
                stats["glyph_names"] += repair_by_glyph_names(font)
                stats["twin_glyphs"] += repair_by_twin_glyphs(font)
                stats["dotted_i"] += repair_dotted_i(font)
                stats["symbols"] += repair_symbol_font(font)
        except Exception as e:  # noqa: BLE001 — bir sayfanın fontu okunamazsa diğerleri onarılır
            log.info("font onarımı atlandı: %s", e)
    if any(stats.values()):
        log.info("pdf metin katmanı onarıldı: %s", stats)
    reader._zeki_text_repaired = stats
    return stats
