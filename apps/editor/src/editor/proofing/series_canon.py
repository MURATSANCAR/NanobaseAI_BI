"""Dizi tutarlılığı: a recurring character must match the other books of its series.

Series membership, in order of authority:
1. `book.universe` — the editor's own declaration (a story universe);
2. the series line of the imprint page ("<Ad> Kitaplar | 6", "<Ad> Kitaplığı / 4",
   "<Ad> Dizisi", "<Ad> Serisi") — read deterministically from the page that carries the
   ISBN, and from METADATA/SERIES claims of any generation of the book. A string without
   a series noun ("<Yayınevi> Çocuk") is a publisher's imprint, not a series, and is ignored.
Two series names are the same when one's words end the other's ("<yayınevi> çocuk <ad>
kitaplar" / "<ad> kitaplar").

A publisher's collection is not a story universe: its books have different authors and
unrelated casts. So a character recurs only when (a) its name is used as a proper name in
BOTH books (capitalised mid-sentence in the book's own text — "Anne", "babam", "fil" are
not), (b) it is not a credit of the book (author, illustrator, a name on the imprint
page), and (c) the two books are in one declared universe, or share an author, or the
author of either is unknown. Different known authors in a collection => a shared name is
a coincidence and is only listed (INFO).

For a recurring character the check compares, each rule exact over the ledger:
spelling of the name, kind, declared sex and age band, kinship stated in the character
descriptions, and the drawn appearance (CCIP distance between the two books' resolved
figures against the corpus-measured `ccip_same_max`).

Measured 2026-09-22 (docs/son-okuma/series_canon.md): the six books contain one real
same-series pair (a publisher's collection, different authors): 0 WARN, correct. No
two books share a story universe, so recall on a real recurring character is UNMEASURED.
"""

from __future__ import annotations

import re
import statistics
import unicodedata

import httpx

from .. import db, source
from ..config import settings

NAME = "series_canon"
VERSION = "1"
LABEL = "Dizi tutarlılığı"

# Turkish series nouns (a closed class of the language, not of one publisher)
_SERIES_NOUN = r"(?:Kitaplar[ıi]?|Kitapl[ıi][ğg][ıi]|Dizisi|Serisi|Seti)"
_CAPWORD = r"[A-ZÇĞİÖŞÜÂÎÛ][A-Za-zÇĞİÖŞÜÂÎÛçğıöşüâîû]+"
SERIES_RE = re.compile(rf"((?:{_CAPWORD}[ \t]+){{1,4}})({_SERIES_NOUN})(?:[ \t]*[|/][ \t]*(\d{{1,4}}))?")
ISBN_RE = re.compile(r"ISBN|97[89][-\s]?\d{1,5}[-\s]?\d{1,7}[-\s]?\d{1,7}[-\s]?\d")

# Kinship / relation words as they appear in descriptions ("Ayşe'nin dedesi").
_KIN = {"annesi": "anne", "babası": "baba", "dedesi": "dede", "ninesi": "nine",
        "anneannesi": "anneanne", "babaannesi": "babaanne", "kardeşi": "kardeş",
        "ablası": "abla", "abisi": "abi", "ağabeyi": "abi", "kuzeni": "kuzen",
        "amcası": "amca", "dayısı": "dayı", "halası": "hala", "teyzesi": "teyze",
        "eniştesi": "enişte", "yengesi": "yenge", "oğlu": "oğul", "kızı": "kız",
        "eşi": "eş", "karısı": "eş", "kocası": "eş", "torunu": "torun",
        "arkadaşı": "arkadaş", "öğretmeni": "öğretmen", "öğrencisi": "öğrenci",
        "kedisi": "evcil hayvan", "köpeği": "evcil hayvan"}
_KIN_RE = re.compile(r"([A-ZÇĞİÖŞÜ][\wçğıöşü]*(?:\s[A-ZÇĞİÖŞÜ][\wçğıöşü]*)*)['’]n?[ıiuü]n\s+"
                     r"(?:(?:küçük|büyük|en yakın|yakın|sevgili)\s+)?(" + "|".join(_KIN) + r")(?:d[ıi]r)?\b")
# a capital here does not mark a proper name: sentence and dialogue starts
_OPENERS = set(".!?…:;\"“”«»'‘’-–—(\n")
# Share of mid-sentence occurrences written with a capital. Measured on all 150 names and
# aliases of the six books: kinship and common nouns ("Anne", "Babam", "Fil", "Martı")
# reach at most 0.67; names reach 0.875 and above. 0.8 sits in the empty gap.
PROPER_MIN = 0.8


