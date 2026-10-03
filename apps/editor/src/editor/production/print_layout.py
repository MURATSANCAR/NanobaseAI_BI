"""Basılı kitabın dizgisinden metnin biçimi: okunmuş paragrafların taşımadığı bilgiyi basılı PDF'ten okur.

Okuma metni paragraf paragraf verir; dipnot, sayfa üst başlığı, sayfa numarası gövdeyle aynı akışa girer, italik /
hizalama / satır sonu kaybolur. Basılı kitabın e-kitabında (`epub_source`, «basılı» kaynak) bunlar dizgiden ayrılır.
Kurallar kitaptan bağımsızdır, ölçüler sayfanın kendi gövde puntosuna ve sütun genişliğine göredir:

- **Gövde puntosu**: kitapta en çok harf taşıyan punto; **sütun**: o puntodaki satırların sol/sağ kenarı.
- **Üst başlık / sayfa numarası**: gövdenin ilk satırından yukarıda ve gövdeden küçük puntolu satırlar; yalnız
  rakamdan oluşan satır sayfa numarasıdır.
- **Dipnot bölgesi**: gövdenin son satırından aşağıda, gövdeden küçük puntolu satırlar. Rakamla başlayan satır yeni
  not, öteki satır önceki notun devamıdır (sayfanın ilk satırı numarasızsa önceki sayfanın son notunun devamı).
- **Gönderme numarası**: gövde satırında üst simge (PDF yazı bayrağı) olarak dizilmiş rakam.
- **Tablo**: sayfadaki çizgili ızgara (en az 2 satır × 2 sütun).
- **Perde sayfası**: gövde puntosunda satırı olmayan, satırları gövdeden büyük, en çok 6 satırlı sayfa.
- **Paragraf biçimi** (paragrafın satırları dizgiden bulunur): en az 2 satırın dörtte üçü sütunun %80'inden kısa ve
  satırlar tireyle bölünmemişse şiir (satır sonları korunur); satırlarının %60'ı italikse italik, sağa yaslıysa
  sağdan; bölüm başındaki italik ya da sağa yaslı paragraflar epigraf (`manuscript` bölümleri kurulunca karar verir).
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field

NOTE_START = re.compile(r"^(\d{1,3})[\s.)]+(\S.*)$")
DIGITS = re.compile(r"^\d{1,4}$")


@dataclass
class Line:
    text: str
    x0: float
    x1: float
    y0: float
    y1: float
    size: float
    italic: float                   # italik harflerin payı
    sup: list[str]                  # üst simge rakamları (gönderme numaraları)


@dataclass
class Page:
    heads: set[str] = field(default_factory=set)            # üst başlık ve sayfa numarası (karşılaştırma anahtarı)
    notes: list[list] = field(default_factory=list)         # [[numara, metin]]; numara None = önceki notun devamı
    note_key: str = ""                                      # dipnot bölgesinin anahtarı (okunmuş paragrafı tanımak için)
    body: list[Line] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    table_key: str = ""
    perde: bool = False


def fold(t: str) -> str:
    from .manuscript import _fold
    return re.sub(r"\s+", "", _fold(t))


def lines_of(page) -> list[Line]:
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            sp = [s for s in ln["spans"] if s["text"].strip()]
            if not sp:
                continue
            text = "".join(s["text"] for s in ln["spans"]).replace("\t", " ").strip()
            n = sum(len(s["text"]) for s in sp) or 1
            size = max(sp, key=lambda s: len(s["text"]))["size"]
            out.append(Line(text, ln["bbox"][0], ln["bbox"][2], ln["bbox"][1], ln["bbox"][3], size,
                            sum(len(s["text"]) for s in sp if s["flags"] & 2) / n,
                            [s["text"].strip() for s in sp if s["flags"] & 1 and s["text"].strip().isdigit()]))
    return sorted(out, key=lambda x: (round(x.y0), x.x0))


def measure(doc) -> tuple[float, float, float]:
    """(gövde puntosu, sütun solu, sütun sağı)."""
    sizes: collections.Counter = collections.Counter()
    for pg in doc:
        for ln in lines_of(pg):
            sizes[round(ln.size * 2) / 2] += len(ln.text)
    body = sizes.most_common(1)[0][0] if sizes else 11.0
    xs0, xs1 = [], []
    for pg in doc:
        for ln in lines_of(pg):
            if abs(ln.size - body) <= 0.6 and len(ln.text) > 30:
                xs0.append(ln.x0)
                xs1.append(ln.x1)
    xs0.sort()
    xs1.sort()
    return body, (xs0[len(xs0) // 10] if xs0 else 0.0), (xs1[len(xs1) * 9 // 10] if xs1 else 1e9)


def page_parts(page, body: float, left: float, right: float) -> Page:
    lines = lines_of(page)
    pg = Page()
    is_body = [abs(ln.size - body) <= max(0.8, body * 0.08) for ln in lines]
    body_idx = [i for i, b in enumerate(is_body) if b]
    if not body_idx:
        big = [ln for ln in lines if ln.size >= body * 1.3]
        pg.perde = bool(big) and len(lines) <= 6 and all(ln.size >= body * 0.95 or DIGITS.match(ln.text) for ln in lines)
        pg.heads = {fold(ln.text) for ln in lines if DIGITS.match(ln.text)}
        return pg
    top, bottom = lines[body_idx[0]].y0, lines[body_idx[-1]].y1
    for i, ln in enumerate(lines):
        small = ln.size < body * 0.92
        if DIGITS.match(ln.text) or (small and ln.y1 <= top + 1):
            pg.heads.add(fold(ln.text))
        elif small and ln.y0 >= bottom - 1:
            m = NOTE_START.match(ln.text)
            if m:
                pg.notes.append([m.group(1), m.group(2)])
            elif pg.notes:
                pg.notes[-1][1] = _join(pg.notes[-1][1], ln.text)
            else:
                pg.notes.append([None, ln.text])
        elif is_body[i] or ln.size >= body * 0.92:
            pg.body.append(ln)
            pg.refs += ln.sup
    pg.note_key = "".join(fold(t) for _, t in pg.notes)
    try:
        for t in page.find_tables().tables:
            rows = [[re.sub(r"\s+", " ", (c or "").replace("\xad", "")).strip() for c in r] for r in t.extract()]
            if t.row_count >= 2 and t.col_count >= 2:
                pg.tables.append(rows)
    except Exception:  # noqa: BLE001 - tablo bulunamazsa sayfa düz metin kalır
        pass
    pg.table_key = "".join(fold(c) for t in pg.tables for r in t for c in r)
    return pg


def _join(a: str, b: str) -> str:
    """Notun satırları: satır sonu tirelemesi (yumuşak tire ya da küçük harfler arasında tire) birleşir."""
    a = a.rstrip()
    if a.endswith("\xad"):
        return a[:-1] + b
    if re.search(r"[a-zçğıöşü]-$", a) and b[:1].islower():
        return a[:-1] + b
    return f"{a} {b}"


def para_lines(body: list[Line], text: str) -> list[Line]:
    """Okunmuş paragrafın dizgideki satırları: anahtarı paragrafın anahtarıyla başlayan ilk satırdan, paragraf bitene
    dek ardışık satırlar."""
    key = fold(text)
    if len(key) < 4:
        return []
    for i, ln in enumerate(body):
        k = fold(ln.text)
        if not k or not key.startswith(k[: min(len(k), 20)]):
            continue
        got, out = "", []
        for ln2 in body[i:]:
            k2 = fold(ln2.text)
            if not key.startswith(got + k2[: max(1, len(k2) - 2)]):
                break
            got += k2
            out.append(ln2)
            if len(got) >= len(key) - 2:
                return out
        if out and len(got) >= 0.9 * len(key):
            return out
    return []


def kind_of(lines: list[Line], left: float, right: float) -> tuple[str, str | None]:
    """(tür, şiirde satır sonlu metin). tür: para | poem | italic | right."""
    if len(lines) < 1:
        return "para", None
    width = max(1.0, right - left)
    italic = sum(1 for ln in lines if ln.italic >= 0.6) / len(lines)
    right_al = sum(1 for ln in lines if ln.x1 >= right - 6 and ln.x0 >= left + width * 0.25) / len(lines)
    short = sum(1 for ln in lines if (ln.x1 - ln.x0) < width * 0.8) / len(lines)
    hyph = any(re.search(r"\w-$", ln.text) for ln in lines[:-1])
    if len(lines) >= 2 and short >= 0.75 and not hyph:
        return "poem", "\n".join(ln.text for ln in lines)
    if right_al >= 0.6:
        return "right", None
    if italic >= 0.6:
        return "italic", None
    return "para", None


def analyze(doc) -> dict[int, Page]:
    body, left, right = measure(doc)
    pages = {i: page_parts(p, body, left, right) for i, p in enumerate(doc, 1)}
    for pg in pages.values():
        pg.left, pg.right = left, right            # type: ignore[attr-defined]
    return pages
