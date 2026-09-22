"""Özellik defteri: bir karakterin görünüşü, sayfa sayfa, metinden ve resimden, kanıtıyla.

Defter (ed.character_attribute, göç 024) süreklilik denetimlerinin ortak kaynağıdır: bir denetim
kitabı yeniden okumaz, defteri okur. Buradaki iş iki okuyucu ve defteri dolduran akıştır:

TEXT okuyucu (book-director, düşünme kapalı, sıcaklık 0): kitap metni PART_WORDS kelimelik
  parçalara bölünür (sayfa bölünmez); her parça için bir çağrı, kapalı kümeden özellik listesi
  ister (kimin, hangi tür, hangi değer, sayfa/paragraf/alıntı). Alıntı sayfada birebir (ya da
  sayfanın kendi kelimelerine oturtulmuş) bulunmazsa kayıt yoktur; bulunursa ledger'a TEXT
  kanıtı yazılır ve defter satırı ona bağlanır. Tek okuma yeter: kanıt alıntıdır, değer kapalı
  kümedendir; yanlış eşleme yargı aşamasında ve editörde görünür.

IMAGE okuyucu (book-vision-deep, sıcaklık VOTE_TEMPERATURE): kimliği çözülmüş (RESOLVED) her
  figür kırpımı için bağımsız okumalar; bir özellik ancak en az iki okuma aynı değeri verirse
  kaydedilir (projede ölçüldü: tek görsel okuma gürültüdür). İki okuma uyuşursa değer; bir
  türde uyuşmazlarsa üçüncü okuma, çoğunluk yoksa BELIRSIZ. Kanıt figürün görsel kanıt satırı
  (visual_region kutusu). Figür başına 2–3 çağrı.

İdempotenlik: character_attribute_read ne okunduğunu tutar (TEXT: sayfa; IMAGE: figür), okuyucu
kimliği prompt adı@sürümüdür. Aynı nesil + aynı okuyucu için yeniden okunmaz; prompt sürümü
artınca yeni satırlar eklenir, eskiler kalır (salt ekleme).

Kitaba özel hiçbir şey yok: özellik türleri ve değerler genel bir sözlüktür (KINDS), eşikler
fiziksel anlamlıdır ve ayardan/sabitten okunur. ÖLÇÜM BEKLİYOR: okuyucuların kesinliği gerçek
kitapta ölçülmedi (docs/son-okuma/appearance.md, «Ölçüm planı»)."""

from __future__ import annotations

import asyncio
from collections import Counter
from itertools import combinations

from .. import db, ledger, schemas, source
from ..llm import Llm

DIRECTOR = "book-director"
VISION = "book-vision-deep"
TEXT_PROMPT = "attribute_text"
IMAGE_PROMPT = "attribute_image"

UNCERTAIN = "BELIRSIZ"
NONE = "YOK"
PART_WORDS = 1500        # text_contradictions ile aynı gerekçe: bir parça şema sınırına sığar
VOTE_TEMPERATURE = 0.6   # bağımsız okumalar (vision.confirm_text_visual oylarıyla aynı)
MIN_AGREE = 2            # bir görsel değer en az bu kadar okumada aynı olmalı
MAX_READINGS = 3         # uyuşmazlıkta en çok bu kadar okuma; sonra BELIRSIZ

# ----------------------------------------------------------------- sözlük
COLOURS = ["SIYAH", "BEYAZ", "GRI", "KAHVERENGI", "SARI", "TURUNCU", "KIRMIZI", "PEMBE", "MOR",
           "MAVI", "YESIL", "BEJ", "COK_RENKLI", "DIGER", NONE, UNCERTAIN]
HAIR = ["SIYAH", "KAHVERENGI", "SARI", "KIZIL", "GRI_BEYAZ", "MAVI", "YESIL", "PEMBE", "MOR",
        "TURUNCU", "KIRMIZI", "DIGER", NONE, UNCERTAIN]
