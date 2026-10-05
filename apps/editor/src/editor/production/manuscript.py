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

import collections
import re
from dataclasses import asdict, dataclass, field

TERMINAL = tuple(".!?…:;”\"»)")          # bu işaretlerden biriyle biten blok cümleyi kapatmıştır
DIALOGUE = re.compile(r"^\s*[-–—]\s*")


@dataclass
class Block:
    kind: str                    # para | dialogue; dizgiyle (`layout=True`): poem | italic | right | epigraph |
    #                              perde_alti | subhead | break | table (metin tablonun HTML'i)
    text: str
    pages: list[int] = field(default_factory=list)   # kaynak sayfalar (okunmuş kitapta)


@dataclass
class Chapter:
    title: str | None
    blocks: list[Block] = field(default_factory=list)
    kind: str = "chapter"        # chapter | perde (bölüm perdesi: başlığı kendi sayfasında, dizgiyle bulunur)


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


def normalize(paragraphs: list[tuple[int, str]], lex=None,
              headings: bool = True) -> list[tuple[str | None, list[Block]]]:
    """(sayfa, metin) sırası → [(bölüm başlığı, bloklar)]. Başlıksız giriş bölümü None başlıklıdır.
    `headings=False`: bölümler başka yerden (dizgiden) bilinir; büyük harfli satır bölüm açmaz."""
    chapters: list[tuple[str | None, list[Block]]] = [(None, [])]
    prev: Block | None = None
    prev_page = None
    for item in paragraphs:
        page, raw = item[0], item[1]
        forced = item[2] if len(item) > 2 else None        # dizgiden bilinen tür (şiir, tablo…): birleşmez
        text = raw.strip()
        if not text:
            continue
        if forced and forced != "para":
            chapters[-1][1].append(Block(forced, text, [page]))
            prev = None
            prev_page = page
            continue
        head, rest = ((text, "") if is_heading(text) else split_leading_heading(text)) if headings else (None, text)
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
            if b.kind not in ("poem", "table"):              # satır sonu ve tablo HTML'i olduğu gibi kalır
                b.text = fix_inline(b.text, lex)
    return [(h, b) for h, b in chapters if b or h]


# ------------------------------------------------------------------ baskı dışı sayfalar
# Okumanın NON_STORY önerisi «hikâye anlatmayan sayfa» demektir (bilgilendirme, kaynakça, önsöz da girer); kurgu
# dışı kitapta gövdenin çoğu bu öneriyi alır. Baskı kararı değildir: Stüdyo yalnız aday sayar ve sayfayı ancak kendi
# metni baskı dışı olduğunu gösterirse atar — künye, içindekiler, yayınevi tanıtımı/reklamı, iç kapak, yazar
# tanıtımı (Stüdyo kendi tanıtım sayfasını basar), boş sayfa. Önsöz, giriş, sonsöz, yazarın notu, kaynakça, notlar,
# ekler, ithaf ve bütün gövde kalır. Kurallar kitaptan bağımsızdır; 2026-10-01 GPU editöründeki 12 okunmuş kitapta
# ölçüldü (eski hâlinde İbn Sina'nın 148, İstediğim İnsan'ın 101 sayfası basılmıyordu).
_KUNYE = (r"\bisbn\b", r"sertifika", r"yay[ıi]n y[öo]netmeni", r"t[üu]m haklar[ıi]", r"©|\bcopyright\b",
          r"bask[ıi] ve cilt", r"matbaa", r"yay[ıi]na haz[ıi]rlayan", r"kapak tasar[ıi]m", r"\bedit[öo]r\b")
_PROMO = re.compile(r"kitap [öo]nerimiz|karekod|qr ?kod|yay[ıi]nlar[ıi]m[ıi]zdan|(yazar[ıi]n|dizinin) di[ğg]er kitaplar",
                    re.I)
_PLACE_YEAR = re.compile(r"^\s*[^\W\d_]+,? (19|20)\d\d\s*$")              # «İstanbul 2026»: künyenin yeri/yılı
_TOC = ("icindekiler", "contents", "fihrist")
_BIO = re.compile(r"do[ğg](du|an|umlu)|d[üu]nyaya gel|mezun|e[ğg]itimini|lisans|[çc]al[ıi][şs]maktad[ıi]r|"
                  r"ya[şs]amaktad[ıi]r|eserleri|kitaplar[ıi]", re.I)
