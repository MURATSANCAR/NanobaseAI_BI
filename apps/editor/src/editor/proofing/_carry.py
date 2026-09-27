"""Aynı kitabın yeniden okumasında editör kararını taşıma — saf parça (veritabanı yok, model yok).

Kullanıcı kararı (2026-09-27): yeniden okumada AYNI bulgu önceki kararı alır; «yanlış alarm» tekrar
çıkmaz, «doğru» denen işaretli gelir. Yalnız aynı kitap içinde; kurallar kendiliğinden değişmez,
kitaplar arası öğrenme yoktur.

**Bulgu parmak izi** = (denetim adı, tür anahtarı, normalleştirilmiş alıntı):
- denetim adı — sürüm DEĞİL: kural sürümü değişse de aynı yerdeki aynı bulgu aynı bulgudur (taşınan
  kararın hangi sürümde verildiği kaynakta saklanır, isabet sürüm başına ayrı sayılır);
- tür anahtarı — `details` içindeki kimlik alanları (ID_FIELDS): tür/kural kodu, ad yazımında
  «biçim → kitaptaki biçim» çifti, sözcük, kök, kalıp… Ölçü, olasılık ve model etiketi (anlam adı,
  hassas içerik kategorisi) kimlik değildir: yeniden koşuda oynar;
- alıntı — Türkçe küçük harf, NFKC, tırnaklar atılır, tire çeşitleri tek tire, yumuşak tire atılır,
  boşluklar teklenir, uçlardaki noktalama atılır. Bulgunun MESAJ metni parmak izine girmez (ekran
  dili değişebilir).

**Sayfa:** alıntılı bulguda alıntı kazanır — sayfa yalnız aynı anahtarlı birden çok geçişi ayırmak
için kullanılır (en yakın sayfa, yeniden dizgide nesiller arası sayfa kayması düzeltilerek). Alıntısız
bulguda (ör. sayfa düzeni) sayfa anahtarın parçasıdır: aynı sayfa (kaymayla) + aynı tür.

**Eşleme** her kaynak koşu (önceki nesil ya da aynı nesilde önceki koşu) ile bugünkü koşu arasında,
anahtar başına bire bir yapılır: her iki taraf için en yakın aday TEK ve karşılıklıysa eşleşir,
eşleşenler çıkarılıp tekrarlanır. Aynı sayfadaki aynı anahtarlı geçişler işaret kutusunun yerine göre
sıralanır. Yine de eşit kalan adaylar = belirsiz → taşınmaz (yanlış taşımaktansa taşımamak); yalnız
adayların hepsi AYNI kararı taşıyorsa sonuç değişmediği için taşınır.
Bir bulguya birden çok kaynak koşudan öneri gelirse (aynı bulgu birkaç okumadır karar
almış) en YENİ karar geçerlidir; en yenisi «geri al» (CLEAR) ise taşınmaz.
"""

from __future__ import annotations

import collections
import unicodedata

# details içinde bulgunun kimliğini taşıyan alanlar (sıra önemsiz). Kod alanları yalnız kod biçimindeyse
# (boşluksuz) alınır: yazımda `rule` bir mesaj cümlesidir, kimlik değil.
ID_FIELDS = ("kind", "rule", "style", "field", "aspect", "op",      # tür / kural kodları
             "form", "book_form",                                   # ad yazımı: «Hanne» → «Anne»
             "word", "lemma", "phrase", "character", "other_book",  # konu
             "forms", "color",                                      # hangi geçişler / hangi metin rengi
             "old", "new")                                          # baskılar arası: eski → yeni
CODE_FIELDS = frozenset({"kind", "rule", "style", "field", "aspect", "op"})

_QUOTES = dict.fromkeys(map(ord, "\"'`´‘’‚‛“”„‟«»‹›"), None)
_DASHES = str.maketrans({c: "-" for c in "‐‑‒–—―−"})
_EDGE = " .,;:!?-/()[]…"


