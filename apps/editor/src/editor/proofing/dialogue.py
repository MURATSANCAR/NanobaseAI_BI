"""Diyalog atfı ve ses: (A) replik sahnede olmayan birine verilmiş mi; (B) bir karakterin
başka birine hitabı açıklamasız değişiyor mu (hep «abla» diyen, birden adıyla).

Okuma: director parça başına bir çağrı — replikler (speaker, addressee, address_term, sayfa,
paragraf, alıntı). Alıntı sayfada bulunmazsa kayıt yok; konuşan/hitap edilen karakter listesine
eşlenmezse (resolve_subject) tahmin yok, satır atlanır.

A. ATIF (deterministik aday): s.p'deki repliğin konuşanı, s.p ± DIALOGUE_PRESENCE_WINDOW
   sayfalarının katılımcı kümesinde yoksa aday. Katılımcı kümesi = o sayfayı kapsayan
   kullanılabilir olayların event_actor satırları (ACTOR/INVOLVED; yoksa çıkarımın `participants`
   adları) ∪ o sayfada metinde anılan çözülmüş karakterler. Küme boşsa (veri yok) aday yok.
   Yargı: iki kapalı soru (Llm.choose) — «X bu sahnede var mı?» (V/Y/B) ve «bu replik X'e ait
   olabilir mi?» (E/H/B); bulgu ancak min(P(Y), P(H)) ≥ DIALOGUE_JUDGE_MIN.
B. HİTAP (ölçülebilir tanım): hitap terimi kapalı SINIFA çevrilir — AD (hitap edilenin adı/takma
   adı), AKRABALIK (abla, abi, anne, baba, dede, nine, teyze, amca, hala, dayı, kardeş, oğlum, kızım…),
   SAYGI (efendim, hocam, öğretmenim, bey, hanım, amca/teyze yabancıya), LAKAP (diğer). Bir
   konuşan→hitap edilen çifti için en az DIALOGUE_MIN_USES hitap varsa ve bir sınıf payı ≥
   DIALOGUE_DOMINANT_SHARE ise baskın sınıftır; başka sınıftan her hitap aday (aynı sınıf içi
   değişim — abla/ablacığım — aday değil). Yargı iki sırada kapalı soru; metin değişimi açıklıyorsa
   (kızgınlık, resmiyet, şaka, kimliğin öğrenilmesi, büyüme) çelişki değil.
Her bulgu iki kanıt taşır (sayfa+alıntı; A'da ikinci kanıt o sayfanın katılımcı listesi ve olay
özeti). Şiddet: A ve olasılık ≥ DIALOGUE_ERROR_MIN → ERROR, diğerleri WARN.

Model çağrısı: parça başına 1 + aday başına 2.
ÖLÇÜM BEKLİYOR: okuyucu kesinliği ve eşikler gerçek kitapta ölçülmedi (docs/son-okuma/dialogue.md)."""

from __future__ import annotations

import asyncio
from collections import Counter

from .. import schemas, source
from ..llm import Llm
from . import _attributes as A
from . import _continuity as C

NAME = "dialogue"
VERSION = "1"
LABEL = "Diyalog atfı ve ses"

JUDGE_MIN = C.setting("dialogue_judge_min", 0.5)          # EDITOR_DIALOGUE_JUDGE_MIN
ERROR_MIN = C.setting("dialogue_error_min", 0.8)          # EDITOR_DIALOGUE_ERROR_MIN
PARALLEL = C.setting("dialogue_parallel", 4)              # EDITOR_DIALOGUE_PARALLEL
PRESENCE_WINDOW = C.setting("dialogue_presence_window", 1)  # EDITOR_DIALOGUE_PRESENCE_WINDOW (sayfa)
MIN_USES = C.setting("dialogue_min_uses", 3)              # EDITOR_DIALOGUE_MIN_USES
DOMINANT_SHARE = C.setting("dialogue_dominant_share", 0.6)  # EDITOR_DIALOGUE_DOMINANT_SHARE

# Genel Türkçe hitap sözlüğü (kitaba özel değil). Kök eşleşir: "ablacığım" → abla.
KINSHIP = ["abla", "abi", "ağabey", "anne", "anneanne", "babaanne", "baba", "dede", "nine", "teyze", "amca",
           "hala", "dayı", "kardeş", "oğul", "kız", "yenge", "enişte", "torun", "yavru", "evlat", "anneciğ", "babacığ"]
