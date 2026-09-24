"""Mekân tutarlılığı: aynı mekânın metinde çelişen tarifi (odanın/evin düzeni, kapı/pencere
yönü, kat, şehir/ülke) ve metnin söylediği ile resmin gösterdiğinin kapalı-küme karşılaştırması.

Figür kimliği gibi bir MEKÂN kimliği yoktur (resimde "aynı oda" tanınmaz). Bu yüzden:
  1. METİN–METİN: director parça başına bir çağrı, mekân bilgisi listesi (place, aspect kapalı
     kümeden, value, sayfa/paragraf/alıntı). Aynı normalleştirilmiş mekân adı + aynı aspect +
     farklı değer, iki ayrı sayfada → aday çift (deterministik). Yargı iki sırada kapalı soru
     (Llm.choose), bulgu ancak min(C_ileri, C_geri) ≥ SETTING_JUDGE_MIN.
  2. METİN–RESİM (yalnız ölçülebilen üç aspect): IC_DIS (içeride/dışarıda), ISIK (gündüz/gece),
     HAVA (güneşli/yağmurlu/karlı). Metin s.p'de bunlardan birini söylüyorsa ve s.p resimliyse
     (page_scan var) derin görsel modele sayfa görüntüsüyle kapalı soru (Llm.choose, tek çağrı,
     olasılık logprobs'tan). Metnin değerine ters cevabın olasılığı ≥ SETTING_IMAGE_MIN → bulgu;
     "belli değil" bulgu değil. Oda düzeni, kapı/pencere yönü, kat, şehir resimden ÖLÇÜLMEZ
     (belgede yazılı; uydurulmaz).
Her bulgu iki kanıt taşır: iki sayfa+alıntı (metin–metin) ya da sayfa+alıntı ve aynı sayfanın
resmi (metin–resim; bbox tam sayfa [0,0,1000,1000]).

Model çağrısı: parça başına 1 + metin–metin aday başına 2 + görsel aspect'li metin bilgisi başına 1.
ÖLÇÜM BEKLİYOR: eşikler ve okuyucu kesinliği gerçek kitapta ölçülmedi (docs/son-okuma/setting.md)."""

from __future__ import annotations

import asyncio
from itertools import combinations

from .. import schemas, source
from ..llm import Llm
from . import _attributes as A
from . import _continuity as C

NAME = "setting"
VERSION = "1"
LABEL = "Mekân tutarlılığı"

JUDGE_MIN = C.setting("setting_judge_min", 0.5)    # EDITOR_SETTING_JUDGE_MIN
IMAGE_MIN = C.setting("setting_image_min", 0.7)    # EDITOR_SETTING_IMAGE_MIN: resmin "ters" olasılığı
PARALLEL = C.setting("setting_parallel", 4)        # EDITOR_SETTING_PARALLEL

ASPECTS = ["KONUM", "DUZEN", "KAPI_YONU", "PENCERE_YONU", "KAT", "IC_DIS", "ISIK", "HAVA"]
ASPECT_TR = {"KONUM": "konum (şehir/ülke/neyin yanında)", "DUZEN": "düzen (odada/evde ne nerede)",
             "KAPI_YONU": "kapının yeri/yönü", "PENCERE_YONU": "pencerenin yeri/yönü", "KAT": "kat",
             "IC_DIS": "içeride/dışarıda", "ISIK": "gündüz/gece", "HAVA": "hava"}
# Resimden ölçülebilen aspect'ler: kapalı değer kümesi, model cevabı harf, harf→değer.
VISUAL = {
    "IC_DIS": {"values": ["IC", "DIS"], "letters": {"I": "IC", "D": "DIS"},
               "question": "Bu resimdeki sahne İÇERİDE mi (bir odanın/binanın içinde) yoksa DIŞARIDA mı?",
               "hint": "I = içeride, D = dışarıda, B = belli değil / ikisi de var"},
    "ISIK": {"values": ["GUNDUZ", "GECE"], "letters": {"G": "GUNDUZ", "K": "GECE"},
             "question": "Bu resimdeki sahne GÜNDÜZ mü yoksa GECE mi geçiyor (gökyüzü, ışık, lamba, yıldız)?",
             "hint": "G = gündüz, K = gece/karanlık, B = belli değil (kapalı mekân, ipucu yok)"},
    "HAVA": {"values": ["GUNESLI", "YAGMURLU", "KARLI"], "letters": {"G": "GUNESLI", "Y": "YAGMURLU", "K": "KARLI"},
             "question": "Bu resimde hava nasıl görünüyor?",
             "hint": "G = güneşli/açık, Y = yağmurlu, K = karlı, B = belli değil (kapalı mekân, ipucu yok)"},
}
VALUE_TR = {"IC": "içeride", "DIS": "dışarıda", "GUNDUZ": "gündüz", "GECE": "gece", "GUNESLI": "güneşli",
            "YAGMURLU": "yağmurlu", "KARLI": "karlı"}