EYES = ["KAHVERENGI", "SIYAH", "MAVI", "YESIL", "GRI", "DIGER", NONE, UNCERTAIN]
PRESENCE = ["VAR", NONE, UNCERTAIN]
ITEMS = ["CANTA", "SIRT_CANTASI", "SEMSIYE", "KITAP", "TOP", "OYUNCAK", "BASTON", "ASA",
         "CICEK", "YIYECEK", "ALET", "DIGER", NONE, UNCERTAIN]

# kind -> (Türkçe ad, izin verilen değerler, kalıcı mı). Kalıcı özellik (saç, göz, ten/kürk,
# gözlük) hikâye içinde nadiren değişir: çelişkisi daha ağır sayılır. Kıyafet ve eşya sahneden
# sahneye değişebilir: çelişki ancak yargı "metin açıklamıyor" derse bulgudur (her tür için öyle,
# ama ağırlık farklı).
KINDS: dict[str, dict] = {
    "SAC_RENGI":        {"label": "saç rengi",            "values": HAIR,     "stable": True},
    "GOZ_RENGI":        {"label": "göz rengi",            "values": EYES,     "stable": True},
    "TEN_KURK_RENGI":   {"label": "ten/kürk/tüy rengi",   "values": COLOURS,  "stable": True},
    "GOZLUK":           {"label": "gözlük",               "values": PRESENCE, "stable": True},
    "SAPKA":            {"label": "şapka/başlık",         "values": PRESENCE, "stable": False},
    "UST_GIYSI_RENGI":  {"label": "üst giysi rengi",      "values": COLOURS,  "stable": False},
    "ALT_GIYSI_RENGI":  {"label": "alt giysi rengi",      "values": COLOURS,  "stable": False},
    "ESYA":             {"label": "taşıdığı eşya",        "values": ITEMS,    "stable": False},
}
ALL_VALUES = sorted({v for k in KINDS.values() for v in k["values"]})


def vocabulary_text() -> str:
    return "\n".join(f"- {k} ({d['label']}): {', '.join(d['values'])}" for k, d in KINDS.items())


def valid_value(kind: str, value: str) -> str | None:
    """Kapalı küme dışındaki cevap değer değildir (kayıt yok)."""
    v = (value or "").strip().upper()
    if kind in KINDS and v in KINDS[kind]["values"]:
        return v
    return None


# ------------------------------------------------------------ şemalar
TEXT_SCHEMA = schemas.obj({"facts": schemas.arr(schemas.obj({
    "subject": schemas.STR, "kind": {"type": "string", "enum": list(KINDS)},
    "value": {"type": "string", "enum": ALL_VALUES},
    "page": schemas.INT, "paragraph": schemas.INT, "quote": schemas.STR}), 0, 120)})

IMAGE_SCHEMA = schemas.obj({"gorunur": schemas.BOOL,
                            **{k: {"type": "string", "enum": d["values"]} for k, d in KINDS.items()}})


# ------------------------------------------------------ saf yardımcılar
def paragraphs(pages: list[dict]) -> list[dict]:
    return [{"page": p["page_no"], "idx": s["idx"], "text": s["text"]} for p in pages for s in p["spans"]]


def parts(paras: list[dict]) -> list[list[dict]]:
    """Ardışık bütün sayfalar, PART_WORDS kelimeye kadar (sayfa bölünmez)."""
    by_page: dict[int, list[dict]] = {}
    for x in paras:
        by_page.setdefault(x["page"], []).append(x)
    out, cur, n = [], [], 0
    for _, ps in sorted(by_page.items()):
        w = sum(len(x["text"].split()) for x in ps)
        if cur and n + w > PART_WORDS:
            out.append(cur)
            cur, n = [], 0
        cur += ps
        n += w
    if cur:
        out.append(cur)
    return out


def part_text(paras: list[dict]) -> str:
    return "\n".join(f"[s{x['page']} p{x['idx']}] {x['text']}" for x in paras)