HONORIFIC = ["efendi", "hoca", "öğretmen", "bey", "hanım", "usta", "doktor", "müdür", "sayın", "komutan", "kaptan"]
CATEGORIES = ["AD", "AKRABALIK", "SAYGI", "LAKAP"]
CATEGORY_TR = {"AD": "adıyla", "AKRABALIK": "akrabalık sözüyle", "SAYGI": "saygı sözüyle", "LAKAP": "takma adla"}

LINE_SCHEMA = schemas.obj({"lines": schemas.arr(schemas.obj({
    "speaker": schemas.STR, "addressee": schemas.STR, "address_term": schemas.STR,
    "page": schemas.INT, "paragraph": schemas.INT, "quote": schemas.STR}), 0, 120)})

READ = ("Aşağıdaki sayfalardaki REPLİKLERİ (tırnak içi ya da konuşma çizgili sözler) çıkar. Karakterler:\n"
        "{characters}\n\n"
        "`speaker` repliği söyleyen (metnin söylediği ya da bağlamdan kesin olan; belli değilse boş bırak); "
        "`addressee` kime söylendiği (belli değilse boş); `address_term` repliğin içinde hitap edilene "
        "seslenilen söz varsa o söz, olduğu gibi (abla, anneciğim, Ayşe, hocam; yoksa boş); `quote` repliğin "
        "metindeki hâli, kelimesi kelimesine. Anlatıcı cümlelerini alma; tahmin yapma.\n\n")

JUDGE_PRESENT = (
    "Soru: s.{page} sayfasındaki şu replik metinde {name} adlı karaktere ait: “{quote}”.\n"
    "Kitabın tamamına bakınca {name} bu sahnede (s.{page} ve çevresinde) bulunuyor mu?\n"
    "Sahnede olanlar (olay kayıtlarından): {present}.\n"
    "Uzaktan konuşma (telefon, mektup, ses), hatırlanan/aktarılan söz, rüya, hayal ya da sonradan sahneye "
    "girme metinde geçiyorsa karakter «var» sayılır.\n\n"
    "Cevap tek harf: V = var (ya da uzaktan/aktarılan konuşma); Y = yok, bu karakter bu sahnede olamaz; "
    "B = karar verilemiyor.")
JUDGE_OWNER = (
    "Soru: s.{page} sayfasındaki şu replik: “{quote}”. Metin bunu {name} adlı karaktere veriyor.\n"
    "Sahnede olanlar (olay kayıtlarından): {present}.\n"
    "Kitabın tamamına bakınca bu replik gerçekten {name} tarafından söylenmiş olabilir mi (sahnede, uzaktan "
    "ya da aktarılan söz olarak)?\n\n"
    "Cevap tek harf: E = evet, söylemiş olabilir; H = hayır, replik yanlış kişiye verilmiş görünüyor; "
    "B = karar verilemiyor.")
JUDGE_ADDRESS = (
    "Soru: {speaker}, {addressee} adlı karaktere hikâye boyunca hep {cat1} sesleniyor "
    "(örnek s.{p1}: “{q1}” → «{t1}»); s.{p2}'de ise {cat2}: “{q2}” → «{t2}».\n"
    "Kitabın tamamına bak: bu değişimi metin açıklıyor mu (kızgınlık, şaka, resmiyet, kimliğin öğrenilmesi, "
    "büyüme, başka birine seslenme, aktarılan söz)? Açıklıyorsa ya da hitap edilen aslında başka biriyse "
    "çelişki yoktur.\n\n"
    "Cevap tek harf: C = açıklamasız ses/hitap tutarsızlığı; U = tutarlı ya da metin açıklıyor; B = karar verilemiyor.")


# --------------------------------------------------------------- saf parça
def presence(evs: list[dict], mentions: list[dict], name_idx: dict[str, str]) -> dict[int, set]:
    """Sayfa -> orada bulunan karakter kimlikleri (olay katılımcıları + metinde anılanlar)."""
    out: dict[int, set] = {}
    for e in evs:
        ids = set(e.get("character_ids") or [])
        if not ids:
            ids = {cid for cid in (A.resolve_subject(n, name_idx) for n in e.get("participants", [])) if cid}
        for p in range(e["page_from"], e["page_to"] + 1):
            out.setdefault(p, set()).update(ids)
    for m in mentions:
        out.setdefault(m["page_no"], set()).add(str(m["character_id"]))
    return out