def _proper_min() -> float:
    """The same threshold editor.naming reads from EDITOR_PROPER_NAME_MIN_SHARE when the
    settings carry it; the measured constant above otherwise (one number, one place)."""
    return float(getattr(settings(), "proper_name_min_share", PROPER_MIN))
# Credit labels of a Turkish imprint page; the capitalised words after one are a person.
_CREDIT_LABEL = (r"(?:Yazar[ıi]?|Çizer|Resimleyen|Resimler|Çizimler|Çeviri|Çeviren|Proje Editörü|Editör|"
                 r"Yayın Yönetmeni|Kapak Tasarım[ıi]?|İç Tasarım[ıi]?|Redaksiyon|Düzelti|Grafik Tasarım[ıi]?)")
_CREDIT_RE = re.compile(_CREDIT_LABEL + r"[ \t]*[:|]?[ \t]*((?:(?!" + _CREDIT_LABEL + r")" + _CAPWORD
                        + r"[ \t]*){1,4})")
FLAT_KINDS = {"UNKNOWN", "OTHER"}
MIN_FIGURES = 2       # resolved drawings per book before the drawings are compared (see docs)


# ------------------------------------------------------------ text helpers
def tr_lower(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").replace("I", "ı").replace("İ", "i").lower()


def fold(s: str) -> str:
    """Name key: Turkish lower case, circumflex dropped, apostrophe suffix cut, spaces
    collapsed. "Kâmil" and "Kamil" share a key; the raw forms still differ."""
    s = tr_lower(s).replace("â", "a").replace("î", "i").replace("û", "u")
    s = re.sub(r"['’]\w*", "", s)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def series_names(text: str) -> list[tuple[str, int | None, str]]:
    """(key, number in the series, the name as printed)."""
    out = []
    for m in SERIES_RE.finditer(text or ""):
        words = fold(m.group(1)).split() + [fold(m.group(2))]
        out.append((" ".join(words), int(m.group(3)) if m.group(3) else None,
                    re.sub(r"\s+", " ", m.group(1) + m.group(2)).strip()))
    return out


def same_series(a: str, b: str) -> bool:
    wa, wb = a.split(), b.split()
    short, long_ = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    return len(short) >= 2 and long_[-len(short):] == short


def book_text(gid: str) -> list[tuple[int, str]]:
    return [(p["page_no"], "\n\n".join(s["text"] for s in p["spans"])) for p in source.read(gid)]


def proper_share(name: str, pages: list[tuple[int, str]]) -> tuple[int, int]:
    """(mid-sentence occurrences, of which capitalised) of the name's first word."""
    first = fold(name).split()
    if not first:
        return 0, 0
    first = first[0]
    mid = cap = 0
    for _, text in pages:
        for m in re.finditer(r"[^\W\d_]+", text):
            if fold(m.group(0)) != first:
                continue
            i = m.start() - 1
            while i >= 0 and text[i] in " \t":
                i -= 1
            if i < 0 or text[i] in _OPENERS:
                continue
            mid += 1
            cap += m.group(0)[0].isupper()
    return mid, cap


def is_proper(name: str, pages: list[tuple[int, str]]) -> bool:
    mid, cap = proper_share(name, pages)
    return mid > 0 and cap / mid >= _proper_min()


# --------------------------------------------------------------- book facts
def _latest_generation(book_id: str) -> str | None:
    r = db.one("SELECT g.id FROM generation g JOIN book_version bv ON bv.id=g.book_version_id"
               " WHERE bv.book_id=%s AND EXISTS (SELECT 1 FROM character c WHERE c.generation_id=g.id)"
               " ORDER BY g.created_at DESC LIMIT 1", book_id)
    return str(r["id"]) if r else None


def _metadata(book_id: str) -> dict[str, list[str]]:
    rows = db.all_rows("SELECT DISTINCT c.subject, c.claim FROM claim c JOIN generation g ON g.id=c.generation_id"
                       " JOIN book_version bv ON bv.id=g.book_version_id WHERE bv.book_id=%s"
                       " AND c.kind='METADATA' AND c.status IN ('VERIFIED','EDITOR_APPROVED','EDITOR_CORRECTED')",
                       book_id)
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["subject"], []).append(r["claim"])
    return out


