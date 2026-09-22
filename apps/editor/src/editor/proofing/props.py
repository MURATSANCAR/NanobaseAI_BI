"""Eşya sürekliliği: bir karakterin taşıdığı nesne (çanta, şapka değil — o SAPKA türünde
appearance'ın işi —, oyuncak, kitap, top…) aynı sahnede açıklamasız kaybolmuyor/belirmiyor mu;
kırılan ya da kaybolan bir nesne sonra açıklamasız sağlam/yerinde görünmüyor mu.

Kaynaklar (ikisi de kanıtlı):
  1. Özellik defterinin ESYA satırları (proofing._attributes; metin alıntı, resim figür kutusu).
     Defter boşsa doldurulur (idempotent; appearance koştuysa 0 çağrı).
  2. Metindeki nesne DURUM cümleleri: director parça başına bir çağrı, kapalı küme
     (YANINDA, BIRAKTI, KAYBOLDU, KIRILDI, BULDU, TAMIR_EDILDI); alıntı sayfada bulunmazsa kayıt yok.

Kurallar (deterministik aday çıkarma, _continuity.scenes ile sahne sınırı):
  A. SAHNE: aynı karakter aynı sahnede s.p'de X eşyasıyla (defter ya da metin), s.q'da (q≠p)
     defterin açık «eşya YOK» satırıyla görülüyor ve arada X için BIRAKTI/KAYBOLDU/KIRILDI/BULDU
     yok → "kayboldu" (q>p) ya da "belirdi" (q<p) adayı. Resimde BAŞKA bir eşya görünmesi X'in
     yokluğunu kanıtlamaz (defter figür başına tek değer taşır). Sahne sınırı = metindeki
     zaman/mekân geçişi kalıbı ya da hikâye dışı sayfa; genel kural, kitaba özel değil.
  B. DURUM: X için KIRILDI/KAYBOLDU s.p'de, sonra s.q'da (q>p) X YANINDA/BULUNDU (defter ya da
     metin) ve arada TAMIR_EDILDI/BULDU yok → "kırılan/kaybolan sağlam" adayı; sahneden bağımsız.
  Eşleme: eşya türü kapalı kümeden (ITEMS); DIGER türünde nesne adı normalleştirilmiş eşleşmeli.

Yargı: text_contradictions/appearance ile aynı biçim — kitabın tamamı + iki gözlem, iki sırada
kapalı soru (Llm.choose, logprobs); bulgu ancak min(C_ileri, C_geri) ≥ PROPS_JUDGE_MIN.
Her bulgu iki kanıt taşır (sayfa+alıntı ya da sayfa+bbox). Şiddet: B kuralı ve olasılık ≥
PROPS_ERROR_MIN → ERROR, diğerleri WARN.

Model çağrısı: parça başına 1 (durum okuyucu) + aday başına 2 (yargı) + defter boşsa
_attributes.fill (appearance ile paylaşılır).

ÖLÇÜM BEKLİYOR: eşikler ve okuyucu kesinliği gerçek kitapta ölçülmedi (docs/son-okuma/props.md)."""

from __future__ import annotations

import asyncio

from .. import schemas, source
from ..llm import Llm
from . import _attributes as A
from . import _continuity as C

NAME = "props"
VERSION = "1"
LABEL = "Eşya sürekliliği"

JUDGE_MIN = C.setting("props_judge_min", 0.5)     # EDITOR_PROPS_JUDGE_MIN; text_contradictions'ta ölçülen başlangıç
ERROR_MIN = C.setting("props_error_min", 0.8)     # EDITOR_PROPS_ERROR_MIN; B kuralında bu üstü ERROR
PARALLEL = C.setting("props_parallel", 4)         # EDITOR_PROPS_PARALLEL

STATES = ["YANINDA", "BIRAKTI", "KAYBOLDU", "KIRILDI", "BULDU", "TAMIR_EDILDI"]
BROKEN = ("KIRILDI", "KAYBOLDU")
RESTORES = {"KIRILDI": ("TAMIR_EDILDI", "BULDU"), "KAYBOLDU": ("BULDU", "TAMIR_EDILDI")}
DROPS = ("BIRAKTI", "KAYBOLDU", "KIRILDI")
ITEM_KINDS = [v for v in A.ITEMS if v not in (A.NONE, A.UNCERTAIN)]
STATE_TR = {"YANINDA": "yanında/elinde", "BIRAKTI": "bıraktı", "KAYBOLDU": "kaybetti", "KIRILDI": "kırıldı",
            "BULDU": "buldu/aldı", "TAMIR_EDILDI": "tamir edildi"}

