"""Zaman çizelgesi: metnin zaman ifadeleri sayfa sırasında okunduğunda çelişiyor mu — gün vakti
geri gidiyor («akşam» sonra aynı akış içinde «öğlen»), mevsim bir geri gidiyor, bir karakterin
yaşı küçülüyor, doğum yılı/yaş/tarih tutmuyor.

Çıkarma DETERMİNİSTİK (model yok): kapalı Türkçe kalıplar sayfa sırasıyla okunur —
  GUN_VAKTI  sabah/öğle/akşam/gece (genel «her sabah» ve selamlar dışarıda);
  GUN_GECISI ertesi gün/sabah, sonraki gün, N gün/hafta/ay/yıl sonra, günler sonra (N bilinmiyor: 2);
  MEVSIM     ilkbahar/yaz/sonbahar/kış;
  YAS        «<ad> N yaşında», «N yaşına girdi/bastı»; TARIH: «YYYY yılında», «YYYY'de doğdu».
Alıntı kanıtı sayfanın kendi kelimeleridir (kalıbın geçtiği cümle).

Sıra denetimi (deterministik, `check_order`): durum makinesi (gün sayacı, gün vakti, mevsim,
karakter başına yaş). Aday:
  - GUN_VAKTI geri: önceki vakitten daha erken bir vakit; SABAH'a dönüş örtük yeni gündür (aday
    değil, gün sayacı +1); öğle→sabah dışındaki her geri adım (akşam→öğle, gece→akşam…) aday.
  - MEVSIM geri: döngüsel uzaklık 3 (bir mevsim geri; kış→ilkbahar ileridir).
  - YAS geri: aynı özne için küçülen yaş. YAS/TARIH: doğum yılı + (yıl, yaş) çifti tutmuyor
    (yıl − doğum ∉ {yaş, yaş+1}).
  Yalnız gerçek olmayan kipte (MEMORY/DREAM/IMAGINATION/HYPOTHETICAL) olay taşıyan sayfaların
  ifadeleri sıraya girmez (_continuity.unreal_pages); karışık sayfa girer, yargı ayırır.

Yargı: kitabın tamamı + iki ifade, iki sırada kapalı soru (Llm.choose, logprobs); metinde geri
dönüş/anı/rüya/özet açıklaması varsa çelişki değil. Bulgu ancak min(C_ileri, C_geri) ≥
TIMELINE_JUDGE_MIN. Her bulgu iki kanıt (iki sayfa + alıntı). Şiddet: YAS/TARIH ve olasılık ≥
TIMELINE_ERROR_MIN → ERROR, diğerleri WARN.

Model çağrısı: aday başına 2; çıkarma 0.
ÖLÇÜM BEKLİYOR: kalıp geri çağırması ve eşikler gerçek kitapta ölçülmedi (docs/son-okuma/timeline.md)."""

from __future__ import annotations

import asyncio
import re

from .. import source
from ..llm import Llm
from . import _attributes as A
from . import _continuity as C

NAME = "timeline"
VERSION = "1"
LABEL = "Zaman çizelgesi"

JUDGE_MIN = C.setting("timeline_judge_min", 0.5)   # EDITOR_TIMELINE_JUDGE_MIN
ERROR_MIN = C.setting("timeline_error_min", 0.8)   # EDITOR_TIMELINE_ERROR_MIN
PARALLEL = C.setting("timeline_parallel", 4)       # EDITOR_TIMELINE_PARALLEL
UNKNOWN_DAYS = C.setting("timeline_unknown_days", 2)   # «günler sonra» kaç gün sayılır

TOD = ["SABAH", "OGLE", "AKSAM", "GECE"]
SEASONS = ["ILKBAHAR", "YAZ", "SONBAHAR", "KIS"]
TOD_TR = {"SABAH": "sabah", "OGLE": "öğle", "AKSAM": "akşam", "GECE": "gece"}
SEASON_TR = {"ILKBAHAR": "ilkbahar", "YAZ": "yaz", "SONBAHAR": "sonbahar", "KIS": "kış"}

_WORDS = {"bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9,
          "on": 10, "on bir": 11, "on iki": 12, "on üç": 13, "on dört": 14, "on beş": 15, "yirmi": 20,
          "otuz": 30, "kırk": 40, "elli": 50, "yüz": 100}