def locate(pages_by_no: dict[int, dict], page: int, paragraph: int | None, quote: str) -> dict | None:
    """Alıntının sayfada basıldığı hâli: alıntıyı içeren span (önce verilen paragraf), yoksa
    sayfanın alıntıya çok yakın kendi kelimeleri. None = sayfada yok."""
    p = pages_by_no.get(page)
    q = (quote or "").strip().strip("“”\"'")
    if not p or not q:
        return None
    k = source.key(q)
    spans = sorted(p["spans"], key=lambda s: s["idx"] != paragraph)
    for s in spans:
        if k and k in source.key(s["text"]):
            return {"page": page, "idx": s["idx"], "quote": q}
    raw = "\n".join(s["text"] for s in p["spans"])
    snapped = ledger.snap_quote(q, raw)
    if snapped:
        for s in spans:
            if source.key(snapped) in source.key(s["text"]):
                return {"page": page, "idx": s["idx"], "quote": snapped}
        return {"page": page, "idx": None, "quote": snapped}
    return None


def name_index(chars: list[dict]) -> dict[str, str]:
    """Normalleştirilmiş ad -> character_id; iki karakterde geçen ad kimseyi göstermez."""
    hits: dict[str, set] = {}
    for ch in chars:
        for n in [ch["canonical_name"], *(ch.get("aliases") or [])]:
            k = ledger.norm(n or "")
            if k:
                hits.setdefault(k, set()).add(str(ch["id"]))
    return {k: next(iter(v)) for k, v in hits.items() if len(v) == 1}


def resolve_subject(subject: str, idx: dict[str, str]) -> str | None:
    """Modelin yazdığı özne -> character_id. Önce olduğu gibi; sonra kesme işaretinden önceki
    kısım ("Ali'nin" → ali); sonra sondan kelime düşürerek ("Ali dede" → ali). Bir ada
    denk gelmezse None: tahmin yok."""
    s = (subject or "").strip()
    if not s:
        return None
    for cand in (s, s.split("'")[0].split("’")[0]):
        k = ledger.norm(cand)
        if k in idx:
            return idx[k]
    words = ledger.norm(s).split()
    for n in range(len(words) - 1, 0, -1):
        k = " ".join(words[:n])
        if k in idx:
            return idx[k]
    return None


def decide(readings: list[dict], kind: str) -> tuple[str | None, float]:
    """Bağımsız okumalardan bir değer: en az MIN_AGREE okuma aynı değeri veriyorsa ve o değer
    tek başına öndeyse (değer, uyuşma payı). Henüz karar yoksa ve okuma hakkı varsa (None, 0):
    bir okuma daha; hak bittiyse (BELIRSIZ, 0)."""
    vals = [valid_value(kind, r.get(kind, "")) or UNCERTAIN for r in readings]
    c = Counter(v for v in vals if v != UNCERTAIN)
    if c:
        (top, n), = c.most_common(1)
        others = max((m for v, m in c.items() if v != top), default=0)
        if n >= MIN_AGREE and n > others:
            return top, n / len(vals)
    if len(readings) < MAX_READINGS:
        return None, 0.0
    return UNCERTAIN, 0.0


def settled(readings: list[dict]) -> bool:
    """Her tür için karar verildi mi (bir tür daha okuma istiyorsa False)."""
    return all(decide(readings, k)[0] is not None for k in KINDS)


def conflicts(rows: list[dict]) -> list[dict]:
    """Aynı karakter + aynı tür + farklı değer, iki AYRI sayfada = aday çift (deterministik).
    Her satır: character_id, character_name, kind, value, page_no, source, confidence, quote,
    bbox, evidence_id, mention_id. BELIRSIZ değer çelişki kurmaz. Her değeri en erken sayfadaki
    satırı temsil eder; ikinci değer için ilkinin sayfasından farklı en erken satır alınır
    (aynı sayfadaki metin–resim farkı bu denetimin değil, metin–görsel teyidinin işidir)."""
    groups: dict[tuple, dict[str, list[dict]]] = {}
    for r in rows:
        if r["value"] == UNCERTAIN or r["kind"] not in KINDS:
            continue
        groups.setdefault((str(r["character_id"]), r["kind"]), {}).setdefault(r["value"], []).append(r)
    out = []
    for (cid, kind), by_val in groups.items():
        for v in by_val.values():
            v.sort(key=lambda r: (r["page_no"], r["source"] != "TEXT", -float(r["confidence"])))
        for x, y in combinations(sorted(by_val), 2):
            a = by_val[x][0]
            b = next((r for r in by_val[y] if r["page_no"] != a["page_no"]), None)
            if b is None:
                b_ = by_val[y][0]
                a = next((r for r in by_val[x] if r["page_no"] != b_["page_no"]), None)
                b = b_ if a is not None else None
            if a is None or b is None:
                continue
            a, b = sorted((a, b), key=lambda r: r["page_no"])
            out.append({"character_id": cid, "character_name": a["character_name"], "kind": kind,
                        "a": a, "b": b,
                        "pages_a": sorted({r["page_no"] for r in by_val[a["value"]]}),
                        "pages_b": sorted({r["page_no"] for r in by_val[b["value"]]})})
    out.sort(key=lambda c: (c["character_name"], c["kind"], c["a"]["page_no"], c["b"]["page_no"]))
    return out