FACT_SCHEMA = schemas.obj({"facts": schemas.arr(schemas.obj({
    "place": schemas.STR, "aspect": {"type": "string", "enum": ASPECTS}, "value": schemas.STR,
    "page": schemas.INT, "paragraph": schemas.INT, "quote": schemas.STR}), 0, 120)})

READ = ("Aşağıdaki sayfalardan MEKÂN bilgilerini çıkar; yalnız metnin açıkça söylediklerini.\n"
        "`place` mekânın metindeki adı (kısa ve her yerde aynı: Ali'nin odası, ev, okul, köy, orman); "
        "`aspect` kapalı kümeden: KONUM (hangi şehir/ülke, neyin yanında/karşısında), DUZEN (odada/evde neyin "
        "nerede olduğu), KAPI_YONU, PENCERE_YONU, KAT (kaçıncı kat), IC_DIS (sahne o an içeride mi dışarıda mı; "
        "değer IC ya da DIS), ISIK (o an gündüz mü gece mi; değer GUNDUZ ya da GECE), HAVA (değer GUNESLI, "
        "YAGMURLU ya da KARLI). `value` kısa; iki yerde aynı özellik söyleniyorsa aynı kelimelerle. "
        "`quote` metinden kelimesi kelimesine. Rüya, hayal, oyun içindeki bilgileri alma; tahmin yapma.\n\n")

JUDGE = (
    "Soru: Aşağıdaki iki mekân bilgisi bu hikâyede AYNI mekân için İKİSİ BİRDEN doğru olabilir mi?\n"
    "Mekân: {place}. Özellik: {aspect}.\n"
    "Bilgi 1 (s.{p1}): “{q1}” → {v1}\nBilgi 2 (s.{p2}): “{q2}” → {v2}\n\n"
    "Önce kitabın tamamına bak: gerçekten aynı mekân mı (aynı adla anılan iki farklı yer olabilir); "
    "arada metin değişimi açıklıyor mu (taşındılar, eşyalar yer değiştirdi, ev yenilendi, başka odaya "
    "geçtiler); bilgilerden biri rüya, hayal, oyun, bir karakterin yanılgısı ya da bakış açısına göre "
    "değişen bir tarif mi (sağ/sol)? Bunlardan biri varsa çelişki yoktur.\n\n"
    "Cevap tek harf: C = mekân çelişkisi (aynı mekân, ikisi birden doğru olamaz, metin açıklamıyor); "
    "U = çelişki yok; B = karar verilemiyor.")


# --------------------------------------------------------------- saf parça
_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def valid_visual(aspect: str, value: str) -> str | None:
    """Modelin yazdığı değer kapalı kümeye (Türkçe harfler sadeleştirilip) çevrilir; küme dışı None."""
    v = (value or "").strip().translate(_TR).upper()
    if aspect in VISUAL and v in VISUAL[aspect]["values"]:
        return v
    return None


def pair_facts(facts: list[dict]) -> list[dict]:
    """Aynı mekân + aynı aspect + farklı değer, iki ayrı sayfada → aday. Her değeri en erken
    sayfadaki bilgi temsil eder. Görsel aspect'lerde değer kapalı kümeye çevrilir."""
    groups: dict[tuple, dict[str, dict]] = {}
    for f in facts:
        place = C.norm(f["place"])
        val = valid_visual(f["aspect"], f["value"]) if f["aspect"] in VISUAL else C.norm(f["value"])
        if not place or not val:
            continue
        groups.setdefault((place, f["aspect"]), {}).setdefault(val, f)
    out = []
    for (place, aspect), vals in groups.items():
        for x, y in combinations(sorted(vals.values(), key=lambda f: (f["page"], f["idx"] or 0)), 2):
            if x["page"] == y["page"]:
                continue
            out.append({"place": x["place"], "aspect": aspect, "a": x, "b": y})
    out.sort(key=lambda c: (c["place"], c["aspect"], c["a"]["page"], c["b"]["page"]))
    return out


def visual_facts(facts: list[dict], illustrated: set) -> list[dict]:
    """Resimden ölçülebilen aspect'li metin bilgileri, resimli sayfalarda; sayfa+aspect başına bir."""
    seen = set()
    out = []
    for f in sorted(facts, key=lambda f: (f["page"], f["idx"] or 0)):
        v = valid_visual(f["aspect"], f["value"])
        if not v or f["page"] not in illustrated or (f["page"], f["aspect"]) in seen:
            continue
        seen.add((f["page"], f["aspect"]))
        out.append({**f, "value": v})
    return out