def _crm(book_id: str) -> dict:
    """Authors and illustrators from the publisher's CRM record (022_book_crm_record), when
    the table and a row exist; the CRM carries no series field."""
    if not db.one("SELECT to_regclass('ed.book_crm_record') AS t")["t"]:
        return {"authors": [], "illustrators": []}
    r = db.one("SELECT authors, illustrators FROM book_crm_record WHERE book_id=%s", book_id)
    return {"authors": list(r["authors"] or []), "illustrators": list(r["illustrators"] or [])} if r else \
        {"authors": [], "illustrators": []}


def book_facts(book_id: str, gid: str | None = None) -> dict:
    b = db.one("SELECT id, title, universe FROM book WHERE id=%s", book_id)
    gid = gid or _latest_generation(book_id)
    meta = _metadata(book_id)
    pages = book_text(gid) if gid else []
    imprint = [(p, t) for p, t in pages if ISBN_RE.search(t)]
    series: dict[str, dict] = {}
    for p, t in imprint:
        for name, no, shown in series_names(t):
            series.setdefault(name, {"name": name, "shown": shown, "number": no, "source": f"künye s.{p}"})
    for v in meta.get("SERIES", []) + meta.get("TITLE", []):
        for name, no, shown in series_names(v):
            series.setdefault(name, {"name": name, "shown": shown, "number": no, "source": "METADATA"})
    crm = _crm(book_id)
    authors = {fold(v) for v in meta.get("AUTHOR", []) + crm["authors"]}
    credits = {fold(v) for k in ("AUTHOR", "ILLUSTRATOR") for v in meta.get(k, [])}
    credits |= {fold(v) for v in crm["authors"] + crm["illustrators"]}
    credits |= {fold(m.group(1)) for _, t in imprint for m in _CREDIT_RE.finditer(t)}
    return {"book_id": str(b["id"]), "title": b["title"], "gid": gid,
            "universe": fold(b["universe"]) if b["universe"] else None,
            "series": list(series.values()), "authors": authors,
            "credits": credits, "pages": pages}


def _is_credit(key: str, credits: set[str]) -> bool:
    """A person of the imprint (author, editor, designer). A one-word key must equal a credit
    ("Can" is not "Samet Can"); a longer key may sit inside a credit line the layer ran
    together ("esra burak" in "burak genç esra burak")."""
    return key in credits or (len(key.split()) >= 2 and any(
        re.search(rf"(?<!\w){re.escape(key)}(?!\w)", c) for c in credits))


def characters(facts: dict) -> list[dict]:
    """Characters of the book that can recur: named with a proper name, not a credit."""
    if not facts["gid"]:
        return []
    out = []
    for c in db.all_rows("SELECT id, canonical_name, aliases, kind, traits, description, first_page,"
                         " identity_status FROM character WHERE generation_id=%s ORDER BY first_page",
                         facts["gid"]):
        names = [n for n in [c["canonical_name"], *c["aliases"]] if n and n.strip()]
        keys = {}
        for n in names:
            k = fold(n)
            if not k or _is_credit(k, facts["credits"]):
                continue
            if is_proper(n, facts["pages"]):
                keys[k] = n
        if keys:
            out.append({**c, "id": str(c["id"]), "keys": keys})
    return out


def _lev1(a: str, b: str) -> bool:
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    s, l = (a, b) if len(a) < len(b) else (b, a)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


def relations(chars: list[dict]) -> dict[tuple[str, str], set[str]]:
    """(character id, other character id) -> relation words, read from descriptions:
    "Ayşe'nin dedesi" in the description of X means X is Ayşe's grandfather."""
    by_key = {k: c["id"] for c in chars for k in c["keys"]}
    out: dict[tuple[str, str], set[str]] = {}
    for c in chars:
        for m in _KIN_RE.finditer(c["description"] or ""):
            other = by_key.get(fold(m.group(1)))
            if other and other != c["id"]:
                out.setdefault((c["id"], other), set()).add(_KIN[m.group(2)])
    return out


# ------------------------------------------------------------- appearance
def _figures(character_id: str) -> list[dict]:
    return db.all_rows("SELECT cm.page_no, fe.vector FROM character_mention cm JOIN figure_embedding fe"
                       " ON fe.mention_id=cm.id AND fe.model='ccip' WHERE cm.character_id=%s"
                       " AND cm.resolution='RESOLVED' ORDER BY cm.page_no", character_id)


