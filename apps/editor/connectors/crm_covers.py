#!/usr/bin/env python3
"""CRM connector (cover + publisher record). Runs where the publisher's CRM is reachable
(the editor's GPU host is not on that network), for every book the editor knows.

  1. asks the editor for its books (title, other spellings `titles` — the cleaned file name
     first —, verified ISBNs, verified authors)                GET  /v1/catalog/cover-requests
  2. reads the CRM book list ONCE (new_kitapBase, ~14k rows) and matches each book; every step
     tries all of the book's names before the next, weaker step:
       ISBN      the ISBN in the card was verified verbatim on the book's imprint page
       TITLE     folded title equal to the CRM name / book name / product name
                 (folding: Turkish letters to ASCII, punctuation and dashes to spaces, so a
                 file-name title like «anne-terligi» equals «Anne Terliği»)
       COMPACT   only when no title is equal: the same folded title with its spaces removed
                 («Dijital Dünyada Ebeveyn Olmak» = «Dijital Dünyada E-beveyn Olmak»: a dash or
                 space inside a word is spelling, not a different book)
       SEGMENT   only when no title is equal: the first « - » part of the CRM name (a trailing
                 «(Ciltli)»-like note removed) equals the title, spaces aside: the CRM name
                 carries the series after the book's own name («Emircan Tasarrufu Öğreniyor -
                 Yaşasın Okuyorum» = «emircantasarrufuogreniyor»)
       PARTIAL   only when nothing is equal: the editor title's words (at least two) open
                 the CRM title word by word, each word a prefix («kaybolan balinalar» →
                 «Kaybolan Balinaların Şarkısı»); a number or a word of one or two letters must
                 be equal, not a prefix («3 kitap» is not «3N Kitap Kırtasiye», «kayi I» is not
                 «Kayıp İslam Tarihi»), a prefix covers at least 60% of its word (a Turkish suffix,
                 «dinozor» → «Dinozorla»; not another word, «kitap» → «Kitapkıran»); a record that is not a book (bookmark, postcard, box set,
                 bulletin, test booklet) or was cancelled («(İptal Edildi)») is never a partial match
     several records left → the editor's verified author narrows them; records that still
     share one folded title (a trailing «(Önceki Ebat)»-like note aside) and one author (an
     empty author field aside) are editions of one book (matched_by gets
     «+EDITIONS»): the record carrying a project card, else the newest, gives the text, and
     cover images are collected from all of them. Different titles left = AMBIGUOUS,
     nothing is guessed; if they still share the book's own name (first part: «Penguen Karcan
     - Mini Masallar 3» and «Penguen Karcan - Penton The Penguin (İngilizce)») that name is sent
     as `crm_title` without a record, so the editor can name the book (editor.book_title).
  3. publisher record for the card: authors (new_yazartext, else the «Yazar - …» participation
     rows, else the project's probable author), illustrators (new_cizerlertext), summary
     (web text > new_ozet > old summary > the project's one-sentence idea), ISBN, stock code,
     first publication date, and the publisher's classification of the book — target audience
     (new_hedefkitle), genres (new_turlertext), web categories, target age range, page count —
     which decides what the editor reads the book as (editor.book_type)
  4. every image the CRM knows for the book with its date: the published cover
     (new_kitap.new_resimurl, dated by the record) and the cover alternatives of the book's
     project (new_kapakalternatifi.new_Link, dated by CreatedOn); the NEWEST readable one wins
     (rule given by the user, 2026-09-20). The CRM stores paths, not bytes → CRM_IMAGE_ROOTS.
  5. posts the result, with or without an image                POST /v1/catalog/crm-lookups

Only what is new or changed (kullanıcı kararı 2026-10-03): matching runs in memory for every book
(one CRM read), but a book is read in full and posted only when it was never looked up, its match
differs from its last lookup (another record, another outcome, another name), or one of its CRM
records was modified / its project got a cover alternative after the last lookup. `--full`
posts every book (first fill, or after a rule change).

Read-only on the CRM. Configuration comes from the environment:
  EDITOR_CATALOG_BASE, EDITOR_CATALOG_KEY   the card service (test host timer: scripts/server/editor-crm-connector.*)
  CRM_CONNECTION_JSON             path of {host, port, user, password, database}
  CRM_IMAGE_ROOTS                 JSON: how a stored path becomes a readable location,
                                  e.g. {"resimurl": "/mnt/crm-web/kitap", "C:\\\\cube\\\\Timas_Folder_Entegrasyon": "/mnt/crm-cube"}

`--dry-run TITLE...` matches the given titles against the CRM and prints what would be
posted, without calling the editor.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path, PureWindowsPath

PLACEHOLDER = re.compile(r"^(hi[cç]biri|none|yok)$", re.I)
ASCII = str.maketrans("çğıöşüâîû", "cgiosuaiu")
SUMMARY_FIELDS = ("new_kitaptanitimwebmetni", "new_ozet", "new_kitabineskiozeti")
AUDIENCE = {1: "CHILD", 2: "YOUNG", 3: "ADULT"}         # new_hedefkitle picklist


def norm_isbn(s: str | None) -> str:
    return re.sub(r"[^0-9Xx]", "", s or "").upper()


# editördeki başlık dosya adından gelebilir: «Dilek Agaci.indd», «…-arsiv.pdf» — uzantı başlığın parçası değil
DOC_EXT = re.compile(r"\.(indd|pdf|docx?|idml|rtf|txt|epub)\s*$", re.I)


def fold(s: str | None) -> str:
    s = DOC_EXT.sub("", unicodedata.normalize("NFKC", s or "").strip())
    s = s.casefold().translate(ASCII)
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def compact(s: str | None) -> str:
    """The folded title without spaces: «e-beveyn», «e beveyn» and «ebeveyn» are one spelling."""
    return fold(s).replace(" ", "")


def plain(s: str | None) -> str:
    """CRM rich-text fields hold HTML (<p>, &uuml;); the card shows plain paragraphs."""
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|li)>", "\n", s or "")
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ")
    return "\n".join(x for x in (re.sub(r"[ \t]+", " ", ln).strip() for ln in s.splitlines()) if x)


def names(s: str | None) -> list[str]:
    return [x.strip() for x in re.split(r"\s*[,;/&]\s*|\s+ve\s+", s or "") if x.strip()]


# Kart servisi (EDITOR_CATALOG_BASE + EDITOR_CATALOG_KEY; /v1/catalog/...) — test sunucusundaki zamanlayıcı kart servisi
# tünelini ve köprünün zaten tuttuğu anahtarı kullanır, yeni anahtar taşınmaz.
PATHS = {"requests": "/v1/catalog/cover-requests", "store": "/v1/catalog/crm-lookups"}


def api(path: str, payload: dict | None = None) -> dict:
    base = os.environ["EDITOR_CATALOG_BASE"].rstrip("/")
    key = os.environ["EDITOR_CATALOG_KEY"]
    path = PATHS.get(path, path)
    req = urllib.request.Request(base + path,
                                 data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={"authorization": "Bearer " + key, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def crm():
    import pymssql
    c = json.load(open(os.environ["CRM_CONNECTION_JSON"]))
    return pymssql.connect(server=c.get("host") or c.get("server"), port=int(c.get("port", 1433)),
                           user=c.get("user") or c.get("username"), password=c["password"],
                           database=c.get("database", "Timas_MSCRM"), login_timeout=20, timeout=300)


NOTE = re.compile(r"\s*\((?![^()]*\b(?:ya[sş]|s[ıi]n[ıi]f)\b)[^()]*\)\s*$", re.I)


def first_part(s: str | None) -> str:
    """The book's own name inside a CRM name: the first « - » part, trailing notes removed."""
    t = re.sub(r"\s+", " ", s or "").strip()
    while NOTE.search(t) and NOTE.sub("", t).strip():
        t = NOTE.sub("", t).strip()
    return re.split(r"\s+[-–—]\s+", t)[0].strip()