_NUM = r"(?:on\s+(?:bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz)|" + "|".join(sorted(_WORDS, key=len, reverse=True)) + r"|\d+)"
_UNIT = {"gün": 1, "hafta": 7, "ay": 30, "yıl": 365, "sene": 365}
_PLURAL_UNIT = {"günler": 1, "haftalar": 7, "aylar": 30, "yıllar": 365}

TOD_RX = re.compile(r"(?<![\w'’])(sabah|öğle|akşam|gece)"
                    r"(?:leyin|yin|üstü|üzeri|yarısı|den sonra|ları|leri|nin|nın|si|sı|ni|ne|ye|ya|a|e|ı|i|n)?(?![\w])", re.I)
GENERIC_RX = re.compile(r"\b(her|bütün|bazı)\s+(sabah|öğle|akşam|gece)|günaydın|iyi\s+(akşamlar|geceler)", re.I)
DAY_RX = re.compile(
    rf"\b(?:(ertesi|sonraki)\s+(gün|sabah|akşam|gece|hafta)|({_NUM})\s+(gün|hafta|ay|yıl|sene)\s+sonra|"
    r"(günler|haftalar|aylar|yıllar)\s+sonra)\b", re.I)
SEASON_RX = re.compile(r"\b(ilkbahar|bahar|yaz(?=\s+(?:tatil|mevsim|gün|güneş|sıcağ|geldi|gelmiş|bitti|boyunca)|ın\b|\b)|sonbahar|güz|kış)\w*", re.I)
AGE_RX = re.compile(rf"\b([A-ZÇĞİÖŞÜ][\wçğıöşü]+)\s+({_NUM})\s+yaş(?:ında|ındaydı|ına\s+(?:girdi|bastı|geldi))", re.I)
YEAR_RX = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
BIRTH_RX = re.compile(r"\b([A-ZÇĞİÖŞÜ][\wçğıöşü]+)[^.!?]*?\b(1[89]\d\d|20\d\d)\b[^.!?]*?\bdoğ(?:du|muş)", re.I)


def _n(s: str) -> int:
    s = s.strip().lower()
    return int(s) if s.isdigit() else _WORDS.get(re.sub(r"\s+", " ", s), 0)


def _tod(word: str) -> str:
    w = word.lower()
    return "SABAH" if w.startswith("sabah") else "OGLE" if w.startswith("öğle") else "AKSAM" if w.startswith("akşam") else "GECE"


def _season(word: str) -> str:
    w = word.lower()
    return "SONBAHAR" if w.startswith(("sonbahar", "güz")) else "ILKBAHAR" if w.startswith(("ilkbahar", "bahar")) \
        else "YAZ" if w.startswith("yaz") else "KIS"


def _sentence(text: str, pos: int) -> str:
    """Kalıbın geçtiği cümle: sayfanın kendi kelimeleri, alıntı kanıtı."""
    lo = max((text.rfind(ch, 0, pos) for ch in ".!?"), default=-1) + 1
    ends = [i for i in (text.find(ch, pos) for ch in ".!?") if i >= 0]
    hi = min(ends) + 1 if ends else len(text)
    return text[lo:hi].strip()