def describe(row: dict) -> str:
    """Bir defter satırının editöre/yargıya anlatımı."""
    label = KINDS.get(row["kind"], {}).get("label", row["kind"])
    val = row["value"].replace("_", " ").lower()
    if row["source"] == "TEXT":
        return f"metin “{row['quote']}” → {label}: {val}"
    return f"resimde {label}: {val}"


# ------------------------------------------------------------ defter okuma
def reader_keys() -> dict[str, str]:
    from .. import prompts
    return {src: f"{name}@{prompts.load(name)[0].version}"
            for src, name in (("TEXT", TEXT_PROMPT), ("IMAGE", IMAGE_PROMPT))}


def characters(generation_id: str) -> list[dict]:
    return db.all_rows("SELECT id, canonical_name, aliases, kind FROM character WHERE generation_id=%s"
                       " AND COALESCE(traits->>'entity_scope','INDIVIDUAL')='INDIVIDUAL'"
                       " ORDER BY first_page NULLS LAST, canonical_name", generation_id)


def figures(generation_id: str) -> list[dict]:
    """Kimliği çözülmüş çizilmiş figürler: kutu ve görsel kanıt satırıyla."""
    return db.all_rows(
        "SELECT cm.id AS mention_id, cm.page_no, cm.character_id, cm.evidence_id, vr.bbox,"
        " ch.canonical_name FROM character_mention cm JOIN evidence e ON e.id=cm.evidence_id"
        " JOIN visual_region vr ON vr.id=e.region_id JOIN character ch ON ch.id=cm.character_id"
        " WHERE cm.generation_id=%s AND cm.via='VISUAL' AND cm.resolution='RESOLVED'"
        " AND vr.bbox IS NOT NULL ORDER BY cm.page_no, vr.id", generation_id)


def rows(generation_id: str, readers: dict[str, str] | None = None) -> list[dict]:
    """Defter satırları (varsayılan: yürürlükteki okuyucu sürümleri)."""
    readers = readers or reader_keys()
    return db.all_rows(
        "SELECT a.id, a.character_id, ch.canonical_name AS character_name, a.page_no, a.kind, a.value,"
        " a.source, a.confidence, a.evidence_id, a.mention_id, a.bbox, a.quote, a.reader, a.readings"
        " FROM character_attribute a JOIN character ch ON ch.id=a.character_id"
        " WHERE a.generation_id=%s AND ((a.source='TEXT' AND a.reader=%s) OR (a.source='IMAGE' AND a.reader=%s))"
        " ORDER BY ch.canonical_name, a.kind, a.page_no", generation_id, readers["TEXT"], readers["IMAGE"])