def load_books(cur) -> list[dict]:
    cur.execute("SELECT new_kitapId, new_name, new_KitabnAd, new_urunadi, new_isbn, new_isbn13, new_resimurl,"
                " new_projekarti, new_yazartext, new_cizerlertext, new_StokKodu, new_ilkyayintarihi,"
                " new_hedefkitle, new_turlertext, new_webkategorileritext, new_hedefkitleyasbaslangic,"
                " new_hedefkitleyasbitis, new_sayfasayisi, ModifiedOn, " + ", ".join(f"CAST({f} AS nvarchar(max)) AS {f}" for f in SUMMARY_FIELDS) +
                " FROM new_kitapBase WHERE statecode=0")
    books = cur.fetchall()
    for b in books:
        b["_titles"] = {t for t in (fold(b.get(k)) for k in ("new_name", "new_KitabnAd", "new_urunadi")) if t}
        b["_compact"] = {t.replace(" ", "") for t in b["_titles"]}
        b["_first"] = {c for c in (compact(first_part(b.get(k))) for k in ("new_name", "new_KitabnAd", "new_urunadi"))
                       if c}
        b["_isbns"] = {i for i in (norm_isbn(b.get("new_isbn13")), norm_isbn(b.get("new_isbn"))) if i}
    return books


def _opens(words: list[str], title: str) -> bool:
    other = title.split()
    return len(words) >= 2 and len(other) >= len(words) and \
        all(o == w if w.isdigit() or o.isdigit() or len(w) <= 2 else o.startswith(w) and len(w) >= 0.6 * len(o)
            for w, o in zip(words, other))


