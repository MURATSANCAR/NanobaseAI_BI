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

MIN_TABLE_LINES = 6             # 2×2 ızgaranın en az çizgisi (3 yatay + 3 dikey)
NOTE_START = re.compile(r"^(\d{1,3})(?:[.)]?\s+)(\S.*)$")       # «18 Gregory…», «18. Gregory…»; «22.11.2015» değil
DIGITS = re.compile(r"^\d{1,4}$")
#: Görsel/tablo başlığı («Grafik 23: …», «Tablo 1: …»): kısa satırlı ama şiir değil.
CAPTION = re.compile(r"^(grafik|tablo|şekil|sekil|harita|resim|görsel|figure|fig\.|table|chart|map)\s*\d", re.I)


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
    body_folds: list[str] = field(default_factory=list)      # gövde satırlarının anahtarı (bir kez hesaplanır)
    body_key: str = ""
    refs: list[str] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    table_y: list[float] = field(default_factory=list)       # tabloların üst kenarı (sayfadaki yeri)
    table_key: str = ""
    perde: bool = False
    breaks: list[float] = field(default_factory=list)       # ara işaretinin (süs) sayfadaki yeri


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
    pg = Page()
    boxes = []
    try:                                    # tablo çizgisiz olmaz: çizgisi az sayfada aranmaz (530 sayfada 230 → birkaç sn)
        found = page.find_tables().tables if len(page.get_drawings()) >= MIN_TABLE_LINES else []
        for t in found:
            rows = [[re.sub(r"\s+", " ", (c or "").replace("\xad\n", "").replace("\xad", "")).strip() for c in r]
                    for r in t.extract()]
            if t.row_count >= 2 and t.col_count >= 2:
                pg.tables.append(rows)
                pg.table_y.append(t.bbox[1])
                boxes.append(t.bbox)
    except Exception:  # noqa: BLE001 - tablo bulunamazsa sayfa düz metin kalır
        pass
    pg.table_key = "".join(fold(c) for t in pg.tables for r in t for c in r)
    # Tablonun satırları ne gövde ne dipnottur (küçük puntolu tablo gövdenin altında kalır, dipnot sanılmamalı).
    lines = [ln for ln in lines_of(page) if not any(b[0] - 1 <= (ln.x0 + ln.x1) / 2 <= b[2] + 1 and
                                                   b[1] - 1 <= (ln.y0 + ln.y1) / 2 <= b[3] + 1 for b in boxes)]
    is_body = [abs(ln.size - body) <= max(0.8, body * 0.08) for ln in lines]
    body_idx = [i for i, b in enumerate(is_body) if b]
    big = [ln for ln in lines if ln.size >= body * 1.3]
    if big and len(lines) <= 6 and sum(len(lines[i].text) for i in body_idx) <= 120 and not pg.tables:
        pg.perde = True                       # bölüm perdesi: büyük başlık + en çok kısa bir alt satır
        pg.heads = {fold(ln.text) for ln in lines if DIGITS.match(ln.text)}
        return pg
    if not body_idx:
        big = [ln for ln in lines if ln.size >= body * 1.3]
        pg.perde = bool(big) and len(lines) <= 6 and not pg.tables and all(ln.size >= body * 0.95 or DIGITS.match(ln.text) for ln in lines)
        pg.heads = {fold(ln.text) for ln in lines if DIGITS.match(ln.text)}
        return pg
    top, bottom = lines[body_idx[0]].y0, lines[body_idx[-1]].y1
    for i, ln in enumerate(lines):
        small = ln.size < body * 0.92
        if small and ln.y0 >= bottom - 1:
            continue
        if DIGITS.match(ln.text) or (small and ln.y1 <= top + 1):
            pg.heads.add(fold(ln.text))
        elif is_body[i] or ln.size >= body * 0.92:
            pg.body.append(ln)
            pg.refs += ln.sup
    below = _same_baseline([ln for ln in lines if ln.size < body * 0.92 and ln.y0 >= bottom - 1])
    folio = below[-1] if below and DIGITS.match(below[-1].text) else None     # sayfa numarası: en alttaki tek sayı
    for ln in below:
        if ln is folio:
            pg.heads.add(fold(ln.text))
            continue
        m = NOTE_START.match(ln.text)
        last = next((int(n) for n, _ in reversed(pg.notes) if n is not None), None)
        # not numarası sırayla artar; sayfanın ilk notu sayfadaki bir gönderme numarasıdır (devam satırındaki
        # «12 Ocak 1999» yeni not sayılmaz)
        n = int(m.group(1)) if m else 0
        if m and ((n == last + 1 or (last < n <= last + 3 and m.group(1) in pg.refs)) if last is not None
                  else (not pg.refs or m.group(1) in pg.refs)):           # basılıda atlanmış numara (71 yok, 72 var)
            pg.notes.append([m.group(1), m.group(2)])
        elif pg.notes:
            pg.notes[-1][1] = _join(pg.notes[-1][1], ln.text)
        else:
            pg.notes.append([None, ln.text])
    pg.note_key = "".join(fold(t) for _, t in pg.notes)
    # Ara işareti: gövdede iki satır arasında olağandan büyük boşluk ve boşlukta süs (çizim ya da resim). Okunmuş
    # metinde izi yoktur; sahne geçişi kaybolmasın.
    try:
        marks = [fitz_rect for fitz_rect in _ornaments(page)]
        for a, b in zip(pg.body, pg.body[1:]):
            gap = b.y0 - a.y1
            if gap > 1.5 * (a.y1 - a.y0) and any(a.y1 - 1 <= (r[1] + r[3]) / 2 <= b.y0 + 1 for r in marks):
                pg.breaks.append((a.y1 + b.y0) / 2)
        if pg.body:                                   # sayfanın başında ya da sonunda (son satırın altında) duran süs
            first, last = pg.body[0], pg.body[-1]
            for r in marks:
                cy = (r[1] + r[3]) / 2
                if (top - 3 * (first.y1 - first.y0) <= cy < first.y0 - 1) or (last.y1 + 1 < cy <= last.y1 + 3 * (last.y1 - last.y0)):
                    pg.breaks.append(cy)
    except Exception:  # noqa: BLE001
        pass
    pg.body_folds = [fold(ln.text) for ln in pg.body]
    pg.body_key = "".join(pg.body_folds)
    return pg


