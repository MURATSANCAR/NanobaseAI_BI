"""Yaş uygunluğu: does the text fit the book's declared age band?

Two parts, both returning candidates for the editor (docs/son-okuma/age_fit.md):

1. Readability (deterministic). The band comes from the book itself (METADATA AGE_RANGE
   claim, book.age_group, else the band printed in the imprint). Pages are measured with
   the Turkish formulas (Ateşman 1997, Çetinkaya–Uzun 2010, Bezirci–Yılmaz 2010) and plain
   counts, and compared with what books PUBLISHED FOR THE SAME BAND actually look like: the
   percentiles in `_age_fit_ref.REFERENCE`, measured on the publisher's 418-book corpus
   (288 books printed "6-10 yaş"). A formula's own grade table is not used as a verdict:
   they were fitted on textbooks for grades 5-12 and do not separate a 6-10 picture book
   from an adult novel well enough (measured, see the doc).
2. Sensitive content (judgement). A generic Turkish lexicon picks passages that MAY carry
   violence, fear, imitable unsafe behaviour, substances, death/grief, insult or sexual
   content; book-director classifies each passage into one closed category (one token, a
   probability) and, when it is not NONE, must return a verbatim quote and the same
   category a second time. A quote that is not in the passage, or a category that changes,
   drops the candidate. Every finding is one passage, never a verdict on the book.

Measured precision (six books, v1): see docs/son-okuma/age_fit.md.
"""
from __future__ import annotations

import asyncio
import re

from .. import db, ledger, source
from ..llm import Llm, PromptRef
from . import _age_fit_text as T
from ._age_fit_ref import REFERENCE, reference_for

NAME = "age_fit"
VERSION = "1"
LABEL = "Yaş uygunluğu"

# --------------------------------------------------------------------------- band ---


def declared_band(generation_id: str, pages: list[dict]) -> tuple[tuple[int, int] | None, str]:
    """(band, where it came from). The book's own word only: nothing is guessed."""
    row = db.one("SELECT claim FROM claim WHERE generation_id=%s AND kind='METADATA' AND subject='AGE_RANGE'"
                 " AND status NOT IN ('REJECTED','SUPERSEDED','EDITOR_REJECTED')"
                 " ORDER BY (status IN ('EDITOR_APPROVED','EDITOR_CORRECTED')) DESC, created_at DESC LIMIT 1",
                 generation_id)
    if row and (b := T.declared_band(row["claim"] + " yaş" if "ya" not in row["claim"].lower() else row["claim"])):
        return b, "metadata_claim"
    row = db.one("SELECT b.age_group FROM generation g JOIN book_version bv ON bv.id=g.book_version_id"
                 " JOIN book b ON b.id=bv.book_id WHERE g.id=%s", generation_id)
    if row and row["age_group"]:
        txt = row["age_group"]
        if b := T.declared_band(txt if "ya" in txt.lower() else txt + " yaş"):
            return b, "book.age_group"
    for p in pages:                       # the imprint: "RAF: 6-10 YAŞ"
        if b := T.declared_band(" ".join(s["text"] for s in p["spans"])):
            return b, f"printed:s{p['page_no']}"
    return None, "none"


# --------------------------------------------------------------------- readability ---


def story_paragraphs(page: dict) -> tuple[list[str], dict]:
    """The page's text the child reads, without imprint, bios and chapter headings."""
    keep, dropped = [], {"imprint": 0, "bio": 0, "garbled": 0, "contents": 0, "heading": 0}
    for s in page["spans"]:
        t = s["text"]
        why = T.is_matter(t) or ("heading" if s["role"] == "heading" or T.is_heading(t) else None)
        if why:
            dropped[why] += 1
        else:
            keep.append(t)
    return keep, dropped


def _pct(value: float, table: list[tuple[float, float]]) -> float:
    """Where `value` sits in a reference percentile table [(pct, value), ...] (monotone)."""
    lo = table[0]
    for p, v in table:
        if v >= value:
            if v == lo[1]:
                return p
            return lo[0] + (p - lo[0]) * (value - lo[1]) / (v - lo[1])
        lo = (p, v)
    return 100.0