#: Kitap olmayan CRM ürünü (kayıt adının kendi parçasında): kısmi eşlemede «Entel Dantel İşler» dosyası «Entel Dantel
#: İşler Ayraç» ürününe, «Dedektif Aynes» «Dedektif Aynes Seti (4 Kitap)»a gitmesin.
NOT_A_BOOK = frozenset({"ayrac", "kartpostal", "set", "seti", "bulten", "bulteni", "insert", "testi", "poster", "takvim",
                        "ajanda", "afis", "koli", "barkod"})
#: Kayıt adının herhangi bir yerinde kitap dışı ürün işareti: «… Seti (4 Kitap)», «Boş Kutu», «Market Grup».
NOT_A_BOOK_ANYWHERE = re.compile(r"\bbos (?:koli|kutu)\b|\btek barkod\b|\bmarket grup\b")
#: Ham adda set: «(4 Kitap)» (setin kendisi); «(10. Kitap)» setin onuncu kitabıdır, kitaptır.
SET_OF_BOOKS = re.compile(r"\(\s*\d+\s+kitap\s*\)", re.I)


def partial_candidate(book: dict) -> bool:
    """Kısmi eşlemeye girebilir mi (kayıt başına bir kez hesaplanır, `_partial`)."""
    if "_partial" not in book:
        name = book.get("new_name") or ""
        book["_partial"] = not (set(fold(first_part(name)).split()) & NOT_A_BOOK) and "iptal edildi" not in fold(name) \
            and not NOT_A_BOOK_ANYWHERE.search(fold(name)) and not SET_OF_BOOKS.search(name)
    return book["_partial"]


def _author_hit(authors: list[str], book: dict) -> bool:
    have = fold(book.get("new_yazartext"))
    return any(fold(a) and fold(a) in have for a in authors)


#: Dosya adının SONUNA bitişik yazılmış dosya hâli sözcükleri («arkadasımgunesic», «hareminpadisahibaski»,
#: «canımarkadasımyeni»): boşluksuz anahtardan atılmış biçim ayrıca denenir (yalnız özgün ad eşleşmezse).
GLUED_TAIL = re.compile(r"(?:baski+|ic|son|ozalit|yeni|small)+$")


def name_variants(names: list[str], lead: bool = True) -> list[str]:
    """Editörün adlarına ek yazımlar (her biri kendi adından SONRA denenir): sona bitişik dosya hâli sözcüğü atılmış,
    `lead` ise başa bitişik sıra numarası da atılmış («7armagan» → «armagan»; «80gundedevrialem» özgün hâliyle önce
    denenir). Numarası atılmış ad yalnız tam eşlemede kullanılır: kısmi eşlemede «365 Sevgili Peygamberim» «Sevgili
    Peygamberim Günlüğümde»ye gider."""
    out: list[str] = []
    for n in names:
        out.append(n)
        c = compact(n)
        stripped = re.sub(r"^\d{1,3}(?=[a-z])", "", c) if lead else c
        for v in (GLUED_TAIL.sub("", c), stripped, GLUED_TAIL.sub("", stripped)):
            if v != c and len(v) >= 6:
                out.append(v)
    return list(dict.fromkeys(out))


