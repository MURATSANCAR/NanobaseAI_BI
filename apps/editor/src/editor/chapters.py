"""Bölüm açılışları dizgiden: punto, bölüm başı boşluğu, başlık altı boşluk ve başlık sayfası.

Büyük harf kuralı («AVOKADO») yalnız bir dizgi alışkanlığıdır; çoğu kitapta başlık normal yazımlıdır
(«Avokado», «Böcek Kapan Menekşe») ya da küçük puntolu bir numaradır («1.»). Ortak olan dizgidir: bölüm
yeni sayfada, metinden aşağıda başlar; başlık gövdeden büyük ya da altında boşluk bırakılmıştır; bazı
kitaplarda başlık kendi sayfasındadır, metin sonraki sayfada başlar. Kural kitaptan bağımsızdır; sayfa
başlığı/altlığı (≥3 sayfada aynı kısa küçük satır), künye, ithaf, içindekiler ve tanıtım sayfası bölüm
sayılmaz. 2026-10-01: 26 kabul kitabında ölçüldü (eski kural Babam 150, Duvarları 199 bölüm buluyordu).
"""

from __future__ import annotations

import re
from collections import Counter

SINK = 0.06          # normal metin üst kenarından bu oran (sayfa yüksekliği) kadar aşağıda başlayan sayfa: bölüm başı
HEAD_BIG = 1.15      # bu oranı aşan satır boşluk aranmadan başlık adayıdır
HEAD_MIN = 1.02      # gövdeden biraz büyük satır, altında boşluk varsa başlık
HEAD_LOW = 0.85      # bölüm başı sayfasında altında boşluk olan küçük puntolu satır da başlıktır («1.», «arayış»)
GAP = 1.8            # başlık ile metin arası: satır aralığının en az bu katı
_NOT_TITLE = ("içindekiler", "contents", "kaynakça", "kaynaklar", "dizin", "notlar", "bibliyografya",
              "yeni kitap önerimiz")
_SENT_BREAK = re.compile(r"[^\W\d_][.!?…]+[\"”’']?\s+\S")      # başlıkta cümle sonu + devam: konuşma/metin
_NUMBER = re.compile(r"^\d{1,3}\.?$")
_IMPRINT = re.compile(r"www\.|\.com|\.tr\b|https?:|^[^\W\d_]+ (19|20)\d\d$", re.I)   # künye/adres: «İstanbul 2026»
_DEDICATION = re.compile(r"[’'](y?[ae]|n[ae])\W*$|\b\w+(ına|ine|una|üne)\W*$")       # ithaf: «… X'e…», «… hatırasına…»


def _norm(t: str) -> str:
    # Türkçe küçültme: «İ».casefold() noktalı «i̇» verir, «İÇİNDEKİLER» «içindekiler»e eşlenmezdi
    t = t.replace("İ", "i").replace("I", "ı").casefold()
    return " ".join(re.sub(r"[^\w\s]|\d", " ", t).split())


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0.0


def _title_like(t: str) -> bool:
    t = t.strip()
    if not t or len(t) > 80 or t[0] in "“\"'‘«-–—…(" or _IMPRINT.search(t):
        return False
    if _NUMBER.match(t):
        return True
    return bool(re.search(r"[^\W\d_]", t)) and not _SENT_BREAK.search(t)


def page_layout(doc, page_lines) -> dict:
    """Kitabın gövde puntosu, satır aralığı ve normal metnin üst kenarı; sayfa başlığı/altlığı ayıklanmış satırlar."""
    raw = {i: [ln for ln in page_lines(p) if ln["text"].strip() and not ln["text"].strip().isdigit()]
           for i, p in enumerate(doc, 1)}
    sizes: Counter = Counter()
    for ls in raw.values():
        for ln in ls:
            sizes[round(ln["size"], 1)] += len(ln["text"])
    body = sizes.most_common(1)[0][0] if sizes else 0.0
    rep = Counter(_norm(ln["text"]) for ls in raw.values() for ln in ls if ln["size"] < body * 0.9)
    pages, steps, tops = {}, [], []
    for i, p in enumerate(doc, 1):
        ls = [ln for ln in raw[i]
              if not (ln["size"] < body * 0.9 and rep[_norm(ln["text"])] >= 3 and len(_norm(ln["text"])) < 60)]
        pages[i] = {"lines": ls, "h": p.rect.height}
        bl = [ln for ln in ls if abs(ln["size"] - body) < 0.6]
        if len(bl) >= 8:
            tops.append(bl[0]["y0"] / p.rect.height)
            steps += [b["y0"] - a["y0"] for a, b in zip(bl, bl[1:]) if 0 < b["y0"] - a["y0"] < body * 3]
    return {"pages": pages, "body": body, "step": _median(steps) or body * 1.4, "top": _median(tops)}