# --------------------------------------------------------- TEXT doldurma
async def fill_text(generation_id: str, llm: Llm | None = None) -> dict:
    from .. import prompts
    llm = llm or Llm(generation_id)
    reader = reader_keys()["TEXT"]
    pages = await asyncio.to_thread(source.read, generation_id)
    done = {r["page_no"] for r in db.all_rows("SELECT page_no FROM character_attribute_read WHERE"
                                              " generation_id=%s AND source='TEXT' AND reader=%s",
                                              generation_id, reader)}
    todo = [p for p in pages if p["page_no"] not in done]
    stats = {"reader": reader, "pages": len(pages), "pages_read_before": len(done), "parts": 0,
             "facts": 0, "unknown_subject": 0, "unverified_quote": 0, "bad_value": 0, "rows": 0,
             "parts_failed": 0}
    chars = characters(generation_id)
    idx = name_index(chars)
    if not todo or not chars:
        with db.tx() as c:
            for p in todo:            # karakter yoksa okunacak bir şey yok; yine de "okundu"
                c.execute("INSERT INTO character_attribute_read(generation_id, source, reader, page_no)"
                          " VALUES (%s,'TEXT',%s,%s) ON CONFLICT DO NOTHING", (generation_id, reader, p["page_no"]))
        return stats
    by_no = {p["page_no"]: p for p in pages}
    char_lines = "\n".join(f"- {ch['canonical_name']}" + (f" (diğer: {', '.join(ch['aliases'])})" if ch["aliases"] else "")
                           for ch in chars)
    ps = parts(paragraphs(todo))
    stats["parts"] = len(ps)

    async def read(part: list[dict]) -> tuple[list[dict], list[int], int | None]:
        ref, body = prompts.render(TEXT_PROMPT, characters=char_lines, vocabulary=vocabulary_text(),
                                   text=part_text(part))
        pnos = sorted({x["page"] for x in part})
        out, call_id = await llm.chat(DIRECTOR, [{"role": "user", "content": body}], prompt=ref,
                                      schema=TEXT_SCHEMA, pages=pnos, max_tokens=8000, temperature=0.0,
                                      thinking=False)
        return out["facts"], pnos, call_id

    got = await asyncio.gather(*(read(part) for part in ps), return_exceptions=True)
    failed = [g for g in got if isinstance(g, BaseException)]
    stats["parts_failed"] = len(failed)
    if failed and len(failed) == len(got):
        raise RuntimeError(f"metin okuyucu hiçbir parçada cevap vermedi: {failed[0]}")
    for g in got:
        if isinstance(g, BaseException):
            continue
        facts, pnos, call_id = g
        stats["facts"] += len(facts)
        with db.tx() as c:
            pidx = ledger.PageIndex.load(c, generation_id)
            for f in facts:
                cid = resolve_subject(f["subject"], idx)
                if not cid:
                    stats["unknown_subject"] += 1
                    continue
                value = valid_value(f["kind"], f["value"])
                if not value:
                    stats["bad_value"] += 1
                    continue
                loc = locate(by_no, int(f["page"]), int(f["paragraph"]) or None, f["quote"])
                if not loc or loc["page"] not in pnos:
                    stats["unverified_quote"] += 1
                    continue
                eid, ok = ledger.save_evidence(c, generation_id, pidx, page=loc["page"], kind="TEXT",
                                               paragraph_idx=loc["idx"], quote=loc["quote"])
                c.execute(
                    "INSERT INTO character_attribute(generation_id, character_id, page_no, kind, value, source,"
                    " confidence, evidence_id, quote, reader, readings, model_call_ids)"
                    " VALUES (%s,%s,%s,%s,%s,'TEXT',%s,%s,%s,%s,%s,%s)",
                    (generation_id, cid, loc["page"], f["kind"], value, 1.0 if ok else 0.6, eid, loc["quote"],
                     reader, db.J([{"subject": f["subject"], "value": f["value"]}]), [call_id] if call_id else []))
                stats["rows"] += 1
            for p in pnos:
                c.execute("INSERT INTO character_attribute_read(generation_id, source, reader, page_no,"
                          " model_call_ids) VALUES (%s,'TEXT',%s,%s,%s) ON CONFLICT DO NOTHING",
                          (generation_id, reader, p, [call_id] if call_id else []))
    return stats