def _word_ends(title: str) -> list[int]:
    """Katlanmış adın kelime sonlarının boşluksuz anahtardaki konumları."""
    ends, n = [], 0
    for w in fold(title).split():
        n += len(w)
        ends.append(n)
    return ends


def _keys(b: dict) -> list[tuple[str, list[int]]]:
    """Kaydın adlarının (boşluksuz anahtar, kelime sonları) çiftleri; kayıt başına bir kez hesaplanır."""
    if "_keys" not in b:
        b["_keys"] = [(compact(t), _word_ends(t)) for t in dict.fromkeys(
            b.get(k) or "" for k in ("new_name", "new_KitabnAd", "new_urunadi")) if compact(t)]
        b["_nums"] = set(re.findall(r"\d+", fold(b.get("new_name"))))
    return b["_keys"]


def opens_compact(want: str, title: str, keys: tuple[str, list[int]] | None = None) -> bool:
    """Boşluksuz dosya adı kayıt adının başı mı (dosya adı kısaltılmış: «mupteladirgemiler» → «Müpteladır Gemiler
    Benim Denizlerime»)? Dosya adı bir kelime sınırında bitmeli: kesmeden sonraki ek ayrı kelime sayılır («sirintopkapi
    sarayi» → «Şirin Topkapı Sarayı'nda»), ama kelimenin içinde bitemez («gizligorev» «Gizli Görevler Okulu» değil)."""
    c, ends = keys or (compact(title), _word_ends(title))
    if len(want) < 10 or not c.startswith(want) or c == want:
        return False
    nxt = next((e for e in ends if e >= len(want)), None)
    return nxt == len(want)


def steps_for(books: list[dict]):
    exact = (("TITLE", lambda n: (lambda t: [b for b in books if t in b["_titles"]])(fold(n))),
             ("COMPACT", lambda n: (lambda c: [b for b in books if c in b["_compact"]])(compact(n))),
             ("SEGMENT", lambda n: (lambda c: [b for b in books if c in b["_first"]])(compact(n))))
    partial = (("PARTIAL", lambda n: (lambda w: [b for b in books if len(w) >= 2 and any(_opens(w, x) for x in b["_titles"])
                                                 and partial_candidate(b)])(fold(n).split())),
               # dosya adı kayıt adının başı (bitişik yazılmış, kısaltılmış ad)
               ("PREFIX", lambda n: (lambda c: [] if len(c) < 10 else [
                   b for b in books if any(k[0].startswith(c) for k in _keys(b))
                   and any(opens_compact(c, "", k) for k in _keys(b)) and partial_candidate(b)])(compact(n))),
               # sondaki cilt numarası: numarasız ad kaydın ilk parçası ve numara kayıt adında; ya da kayıt adı ad + numara
               # ile başlıyor («dangerdan2» → «Danger Dan - Milli Marşı Kurtarıyor 2», «kayi1» → «Kayı 1: Ertuğrul'un
               # Ocağı»; «ulak4» numarasız «Ulak - …»ya, «Can Avar 2» «Canavar Otu - … 2»ye gitmez)
               ("SERIES_NO", lambda n: series_no(books, compact(n))))
    return exact, partial


def series_no(books: list[dict], c: str) -> list[dict]:
    m = re.fullmatch(r"(.{4,}?)(\d{1,2})", c)
    if not m:
        return []
    base, no = m.groups()
    out = []
    for b in books:
        if not ((base in b["_first"] and no in b["_nums"]) or any(k[0].startswith(c) and any(
                e == len(c) for e in k[1]) for k in _keys(b))):
            continue
        if partial_candidate(b):
            out.append(b)
    return out