def _opening(v: dict, L: dict) -> dict | None:
    ls, body, step = v["lines"], L["body"], L["step"]
    if not ls:
        return None
    sunk = ls[0]["y0"] / v["h"] > L["top"] + SINK

    def is_body(ln):
        return abs(ln["size"] - body) < 0.6 and len(ln["text"]) > 25

    if sum(map(is_body, ls)) < 3:
        # başlık sayfası: yalnız kısa satırlar (bölüm adı, kısım adı); metin sonraki sayfada
        lines = [ln for ln in ls if _title_like(ln["text"])]
        words = sum(len(ln["text"].split()) for ln in lines)
        text = " ".join(ln["text"].strip() for ln in lines)
        if lines and len(lines) == len(ls) and len(ls) <= 6 and words <= 12 and not _DEDICATION.search(text):
            return {"title": text, "size": max(ln["size"] for ln in lines), "kind": "page"}
        return None
    head, i = [], 0
    while i < len(ls) and len(head) < 4:
        ln = ls[i]
        nxt = ls[i + 1] if i + 1 < len(ls) else None
        gap = (nxt["y0"] - ln["y0"]) if nxt else 1e9
        big = ln["size"] >= body * HEAD_BIG
        ok = _title_like(ln["text"]) and (
            big or (gap >= step * GAP and (ln["size"] >= body * HEAD_MIN or (sunk and ln["size"] >= body * HEAD_LOW)))
            or (head and abs(ln["size"] - head[-1]["size"]) < 0.3))
        if not ok:
            break
        head.append(ln)
        i += 1
        if gap >= step * GAP:
            break
    if not head:
        return {"title": "", "size": 0, "kind": "sunk"} if sunk else None
    title = " ".join(ln["text"].strip() for ln in head)
    if title[:1].islower() and not sunk:
        return None
    return {"title": title, "size": max(ln["size"] for ln in head), "kind": "sunk" if sunk else "head"}


def page_headings(doc, page_lines) -> dict[int, dict]:
    """Sayfa no → açılış ({title, size, kind: page|sunk|head|empty}). Açılış olmayan sayfa yoktur."""
    L = page_layout(doc, page_lines)
    out = {}
    for i, v in L["pages"].items():
        o = _opening(v, L)
        if o:
            out[i] = o
        elif not v["lines"]:
            out[i] = {"title": "", "size": 0, "kind": "empty"}
    return out


def _skip(title: str, book_title: str, page: int, last_page: int) -> bool:
    n = _norm(title)
    if any(n.startswith(x) for x in _NOT_TITLE):
        return True
    # kitabın kendi adı ilk sayfalarda: iç kapak, bölüm değil
    return bool(book_title) and n.startswith(_norm(book_title)) and page <= max(6, last_page // 10)


def chapters_from_pages(pages: list[dict], headings: dict[int, dict], book_title: str = "") -> list[dict]:
    """Sayfalar (page_no + spans) ve dizgi açılışlarından bölümler: [{title, page_from, page_to}]."""
    by_page = {p["page_no"]: [s["text"].strip() for s in p["spans"] if s["text"].strip()] for p in pages}
    last_page = max(by_page, default=0)
    starts, pending = [], None
    for p in sorted(by_page):
        h = headings.get(p)
        if h and h["kind"] == "empty":
            continue
        near = pending is not None and p - pending["last"] <= 2
        if h and h["kind"] == "page":
            if _skip(h["title"], book_title, p, last_page):
                pending = None
            elif near:
                pending.update(title=pending["title"] + " " + h["title"], last=p)
            else:
                pending = {"page": p, "title": h["title"], "size": h["size"], "last": p, "kind": "page"}
            continue
        if near and by_page[p]:
            starts.append({**pending, "title": (pending["title"] + " " + (h["title"] if h else "")).strip()})
        elif h and h["title"]:
            n = _norm(h["title"])
            paras = by_page[p]
            bio = any(_norm(t).startswith(n) and len(t) > 60 for t in paras[1:2]) if n else False
            # Sahne arasından sonra büyük puntolu ilk satır («Dükkânı için özel bir e-posta hesabı oluşturduktan
            # sonra») aynı paragrafta cümle olarak sürer: başlık değil, başlık kendi paragrafıdır.
            bio = bio or (h["kind"] == "head" and bool(n) and any(
                _norm(t).startswith(n) and len(t) > len(h["title"]) + 40 for t in paras[:1]))
            if (n or _NUMBER.match(h["title"].strip())) and not _skip(h["title"], book_title, p, last_page) and not bio:
                starts.append({"page": p, "title": h["title"], "size": h["size"], "kind": h["kind"]})
        pending = None
    # Bölüm başlıkları bir kitapta aynı dizgide: güçlü açılışların (başlık sayfası / bölüm başı boşluğu) puntosundan
    # sapan zayıf aday (yalnız büyük punto) konuşma balonu ya da ara başlıktır.
    strong = [s["size"] for s in starts if s["kind"] in ("page", "sunk")]
    if strong:
        keep = {k for k, _ in Counter(round(x) for x in strong).most_common(2)}
        starts = [s for s in starts if s["kind"] != "head" or round(s["size"]) in keep or s["size"] > max(keep)]
    if not starts:
        return [{"title": "Kitap", "page_from": 1, "page_to": last_page}]
    out = []
    for i, s in enumerate(starts):
        end = starts[i + 1]["page"] - 1 if i + 1 < len(starts) else last_page
        out.append({"title": s["title"], "page_from": s["page"], "page_to": max(s["page"], end)})
    if starts[0]["page"] > 1:
        out.insert(0, {"title": "Başlıksız başlangıç", "page_from": 1, "page_to": starts[0]["page"] - 1})
    return out


def for_generation(generation_id: str, pages: list[dict] | None = None) -> list[dict] | None:
    """Okunmuş kitabın bölümleri, kitabın kendi PDF dizgisinden. PDF açılamazsa None (çağıran eski kurala döner)."""
    from . import db, source
    from .document import _open_version, _page_lines
    g = db.one("SELECT g.book_version_id, b.title FROM generation g JOIN book_version bv ON bv.id=g.book_version_id "
               "JOIN book b ON b.id=bv.book_id WHERE g.id=%s", generation_id)
    if g is None:
        return None
    try:
        doc, _ = _open_version(str(g["book_version_id"]))
    except Exception:  # noqa: BLE001 - dosya taşınmış/silinmiş: dizgi yok, eski kural
        return None
    with doc:
        headings = page_headings(doc, _page_lines)
    return chapters_from_pages(pages if pages is not None else source.read(generation_id), headings, g["title"] or "")