def extract(pages: list[dict], name_idx: dict[str, str] | None = None) -> list[dict]:
    """Sayfa sıralı zaman ifadeleri: kind, value, page, idx, pos, quote (+subject/year)."""
    out = []
    for p in sorted(pages, key=lambda x: x["page_no"]):
        for s in p["spans"]:
            t = s["text"]
            generic = [(m.start(), m.end()) for m in GENERIC_RX.finditer(t)]

            def inside(m):
                return any(a <= m.start() < b for a, b in generic)
            base = {"page": p["page_no"], "idx": s["idx"]}
            day_spans = []
            for m in DAY_RX.finditer(t):
                day_spans.append((m.start(), m.end()))
                if m.group(1):
                    days = 7 if m.group(2).lower() == "hafta" else 1
                    tod = _tod(m.group(2)) if m.group(2).lower() in ("sabah", "akşam", "gece") else None
                elif m.group(3):
                    days = _n(m.group(3)) * _UNIT[m.group(4).lower()]
                    tod = None
                else:
                    days = UNKNOWN_DAYS * _PLURAL_UNIT.get(m.group(5).lower(), 1)
                    tod = None
                out.append({**base, "kind": "GUN_GECISI", "value": days, "tod": tod, "pos": m.start(),
                            "quote": _sentence(t, m.start()), "span": (m.start(), m.end())})
            for m in TOD_RX.finditer(t):
                if inside(m) or any(a <= m.start() < b for a, b in day_spans):
                    continue
                out.append({**base, "kind": "GUN_VAKTI", "value": _tod(m.group(1)), "pos": m.start(),
                            "quote": _sentence(t, m.start()), "span": (m.start(), m.end())})
            for m in SEASON_RX.finditer(t):
                out.append({**base, "kind": "MEVSIM", "value": _season(m.group(1)), "pos": m.start(),
                            "quote": _sentence(t, m.start()), "span": (m.start(), m.end())})
            for m in AGE_RX.finditer(t):
                subj = m.group(1)
                cid = A.resolve_subject(subj, name_idx) if name_idx else None
                yrs = YEAR_RX.findall(_sentence(t, m.start()))
                out.append({**base, "kind": "YAS", "value": _n(m.group(2)), "subject": cid or C.norm(subj),
                            "year": int(yrs[0]) if yrs else None, "pos": m.start(),
                            "quote": _sentence(t, m.start()), "span": (m.start(), m.end())})
            for m in BIRTH_RX.finditer(t):
                subj = m.group(1)
                cid = A.resolve_subject(subj, name_idx) if name_idx else None
                out.append({**base, "kind": "DOGUM", "value": int(m.group(2)), "subject": cid or C.norm(subj),
                            "pos": m.start(), "quote": _sentence(t, m.start()), "span": (m.start(), m.end())})
    out.sort(key=lambda e: (e["page"], e["idx"], e["pos"]))
    for e in out:
        e.pop("span", None)
    return out


def check_order(exprs: list[dict], skip_pages: set | None = None) -> list[dict]:
    """Durum makinesi; aday: kind, a (önceki ifade), b (geri giden ifade), why."""
    skip = skip_pages or set()
    tod = day = season = tod_expr = season_expr = None
    ages: dict = {}
    births: dict = {}
    out = []
    for e in exprs:
        if e["page"] in skip:
            continue
        k, v = e["kind"], e["value"]
        if k == "GUN_GECISI":
            day = (day or 0) + v                  # mevsim korunur; uzun aralığı yargı değerlendirir
            tod, tod_expr = (e["tod"], e) if e.get("tod") else (None, None)
        elif k == "GUN_VAKTI":
            if tod is not None and TOD.index(v) < TOD.index(tod):
                if v == "SABAH":
                    day = (day or 0) + 1              # örtük yeni gün
                else:
                    out.append({"kind": "GUN_VAKTI", "a": tod_expr, "b": e,
                                "why": f"{TOD_TR[tod]} sonra aynı akışta {TOD_TR[v]}"})
                    continue
            tod, tod_expr = v, e
        elif k == "MEVSIM":
            if season is not None and (SEASONS.index(v) - SEASONS.index(season)) % 4 == 3:
                out.append({"kind": "MEVSIM", "a": season_expr, "b": e,
                            "why": f"{SEASON_TR[season]} sonra {SEASON_TR[v]}"})
                continue
            season, season_expr = v, e
        elif k == "YAS":
            prev = ages.get(e["subject"])
            if prev and v < prev["value"]:
                out.append({"kind": "YAS", "a": prev, "b": e, "why": f"yaş {prev['value']} sonra {v}"})
            else:
                ages[e["subject"]] = e
            b = births.get(e["subject"])
            if b and e.get("year") and (e["year"] - b["value"]) not in (v, v + 1):
                out.append({"kind": "TARIH", "a": b, "b": e,
                            "why": f"{b['value']} doğumlu, {e['year']} yılında {v} yaşında"})
        elif k == "DOGUM":
            births[e["subject"]] = e
            for a in (x for x in ages.values() if x["subject"] == e["subject"] and x.get("year")):
                if (a["year"] - v) not in (a["value"], a["value"] + 1):
                    out.append({"kind": "TARIH", "a": a, "b": e,
                                "why": f"{a['year']} yılında {a['value']} yaşında, doğum {v}"})
    return out


