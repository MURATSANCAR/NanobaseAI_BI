"""Basıma hazırlığın girdisi: kitabın metni, bölümlere ve bloklara ayrılmış hâli (Manuscript).

İki kaynak aynı yapıyı doldurur:
- `from_generation`: editörün okuduğu kitap (ed.paragraph + sayfa rolleri + kitap kartı). Okuma bir
  kez yapılır; basıma hazırlık onun çıktısını kullanır, kitabı yeniden okutmaz.
- `from_docx`: yazardan gelen Word dosyası (Başlık = kitap adı, Başlık 1 = bölüm).

Okunmuş kayıt basılı sayfadan geldiği için baskı artıkları taşır; `normalize` bunları kitaptan
bağımsız kurallarla giderir: sayfa sonunda bölünen cümle, satır sonu tirelemesi, bölüm başlığının
ilk paragrafa yapışması, tırnaktan önce eksik boşluk. Tire birleştirmesi yalnız birleşen kelime
Türkçe sözlükte geçerliyse yapılır.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

TERMINAL = tuple(".!?…:;”\"»)")          # bu işaretlerden biriyle biten blok cümleyi kapatmıştır
DIALOGUE = re.compile(r"^\s*[-–—]\s*")


@dataclass
class Block:
    kind: str                    # para | dialogue
    text: str
    pages: list[int] = field(default_factory=list)   # kaynak sayfalar (okunmuş kitapta)


@dataclass
class Chapter:
    title: str | None
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Manuscript:
    title: str
    author: str | None = None
    illustrator: str | None = None
    meta: dict = field(default_factory=dict)      # ISBN, yaş aralığı, tür, dizi… (kaynağında yazdığı gibi)
    chapters: list[Chapter] = field(default_factory=list)
    source: dict = field(default_factory=dict)

    def blocks(self):
        for ci, ch in enumerate(self.chapters):
            for bi, b in enumerate(ch.blocks):
                yield ci, bi, b

    def text(self) -> str:
        return "\n\n".join((f"## {c.title}\n\n" if c.title else "") + "\n\n".join(b.text for b in c.blocks)
                           for c in self.chapters)

    def to_json(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ normalize
def _letters(s: str) -> str:
    return re.sub(r"[^A-Za-zÇĞİÖŞÜÂÎÛçğıöşüâîû]", "", s)


_LOWER_UPPER = re.compile(r"[a-zçğıöşüâîû][A-ZÇĞİÖŞÜÂÎÛ]")


def _styled_case(t: str) -> bool:
    """Tasarımcı yazımı başlık: «KİtApLaRdAn NeFrEt EdİyOrUm», «EvE Dönüş». Kelimelerin en az yarısı ya
    tamamen büyük ya da kelime içinde küçükten büyüğe geçen harf taşır; en az biri bu geçişi taşır (düz
    metinde kelime içinde küçük harften sonra büyük harf gelmez)."""
    words = [_letters(w) for w in t.split() if len(_letters(w)) >= 2]
    if not words:
        return False
    mixed = [w for w in words if _LOWER_UPPER.search(w)]
    styled = [w for w in words if _LOWER_UPPER.search(w) or w == w.upper()]
    return bool(mixed) and 2 * len(styled) >= len(words)


def is_heading(text: str) -> bool:
    """Bölüm başlığı: bütün harfleri büyük (ya da tasarımcı yazımı, `_styled_case`), en çok 6 kelime, cümle
    işaretiyle bitmeyen, konuşma ya da alıntı olmayan satır."""
    t = text.strip()
    letters = _letters(t)
    return (bool(letters) and len(letters) >= 3 and (letters == letters.upper() or _styled_case(t))
            and len(t.split()) <= 6 and not t.endswith(TERMINAL)
            and not DIALOGUE.match(t) and not t.startswith(("“", "\"", "«")))


def split_leading_heading(text: str) -> tuple[str | None, str]:
    """«MERAKLI VOMBAT Kahvaltı masasında…» → («MERAKLI VOMBAT», «Kahvaltı masasında…»): paragrafın
    başındaki büyük harfli kelime dizisi (en az 2), ardından büyük harfle başlayan küçük harfli kelime."""
    words = text.split()
    k = 0
    while k < len(words) and len(_letters(words[k])) >= 2 and _letters(words[k]) == _letters(words[k]).upper():
        k += 1
    if 2 <= k < len(words) and k <= 6 and words[k][:1].isupper() and words[k][1:2].islower():
        return " ".join(words[:k]), " ".join(words[k:])
    return None, text


def _lexicon():
    from ..proofing._spelling_text import Lexicon
    return Lexicon()


def join_hyphen(left: str, right: str, lex) -> str | None:
    """«se-» + «pete» → «sepete», yalnız birleşen kelime geçerliyse."""
    a = re.search(r"(\w+)[-–]\s*$", left)
    b = re.match(r"\s*(\w+)", right)
    if not a or not b:
        return None
    word = a.group(1) + b.group(1)
    if lex is not None and not lex.valid(word):
        return None
    return left[:a.start()] + word + right[b.end():]


_INLINE_HYPHEN = re.compile(r"(\w+)[-–] (\w+)")
_GLUED_HYPHEN = re.compile(r"(?<![\w-])([a-zçğıöşüâîû]{2,})-([a-zçğıöşüâîû]{2,})(?![\w-])")


def fix_inline(text: str, lex) -> str:
    """Satır içinde kalmış tire artığı («YAV- RUCUĞUM») ve tırnak öncesi eksik boşluk."""
    def rep(m):
        word = m.group(1) + m.group(2)
        same_case = (m.group(1).isupper() and m.group(2).isupper()) or m.group(2).islower()
        return word if same_case and lex is not None and lex.valid(word) else m.group(0)
    text = _INLINE_HYPHEN.sub(rep, text)

    def glued(m):
        """«yeterin-ce», «ya-kalamıştım»: metin katmanında satır sonundan kalmış tire. Birleşen kelime geçerli
        ve parçalardan biri tek başına kelime değilse birleşir; «Ali-Veli», «aha-hahaha» gibi gerçek tire kalır."""
        a, b = m.group(1), m.group(2)
        if lex is None or not lex.valid(a + b):
            return m.group(0)
        return a + b if not (lex.valid(a) and lex.valid(b)) else m.group(0)
    text = _GLUED_HYPHEN.sub(glued, text)
    text = re.sub(r"(\w)([“«])", r"\1 \2", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def normalize(paragraphs: list[tuple[int, str]], lex=None) -> list[tuple[str | None, list[Block]]]:
    """(sayfa, metin) sırası → [(bölüm başlığı, bloklar)]. Başlıksız giriş bölümü None başlıklıdır."""
    chapters: list[tuple[str | None, list[Block]]] = [(None, [])]
    prev: Block | None = None
    prev_page = None
    for page, raw in paragraphs:
        text = raw.strip()
        if not text:
            continue
        head, rest = (text, "") if is_heading(text) else split_leading_heading(text)
        if head and chapters[-1][0] is not None and not chapters[-1][1]:
            # Başlık birkaç satıra bölünmüş («KoRsAnLaRlA» / «BİrLİkTe BaLİnAnın» / «KaRnınDa»): tek başlık.
            chapters[-1] = (f"{chapters[-1][0]} {head}", [])
            prev = None
            if not rest:
                continue
            text = rest
        elif head:
            chapters.append((head, []))
            prev = None
            if not rest:
                continue
            text = rest
        # Yarım kalan cümle: önceki blok cümle işaretiyle bitmiyor, bu blok küçük harfle başlıyor ve ya sayfa
        # değişti ya da önceki blok tireyle bölünmüş bir kelimeyle bitiyor (paragraf yarım kelimeyle bitemez;
        # metin katmanı aynı sayfada satır sonunda da bölebiliyor: «ola-» / «cak!») → aynı paragraf.
        hyphen_end = bool(re.search(r"\w[-–]\s*$", prev.text)) if prev is not None else False
        if (prev is not None and (page != prev_page or hyphen_end) and not prev.text.endswith(TERMINAL)
                and text[:1].islower()):
            joined = join_hyphen(prev.text, text, lex) if re.search(r"\w[-–]\s*$", prev.text) else None
            prev.text = joined or f"{prev.text} {text}"
            prev.pages.append(page)
            prev_page = page
            continue
        kind = "dialogue" if DIALOGUE.match(text) else "para"
        if kind == "dialogue":
            text = DIALOGUE.sub("", text)
        prev = Block(kind, text, [page])
        chapters[-1][1].append(prev)
        prev_page = page
    for _, blocks in chapters:
        for b in blocks:
            b.text = fix_inline(b.text, lex)
    return [(h, b) for h, b in chapters if b or h]


# ------------------------------------------------------------------ sources
def _first(meta: dict, key: str) -> str | None:
    v = meta.get(key)
    if isinstance(v, list) and v:
        v = v[0]
    if isinstance(v, dict):
        v = v.get("value")
    return str(v).strip() if v else None


def from_generation(generation_id: str, lex=None) -> Manuscript:
    """Editörün okuduğu kitaptan. Hikâye dışı sayfalar (künye, tanıtım) sayfa rolünden çıkar;
    kitap bilgisi kitabın güncel kartından (künyeden çıkarılmış, kanıtlı)."""
    from .. import db
    lex = lex if lex is not None else _lexicon()
    g = db.one("SELECT g.id, bv.book_id, b.title AS file_title FROM ed.generation g "
               "JOIN ed.book_version bv ON bv.id=g.book_version_id JOIN ed.book b ON b.id=bv.book_id "
               "WHERE g.id=%s", generation_id)
    if g is None:
        raise ValueError(f"okuma nesli yok: {generation_id}")
    non_story = {r["page_no"] for r in db.all_rows(
        "SELECT DISTINCT ON (page_no) page_no, role FROM ed.page_role WHERE generation_id=%s "
        "ORDER BY page_no, (source='editor') DESC", generation_id) if r["role"] == "NON_STORY"}
    rows = db.all_rows("SELECT page_no, idx, text FROM ed.paragraph WHERE generation_id=%s "
                       "ORDER BY page_no, idx", generation_id)
    card = db.one("SELECT title, metadata, age_min, age_max FROM ed.book_card WHERE book_id=%s "
                  "ORDER BY is_current DESC, created_at DESC LIMIT 1", g["book_id"]) or {}
    meta = dict(card.get("metadata") or {})
    # Kitap bilgisinin kaydı CRM'dir (künye çıkarımı bir kitapta ilk bölüm başlığını kitap adı
    # sanmıştı: «MERAKLI VOMBAT» ← «Dünyanın En Korkak Hayvanı»). Kart yalnız CRM'de olmayan alan için.
    crm = db.one("SELECT crm_title, authors, illustrators, summary, isbn, stock_code, crm_book_id "
                 "FROM ed.book_crm_record WHERE book_id=%s", g["book_id"]) or {}
    fields = {k: _first(meta, k) for k in ("ISBN", "AGE_RANGE", "GENRE", "SERIES", "PUBLISHER") if _first(meta, k)}
    if crm.get("isbn"):
        fields["ISBN"] = crm["isbn"]
    if crm.get("stock_code"):
        fields["STOCK_CODE"] = crm["stock_code"]
    if crm.get("summary"):
        fields["CRM_SUMMARY"] = crm["summary"]
    if card.get("age_min"):
        fields |= {"age_min": card["age_min"], "age_max": card["age_max"]}
    crm_author = ", ".join(crm.get("authors") or [])
    author = crm_author or _first(meta, "AUTHOR")
    ms = Manuscript(
        title=crm.get("crm_title") or _first(meta, "TITLE") or card.get("title") or g["file_title"],
        author=author,
        illustrator=", ".join(crm.get("illustrators") or []) or _first(meta, "ILLUSTRATOR"),
        meta=fields,
        source={"kind": "generation", "generation_id": str(generation_id), "book_id": str(g["book_id"]),
                "crm_book_id": str(crm["crm_book_id"]) if crm.get("crm_book_id") else None,
                "non_story_pages": sorted(non_story),
                "origin": {"title": "crm" if crm.get("crm_title") else "card",
                           "author": "crm" if crm_author else "card" if author else None}})
    paras = [(r["page_no"], r["text"]) for r in rows if r["page_no"] not in non_story]
    ms.chapters = [Chapter(h, b) for h, b in normalize(paras, lex)]
    return ms


def from_docx(path: str, lex=None) -> Manuscript:
    """Yazar dosyasından: Title/Başlık stili kitap adı, hemen ardından gelen ilk paragraf yazar,
    Heading 1 / Başlık 1 bölüm. Başlık stili kullanılmamış dosyada büyük harfli satır kuralı geçerlidir."""
    from docx import Document
    lex = lex if lex is not None else _lexicon()
    doc = Document(path)
    title = author = None
    paras: list[tuple[int, str]] = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if not t:
            continue
        style = (p.style.name or "").lower()
        if title is None and style in ("title", "başlık"):
            title = t
            continue
        if title is not None and author is None and not paras and not style.startswith(("heading", "başlık")):
            author = t
            continue
        if style.startswith(("heading 1", "başlık 1")):
            from ..proofing._spelling_text import upper_tr
            t = upper_tr(t)                  # bölüm başlığı kuralıyla aynı yoldan geçsin
        paras.append((0, t))
    ms = Manuscript(title=title or _docx_title(doc, path), author=author,
                    source={"kind": "docx", "path": path,
                            "origin": {"title": "docx", "author": "docx" if author else None}})
    ms.chapters = [Chapter(h, b) for h, b in normalize(paras, lex)]
    _crm_by_title(ms)
    return ms


def _docx_title(doc, path: str) -> str:
    """Başlık stili kullanılmamış dosyada kitap adı: belge özelliklerindeki başlık, yoksa dosya adı
    (uzantısız; alt çizgi ve tire boşluk olur). Belge özelliğindeki yazar alanı kullanılmaz: çoğu zaman
    dosyayı kaydeden kişidir, kitabın yazarı değil."""
    t = (getattr(doc.core_properties, "title", None) or "").strip()
    if t:
        return t
    stem = re.sub(r"\.(docx?|rtf|odt)$", "", path.rsplit("/", 1)[-1], flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"[_\-]+", " ", stem)).strip() or stem


def crm_lookup(title: str) -> tuple[dict | None, str]:
    """Kitap adıyla CRM kaydı (editörün eşlediği kitaplar): büyük/küçük harf ve boşluk farkı gözetmeden birebir.
    Dönen: (kayıt ya da None, eşleşme özeti: «kitap adı» | «yok» | «N aday»)."""
    from .. import db
    from ..proofing._spelling_text import lower_tr
    rows = db.all_rows("SELECT crm_title, authors, illustrators, summary, isbn, stock_code, crm_book_id "
                       "FROM ed.book_crm_record")
    key = lower_tr(re.sub(r"\s+", " ", title or "")).strip()
    hit = [r for r in rows if r["crm_title"] and lower_tr(re.sub(r"\s+", " ", r["crm_title"])).strip() == key]
    if len(hit) != 1:
        return None, "yok" if not hit else f"{len(hit)} aday"
    return hit[0], "kitap adı"


def _crm_by_title(ms: Manuscript) -> None:
    """Word dosyasının kitap adı CRM kaydıyla (editörün eşlediği kitaplar) birebir eşleşirse kitap
    bilgisi oradan gelir. Eşleşme yoksa alanlar boş kalır; ekranda elle tamamlanır."""
    r, match = crm_lookup(ms.title)
    if r is None:
        ms.source["crm_match"] = match
        return
    if not ms.author and r["authors"]:
        ms.source.setdefault("origin", {})["author"] = "crm"
    ms.author = ms.author or ", ".join(r["authors"] or []) or None
    # Çizer kitabın resimli olduğunun yayınevi kaydıdır (profil resim kararında kullanır).
    ms.illustrator = ms.illustrator or ", ".join(r["illustrators"] or []) or None
    ms.meta |= {k: v for k, v in (("ISBN", r["isbn"]), ("STOCK_CODE", r["stock_code"]),
                                  ("CRM_SUMMARY", r["summary"])) if v}
    ms.source["crm_book_id"] = str(r["crm_book_id"])
    ms.source["crm_match"] = match


# ------------------------------------------------------------------ editörün düzelttiği kitap bilgisi
# Kitap adı ve yazar okunduğu yerden gelir (CRM, Word dosyası, okunmuş kitabın kartı); editör künyede düzeltir.
# Tek doğruluk kaynağı manuscript.json'un kendi `title`/`author` alanıdır: kapak, iç kapak, künye, dizgi, pazarlama
# kiti, e-kitap, kolaj etiketleri hepsi oradan okur, hiçbiri değişmez. Okunan özgün değer `source.read`'de,
# editörün geçerli düzeltmesi `source.edits`'te (kim, ne zaman, eski değer), bütün düzeltmeler `source.edit_log`'da
# kalır. Editörün girdiği değer her zaman kazanır: CRM eşleşmesi onu ezmez, metin yeniden okunursa yeniden uygulanır.
BOOK_FIELDS = {"title": "Kitap", "author": "Yazar"}
ORIGIN_LABEL = {"crm": "yayınevi kaydı", "docx": "Word dosyası", "card": "okunmuş kitap"}


def field_source(source: dict, field: str) -> dict:
    """Kitap adının / yazarın kaynağı ekran için: editör düzeltmesiyse {"label", "by", "at", "was"}, değilse
    {"label"} (okunduğu yer). Kaynağı kayda geçmemiş eski işlerde kaynağın türünden çıkarılır."""
    e = (source.get("edits") or {}).get(field)
    if e:
        return {"label": f"editör: {e.get('by') or '?'}", "by": e.get("by"), "at": e.get("at"), "was": e.get("was")}
    origin = source.get("origin") or {}
    o = origin.get(field) or ""
    if field not in origin:
        kind, linked = source.get("kind"), bool(source.get("crm_book_id"))
        if kind == "docx":
            o = "crm" if field == "author" and linked else "docx"
        elif kind == "generation":
            o = "crm" if linked else "card"
    return {"label": ORIGIN_LABEL[o]} if o in ORIGIN_LABEL else {}


def author_cleared(source: dict) -> bool:
    """Editör yazarı bilerek boş bıraktı (yazarsız kitap): künyede «Yazar» satırı basılmaz, eksik sayılmaz."""
    e = (source.get("edits") or {}).get("author")
    return bool(e) and not e.get("value")


def reapply_edits(ms: Manuscript, old_source: dict | None) -> None:
    """Metin aynı iş klasöründe yeniden okunduğunda editörün kitap adı/yazar düzeltmeleri korunur."""
    old = old_source or {}
    if not old.get("edits"):
        return
    ms.source["read"] = {k: getattr(ms, k) for k in BOOK_FIELDS}
    for k, e in old["edits"].items():
        if k in BOOK_FIELDS:
            setattr(ms, k, e.get("value") or None)
    ms.source["edits"] = old["edits"]
    ms.source["edit_log"] = old.get("edit_log") or []


def fill_from_crm(m: dict, row: dict, manual: dict | None = None) -> list[str]:
    """Kitap adı değişince bulunan CRM kaydından yalnız BOŞ alanlar dolar; editörün girdiği alan (düzeltilmiş ya da
    bilerek boş bırakılmış yazar, künyede elle girilen ISBN) ezilmez. İş başka bir CRM kaydına bağlıysa iki kayıt
    karışmaz, hiçbir şey dolmaz. `m` manuscript.json sözlüğü, yerinde değişir. Dönen: dolan alanlar."""
    src = m.setdefault("source", {})
    rid = str(row["crm_book_id"])
    if src.get("crm_book_id") and str(src["crm_book_id"]) != rid:
        return []
    filled = []
    authors = ", ".join(row.get("authors") or [])
    if authors and not m.get("author") and "author" not in (src.get("edits") or {}):
        m["author"] = authors
        src.setdefault("origin", {})["author"] = "crm"
        filled.append("author")
    ill = ", ".join(row.get("illustrators") or [])
    if ill and not m.get("illustrator"):
        m["illustrator"] = ill
        filled.append("illustrator")
    meta = m.setdefault("meta", {})
    manual = manual or {}
    for key, value, label in (("ISBN", row.get("isbn"), "ISBN"), ("STOCK_CODE", row.get("stock_code"), None),
                              ("CRM_SUMMARY", row.get("summary"), None)):
        if value and not meta.get(key) and not (label and manual.get(label)):
            meta[key] = value
            filled.append(key)
    src["crm_book_id"] = rid
    return filled