def readability(pages: list[dict], band: tuple[int, int] | None) -> tuple[list[dict], dict]:
    ref_key, ref = reference_for(band)
    findings, per_page, all_paras = [], [], []
    dropped_total = {"imprint": 0, "bio": 0, "garbled": 0, "contents": 0, "heading": 0}
    for p in pages:
        paras, dropped = story_paragraphs(p)
        for k, v in dropped.items():
            dropped_total[k] += v
        all_paras += paras
        if not paras:
            continue
        m = T.measure(paras)
        if not m.get("words"):
            continue
        per_page.append({"page": p["page_no"], **m})
        if ref is None:
            continue
        # (a) one sentence far longer than books for this band use
        for para in T.stream(paras):
            for s in T.sentences(para):
                n = len(T.words(s))
                if n > ref["sentence_words_p99"] and not T.BROKEN.search(s):
                    findings.append({
                        "page": p["page_no"], "severity": "WARN", "quote": s.strip()[:600],
                        "message": f"Çok uzun cümle: {n} kelime. {ref_key} yaş için yayımlanmış kitaplarda "
                                   f"cümlelerin %99'u {ref['sentence_words_p99']} kelimeyi geçmiyor "
                                   f"(ortanca {ref['sentence_words_p50']}).",
                        "suggestion": "Cümleyi bölmeyi düşünün.",
                        "details": {"kind": "LONG_SENTENCE", "words": n, "band": band, "reference": ref_key,
                                    "threshold": ref["sentence_words_p99"]}})
        # (b) a page whose text is harder than 99 of 100 pages of books for this band
        if m["sentences"] >= ref["page_min_sentences"]:
            hard = [k for k, lim in (("atesman", ref["page_atesman_p1"]),) if m[k] < lim] + \
                   [k for k, lim in (("yod", ref["page_yod_p99"]), ("asl", ref["page_asl_p99"])) if m[k] > lim]
            if len(hard) >= 2:
                findings.append({
                    "page": p["page_no"], "severity": "WARN",
                    "message": f"Sayfa metni {ref_key} yaş kitaplarının sayfalarının %99'undan daha zor: "
                               f"Ateşman {m['atesman']} (bant alt %1: {ref['page_atesman_p1']}), "
                               f"Bezirci–Yılmaz {m['yod']} (üst %1: {ref['page_yod_p99']}), "
                               f"ortalama cümle {m['asl']} kelime (üst %1: {ref['page_asl_p99']}).",
                    "suggestion": "Cümleleri kısaltmayı, uzun/çok heceli sözcükleri sadeleştirmeyi düşünün.",
                    "details": {"kind": "HARD_PAGE", "measures": m, "exceeds": hard, "band": band,
                                "reference": ref_key}})
    book = T.measure(all_paras)
    stats = {"band": band, "reference": ref_key, "dropped_paragraphs": dropped_total, "book": book,
             "pages_measured": len(per_page), "pages": per_page}
    if book.get("words"):
        pos = ({k: round(_pct(book[k], ref["book_pct"][k]), 1) for k in ("atesman", "cetinkaya", "yod", "asl")}
               if ref else {})
        # Book level is information, never a warning: the formulas separate 6-10 books from
        # adult novels with AUC 0.70-0.73 only (_age_fit_ref), too weak for a verdict.
        harder = ([k for k in ("yod", "asl") if pos[k] >= 95] + (["atesman"] if pos["atesman"] <= 5 else [])
                  if ref else [])
        stats["book_percentile_in_band"] = pos
        msg = (f"Kitap geneli: {book['words']} kelime, {book['sentences']} cümle; ortalama cümle {book['asl']} "
               f"kelime, kelime başına {book['asw']} hece; Ateşman {book['atesman']}, Çetinkaya–Uzun "
               f"{book['cetinkaya']}, Bezirci–Yılmaz {book['yod']}; diyalog payı %{round(100*book['dialogue_share'])}.")
        if ref:
            msg += (f" {ref_key} yaş kitapları arasındaki yeri (yüzdelik): Ateşman {pos['atesman']}, "
                    f"Bezirci–Yılmaz {pos['yod']}, ortalama cümle {pos['asl']}.")
        else:
            msg += " Bu yaş bandı için karşılaştırma derlemi yok; sayfa ve cümle uyarısı üretilmedi."
        findings.insert(0, {"page": None, "severity": "INFO", "message": msg,
                            "details": {"kind": "BOOK_MEASURES", "measures": book, "band": band,
                                        "reference": ref_key, "percentile_in_band": pos, "harder": harder}})
    return findings, stats


# ------------------------------------------------------------- sensitive content ---