def match(books: list[dict], isbns: list[str], title: str, authors: list[str] = (),
          titles: list[str] = ()) -> tuple[str, list[dict], str]:
    """-> (matched_by, records, detail). One record, or several editions of one book. `titles`: the
    book's spellings in the editor's order (an automatic name: cleaned file name first, the current
    title last — a name taken from the CRM, «Arsen Lüpen», must not re-match by itself and land on
    another record). Each name goes through all steps before the next name; a name of the editor's
    list is never matched partially before an earlier name had its exact steps."""
    wanted = {i for i in map(norm_isbn, isbns) if i}
    given = list(dict.fromkeys(n for n in [*titles, title] if fold(n)))
    names, loose = name_variants(given), name_variants(given, lead=False)
    exact, partial = steps_for(books)
    how, rows = "NONE", []
    if wanted:
        how, rows = "ISBN", [b for b in books if b["_isbns"] & wanted]
    # tam adımlar (TITLE/COMPACT/SEGMENT) ad ad sırayla; kısmi eşleme ancak hiçbir ad tam eşleşmezse
    for group, group_names in ((exact, names), (partial, loose)):
        for n in group_names:
            if rows:
                break
            for step, find in group:
                how, rows = step, find(n)
                if rows:
                    break
        if rows:
            break
    if not rows:
        return "NONE", [], ""
    if len(rows) > 1 and authors:
        rows = [b for b in rows if _author_hit(authors, b)] or rows
    if len(rows) == 1:
        return how, rows, ""
    # «X (Önceki Ebat)», «X?» and a record whose author was left empty are still book X.
    same_title = len({compact(re.sub(r"\s*\([^)]*\)\s*$", "", b["new_name"])) for b in rows}) == 1
    same_author = len({a for a in (fold(b.get("new_yazartext")) for b in rows) if a}) <= 1
    if same_title and same_author:
        rows.sort(key=lambda b: (b["new_projekarti"] is not None, b["ModifiedOn"]), reverse=True)
        return how + "+EDITIONS", rows, f"{len(rows)} baskı: " + "; ".join(
            filter(None, (b.get("new_isbn13") or b.get("new_isbn") for b in rows)))
    return "AMBIGUOUS", rows, f"{len(rows)} CRM kaydı: " + "; ".join(b["new_name"] for b in rows[:5])


def project(cur, project_id) -> dict:
    if not project_id:
        return {}
    cur.execute("SELECT new_name, new_ProjeFikriTekcmleile, new_olasiyazartext FROM new_projeBase"
                " WHERE new_projeId=%s", (str(project_id),))
    return cur.fetchone() or {}


def participants(cur, book_id, role: str) -> list[str]:
    cur.execute("SELECT new_name FROM new_eserkatilimBase WHERE new_Kitap=%s AND statecode=0"
                " AND new_name LIKE %s ORDER BY CreatedOn", (str(book_id), role + " - %"))
    return [r["new_name"].split(" - ", 1)[1].strip() for r in cur.fetchall()]


def genres(s: str | None) -> list[str]:
    """new_turlertext: «Bilim Tarihi,İnceleme-Araştırma» — comma separated, kept as written."""
    return list(dict.fromkeys(x.strip() for x in (s or "").split(",") if x.strip()))


def age(v) -> int | None:
    """A target age of 0 is an unfilled field, not a newborn reader."""
    return int(v) if v not in (None, "") and int(v) > 0 else None


def record(cur, book: dict) -> dict:
    """The publisher's facts about the book, as the CRM holds them (not verified in the book)."""
    proj = project(cur, book.get("new_projekarti"))
    authors = names(book.get("new_yazartext")) or participants(cur, book["new_kitapId"], "Yazar") \
        or names(proj.get("new_olasiyazartext"))
    summary, field = next(((plain(book[f]), f) for f in SUMMARY_FIELDS if plain(book.get(f))),
                          (plain(proj.get("new_ProjeFikriTekcmleile")), "new_proje.new_ProjeFikriTekcmleile"))
    first = book.get("new_ilkyayintarihi")
    return {"crm_book_id": str(book["new_kitapId"]), "crm_project_id": str(book["new_projekarti"] or "") or None,
            "title": book["new_name"], "authors": authors, "illustrators": names(book.get("new_cizerlertext")),
            "summary": summary or None, "summary_field": field if summary else None,
            "isbn": book.get("new_isbn13") or book.get("new_isbn"), "stock_code": book.get("new_StokKodu"),
            "first_publish_date": first.date().isoformat() if first else None,
            "audience": AUDIENCE.get(book.get("new_hedefkitle")), "genres": genres(book.get("new_turlertext")),
            "web_categories": (book.get("new_webkategorileritext") or "").strip() or None,
            "age_from": age(book.get("new_hedefkitleyasbaslangic")), "age_to": age(book.get("new_hedefkitleyasbitis")),
            "page_count": age(book.get("new_sayfasayisi")),
            "crm_modified_on": book["ModifiedOn"].isoformat()}


