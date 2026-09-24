"""Sanat yönetimi: üslup rehberi, karakter kartları, sayfa sahneleri (ana model).

Her karar kitaptan gelir ve alıntıyla bağlanır: karakter görünüşünde metinden gelen ayrıntının alıntısı,
sayfa sahnesinde o sayfanın cümlesi metinde birebir aranır; alıntısı bulunmayan sahne tarifi yeniden
istenir, ikinci denemede de tutmazsa sayfanın kendi metninin ilk cümlesiyle sade tarife düşer.
Karakter görünüşü okuma sırasında özgün resimlerden çıkarılan betimlemelerden ALINMAZ: tasarım
sıfırdandır, yalnız metin bağlayıcıdır.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import asdict, dataclass, field

from ..prompts import render
from .manuscript import Manuscript
from .profile import Profile
from .typeset import PageMap

HEX = {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$"}
STYLE_SCHEMA = {"type": "object", "additionalProperties": False,
                "required": ["medium", "line", "lighting", "mood", "palette", "accent", "style_prompt", "avoid", "why"],
                "properties": {"medium": {"type": "string"}, "line": {"type": "string"},
                               "lighting": {"type": "string"}, "mood": {"type": "string"},
                               "palette": {"type": "array", "items": HEX, "minItems": 5, "maxItems": 5},
                               "accent": HEX, "style_prompt": {"type": "string"},
                               "avoid": {"type": "string"}, "why": {"type": "string"}}}
CHAR_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["characters"], "properties": {
    "characters": {"type": "array", "maxItems": 8, "items": {
        "type": "object", "additionalProperties": False,
        "required": ["name", "species", "look", "from_text", "role"],
        "properties": {"name": {"type": "string"}, "species": {"type": "string"}, "look": {"type": "string"},
                       "from_text": {"type": "array", "items": {"type": "string"}},
                       "role": {"type": "string", "enum": ["ANA", "YAN"]}}}}}}
PAGE_SCHEMA = {"type": "object", "additionalProperties": False,
               "required": ["moment", "quote", "characters", "scene", "setting"],
               "properties": {"moment": {"type": "string"}, "quote": {"type": "string"},
                              "characters": {"type": "array", "items": {"type": "string"}},
                              "scene": {"type": "string"}, "setting": {"type": "string"}}}


@dataclass
class Style:
    medium: str
    line: str
    lighting: str
    mood: str
    palette: list[str]
    accent: str
    style_prompt: str
    avoid: str
    why: str


@dataclass
class Character:
    name: str
    species: str
    look: str
    from_text: list[str]
    role: str


@dataclass
class Scene:
    page: int
    kind: str                     # flow | full
    moment: str
    quote: str
    characters: list[str]
    scene: str
    setting: str
    grounded: bool                # alıntı sayfa metninde birebir bulundu


@dataclass
class ArtPlan:
    style: Style
    characters: list[Character]
    scenes: list[Scene] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("“", "\"").replace("”", "\"")).strip().casefold()


def _age(p: Profile) -> str:
    return f"{p.age_min}-{p.age_max}"


async def style(ms: Manuscript, p: Profile, llm) -> Style:
    excerpt = "\n\n".join(b.text for b in ms.chapters[0].blocks)[:3000]
    ref, prompt = render("production_style", title=ms.title, age=_age(p), genre=p.genre,
                         tone=", ".join(p.tone), summary=ms.meta.get("CRM_SUMMARY") or "(yok)", excerpt=excerpt)
    out, _ = await llm.chat("book-director", [{"role": "user", "content": prompt}], prompt=ref,
                            schema=STYLE_SCHEMA, max_tokens=2000, thinking=False, temperature=0.4)
    if "text" not in out["avoid"].lower():
        out["avoid"] = "text, letters, words, " + out["avoid"]
    return Style(**out)


def _analysis_characters(ms: Manuscript) -> str:
    """Okumanın bulduğu karakterler (ad, tür, metinden betimleme); görünüş alanı özgün resimden
    geldiği için gönderilmez."""
    gid = ms.source.get("generation_id")
    if not gid:
        return "(analiz yok)"
    from .. import db
    rows = db.all_rows("SELECT canonical_name, kind, description FROM ed.character WHERE generation_id=%s "
                       "AND identity_status<>'REJECTED' ORDER BY first_page NULLS LAST", gid)
    return "\n".join(f"- {r['canonical_name']} ({r['kind']}): {r['description'] or ''}" for r in rows) or "(yok)"


async def characters(ms: Manuscript, p: Profile, st: Style, llm) -> list[Character]:
    ref, prompt = render("production_characters", title=ms.title, age=_age(p), style=st.style_prompt,
                         characters=_analysis_characters(ms), text=ms.text()[:60000])
    out, _ = await llm.chat("book-director", [{"role": "user", "content": prompt}], prompt=ref,
                            schema=CHAR_SCHEMA, max_tokens=4000, thinking=False)
    full = _norm(ms.text())
    chars = []
    for c in out["characters"]:
        if _norm(c["name"]) not in full:                   # metinde geçmeyen ad: kitap dışı kişi
            continue
        c["from_text"] = [q for q in c["from_text"] if _norm(q) in full]
        chars.append(Character(**c))
    return chars


def _char_lines(chars: list[Character]) -> str:
    return "\n".join(f"- {c.name}: {c.species}; {c.look}" for c in chars)


async def _scene(ms, p, chars, llm, page_no, kind, before, text, after, placement) -> Scene:
    ref, prompt = render("production_page_art", title=ms.title, age=_age(p), characters=_char_lines(chars),
                         before=before or "(yok)", page_text=text, after=after or "(yok)", placement=placement)
    names = {c.name for c in chars}
    for attempt in range(2):
        out, _ = await llm.chat("book-director", [{"role": "user", "content": prompt}], prompt=ref,
                                schema=PAGE_SCHEMA, max_tokens=1500, thinking=False, pages=[page_no],
                                temperature=0.3 + 0.3 * attempt)
        if _norm(out["quote"]) and _norm(out["quote"]) in _norm(text):
            return Scene(page_no, kind, out["moment"], out["quote"], [n for n in out["characters"] if n in names],
                         out["scene"], out["setting"], True)
    first = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    return Scene(page_no, kind, first, first, [n for n in names if n in text], out["scene"], out["setting"], False)


async def scenes(ms: Manuscript, p: Profile, chars: list[Character], pm: PageMap, llm,
                 concurrency: int = 6) -> list[Scene]:
    """Her resimli sayfa için sahne. Akış sayfası kendi metnini, tam sayfa resim bir sonraki bölümün
    açılışını (ya da açılış resmi ilk sayfayı) anlatır."""
    pages = pm.pages
    flow = [pg for pg in pages if pg.kind == "flow" and pg.text]
    sem = asyncio.Semaphore(concurrency)

    def around(i):
        return (flow[i - 1].text if i > 0 else "", flow[i + 1].text if i + 1 < len(flow) else "")

    async def one(pg, kind, text, before, after, placement):
        async with sem:
            return await _scene(ms, p, chars, llm, pg.no, kind, before, text, after, placement)

    jobs = []
    for i, pg in enumerate(flow):
        b, a = around(i)
        jobs.append(one(pg, "flow", pg.text, b, a, "üst bandında, sayfa genişliğinde"))
    for pg in pages:
        if pg.kind == "full":
            nxt = next((f for f in flow if f.no > pg.no), flow[-1])
            prv = next((f for f in reversed(flow) if f.no < pg.no), None)
            jobs.append(one(pg, "full", nxt.text, prv.text if prv else "", "", "tamamında (tam sayfa)"))
    return sorted(await asyncio.gather(*jobs), key=lambda s: s.page)