def image_verdict(aspect: str, text_value: str, probs: dict) -> dict:
    """Modelin harf dağılımından: resmin metne TERS bir değer verme olasılığı ve o değer."""
    letters = VISUAL[aspect]["letters"]
    against = {letters[k]: p for k, p in probs.items() if k in letters and letters[k] != text_value}
    top = max(against, key=against.get) if against else None
    return {"p_against": max(against.values()) if against else 0.0, "seen": top,
            "p_agree": sum(p for k, p in probs.items() if letters.get(k) == text_value),
            "p_unclear": probs.get("B", 0.0)}


# ------------------------------------------------------------------ okuma
async def read_facts(llm: Llm, pages: list[dict]) -> tuple[list[dict], dict]:
    by_no = C.by_no(pages)
    ps = A.parts(A.paragraphs(pages))

    async def one(part):
        out, _ = await llm.chat(C.DIRECTOR, [{"role": "user", "content": READ + C.INTRO + A.part_text(part)}],
                                schema=FACT_SCHEMA, pages=sorted({x["page"] for x in part}),
                                max_tokens=8000, temperature=0.0, thinking=False)
        return out["facts"]
    got = await asyncio.gather(*(one(p) for p in ps), return_exceptions=True)
    failed = [g for g in got if isinstance(g, BaseException)]
    if ps and len(failed) == len(got):
        raise RuntimeError(f"mekân okuyucu hiçbir parçada cevap vermedi: {failed[0]}")
    facts, unverified = [], 0
    for g in got:
        if isinstance(g, BaseException):
            continue
        for f in g:
            loc = A.locate(by_no, int(f["page"]), int(f["paragraph"]) or None, f["quote"])
            if not loc:
                unverified += 1
                continue
            facts.append({"place": f["place"], "aspect": f["aspect"], "value": f["value"], "page": loc["page"],
                          "idx": loc["idx"], "quote": loc["quote"]})
    return facts, {"parts": len(ps), "parts_failed": len(failed), "facts": len(facts), "unverified_quote": unverified}


async def ask_image(llm, aspect: str, page_no: int, png: bytes) -> dict:
    from ..llm import image_part
    spec = VISUAL[aspect]
    body = (f"Resimli çocuk kitabının {page_no}. sayfası. {spec['question']}\n"
            f"Yalnız resme bak, metni okuma. Cevap tek harf: {spec['hint']}.")
    probs, _ = await llm.choose(C.VISION, [{"role": "user", "content": [image_part(png), {"type": "text", "text": body}]}],
                                list(spec["letters"]) + ["B"], pages=[page_no])
    return probs


# ------------------------------------------------------------------ bulgu
def _ev(f: dict) -> dict:
    return {"page": f["page"], "paragraph": f.get("idx"), "place": f["place"], "aspect": f["aspect"],
            "value": f["value"], "quote": f["quote"]}


def finding_text(c: dict, v: dict) -> dict:
    a, b = c["a"], c["b"]
    return {"page": b["page"], "severity": "WARN", "quote": b["quote"],
            "message": (f"Mekân tutarlılığı ({ASPECT_TR[c['aspect']]}) — «{c['place']}»: s.{a['page']} “{a['quote']}” "
                        f"({a['value']}); s.{b['page']} “{b['quote']}” ({b['value']}). Hikâye bu farkı açıklamıyor."),
            "suggestion": "İki tarifi karşılaştırıp birini düzeltin ya da değişimi açıklayan bir cümle ekleyin.",
            "details": {"kind": "TEXT_TEXT", "place": c["place"], "aspect": c["aspect"], "a": _ev(a), "b": _ev(b),
                        "judge": {k: v[k] for k in ("forward", "reverse")}, "p_contradiction": round(v["p"], 3)}}


def finding_image(f: dict, verdict: dict) -> dict:
    return {"page": f["page"], "severity": "WARN", "quote": f["quote"], "bbox": [0, 0, 1000, 1000],
            "message": (f"Mekân tutarlılığı ({ASPECT_TR[f['aspect']]}) — s.{f['page']} metin “{f['quote']}” "
                        f"({VALUE_TR[f['value']]}) derken resim {VALUE_TR[verdict['seen']]} gösteriyor "
                        f"(olasılık {verdict['p_against']:.2f})."),
            "suggestion": "Sayfanın resmiyle metnini karşılaştırın; çizimi ya da cümleyi düzeltin.",
            "details": {"kind": "TEXT_IMAGE", "aspect": f["aspect"], "a": _ev(f),
                        "b": {"page": f["page"], "source": "IMAGE", "bbox": [0, 0, 1000, 1000], "seen": verdict["seen"]},
                        "image": {k: round(verdict[k], 3) for k in ("p_against", "p_agree", "p_unclear")}}}