def candidates(cur, book: dict) -> list[dict]:
    out = []
    if book.get("new_resimurl"):
        out.append({"kind": "resimurl", "path": book["new_resimurl"], "name": "yayın kapağı",
                    "date": book["ModifiedOn"].isoformat()})
    if book.get("new_projekarti"):
        cur.execute("SELECT new_name, new_Link, CreatedOn FROM new_kapakalternatifiBase WHERE new_Proje=%s"
                    " AND statecode=0 AND new_Link IS NOT NULL", (str(book["new_projekarti"]),))
        for r in cur.fetchall():
            if not PLACEHOLDER.match((r["new_name"] or "").strip()):
                out.append({"kind": "kapak_alternatifi", "path": r["new_Link"], "name": r["new_name"],
                            "date": r["CreatedOn"].isoformat()})
    return out


def fetch(cand: dict) -> bytes | None:
    """Stored path -> bytes, through the configured roots (a mounted share or folder)."""
    roots = json.loads(os.environ.get("CRM_IMAGE_ROOTS", "{}"))
    p = cand["path"].replace("https://", "").replace("http://", "")
    if cand["kind"] == "resimurl" and "resimurl" in roots:
        f = Path(roots["resimurl"]) / Path(*PureWindowsPath(p).parts)
        return f.read_bytes() if f.is_file() else None
    for prefix, root in roots.items():
        if prefix != "resimurl" and p.lower().startswith(prefix.lower()):
            f = Path(root) / Path(*PureWindowsPath(p[len(prefix):].lstrip("\\/")).parts)
            return f.read_bytes() if f.is_file() else None
    return None


def _utc(s: str | None):
    """Editörün ISO zamanı → CRM'in saklama biçimi (saat dilimsiz UTC)."""
    from datetime import datetime, timezone
    if not s:
        return None
    t = datetime.fromisoformat(s)
    return t.astimezone(timezone.utc).replace(tzinfo=None) if t.tzinfo else t


def latest_alternatives(cur) -> dict[str, object]:
    """Proje → en yeni kapak alternatifinin CreatedOn'u (yeni eklenen kapak kitabı değişmiş sayar)."""
    cur.execute("SELECT new_Proje, max(CreatedOn) AS t FROM new_kapakalternatifiBase WHERE statecode=0"
                " AND new_Link IS NOT NULL GROUP BY new_Proje")
    return {str(r["new_Proje"]): r["t"] for r in cur.fetchall() if r["new_Proje"]}


def own_name(rows: list[dict]) -> str | None:
    """Belirsiz eşleşmede kayıtların ortak kitap adı (hepsinde aynıysa), yoksa None."""
    if len({compact(first_part(r["new_name"])) for r in rows}) != 1:
        return None
    best = max(rows, key=lambda r: (r["new_projekarti"] is not None, r["ModifiedOn"]))
    return first_part(best["new_name"])


def match_book(books: list[dict], b: dict) -> tuple[str, list[dict], str]:
    """Editörün bir kitabı için eşleme. `title_auto`: bugünkü ad editörün kendi çıkardığı ad (CRM/site/künye/dosya);
    eşleştirmeye girmez, yalnız `titles` (dosya adı) aranır."""
    titles = b.get("titles") or []
    title = titles[0] if b.get("title_auto") and titles else b["title"]
    return match(books, b.get("isbns") or [], title, b.get("authors") or [], titles)


