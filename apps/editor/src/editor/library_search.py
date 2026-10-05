"""Kütüphane geneli Kitaba sor: soruya göre aday kitap seçimi (kitap adı geçmeyen soru).

2026-10-05 ölçümü (kart servisi, 75 okunmuş kitap): «Bir tilkinin hasta bir kızla bağ kurduğu ve kızın Bee diye
çağrıldığı kitap hangisi?» gibi olay/karakter tarifli sorular «Kitapta bulunamadı» dönüyordu. İki neden: (1) bütün
kitapların kartı tek bağlama konuyordu; 75 kartın toplamı ~192 bin token, yer ~127 bin; her kitaba eşit pay düşünce
tek satırlık özet sığmıyor ve kitap yalnız adıyla kalıyordu. Olay/özet/karakter içeriğiyle arama yapılmıyordu, aday
yalnız ad/yaş/tür eşleşmesiydi. (2) Adı «Kitap» olan arşiv kitapları her soruda «adı geçen kitap» sayılıyordu
(`quick_answer.mentioned`).

Aday üreten üç kaynak (kitap başına puan, en iyi `TOP_BOOKS` kitap; hepsi model çağırmaz):
- Anlamsal: sorunun TEK embedding'i (etkileşimli; GPU kopyası kapalıysa CPU eşi) ile mevcut `editor_passages_v1`
  koleksiyonunda, her kitabın güncel arama dizininin (`search_index` build_key) metin paragrafları ve olayları
  arasında kitaba göre gruplu arama.
- Sözcük: kitabın özeti, bölüm özetleri, olayları ve karakter kayıtları (ad + tanım) üzerinde Türkçe kök önekli
  (4 harf) ters dizin; ağırlık kitaplar arası seyreklik (idf). Dizindeki embedding'ler yalnız paragraf ve olay için
  var; özet/bölüm özeti/karakter tanımı bu yolla aranır (dizine yazma yok).
- Karakter adı: soruda büyük harfle geçen bir ad kitabın karakter adıyla ya da diğer adıyla birebir eşleşirse
  («Bee»).
Sıralama: anlamsal ve sözcük sıralarının karşılıklı sıra birleşimi (RRF), karakter adı eşleşmesi en öne. Adayın
eşleşen kayıtları (sayfasıyla) bağlama yazılır; model kitabın soruya uyup uymadığına kayıtlara bakarak karar verir.

Kitap seçimi kitaba özel değildir: kural, sözcük listesi ve eşikler hiçbir kitabın adını ya da içeriğini bilmez.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import time
import unicodedata
from typing import Any

from . import read_model

log = logging.getLogger("editor.library_search")

#: Bağlama tam kartıyla giren en çok aday kitap (içerik eşleşmesi; yaş/tür eşleşenler ayrıca gelir).
TOP_BOOKS = int(os.environ.get("EDITOR_LIBRARY_CANDIDATES", "5"))
#: Aday başına bağlama yazılan eşleşen kayıt (anlamsal + sözcük).
HITS_PER_BOOK = 4
#: Anlamsal aramada kitap grubu sayısı (sıralama için; bağlama TOP_BOOKS girer).
SEMANTIC_GROUPS = 20
#: Anlamsal arama (embedding + qdrant) en çok bu kadar sürer; aşarsa yalnız sözcük ve ad eşleşmesi kullanılır.
SEMANTIC_TIMEOUT = float(os.environ.get("EDITOR_LIBRARY_SEMANTIC_TIMEOUT_SEC", "15"))
#: Karşılıklı sıra birleşimi sabiti (RRF).
RRF_K = 60
#: Eşleşen kaydın bağlamdaki en çok uzunluğu (karakter).
HIT_CHARS = 500

_TR = str.maketrans("çğıöşüâîûÇĞİIÖŞÜÂÎÛ", "cgiosuaiuCGIIOSUAIU")

#: Sözcük aramasında sayılmayan genel sözcükler (soru kalıbı ve bağlaçlar; kitaptan bağımsız).
STOPWORDS = frozenset("""
bir bu su o ve veya ile ya da de ki mi mu ne neden nasil nerede kim kimi kimin hangi hangisi hangileri hangisidir
icin gibi kadar daha cok en olan oldugu oldugunu olarak olur oluyor var yok mu midir mudur icinde uzerine hakkinda
kitap kitabi kitabin kitaplar kitaplari kitaplarimiz kitabimiz kitaplarimizdan kitapta kitaptan anlatan anlatildigi
anlatir anlatiyor anlattigi hikaye hikayesi hikayesini hikayenin oyku konu konusu soz eden geciyor gecen gectigi
biz bizim sen siz onun ona onu onlar sey seyi sonra once bana bize var midir mi acaba lutfen soyle soyler soyleyin
""".split())

_WORD = re.compile(r"[a-z0-9]+")
_PROPER = re.compile(r"[A-ZÇĞİÖŞÜÂÎÛ][^\s.,;:!?«»\"()\[\]]*")


def fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").translate(_TR).lower()


def stem(word: str) -> str:
    """Türkçe ek payı: dört harflik önek («dedesinin» ~ «dedem», «tilkinin» ~ «tilki»)."""
    return word[:4]


def stems(text: str) -> set[str]:
    return {stem(w) for w in _WORD.findall(fold(text)) if len(w) >= 3 and w not in STOPWORDS and not w.isdigit()}


def _pages(p: Any) -> list[int]:
    return sorted({int(x) for x in (p or []) if str(x).lstrip("-").isdigit()})


# ------------------------------------------------------------------ kitap başına sözcük kayıtları
#: (kitap, kart build_key) -> kayıtlar. Bir build_key'in içeriği değişmez.
_DOCS: dict[tuple[str, str], list[dict]] = {}


def chapter_sentences(c, gid: str) -> list[dict]:
    """Bölüm özeti cümleleri (güncel `chapter_summaries` çıktısı); yoksa boş."""
    try:
        row = read_model.artifact(c, gid, "chapter_summaries")["artifact"]
    except Exception as e:  # noqa: BLE001 — çıktı yok ya da okunamadı: bölüm özeti olmadan aranır
        log.info("chapter summaries unavailable (%s): %s", gid, str(e)[:120])
        return []
    out = []
    for ch in ((row or {}).get("content") or {}).get("chapters") or []:
        for s in (ch.get("sentences") or []) if isinstance(ch, dict) else []:
            if isinstance(s, dict) and s.get("text"):
                out.append({"kind": "bölüm özeti", "text": str(s["text"]), "pages": _pages(s.get("pages"))})
    return out


def book_docs(b: dict, c) -> list[dict]:
    """Kitabın aranan kayıtları: özet, bölüm özetleri, olaylar, karakterler (ad + diğer adlar + tanım)."""
    key = (b["book_id"], str(b.get("card_key") or b["generation_id"]))
    if key in _DOCS:
        return _DOCS[key]
    # Kitabın adı, türü/kategorisi ve temaları («Güzel Ahlakım» → ahlak sorusu; 2026-10-05: adı ve teması sorudaki
    # sözcüğü taşıyan kitap ad/özet eşleşmesi olmadığı için aday olmuyordu).
    names = "; ".join(dict.fromkeys(x for x in (b.get("crm_title"), b.get("title")) if x))
    rec = (b.get("recommendation") or {}).get("category") or []
    genre = [str(m["claim"]) for m in b.get("metadata") or [] if m.get("subject") == "GENRE" and m.get("claim")]
    themes: dict[str, set] = {}
    for t in b.get("themes") or []:
        if t.get("claim"):
            themes.setdefault(str(t["claim"]), set()).update(_pages(t.get("source_pages")))
    docs = [{"kind": "kitap adı ve türü", "text": "; ".join([names, *genre, *rec]), "pages": []}]
    docs += [{"kind": "tema", "text": t, "pages": sorted(p)} for t, p in themes.items()]
    docs += [{"kind": "özet", "text": str(s["text"]), "pages": _pages(s.get("pages"))}
             for s in b.get("summary") or [] if s.get("text")]
    docs += chapter_sentences(c, b["generation_id"]) if c is not None else []
    docs += [{"kind": "olay", "text": str(e["summary"]), "pages": [e["page_from"]] if e.get("page_from") else []}
             for e in b.get("events") or [] if e.get("summary") and e.get("merged_into") is None]
    for ch in [*(b.get("characters") or []), *(b.get("other_characters") or [])]:
        if ch.get("identity_status") == "UNCERTAIN":
            continue
        names = ", ".join([ch["canonical_name"], *(ch.get("aliases") or [])])
        pages = ch.get("description_pages") or ([ch["first_page"]] if ch.get("first_page") else [])
        docs.append({"kind": "karakter", "text": f"{names}: {ch.get('description') or ''}".strip(": "),
                     "pages": _pages(pages)})
    for d in docs:
        d["stems"] = stems(d["text"])
    if b.get("card_key"):
        _DOCS[key] = docs
    return docs


def lexical(question: str, books: list[dict], docs: dict[str, list[dict]]) -> dict[str, dict]:
    """{book_id: {'score', 'hits'}}: sorudaki köklerin kitap kayıtlarında geçişi, kitaplar arası seyreklikle
    ağırlıklı. Kitap puanı = en iyi üç kaydın puanı (1, 1/2, 1/4) + kitapta geçen köklerin ağırlığı."""
    asked = stems(question)
    if not asked or not books:
        return {}
    n = len(books)
    present = {b["book_id"]: set().union(*(d["stems"] for d in docs[b["book_id"]])) if docs[b["book_id"]] else set()
               for b in books}
    # Üç harfli kök ekle uzar: «kız» ~ «kızın», «din» ~ «dini» (dört harflik önek ayrı kök sayılır).
    vocab = set().union(*present.values()) if present else set()
    asked |= {v for s in asked if len(s) == 3 for v in vocab if len(v) == 4 and v.startswith(s)}
    df = {s: sum(1 for st in present.values() if s in st) for s in asked}
    idf = {s: math.log((n + 1) / (df[s] + 0.5)) for s in asked if df[s]}
    idf = {s: w for s, w in idf.items() if w > 0}
    out = {}
    for b in books:
        bid = b["book_id"]
        cover = sum(w for s, w in idf.items() if s in present[bid])
        if not cover:
            continue
        scored = sorted(((sum(idf.get(s, 0) for s in d["stems"] & asked), i) for i, d in enumerate(docs[bid])),
                        reverse=True)[:HITS_PER_BOOK]
        top = [s for s, _ in scored]
        score = sum(s * w for s, w in zip(top, (1, 0.5, 0.25))) + cover
        out[bid] = {"score": score, "hits": [docs[bid][i] for s, i in scored if s > 0]}
    return out


def name_matches(question: str, books: list[dict]) -> dict[str, list[str]]:
    """{book_id: [eşleşen karakter adları]}: soruda büyük harfle başlayan bir ad (ek ayrılmış: «Bee'nin» → «Bee»)
    kitabın karakter adına ya da diğer adına birebir eşit. Çok sözcüklü ad soruda aynı sırayla geçmeli."""
    words = [fold(re.split(r"['’]", m.group(0))[0]) for m in _PROPER.finditer(question or "")]
    words = [" ".join(_WORD.findall(w)) for w in words]
    q = f" {' '.join(_WORD.findall(fold(question)))} "
    proper = {w for w in words if w}
    out: dict[str, list[str]] = {}
    for b in books:
        hit = []
        for ch in [*(b.get("characters") or []), *(b.get("other_characters") or [])]:
            for name in [ch.get("canonical_name"), *(ch.get("aliases") or [])]:
                key = " ".join(_WORD.findall(fold(name or "")))
                if len(key) < 3 or key.split()[0] not in proper or f" {key} " not in q:
                    continue
                if ch["canonical_name"] not in hit:
                    hit.append(ch["canonical_name"])
        if hit:
            out[b["book_id"]] = hit
    return out


# ------------------------------------------------------------------ anlamsal arama (mevcut dizin, tek embedding)
#: Sorunun embedding'i (aynı soru derin okumada yeniden gömülmez). Küçük: son birkaç soru.
_VECS: dict[str, list[float]] = {}


async def question_vector(question: str) -> list[float]:
    from . import retrieval
    from .llm import INTERACTIVE, Llm
    if question not in _VECS:
        vec = (await Llm(None).embed([question], instruction=retrieval.QUERY_INSTRUCTION, headers=INTERACTIVE))[0]
        while len(_VECS) >= 32:
            _VECS.pop(next(iter(_VECS)))
        _VECS[question] = vec
    return _VECS[question]


def index_keys(c, generation_ids: list[str]) -> dict[str, str]:
    """{generation_id: güncel arama dizininin build_key'i} (`retrieval.prune_all` ile aynı kural)."""
    if not generation_ids:
        return {}
    rows = c.execute(
        "SELECT a.generation_id, v.build_key FROM ed.current_artifact a JOIN ed.artifact_version v"
        " ON v.generation_id=a.generation_id AND v.kind=a.kind AND v.input_digest=a.input_digest"
        " WHERE a.kind='search_index' AND a.generation_id=ANY(%s::uuid[]) ORDER BY a.generation_id, v.created_at DESC",
        (generation_ids,)).fetchall()
    out: dict[str, str] = {}
    for r in rows:
        if r.get("build_key"):
            out.setdefault(str(r["generation_id"]), r["build_key"])
    return out


async def semantic(question: str, keys: dict[str, str], *, groups: int = SEMANTIC_GROUPS,
                   per_book: int = HITS_PER_BOOK, kinds: list[str] | None = None) -> dict[str, dict]:
    """{generation_id: {'score', 'hits'}}: dizinde kitaba göre gruplu en yakın paragraf/olaylar. Yalnız her kitabın
    güncel dizin anahtarı (eski anahtarın noktaları sayılmaz)."""
    from qdrant_client import models

    from . import retrieval
    if not keys:
        return {}
    vec = await question_vector(question)
    should = [models.Filter(must=[
        models.FieldCondition(key="generation_id", match=models.MatchValue(value=g)),
        models.FieldCondition(key="build_key", match=models.MatchValue(value=k))]) for g, k in keys.items()]
    must = [models.FieldCondition(key="generation_id", match=models.MatchAny(any=list(keys)))]
    if kinds:
        must.append(models.FieldCondition(key="kind", match=models.MatchAny(any=kinds)))
    res = await retrieval.qdrant().query_points_groups(
        retrieval.PASSAGES, query=vec, group_by="generation_id", limit=groups, group_size=per_book,
        with_payload=["generation_id", "build_key", "kind", "page_no", "text"],
        query_filter=models.Filter(must=must, should=should))
    out = {}
    for g in res.groups:
        hits = [h for h in g.hits if keys.get(str(h.payload.get("generation_id"))) == h.payload.get("build_key")]
        if not hits:
            continue
        top = sorted((h.score for h in hits), reverse=True)
        out[str(g.id)] = {"score": sum(s * w for s, w in zip(top, (1, 0.5, 0.25))),
                          "hits": [{"kind": "metin" if h.payload.get("kind") == "paragraph" else "olay",
                                    "text": str(h.payload.get("text") or ""),
                                    "pages": _pages([h.payload.get("page_no")])} for h in hits]}
    return out


# ------------------------------------------------------------------ birleştirme
def prepare(books: list[dict], c) -> dict:
    """Aramanın DB'den okuduğu kısım (okuma bağlantısı açıkken): kitap kayıtları ve güncel dizin anahtarları."""
    t0 = time.time()
    docs = {b["book_id"]: book_docs(b, c) for b in books}
    keys = index_keys(c, [b["generation_id"] for b in books]) if c is not None else {}
    return {"docs": docs, "keys": keys, "sec": round(time.time() - t0, 2)}


async def candidates(question: str, books: list[dict], prepared: dict, *, top: int = TOP_BOOKS,
                     named: list[dict] | None = None) -> tuple[list[dict], dict]:
    """(aday kitaplar, ölçüm). Aday: {'book', 'score', 'reasons', 'hits'}; sıra: karakter adı / soruda kısa adı geçen
    kitap (`named`) önce, sonra anlamsal + sözcük sıralarının RRF toplamı. Anlamsal arama düşerse (dizin yok, süre
    doldu) diğer iki kaynak kalır."""
    docs, keys = prepared["docs"], prepared["keys"]
    t1 = time.time()
    lex = lexical(question, books, docs)
    names = name_matches(question, books)
    titled = {b["book_id"] for b in named or []}
    sem: dict[str, dict] = {}
    err = None
    try:
        sem = await asyncio.wait_for(semantic(question, keys), SEMANTIC_TIMEOUT)
    except Exception as e:  # noqa: BLE001 — dizin/embedding yok ya da süre doldu: sözcük ve ad eşleşmesi kalır
        err = str(e)[:200] or type(e).__name__
        log.info("library semantic search skipped: %s", err)
    t2 = time.time()
    by_gid = {b["generation_id"]: b for b in books}
    sem_rank = [by_gid[g]["book_id"] for g, _ in sorted(sem.items(), key=lambda x: -x[1]["score"]) if g in by_gid]
    lex_rank = [bid for bid, _ in sorted(lex.items(), key=lambda x: -x[1]["score"])]
    fused: dict[str, float] = {}
    for rank in (sem_rank, lex_rank):
        for i, bid in enumerate(rank):
            fused[bid] = fused.get(bid, 0.0) + 1.0 / (RRF_K + i + 1)
    for bid in set(names) | titled:
        fused[bid] = fused.get(bid, 0.0) + 1.0
    by_id = {b["book_id"]: b for b in books}
    out = []
    for bid in sorted(fused, key=lambda x: -fused[x])[:max(top, len(set(names) | titled))]:
        b = by_id[bid]
        reasons, hits = [], []
        if bid in titled:
            reasons.append("kitabın adı soruda geçiyor")
        if bid in names:
            reasons.append("karakter adı: " + ", ".join(names[bid]))
        s = sem.get(b["generation_id"])
        if s:
            reasons.append("içerik benzerliği")
            hits += s["hits"]
        if bid in lex:
            reasons.append("özet/olay/karakter sözcükleri")
            seen = {h["text"] for h in hits}
            hits += [h for h in lex[bid]["hits"] if h["text"] not in seen]
        out.append({"book": b, "score": round(fused[bid], 4), "reasons": reasons, "hits": hits[:2 * HITS_PER_BOOK]})
    stats = {"docs_sec": prepared.get("sec"), "search_sec": round(t2 - t1, 2), "semantic_books": len(sem),
             "lexical_books": len(lex), "name_books": len(names), "semantic_error": err}
    return out, stats


def hit_lines(hits: list[dict]) -> list[str]:
    out = []
    for h in hits:
        text = " ".join(h["text"].split())
        if len(text) > HIT_CHARS:
            text = text[:HIT_CHARS].rsplit(" ", 1)[0] + " …"
        page = f"s.{','.join(str(p) for p in h['pages'])}" if h.get("pages") else "sayfa yok"
        out.append(f"- [{page}] ({h['kind']}) {text}")
    return out