def _ornaments(page) -> list[tuple]:
    """Sayfadaki küçük süsler: çizim kümeleri ve resimler (en çok sütunun yarısı genişliğinde, 60 pt yüksekliğinde)."""
    out = []
    for r in page.cluster_drawings() if hasattr(page, "cluster_drawings") else []:
        if r.width <= page.rect.width / 2 and r.height <= 60:
            out.append((r.x0, r.y0, r.x1, r.y1))
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        if (x1 - x0) <= page.rect.width / 2 and (y1 - y0) <= 60:
            out.append((x0, y0, x1, y1))
    return out


def _same_baseline(lines: list[Line]) -> list[Line]:
    """Aynı satır çizgisindeki parçalar tek satır (dipnot numarası ile metni ayrı parça dizilmiş olabilir)."""
    out: list[Line] = []
    for ln in sorted(lines, key=lambda x: (round(x.y0), x.x0)):
        if out and abs(out[-1].y0 - ln.y0) <= 1.5 and ln.x0 >= out[-1].x1 - 1:
            prev = out[-1]
            out[-1] = Line(f"{prev.text} {ln.text}", prev.x0, ln.x1, prev.y0, max(prev.y1, ln.y1), prev.size,
                           min(prev.italic, ln.italic), prev.sup + ln.sup)
        else:
            out.append(ln)
    return out


def _join(a: str, b: str) -> str:
    """Notun satırları: satır sonu tirelemesi (yumuşak tire ya da küçük harfler arasında tire) birleşir."""
    a = a.rstrip()
    if a.endswith("\xad"):
        return a[:-1] + b
    if re.search(r"[a-zçğıöşü][-\u2010]$", a) and b[:1].islower():
        return a[:-1] + b
    if re.search(r"https?://\S*$|www\.\S*$", a) and (a.endswith(("/", ".", "-", "=", "&", "?", "_")) or
                                                    not re.match(r"[A-ZÇĞİÖŞÜ(“\"]", b)):
        return a + b                                  # satır sonunda bölünmüş bağlantı adresi
    return f"{a} {b}"