STATE_SCHEMA = schemas.obj({"states": schemas.arr(schemas.obj({
    "subject": schemas.STR, "item": schemas.STR,
    "item_kind": {"type": "string", "enum": ITEM_KINDS},
    "state": {"type": "string", "enum": STATES},
    "page": schemas.INT, "paragraph": schemas.INT, "quote": schemas.STR}), 0, 120)})

READ = ("Aşağıdaki sayfalardan karakterlerin NESNELERİYLE ilgili durum cümlelerini çıkar; yalnız metnin "
        "açıkça söylediklerini. Karakterler:\n{characters}\n\n"
        "Nesne türleri (kapalı küme): {kinds}. Durumlar: YANINDA (taşıyor, elinde, kullanıyor, sırtında), "
        "BIRAKTI (bıraktı, verdi, çıkardı), KAYBOLDU (kaybetti, düşürdü, çalındı, uçtu gitti), KIRILDI "
        "(kırıldı, yırtıldı, bozuldu, parçalandı), BULDU (buldu, geri aldı, yenisini aldı, hediye edildi), "
        "TAMIR_EDILDI (tamir edildi, yapıştırıldı, dikildi, düzeldi).\n"
        "`subject` nesnenin kime ait olduğu (metindeki adıyla); `item` nesnenin metindeki adı (kısa: "
        "kırmızı çanta, uçurtma); `item_kind` kapalı kümeden en yakın tür; `quote` metinden kelimesi "
        "kelimesine. Rüya, hayal, oyun içindeki durumları alma; tahmin yapma.\n\n")

JUDGE = (
    "Soru: Aşağıdaki iki gözlem bu hikâyede AYNI karakterin AYNI nesnesi için İKİSİ BİRDEN doğru olabilir mi?\n"
    "Karakter: {name}. Nesne: {item}.\n"
    "Gözlem 1 (s.{p1}): {d1}\nGözlem 2 (s.{p2}): {d2}\n\n"
    "Önce kitabın tamamına bak: iki sayfa arasında metin bu değişimi açıklıyor mu (bıraktı, verdi, "
    "kaybetti, buldu, tamir edildi, yenisini aldı, sahne/gün değişti, eve gidip geldi); gözlemlerden biri "
    "rüya, hayal, oyun ya da geçmişe dönüş içinde mi; resimdeki gözlem kırpımın kestiği ya da elinde "
    "olmayan ama yakında duran bir nesne olabilir mi? Bunlardan biri varsa çelişki yoktur. Aynı sahne "
    "içinde nesne açıklamasız kayboluyor/beliriyor ya da kırılan/kaybolan nesne açıklamasız sağlam ve "
    "yerindeyse çelişkidir.\n\n"
    "Cevap tek harf: C = süreklilik hatası (metin açıklamıyor); U = çelişki yok (bağdaşıyor ya da "
    "metin/bağlam açıklıyor); B = karar verilemiyor.")


# ------------------------------------------------------------ gözlemler
def item_key(kind: str, item: str) -> str:
    """Eşya kimliği: kapalı tür; DIGER'de nesnenin normalleştirilmiş adı."""
    return f"DIGER:{C.norm(item)}" if kind == "DIGER" else kind


def observations(rows: list[dict], states: list[dict]) -> list[dict]:
    """Defter ESYA satırları + metin durum cümleleri tek listede. Her gözlem: character_id,
    character_name, item (anlatım), key (eşya kimliği ya da None=eşyasız), state, page, source
    (TEXT|IMAGE|STATE), quote|bbox, evidence_id|mention_id."""
    out = []
    for r in rows:
        if r["kind"] != "ESYA" or r["value"] == A.UNCERTAIN:
            continue
        none = r["value"] == A.NONE
        out.append({"character_id": str(r["character_id"]), "character_name": r["character_name"],
                    "item": "eşya yok" if none else r["value"].replace("_", " ").lower(),
                    "key": None if none else r["value"], "state": "YOK" if none else "YANINDA",
                    "page": r["page_no"], "idx": None, "source": r["source"], "quote": r.get("quote"),
                    "bbox": r.get("bbox"), "evidence_id": r.get("evidence_id"), "mention_id": r.get("mention_id")})
    for s in states:
        out.append({"character_id": s["character_id"], "character_name": s["character_name"],
                    "item": s["item"], "key": item_key(s["item_kind"], s["item"]), "state": s["state"],
                    "page": s["page"], "idx": s.get("idx"), "source": "STATE", "quote": s["quote"],
                    "bbox": None, "evidence_id": None, "mention_id": None})
    out.sort(key=lambda o: (o["character_id"], o["page"], o["source"] != "STATE"))
    return out