async def check(facts: list[dict], pages: list[dict], llm, illustrated: set | None = None,
                png_of=None) -> tuple[list[dict], dict]:
    """png_of(page_no) -> bytes: resimli sayfanın görüntüsü (run() verir; testte sahte)."""
    story = C.story_pages(pages)
    cands = pair_facts(facts)
    vfacts = visual_facts(facts, illustrated or set()) if png_of else []
    stats = {"facts": len(facts), "candidates": len(cands), "visual_facts": len(vfacts), "judge_failed": 0,
             "image_failed": 0, "confirmed_text": 0, "confirmed_image": 0, "candidates_detail": [],
             "visual_detail": []}
    findings = []
    sem = asyncio.Semaphore(PARALLEL)
    if cands:
        text = C.book_text(story)

        def body(c, x, y):
            return C.INTRO + text + "\n\n" + JUDGE.format(place=c["place"], aspect=ASPECT_TR[c["aspect"]],
                                                          p1=x["page"], q1=x["quote"], v1=x["value"],
                                                          p2=y["page"], q2=y["quote"], v2=y["value"])
        verdicts = await asyncio.gather(
            *(C.judge_both(llm, body(c, c["a"], c["b"]), body(c, c["b"], c["a"]), sem,
                           sorted({c["a"]["page"], c["b"]["page"]})) for c in cands), return_exceptions=True)
        for c, v in zip(cands, verdicts):
            d = {"place": c["place"], "aspect": c["aspect"], "a": _ev(c["a"]), "b": _ev(c["b"])}
            if isinstance(v, BaseException):
                stats["judge_failed"] += 1
                stats["candidates_detail"].append({**d, "p": None})
                continue
            stats["candidates_detail"].append({**d, "p": round(v["p"], 3)})
            if v["p"] >= JUDGE_MIN:
                findings.append(finding_text(c, v))
                stats["confirmed_text"] += 1
    if vfacts:
        async def one(f):
            async with sem:
                return await ask_image(llm, f["aspect"], f["page"], png_of(f["page"]))
        got = await asyncio.gather(*(one(f) for f in vfacts), return_exceptions=True)
        for f, probs in zip(vfacts, got):
            if isinstance(probs, BaseException):
                stats["image_failed"] += 1
                stats["visual_detail"].append({**_ev(f), "p_against": None})
                continue
            v = image_verdict(f["aspect"], f["value"], probs)
            stats["visual_detail"].append({**_ev(f), "seen": v["seen"], "p_against": round(v["p_against"], 3)})
            if v["seen"] and v["p_against"] >= IMAGE_MIN:
                findings.append(finding_image(f, v))
                stats["confirmed_image"] += 1
    return findings, stats


async def run(generation_id: str):
    from pathlib import Path
    from .. import db
    from ..document import render_page
    llm = Llm(generation_id)
    pages = await asyncio.to_thread(source.read, generation_id)
    facts, rstats = await read_facts(llm, C.story_pages(pages))
    # a page with no picture has only its 'no-illustration' screen row: nothing to look at
    illustrated = {r["page_no"] for r in await asyncio.to_thread(
        db.all_rows, "SELECT DISTINCT page_no FROM page_scan WHERE generation_id=%s"
        " AND alias NOT IN ('deferred-to-deep','no-illustration')", generation_id)}
    gen = await asyncio.to_thread(db.one, "SELECT book_version_id FROM generation WHERE id=%s", generation_id)
    bv = str(gen["book_version_id"])

    def png_of(page_no: int) -> bytes:
        return Path(render_page(bv, page_no)["path"]).read_bytes()
    findings, stats = await check(facts, pages, llm, illustrated, png_of)
    stats["reader"] = rstats
    findings.append({"page": None, "severity": "INFO",
                     "message": (f"Mekân tutarlılığı: {stats['facts']} mekân bilgisi okundu; {stats['candidates']} "
                                 f"metin–metin adayı yargılandı ({stats['confirmed_text']} bulgu), "
                                 f"{stats['visual_facts']} bilgi resimle karşılaştırıldı ({stats['confirmed_image']} "
                                 "bulgu). Oda düzeni, kapı/pencere yönü, kat ve şehir resimden ölçülmez. "
                                 "Eşikler henüz gerçek kitapta ölçülmedi.")})
    return findings, stats