def cross_distance(a: list[list[float]], b: list[list[float]]) -> float | None:
    """Median CCIP distance between every figure of A and every figure of B."""
    if not a or not b:
        return None
    with httpx.Client(base_url=settings().embed_url, timeout=120) as c:
        m = c.post("/differences", json={"features": a + b}).json()["matrix"]
    return statistics.median(m[i][len(a) + j] for i in range(len(a)) for j in range(len(b)))


# -------------------------------------------------------------------- run
def _peers(me: dict) -> list[tuple[dict, str]]:
    """Other books of the same series and why they are peers."""
    out = []
    for r in db.all_rows("SELECT id FROM book WHERE id<>%s ORDER BY created_at", me["book_id"]):
        other = book_facts(str(r["id"]))
        if me["universe"] and other["universe"] == me["universe"]:
            out.append((other, "universe"))
            continue
        hit = [(a, b) for a in me["series"] for b in other["series"] if same_series(a["name"], b["name"])]
        if hit:
            out.append((other, "series"))
            other["matched_series"] = hit[0][1]
    return out


def _compare(a: dict, b: dict, me: dict, other: dict, rel_a: dict, rel_b: dict, pair_ids: dict,
             universe: bool) -> list[dict]:
    """Findings for one recurring character: A in this book, B in the other book."""
    out = []
    page = a["first_page"]
    where = f"«{other['title']}»" + (f" (dizinin {other['matched_series']['number']}. kitabı)"
                                     if other.get("matched_series", {}).get("number") else "")
    base = {"page": page, "details": {"character": a["canonical_name"], "other_book": other["title"],
                                     "other_character": b["canonical_name"], "other_first_page": b["first_page"],
                                     "same_universe_basis": universe}}
    shared = set(a["keys"]) & set(b["keys"])
    for k in shared:
        if a["keys"][k] != b["keys"][k]:
            out.append({**base, "severity": "WARN", "quote": a["keys"][k], "suggestion": b["keys"][k],
                        "message": f"Ad yazımı dizideki öbür kitaptan farklı: bu kitapta «{a['keys'][k]}», "
                                   f"{where} kitabında «{b['keys'][k]}» (s.{b['first_page']})."})
    if not shared:
        ka, kb = sorted(a["keys"])[0], sorted(b["keys"])[0]
        out.append({**base, "severity": "WARN", "quote": a["keys"][ka], "suggestion": b["keys"][kb],
                    "message": f"Ad yazımı dizideki öbür kitaptan bir harf farklı olabilir: bu kitapta "
                               f"«{a['keys'][ka]}», {where} kitabında «{b['keys'][kb]}». Aynı karakterse yazım "
                               f"birleştirilmeli; farklı karakterse yok sayın."})
    if a["kind"] not in FLAT_KINDS and b["kind"] not in FLAT_KINDS and a["kind"] != b["kind"]:
        out.append({**base, "severity": "WARN",
                    "message": f"«{a['canonical_name']}» bu kitapta {a['kind']}, {where} kitabında {b['kind']}. "
                               f"Hikâye bu değişikliği açıklamıyorsa dizi tutarsızlığı."})
    ta, tb = a["traits"] or {}, b["traits"] or {}
    for field, tr in (("sex", "cinsiyet"), ("age_band", "yaş grubu")):
        va, vb = ta.get(field), tb.get(field)
        if va and vb and "UNKNOWN" not in (va, vb) and va != vb:
            out.append({**base, "severity": "WARN",
                        "message": f"«{a['canonical_name']}» için {tr} farklı: bu kitapta {va}, {where} kitabında "
                                   f"{vb}. Hikâye açıklamıyorsa (ör. zaman geçmesi) dizi tutarsızlığı."})
    for (x, y), rels in rel_a.items():
        if x != a["id"] or y not in pair_ids:
            continue
        other_rels = rel_b.get((b["id"], pair_ids[y]["b"]))
        if other_rels and not (rels & other_rels):
            out.append({**base, "severity": "WARN",
                        "message": f"Akrabalık farklı: bu kitapta «{a['canonical_name']}», «{pair_ids[y]['name']}» "
                                   f"için {'/'.join(sorted(rels))}; {where} kitabında {'/'.join(sorted(other_rels))}.",
                        "details": {**base["details"], "description": a["description"],
                                    "other_description": b["description"]}})
    fa, fb = _figures(a["id"]), _figures(b["id"])
    # One drawing against one is a single noisy distance (measured: 2 of 3 same-character
    # 1-vs-1 comparisons crossed the threshold); at least MIN_FIGURES on each side.
    if len(fa) < MIN_FIGURES or len(fb) < MIN_FIGURES:
        return out
    d = cross_distance([list(f["vector"]) for f in fa], [list(f["vector"]) for f in fb])
    if d is not None and d >= settings().ccip_same_max:
        out.append({**base, "severity": "WARN",
                    "message": f"«{a['canonical_name']}» çizimi {where} kitabındaki çiziminden farklı görünüyor "
                               f"(CCIP medyan uzaklık {d:.3f} ≥ {settings().ccip_same_max}). Saç, ten, göz, "
                               f"ayırt edici işaretleri iki kitabın sayfalarında karşılaştırın.",
                    "details": {**base["details"], "ccip_median": round(d, 4),
                                "pages": [f["page_no"] for f in fa], "other_pages": [f["page_no"] for f in fb]}})
    return out


