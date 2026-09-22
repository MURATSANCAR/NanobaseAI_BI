"""Künye — CRM karşılaştırması: the imprint as printed in the book against the publisher's CRM
record of the same book. Deterministic, no model: every value compared is read from the page
text (source.read) with a pattern and from the stored CRM record, and every finding quotes
the printed line.

Where the CRM comes from: the editor's GPU host cannot reach the CRM. The CRM connector
(connectors/crm_covers.py) already runs where the CRM is reachable and posts each book's CRM
record, which catalog.store_crm_record keeps in ed.book_crm_record (title, authors,
illustrators, ISBN, stock code). This check reads that row; it never talks to the CRM and
never writes anything. The imprint fields the connector does not carry yet (edition number
and date, target age, shelf, series and its number, publication number, page count,
translators, editor / project editor / publishing director, the participation roles) are
read from the row's `imprint` object when present (the connector/table change is in
docs/son-okuma/imprint_crm.md); without it only the base fields are compared.

Comparisons (each explained with its measurement in the doc):
  ISBN          every ISBN printed in the book: check digit (ISBN-13 mod 10, ISBN-10 mod 11);
                equal to the CRM ISBN (digits only)
  title         the CRM title found in the book's text (folded); not found = could not be
                compared (titles are often drawn, not typeset) — INFO, never a mismatch
  people        each CRM contributor (author, illustrator, translator; editor, project
                editor, publishing director when known) found in the book: the same name,
                a name that differs (a surname more or less, e.g. printed «AD SOYAD
                EKSOYAD», CRM «Ad Soyad»), or not in the book; a person the book labels
                (Yazar:, Çizer:, Çeviri:) that the CRM does not have
  edition       «N. Baskı» and its month/year against the CRM edition number and date
  age           printed «a - b Yaş» against the CRM shelf range and the CRM target age
  series        printed «<Dizi> / n» against the CRM imprint series (name words and number)
  pub. number   printed «Yayın No» / «YAYINLARI / n» against the CRM publication number
  pages         the PDF's page count against the CRM page count"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from .. import db, source

NAME = "imprint_crm"
VERSION = "1"
LABEL = "Künye — CRM karşılaştırması"

MONTHS = ["ocak", "subat", "mart", "nisan", "mayis", "haziran", "temmuz", "agustos", "eylul", "ekim",
          "kasim", "aralik"]
MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
             "Kasım", "Aralık"]
# Dynamics stores date-times in UTC; a «Temmuz 2026» printing is 2026-06-30T21:00Z. The
# publisher is in Istanbul (UTC+3 all year since 2016).
LOCAL = timezone(timedelta(hours=3))
ASCII = str.maketrans("çğıöşüâîû", "cgiosuaiu")
# words that name the KIND of a series, not the series («… Kitaplığı», «… Kitaplar»). A publisher's
# own name is NOT listed here: when the CRM writes the imprint in front of the series
# («<Yayınevi> Çocuk <Dizi> Kitaplar») the comparison below accepts one name's words
# being contained in the other's, so no publisher is named in the code.
SERIES_GENERIC = {"kitapligi", "kitaplik", "kitaplar", "kitap", "dizisi", "dizi", "seri", "serisi", "cocuk",
                  "yayinlari", "yayinevi"}
ROLE_LABELS = {
    "AUTHOR": r"Yazar|Yazan|Yazarı",
    "ILLUSTRATOR": r"Çizer|Çizen|Resimleyen|Resimler|Resimleme|İllüstrasyon|Illüstrasyon",
    "TRANSLATOR": r"Çeviri|Çeviren|Tercüme|Türkçesi",
    "EDITOR": r"Editör",
    "PROJECT_EDITOR": r"Proje Editörü",
    "DIRECTOR": r"Yayın Yönetmeni",
}
ROLE_TR = {"AUTHOR": "yazar", "ILLUSTRATOR": "çizer", "TRANSLATOR": "çevirmen", "EDITOR": "editör",
           "PROJECT_EDITOR": "proje editörü", "DIRECTOR": "yayın yönetmeni"}
CRM_ROLE = {"Yazar": "AUTHOR", "Çizer": "ILLUSTRATOR", "Tercüme": "TRANSLATOR"}


# ----------------------------------------------------------------- text helpers
def fold(s: str | None) -> str:
    """Turkish-insensitive comparison form: «ŞİRİN», «Şirin», «SIRIN» are one word."""
    s = unicodedata.normalize("NFKC", s or "").replace("İ", "i").replace("I", "ı").casefold().translate(ASCII)
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def squash(s: str | None) -> str:
    """Folded, without spaces: a PDF that splits a word («SOYA D») still compares."""
    return fold(s).replace(" ", "")


def isbn_digits(s: str | None) -> str:
    return re.sub(r"[^0-9Xx]", "", s or "").upper()


def isbn_valid(d: str) -> bool:
    if len(d) == 13 and d.isdigit():
        return sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(d)) % 10 == 0
    if len(d) == 10 and d[:9].isdigit() and (d[9].isdigit() or d[9] == "X"):
        return sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(d)) % 11 == 0
    return False


ISBN_RE = re.compile(r"(?<![\d-])(97[89](?:[\s\-‐–]?\d){10}|\d(?:[\s\-‐–]?\d){8}[\s\-‐–]?[\dXx])(?![\d-])")


def printed_isbns(text: str) -> list[str]:
    """ISBN-like numbers next to the word ISBN or «Seri No» (a phone number is not an ISBN)."""
    out = []
    for m in re.finditer(r"(ISBN|Seri\s*No)", text, re.I):
        window = text[m.end(): m.end() + 60]
        n = ISBN_RE.search(window)
        if n:
            out.append(n.group(1).strip())
    return list(dict.fromkeys(out))


def local_date(v) -> datetime | None:
    if not v:
        return None
    d = v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(LOCAL)


def same_series(a: set[str], b: set[str]) -> bool:
    """Two series names (as sets of their non-generic words) name one series when both have
    a word left and the shorter one's words are all in the longer one («geyikli» in
    «<yayınevi> cocuk geyikli»)."""
    return bool(a) and bool(b) and (a <= b or b <= a)


def age_range(s: str | None) -> tuple[int, int] | None:
    m = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*ya[sş]", s or "", re.I)
    return (int(m.group(1)), int(m.group(2))) if m else None


# ----------------------------------------------------------------- reading the book
def imprint_pages(pages: list[dict]) -> list[dict]:
    """Pages that carry the imprint: an ISBN, a copyright line or a «Baskı» line. Measured on six
    books: always one front page (s2 or s3); none of their story pages matched."""
    out = []
    for p in pages:
        t = "\n".join(s["text"] for s in p["spans"])
        if re.search(r"ISBN|©|Sertifika\s*No|\d+\s*\.\s*Bask[ıi]", t, re.I):
            out.append(p)
    return out


def page_text(p: dict) -> str:
    return "\n".join(s["text"] for s in p["spans"])


def labelled_people(text: str) -> list[tuple[str, str, str]]:
    """(role, printed name, printed line) for «Çizer: X Y» and «Editör | X Y» lines."""
    out = []
    labels = "|".join(f"(?P<{k}>{v})" for k, v in ROLE_LABELS.items())
    name = r"((?:[A-ZÇĞİÖŞÜÂÎÛ][\wçğıöşüâîûÇĞİÖŞÜ’'\.-]*\s?){2,5})"
    for m in re.finditer(rf"(?<![\wçğıöşü])(?:{labels})\s*[:|]?\s*{name}", text):
        role = next(k for k in ROLE_LABELS if m.group(k))
        printed = m.group(len(ROLE_LABELS) + 1).strip()
        # the name ends where the next label starts («Ad Soyad Proje Editörü …»)
        cut = re.split(rf"\s(?:{'|'.join(ROLE_LABELS.values())}|Kapak|İç|Baskı|Yayın|ISBN|Raf)\b", printed)[0]
        cut = cut.strip(" .:|")
        if len(cut.split()) >= 2:
            out.append((role, cut, m.group(0).strip()))
    return out


_LABEL_RE = re.compile(r"^(?:" + "|".join(ROLE_LABELS.values()) + r")\s*[:|]?\s*", re.I)


def name_line(text: str) -> str | None:
    """A span that is only a name: a bio header, «Çizer: X Y», an OCR «**Editör:** X Y».
    2-6 words, no sentence punctuation inside; markdown, edge punctuation and a leading role
    label are removed. None for running text."""
    t = re.sub(r"[*#_]+", " ", text).strip(" .,:;|-–•\t")
    t = _LABEL_RE.sub("", t).strip(" .,:;|-–")
    words = t.split()
    if not 2 <= len(words) <= 6 or re.search(r"[.!?…:;]", t):
        return None
    return t


def _merge_split(line_toks: list[str], want: list[str]) -> list[str]:
    """A PDF that breaks a word («SOYA D») gives two tokens; join neighbours that make a CRM token."""
    out, i = [], 0
    while i < len(line_toks):
        for n in (3, 2):
            if "".join(line_toks[i:i + n]) in want and len(line_toks[i:i + n]) == n:
                out.append("".join(line_toks[i:i + n]))
                i += n
                break
        else:
            out.append(line_toks[i])
            i += 1
    return out


def find_person(crm_name: str, pages: list[dict]) -> dict:
    """Where the CRM's name is in the book and how it is printed there.
    SAME       a name line of the book is that name, or the name is in the text
    DIFFERENT  a name line shares at least two of its words and differs by exactly ONE name word
               (a surname more or less: «Ad Soyad» / «AD SOYAD EKSOYAD», «Ad İkinciad
               Soyad Eksoyad» / «AD İKİNCİAD EKSOYAD»). Two or more words of difference is another
               name on the same layout line (two credits the layer ran together), measured on the six books.
    ABSENT     neither"""
    from collections import Counter
    toks = fold(crm_name).split()
    want = squash(crm_name)
    if len(toks) < 2:
        return {"status": "SKIP"}
    best = None
    for p in pages:
        for s in p["spans"]:
            line = name_line(s["text"])
            if not line:
                continue
            lt = _merge_split(fold(line).split(), toks)
            if Counter(lt) == Counter(toks):
                return {"status": "SAME", "page": p["page_no"], "printed": line}
            shared = sum((Counter(lt) & Counter(toks)).values())
            diff = sum((Counter(lt) - Counter(toks)).values()) + sum((Counter(toks) - Counter(lt)).values())
            if best is None and shared >= 2 and diff == 1:
                best = {"status": "DIFFERENT", "page": p["page_no"], "printed": line}
    if best:        # the credit line differs; the exact name elsewhere (a web handle) does not undo it
        return best
    for p in pages:
        if want in squash(page_text(p)):
            return {"status": "SAME", "page": p["page_no"], "printed": crm_name}
    return {"status": "ABSENT"}


# ----------------------------------------------------------------- the CRM record
def crm_people(rec: dict) -> list[tuple[str, str]]:
    """(role, name) from the CRM: participation rows when the imprint object has them, the
    text fields otherwise; editor roles from the imprint object."""
    imp = rec.get("imprint") or {}
    out: list[tuple[str, str]] = []
    roles = imp.get("roles") or {}
    for crm_role, role in CRM_ROLE.items():
        for n in roles.get(crm_role, []):
            out.append((role, n))
    split = lambda s: [x.strip() for x in re.split(r"\s*[,;/&]\s*|\s+ve\s+", s or "") if x.strip()]  # noqa: E731
    for role, names in (("AUTHOR", rec.get("authors") or split(imp.get("authors_text"))),
                        ("ILLUSTRATOR", rec.get("illustrators") or split(imp.get("illustrators_text"))),
                        ("TRANSLATOR", split(imp.get("translators_text")))):
        for n in names:
            out.append((role, n))
    for role, key in (("EDITOR", "editor"), ("PROJECT_EDITOR", "project_editor"),
                      ("DIRECTOR", "publishing_director")):
        if imp.get(key):
            out.append((role, imp[key]))
    seen, uniq = set(), []
    for role, n in out:
        if (role, squash(n)) not in seen:
            seen.add((role, squash(n)))
            uniq.append((role, n))
    return uniq


def load_crm(generation_id: str) -> tuple[dict | None, int]:
    g = db.one("SELECT v.book_id, v.id AS bv FROM generation g JOIN book_version v ON v.id=g.book_version_id"
               " WHERE g.id=%s", generation_id)
    if g is None:
        raise KeyError(generation_id)
    n_pages = db.one("SELECT count(*) AS n FROM page WHERE book_version_id=%s", g["bv"])["n"]
    rec = db.one("SELECT to_jsonb(r) AS r FROM book_crm_record r WHERE book_id=%s", g["book_id"])
    return (rec["r"] if rec else None), n_pages


# ----------------------------------------------------------------- comparison
def compare(pages: list[dict], rec: dict | None, n_pages: int) -> tuple[list[dict], dict]:
    F: list[dict] = []

    def add(sev, page, msg, quote=None, sugg=None, **details):
        F.append({"page": page, "severity": sev, "message": msg, "quote": quote, "suggestion": sugg,
                  "details": details})

    if not rec:
        add("INFO", None, "Kitabın CRM kaydı yok (CRM bağlayıcısı bu kitabı eşleştiremedi); künye karşılaştırılamadı.")
        return F, {"crm": False}
    imp = rec.get("imprint") or {}
    ipages = imprint_pages(pages)
    itext = "\n".join(page_text(p) for p in ipages)
    ipage_no = ipages[0]["page_no"] if ipages else None
    stats = {"crm": True, "matched_by": rec.get("matched_by"), "imprint_pages": [p["page_no"] for p in ipages],
             "imprint_fields": bool(imp), "compared": []}

    def line_of(pattern: str) -> tuple[int | None, str | None, re.Match | None]:
        """(page, the printed words around the match, match): a quote short enough to find."""
        for p in ipages:
            for s in p["spans"]:
                m = re.search(pattern, s["text"], re.I)
                if m:
                    return p["page_no"], s["text"][m.start(): m.end() + 24].strip(), m
        return None, None, None

    # ---- ISBN
    crm_isbn = isbn_digits(rec.get("isbn") or imp.get("isbn13"))
    other_crm = {isbn_digits(imp.get(k)) for k in ("isbn10", "ebook_isbn")} - {""}
    book_isbns = printed_isbns(itext)
    stats["compared"].append("isbn")
    if crm_isbn and not isbn_valid(crm_isbn):
        add("WARN", None, f"CRM'deki ISBN'in denetim hanesi tutmuyor: {rec.get('isbn')}.",
            sugg="CRM kaydındaki ISBN'i düzeltin.", crm_isbn=rec.get("isbn"))
    if not book_isbns:
        add("WARN", ipage_no, "Künyede ISBN bulunamadı.", sugg="Künyeye ISBN'i ekleyin.", crm_isbn=rec.get("isbn"))
    for printed in book_isbns:
        d = isbn_digits(printed)
        pg, line, _ = line_of(re.escape(printed))
        if not isbn_valid(d):
            add("ERROR", pg, f"Künyedeki ISBN'in denetim hanesi tutmuyor: {printed}.", quote=printed,
                sugg=f"CRM'deki ISBN: {rec.get('isbn')}" if crm_isbn else None, printed=printed)
        if crm_isbn and d != crm_isbn:
            sev = "INFO" if d in other_crm else "ERROR"
            add(sev, pg, f"Künyedeki ISBN ({printed}) CRM'deki ISBN'den ({rec.get('isbn')}) farklı"
                + (" — CRM'de bu kitabın başka bir ISBN alanında kayıtlı." if sev == "INFO" else "."),
                quote=printed, sugg=f"ISBN: {rec.get('isbn')}", printed=printed, crm=rec.get("isbn"),
                matched_by=rec.get("matched_by"))

    # ---- title
    titles = imp.get("titles") or [rec.get("crm_title")]
    titles = [t for t in titles if t]
    if titles:
        stats["compared"].append("title")
        where = next(((p["page_no"], t) for t in titles for p in pages
                      if squash(t) and squash(t) in squash(page_text(p))), None)
        if where is None:
            add("INFO", None, f"CRM'deki kitap adı («{titles[0]}») kitabın metninde bulunamadı; ad kapakta "
                "çizim olarak basılmış olabilir, karşılaştırılamadı.", crm_title=titles[0])

    # ---- people
    people = crm_people(rec)
    stats["compared"].append("people")
    for role, name in people:
        hit = find_person(name, pages)
        if hit["status"] == "DIFFERENT":
            add("WARN", hit["page"], f"{ROLE_TR[role].capitalize()} adı kitapta «{hit['printed']}», CRM'de "
                f"«{name}» olarak yazılmış.", quote=hit["printed"],
                sugg="Adın doğru yazımını yazarla/CRM ile teyit edin.", role=role, crm=name, printed=hit["printed"])
        elif hit["status"] == "ABSENT":
            sev = "WARN" if role in ("AUTHOR", "ILLUSTRATOR", "TRANSLATOR") else "INFO"
            add(sev, ipage_no, f"CRM'de {ROLE_TR[role]} olarak kayıtlı «{name}» kitapta bulunamadı.",
                sugg="Künyeyi ya da CRM kaydını kontrol edin.", role=role, crm=name)
    crm_sq = {squash(n) for _, n in people}
    for p in ipages + [p for p in pages[:6] if p not in ipages]:
        for role, printed, line in labelled_people(page_text(p)):
            sq = squash(printed)
            if role in ("AUTHOR", "ILLUSTRATOR", "TRANSLATOR", "EDITOR", "PROJECT_EDITOR", "DIRECTOR") \
                    and not any(sq == c or (len(c) > 5 and (c in sq or sq in c)) for c in crm_sq):
                known = role in ("AUTHOR", "ILLUSTRATOR") or imp
                if known:
                    add("WARN", p["page_no"], f"Künyede {ROLE_TR[role]} olarak «{printed}» yazıyor; CRM'de bu "
                        "rolde böyle biri yok.", quote=line, sugg="CRM kaydını ya da künyeyi kontrol edin.",
                        role=role, printed=printed, crm=[n for r, n in people if r == role])

    # ---- edition
    pg, line, m = line_of(r"(\d{1,2})\s*\.\s*Bask[ıi]")
    if m and imp.get("edition_no") is not None:
        stats["compared"].append("edition")
        printed_no, crm_no = int(m.group(1)), int(imp["edition_no"])
        if printed_no != crm_no:
            add("WARN", pg, f"Künyede {printed_no}. baskı yazıyor; CRM'de kayıtlı son baskı {crm_no}."
                + (" Bu dosya daha eski bir baskıya ait olabilir." if printed_no < crm_no else ""),
                quote=line, sugg=f"Yeni baskıysa künyeyi «{crm_no}. Baskı» yapın; değilse CRM'i düzeltin.",
                printed=printed_no, crm=crm_no)
        else:
            mm = re.search(r"Bask[ıi]\W{0,4}(" + "|".join(MONTHS_TR) + r")\W{0,3}(\d{4})", line, re.I)
            when = local_date(imp.get("edition_date"))
            if mm and when:
                pm = MONTHS.index(fold(mm.group(1))) + 1
                if (int(mm.group(2)), pm) != (when.year, when.month):
                    add("INFO", pg, f"Künyede baskı tarihi {mm.group(1)} {mm.group(2)}; CRM'de "
                        f"{MONTHS_TR[when.month - 1]} {when.year}.", quote=line,
                        printed=f"{mm.group(1)} {mm.group(2)}", crm=when.date().isoformat())

    # ---- age
    pg, line, m = line_of(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*ya[sş]")
    if m and imp:
        stats["compared"].append("age")
        printed = (int(m.group(1)), int(m.group(2)))
        shelf = age_range(imp.get("shelf_text"))
        if shelf and shelf != printed:
            add("WARN", pg, f"Künyedeki raf yaşı {printed[0]}-{printed[1]}; CRM'deki raf «{imp['shelf_text']}».",
                quote=line, printed=list(printed), crm=imp.get("shelf_text"))
        lo, hi = imp.get("age_from"), imp.get("age_to")
        if lo is not None and hi is not None and not (printed[0] <= int(lo) and int(hi) <= printed[1]):
            add("WARN", pg, f"Künyede {printed[0]}-{printed[1]} yaş yazıyor; CRM'deki hedef yaş {lo}-{hi} bu "
                "aralığın dışına taşıyor.", quote=line, sugg="Hedef yaşı CRM'de ya da künyede düzeltin.",
                printed=list(printed), crm=[lo, hi])
        ages = [int(x) for x in re.findall(r"\d{1,2}", imp.get("ages_text") or "")]
        if ages and lo is not None and hi is not None and not any(int(lo) <= a <= int(hi) for a in ages):
            add("INFO", None, f"CRM kendi içinde tutarsız: hedef yaş {lo}-{hi}, yaş etiketleri "
                f"«{imp['ages_text']}».", crm_target=[lo, hi], crm_ages=imp.get("ages_text"))

    # ---- series
    series_name = imp.get("imprint_series") or imp.get("series")
    if imp and series_name:
        stats["compared"].append("series")
        cands = []
        for p in ipages:
            for s in p["spans"]:
                for mm in re.finditer(r"((?:[A-ZÇĞİÖŞÜ][\wçğıöşü]+\s+){0,3}(?:Kitaplığı|Kitaplar|Dizisi|Serisi))"
                                      r"\s*[/|]?\s*(\d{1,3})?", s["text"]):
                    cands.append((p["page_no"], mm.group(0).strip(), mm.group(1), mm.group(2)))
        key = lambda n: {w for w in fold(n).split() if w not in SERIES_GENERIC}  # noqa: E731
        crm_names = [n for n in (imp.get("imprint_series"), imp.get("series")) if n]
        if not cands:
            add("INFO", ipage_no, f"CRM'de kitap «{series_name}» dizisinde"
                + (f" ({imp['imprint_series_no']}. kitap)" if imp.get("imprint_series_no") else "")
                + "; künyede dizi adı bulunamadı.", crm=series_name)
        else:
            pgc, linec, printed, num = cands[0]
            if not same_series(key(printed), key(imp.get("imprint_series") or series_name)):
                also = [n for n in crm_names if same_series(key(printed), key(n))]
                add("WARN", pgc, f"Künyede dizi «{printed}»; CRM'in künye dizisi alanında «{series_name}»"
                    + (f" (CRM'in dizi alanında ise «{also[0]}»: CRM'in iki alanı birbirini tutmuyor)" if also else "")
                    + ".", quote=linec, sugg="Dizi adını CRM ile künyede aynı yapın.", printed=printed,
                    crm=crm_names)
            no = imp.get("imprint_series_no")
            if num and no and str(no).strip() != num:
                add("WARN", pgc, f"Künyede dizi numarası {num}; CRM'de {no}.", quote=linec, printed=num, crm=no)

    # ---- publication number
    pub = imp.get("publication_no")
    if pub:
        pg, line, m = line_of(r"(?:Yay[ıi]n\s*No|YAYINLARI)\s*[:|/]?\s*(\d{1,6})\b")
        if m:
            stats["compared"].append("publication_no")
            if m.group(1) != str(pub).strip():
                same_as_series = str(imp.get("imprint_series_no") or "").strip() == m.group(1)
                add("WARN", pg, f"Künyedeki yayın numarası {m.group(1)}; CRM'de {pub}."
                    + (" Basılı sayı dizi numarasıyla aynı: dizi numarası yayın numarası yerine yazılmış olabilir."
                       if same_as_series else ""), quote=line, sugg=f"Yayın No: {pub}",
                    printed=m.group(1), crm=pub)

    # ---- page count
    if imp.get("page_count"):
        stats["compared"].append("pages")
        if int(imp["page_count"]) != n_pages:
            add("WARN", None, f"PDF {n_pages} sayfa; CRM'de sayfa sayısı {imp['page_count']}.",
                printed=n_pages, crm=imp["page_count"])
    return F, stats


async def run(generation_id: str):
    pages = await asyncio.to_thread(source.read, generation_id)
    rec, n_pages = await asyncio.to_thread(load_crm, generation_id)
    return compare(pages, rec, n_pages)