_SENTENCE_END = re.compile(r"[.!?…:;][\"”’'»)]?\s*$")
_BORN = re.compile(r"do[ğg](du|an|umlu)|d[üu]nyaya gel", re.I)
_PAGE_REF =re.compile(r"(?:/|\.{3,}|…+)\s*\d{1,3}\b|\s\d{1,3}$")


def _fold(t: str) -> str:
    """Karşılaştırma anahtarı: küçük harf, düzeltme işaretsiz, i/ı ayrımsız (büyük harfli Türkçe ad ile yabancı ad
    aynı anahtara düşer), noktalama ve rakamsız. Okunmuş metinde «İ» bazen I + birleşen nokta olarak gelir (NFC)."""
    import unicodedata
    t = unicodedata.normalize("NFC", t).replace("İ", "i").casefold().replace("ı", "i")
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]|\d|_", " ", t).split())


def _caps(t: str) -> bool:
    letters = [c for c in t if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def print_plan(pages: dict[int, list[str]], candidates: set[int], last_page: int,
               titles: list[str], names: list[str]) -> dict[int, tuple[str, int]]:
    """Baskıya girmeyecek sayfalar: {sayfa: (neden, kalan ilk paragraf sayısı)}; 0 = sayfa bütünüyle çıkar.
    `pages`: sayfa → okunmuş paragraflar; `candidates`: okumanın (ya da editörün) hikâye dışı dediği sayfalar —
    yalnız bunlar atılabilir; `titles`/`names`: kitabın adı ve yazar/çevirmen adları (iç kapak, tanıtım)."""
    titles = [t for t in (_fold(x) for x in titles if x) if len(t) >= 3]
    names = [n for n in (_fold(x) for part in names if part for x in re.split(r"[,;&]| ve ", part)) if len(n) >= 5]
    front = max(10, last_page // 10)
    back = max(5, last_page // 20)
    opening = {}                                   # bir kitapta ≥3 sayfayı açan satır sayfa başlığıdır (künye değil)
    for ps in pages.values():
        for t in ps[:2]:
            opening[_fold(t)] = opening.get(_fold(t), 0) + 1
    out: dict[int, tuple[str, int]] = {}

    def text_of(p):
        return " ".join(pages.get(p, []))

    def words(p):
        return len(text_of(p).split())

    def is_toc(p):
        ps = [t for t in pages.get(p, []) if t.strip()]
        return bool(ps) and any(_fold(ps[0]).startswith(x) for x in _TOC)

    def toc_like(p):
        tokens = text_of(p).split()
        refs = len(_PAGE_REF.findall(text_of(p))) + sum(1 for t in pages.get(p, []) if re.search(r"\d{1,3}\s*$", t))
        nums = sum(1 for t in tokens if re.fullmatch(r"\d{1,3}", t))
        return bool(tokens) and (refs >= 3 or nums / len(tokens) >= 0.06)

    def has_name(t):
        f = _fold(t)
        return any(n in f for n in names)

    toc_pages: set[int] = set()
    for p in sorted(candidates):
        ps = [t for t in pages.get(p, []) if t.strip()]
        if not ps or p in out:
            continue
        low = text_of(p).casefold()
        if sum(1 for k in _KUNYE if re.search(k, low)) >= 3 or re.search(r"\bisbn\b", low) and "sertifika" in low:
            out[p] = ("künye", 0)
        elif is_toc(p) or (p - 1 in toc_pages and toc_like(p)):
            toc_pages.add(p)
            out[p] = ("içindekiler", 0)
        elif all(_PLACE_YEAR.match(t) or re.search(r"www\.|https?:", t) for t in ps):
            out[p] = ("künye", 0)
        elif p <= front and _BIO.search(text_of(p)) and (
                (opening.get(_fold(ps[0]), 0) < 3 and (has_name(ps[0]) or (_caps(ps[0]) and 2 <= len(ps[0].split()) <= 4
                                                                       and _BORN.search(text_of(p)))))
                # yazar adı sayfa başlığı olarak da basılmışsa: adın altındaki paragraf doğumla başlar
                or (opening.get(_fold(ps[0]), 0) >= 3 and len(ps) > 1 and _BORN.search(ps[1][:160]))):
            out[p] = ("yazar tanıtımı", 0)
            nxt = p + 1                             # tanıtım içindekilere kadar sürebilir (üyelikler, eser listesi)
            run = []
            while nxt in candidates and nxt <= front and not is_toc(nxt) and pages.get(nxt):
                run.append(nxt)
                nxt += 1
            if run and is_toc(nxt) and len(run) <= 3:
                for q in run:
                    out[q] = ("yazar tanıtımı", 0)
        elif (p <= front and words(p) <= 40 and all(len(t.split()) <= 15 and not _SENTENCE_END.search(t) for t in ps)
              and any(any(x in _fold(t) for x in titles) or has_name(t) for t in ps)):
            # kitap adı/yazar/yayınevi satırları tek başına; cümleyle biten satır (bölüm sonu, ithaf, epigraf) varsa değil
            out[p] = ("iç kapak", 0)
        else:
            # reklam yalnız kitabın son sayfalarında aranır (gövdede «karekod» geçen kurgu dışı metin kalır)
            cut = next((i for i, t in enumerate(ps) if _PROMO.search(t)), None) if p > last_page - back else None
            if cut is not None:
                out[p] = ("yayınevi tanıtımı", cut)
            elif p <= front and _PLACE_YEAR.match(ps[-1]) and len(ps) > 1:
                out[p] = ("künye", len(ps) - 1)
    # Tanıtım sayfasından sonra kitabın sonuna dek süren hikâye dışı sayfalar: yayınevinin diğer kitapları.
    promo = [p for p, (why, _) in out.items() if why == "yayınevi tanıtımı"]
    tail = [p for p in range(min(promo) + 1, last_page + 1)] if promo else []
    if tail and all(p in candidates or not pages.get(p) for p in tail):
        for p in tail:
            if pages.get(p) and p not in out:
                out[p] = ("yayınevi tanıtımı", 0)
    # Kitabın sonundan geriye: başka bir kitabın adı + yazarı (büyük harf, art arda satırlar) ile açılan hikâye dışı
    # sayfalar kitap reklamıdır; ilk böyle olmayan sayfada durulur.
    def ad_like(ps):
        return any(_caps(a) and _caps(b) and len(a.split()) <= 10 and 2 <= len(b.split()) <= 4
                   and not any(_fold(a).startswith(x) or x.startswith(_fold(a)) for x in titles)
                   for a, b in zip(ps[:4], ps[1:5]))

    for p in range(last_page, max(0, last_page - back), -1):
        ps = [t for t in pages.get(p, []) if t.strip()]
        if not ps or (p in out and out[p][1] == 0):
            continue
        if p not in candidates or p in out or not ad_like(ps):
            break
        out[p] = ("yayınevi tanıtımı", 0)
    return out


# ------------------------------------------------------------------ sources
def _first(meta: dict, key: str) -> str | None:
    v = meta.get(key)
    if isinstance(v, list) and v:
        v = v[0]
    if isinstance(v, dict):
        v = v.get("value")
    return str(v).strip() if v else None


def from_generation(generation_id: str, lex=None, layout: bool | str = False) -> Manuscript:
    """Editörün okuduğu kitaptan. Hikâye dışı sayfalar (künye, tanıtım) sayfa rolünden çıkar;
    kitap bilgisi kitabın güncel kartından (künyeden çıkarılmış, kanıtlı).
    `layout=True` (basılı kitabın e-kitabı): basılı PDF'in dizgisiyle sayfa üst başlıkları ve numaraları gövdeden
    çıkar, dipnotlar bölüm sonuna «[n] …» notu olur ve metindeki gönderme «[n]» olur, tablolar tablo olur, paragrafın
    biçimi (şiir, italik, sağa yaslı, epigraf, perde) bloğun türüne yazılır (`print_layout`, `_apply_layout`).
    `layout="print"` (stüdyonun basılı tasarımı): yalnız temizlik — üst başlık, sayfa numarası ve dipnot gövdeden
    çıkar, bölünen cümle birleşir, dipnotlar bölüm sonunda «¹ metin» paragrafı, göndermeler üst simge rakam; bloklar
    para/diyalog kalır (dizgi yeni türleri tanımaz), tablo okunmuş metniyle kalır."""
    from .. import db
    lex = lex if lex is not None else _lexicon()
    g = db.one("SELECT g.id, bv.book_id, b.title AS file_title FROM ed.generation g "
               "JOIN ed.book_version bv ON bv.id=g.book_version_id JOIN ed.book b ON b.id=bv.book_id "
               "WHERE g.id=%s", generation_id)
    if g is None:
        raise ValueError(f"okuma nesli yok: {generation_id}")
    # Hikâye dışı önerisi yalnız adaydır; hangisinin basılmayacağına sayfanın metni karar verir (`print_plan`).
    candidates = {r["page_no"] for r in db.all_rows(
        "SELECT DISTINCT ON (page_no) page_no, role FROM ed.page_role WHERE generation_id=%s "
        "ORDER BY page_no, (source='editor') DESC", generation_id) if r["role"] in ("NON_STORY", "FRONT_MATTER")}
    rows = db.all_rows("SELECT page_no, idx, text FROM ed.paragraph WHERE generation_id=%s "
                       "ORDER BY page_no, idx", generation_id)
    last_page = (db.one("SELECT page_count FROM ed.book_version bv JOIN ed.generation g ON g.book_version_id=bv.id "
                        "WHERE g.id=%s", generation_id) or {}).get("page_count") or max(
        (r["page_no"] for r in rows), default=0)
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
    by_page: dict[int, list[str]] = {}
    for r in rows:
        by_page.setdefault(r["page_no"], []).append(r["text"])
    plan = print_plan(by_page, candidates, last_page,
                      [crm.get("crm_title"), _first(meta, "TITLE"), card.get("title"), g["file_title"]],
                      [crm_author, _first(meta, "AUTHOR"), _first(meta, "TRANSLATOR"),
                       ", ".join(crm.get("illustrators") or [])])
    dropped = {p for p, (_, keep) in plan.items() if keep == 0}
    ms = Manuscript(
        title=crm.get("crm_title") or _first(meta, "TITLE") or card.get("title") or g["file_title"],
        author=author,
        illustrator=", ".join(crm.get("illustrators") or []) or _first(meta, "ILLUSTRATOR"),
        meta=fields,
        source={"kind": "generation", "generation_id": str(generation_id), "book_id": str(g["book_id"]),
                "crm_book_id": str(crm["crm_book_id"]) if crm.get("crm_book_id") else None,
                "non_story_pages": sorted(dropped),       # basılmayan sayfalar (adı eski kayıtlarla uyumlu)
                "not_printed": {str(p): why for p, (why, keep) in sorted(plan.items())},
                "origin": {"title": "crm" if crm.get("crm_title") else "card",
                           "author": "crm" if crm_author else "card" if author else None}})
    spaced = spaced_layout(generation_id)
    paras = [(p, part) for p, texts in sorted(by_page.items())
             for i, text in enumerate(texts) if p not in plan or i < plan[p][1]
             for part in resplit(text, (spaced or {}).get(p, []))]
    pages = _print_pages(generation_id) if layout else None
    notes: dict = {}
    if pages:
        paras, notes = _apply_layout(paras, pages, tables=layout != "print")
        if layout == "print":
            paras = [(p, t) for p, t, _ in paras]       # tür yok: basılı dizgi para/diyalog bilir
    ms.chapters = by_typeset(generation_id, paras, lex) or [Chapter(h, b) for h, b in normalize(paras, lex)]
    if pages:
        _finish_layout(ms, pages, notes, print_style=layout == "print")
    return ms


def _print_pages(generation_id: str):
    try:
        from .. import db
        from ..document import _open_version
        from . import print_layout
        g = db.one("SELECT book_version_id FROM ed.generation WHERE id=%s", generation_id)
        doc, _ = _open_version(str(g["book_version_id"]))
    except Exception:  # noqa: BLE001 - PDF yoksa (taranmış kitap vb.) okunmuş paragraflar olduğu gibi
        return None
    with doc:
        return print_layout.analyze(doc)


_INDEX_TITLE = re.compile(r"^((genel|kişi|kisi|yer|kavram|isim|özel ad|ozel ad)(ler)?\s+)?(dizin[i]?|indeks|index)$")


def index_pages(by_page: dict[int, str]) -> set[int]:
    """Kitabın sonundaki dizin sayfaları (e-kitapta sayfa numaraları anlamsızdır; yayınevinin e-kitaplarında dizin
    yoktur): «Dizin / İndeks / Index» başlıklı paragrafla açılan sayfa ve ardından kelimelerinin en az %30'u sayfa
    numarası olan sayfalar."""
    out: set[int] = set()
    start = next((p for p in sorted(by_page) if any(_INDEX_TITLE.match(" ".join(_fold(t).split()))
                                                    for t in by_page[p].split("\n")[:3] if len(t) <= 40)), None)
    if start is None:
        return out
    for p in sorted(x for x in by_page if x >= start):
        toks = by_page[p].split()
        nums = sum(1 for t in toks if re.fullmatch(r"\d{1,4}([-–]\d{1,4})?[,;.]?", t))
        if p == start or (toks and nums / len(toks) >= 0.3):
            out.add(p)
        else:
            break
    return out


_MARK = re.compile(r"\[\[(\d+):(\d+)\]\]")


def _cut_after(text: str, head: str, folded: bool = False) -> int:
    """Metnin, `head` satırının harflerini (katlanmış anahtar) tükettiği konum; metin o satırla başlamıyorsa 0.
    `folded`: `head` zaten katlanmış anahtardır."""
    from .print_layout import fold
    want = head if folded else fold(head)
    if not want or not fold(text).startswith(want):
        return 0
    got = ""
    for i, ch in enumerate(text):
        got += fold(ch)
        if len(got) >= len(want):
            return i + 1
    return 0


def _apply_layout(paras: list[tuple[int, str]], pages: dict, tables: bool = True) -> tuple[list[tuple], dict]:
    """Okunmuş paragraflar dizgiyle: üst başlık/sayfa no ve dipnot/tablo bölgesindeki paragraf düşer, gönderme
    numarası «[[sayfa:no]]» işareti olur, paragrafa dizgiden tür yazılır, tablo ilk tablo paragrafının yerine girer.
    Döner: ([(sayfa, metin, tür)], {(sayfa, no): not metni})."""
    import html as _html
    from .print_layout import fold, kind_of, para_lines

    def table_html(rows):
        head = "".join(f"<th>{_html.escape(c)}</th>" for c in rows[0])
        body = "".join("<tr>" + "".join(f"<td>{_html.escape(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
        return f'<table class="e-tablo"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
    out: list[tuple] = []
    ys: list[float | None] = []                        # öğenin basılı sayfadaki yeri (tablolu sayfada sıra için)
    placed: set[int] = set()
    notes: dict[tuple[int, str], str] = {}
    last_note = None
    for p in sorted(pages):
        for num, text in pages[p].notes:
            if num is None and last_note is not None:
                notes[last_note] = f"{notes[last_note]} {text}"
            elif num is not None:
                last_note = (p, num)
                notes[last_note] = text
    used: dict[int, set[str]] = {}
    # sayfa üst başlığı birçok sayfada tekrar eder; tek sayfadaki «baş» satırı (sayfa başında açılan ara başlık) değil
    repeated = collections.Counter(h for pg in pages.values() for h in pg.heads)
    index = index_pages({p: "\n".join(t for q, t in paras if q == p) for p in {q for q, _ in paras}})
    for p, text in paras:
        if p in index:                                # dizin e-kitaba girmez
            continue
        pg = pages.get(p)
        if pg is None:
            out.append((p, text, None))
            ys.append(None)
            continue
        k = fold(text)
        prev = pages.get(p - 1)
        if k in pg.heads or not k:
            continue
        # okumada sayfa üst başlığı alttaki paragrafla birleşmiş olabilir («OSMANLI’DA … TEMELLERİ DERS KİTAPLARI…»)
        for h in sorted(pg.heads, key=len, reverse=True):
            if len(h) >= 8 and k.startswith(h) and len(k) > len(h) and repeated[h] >= 3:
                cut = _cut_after(text, h, folded=True)
                if cut:
                    text, k = text[cut:].strip(), fold(text[cut:])
                break
        # okumada sayfanın son paragrafı o sayfanın dipnotlarıyla birleşmiş olabilir («… sorunu. 2 Fredde Lokkegaard…»):
        # notlar sayfanın notlarından zaten alınır, paragraf ilk notun başladığı yerde kesilir
        if pg.notes and pg.notes[0][1]:
            nk = fold(pg.notes[0][1])[:30]
            at = k.find(nk) if len(nk) >= 20 else -1
            if at > 0 and k[at:] and k[at:][:200] in pg.note_key + fold(" ".join(t for _, t in pg.notes[1:])):
                cut = _cut_after(text, k[:at], folded=True)
                while cut and cut < len(text) and text[cut] in ".,;:!?…”\"’')]»":
                    cut += 1                              # cümle sonu noktalaması paragrafta kalır
                if cut:
                    body = text[:cut].rstrip()
                    if pg.notes[0][0]:
                        body = re.sub(rf"\s*{pg.notes[0][0]}\s*$", "", body)
                    text, k = body, fold(body)
        probe = k[: min(40, len(k))]
        if len(k) >= 6 and (probe in pg.note_key or (prev is not None and probe in prev.note_key)) \
                and probe not in pg.body_key:
            continue
        if tables and pg.tables and len(k) >= 6 and probe in pg.table_key:
            if p not in placed:
                placed.add(p)
                for rows, y in zip(pg.tables, pg.table_y):
                    out.append((p, table_html(rows), "table"))
                    ys.append(y)
            continue
        # Gönderme numarası üst simge işaretli değilse de (PDF'e göre değişir) sayfanın not numarası metinde aranır;
        # biri bulunamazsa ötekiler yine aranır.
        for n in sorted(set(pg.refs) | {x for x, _ in pg.notes if x}, key=int):
            if n in used.setdefault(p, set()):
                continue
            new, cnt = re.subn(rf"(?<=[^\s\d\[]){n}(?=[\s.,;:!?”\"’')»]|$)", f"[[{p}:{n}]]", text, count=1)
            if cnt:
                text = new
                used[p].add(n)
        lines = para_lines(pg, text)
        font = getattr(pg, "font", "")
        # Okumada ara başlık altındaki paragrafla birleşmiş olabilir («YUNAN AYAKLANMASI Erken bir tarihte…»): ilk
        # satırı tek başına alt başlıksa ve ikinci satır değilse başlık ayrı paragraf olur.
        head = 0
        while head < min(3, len(lines) - 1) and kind_of(lines[head:head + 1], pg.left, pg.right, pg.size,
                                                        font)[0] == "subhead":
            head += 1
        if head and kind_of(lines[:head], pg.left, pg.right, pg.size, font)[0] == "subhead":
            cut = _cut_after(text, " ".join(ln.text for ln in lines[:head]))
            if cut:
                out.append((p, text[:cut].strip(), "subhead"))
                ys.append(lines[0].y0)
                text, lines = text[cut:].strip(), lines[head:]
        kind, poem = kind_of(lines, pg.left, pg.right, pg.size, font)
        out.append((p, poem if poem and "[[" not in text else text, kind if kind != "para" else None))
        ys.append(lines[0].y0 if lines else None)
    # Gönderme numarası metinde bulunamayan not kaybolmaz: sayfanın son paragrafının sonuna bağlanır.
    for p, pg in pages.items():
        lost = [n for n, _ in pg.notes if n and n not in used.get(p, set())]
        at = max((i for i, x in enumerate(out) if x[0] == p and x[2] in (None, "italic", "right")), default=None)
        if lost and at is not None:
            q, t, k = out[at]
            out[at] = (q, t + "".join(f"[[{p}:{n}]]" for n in lost), k)
    for p, pg in pages.items():                       # tablo okumada hiç paragraf vermediyse sayfadaki yerine
        if tables and pg.tables and p not in placed:
            at = max((i for i, x in enumerate(out) if x[0] <= p), default=-1) + 1
            for rows, y in zip(pg.tables, pg.table_y):
                out.insert(at, (p, table_html(rows), "table"))
                ys.insert(at, y)
                at += 1
    # Ara işareti (süs): sayfada, ardından gelen ilk paragrafın önüne.
    for p, pg in pages.items():
        for y in pg.breaks:
            at = next((i for i, (q, _, _) in enumerate(out) if q == p and ys[i] is not None and ys[i] > y), None)
            if at is None:                            # sayfanın son satırının altındaki süs: sayfanın ardına
                at = max((i for i, x in enumerate(out) if x[0] == p), default=None)
                at = at + 1 if at is not None else None
            if at is not None and not (at > 0 and out[at - 1][2] == "break"):
                out.insert(at, (p, "* * *", "break"))
                ys.insert(at, y)
    # Tablolu sayfada öğeler basılı sayfadaki yerine göre sıralanır (tablo başlığının ikinci satırı tablodan önce).
    i = 0
    while i < len(out):
        j = i
        while j < len(out) and out[j][0] == out[i][0]:
            j += 1
        if tables and any(x[2] == "table" for x in out[i:j]):
            known, last = {}, -1.0                    # yeri bulunamayan paragraf öncekinin hemen ardında kalır
            for k in range(i, j):
                last = ys[k] if ys[k] is not None else last + 0.01
                known[k] = last
            order = sorted(range(i, j), key=lambda k: known[k])
            out[i:j] = [out[k] for k in order]
            ys[i:j] = [ys[k] for k in order]
        i = j
    return out, notes


def _clean_title(t: str) -> str:
    """Devam sayfasının başlığı bölüm adına eklenmiş olabilir («EK 2: X EK 2: X (Devam)»): tek ad."""
    t = re.sub(r"\s*\(devam(ı)?\)\s*$", "", " ".join(t.split()), flags=re.I)
    half = len(t) // 2
    for cut in range(half - 2, half + 3):
        a, b = t[:cut].strip(), t[cut:].strip()
        if a and a == b:
            return a
    return t


def _recut_perde(ms: Manuscript, pages: dict) -> None:
    """Perde sayfası olan kitapta bölümler perdeden başlar: perde sayfasındaki ilk paragraf bölüm adı, kısa alt satırı
    perde altı; dizgiden bulunmuş bölüm adları («I», «II»: perdeden sonraki alt başlık) bölüm içi başlık olur."""
    perde = {p for p, pg in pages.items() if pg.perde}
    if not perde:
        return
    flat: list[Block] = []
    for ch in ms.chapters:
        if ch.title:
            first = ch.blocks[0].pages[:1] if ch.blocks else []
            flat.append(Block("subhead", ch.title, list(first)))
        flat += ch.blocks
    out: list[Chapter] = [Chapter(None, [])]
    i = 0
    while i < len(flat):
        b = flat[i]
        p = b.pages[0] if b.pages else None
        if p in perde:
            ch = Chapter(b.text, [], "perde")
            out.append(ch)
            i += 1
            while i < len(flat) and flat[i].pages and flat[i].pages[0] == p:
                ch.blocks.append(Block("perde_alti", flat[i].text, flat[i].pages))
                i += 1
            continue
        out[-1].blocks.append(b)
        i += 1
    ms.chapters = [c for c in out if c.blocks or c.title]


_SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _finish_layout(ms: Manuscript, pages: dict, notes: dict, print_style: bool = False) -> None:
    """Bölümler kurulduktan sonra: gönderme işaretleri bölüm içinde 1'den numaralanır («[k]»), notlar bölüm sonuna
    «[k] metin» paragrafı olur (e-kitap bunları kitabın sonundaki notlara bağlar); bölüm başındaki italik / sağa
    yaslı paragraflar epigraf; perde sayfasıyla açılan bölüm perde, o sayfadaki kısa paragraf perde altı."""
    if not print_style:
        _recut_perde(ms, pages)
    for ch in ms.chapters:                            # ardışık şiir blokları (dörtlükler) tek şiir
        merged: list[Block] = []
        for b in ch.blocks:
            if b.kind == "poem" and merged and merged[-1].kind == "poem":
                merged[-1].text += "\n\n" + b.text
                merged[-1].pages += [p for p in b.pages if p not in merged[-1].pages]
            elif (b.kind == "subhead" and merged and merged[-1].kind == "subhead" and b.pages[:1] == merged[-1].pages[-1:]
                  and len(merged[-1].text) + len(b.text) <= 160):
                merged[-1].text += " " + b.text           # iki satıra bölünmüş ara başlık («… ÖRGÜTLENMESİ:» + «SOSYAL …»)
            else:
                merged.append(b)
        ch.blocks = merged
    if not print_style:
        # Bölüm adı yalnız etiketse («1. FASL», «BİRİNCİ BÖLÜM») ve bölüm bir ara başlıkla açılıyorsa ikisi tek perde
        # başlığıdır (Timaş Şer'î Siyaset: «1. Fasl [Emanetlerin Eda Edilmesi]» e-perde).
        from ..chapters import _label_only
        for ch in ms.chapters:
            if ch.title and _label_only(ch.title) and ch.blocks and ch.blocks[0].kind == "subhead":
                ch.title = f"{ch.title} {ch.blocks.pop(0).text}"
                ch.kind = "perde"
    for ch in ms.chapters:
        k = 0
        found: list[tuple[int, str]] = []

        def renum(m):
            nonlocal k
            key = (int(m.group(1)), m.group(2))
            text = notes.get(key) or notes.get((key[0] + 1, key[1]))
            if not text:
                return ""
            k += 1
            found.append((k, text))
            return str(k).translate(_SUP) if print_style else f"[{k}]"
        if ch.title:
            ch.title = _MARK.sub(renum, _clean_title(ch.title))
        for b in ch.blocks:
            if b.kind != "table":
                b.text = _MARK.sub(renum, b.text)
        first = ch.blocks[0].pages[0] if ch.blocks and ch.blocks[0].pages else None
        if ch.kind != "perde" and first is not None and pages.get(first) is not None and pages[first].perde:
            ch.kind = "perde"
            for b in ch.blocks:
                if b.pages and b.pages[0] == first and len(b.text) <= 120:
                    b.kind = "perde_alti"
        start = True                                  # bölüm ve alt bölüm başındaki italik / sağa yaslı: epigraf
        for b in ch.blocks:
            if b.kind in ("perde_alti", "subhead"):
                start = True
                continue
            if start and b.kind in ("italic", "right") and len(b.text) <= 600:
                b.kind = "epigraph"
                continue
            start = False
        if print_style:                               # basılı dizgi: bölüm sonunda «Notlar», üst simge numaralı
            ch.blocks += [Block("para", f"{str(n).translate(_SUP)} {t}", []) for n, t in found]
        else:
            ch.blocks += [Block("para", f"[{n}] {t}", []) for n, t in found]


def resplit(text: str, parts: list[str]) -> list[str]:
    """Okunmuş paragrafı dizgideki paragraf başlarından böler (`parts`: aynı sayfanın dizgiden paragrafları).
    Metin değişmez, yalnız bölünür: her paragraf başı okunmuş metinde aynen (ilk 30 harf, kelime başında)
    aranır; bulunamayan baş (font onarımı, tire birleşimi farkı) atlanır, paragraf orada bölünmez."""
    if len(parts) < 2:
        return [text]
    out, cur = [], 0
    for nxt in parts[1:]:
        probe = nxt[:30].strip()
        if len(probe) < 8:
            continue
        i = text.find(probe, cur + 1)
        if i <= cur or text[i - 1] != " ":
            continue
        out.append(text[cur:i].strip())
        cur = i
    out.append(text[cur:].strip())
    return [o for o in out if o]


def spaced_layout(generation_id: str) -> dict[int, list[str]] | None:
    """Sayfa no → dizgiden paragraflar (önünde boşluk bırakılan paragraflar dahil). PDF yoksa None."""
    try:
        from .. import db
        from ..document import _open_version, paragraphs_from_layout
        g = db.one("SELECT book_version_id FROM ed.generation WHERE id=%s", generation_id)
        doc, _ = _open_version(str(g["book_version_id"]))
    except Exception:  # noqa: BLE001 - dizgi okunamazsa okunmuş paragraflar olduğu gibi
        return None
    with doc:
        return {i: paragraphs_from_layout(p, spaced=True) for i, p in enumerate(doc, 1)}


_TITLE_END = re.compile(r"[.!?…:;,]$")


def _key(t: str) -> str:
    return re.sub(r"[^\w]", "", t.casefold())


def split_typeset(chapters: list[dict], paras: list[tuple[int, str]], lex=None) -> list[Chapter] | None:
    """Dizgiden bulunmuş bölümler (`editor.chapters`: [{title, page_from, page_to}]) üzerine okunmuş paragraflar.
    Bölümün ilk sayfasının başındaki başlık paragrafları gövdeden çıkar ve başlık metni olur (okunmuş metin
    font onarımından geçmiştir, PDF'in ham satırı geçmemiş olabilir). Tek «Kitap» bölümü bilgi taşımaz → None."""
    if len(chapters) < 2:
        return None
    out: list[Chapter] = []
    for ch in chapters:
        mine = [x for x in paras if ch["page_from"] <= x[0] <= ch["page_to"] and x[1].strip()]
        intro = ch["title"] == "Başlıksız başlangıç"
        title = None if intro else ch["title"]
        if title:
            want, got, k = _key(title), "", 0
            # başlık birkaç paragrafa bölünmüş olabilir («Birinci Kısım» / «1.»); başlıktan uzun olmayan,
            # cümle gibi bitmeyen kısa paragraflar başlığa aittir
            while (k < len(mine) and k < 4 and len(mine[k][1]) <= 80 and not _TITLE_END.search(mine[k][1].strip())
                   and len(got + _key(mine[k][1])) <= len(want) + 4):
                got += _key(mine[k][1])
                k += 1
            if k and (got == want or len(got) >= 0.6 * len(want)):
                title = " ".join(x[1].strip() for x in mine[:k])
                mine = mine[k:]
        blocks = [b for _, bs in normalize(mine, lex, headings=False) for b in bs]
        if blocks:                      # metni olmayan bölüm (hikâye dışı sayfalar) boş başlık basmaz
            out.append(Chapter(title, blocks))
    return out if sum(1 for c in out if c.title) >= 2 else None


def by_typeset(generation_id: str, paras: list[tuple[int, str]], lex=None) -> list[Chapter] | None:
    """Okunmuş kitabın bölümleri kitabın kendi dizgisinden; PDF yoksa ya da bölüm bulunamazsa None."""
    try:
        from .. import chapters as typeset
        found = typeset.for_generation(generation_id)
    except Exception:  # noqa: BLE001 - dizgi okunamazsa eski büyük harf kuralı
        return None
    return split_typeset(found, paras, lex) if found else None


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