JUDGE = (
    "Soru: Aşağıdaki iki zaman ifadesi hikâyenin akışında bu SIRAYLA okunduğunda çelişiyor mu?\n"
    "İfade 1 (s.{p1}): “{q1}”\nİfade 2 (s.{p2}): “{q2}”\nOkunan sıra sorunu: {why}.\n\n"
    "Önce kitabın tamamına bak: ikinci ifade bir geri dönüş, anı, rüya, hayal, özet ya da başka bir "
    "günün anlatımı mı; arada gün/mevsim/yıl geçtiğini söyleyen bir cümle var mı; ifadelerden biri "
    "genel bir alışkanlık («her sabah») ya da mecaz mı; farklı kişiler/olaylar mı? Bunlardan biri "
    "varsa çelişki yoktur. Aynı olay akışında zaman açıklamasız geri gidiyorsa çelişkidir.\n\n"
    "Cevap tek harf: C = zaman çelişkisi (metin açıklamıyor); U = çelişki yok (bağdaşıyor ya da metin "
    "açıklıyor); B = karar verilemiyor.")

KIND_TR = {"GUN_VAKTI": "gün vakti", "MEVSIM": "mevsim", "YAS": "yaş", "TARIH": "yaş/tarih"}


def _ev(e: dict) -> dict:
    return {"page": e["page"], "paragraph": e.get("idx"), "kind": e["kind"], "value": e["value"], "quote": e["quote"]}


def finding_of(c: dict, v: dict) -> dict:
    a, b = c["a"], c["b"]
    p = v["p"]
    sev = "ERROR" if c["kind"] in ("YAS", "TARIH") and p >= ERROR_MIN else "WARN"
    return {"page": b["page"], "severity": sev, "quote": b["quote"],
            "message": (f"Zaman çizelgesi ({KIND_TR[c['kind']]}): s.{a['page']} “{a['quote']}” sonra "
                        f"s.{b['page']} “{b['quote']}” — {c['why']}; metin geri dönüşü açıklamıyor."),
            "suggestion": "İki yeri karşılaştırın; zaman ifadesini düzeltin ya da geçişi (ertesi gün, o sırada, "
                          "anımsadı) açıkça yazın.",
            "details": {"kind": c["kind"], "a": _ev(a), "b": _ev(b), "why": c["why"],
                        "judge": {k: v[k] for k in ("forward", "reverse")}, "p_contradiction": round(p, 3)}}


async def check(pages: list[dict], llm, evs: list[dict] | None = None,
                name_idx: dict[str, str] | None = None) -> tuple[list[dict], dict]:
    story = C.story_pages(pages)
    exprs = extract(story, name_idx)
    skip = C.unreal_pages(evs or [])
    cands = check_order(exprs, skip)
    stats = {"expressions": len(exprs), "by_kind": {k: sum(e["kind"] == k for e in exprs)
                                                    for k in ("GUN_VAKTI", "GUN_GECISI", "MEVSIM", "YAS", "DOGUM")},
             "unreal_pages": sorted(skip), "candidates": len(cands), "judge_failed": 0, "confirmed": 0,
             "candidates_detail": []}
    findings = []
    if cands:
        text = C.book_text(story)
        sem = asyncio.Semaphore(PARALLEL)

        def body(c, x, y):
            return C.INTRO + text + "\n\n" + JUDGE.format(p1=x["page"], q1=x["quote"], p2=y["page"], q2=y["quote"],
                                                          why=c["why"])
        verdicts = await asyncio.gather(
            *(C.judge_both(llm, body(c, c["a"], c["b"]), body(c, c["b"], c["a"]), sem,
                           sorted({c["a"]["page"], c["b"]["page"]})) for c in cands), return_exceptions=True)
        for c, v in zip(cands, verdicts):
            d = {"kind": c["kind"], "a": _ev(c["a"]), "b": _ev(c["b"]), "why": c["why"]}
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
    pages = await asyncio.to_thread(source.read, generation_id)
    evs = await asyncio.to_thread(C.events, generation_id)
    chars = await asyncio.to_thread(A.characters, generation_id)
    findings, stats = await check(pages, Llm(generation_id), evs, A.name_index(chars))
    findings.append({"page": None, "severity": "INFO",
                     "message": (f"Zaman çizelgesi: {stats['expressions']} zaman ifadesi okundu "
                                 f"({', '.join(f'{k.lower()} {n}' for k, n in stats['by_kind'].items() if n)}), "
                                 f"{len(stats['unreal_pages'])} sayfa anı/rüya diye sıraya girmedi; "
                                 f"{stats['candidates']} aday yargılandı, {stats['confirmed']} bulgu. "
                                 "Eşikler henüz gerçek kitapta ölçülmedi.")})
    return findings, stats