CATEGORIES = {
    "A": ("NONE", "yaşa uygun, dikkat gerektirmiyor"),
    "B": ("VIOLENCE", "ayrıntılı ya da onaylanan şiddet, yaralama, kan, silah"),
    "C": ("FEAR", "bu yaş için fazla yoğun korku, dehşet, kâbus sahnesi"),
    "D": ("UNSAFE_IMITABLE", "çocuğun taklit edebileceği tehlikeli davranış (ateş, kibrit, ilaç, yükseklik, "
                             "yabancıyla gitme, trafik, suya girme...) sonuçsuz ya da olumlu gösterilmiş"),
    "E": ("SUBSTANCE", "alkol, sigara, uyuşturucu"),
    "F": ("DEATH_GRIEF", "ölüm, yas, ciddi hastalık"),
    "G": ("INSULT_DISCRIMINATION", "aşağılama, lakap takma, ayrımcılık onaylanarak gösterilmiş"),
    "H": ("SEXUAL", "cinsellik"),
}
SEVERITY = {"VIOLENCE": "WARN", "UNSAFE_IMITABLE": "WARN", "SUBSTANCE": "WARN", "SEXUAL": "WARN",
            "INSULT_DISCRIMINATION": "WARN", "FEAR": "INFO", "DEATH_GRIEF": "INFO"}

# Stems that MAY open such a passage. Generic Turkish, never taken from one book. A hit only
# sends the passage to the classifier; the lexicon's recall is measured (doc) against the
# classifier run over every paragraph of a book.
LEXICON = {
    "VIOLENCE": r"öldür|kan\b|kanı\b|kana\b|kanlı|kanam|kanıyor|bıçak|silah|tabanca|tüfek|dövü?[şy]?|"
                r"yumrukla|tokat|yarala|saldır|savaş|bomba|kavga|tekme|ısır|parçala|boğazla|"
                r"vur(?:du|uyor|acak|mak|dum|ul)",
    "FEAR": r"kork|dehşet|canavar|hayalet|cadı|kâbus|kabus|çığlık|ürper|karanlık|ejderha|zombi|vampir|panik",
    "UNSAFE_IMITABLE": r"kibrit|çakmak|yangın|ateş|yak(?:tı|mak|arak|acağ|ıyor|ma\b)|priz|ilaç|hap\b|balkon|"
                       r"pencereden|çatı|tırman|yabancı|kaybol|makas|boğul|trafik|karşıdan karşıya|"
                       r"emniyet kemeri|zehir|deterjan|çamaşır suyu|gizlice",
    "SUBSTANCE": r"sigara|alkol|içki\b|içkil|bira\b|biralar|şarap|rakı\b|sarhoş|uyuşturucu|tütün",
    "DEATH_GRIEF": r"öldü|ölüm|ölmüş|vefat|cenaze|mezar|yas\b|kanser|son nefes",
    "INSULT_DISCRIMINATION": r"aptal|salak|şişko|gerizekalı|ahmak|ezik\b|dalga geç|alay et|lakap",
    "SEXUAL": r"öpüş|öptü|öpücük|çıplak|seks",
}
# every stem starts a word ("bira" must not match "biraz")
_LEX = re.compile("|".join(f"(?P<{k}>(?<!\\w)(?:{v}))" for k, v in LEXICON.items()), re.I)

CLASSIFY = PromptRef("proof_age_sensitive", "1")
QUOTE = PromptRef("proof_age_sensitive_quote", "1")


def _classify_prompt(band_txt: str, context: str, passage: str) -> str:
    cats = "\n".join(f"{k}) {name}: {desc}" for k, (name, desc) in CATEGORIES.items())
    return (f"Bir çocuk kitabının son okumasını yapan editörsün. Kitabın yayınevince beyan edilen okur yaşı: "
            f"{band_txt}.\nAşağıdaki PASAJ bu yaştaki bir çocuk için editörün dikkatini gerektiren bir içerik "
            f"taşıyor mu? Hikâyenin olağan çatışması, hafif heyecan, eğlenceli abartı, sonucu gösterilip "
            f"doğrusu öğretilen hata ve masalsı tehlike dikkat gerektirmez (A). Yalnız pasajın KENDİSİNDE "
            f"yazanı değerlendir; tahmin yürütme.\nKategoriler:\n{cats}\n\nÖnceki paragraf (yalnız bağlam):\n"
            f"<<<{context or '-'}>>>\nPASAJ:\n<<<{passage}>>>\nTek harfle cevap ver.")


def _quote_prompt(band_txt: str, passage: str) -> str:
    cats = ", ".join(name for name, _ in CATEGORIES.values())
    return (f"Bir çocuk kitabının son okumasını yapan editörsün; okur yaşı {band_txt}.\nPASAJ:\n<<<{passage}>>>\n"
            f"Bu pasajda bu yaş için editörün dikkatini gerektiren içerik varsa kategorisini ({cats}) seç, "
            f"pasajdan o içeriği taşıyan kısmı HARFİ HARFİNE (kelimesi kelimesine, değiştirmeden) `quote` "
            f"alanına kopyala ve nedenini tek cümle Türkçe `reason` alanına yaz. Yoksa kategori NONE, quote "
            f"boş olsun.")