def norm(s) -> str:
    """Karşılaştırma biçimi: NFKC, Türkçe küçük harf, tırnaksız, tek tire, tek boşluk, uçları temiz."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).replace("­", "")
    s = s.replace("I", "ı").replace("İ", "i").lower().translate(_QUOTES).translate(_DASHES)
    return " ".join(s.split()).strip(_EDGE)


def _val(field: str, v):
    if isinstance(v, bool) or isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        if field in CODE_FIELDS and (len(v) > 64 or any(ch.isspace() for ch in v)):
            return None
        return norm(v) or None
    if isinstance(v, (list, tuple)) and v and all(isinstance(x, (str, int)) and not isinstance(x, bool) for x in v):
        return " ".join(norm(x) for x in v) or None
    return None


def ident(details: dict | None) -> tuple:
    """Tür anahtarı: kimlik alanlarının normalleştirilmiş değerleri, alan adıyla, sıralı."""
    d = details or {}
    out = []
    for k in ID_FIELDS:
        v = _val(k, d.get(k))
        if v is not None:
            out.append((k, v))
    return tuple(sorted(out))


def fingerprint(f: dict) -> tuple:
    """(denetim adı, tür anahtarı, alıntı|None). `f`: check, quote, details (ya da hazır `ident` sözlüğü)."""
    q = norm(f.get("quote")) or None
    return (f["check"], ident(f.get("details") if f.get("details") is not None else f.get("ident")), q)


def _dist(n, o, delta: int, page_bound: bool):
    """(sayfa uzaklığı, sayfa içi sıra farkı) ya da None (aday değil). `n`, `o`: (sayfa, sıra|None)."""
    (n_page, n_rank), (o_page, o_rank) = n, o
    if n_page is None or o_page is None:
        if n_page is not None or o_page is not None:
            return None
        d = 0
    else:
        d = abs(int(n_page) - (int(o_page) + delta))
        if page_bound and d:
            return None
    # Sıra yalnız AYNI sayfada (kaymayla) anlamlıdır; başka sayfadaki geçişler arasında eşitliği bozmaz.
    return (d, abs(n_rank - o_rank) if d == 0 and n_rank is not None and o_rank is not None else 0)


def ranks(rows: list[dict]) -> list[tuple]:
    """Her geçiş için (sayfa, sayfa içi sıra): aynı sayfadaki geçişler işaret kutusunun yerine göre (yukarıdan
    aşağı, soldan sağa) sıralanır — aynı sayfada iki kez geçen aynı yazım hatası böyle ayrılır. Sayfadaki
    geçişlerden birinin kutusu yoksa sıra yok (yer bilinmiyor: eşitlik kalır, taşınmaz)."""
    by_page = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by_page[r.get("page")].append(i)
    out: list[tuple] = [(r.get("page"), None) for r in rows]
    for page, idx in by_page.items():
        if len(idx) < 2 or any(not _box(rows[i].get("bbox")) for i in idx):
            continue
        for rank, i in enumerate(sorted(idx, key=lambda i: (_box(rows[i]["bbox"])[1], _box(rows[i]["bbox"])[0]))):
            out[i] = (page, rank)
    return out


def _box(b):
    if isinstance(b, (list, tuple)) and len(b) == 4 and all(isinstance(v, (int, float)) for v in b):
        return b
    return None


def align(new_pages: list, old_pages: list, delta: int = 0, page_bound: bool = False):
    """`new_pages`, `old_pages`: (sayfa, sıra|None) listeleri (bkz. ranks) ya da yalnız sayfalar.
    Aynı anahtarlı geçişlerin bire bir eşlemesi. Döner: (eşler {yeni_i: eski_i}, belirsizler {yeni_i:
    [en yakın eski_i…]}). Karşılıklı ve tek en yakın aday eşleşir; eşleşenler çıkarılıp tekrarlanır.
    Tek yeni ↔ tek eski alıntılı geçişte sayfa bakılmaz (alıntı kazanır; sayfasız ↔ sayfalı hariç)."""
    new_pages = [p if isinstance(p, tuple) else (p, None) for p in new_pages]
    old_pages = [p if isinstance(p, tuple) else (p, None) for p in old_pages]
    pairs: dict[int, int] = {}
    free_n, free_o = set(range(len(new_pages))), set(range(len(old_pages)))
    best_n: dict[int, tuple[int, list[int]]] = {}
    while free_n and free_o:
        best_n, best_o = {}, {}
        for n in free_n:
            for o in free_o:
                d = _dist(new_pages[n], old_pages[o], delta, page_bound)
                if d is None:
                    continue
                for side, key, other in ((best_n, n, o), (best_o, o, n)):
                    cur = side.get(key)
                    if cur is None or d < cur[0]:
                        side[key] = (d, [other])
                    elif d == cur[0]:
                        cur[1].append(other)
        found = [(n, os[0]) for n, (_, os) in best_n.items()
                 if len(os) == 1 and best_o.get(os[0], (None, []))[1] == [n]]
        if not found:
            break
        for n, o in found:
            pairs[n] = o
            free_n.discard(n)
            free_o.discard(o)
    # Karşılıklı tek en yakın çift kalmadıysa geriye kalan her adayda bir eşitlik vardır (eşitlik yoksa en kısa
    # uzaklıktaki çift her zaman karşılıklıdır): adayı olup eşleşemeyen yeni geçiş belirsizdir.
    ambiguous = {n: best_n[n][1] for n in free_n if n in best_n} if free_n and free_o else {}
    return pairs, ambiguous


def page_shift(current: list[dict], source: list[dict]) -> int:
    """İki nesil arasındaki sayfa kayması: iki tarafta da TEK geçen alıntılı anahtarların sayfa farklarının
    çoğunluk değeri (yarıdan fazlası aynı farkı göstermiyorsa 0). Aynı nesilde kayma yoktur."""
    def uniq(rows):
        by = collections.defaultdict(list)
        for r in rows:
            k = r["_fp"]
            if k[2] is not None and r.get("page") is not None:
                by[k].append(r["page"])
        return {k: v[0] for k, v in by.items() if len(v) == 1}
    a, b = uniq(current), uniq(source)
    offsets = [a[k] - b[k] for k in a.keys() & b.keys()]
    if not offsets:
        return 0
    val, n = collections.Counter(offsets).most_common(1)[0]
    return val if n * 2 > len(offsets) else 0


def carry(current: list[dict], sources: list[dict], current_generation: str | None = None):
    """Önceki kararları bugünkü bulgulara eşler.

    current: bugünkü koşuların BÜTÜN bulguları — {id, check, page, quote, bbox, details|ident, blocked}; `blocked`
        bulgunun kendi kararı var (CLEAR dahil): eşlemeye katılır (geçişi tutar), karar almaz.
    sources: kararı olan önceki koşuların BÜTÜN bulguları — {id, run_id, generation_id, check, page, quote,
        bbox, details|ident, decision|None}; decision: {id, verdict, reason_code, note, decided_by, created_at,
        check_version, read_at}.
    Döner: ({bulgu_id: {"decision": kaynak karar, "finding_id", "generation_id", "page"}}, sayılar).
    """
    for r in current:
        r["_fp"] = fingerprint(r)
    for r in sources:
        r["_fp"] = fingerprint(r)
    cur_groups: dict[tuple, list[dict]] = collections.defaultdict(list)
    for r in current:
        cur_groups[r["_fp"]].append(r)

    by_gen: dict[str, list[dict]] = collections.defaultdict(list)
    for r in sources:
        by_gen[str(r["generation_id"])].append(r)
    shift = {g: (0 if g == str(current_generation) else page_shift(current, rows)) for g, rows in by_gen.items()}

    by_run: dict[str, list[dict]] = collections.defaultdict(list)
    for r in sources:
        by_run[str(r["run_id"])].append(r)

    proposals: dict[str, list[dict]] = collections.defaultdict(list)
    tied: set[str] = set()
    for run_rows in by_run.values():
        groups: dict[tuple, list[dict]] = collections.defaultdict(list)
        for r in run_rows:
            groups[r["_fp"]].append(r)
        for fp, olds in groups.items():
            news = cur_groups.get(fp)
            if not news or not any(o.get("decision") for o in olds):
                continue
            delta = shift[str(olds[0]["generation_id"])]
            pairs, amb = align(ranks(news), ranks(olds), delta, page_bound=fp[2] is None)
            for ni, oi in pairs.items():
                if olds[oi].get("decision"):
                    proposals[str(news[ni]["id"])].append(olds[oi])
            # Eşitlikte kalan geçişler: adayların HEPSİ aynı kararı taşıyorsa (karar + gerekçe) hangisiyle eşlendiği
            # sonucu değiştirmez — aynı sayfada iki kez geçen aynı yazım hatası gibi; karar taşınır, her yeni
            # geçişe mümkünse ayrı bir kaynak verilir. Kararlar ayrışıyorsa ya da biri kararsızsa belirsiz.
            used: set[int] = set()
            new_pos = ranks(news)
            for ni in sorted(amb, key=lambda i: (new_pos[i][0] is None, new_pos[i][0] or 0, i)):
                ois = amb[ni]
                outcomes = {(olds[oi]["decision"]["verdict"], olds[oi]["decision"].get("reason_code"))
                            if olds[oi].get("decision") else None for oi in ois}
                if len(outcomes) == 1 and None not in outcomes:
                    free = [oi for oi in sorted(ois) if oi not in used] or sorted(ois)
                    used.add(free[0])
                    proposals[str(news[ni]["id"])].append(olds[free[0]])
                elif any(olds[oi].get("decision") for oi in ois):
                    tied.add(str(news[ni]["id"]))

    out: dict[str, dict] = {}
    stats = collections.Counter()
    for r in current:
        fid = str(r["id"])
        if r.get("blocked"):
            continue
        props = proposals.get(fid)
        if not props:
            if fid in tied:
                stats["ambiguous"] += 1
            continue
        src = max(props, key=lambda o: (o["decision"]["created_at"], str(o["decision"]["id"])))
        if src["decision"]["verdict"] not in ("ACCEPT", "REJECT"):
            stats["cleared"] += 1
            continue
        out[fid] = {"decision": src["decision"], "finding_id": str(src["id"]),
                    "generation_id": str(src["generation_id"]), "page": src.get("page")}
        stats["carried_" + src["decision"]["verdict"].lower()] += 1
    stats["shifted_generations"] = sum(1 for v in shift.values() if v)
    return out, dict(stats)


def public(c: dict | None, current_generation: str | None = None) -> dict | None:
    """Taşınan karar → ekrana giden karar: kendi kararla aynı biçim + `inherited` ve kaynağı."""
    if not c:
        return None
    d = c["decision"]
    at = d.get("created_at")
    read_at = d.get("read_at")
    iso = lambda t: t.isoformat() if hasattr(t, "isoformat") else t  # noqa: E731
    return {"verdict": d["verdict"], "reasonCode": d.get("reason_code"), "note": d.get("note"),
            "decidedBy": d["decided_by"], "at": iso(at), "inherited": True,
            "source": {"decisionId": str(d["id"]), "findingId": c["finding_id"], "generationId": c["generation_id"],
                       "sameReading": current_generation is not None and c["generation_id"] == str(current_generation),
                       "page": c.get("page"), "checkVersion": d.get("check_version"), "readAt": iso(read_at)}}