def describe(o: dict) -> str:
    if o["source"] == "IMAGE":
        return f"resimde {o['item']}" if o["key"] else "resimde elinde/yanında eşya yok"
    return f"metin “{o['quote']}” → {o['item']}: {STATE_TR.get(o['state'], o['state'].lower())}"


def _between(obs: list[dict], a: dict, b: dict, key: str, states: tuple) -> bool:
    lo, hi = sorted((a["page"], b["page"]))
    return any(o["key"] == key and o["state"] in states and lo <= o["page"] <= hi for o in obs)


def candidates(obs: list[dict], scene_of: dict[int, int]) -> list[dict]:
    """A ve B kuralı, deterministik. Her aday: rule, character_id/name, key, item, a, b."""
    by_char: dict[str, list[dict]] = {}
    for o in obs:
        by_char.setdefault(o["character_id"], []).append(o)
    out = []
    seen = set()
    for cid, xs in by_char.items():
        # A: aynı sahnede X var / eşya yok. Yoksunluk kanıtı yalnız defterin açık YOK satırıdır
        # (resimde başka bir eşya görünmesi X'in yokluğunu kanıtlamaz: defter figür başına tek değer)
        has = [o for o in xs if o["key"] and o["state"] == "YANINDA"]
        for h in has:
            for o in xs:
                if o["page"] == h["page"] or o["state"] != "YOK" or o["source"] == "STATE":
                    continue
                if scene_of.get(o["page"]) != scene_of.get(h["page"]):
                    continue
                if _between(xs, h, o, h["key"], DROPS + ("BULDU",)):
                    continue
                a, b = sorted((h, o), key=lambda z: z["page"])
                k = ("A", cid, h["key"], a["page"], b["page"])
                if k in seen:
                    continue
                seen.add(k)
                out.append({"rule": "A", "character_id": cid, "character_name": h["character_name"],
                            "key": h["key"], "item": h["item"], "a": a, "b": b,
                            "why": "aynı sahnede kayboluyor" if b is o else "aynı sahnede beliriyor"})
        # B: kırıldı/kayboldu, sonra sağlam/yerinde
        for br in (o for o in xs if o["state"] in BROKEN):
            later = [o for o in xs if o["key"] == br["key"] and o["page"] > br["page"]
                     and o["state"] in ("YANINDA", "BULDU")]
            for o in later:
                if o["state"] == "BULDU":
                    break                        # açıklama metinde: bundan sonrası aday değil
                if _between(xs, br, o, br["key"], RESTORES[br["state"]]):
                    continue
                k = ("B", cid, br["key"], br["page"], o["page"])
                if k not in seen:
                    seen.add(k)
                    out.append({"rule": "B", "character_id": cid, "character_name": br["character_name"],
                                "key": br["key"], "item": br["item"], "a": br, "b": o,
                                "why": f"{STATE_TR[br['state']]}, sonra açıklamasız yerinde"})
                break                            # ilk sağlam görünüş yeter
    out.sort(key=lambda c: (c["character_name"], c["rule"], c["a"]["page"], c["b"]["page"]))
    return out


# ------------------------------------------------------------------ okuma
async def read_states(llm: Llm, pages: list[dict], chars: list[dict]) -> tuple[list[dict], dict]:
    """Metin durum cümleleri; alıntı sayfada bulunmazsa ya da özne karaktere eşlenmezse kayıt yok."""
    idx = A.name_index(chars)
    by_no = C.by_no(pages)
    names = {str(ch["id"]): ch["canonical_name"] for ch in chars}
    lines = "\n".join(f"- {ch['canonical_name']}" + (f" (diğer: {', '.join(ch['aliases'])})" if ch.get("aliases") else "")
                      for ch in chars)
    ps = A.parts(A.paragraphs(pages))
    ask = READ.format(characters=lines, kinds=", ".join(ITEM_KINDS))

    async def one(part):
        out, _ = await llm.chat(C.DIRECTOR, [{"role": "user", "content": ask + C.INTRO + A.part_text(part)}],
                                schema=STATE_SCHEMA, pages=sorted({x["page"] for x in part}),
                                max_tokens=8000, temperature=0.0, thinking=False)
        return out["states"]
    got = await asyncio.gather(*(one(p) for p in ps), return_exceptions=True)
    failed = [g for g in got if isinstance(g, BaseException)]
    if ps and len(failed) == len(got):
        raise RuntimeError(f"durum okuyucu hiçbir parçada cevap vermedi: {failed[0]}")
    states, unknown, unverified = [], 0, 0
    for g in got:
        if isinstance(g, BaseException):
            continue
        for s in g:
            cid = A.resolve_subject(s["subject"], idx)
            if not cid:
                unknown += 1
                continue
            loc = A.locate(by_no, int(s["page"]), int(s["paragraph"]) or None, s["quote"])
            if not loc:
                unverified += 1
                continue
            states.append({"character_id": cid, "character_name": names[cid], "item": s["item"],
                           "item_kind": s["item_kind"], "state": s["state"], "page": loc["page"],
                           "idx": loc["idx"], "quote": loc["quote"]})
    return states, {"parts": len(ps), "parts_failed": len(failed), "states": len(states),
                    "unknown_subject": unknown, "unverified_quote": unverified}