def match(ca: list[dict], cb: list[dict]) -> list[tuple[dict, dict]]:
    """Same proper-name key, or (both confirmed, same concrete kind) one letter apart."""
    pairs, used = [], set()
    for a in ca:
        for b in cb:
            if b["id"] in used:
                continue
            if set(a["keys"]) & set(b["keys"]):
                pairs.append((a, b)); used.add(b["id"]); break
    for a in ca:
        if any(a is p[0] for p in pairs):
            continue
        for b in cb:
            if b["id"] in used or a["identity_status"] != "CONFIRMED" or b["identity_status"] != "CONFIRMED":
                continue
            if a["kind"] in FLAT_KINDS or a["kind"] != b["kind"]:
                continue
            if any(len(x) >= 5 and _lev1(x, y) for x in a["keys"] for y in b["keys"]):
                pairs.append((a, b)); used.add(b["id"]); break
    return pairs


async def run(generation_id: str):
    gen = db.one("SELECT bv.book_id FROM generation g JOIN book_version bv ON bv.id=g.book_version_id"
                 " WHERE g.id=%s", generation_id)
    me = book_facts(str(gen["book_id"]), generation_id)
    stats = {"series": me["series"], "universe": me["universe"], "peers": []}
    if not me["series"] and not me["universe"]:
        return [{"page": None, "severity": "INFO",
                 "message": "Kitabın dizisi belirlenemedi (künyede dizi adı yok, kitaba evren/dizi girilmemiş); "
                            "dizi karşılaştırması yapılmadı."}], stats
    peers = [p for p in _peers(me) if p[0]["gid"]]
    label = me["universe"] or ", ".join(s["shown"] + (f" (dizinin {s['number']}. kitabı)" if s["number"] else "") for s in me["series"])
    if not peers:
        return [{"page": None, "severity": "INFO",
                 "message": f"Dizi: {label}. Bu diziden analiz edilmiş başka kitap yok; karşılaştırma yapılmadı."}], stats
    findings = []
    ca = characters(me)
    rel_a = relations(ca)
    for other, why in peers:
        universe = why == "universe" or bool(me["authors"] & other["authors"])
        coincidence = not universe and me["authors"] and other["authors"]
        cb = characters(other)
        pairs = match(ca, cb)
        stats["peers"].append({"title": other["title"], "basis": why, "authors": sorted(other["authors"]),
                               "recurring_candidates": [(a["canonical_name"], b["canonical_name"]) for a, b in pairs],
                               "proper_named": [len(ca), len(cb)], "different_authors": bool(coincidence)})
        if not pairs:
            findings.append({"page": None, "severity": "INFO",
                             "message": f"Dizi: {label}. «{other['title']}» ile karşılaştırıldı: ortak karakter yok."})
            continue
        if coincidence:
            findings.append({"page": None, "severity": "INFO",
                             "message": f"«{other['title']}» aynı dizide ama yazarları farklı (bağımsız hikâyeler); "
                                        f"aynı adlı karakterler tesadüf sayıldı: "
                                        + ", ".join(a["canonical_name"] for a, _ in pairs) + "."})
            continue
        rel_b = relations(cb)
        pair_ids = {a["id"]: {"b": b["id"], "name": a["canonical_name"]} for a, b in pairs}
        for a, b in pairs:
            findings.extend(_compare(a, b, me, other, rel_a, rel_b, pair_ids, universe))
    return findings, stats