# -------------------------------------------------------- IMAGE doldurma
async def fill_image(generation_id: str, llm: Llm | None = None) -> dict:
    from pathlib import Path
    from .. import prompts
    from ..config import settings
    from ..document import render_page
    from ..llm import image_part
    from ..vision import _crop
    llm = llm or Llm(generation_id)
    reader = reader_keys()["IMAGE"]
    figs = figures(generation_id)
    done = {str(r["mention_id"]) for r in db.all_rows(
        "SELECT mention_id FROM character_attribute_read WHERE generation_id=%s AND source='IMAGE' AND reader=%s",
        generation_id, reader)}
    todo = [f for f in figs if str(f["mention_id"]) not in done]
    stats = {"reader": reader, "figures": len(figs), "figures_read_before": len(done), "read": 0,
             "not_visible": 0, "rows": 0, "uncertain": 0, "calls": 0, "figures_failed": 0}
    if not todo:
        return stats
    gen = db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)
    bv = str(gen["book_version_id"])
    gdir = Path(render_page(bv, todo[0]["page_no"])["path"]).parent / "gallery" / generation_id
    sem = asyncio.Semaphore(settings().deep_concurrency * 2)

    async def one(f: dict) -> None:
        png = _crop(render_page(bv, f["page_no"])["path"], f["bbox"], gdir / f"fig-{f['mention_id']}.png").read_bytes()
        ref, body = prompts.render(IMAGE_PROMPT, page_no=str(f["page_no"]), name=f["canonical_name"],
                                   vocabulary=vocabulary_text())
        msgs = [{"role": "user", "content": [image_part(png), {"type": "text", "text": body}]}]

        async def ask() -> tuple[dict, int]:
            async with sem:
                return await llm.chat(VISION, msgs, prompt=ref, schema=IMAGE_SCHEMA, pages=[f["page_no"]],
                                      max_tokens=2048, temperature=VOTE_TEMPERATURE)
        # iki bağımsız okuma; uyuşmayan tür kaldıysa üçüncü
        first = await asyncio.gather(ask(), ask())
        readings, calls = [r for r, _ in first], [c for _, c in first]
        stats["calls"] += 2
        if not settled(readings):
            r3, c3 = await ask()
            readings.append(r3)
            calls.append(c3)
            stats["calls"] += 1
        visible = sum(bool(r.get("gorunur")) for r in readings) * 2 > len(readings)
        with db.tx() as c:
            if visible:
                for kind in KINDS:
                    value, share = decide(readings, kind)
                    value = value or UNCERTAIN
                    stats["uncertain"] += value == UNCERTAIN
                    c.execute(
                        "INSERT INTO character_attribute(generation_id, character_id, page_no, kind, value, source,"
                        " confidence, evidence_id, mention_id, bbox, reader, readings, model_call_ids)"
                        " VALUES (%s,%s,%s,%s,%s,'IMAGE',%s,%s,%s,%s,%s,%s,%s)",
                        (generation_id, f["character_id"], f["page_no"], kind, value, share, f["evidence_id"],
                         f["mention_id"], db.J(f["bbox"]), reader,
                         db.J([valid_value(kind, r.get(kind, "")) or UNCERTAIN for r in readings]), calls))
                    stats["rows"] += 1
            else:
                stats["not_visible"] += 1
            c.execute("INSERT INTO character_attribute_read(generation_id, source, reader, page_no, mention_id,"
                      " character_id, readings, model_call_ids) VALUES (%s,'IMAGE',%s,%s,%s,%s,%s,%s)"
                      " ON CONFLICT DO NOTHING",
                      (generation_id, reader, f["page_no"], f["mention_id"], f["character_id"], db.J(readings), calls))
        stats["read"] += 1

    res = await asyncio.gather(*(one(f) for f in todo), return_exceptions=True)
    failed = [r for r in res if isinstance(r, BaseException)]
    stats["figures_failed"] = len(failed)
    if failed and len(failed) == len(res):
        raise RuntimeError(f"görsel okuyucu hiçbir figürde cevap vermedi: {failed[0]}")
    return stats


async def fill(generation_id: str, llm: Llm | None = None) -> dict:
    """Defteri doldur (idempotent). Önce metin (director), sonra resim (derin görsel model):
    iki model kartta birlikte durmaz, sıra geçiş sayısını bir tutar."""
    llm = llm or Llm(generation_id)
    text = await fill_text(generation_id, llm)
    image = await fill_image(generation_id, llm)
    return {"text": text, "image": image}
