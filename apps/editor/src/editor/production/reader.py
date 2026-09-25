"""Okur araçları (Kitap Tasarım Stüdyosu): çocuk gözüyle okuma ve sayfa çevirme merakı.

**Çocuk gözüyle okuma.** Zeki AI sayfa planının metnini kitabın hedef okur yaşındaki (profildeki bandın alt ucu:
bandın en zorlanacak okuru) bir okur gibi sayfa sayfa okur ve takıldığı yerleri işaretler: anlaşılmayan
kelime/deyim, uzun ya da karışık cümle, kimin konuştuğu belirsiz konuşma, resimle (sahne tarifiyle) çelişen metin,
sıkıcı/tekrarlı yer, merak kaybı. Her işaretin alıntısı o metin parçasında (paragraf, balon, serbest yazı) birebir
bulunmak ZORUNDADIR; bulunmazsa işaret atılır (son okumanın yaş uygunluğu denetimindeki kalıp) ve sayılır.

Tek okuma gürültülüdür (aynı model aynı sayfada her okumada başka yer işaretler): her sayfa `passes` kez, birbirinden
bağımsız (sıcaklıkla) okunur; aynı parçada örtüşen işaretler kümelenir ve yalnız okumaların çoğunluğunda (> yarısı)
geçen küme gösterilir. Kaç okuma yapılacağı yönetim ayarıdır (köprü `STUDIO_READER_PASSES` gönderir). Metinden
denetlenebilen iddialar (resimle çelişki, konuşanın belirsizliği) editöre gitmeden çürütülmeye çalışılır: ayrı bir
kapalı küme sorusu iddiayı doğrulamazsa işaret düşer (sayılır, `refuted`).

**Sayfa çevirme merakı** (yalnız resimli kitapta): her çift sayfanın (sol çift numara + sağ tek numara) sayfa
çevrilmeden önce okunan son cümlesi için "sonra ne oldu?" gerilimi kapalı kümeyle ölçülür (tek belirteç, olasılık
dağılımı: tek çağrı oylamanın yerini tutar). Güçlü değilse resimli kitap zanaatından bir kalıpla (soru, yarım kalan
eylem, ses sözcüğü, "ama…", beklenti) yeniden yazım önerilir; öneri hikâyeye olay/duygu ekliyor, özgün cümleyi
eksiltiyor ya da sonraki sayfada olmayanı vaat ediyorsa çürütülür ve yenisi yazılır (en çok okuma sayısı kadar aday).
Güçlüyse öneri yok.

Kurallar kitaptan bağımsızdır: istemde kitap adı/karakter/eşik yoktur; yaş ve resim kararı işin profilinden gelir.
Model gateway üzerinden (`FileLlm`, kayıt işin provenance.jsonl'una). Sonuç `okur/<koşu>.json` (koşu sürerken her
sayfa bitince yazılır; süreç düşerse yalnız eksik sayfalar yeniden okunur), editör kararları ayrı dosyada
(`okur/<koşu>.decisions.json`: koşu sürerken verilen karar ezilmez). Öneriyi uygulamak metni ekranda değiştirir ve
sayfa düzeninin otomatik kayıt sırasından gider (geri alınabilir, her kayıt `plan-history`'de).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import secrets
import time
from collections import Counter
from pathlib import Path

from . import plan as plan_mod
from . import studio
from ..llm import PromptRef

DIR = "okur"
ALIAS = os.environ.get("STUDIO_READER_ALIAS", "book-director")
PARALLEL = max(1, int(os.environ.get("STUDIO_READER_PARALLEL", "4") or 4))   # aynı anda giden model çağrısı
TEMPERATURE = 0.7            # okumalar bağımsız olsun: aynı sıcaklıkta tekrar eden okuma oylamayı anlamsızlaştırır
STALE_SECONDS = 180          # koşu kaydı bu kadar süre yenilenmediyse ve bu süreçte görev yoksa «yarıda kaldı»
READ = PromptRef("studio_reader_child", "1")
TURN_JUDGE = PromptRef("studio_reader_turn_judge", "1")
TURN_FIX = PromptRef("studio_reader_turn_fix", "1")
REFUTE = PromptRef("studio_reader_refute", "1")          # denetlenebilir işaretin çürütülmesi (resim, konuşan)
TURN_REFUTE = PromptRef("studio_reader_turn_refute", "1")  # sayfa sonu önerisi hikâyeyi değiştiriyor mu
KEEP_P = 0.5                 # çürütmede «iddia doğru» olasılığı bundan küçükse işaret/öneri düşer (yazı turası sınırı)

KINDS = {                    # kod → ekrandaki ad
    "KELIME": "Anlaşılmayan kelime ya da deyim",
    "CUMLE": "Uzun ya da karışık cümle",
    "KONUSAN": "Kimin konuştuğu belirsiz",
    "RESIM": "Resimle çelişiyor",
    "SIKICI": "Sıkıcı ya da tekrarlı",
    "MERAK": "Merak kayboluyor",
}
TECHNIQUES = {
    "SORU": "Soru",
    "YARIM_EYLEM": "Yarım kalan eylem",
    "SES": "Ses sözcüğü",
    "AMA": "«Ama…» kalıbı",
    "BEKLENTI": "Beklenti («tam o sırada…»)",
}
DECISIONS = {"applied", "dismissed", "accepted", "rejected", "open"}

_tasks: dict[str, asyncio.Task] = {}


def _now() -> float:
    return time.time()


# ------------------------------------------------------------------ kitap bilgisi
def reader_age(d: Path) -> dict:
    """Okur yaşı: profil bandının alt ucu (bandın en genç okuru metinde ilk takılandır)."""
    prof = studio.read(d, "profile.json") or {}
    lo, hi = prof.get("age_min"), prof.get("age_max")
    age = lo if lo is not None else hi
    return {"age": int(age) if age is not None else None, "band": [lo, hi] if lo is not None else None,
            "source": prof.get("age_source")}


def who(age: int) -> str:
    """«Sen … yaşında bir …» (ek ünlü uyumuyla)."""
    return "çocuksun" if age <= 12 else ("gençsin" if age <= 17 else "okursun")


def picture_book(d: Path, plan: dict) -> bool:
    """Resimli kitap: profilde her sayfa resimli ya da planın sayfalarının en az yarısında resim var."""
    prof = studio.read(d, "profile.json") or {}
    if prof.get("illustration") == "HER_SAYFA":
        return True
    pages = plan.get("pages") or []
    return bool(pages) and sum(1 for p in pages if p.get("art")) * 2 >= len(pages)


def _runs_text(runs) -> str:
    return "".join(r.get("text", "") for r in runs or [])


def page_items(pg: dict) -> list[dict]:
    """Sayfada okunan metin parçaları, okuma sırasıyla: sayfa metninin blokları, balonlar, serbest yazılar."""
    out = []
    for b in (pg.get("text") or {}).get("blocks", []):
        t = _runs_text(b.get("runs"))
        if t.strip():
            out.append({"target": "block", "id": b["id"], "kind": b.get("kind", "para"), "text": t})
    for bb in pg.get("bubbles") or []:
        if (bb.get("text") or "").strip():
            out.append({"target": "bubble", "id": bb["id"], "speaker": bb.get("speaker"), "text": bb["text"]})
    for x in sorted(pg.get("texts") or [], key=lambda x: x.get("z", 0)):
        t = _runs_text(x.get("runs"))
        if t.strip():
            out.append({"target": "free", "id": x["id"], "text": t})
    return out


def scene_text(d: Path, pg: dict, plan: dict) -> str | None:
    """Sayfadaki resmin tarifi (sahne planından); fotoğrafsa adı; resim yoksa None."""
    art = pg.get("art")
    if not art:
        return None
    if art.get("asset"):
        a = (plan.get("assets") or {}).get(art["asset"]) or {}
        return f"Sayfada bir fotoğraf var ({a.get('name') or 'adı yok'}); içeriği bilinmiyor."
    ap = studio.read(d, "artplan.json") or {}
    sc = next((s for s in ap.get("scenes", []) if s.get("art_id") and s.get("art_id") == art.get("id")), None)
    if not sc:
        return None
    parts = [sc.get("scene") or sc.get("moment") or ""]
    if sc.get("setting"):
        parts.append(f"Mekân: {sc['setting']}")
    if sc.get("characters"):
        parts.append("Resimdeki karakterler: " + ", ".join(sc["characters"]))
    txt = ". ".join(p.strip().rstrip(".") for p in parts if p and p.strip())
    return txt or None


# ------------------------------------------------------------------ alıntı doğrulama
_FOLD = {"’": "'", "‘": "'", "`": "'", "“": '"', "”": '"', "«": '"', "»": '"', "–": "-", "—": "-", "­": ""}


def _fold(text: str) -> tuple[str, list[int]]:
    """Karşılaştırma biçimi (tırnak/tire birleşik, boşluk tek, Türkçe küçük harf) ve her harfin özgün yeri."""
    out, idx, space = [], [], False
    for i, ch in enumerate(text):
        c = _FOLD.get(ch, ch)
        if not c:
            continue
        if c.isspace():
            if space or not out:
                continue
            c, space = " ", True
        else:
            space = False
            c = "ı" if c == "I" else "i" if c == "İ" else c.lower()
        for cc in c:
            out.append(cc)
            idx.append(i)
    return "".join(out), idx


def locate(quote: str, text: str) -> tuple[int, int] | None:
    """Alıntının metindeki yeri (özgün harf aralığı). Birebir değilse None — işaret atılır."""
    q = (quote or "").strip().strip("\"'«»“”‘’").strip()
    if not q:
        return None
    nt, idx = _fold(text)
    for cand in (q, q.rstrip(".,;:!?…").strip()):
        nq = _fold(cand)[0].strip()
        if len(nq) < 2:
            continue
        pos = nt.find(nq)
        if pos >= 0:
            return idx[pos], idx[pos + len(nq) - 1] + 1
    return None


_SENT = re.compile(r"(?<=[.!?…])[\"”’»)]*\s+")
_OPEN, _CLOSE = "“«", "”»"
_STARTS = "“\"«‘'-–—("


def last_sentence(text: str) -> tuple[int, int] | None:
    """Metnin son cümlesinin yeri (son boş olmayan satırın son cümlesi). Tırnak içindeki noktalama cümleyi
    bitirmez; kapanan tırnaktan sonra küçük harfle süren konuşma eki («… diye zıpladı») aynı cümledir."""
    t = text.rstrip()
    if not t.strip():
        return None
    line_start = t.rfind("\n") + 1
    line = t[line_start:]
    cut = 0
    for m in _SENT.finditer(line):
        rest = line[m.end():]
        head = line[:m.end()]
        inside = sum(head.count(c) for c in _OPEN) > sum(head.count(c) for c in _CLOSE)
        if rest.strip() and not inside and (rest[0].isupper() or rest[0] in _STARTS):
            cut = m.end()
    start = line_start + cut
    while start < len(t) and t[start].isspace():
        start += 1
    return (start, len(t)) if start < len(t) else None


# ------------------------------------------------------------------ çocuk gözüyle okuma
def _handles(items: list[dict]) -> dict[str, dict]:
    return {f"M{i + 1}": it for i, it in enumerate(items)}


def _item_line(h: str, it: dict) -> str:
    if it["target"] == "bubble":
        sp = it.get("speaker")
        kind = f"konuşma balonu, konuşan: {sp}" if sp else "konuşma balonu, konuşan belirtilmemiş"
    elif it["target"] == "free":
        kind = "sayfadaki ayrı yazı"
    else:
        kind = {"dialogue": "konuşma", "sound": "ses sözcüğü", "heading": "başlık"}.get(it.get("kind"), "paragraf")
    return f"[{h}] ({kind}) {it['text']}"


def child_prompt(age: int, items: list[dict], scene: str | None, before: str) -> str:
    handles = _handles(items)
    listen = " ya da bir büyük sana sesli okuyor" if age <= 7 else ""
    kinds = [("KELIME", "anlamını bilmediğin kelime ya da deyim"),
             ("CUMLE", "çok uzun ya da karışık, okurken kaybolduğun cümle"),
             ("KONUSAN", "bir konuşmada kimin konuştuğunu anlayamadığın yer")]
    if scene:
        kinds.append(("RESIM", "metnin, aşağıda tarifi verilen resimde görünenle çeliştiği yer"))
    kinds += [("SIKICI", "sıkıldığın, aynı şeyin gereksiz yere tekrarlandığı yer"),
              ("MERAK", "merakının söndüğü, «e sonra ne oldu?» demediğin yer")]
    lines = "\n".join(f"- {k}: {v}" for k, v in kinds)
    body = "\n".join(_item_line(h, it) for h, it in handles.items())
    return (
        f"Sen {age} yaşında bir {who(age)}. Aşağıdaki kitap sayfasını okuyorsun{listen}. {age} yaşındaki bir "
        f"okur olarak nerede takıldığını işaretle:\n{lines}\n\n"
        "Yalnız gerçekten takıldığın yerleri işaretle; sorunsuz bir sayfada boş liste ver. Her işaret için:\n"
        "- item: takıldığın metin parçasının etiketi (M1 gibi)\n"
        "- quote: takıldığın yeri o parçadan HARFİ HARFİNE kopyala (kelime, deyim ya da cümle; değiştirme)\n"
        f"- reason: neden takıldığını {age} yaşındaki bir okurun ağzından tek kısa cümleyle\n"
        f"- replacement: quote'un yerine konacak, {age} yaşına uygun sade metin; olayı ve anlamı değiştirme, "
        "konuşanı belli etmek gerekiyorsa ekle. Metinle düzeltilemiyorsa (ör. resim yanlış) boş bırak.\n\n"
        f"Önceki sayfanın sonu (yalnız bağlam, işaretleme):\n<<<{before or '-'}>>>\n"
        + (f"Bu sayfadaki resmin tarifi:\n<<<{scene}>>>\n" if scene else "Bu sayfada resim yok.\n")
        + f"SAYFA:\n{body}"
    )


def child_schema(handles: list[str], scene: bool) -> dict:
    kinds = [k for k in KINDS if scene or k != "RESIM"]
    flag = {"type": "object", "additionalProperties": False, "required": ["item", "kind", "quote", "reason", "replacement"],
            "properties": {"item": {"type": "string", "enum": handles}, "kind": {"type": "string", "enum": kinds},
                           "quote": {"type": "string", "maxLength": 400}, "reason": {"type": "string", "maxLength": 300},
                           "replacement": {"type": "string", "maxLength": 600}}}
    return {"type": "object", "additionalProperties": False, "required": ["flags"],
            "properties": {"flags": {"type": "array", "items": flag}}}


def verify(out: dict, items: list[dict], pass_no: int) -> tuple[list[dict], int]:
    """Modelin işaretlerinden metinde birebir bulunanlar (özgün aralıkla) ve atılan sayısı."""
    handles = _handles(items)
    kept, dropped = [], 0
    for f in (out or {}).get("flags") or []:
        it = handles.get(f.get("item"))
        span = locate(f.get("quote", ""), it["text"]) if it else None
        if not it or span is None or f.get("kind") not in KINDS:
            dropped += 1
            continue
        quote = it["text"][span[0]:span[1]]
        rep = (f.get("replacement") or "").strip()
        if rep == quote.strip():
            rep = ""
        kept.append({"target": it["target"], "id": it["id"], "start": span[0], "end": span[1], "quote": quote,
                     "kind": f["kind"], "reason": (f.get("reason") or "").strip(), "replacement": rep, "pass": pass_no})
    return kept, dropped


def _fid(pid: str, f: dict) -> str:
    raw = f"{pid}|{f['target']}|{f['id']}|{f['start']}|{f['end']}|{f['kind']}"
    return "k_" + hashlib.sha1(raw.encode()).hexdigest()[:10]


def vote(passes: list[list[dict]], n: int) -> list[dict]:
    """Aynı parçada örtüşen işaretleri kümeler; okumaların çoğunluğunda (> n/2) geçen kümeyi tek işaret yapar."""
    clusters: list[list[dict]] = []
    for flags in passes:
        for f in flags:
            home = next((c for c in clusters if any(m["target"] == f["target"] and m["id"] == f["id"]
                                                    and f["start"] < m["end"] and m["start"] < f["end"] for m in c)), None)
            if home is None:
                clusters.append([f])
            else:
                home.append(f)
    need = n // 2 + 1
    out = []
    for c in clusters:
        votes = len({m["pass"] for m in c})
        if votes < need:
            continue
        kind = Counter(m["kind"] for m in c).most_common(1)[0][0]
        same = [m for m in c if m["kind"] == kind]
        qc = Counter((m["start"], m["end"]) for m in same)
        # en çok okumanın seçtiği aralık; eşitlikte önerisi olan (uygulanabilir), sonra en kısa
        best = max(same, key=lambda m: (qc[(m["start"], m["end"])], bool(m["replacement"]), -(m["end"] - m["start"])))
        rep = best["replacement"] or next((m["replacement"] for m in same if m["replacement"]
                                           and (m["start"], m["end"]) == (best["start"], best["end"])), "")
        out.append({k: best[k] for k in ("target", "id", "start", "end", "quote", "kind", "reason")} |
                   {"replacement": rep, "votes": votes, "passes": n,
                    "kinds": sorted({m["kind"] for m in c}),
                    # aynı aralık için öteki okumaların önerileri: ilk öneri sınamayı geçemezse sıradaki denenir
                    "alternatives": list(dict.fromkeys(m["replacement"] for m in same if m["replacement"]
                                                       and m["replacement"] != rep
                                                       and (m["start"], m["end"]) == (best["start"], best["end"])))})
    return sorted(out, key=lambda f: (f["target"] != "block", f["id"], f["start"]))


async def read_page(llm, d: Path, plan: dict, i: int, age: int, passes: int, sem: asyncio.Semaphore) -> dict:
    pg = plan["pages"][i]
    items = page_items(pg)
    no = plan_mod.FRONT + i + 1
    if not items:
        return {"no": no, "flags": [], "raw": 0, "dropped": 0, "ok_passes": 0, "failed_passes": 0}
    before = ""
    if i > 0:
        prev = page_items(plan["pages"][i - 1])
        before = " ".join(it["text"] for it in prev)[-400:]
    scene = scene_text(d, pg, plan)
    prompt = child_prompt(age, items, scene, before)
    schema = child_schema(list(_handles(items)), bool(scene))

    async def one(k: int):
        async with sem:
            try:
                out, _ = await llm.chat(ALIAS, [{"role": "user", "content": prompt}], schema=schema, prompt=READ,
                                        pages=[no], max_tokens=3000, temperature=TEMPERATURE, thinking=False,
                                        retries=1)
                return verify(out, items, k)
            except Exception as e:  # noqa: BLE001 - bir okuma düşerse ötekiler oylar; sayılır
                return e

    res = await asyncio.gather(*(one(k) for k in range(passes)))
    ok = [r for r in res if not isinstance(r, Exception)]
    failed = [r for r in res if isinstance(r, Exception)]
    if not ok:
        raise RuntimeError(f"{no}. sayfa okunamadı: {type(failed[0]).__name__}")
    flags = vote([r[0] for r in ok], len(ok))
    texts = {(it["target"], it["id"]): it["text"] for it in items}
    kept, refuted = [], 0
    for f in flags:
        if f["kind"] in REFUTABLE:
            p = await refute_flag(llm, age, f, texts[(f["target"], f["id"])], items, scene, no, sem)
            f["check"] = round(p, 3)
            if p < KEEP_P:
                refuted += 1
                continue
        if f["replacement"]:
            f["replacement"], rejected = await pick_replacement(llm, age, f, texts[(f["target"], f["id"])], no, sem)
            f["replacements_rejected"] = rejected
        f.pop("alternatives", None)
        f["fid"] = _fid(pg["id"], f)
        f["page"] = pg["id"]
        f["no"] = no
        kept.append(f)
    return {"no": no, "flags": kept, "raw": sum(len(r[0]) for r in ok), "dropped": sum(r[1] for r in ok),
            "refuted": refuted, "ok_passes": len(ok), "failed_passes": len(failed)}


REPLACE = PromptRef("studio_reader_replacement_check", "1")


async def pick_replacement(llm, age: int, f: dict, text: str, no: int, sem: asyncio.Semaphore) -> tuple[str, int]:
    """İşaretin önerisi metne konmadan sınanır: doğru Türkçe mi, anlamı ve olayı koruyor mu, bu yaşa daha uygun mu.
    Geçemeyen öneri atılır, aynı aralık için öteki okumaların önerisi denenir; hiçbiri geçmezse işaret önerisiz
    kalır (editör yine görür). Dönen: (öneri ya da "", atılan öneri sayısı)."""
    rejected = 0
    for rep in [f["replacement"], *f.get("alternatives", [])]:
        new = text[:f["start"]] + rep + text[f["end"]:]
        prompt = (f"Bir çocuk kitabı ({age} yaş okur). Özgün metin:\n<<<{text}>>>\nÖnerilen yeni metin:\n<<<{new}>>>\n"
                  f"Değişen yer: «{f['quote']}» → «{rep}»\n"
                  "Yeni metin doğru ve doğal Türkçe mi, olayı ve anlamı koruyor mu, bu yaştaki okur için özgününden daha "
                  "anlaşılır mı?\nA) Evet, üçü de\nB) Hayır\nTek harfle cevap ver.")
        try:
            async with sem:
                probs, _ = await llm.choose(ALIAS, [{"role": "user", "content": prompt}], ["A", "B"], prompt=REPLACE,
                                            pages=[no])
        except Exception:  # noqa: BLE001 - sınanamayan öneri gösterilmez; işaret kalır
            rejected += 1
            continue
        if float(probs.get("A", 0.0)) >= KEEP_P:
            return rep, rejected
        rejected += 1
    return "", rejected


REFUTABLE = ("RESIM", "KONUSAN")    # metinden denetlenebilen iddialar; kelime/cümle/sıkıcılık okurun öznel tepkisi


def refute_prompt(age: int, f: dict, text: str, items: list[dict], scene: str | None) -> str:
    page = "\n".join(_item_line(h, it) for h, it in _handles(items).items())
    if f["kind"] == "RESIM":
        return (f"Bir çocuk kitabı sayfası.\nResmin tarifi:\n<<<{scene or '-'}>>>\nSayfanın metni:\n<<<{page}>>>\n"
                f"İddia: metindeki «{f['quote']}» resimde görünenle çelişiyor. Gerekçe: {f['reason']}\n"
                "Yalnız metinde yazanı resim tarifinde yazanla karşılaştır. Resimde gösterilmeyen ama çelişmeyen ayrıntı, "
                "yer adı ya da okurun bilmediği bir kelime çelişki DEĞİLDİR.\n"
                "A) Evet, metinle resim açıkça çelişiyor\nB) Hayır, çelişki yok\nTek harfle cevap ver.")
    return (f"Bir çocuk kitabı sayfası ({age} yaş okur):\n<<<{page}>>>\n"
            f"İddia: «{f['quote']}» sözünü kimin söylediği anlaşılmıyor.\n"
            "Konuşma çizgisi, «dedi/diye sordu» eki, balonun konuşanı ya da önceki cümle konuşanı belli ediyorsa "
            "belirsizlik yoktur.\nA) Evet, kimin konuştuğu gerçekten belirsiz\nB) Hayır, konuşan belli\n"
            "Tek harfle cevap ver.")


async def refute_flag(llm, age: int, f: dict, text: str, items: list[dict], scene: str | None, no: int,
                      sem: asyncio.Semaphore) -> float:
    """İddianın doğru olma olasılığı (kapalı küme, tek çağrı). Model yanıt veremezse işaret kalır (1.0)."""
    try:
        async with sem:
            probs, _ = await llm.choose(ALIAS, [{"role": "user", "content": refute_prompt(age, f, text, items, scene)}],
                                        ["A", "B"], prompt=REFUTE, pages=[no])
        return float(probs.get("A", 0.0))
    except Exception:  # noqa: BLE001 - çürütülemeyen işaret editöre gider
        return 1.0


# ------------------------------------------------------------------ sayfa çevirme merakı
def spreads(plan: dict) -> list[dict]:
    """Çift sayfalar (sol çift, sağ tek numara) ve sayfa çevrilmeden önce okunan son cümle. Son çift sayfadan sonra
    çevrilecek sayfa yoktur, o yüzden alınmaz. Metni olmayan çift sayfa atlanır."""
    by_no = {plan_mod.FRONT + i + 1: pg for i, pg in enumerate(plan["pages"])}
    if not by_no:
        return []
    groups: dict[int, list[int]] = {}
    for no in sorted(by_no):
        groups.setdefault(no // 2, []).append(no)
    keys = sorted(groups)
    out = []
    for gi, s in enumerate(keys[:-1]):
        nos = groups[s]
        last = None
        for no in reversed(nos):                         # sağ sayfa önce: çevrilmeden hemen önce okunan
            items = page_items(by_no[no])
            blocks = [it for it in items if it["target"] == "block"] or [it for it in items if it["target"] == "bubble"]
            if blocks:
                last = (no, blocks[-1])
                break
        if not last:
            continue
        no, it = last
        span = last_sentence(it["text"])
        if not span:
            continue
        nxt = " ".join(x["text"] for n in groups[keys[gi + 1]] for x in page_items(by_no[n]))[:500]
        here = " ".join(x["text"] for n in nos for x in page_items(by_no[n]))[-900:]
        out.append({"spread": [n for n in nos], "no": no, "page": by_no[no]["id"], "target": it["target"],
                    "id": it["id"], "start": span[0], "end": span[1], "quote": it["text"][span[0]:span[1]],
                    "context": here, "next": nxt})
    return out


def judge_prompt(age: int, sp: dict) -> str:
    return (
        f"Resimli bir çocuk kitabı ({age} yaş). Okur sayfayı çevirmeden önce şu çift sayfayı okudu:\n<<<{sp['context']}>>>\n"
        f"Sayfa çevrilmeden önce okunan SON CÜMLE:\n<<<{sp['quote']}>>>\n\n"
        "Bu son cümle okuru «sonra ne oldu?» diye sayfayı çevirmeye ne kadar çekiyor?\n"
        "A) Güçlü: soru, yarım kalan eylem, ses, «ama…», bir şeyin olmak üzere olduğu duygusu var.\n"
        "B) Orta: olay sürüyor ama merak uyandırmıyor.\n"
        "C) Zayıf: olay kapanmış, çevirmek için bir neden yok.\nTek harfle cevap ver.")


def fix_prompt(age: int, sp: dict) -> str:
    tech = "\n".join(f"- {k}: {v}" for k, v in TECHNIQUES.items())
    return (
        f"Resimli bir çocuk kitabının ({age} yaş) editörüsün. Sayfa çevrilmeden önce okunan son cümleyi, okur "
        "«sonra ne oldu?» diye sayfayı çevirmek istesin diye yeniden yaz. Resimli kitap kalıplarından birini seç:\n"
        f"{tech}\n\nKurallar: olayı, karakterleri ve anlamı değiştirme; sonraki sayfada olanı önceden söyleme; "
        f"{age} yaşına uygun kısa ve sade yaz; cümlenin kitaptaki üslubunu koru.\n\n"
        f"Çift sayfanın metni (bağlam):\n<<<{sp['context']}>>>\nSON CÜMLE:\n<<<{sp['quote']}>>>\n"
        f"Sonraki sayfanın başı (yalnız bağlam, söyleme):\n<<<{sp['next'] or '-'}>>>\n"
        "replacement: son cümlenin yerine geçecek metin; technique: seçtiğin kalıp; reason: neden daha çok merak "
        "uyandırdığı, tek kısa cümle.")


FIX_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["technique", "replacement", "reason"],
              "properties": {"technique": {"type": "string", "enum": list(TECHNIQUES)},
                             "replacement": {"type": "string", "maxLength": 600},
                             "reason": {"type": "string", "maxLength": 300}}}


async def judge_spread(llm, age: int, sp: dict, sem: asyncio.Semaphore, attempts: int = 1) -> dict:
    """Gerilim ölçümü; güçlü değilse en çok `attempts` aday öneri yazılır, her biri çürütülür (hikâyeyi
    değiştiren/eksilten öneri düşer), ilk ayakta kalan gösterilir. Hiçbiri kalmazsa «öneri yok»."""
    async with sem:
        probs, _ = await llm.choose(ALIAS, [{"role": "user", "content": judge_prompt(age, sp)}], ["A", "B", "C"],
                                    prompt=TURN_JUDGE, pages=[sp["no"]])
    best = max(probs, key=probs.get)
    res = {k: sp[k] for k in ("spread", "no", "page", "target", "id", "start", "end", "quote")}
    res.update(probs={k: round(v, 3) for k, v in probs.items()}, strength={"A": "güçlü", "B": "orta", "C": "zayıf"}[best])
    res["fid"] = "t_" + hashlib.sha1(f"{sp['page']}|{sp['id']}|{sp['start']}|{sp['end']}".encode()).hexdigest()[:10]
    if best == "A":
        res["status"] = "strong"
        return res
    tried = []
    for k in range(max(1, attempts)):
        async with sem:
            out, _ = await llm.chat(ALIAS, [{"role": "user", "content": fix_prompt(age, sp)}], schema=FIX_SCHEMA,
                                    prompt=TURN_FIX, pages=[sp["no"]], max_tokens=900,
                                    temperature=0.3 if k == 0 else TEMPERATURE, thinking=False)
        rep = (out.get("replacement") or "").strip()
        if not rep or rep == sp["quote"].strip() or rep in (t["replacement"] for t in tried):
            continue
        async with sem:
            probs, _ = await llm.choose(ALIAS, [{"role": "user", "content": turn_refute_prompt(age, sp, rep)}],
                                        ["A", "B"], prompt=TURN_REFUTE, pages=[sp["no"]])
        keep = float(probs.get("A", 0.0))
        tried.append({"replacement": rep, "technique": out.get("technique"), "keep": round(keep, 3)})
        if keep >= KEEP_P:
            res.update(status="suggested", technique=out.get("technique"), replacement=rep, check=round(keep, 3),
                       reason=(out.get("reason") or "").strip(), tried=len(tried))
            return res
    res.update(status="no_fix", tried=len(tried), rejected=tried)
    return res


def turn_refute_prompt(age: int, sp: dict, rep: str) -> str:
    return (f"Resimli bir çocuk kitabı ({age} yaş). Çift sayfanın metni:\n<<<{sp['context']}>>>\n"
            f"Sonraki sayfanın başı:\n<<<{sp['next'] or '-'}>>>\n"
            f"Özgün son cümle: «{sp['quote']}»\nÖnerilen yeni son cümle: «{rep}»\n\n"
            "Yeni cümle hikâyede olmayan bir olay, duygu, eşya ya da bilgi ekliyor mu, özgün cümlenin söylediğini "
            "(konuşma dahil) atıyor mu, ya da sonraki sayfada gerçekleşmeyen bir şey vaat ediyor mu?\n"
            "A) Hayır: aynı olayı merak uyandıracak biçimde söylüyor\nB) Evet: hikâyeyi değiştiriyor ya da eksiltiyor\n"
            "Tek harfle cevap ver.")


# ------------------------------------------------------------------ koşular
def _dir(d: Path) -> Path:
    p = d / DIR
    p.mkdir(exist_ok=True)
    return p


def load_run(d: Path, rid: str) -> dict | None:
    if not re.fullmatch(r"r_[0-9a-f]{8}", rid or ""):
        return None
    run = studio.read(d / DIR, f"{rid}.json")
    if run is None:
        return None
    if run["status"] == "running" and rid not in _tasks and _now() - run.get("updated", 0) > STALE_SECONDS:
        run["status"] = "interrupted"
    run["decisions"] = studio.read(d / DIR, f"{rid}.decisions.json", {})
    return run


def runs(d: Path) -> list[dict]:
    out = []
    for p in sorted((d / DIR).glob("r_*.json")) if (d / DIR).exists() else []:
        if p.name.endswith(".decisions.json"):
            continue
        r = load_run(d, p.stem)
        if r:
            out.append(summary(r))
    return sorted(out, key=lambda r: -r["created"])


def summary(run: dict) -> dict:
    keys = ("id", "kind", "status", "created", "updated", "by", "plan_rev", "age", "band", "passes", "progress", "error")
    s = {k: run.get(k) for k in keys}
    s["flags"] = sum(len(p.get("flags") or []) for p in (run.get("pages") or {}).values()) if run["kind"] == "child" \
        else sum(1 for x in run.get("spreads") or [] if x.get("status") == "suggested")
    return s


def latest(d: Path, kind: str) -> dict | None:
    return next((r for r in runs(d) if r["kind"] == kind), None)


def flat(run: dict) -> dict:
    """Ekrana giden görünüm: işaretler düz liste, sayfa sırasıyla; editör kararı her işaretin yanında."""
    dec = run.get("decisions") or {}
    out = {k: v for k, v in run.items() if k not in ("pages", "spreads", "decisions", "plan", "targets")}
    if run["kind"] == "child":
        flags = [f for p in sorted((run.get("pages") or {}).values(), key=lambda p: p["no"]) for f in p.get("flags") or []]
        out["flags"] = [{**f, "label": KINDS.get(f["kind"], f["kind"]), "decision": (dec.get(f["fid"]) or {}).get("decision")}
                        for f in flags]
        pages = (run.get("pages") or {}).values()
        out["stats"] = {"raw": sum(p.get("raw", 0) for p in pages), "dropped": sum(p.get("dropped", 0) for p in pages),
                        "shown": len(out["flags"]), "failed_pages": sum(1 for p in pages if p.get("error")),
                        "failed_passes": sum(p.get("failed_passes", 0) for p in pages),
                        "refuted": sum(p.get("refuted", 0) for p in pages)}
    else:
        out["spreads"] = [{**x, "technique_label": TECHNIQUES.get(x.get("technique") or "", None),
                           "decision": (dec.get(x["fid"]) or {}).get("decision")} for x in run.get("spreads") or []]
    return out


def decide(d: Path, rid: str, fid: str, decision: str, by: str) -> dict:
    if decision not in DECISIONS:
        raise ValueError("karar geçersiz")
    run = load_run(d, rid)
    if run is None:
        raise KeyError("okuma yok")
    known = {f["fid"] for p in (run.get("pages") or {}).values() for f in p.get("flags") or []} | \
        {x["fid"] for x in run.get("spreads") or []}
    if fid not in known:
        raise KeyError("işaret yok")
    dec = studio.read(d / DIR, f"{rid}.decisions.json", {})
    if decision == "open":
        dec.pop(fid, None)
    else:
        dec[fid] = {"decision": decision, "by": by, "at": _now()}
    studio.write(d / DIR, f"{rid}.decisions.json", dec)
    with (d / "provenance.jsonl").open("a") as f:
        f.write(json.dumps({"kind": "reader_decision", "run": rid, "flag": fid, "decision": decision, "by": by,
                            "at": _now()}, ensure_ascii=False) + "\n")
    return dec


def running(d: Path, kind: str) -> dict | None:
    r = latest(d, kind)
    return r if r and r["status"] == "running" else None


def new_run(d: Path, kind: str, by: str, passes: int | None = None) -> dict:
    plan = plan_mod.load(d)
    if plan is None:
        raise plan_mod.NoPlan(d.name)
    age = reader_age(d)
    if age["age"] is None:
        raise ValueError("Kitabın okur yaşı bilinmiyor (profil yok)")
    if kind == "turn" and not picture_book(d, plan):
        raise ValueError("Sayfa çevirme merakı yalnız resimli kitapta ölçülür")
    rid = f"r_{secrets.token_hex(4)}"
    run = {"id": rid, "kind": kind, "status": "running", "created": _now(), "updated": _now(), "by": by,
           "plan_rev": plan["rev"], "plan": plan, "age": age["age"], "band": age["band"],
           "passes": int(passes or 1), "progress": [0, 0], "error": None}
    if kind == "child":
        run["pages"] = {}
        run["progress"] = [0, len(plan["pages"])]
    else:
        run["spreads"] = []
        run["targets"] = spreads(plan)
        run["progress"] = [0, len(run["targets"])]
    studio.write(_dir(d), f"{rid}.json", run)
    return run


async def execute(d: Path, rid: str, llm) -> dict:
    """Koşuyu yürütür (eksik sayfalar/çift sayfalar). Her parça bitince kayıt yazılır; hata koşuyu bitirmez,
    o parçaya yazılır. Dönen: son kayıt."""
    run = studio.read(d / DIR, f"{rid}.json")
    run.update(status="running", updated=_now(), error=None)
    plan = run["plan"]
    sem = asyncio.Semaphore(PARALLEL)
    lock = asyncio.Lock()

    async def save():
        run["updated"] = _now()
        await asyncio.to_thread(studio.write, d / DIR, f"{rid}.json", run)

    if run["kind"] == "child":
        async def one(i: int):
            pg = plan["pages"][i]
            if (run["pages"].get(pg["id"]) or {}).get("done"):
                return
            try:
                res = await read_page(llm, d, plan, i, run["age"], run["passes"], sem)
                res["done"] = True
            except Exception as e:  # noqa: BLE001 - sayfa hatası kayda geçer, koşu sürer; sürdürmede yeniden okunur
                res = {"no": plan_mod.FRONT + i + 1, "flags": [], "error": f"{type(e).__name__}: {str(e)[:200]}"}
            async with lock:
                run["pages"][pg["id"]] = res
                run["progress"] = [sum(1 for p in run["pages"].values() if p.get("done")), len(plan["pages"])]
                await save()
        await asyncio.gather(*(one(i) for i in range(len(plan["pages"]))))
        failed = [p["no"] for p in run["pages"].values() if p.get("error")]
    else:
        done = {x["fid"]: x for x in run["spreads"]}

        async def one_t(sp: dict):
            key = "t_" + hashlib.sha1(f"{sp['page']}|{sp['id']}|{sp['start']}|{sp['end']}".encode()).hexdigest()[:10]
            if key in done and done[key].get("status") != "failed":
                return
            try:
                res = await judge_spread(llm, run["age"], sp, sem, run.get("passes") or 1)
            except Exception as e:  # noqa: BLE001
                res = {k: sp[k] for k in ("spread", "no", "page", "target", "id", "start", "end", "quote")}
                res.update(fid=key, status="failed", error=f"{type(e).__name__}: {str(e)[:200]}")
            async with lock:
                run["spreads"] = [x for x in run["spreads"] if x["fid"] != key] + [res]
                run["spreads"].sort(key=lambda x: x["no"])
                run["progress"] = [sum(1 for x in run["spreads"] if x.get("status") != "failed"), len(run["targets"])]
                await save()
        await asyncio.gather(*(one_t(sp) for sp in run["targets"]))
        failed = [x["no"] for x in run["spreads"] if x.get("status") == "failed"]
    run["status"] = "done" if not failed else "partial"
    run["error"] = (f"{len(failed)} sayfa okunamadı: " + ", ".join(map(str, sorted(failed)))) if failed else None
    run["finished"] = _now()
    await save()
    return run


def start(d: Path, rid: str, llm) -> None:
    """Koşuyu bu süreçte arka planda başlatır (API olay döngüsünde)."""
    async def go():
        try:
            await execute(d, rid, llm)
        except Exception as e:  # noqa: BLE001 - kayıt hatayı taşır; ekran «sürdür» der
            run = studio.read(d / DIR, f"{rid}.json") or {}
            run.update(status="failed", error=f"{type(e).__name__}: {str(e)[:300]}", updated=_now())
            studio.write(d / DIR, f"{rid}.json", run)
        finally:
            _tasks.pop(rid, None)
    _tasks[rid] = asyncio.get_running_loop().create_task(go())


def is_running(rid: str) -> bool:
    return rid in _tasks


def need(n: int) -> int:
    """Gösterilmek için gereken oy (bilgi amaçlı; `vote` ile aynı kural)."""
    return n // 2 + 1 if n > 0 else 0


__all__ = ["KINDS", "TECHNIQUES", "reader_age", "picture_book", "page_items", "locate", "last_sentence", "vote",
           "spreads", "new_run", "execute", "start", "load_run", "runs", "latest", "flat", "decide", "need"]
