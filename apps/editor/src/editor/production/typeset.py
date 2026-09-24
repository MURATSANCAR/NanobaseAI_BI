"""Dizgi: Manuscript + Spec → iç sayfa PDF'i (Typst, templates/book.typ).

İki geçiş:
1. Yer tutucu resimlerle derle, her bloğun başladığı/bittiği sayfayı sorgula (`metadata`). Sayfa
   sayısını forma katına oturtmak için punto (yaş kuralının bir alt basamağına kadar) ve resim bandı
   oranı (spec aralığında) taranır; kalan boşluk bölüm aralarına tam sayfa resimle doldurulur.
   Seçim sırası: en az sayfa → en büyük resim bandı → en büyük punto → en az tam sayfa.
2. Resimler geldikten sonra aynı yerleşimle yeniden derle (resim metnin akışını değiştirmez).

Sayfa haritası (`PageMap`) her sayfanın türünü ve metnini verir; resim tarifleri buradan yazılır.
"""

from __future__ import annotations

import json
import math
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .manuscript import Manuscript
from .spec import Spec

TEMPLATE = Path(__file__).resolve().parent / "templates" / "book.typ"
FRONT_PAGES = 4                         # iç kapak, künye, yazar/çizer, açılış resmi (ya da boş)
SOUND = re.compile(r"(\w)\1\1")          # «Güüüümmm», «Roooaaah»: aynı harf 3+ kez


@dataclass
class Layout:
    art_ratio: float
    body_size: float
    accent: str
    pads: dict = field(default_factory=dict)          # {bölüm sırası|"end": dolgu sayfası adedi}
    opening_full: bool = True
    chapter_art: bool = False     # her bölümün önünde tam sayfa resim (bölüm başı resimli kitap)
    pad_blank: bool = False       # dolgu sayfaları boş (resimsiz/bölüm başı resimli kitapta sonda)


@dataclass
class Page:
    no: int
    kind: str                     # front | flow | full
    key: str | None = None        # ön sayfa anahtarı / tam sayfa anahtarı
    chapter: int | None = None
    blocks: list[str] = field(default_factory=list)   # bu sayfada görünen blok kimlikleri
    text: str = ""


@dataclass
class PageMap:
    pages: list[Page]
    layout: Layout

    def art_pages(self) -> set[int]:
        """Resmin gerçekten basıldığı sayfalar: tam sayfa resimler ve (bant varsa) metin sayfaları."""
        band = self.layout.art_ratio > 0
        return {p.no for p in self.pages if p.kind == "full" or (band and p.kind == "flow" and p.text)}

    def to_json(self) -> dict:
        return {"layout": asdict(self.layout), "pages": [asdict(p) for p in self.pages]}


def block_kind(kind: str, text: str) -> str:
    if kind == "para" and len(text.split()) <= 3 and SOUND.search(text.casefold()):
        return "sound"
    return kind


def book_data(ms: Manuscript, spec: Spec, layout: Layout, front: dict, art: dict[int, str]) -> dict:
    return {
        "book": {"title": ms.title, "author": ms.author or "", "publisher": ms.meta.get("PUBLISHER") or ""},
        "spec": asdict(spec), "layout": asdict(layout), "front": front,
        "art": {str(k): v for k, v in art.items()},
        "chapters": [{"title": c.title, "blocks": [
            {"id": f"c{ci}b{bi}", "kind": block_kind(b.kind, b.text), "text": b.text}
            for bi, b in enumerate(c.blocks)]} for ci, c in enumerate(ms.chapters)],
    }


