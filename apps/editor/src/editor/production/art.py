"""Sanat yönetimi: üslup rehberi, karakter kartları, sayfa sahneleri (ana model).

Her karar kitaptan gelir ve alıntıyla bağlanır: karakter görünüşünde metinden gelen ayrıntının alıntısı,
sayfa sahnesinde o sayfanın cümlesi metinde birebir aranır; alıntısı bulunmayan sahne tarifi yeniden
istenir, ikinci denemede de tutmazsa sayfanın kendi metninin ilk cümlesiyle sade tarife düşer.
Karakter görünüşü okuma sırasında özgün resimlerden çıkarılan betimlemelerden ALINMAZ: tasarım
sıfırdandır, yalnız metin bağlayıcıdır.
"""

from __future__ import annotations

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
OUTFIT = {"type": "object", "additionalProperties": False, "required": ["name", "look", "from_text"],
          "properties": {"name": {"type": "string"}, "look": {"type": "string"},
                         "from_text": {"type": "array", "items": {"type": "string"}}}}
CHAR_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["characters"], "properties": {
    "characters": {"type": "array", "maxItems": 8, "items": {
        "type": "object", "additionalProperties": False,
        "required": ["name", "species", "base_look", "outfits", "default_outfit", "from_text", "role"],
        "properties": {"name": {"type": "string"}, "species": {"type": "string"}, "base_look": {"type": "string"},
                       "outfits": {"type": "array", "minItems": 1, "maxItems": 5, "items": OUTFIT},
                       "default_outfit": {"type": "string"},
                       "from_text": {"type": "array", "items": {"type": "string"}},
                       "role": {"type": "string", "enum": ["ANA", "YAN"]}}}}}}
PAGE_SCHEMA = {"type": "object", "additionalProperties": False,
               "required": ["moment", "quote", "characters", "outfits", "new_day", "time_quote", "setting",
                            "setting_reason", "scene"],
               "properties": {"moment": {"type": "string"}, "quote": {"type": "string"},
                              "new_day": {"type": "boolean"}, "time_quote": {"type": "string"},
                              "characters": {"type": "array", "items": {"type": "string"}},
                              "outfits": {"type": "array", "items": {
                                  "type": "object", "additionalProperties": False, "required": ["character", "outfit"],
                                  "properties": {"character": {"type": "string"}, "outfit": {"type": "string"}}}},
                              "setting": {"type": "string"}, "setting_reason": {"type": "string"},
                              "scene": {"type": "string"}}}
DIRECTION_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["english"],
                    "properties": {"english": {"type": "string"}}}


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
    look: str                     # sabit görünüş (v1 planlarında giysi dahil tek tarif)
    from_text: list[str]
    role: str
    outfits: list[dict] = field(default_factory=list)   # [{name, look, from_text}]
    default_outfit: str = ""

    def outfit(self, name: str | None) -> str:
        """Kıyafetin tarifi; bilinmeyen ad varsayılana düşer."""
        by = {o["name"]: o["look"] for o in self.outfits}
        return by.get(name or "", by.get(self.default_outfit, ""))


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
    outfits: dict = field(default_factory=dict)          # karakter → kıyafet adı (bu sayfada)
    setting_reason: str = ""
    new_day: bool = False         # metin bu sayfada yeni bir güne geçti (alıntısı sayfada bulundu)
    art_id: str | None = None     # sayfa planındaki kalıcı resim kimliği (plan.freeze yazar; sayfa sırası değişse de sabit)


@dataclass
class ArtPlan:
    style: Style
    characters: list[Character]
    scenes: list[Scene] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("“", "\"").replace("”", "\"")).strip().casefold()