def para_lines(pg: Page, text: str) -> list[Line]:
    """Okunmuş paragrafın dizgideki satırları: anahtarı paragrafın anahtarıyla başlayan ilk satırdan, paragraf bitene
    dek ardışık satırlar."""
    key = fold(text)
    if len(key) < 4:                                  # kısa paragraf («II»): yalnız aynı satırla eşleşir
        return [ln for k, ln in zip(pg.body_folds, pg.body) if k == key][:1] if key else []
    if key[:12] not in pg.body_key:
        return []
    body, folds = pg.body, pg.body_folds
    for i, ln in enumerate(body):
        k = folds[i]
        if not k or not key.startswith(k[: min(len(k), 20)]):
            continue
        got, out = "", []
        for j, ln2 in enumerate(body[i:], i):
            k2 = folds[j]
            if not key.startswith(got + k2[: max(1, len(k2) - 2)]):
                break
            got += k2
            out.append(ln2)
            if len(got) >= len(key) - 2:
                return out
        if out and len(got) >= 0.9 * len(key):
            return out
    return []


def kind_of(lines: list[Line], left: float, right: float, body: float = 0.0) -> tuple[str, str | None]:
    """(tür, şiirde satır sonlu metin). tür: para | subhead | poem | italic | right. Alt başlık: tek, ortalı, gövdeden
    belirgin büyük puntolu kısa satır («II»). Şiir: en az 2 satır, satırların dörtte üçü
    sütunun %80'inden kısa, hepsi aynı soldan başlar (iki sütunlu kısaltma listesi, ortalı grafik başlığı değil),
    gövde puntosunda (bölüm başlığı değil), tireyle bölünmemiş; sağa yaslı satırlar şiir sayılmaz (imza, kaynak)."""
    if len(lines) < 1:
        return "para", None
    width = max(1.0, right - left)
    italic = sum(1 for ln in lines if ln.italic >= 0.6) / len(lines)
    right_al = sum(1 for ln in lines if ln.x1 >= right - 6 and ln.x0 >= left + width * 0.25) / len(lines)
    short = sum(1 for ln in lines if (ln.x1 - ln.x0) < width * 0.8) / len(lines)
    hyph = any(re.search(r"\w[-\xad]$", ln.text) for ln in lines[:-1])
    same_left = max(ln.x0 for ln in lines) - min(ln.x0 for ln in lines) <= 4
    body_size = not body or all(ln.size <= body * 1.08 for ln in lines)
    mid = (left + right) / 2
    if (len(lines) == 1 and body and lines[0].size >= body * 1.12 and len(lines[0].text) <= 80
            and abs((lines[0].x0 + lines[0].x1) / 2 - mid) <= 12):
        return "subhead", None
    if right_al >= 0.6:
        return "right", None
    caption = bool(CAPTION.match(lines[0].text))
    if len(lines) >= 2 and short >= 0.75 and not hyph and same_left and body_size and not caption:
        return "poem", "\n".join(ln.text for ln in lines)
    if italic >= 0.6:
        return "italic", None
    return "para", None


def analyze(doc) -> dict[int, Page]:
    body, left, right = measure(doc)
    pages = {i: page_parts(p, body, left, right) for i, p in enumerate(doc, 1)}
    # Sayfa altı künyesi («nurullah genç · her şey yanıp gül oldu 11»): kitabın birçok sayfasında aynen tekrarlanan
    # küçük puntolu alt satır dipnot değildir (rakamsız anahtarı en az 5 sayfada ve sayfaların %10'unda geçer).
    seen = collections.Counter(fold(t) for pg in pages.values() for t in {t for _, t in pg.notes})
    footer = {k for k, n in seen.items() if k and n >= max(5, len(pages) // 10)}
    for pg in pages.values():
        if any(fold(t) in footer for _, t in pg.notes):
            pg.heads |= {fold(t) for _, t in pg.notes if fold(t) in footer}
            pg.notes = [[n, t] for n, t in pg.notes if fold(t) not in footer]
            pg.note_key = "".join(fold(t) for _, t in pg.notes)
    for pg in pages.values():
        pg.left, pg.right, pg.size = left, right, body     # type: ignore[attr-defined]
    return pages