def present_near(pres: dict[int, set], page: int, window: int = PRESENCE_WINDOW) -> set:
    s: set = set()
    for p in range(page - window, page + window + 1):
        s |= pres.get(p, set())
    return s


def attribution_candidates(lines: list[dict], pres: dict[int, set]) -> list[dict]:
    """Konuşanı çözülmüş her replik: konuşan sayfa ± pencere katılımcılarında yoksa aday."""
    out = []
    for ln in lines:
        if not ln.get("speaker_id"):
            continue
        near = present_near(pres, ln["page"])
        if not near or ln["speaker_id"] in near:
            continue
        out.append({"rule": "A", "line": ln, "present": sorted(near)})
    return out


def term_category(term: str, addressee_names: list[str]) -> str | None:
    t = C.norm(term)
    if not t:
        return None
    for n in addressee_names:
        k = C.norm(n)
        if k and (t == k or t.startswith(k) or k.startswith(t.split()[0])):
            return "AD"
    for root in KINSHIP:
        if t.startswith(root):
            return "AKRABALIK"
    for root in HONORIFIC:
        if t.startswith(root) or t.endswith(" " + root) or any(w.startswith(root) for w in t.split()):
            return "SAYGI"
    return "LAKAP"


def address_candidates(lines: list[dict], names_of: dict[str, list[str]]) -> list[dict]:
    """Konuşan→hitap edilen çifti: baskın sınıf varsa başka sınıftan hitaplar aday."""
    pairs: dict[tuple, list[dict]] = {}
    for ln in lines:
        if ln.get("speaker_id") and ln.get("addressee_id") and ln.get("address_term"):
            cat = term_category(ln["address_term"], names_of.get(ln["addressee_id"], []))
            if cat:
                pairs.setdefault((ln["speaker_id"], ln["addressee_id"]), []).append({**ln, "category": cat})
    out = []
    for key, uses in pairs.items():
        if len(uses) < MIN_USES:
            continue
        cnt = Counter(u["category"] for u in uses)
        dom, n = cnt.most_common(1)[0]
        if n / len(uses) < DOMINANT_SHARE:
            continue
        example = next(u for u in sorted(uses, key=lambda u: (u["page"], u["idx"] or 0)) if u["category"] == dom)
        for u in sorted(uses, key=lambda u: (u["page"], u["idx"] or 0)):
            if u["category"] != dom and u["page"] != example["page"]:
                out.append({"rule": "B", "dominant": dom, "a": example, "b": u, "uses": len(uses), "share": n / len(uses)})
    out.sort(key=lambda c: (c["a"]["speaker"], c["b"]["page"]))
    return out


# ------------------------------------------------------------------ okuma
async def read_lines(llm: Llm, pages: list[dict], chars: list[dict]) -> tuple[list[dict], dict]:
    idx = A.name_index(chars)
    by_no = C.by_no(pages)
    names = {str(ch["id"]): ch["canonical_name"] for ch in chars}
    char_lines = "\n".join(f"- {ch['canonical_name']}" + (f" (diğer: {', '.join(ch['aliases'])})" if ch.get("aliases") else "")
                           for ch in chars)
    ps = A.parts(A.paragraphs(pages))
    ask = READ.format(characters=char_lines)

    async def one(part):
        out, _ = await llm.chat(C.DIRECTOR, [{"role": "user", "content": ask + C.INTRO + A.part_text(part)}],
                                schema=LINE_SCHEMA, pages=sorted({x["page"] for x in part}),
                                max_tokens=8000, temperature=0.0, thinking=False)
        return out["lines"]
    got = await asyncio.gather(*(one(p) for p in ps), return_exceptions=True)
    failed = [g for g in got if isinstance(g, BaseException)]
    if ps and len(failed) == len(got):
        raise RuntimeError(f"replik okuyucu hiçbir parçada cevap vermedi: {failed[0]}")
    lines, unverified, unknown = [], 0, 0
    for g in got:
        if isinstance(g, BaseException):
            continue
        for ln in g:
            loc = A.locate(by_no, int(ln["page"]), int(ln["paragraph"]) or None, ln["quote"])
            if not loc:
                unverified += 1
                continue
            sid = A.resolve_subject(ln.get("speaker", ""), idx)
            aid = A.resolve_subject(ln.get("addressee", ""), idx)
            if ln.get("speaker") and not sid:
                unknown += 1
            lines.append({"speaker": ln.get("speaker", ""), "speaker_id": sid, "speaker_name": names.get(sid or "", ""),
                          "addressee": ln.get("addressee", ""), "addressee_id": aid,
                          "addressee_name": names.get(aid or "", ""), "address_term": ln.get("address_term", ""),
                          "page": loc["page"], "idx": loc["idx"], "quote": loc["quote"]})
    return lines, {"parts": len(ps), "parts_failed": len(failed), "lines": len(lines),
                   "unverified_quote": unverified, "unknown_speaker": unknown}