def _fold(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def _mentions(name: str, text: str) -> bool:
    """Ad metinde geçiyor mu: adın 3+ harfli herhangi bir kelimesi, ekiyle birlikte («Salyangoz'un»)."""
    t = _fold(text)
    return any(re.search(rf"(?<!\w){re.escape(w)}", t) for w in re.findall(r"\w{3,}", _fold(name)))


def _allowed(chars: list, window: str, prev_chars: list[str]) -> list:
    """Bu sayfanın resmine girebilecek karakterler: adı sayfada ya da komşu sayfalarda geçenler; ana
    karakter adı anılmadan («o») önceki resimden sürebilir. Model sahneye metinde olmayanı koyamaz."""
    return [c for c in chars if _mentions(c.name, window) or (c.role == "ANA" and c.name in prev_chars)]


def _outfit_in_text(c: Character, name: str, text: str) -> bool:
    o = next((o for o in c.outfits if o["name"] == name), None)
    return bool(o) and (_mentions(o["name"], text) or any(_norm(q) in _norm(text) for q in o["from_text"] if q))


def _new_day_outfits(chars: list, wear: dict, prev: dict, text: str) -> dict:
    """Yeni günde önceki sayfadan sürüp gelen kıyafet, bu sayfanın metni onu giydirmiyorsa varsayılana döner."""
    by = {c.name: c for c in chars}
    out = {}
    for n, o in wear.items():
        c = by[n]
        out[n] = c.default_outfit if o == prev.get(n) and o != c.default_outfit and not _outfit_in_text(c, o, text) else o
    return out


def _drop_mentions(scene: str, names: list[str]) -> str:
    """Sahne tarifinden izinsiz karakterin geçtiği cümleleri çıkarır."""
    keep = [x for x in re.split(r"(?<=[.!?])\s+", scene) if not any(_fold(n) in _fold(x) for n in names)]
    return " ".join(keep) or scene


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
        outfits = [{**o, "from_text": [q for q in o["from_text"] if _norm(q) in full]} for o in c["outfits"]]
        names = {o["name"] for o in outfits}
        chars.append(Character(name=c["name"], species=c["species"], look=c["base_look"],
                               from_text=[q for q in c["from_text"] if _norm(q) in full], role=c["role"],
                               outfits=outfits,
                               default_outfit=c["default_outfit"] if c["default_outfit"] in names else outfits[0]["name"]))
    return chars


def _char_lines(chars: list[Character]) -> str:
    def fits(c):
        return "; ".join(f"«{o['name']}»{' (varsayılan)' if o['name'] == c.default_outfit else ''}: {o['look']}"
                         for o in c.outfits) or "—"
    return "\n".join(f"- {c.name}: {c.species}; {c.look} | kıyafetler: {fits(c)}" for c in chars)


async def _scene(ms, p, chars, llm, page_no, kind, before, text, after, placement,
                 prev_setting: str = "", prev_outfits: dict | None = None,
                 prev_chars: list[str] | None = None) -> Scene:
    prev_outfits = prev_outfits or {}
    cast = _allowed(chars, "\n".join((before, text, after)), prev_chars or [])
    prev = ", ".join(f"{k}: {v}" for k, v in prev_outfits.items()) or "(yok)"
    ref, prompt = render("production_page_art", title=ms.title, age=_age(p),
                         characters=_char_lines(cast) or "(bu sayfada adı geçen karakter yok)",
                         before=before or "(yok)", page_text=text, after=after or "(yok)", placement=placement,
                         prev_setting=prev_setting or "(ilk sayfa)", prev_outfits=prev)
    names = {c.name for c in cast}
    outsiders = [c.name for c in chars if c.name not in names]
    fits = {c.name: {o["name"] for o in c.outfits} for c in cast}
    for attempt in range(2):
        out, _ = await llm.chat("book-director", [{"role": "user", "content": prompt}], prompt=ref,
                                schema=PAGE_SCHEMA, max_tokens=1800, thinking=False, pages=[page_no],
                                temperature=0.3 + 0.3 * attempt)
        who = [n for n in out["characters"] if n in names]
        wear = {o["character"]: o["outfit"] for o in out["outfits"]
                if o["character"] in who and o["outfit"] in fits.get(o["character"], ())}
        new_day = bool(out["new_day"] and _norm(out["time_quote"]) and _norm(out["time_quote"]) in _norm(text))
        if new_day:
            wear = _new_day_outfits(cast, wear, prev_outfits, text)
        scene = _drop_mentions(out["scene"], outsiders)
        if _norm(out["quote"]) and _norm(out["quote"]) in _norm(text):
            return Scene(page_no, kind, out["moment"], out["quote"], who, scene, out["setting"], True,
                         wear, out["setting_reason"], new_day)
    first = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    return Scene(page_no, kind, first, first, [n for n in names if _mentions(n, text)] or who, scene,
                 out["setting"], False, wear, out["setting_reason"], new_day)


async def scenes(ms: Manuscript, p: Profile, chars: list[Character], pm: PageMap, llm) -> list[Scene]:
    """Her resimli sayfa için sahne, sayfa sırasıyla: her sayfaya önceki sayfanın mekânı ve kıyafetleri
    verilir (süreklilik). Tam sayfa resim bir sonraki bölümün açılışını anlatır."""
    flow = [pg for pg in pm.pages if pg.kind == "flow" and pg.text]
    out: list[Scene] = []
    prev_setting, prev_outfits, prev_chars = "", {}, []
    painted = pm.art_pages()
    for pg in pm.pages:
        if pg.no not in painted:
            continue
        if pg.kind == "flow" and pg.text:
            i = flow.index(pg)
            before, after = (flow[i - 1].text if i else ""), (flow[i + 1].text if i + 1 < len(flow) else "")
            sc = await _scene(ms, p, chars, llm, pg.no, "flow", before, pg.text, after,
                              "üst bandında, sayfa genişliğinde", prev_setting, prev_outfits, prev_chars)
        elif pg.kind == "full":
            nxt = next((f for f in flow if f.no > pg.no), flow[-1])
            prv = next((f for f in reversed(flow) if f.no < pg.no), None)
            sc = await _scene(ms, p, chars, llm, pg.no, "full", prv.text if prv else "", nxt.text, "",
                              "tamamında (tam sayfa)", prev_setting, prev_outfits, prev_chars)
        else:
            continue
        out.append(sc)
        prev_setting = sc.setting
        prev_outfits = {**({} if sc.new_day else prev_outfits), **sc.outfits}
        prev_chars = sc.characters
    return out


async def direction_en(text: str, chars: list[Character], llm) -> str:
    """Editörün yönlendirmesi görsel model için İngilizce. Görsel model Türkçe kelimeyi başka bir şeye
    benzetebiliyor (2026-09-25: «karga» istendi, martı çizildi). Karakter adları olduğu gibi kalır."""
    if not text.strip():
        return ""
    ref, prompt = render("production_direction", text=text.strip(),
                         characters=", ".join(c.name for c in chars) or "(yok)")
    out, _ = await llm.chat("book-director", [{"role": "user", "content": prompt}], prompt=ref,
                            schema=DIRECTION_SCHEMA, max_tokens=400, thinking=False, temperature=0.0)
    return out["english"].strip() or text.strip()