QUOTE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["category", "quote", "reason"],
                "properties": {"category": {"type": "string", "enum": [n for n, _ in CATEGORIES.values()]},
                               "quote": {"type": "string", "maxLength": 600},
                               "reason": {"type": "string", "maxLength": 400}}}


def candidates(pages: list[dict]) -> list[dict]:
    """Story paragraphs that contain a lexicon stem, with the previous paragraph as context."""
    out, prev = [], ""
    for p in pages:
        paras, _ = story_paragraphs(p)
        for para in paras:
            hits = sorted({m.lastgroup for m in _LEX.finditer(para)})
            if hits:
                out.append({"page": p["page_no"], "text": para, "context": prev[-600:], "lexicon": hits})
            prev = para
    return out


async def sensitive(generation_id: str, pages: list[dict], band: tuple[int, int] | None,
                    only: list[dict] | None = None) -> tuple[list[dict], dict]:
    band_txt = f"{band[0]}-{band[1]} yaş" if band else "belirtilmemiş (çocuk kitabı)"
    cands = only if only is not None else candidates(pages)
    llm = Llm(generation_id)
    letters = list(CATEGORIES)
    sem = asyncio.Semaphore(4)
    stats = {"candidates": len(cands), "classified_not_none": 0, "quote_not_verbatim": 0,
             "category_changed": 0, "failed": 0}

    async def one(c: dict) -> dict | None:
        async with sem:
            try:
                probs, _ = await llm.choose("book-director", [{"role": "user", "content": _classify_prompt(
                    band_txt, c["context"], c["text"])}], letters, pages=[c["page"]], prompt=CLASSIFY)
            except Exception:  # noqa: BLE001 - one passage lost is counted, the rest go on
                stats["failed"] += 1
                return None
            best = max(probs, key=probs.get)
            c = {**c, "probs": {CATEGORIES[k][0]: round(v, 3) for k, v in probs.items() if v >= 0.01}}
            if best == "A":
                return c
            stats["classified_not_none"] += 1
            cat = CATEGORIES[best][0]
            out, _ = await llm.chat("book-director", [{"role": "user", "content": _quote_prompt(band_txt, c["text"])}],
                                    schema=QUOTE_SCHEMA, max_tokens=700, temperature=0.0, thinking=False,
                                    pages=[c["page"]], prompt=QUOTE)
            c = {**c, "category": cat, "p": round(probs[best], 3), "second": out}
            if out["category"] != cat:
                stats["category_changed"] += 1
                return c
            if not out["quote"].strip() or ledger.norm(out["quote"]) not in ledger.norm(c["text"]):
                stats["quote_not_verbatim"] += 1
                return c
            c["confirmed"] = True
            return c

    results = [r for r in await asyncio.gather(*(one(c) for c in cands)) if r]
    findings = []
    for r in results:
        if not r.get("confirmed"):
            continue
        name = r["category"]
        desc = next(d for n, d in CATEGORIES.values() if n == name)
        findings.append({
            "page": r["page"], "severity": SEVERITY[name] if r["p"] >= 0.8 else "INFO",
            "quote": r["second"]["quote"].strip(),
            "message": f"{band_txt} için hassas içerik adayı ({desc}): {r['second']['reason']}",
            "details": {"kind": "SENSITIVE", "category": name, "probability": r["p"], "probs": r["probs"],
                        "lexicon": r["lexicon"], "band": band}})
    stats["confirmed"] = len(findings)
    stats["by_category"] = {n: sum(f["details"]["category"] == n for f in findings) for n, _ in CATEGORIES.values()
                            if n != "NONE"}
    stats["results"] = [{k: r.get(k) for k in ("page", "lexicon", "probs", "category", "p", "confirmed")}
                        for r in results]
    return findings, stats


async def run(generation_id: str):
    pages = source.read(generation_id)
    band, band_source = declared_band(generation_id, pages)
    findings, stats = readability(pages, band)
    if band is None:
        findings.insert(0, {"page": None, "severity": "INFO",
                            "message": "Kitapta beyan edilmiş yaş bandı bulunamadı (künye, üst veri); "
                                       "okunabilirlik yalnız ölçüldü, banda göre uyarı üretilmedi.",
                            "details": {"kind": "NO_BAND"}})
    sens, sstats = await sensitive(generation_id, pages, band)
    stats.update(band_source=band_source, sensitive=sstats)
    return findings + sens, stats