# ------------------------------------------------------------------ yargı
def _ev(o: dict) -> dict:
    return {"page": o["page"], "source": o["source"], "state": o["state"], "item": o["item"],
            "quote": o.get("quote"), "bbox": o.get("bbox"),
            "evidence_id": str(o["evidence_id"]) if o.get("evidence_id") else None,
            "mention_id": str(o["mention_id"]) if o.get("mention_id") else None}


def finding_of(c: dict, v: dict) -> dict:
    a, b = c["a"], c["b"]
    p = v["p"]
    sev = "ERROR" if c["rule"] == "B" and p >= ERROR_MIN else "WARN"
    return {"page": b["page"], "severity": sev,
            "quote": b["quote"] if b["source"] != "IMAGE" else None,
            "bbox": b["bbox"] if b["source"] == "IMAGE" else None,
            "message": (f"Eşya sürekliliği — «{c['character_name']}», {c['item']}: s.{a['page']} {describe(a)}; "
                        f"s.{b['page']} {describe(b)}. {c['why'].capitalize()}; hikâye bunu açıklamıyor."),
            "suggestion": "İki yeri yan yana karşılaştırın; çizimi ya da metni düzeltin veya değişimi açıklayan "
                          "bir cümle ekleyin.",
            "details": {"rule": c["rule"], "character": c["character_name"], "character_id": c["character_id"],
                        "item_key": c["key"], "a": _ev(a), "b": _ev(b),
                        "judge": {k: v[k] for k in ("forward", "reverse")}, "p_contradiction": round(p, 3)}}


async def check(rows: list[dict], states: list[dict], pages: list[dict], llm) -> tuple[list[dict], dict]:
    story = C.story_pages(pages)
    scene_of = C.scenes(pages, C.scene_breaks(story))
    obs = observations(rows, states)
    cands = candidates(obs, scene_of)
    stats = {"observations": len(obs), "ledger_rows": sum(o["source"] != "STATE" for o in obs),
             "state_rows": len(states), "scenes": len(set(scene_of.values())), "candidates": len(cands),
             "judge_failed": 0, "confirmed": 0, "candidates_detail": []}
    findings = []
    if cands:
        text = C.book_text(story)
        sem = asyncio.Semaphore(PARALLEL)

        def body(c, x, y):
            return C.INTRO + text + "\n\n" + JUDGE.format(name=c["character_name"], item=c["item"],
                                                          p1=x["page"], d1=describe(x), p2=y["page"], d2=describe(y))
        verdicts = await asyncio.gather(
            *(C.judge_both(llm, body(c, c["a"], c["b"]), body(c, c["b"], c["a"]), sem,
                           sorted({c["a"]["page"], c["b"]["page"]})) for c in cands), return_exceptions=True)
        for c, v in zip(cands, verdicts):
            d = {"rule": c["rule"], "character": c["character_name"], "item": c["item"], "a": _ev(c["a"]), "b": _ev(c["b"])}
            if isinstance(v, BaseException):
                stats["judge_failed"] += 1
                stats["candidates_detail"].append({**d, "p": None})
                continue
            stats["candidates_detail"].append({**d, "p": round(v["p"], 3)})
            if v["p"] >= JUDGE_MIN:
                findings.append(finding_of(c, v))
    stats["confirmed"] = len(findings)
    return findings, stats


async def run(generation_id: str):
    llm = Llm(generation_id)
    fill = await A.fill(generation_id, llm)                 # idempotent; appearance doldurduysa 0 çağrı
    rows = await asyncio.to_thread(A.rows, generation_id)
    pages = await asyncio.to_thread(source.read, generation_id)
    chars = await asyncio.to_thread(A.characters, generation_id)
    states, rstats = await read_states(llm, C.story_pages(pages), chars)
    findings, stats = await check(rows, states, pages, llm)
    stats["reader"] = rstats
    stats["ledger"] = fill
    findings.append({"page": None, "severity": "INFO",
                     "message": (f"Eşya sürekliliği: {stats['ledger_rows']} defter ve {stats['state_rows']} metin "
                                 f"durum kaydı, {stats['scenes']} sahne; {stats['candidates']} aday yargılandı, "
                                 f"{stats['confirmed']} bulgu. Eşikler henüz gerçek kitapta ölçülmedi.")})
    return findings, stats