def unchanged(b: dict, m: tuple[str, list[dict], str], alternatives: dict) -> bool:
    """Kitabın son aramasından beri hiçbir şey değişmedi mi (yeniden okumaya ve göndermeye gerek yok)."""
    last = b.get("last_lookup")
    at = _utc((last or {}).get("at"))
    if not last or at is None:
        return False                                      # hiç aranmamış: yeni
    how, rows, _ = m
    if how == "NONE":
        return last["outcome"] == "NO_MATCH"
    if how == "AMBIGUOUS":
        return last["outcome"] == "AMBIGUOUS" and (last.get("crm_title") or None) == own_name(rows)
    if last["outcome"] in ("NO_MATCH", "AMBIGUOUS") or last.get("crm_book_id") != str(rows[0]["new_kitapId"]):
        return False                                      # eşleşme değişti
    for r in rows:
        if r["ModifiedOn"] and r["ModifiedOn"] > at:
            return False                                  # CRM kaydı değişti
        alt = alternatives.get(str(r["new_projekarti"] or ""))
        if alt and alt > at:
            return False                                  # projeye yeni kapak eklendi
    return True


def report(cur, books: list[dict], b: dict, with_image: bool = True, m: tuple | None = None) -> dict:
    import base64
    how, rows, detail = m or match_book(books, b)
    rep = {"book_id": b.get("book_id"), "matched_by": how, "candidates": [], "outcome": "NO_MATCH",
           "detail": detail or None}
    if how == "AMBIGUOUS":
        rep["outcome"] = "AMBIGUOUS"
        # kayıt seçilemedi ama kitabın adı bütün kayıtlarda aynıysa ad bellidir (kayıt bilgisi gönderilmez)
        name = own_name(rows)
        if name:
            rep["crm_title"] = name
    elif rows:
        main_row = rows[0]
        cands = sorted((c for r in rows for c in candidates(cur, r)), key=lambda x: x["date"], reverse=True)
        rep.update(crm_book_id=str(main_row["new_kitapId"]), crm_title=main_row["new_name"], candidates=cands,
                   crm=record(cur, main_row), outcome="NO_IMAGE" if not cands else "FETCH_FAILED")
        for cand in cands if with_image else []:     # newest first; an unreadable file falls to the next
            data = fetch(cand)
            if data:
                rep.update(outcome="STORED", chosen=cand, file_name=PureWindowsPath(cand["path"]).name,
                           image_b64=base64.b64encode(data).decode())
                break
    return rep


def _clean(t: str) -> str:
    """--dry-run: the order number in front of a file name («1- todişin bir günü») is not part of the name."""
    return re.sub(r"^\s*\d{1,3}\s*[-_.)]*\s+", "", re.sub(r"^\s*\d{1,3}\s*[-_.)]+\s*", "", t or "")).strip()


def main(argv: list[str]) -> int:
    conn = crm()
    cur = conn.cursor(as_dict=True)
    books = load_books(cur)
    if argv[:1] == ["--dry-run"]:
        for t in argv[1:]:
            rep = report(cur, books, {"title": t, "titles": [_clean(t)]}, with_image=False)
            crm_rec = rep.get("crm") or {}
            print(json.dumps({"title": t, "matched_by": rep["matched_by"], "outcome": rep["outcome"],
                              "crm_title": rep.get("crm_title"), "detail": rep["detail"],
                              "authors": crm_rec.get("authors"), "summary_field": crm_rec.get("summary_field"),
                              "summary": (crm_rec.get("summary") or "")[:80], "images": len(rep["candidates"])},
                             ensure_ascii=False), flush=True)
        return 0
    full = "--full" in argv
    alternatives = latest_alternatives(cur)
    seen = skipped = failed = 0
    for b in api("requests")["books"]:
        seen += 1
        m = match_book(books, b)
        if not full and unchanged(b, m, alternatives):
            skipped += 1
            continue
        rep = report(cur, books, b, m=m)
        print(b["title"], "→", rep["matched_by"], rep["outcome"], (rep.get("crm") or {}).get("audience") or "",
              (rep.get("chosen") or {}).get("name", ""), flush=True)
        for attempt in (1, 2):       # kart servisi yeniden başlarken bağlantı kopabilir: bir kez daha, sonra sıradaki
            try:
                api("store", rep)
                break
            except OSError as e:
                if attempt == 2:
                    failed += 1
                    print("  yazılamadı:", type(e).__name__, e, flush=True)
    print(f"{seen} kitap; {seen - skipped - failed} yazıldı, {skipped} değişmemiş (atlandı), {failed} yazılamadı"
          + (" [--full]" if full else ""), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