# ------------------------------------------------------------------ bulgu
def _ev(ln: dict) -> dict:
    return {"page": ln["page"], "paragraph": ln.get("idx"), "quote": ln["quote"], "speaker": ln.get("speaker_name"),
            "addressee": ln.get("addressee_name"), "address_term": ln.get("address_term")}


def finding_attribution(c: dict, v: dict, names: dict[str, str], evs_on_page: list[dict]) -> dict:
    ln = c["line"]
    p = v["p"]
    who = ", ".join(names.get(i, i) for i in c["present"]) or "-"
    return {"page": ln["page"], "severity": "ERROR" if p >= ERROR_MIN else "WARN", "quote": ln["quote"],
            "message": (f"Diyalog atfı — s.{ln['page']} “{ln['quote']}” repliği «{ln['speaker_name']}» adına yazılmış; "
                        f"olay kayıtlarına göre bu sahnede olanlar: {who}. Hikâye {ln['speaker_name']}'in "
                        "orada olduğunu açıklamıyor."),
            "suggestion": "Repliğin sahibini ve sahnede kimin olduğunu kontrol edin; adı ya da olay anlatımını düzeltin.",
            "details": {"rule": "A", "a": _ev(ln), "b": {"page": ln["page"], "present": [names.get(i, i) for i in c["present"]],
                                                          "events": evs_on_page},
                        "judge": {k: v[k] for k in ("forward", "reverse")}, "p_contradiction": round(p, 3)}}


def finding_address(c: dict, v: dict) -> dict:
    a, b = c["a"], c["b"]
    return {"page": b["page"], "severity": "WARN", "quote": b["quote"],
            "message": (f"Ses/hitap — «{a['speaker_name']}», «{a['addressee_name']}» adlı karaktere {c['uses']} "
                        f"replikte çoğunlukla {CATEGORY_TR[c['dominant']]} sesleniyor (s.{a['page']} «{a['address_term']}»); "
                        f"s.{b['page']}'de {CATEGORY_TR[b['category']]}: «{b['address_term']}». Hikâye bu değişimi açıklamıyor."),
            "suggestion": "Hitabı öteki repliklerle aynı yapın ya da değişimin nedenini metinde gösterin.",
            "details": {"rule": "B", "dominant": c["dominant"], "deviant": b["category"], "uses": c["uses"],
                        "share": round(c["share"], 3), "a": _ev(a), "b": _ev(b),
                        "judge": {k: v[k] for k in ("forward", "reverse")}, "p_contradiction": round(v["p"], 3)}}