class Typesetter:
    def __init__(self, workdir: Path, font_dir: Path):
        self.dir = Path(workdir)
        self.dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(TEMPLATE, self.dir / "book.typ")
        self.fonts = [str(font_dir)]

    def _write(self, data: dict, name: str) -> str:
        (self.dir / name).write_text(json.dumps(data, ensure_ascii=False))
        return name

    def marks(self, data: dict) -> list[dict]:
        import typst
        name = self._write(data, "data.json")
        out = typst.query(str(self.dir / "book.typ"), "metadata", root=str(self.dir),
                          font_paths=self.fonts, ignore_system_fonts=True, sys_inputs={"data": name})
        return [m["value"] for m in json.loads(out) if isinstance(m.get("value"), dict) and "kind" in m["value"]]

    def compile(self, data: dict, pdf: str) -> Path:
        import typst
        name = self._write(data, "data.json")
        path = self.dir / pdf
        typst.compile(str(self.dir / "book.typ"), output=str(path), root=str(self.dir),
                      font_paths=self.fonts, ignore_system_fonts=True, sys_inputs={"data": name})
        return path

    def page_map(self, ms: Manuscript, data: dict, layout: Layout) -> PageMap:
        marks = self.marks(data)
        total = max(m["page"] for m in marks)
        pages = {n: Page(n, "flow") for n in range(1, total + 1)}
        texts = {f"c{ci}b{bi}": b.text for ci, bi, b in ms.blocks()}
        start: dict[str, int] = {}
        chapter_at = 0
        for m in sorted(marks, key=lambda m: m["page"]):
            p = pages[m["page"]]
            if m["kind"] in ("front", "full"):
                p.kind, p.key = m["kind"], m["key"]
            elif m["kind"] == "chapter":
                chapter_at = m["ci"]
                p.chapter = chapter_at
            elif m["kind"] == "s":
                start[m["id"]] = m["page"]
            elif m["kind"] == "e":
                for n in range(start.get(m["id"], m["page"]), m["page"] + 1):
                    if m["id"] not in pages[n].blocks:
                        pages[n].blocks.append(m["id"])
                        pages[n].chapter = int(m["id"][1:].split("b")[0])
        for p in pages.values():
            p.text = "\n".join(texts[i] for i in p.blocks)
        return PageMap([pages[n] for n in sorted(pages)], layout)

    def fit(self, ms: Manuscript, spec: Spec, front: dict, accent: str) -> PageMap:
        """Forma katına oturan en iyi yerleşim (modül belgesindeki sıra)."""
        lo, hi = spec.art_ratio
        ratios = [round(hi - i * 0.04, 2) for i in range(int(round((hi - lo) / 0.04)) + 1)] if hi else [0.0]
        sizes = [spec.body_size, spec.body_size - 1]
        # Resim türüne göre: her sayfada → üst bant + dolgu bölüm arasına tam sayfa resim; bölüm başında →
        # açılış ve her bölümün önünde tam sayfa resim, dolgu sonda boş; resimsiz → dolgu sonda boş.
        chapter_art = spec.illustration == "BOLUM_BASI"
        opening = spec.illustration != "YOK"
        tried = []
        for size in sizes:
            for r in ratios:
                lay = Layout(art_ratio=r, body_size=size, accent=accent, opening_full=opening,
                             chapter_art=chapter_art, pad_blank=not hi)
                marks = self.marks(book_data(ms, spec, lay, front, {}))
                pages = max(m["page"] for m in marks)
                target = math.ceil(pages / spec.signature) * spec.signature
                tried.append((target, -r, -size, target - pages, lay))
        target, _, _, pad, lay = min(tried, key=lambda t: t[:4])
        lay.pads = ({"end": pad} if lay.pad_blank else self._spread_pads(ms, pad)) if pad else {}
        data = book_data(ms, spec, lay, front, {})
        pm = self.page_map(ms, data, lay)
        if len(pm.pages) % spec.signature:
            raise RuntimeError(f"forma katına oturmadı: {len(pm.pages)} sayfa (hedef {target})")
        return pm

    @staticmethod
    def _spread_pads(ms: Manuscript, pad: int) -> dict:
        """Tam sayfa resimler bölüm aralarına, en uzun bölümlerin önüne; bölümden fazlası sona."""
        order = sorted(range(1, len(ms.chapters)), key=lambda i: -sum(len(b.text) for b in ms.chapters[i].blocks))
        pads: dict = {}
        for i in range(pad):
            key = str(order[i]) if i < len(order) else "end"
            pads[key] = pads.get(key, 0) + 1
        return pads