async def check(lines: list[dict], pages: list[dict], llm, evs: list[dict], mentions: list[dict],
                chars: list[dict]) -> tuple[list[dict], dict]:
    story = C.story_pages(pages)
    idx = A.name_index(chars)
    names = {str(ch["id"]): ch["canonical_name"] for ch in chars}
    names_of = {str(ch["id"]): [ch["canonical_name"], *(ch.get("aliases") or [])] for ch in chars}
    pres = presence(evs, mentions, idx)
    ca = attribution_candidates(lines, pres)
    cb = address_candidates(lines, names_of)
    stats = {"lines": len(lines), "lines_resolved": sum(bool(l.get("speaker_id")) for l in lines),
             "pages_with_presence": len(pres), "candidates_attribution": len(ca), "candidates_address": len(cb),
             "judge_failed": 0, "confirmed_attribution": 0, "confirmed_address": 0, "candidates_detail": []}
    findings = []
    if not (ca or cb):
        return findings, stats
    text = C.book_text(story)
    sem = asyncio.Semaphore(PARALLEL)
    jobs = []
    for c in ca:
        ln = c["line"]
        present = ", ".join(names.get(i, i) for i in c["present"]) or "-"
        f1 = C.INTRO + text + "\n\n" + JUDGE_PRESENT.format(page=ln["page"], name=ln["speaker_name"], quote=ln["quote"], present=present)
        f2 = C.INTRO + text + "\n\n" + JUDGE_OWNER.format(page=ln["page"], name=ln["speaker_name"], quote=ln["quote"], present=present)
        jobs.append(_judge_two(llm, f1, f2, sem, [ln["page"]]))
    for c in cb:
        a, b = c["a"], c["b"]

        def body(x, y, c=c):
            return C.INTRO + text + "\n\n" + JUDGE_ADDRESS.format(
                speaker=x["speaker_name"], addressee=x["addressee_name"], cat1=CATEGORY_TR[x["category"]],
                p1=x["page"], q1=x["quote"], t1=x["address_term"], cat2=CATEGORY_TR[y["category"]],
                p2=y["page"], q2=y["quote"], t2=y["address_term"])
        jobs.append(C.judge_both(llm, body(a, b), body(b, a), sem, sorted({a["page"], b["page"]})))
    verdicts = await asyncio.gather(*jobs, return_exceptions=True)
    for c, v in zip(ca + cb, verdicts):
        d = {"rule": c["rule"], "a": _ev(c["line"] if c["rule"] == "A" else c["a"]),
             "b": (c["present"] if c["rule"] == "A" else _ev(c["b"]))}
        if isinstance(v, BaseException):
            stats["judge_failed"] += 1
            stats["candidates_detail"].append({**d, "p": None})
            continue
        stats["candidates_detail"].append({**d, "p": round(v["p"], 3)})
        if v["p"] < JUDGE_MIN:
            continue
        if c["rule"] == "A":
            pg = c["line"]["page"]
            on_page = [{"summary": e["summary"], "pages": [e["page_from"], e["page_to"]]} for e in evs
                       if e["page_from"] <= pg <= e["page_to"]][:6]
            findings.append(finding_attribution(c, v, names, on_page))
            stats["confirmed_attribution"] += 1
        else:
            findings.append(finding_address(c, v))
            stats["confirmed_address"] += 1
    return findings, stats


async def _judge_two(llm, body_present: str, body_owner: str, sem, pages) -> dict:
    """Atıf için iki farklı kapalı soru; 'çelişki' = Y (yok) ve H (hayır) olasılıklarının küçüğü."""
    async def ask(body, choices):
        async with sem:
            probs, _ = await llm.choose(C.DIRECTOR, [{"role": "user", "content": body}], choices, pages=pages)
        return probs
    p1, p2 = await asyncio.gather(ask(body_present, ["V", "Y", "B"]), ask(body_owner, ["E", "H", "B"]))
    return {"forward": p1, "reverse": p2, "p": min(p1["Y"], p2["H"])}


async def run(generation_id: str):
    llm = Llm(generation_id)
    pages = await asyncio.to_thread(source.read, generation_id)
    chars = await asyncio.to_thread(A.characters, generation_id)
    evs = await asyncio.to_thread(C.events, generation_id)
    mentions = await asyncio.to_thread(C.text_mentions, generation_id)
    lines, rstats = await read_lines(llm, C.story_pages(pages), chars)
    findings, stats = await check(lines, pages, llm, evs, mentions, chars)
    stats["reader"] = rstats
    findings.append({"page": None, "severity": "INFO",
                     "message": (f"Diyalog: {stats['lines']} replik okundu ({stats['lines_resolved']} konuşanı çözülmüş), "
                                 f"{stats['pages_with_presence']} sayfada katılımcı bilgisi; atıf adayı "
                                 f"{stats['candidates_attribution']} ({stats['confirmed_attribution']} bulgu), hitap adayı "
                                 f"{stats['candidates_address']} ({stats['confirmed_address']} bulgu). "
                                 "Eşikler henüz gerçek kitapta ölçülmedi.")})
    return findings, stats
