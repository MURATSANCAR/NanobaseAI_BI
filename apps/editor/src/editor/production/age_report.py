"""Yaş uygunluğu raporu (Kitap Tasarım Stüdyosu): kelime düzeyi, cümle uzunluğu, hassas içerik ve okul/MEB
ölçütlerine uygunluk.

Yeni ölçü yazılmaz; son okumanın yaş uygunluğu denetimi (`proofing/age_fit`, belgesi
`docs/son-okuma/age_fit.md`) stüdyo işinin GÜNCEL metnine uygulanır:
- metin: sayfa planı varsa planın sayfaları (sayfa kimliğiyle; ekran bulgudan o sayfayı açar), yoksa dizginin sayfa
  haritası, o da yoksa el yazmasının bölümleri;
- hedef yaş: işin profili (yayınevi beyanı/CRM, yoksa Zeki AI okuması; kaynağı raporda yazılı);
- okunabilirlik (Ateşman, Çetinkaya–Uzun, Bezirci–Yılmaz; bant derleminin yüzdelikleriyle) ve hassas içerik
  (genel sözlük + model sınıflaması + harfi harfine alıntı) `age_fit.readability` / `age_fit.sensitive`.

Eklenen tek ölçü kelime düzeyidir ve o da derlemden ölçülür (uydurma liste yok): yayınevinin kendi kitapları
(bant kitaplarının kendi künyesinde basılı «6-10 yaş»; `_age_fit_ref` ile aynı derlem, aynı paragraf kurucu)
Zemberek köküne indirilir; bir kökün kaç bant kitabında geçtiği (`df`) `data/age_vocab.json.gz`'dedir. «Seyrek»
eşiği de ölçüdür: bant kitaplarının kendi kelime kullanımlarının (kitap ağırlıklı, kitap kendisi hariç) en çok
%1'inin kaldığı en büyük `df` (`K`). Kitap derlemin içindeyse (aynı kitabın seyrek kökleri) kendisi sayılmaz.
Seyrek her kök sayfalarıyla listelenir (tavan yok); her birine Zeki AI sade karşılık önerir, öneri editör onayına
gider, onaylanan metne ancak editör «uygula» deyince girer.

MEB/okul ölçütleri `docs/analiz/meb-uygunluk-olcutleri.md`'dedir (kaynak bağlantılarıyla). Otomatik denetlenebilenler
burada `CHECKS` ile ölçülür; denetlenemeyenler `CHECKLIST` editör kontrol listesidir (işaretleyen kişi ve zaman
kaydıyla). Kaynağı bulunamayan ölçüt yazılmadı.

Dosyalar (iş klasörü): yas-raporu.json (son rapor), yas-raporu-durum.json (süren/biten koşu), yas-raporu-kararlar.json
(editör kararları: bulgu, kelime önerisi, kontrol listesi; salt ekleme günlüğü + son hâl), yas-raporu/ (PDF dizgisi).
"""

from __future__ import annotations

import asyncio
import collections
import gzip
import hashlib
import json
import re
import threading
import time
from functools import lru_cache
from pathlib import Path

from ..proofing import _age_fit_text as T
from ..proofing import _word_variety as W
from ..proofing import age_fit
from ..proofing._age_fit_ref import REFERENCE, reference_for
from . import studio

VOCAB_FILE = Path(__file__).resolve().parent / "data" / "age_vocab.json.gz"
TEMPLATE = Path(__file__).resolve().parent / "templates" / "age_report.typ"
REPORT = "yas-raporu.json"
STATUS = "yas-raporu-durum.json"
DECISIONS = "yas-raporu-kararlar.json"
PDF_DIR = "yas-raporu"
VERSION = "1"
# 1117 sayılı Kanun m.1 «on sekiz yaşından küçükler»: bandın en küçük yaşı bundan büyükse kitap çocuk/genç
# kitabı değildir; hassas içerik ve okul ölçütleri koşmaz, rapor bunu söyler.
ADULT = 18
PARALLEL = 4                    # model çağrısı eşzamanlılığı (age_fit.sensitive ile aynı)
SYN = "book-director"


# ====================================================================== metin
def job_pages(d: Path) -> tuple[list[dict], str]:
    """Stüdyo işinin güncel metni, age_fit'in beklediği biçimde: [{"page_no", "pid", "label", "spans": [{text, role}]}].

    Sayfa planı: yazı kutusunun blokları (başlık bloğu `heading`, konuşma bloğu «– » ile), balonlar konuşma satırı;
    serbest yazı ve efekt yazı süs sayılır (`heading`, okunabilirliğe girmez). Plan yoksa sayfa haritası (ön sayfalar
    hariç), o da yoksa el yazmasının bölümleri."""
    from . import plan as plan_mod
    pl = plan_mod.load(d)
    if pl is not None:
        out = []
        for i, pg in enumerate(pl["pages"]):
            spans = []
            for b in (pg.get("text") or {}).get("blocks", []):
                t = "".join(r.get("text", "") for r in b["runs"]) if b.get("runs") else b.get("text", "")
                if not t.strip():
                    continue
                if b.get("kind") == "dialogue" and not T._DASH.match(t):
                    t = "– " + t
                spans.append({"text": t, "role": "heading" if b.get("kind") == "heading" else "body"})
            for bb in pg.get("bubbles") or []:
                if (bb.get("text") or "").strip():
                    spans.append({"text": "– " + bb["text"].strip(), "role": "body"})
            for x in pg.get("texts") or []:
                t = "".join(r.get("text", "") for r in x.get("runs", []))
                if t.strip():
                    spans.append({"text": t, "role": "heading"})
            no = plan_mod.FRONT + i + 1
            out.append({"page_no": no, "pid": pg["id"], "label": f"{no}. sayfa", "spans": spans})
        return out, "plan"
    pm = studio.read(d, "pagemap.json")
    if pm:
        out = []
        for p in pm["pages"]:
            if p.get("kind") == "front" or not (p.get("text") or "").strip():
                continue
            spans = [{"text": t.strip(), "role": "body"} for t in re.split(r"\n\s*\n", p["text"]) if t.strip()]
            out.append({"page_no": p["no"], "pid": None, "label": f"{p['no']}. sayfa", "spans": spans})
        return out, "pagemap"
    ms = studio.read(d, "manuscript.json") or {"chapters": []}
    out = []
    for ci, ch in enumerate(ms["chapters"]):
        spans = ([{"text": ch["title"], "role": "heading"}] if ch.get("title") else []) + \
                [{"text": b["text"], "role": "body"} for b in ch["blocks"] if b["text"].strip()]
        out.append({"page_no": ci + 1, "pid": None, "label": f"{ci + 1}. bölüm", "spans": spans})
    return out, "manuscript"


def text_hash(pages: list[dict]) -> str:
    h = hashlib.sha256()
    for p in pages:
        h.update(json.dumps([p["page_no"], p["pid"], p["spans"]], ensure_ascii=False).encode())
    return h.hexdigest()[:16]


def band_of(d: Path) -> tuple[tuple[int, int] | None, str]:
    """Hedef yaş: işin profili. Kaynak metni profilden (yayınevi beyanı/CRM ya da model okuması)."""
    prof = studio.read(d, "profile.json") or {}
    lo, hi = prof.get("age_min"), prof.get("age_max")
    if isinstance(lo, int) and isinstance(hi, int) and 0 <= lo <= hi:
        src = prof.get("age_source") or "profil"
        return (lo, hi), ("Zeki AI okuması (yayınevi beyanı yok)" if src == "model okuması" else src)
    return None, "yok"


# ====================================================================== kelime düzeyi
_an_lock = threading.Lock()


@lru_cache(maxsize=1)
def _analyzer():
    import logging
    logging.getLogger("zeyrek").setLevel(logging.ERROR)
    import zeyrek
    return zeyrek.MorphAnalyzer()


@lru_cache(maxsize=200_000)
def _cands(form: str) -> tuple:
    """Zemberek çözümlemeleri → (kök, tür, gövde uzunluğu, özel ad mı) (word_variety ile aynı)."""
    with _an_lock:
        try:
            an = list(_analyzer()._parse(form))
        except Exception:  # noqa: BLE001 - çözümleyicinin tek biçimde düşmesi «çözümleme yok»tur
            an = []
    return tuple(W.candidates(an))


def lemma_tokens(pages: list[dict]) -> tuple[list[dict], dict[str, list[int]]]:
    """Hikâye metnindeki içerik sözcükleri köküyle: [{page_no, word, form, lemma, pos, sentence}] ve çözümlenemeyen
    biçimler {biçim: [sayfa]}. Özel ad (cümle ortasında büyük harf, kesmeli büyük harf, cümle başında yalnız özel ad
    çözümlemesi) ve işlev sözcüğü (bağlaç, zamir, edat…) dışarıda: kelime düzeyi söz varlığıdır.
    Kitabın kendi kullanımı da bakılır: cümle ortasında büyük harfle geçen biçim her yerde addır; hep cümle başında,
    büyük harfle ve en az iki kez geçip hiç küçük harfle geçmeyen biçim de addır («Elif» sözlükte harf adıdır)."""
    sents = []
    for p in pages:
        paras, _ = age_fit.story_paragraphs(p)
        for para in T.stream(paras):
            for s in T.sentences(para):
                sents.append((p["page_no"], s, [w.replace("’", "'").partition("'") for w in T.words(s)]))
    mid_name, lower, start_cap = set(), set(), collections.Counter()
    for _, _, ws in sents:
        for k, (base, _, suf) in enumerate(ws):
            f = W.lower_tr(base)
            if base[:1].islower():
                lower.add(f)
            elif k == 0 and not base.isupper():
                start_cap[f] += 1
            elif W.word_kind(base, "'" if suf else "", k == 0) == "name":
                mid_name.add(f)
    names = mid_name | {f for f, n in start_cap.items() if n >= 2 and f not in lower}
    raw, form_cands, counts = [], {}, collections.Counter()
    for page_no, s, ws in sents:
        for k, (base, _, suf) in enumerate(ws):
            if W.word_kind(base, "'" if suf else "", k == 0) == "name":
                continue
            form = W.lower_tr(base)
            if len(form) < 2 or (form in names and base[:1].isupper() and not base.isupper()):
                continue
            if form not in form_cands:
                form_cands[form] = list(_cands(form))
            cs = form_cands[form]
            if base[:1].isupper() and not base.isupper() and cs and all(c[3] for c in cs):
                continue                    # cümle başında, sözlükte yalnız özel ad
            counts[form] += 1
            raw.append((page_no, base, form, s.strip()))
    chosen = W.choose_lemmas(form_cands, counts)
    toks, unknown = [], collections.defaultdict(list)
    for page_no, word, form, sent in raw:
        if form not in chosen:
            unknown[form].append(page_no)
            continue
        lem, pos, _amb = chosen[form]
        if pos not in W.CONTENT_POS:
            continue
        toks.append({"page_no": page_no, "word": word, "form": form, "lemma": lem, "pos": pos, "sentence": sent})
    return toks, dict(unknown)


@lru_cache(maxsize=1)
def vocab() -> dict | None:
    if not VOCAB_FILE.exists():
        return None
    with gzip.open(VOCAB_FILE, "rt", encoding="utf-8") as f:
        return json.load(f)


def vocab_for(band: tuple[int, int] | None) -> tuple[str | None, dict | None]:
    """Bandı içeren ölçülmüş kelime derlemi (okunabilirlik referansıyla aynı eşleme: 7-9 → 6-10)."""
    key, _ = reference_for(band)
    v = vocab()
    if key is None or v is None or key not in v["bands"]:
        return None, None
    return key, v["bands"][key]


def same_book(ref: dict, lemmas: set[str]) -> int | None:
    """Kitap derlemin içindeyse o kitabın sırası: derlem kitabının seyrek köklerinin (df ≤ K+1) payı kitabımızda
    `same_book_min`'den büyükse aynı kitaptır (eşik derlemde ölçüldü: başka kitaplar arasındaki en yüksek pay)."""
    per: dict[int, int] = collections.Counter()
    for lem, books in ref["rare_books"].items():
        if lem in lemmas:
            for b in books:
                per[b] += 1
    best = None
    for b, n in per.items():
        size = ref["book_rare_sizes"][b]
        if size >= ref["same_book_min_size"] and n / size > ref["same_book_min"]:
            if best is None or n / size > best[1]:
                best = (b, n / size)
    return best[0] if best else None


def rare_words(pages: list[dict], band: tuple[int, int] | None) -> tuple[list[dict], dict]:
    """Bant kitaplarında seyrek kökler, sayfalarıyla. Liste kesilmez."""
    key, ref = vocab_for(band)
    toks, unknown = lemma_tokens(pages)
    stats = {"reference": key, "content_tokens": len(toks), "lemmas": len({t["lemma"] for t in toks}),
             "unknown_forms": len(unknown), "unknown": [{"form": f, "pages": sorted(set(ps))}
                                                        for f, ps in sorted(unknown.items())]}
    if ref is None:
        return [], stats
    df = ref["df"]
    own = same_book(ref, {t["lemma"] for t in toks})
    in_own = {lem for lem, books in ref["rare_books"].items() if own is not None and own in books}
    K = ref["K"]
    groups: dict[str, dict] = {}
    rare_tok = 0
    for t in toks:
        n = df.get(t["lemma"], 0) - (1 if t["lemma"] in in_own else 0)
        if n > K:
            continue
        rare_tok += 1
        g = groups.setdefault(t["lemma"], {"lemma": t["lemma"], "pos": t["pos"], "df": n, "forms": [], "pages": []})
        if t["form"] not in g["forms"]:
            g["forms"].append(t["form"])
        g["pages"].append({"page_no": t["page_no"], "word": t["word"], "form": t["form"], "sentence": t["sentence"][:600]})
    share = rare_tok / len(toks) if toks else 0.0
    stats.update(books=ref["books"], K=K, own_book_excluded=own is not None, rare_tokens=rare_tok,
                 rare_share=round(share, 4), rare_share_pct=round(age_fit._pct(share, ref["book_rare_share"]), 1)
                 if toks else None, rare_share_p95=_at(ref["book_rare_share"], 95))
    out = sorted(groups.values(), key=lambda g: (g["df"], g["pages"][0]["page_no"], g["lemma"]))
    return out, stats


def _pc(v: float, places: int = 1) -> str:
    """Yüzde, Türkçe ondalıkla: 0.0556 → «%5,6»."""
    return "%" + f"{100 * v:.{places}f}".replace(".", ",")


def _at(table: list, pct: float) -> float | None:
    return next((v for p, v in table if p == pct), None)


# ---------------------------------------------------------------------- derlem ölçümü (bir kez, GPU'da)
def _corpus_book(path: str) -> dict | None:
    """Bir PDF: metin katmanı → paragraf (okumadaki kurucu) → basılı bant → hikâye kökleri."""
    import pymupdf

    from ..document import _garbled_ratio, paragraphs_from_layout
    try:
        doc = pymupdf.open(path)
    except Exception:  # noqa: BLE001
        return None
    pages = []
    for i, page in enumerate(doc, start=1):
        try:
            if _garbled_ratio(page.get_text("text") or "") > 0.02:
                continue
            paras = paragraphs_from_layout(page)
        except Exception:  # noqa: BLE001 - okunamayan sayfa atlanır
            continue
        if paras:
            pages.append({"page_no": i, "pid": None, "spans": [{"text": t, "role": "body"} for t in paras]})
    full = " ".join(s["text"] for p in pages for s in p["spans"])
    band = T.declared_band(full)
    key, _ = reference_for(band)
    if key is None:
        return {"path": path, "band": band, "key": None}
    toks, _ = lemma_tokens(pages)
    words = sum(len(T.words(para)) for p in pages for para in age_fit.story_paragraphs(p)[0])
    return {"path": path, "band": band, "key": key, "words": words,
            "hash": hashlib.sha256(full.encode()).hexdigest()[:16],
            "lemmas": collections.Counter(t["lemma"] for t in toks)}


def build_vocab(root: str, out: str, workers: int = 32, min_words: int = 300) -> dict:
    """Derlemden kelime referansı: bant başına kök → kaç kitapta (df), seyrek eşiği K, kitabın seyrek payı yüzdelikleri,
    aynı-kitap eşiği. `_age_fit_ref` ile aynı derlem kuralları: bant kitabın kendi basılı bandı, ≥300 kelime,
    kitap ağırlıklı yüzdelik, en az 30 kitap."""
    from concurrent.futures import ProcessPoolExecutor
    paths = sorted(str(p) for p in Path(root).rglob("*.pdf") if "/nonbook/" not in str(p))
    with ProcessPoolExecutor(workers) as ex:
        books = [b for b in ex.map(_corpus_book, paths, chunksize=1) if b]
    by_band: dict[str, list[dict]] = collections.defaultdict(list)
    seen = set()
    for b in books:
        if b.get("key") and b["words"] >= min_words and b["hash"] not in seen:
            seen.add(b["hash"])
            by_band[b["key"]].append(b)
    res = {"version": 1, "measured": time.strftime("%Y-%m-%d"), "root": root, "pdfs": len(paths), "bands": {}}
    for key, bs in by_band.items():
        if len(bs) < 30:
            res["bands"][key] = {"books": len(bs), "skipped": "30 kitaptan az"}
            continue
        df = collections.Counter()
        for b in bs:
            df.update(b["lemmas"].keys())
        # K: bant kitaplarının kelime kullanımlarının (kitap ağırlıklı, kitap kendisi hariç) en çok %1'inin
        # kaldığı en büyük df. F(k) = ortalama_b(pay(df_{-b} ≤ k)).
        def share_upto(k):
            vals = []
            for b in bs:
                tot = sum(b["lemmas"].values())
                low = sum(c for lem, c in b["lemmas"].items() if df[lem] - 1 <= k)
                vals.append(low / tot if tot else 0.0)
            return vals
        F = {}
        for k in range(0, len(bs)):
            F[k] = sum(share_upto(k)) / len(bs)
            if F[k] > 0.01:
                break
        K = max([k for k, v in F.items() if v <= 0.01], default=-1)
        shares = sorted(share_upto(K)) if K >= 0 else [0.0] * len(bs)
        pct = [1, 5, 10, 25, 50, 75, 90, 95, 99]
        table = [(p, round(shares[min(len(shares) - 1, int(round(p / 100 * (len(shares) - 1))))], 4)) for p in pct]
        rare_books = collections.defaultdict(list)
        for i, b in enumerate(bs):
            for lem in b["lemmas"]:
                if df[lem] <= K + 1:
                    rare_books[lem].append(i)
        sizes = [sum(1 for lem in b["lemmas"] if df[lem] <= K + 1) for b in bs]
        # aynı kitap eşiği: iki FARKLI kitap arasında seyrek kök payının en yükseği (seri kitaplar dahil)
        cross = 0.0
        sets = [{lem for lem in b["lemmas"] if df[lem] <= K + 1} for b in bs]
        for i in range(len(bs)):
            for j in range(len(bs)):
                if i != j and sizes[j] >= 5:
                    cross = max(cross, len(sets[i] & sets[j]) / sizes[j])
        res["bands"][key] = {
            "books": len(bs), "K": K, "F": {str(k): round(v, 4) for k, v in F.items()},
            "book_rare_share": table, "df": dict(sorted(df.items())), "rare_books": dict(sorted(rare_books.items())),
            "book_rare_sizes": sizes, "same_book_min": round(cross, 3), "same_book_min_size": 5,
            "files": [Path(b["path"]).name for b in bs]}
    with gzip.open(out, "wt", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, separators=(",", ":"))
    return {k: {kk: vv for kk, vv in v.items() if kk not in ("df", "rare_books", "book_rare_sizes", "files")}
            for k, v in res["bands"].items()} | {"pdfs": len(paths), "books_with_band": sum(1 for b in books if b.get("key"))}


# ====================================================================== sade karşılık önerisi (model)
SYN_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["anlam", "bicimler"],
              "properties": {"anlam": {"type": "string", "maxLength": 200},
                             "bicimler": {"type": "array", "items": {
                                 "type": "object", "additionalProperties": False, "required": ["bicim", "oneriler"],
                                 "properties": {"bicim": {"type": "string", "maxLength": 80},
                                                "oneriler": {"type": "array", "maxItems": 3,
                                                             "items": {"type": "string", "maxLength": 80}}}}}}}


def _syn_prompt(band_txt: str, g: dict) -> str:
    ex = []
    for f in g["forms"]:
        s = next(p["sentence"] for p in g["pages"] if p["form"] == f)
        ex.append(f"- «{f}»: {s}")
    return (f"Bir çocuk kitabının editörüne yardım ediyorsun. Kitabın okur yaşı: {band_txt}. «{g['lemma']}» sözcüğü bu "
            f"yaş için yayımlanmış kitaplarda seyrek geçiyor. Kitapta geçtiği biçimler ve birer cümlesi:\n"
            + "\n".join(ex) +
            "\nHer biçim için, o cümlede aynı yere aynı eklerle konabilecek, bu yaştaki çocuğun anlayacağı daha sade "
            "karşılıklar öner (en çok 3; anlamı değiştirme; iyi bir karşılık yoksa boş liste). `bicim` alanına biçimi "
            "yukarıda yazıldığı gibi koy. `anlam`: sözcüğün bu cümlelerdeki anlamı, en çok 12 kelime, Türkçe.")


def _clean_syn(g: dict, out: dict) -> dict:
    by_form = {}
    for b in out.get("bicimler") or []:
        f = W.lower_tr((b.get("bicim") or "").strip())
        if f not in g["forms"]:
            continue
        opts = []
        for o in b.get("oneriler") or []:
            o = " ".join(str(o).split())
            if o and W.lower_tr(o) != f and len(o.split()) <= 4 and o not in opts:
                opts.append(o)
        by_form[f] = opts
    return {"meaning": " ".join((out.get("anlam") or "").split())[:200], "by_form": by_form}


async def suggest(words: list[dict], band: tuple[int, int] | None, llm, progress=None) -> dict:
    """Her seyrek köke sade karşılık (Zeki AI). Bir kökün çağrısı düşerse o kökte `suggestion_error` yazılır, kalanlar
    sürer; hiçbir öneri metne kendiliğinden girmez."""
    from ..llm import PromptRef
    band_txt = f"{band[0]}-{band[1]} yaş" if band else "belirtilmemiş"
    sem = asyncio.Semaphore(PARALLEL)
    stats = {"asked": len(words), "failed": 0, "empty": 0}
    ref = PromptRef("studio_age_synonyms", "1")

    async def one(g):
        async with sem:
            try:
                out, _ = await llm.chat(SYN, [{"role": "user", "content": _syn_prompt(band_txt, g)}], schema=SYN_SCHEMA,
                                        prompt=ref, pages=sorted({p["page_no"] for p in g["pages"]}), max_tokens=600,
                                        temperature=0.0, thinking=False)
                g["suggestion"] = _clean_syn(g, out)
                if not any(g["suggestion"]["by_form"].values()):
                    stats["empty"] += 1
            except Exception:  # noqa: BLE001 - bir kök kaybolursa sayılır, rapor sürer
                stats["failed"] += 1
                g["suggestion"] = None
                g["suggestion_error"] = "Öneri alınamadı; raporu yeniden çıkarınca tekrar denenir."
            if progress:
                progress()
    await asyncio.gather(*(one(g) for g in words))
    return stats


# ====================================================================== okul / MEB ölçütleri
# Kaynaklar (bağlantı ve madde metni: docs/analiz/meb-uygunluk-olcutleri.md). Ekranda ve PDF'te bu adlarla görünür.
SOURCES = {
    "OKY": {"title": "Millî Eğitim Bakanlığı Okul Kütüphaneleri Yönetmeliği (RG 23.11.2024/32731)",
            "url": "https://www.lexpera.com.tr/resmi-gazete/metin/milli-egitim-bakanligi-okul-kutuphaneleri-yonetmeligi-32731"},
    "KLV": {"title": "Okul Kütüphaneleri Yönetmeliği Uygulama Kılavuzu (MEB, 2025)",
            "url": "https://www.meb.gov.tr/meb_iys_dosyalar/2025_10/22121751_Okul_Kutuphaneleri_Yonetmelik_Uygulama_Kilavuzu.pdf"},
    "DKY": {"title": "MEB Ders Kitapları ve Eğitim Araçları Yönetmeliği (RG 14.10.2021/31628)",
            "url": "https://www.resmigazete.gov.tr/eskiler/2021/10/20211014-1.htm"},
    "KRT": {"title": "TTKB, taslak ders kitapları ve eğitim araçlarının incelenmesinde değerlendirmeye esas kriterler "
                     "ve açıklamaları (Kurul mütalaası 15.10.2024)",
            "url": "https://ttkb.meb.gov.tr/meb_iys_dosyalar/2024_10/15183917_tymm_kriter_ve_aciklamalari.pdf"},
    "TDP": {"title": "Türkçe Dersi Öğretim Programı (MEB, 2019): ders kitaplarına alınacak metinlerin nitelikleri",
            "url": "https://mufredat.meb.gov.tr/Dosyalar/20195716392253-02-T%C3%BCrk%C3%A7e%20%C3%96%C4%9Fretim%20Program%C4%B1%202019.pdf"},
    "TEM": {"title": "TEGM duyurusu: 100 Temel Eser listeleri uygulamadan kaldırıldı (2018/17 sayılı Genelge)",
            "url": "https://tegm.meb.gov.tr/www/ogrencilerimize-okuma-aliskanligi-kazandirmak-amaciyla-ilkogretim-ve-ortaogretim-ogrencileri-icin-tavsiye-niteliginde-belirlenen-100-temel-eser-listeleri-uygulamadan-kaldirilmistir/icerik/557"},
    "MUZ": {"title": "1117 sayılı Küçükleri Muzır Neşriyattan Koruma Kanunu",
            "url": "https://www.mevzuat.gov.tr/MevzuatMetin/1.3.1117.pdf"},
    "KYT": {"title": "MEB Okul Öncesi Eğitim ve İlköğretim Kurumları Yönetmeliği (ilkokula kayıt: 69 ay)",
            "url": "https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=19942&MevzuatTur=7&MevzuatTertip=5"},
}

# Editör kontrol listesi: otomatik denetlenemeyen maddeler. Metin kaynağın ifadesine yakın; kaynak/madde yanında.
CHECKLIST = [
    ("amac", "Türk millî eğitiminin genel amaçlarına ve temel ilkelerine uygun", "OKY m.10/1-a, m.10/4; KLV 2.2"),
    ("deger", "Millî, manevi, kültürel, ahlaki ve insani değerlere uygun", "OKY m.10/1-c; KLV 2.2"),
    ("kisilik", "Beden, zihin, ahlak, ruh ve duygu bakımından dengeli ve sağlıklı kişiliği destekler", "OKY m.10/1-ç; KLV 2.2"),
    ("turkce", "Türkçenin doğru ve güzel kullanımını; okuma, dinleme, anlama, konuşma ve yazma becerilerini destekler",
     "OKY m.10/1-d; KLV 2.2; KRT 6.1–6.3"),
    ("dusunme", "Eleştirel, analitik ve özgün düşünmeyi destekler", "OKY m.10/1-e; KLV 2.2"),
    ("okuryazarlik", "Görsel, dijital ve medya okuryazarlığını destekler", "OKY m.10/1-f; KLV 2.2"),
    ("esitlik", "Eşitlikçi ve kapsayıcı; kişi ve toplulukları aşağılayan, dışlayan, etiketleyen ifade ve kadın-erkek "
                "kalıp yargısı yok", "KRT 1.3.1–1.3.4"),
    ("engelli", "Engelli bireyler hakkında genelleme yapan, onları kısıtlamalarla tanımlayan ifade ve görsel yok", "KRT 1.3.5"),
    ("cocuk_haklari", "Çocuk haklarına (yaşama, gelişim, korunma, katılım) aykırı yazılı ya da görsel unsur yok", "KRT 1.3.7"),
    ("rol_modeli", "Yaşa ve gelişim seviyesine uygun olmayan rol modeli, ürün, sembol, imge (yazıda ve resimlerde) yok",
     "KRT 1.5.1"),
    ("saglik", "Fiziksel gelişimi ve beden sağlığını olumsuz etkileyecek öğe yok", "KRT 1.5.2"),
    ("argo", "Argo ve küfür, olumsuz örnek oluşturabilecek davranış yok (otomatik hassas içerik taraması yardımcıdır, "
             "yerine geçmez)", "TDP madde 9; KRT 1.5.1"),
    ("reklam", "Lehte ya da aleyhte reklam, ticari yönlendirme ya da çağrışım yok", "KRT 1.7.1"),
    ("telif", "Alıntı ve atıflar telif mevzuatına uygun, kaynak gösterilmiş", "KRT 1.8.1"),
    ("kisisel_veri", "Kimliği belirli ya da belirlenebilir gerçek kişiyle ilişkilendirilebilecek kişisel veri yok", "KRT 1.6.1"),
    ("cevre", "Çevre bilincine ve hayvan haklarına aykırı yazılı ya da görsel unsur yok", "KRT 1.9.1, 1.9.3"),
    ("muzir", "On sekiz yaşından küçüklerin maneviyatına zararlı (muzır) içerik yok", "MUZ m.1"),
]

# Ders kitabı punto alt sınırı (DKY m.8/6; KRT 7.5.4): sınıf → punto. Okul kütüphanesi kitabı için bağlayıcı değildir;
# rapor bilgi olarak verir.
PUNTO_MIN = {1: 20, 2: 18, 3: 14, 4: 12, 5: 11}
PUNTO_UPPER = 10                   # 5. sınıftan yukarı
MEB_PHRASE = re.compile(r"(?<![^\W\d_])M\.?\s?E\.?\s?B\.?\s*(?:['’]?(?:in|ın))?\s*tavsiye|Mill[iî]\s+Eğitim\s+Bakanlığı\s*"
                        r"(?:['’]?nca|['’]?nın)?\s*tavsiye|100\s*Temel\s*Eser|Yüz\s+Temel\s+Eser", re.I)
_CAPS = re.compile(r"(?<![^\W\d_])[A-ZÇĞİÖŞÜÂÎÛ]{2,}(?![^\W\d_])")


def grade_for(age_min: int) -> int | None:
    """Bandın en küçük okurunun bulunabileceği en alt sınıf. İlkokula eylül sonunda 69 ayını dolduran çocuk
    kaydolur (KYT): 6 yaşındaki (72–83 ay) çocuk 1. sınıftadır, 7 yaşındaki 1. ya da 2. sınıfta — punto için
    küçük sınıf (büyük punto) alınır. 6 yaşından küçük: okul öncesi, ders kitabı kuralı yok."""
    if age_min < 6:
        return None
    return max(1, age_min - 6)


def auto_checks(d: Path, pages: list[dict], band, findings: list[dict], words: list[dict], wstats: dict) -> list[dict]:
    """Otomatik denetlenebilen ölçütler. Durum: ok | warn | info. Editörün «sorun değil» dediği bulgu hükümde düşülür
    (`verdict`); buradaki sayılar raporun çıktığı andır."""
    from . import plan as plan_mod
    out = []
    pl, spec = plan_mod.load(d), studio.read(d, "spec.json") or {}
    long_n = sum(f["kind"] == "LONG_SENTENCE" for f in findings)
    hard_n = sum(f["kind"] == "HARD_PAGE" for f in findings)
    sens = [f for f in findings if f["kind"] == "SENSITIVE"]
    ref_key, _ = reference_for(band)
    book = next((f for f in findings if f["kind"] == "BOOK_MEASURES"), None)
    harder = (book or {}).get("details", {}).get("harder") or []
    if band is None:
        age_detail = "Hedef yaş belirtilmemiş; banda göre değerlendirilemedi."
    elif ref_key is None:
        age_detail = (f"{band[0]}–{band[1]} yaş için yayımlanmış kitaplardan ölçülmüş karşılaştırma derlemi yok; "
                      "metin ölçüldü, banda göre yargılanmadı.")
    else:
        age_detail = (f"Kitap geneli {ref_key} yaş kitaplarıyla karşılaştırıldı" +
                      (f"; {len(harder)} okunabilirlik ölçüsünde bant kitaplarının %95'inden zor." if harder
                       else "; bant kitaplarının olağan aralığında.") +
                      f" Zor sayfa: {hard_n}.")
    out.append({"id": "yas", "title": "Öğrencilerin yaş ve gelişim düzeyine uygun (okunabilirlik)",
                "source": "OKY m.10/1-b; KLV 1.4, 2.2", "kinds": ["HARD_PAGE"],
                "status": "info" if ref_key is None else ("warn" if harder or hard_n else "ok"), "detail": age_detail})
    out.append({"id": "cumle", "title": "Akıcılığı bozacak uzun cümle yok", "source": "KRT 6.3.2", "kinds": ["LONG_SENTENCE"],
                "status": "info" if ref_key is None else ("warn" if long_n else "ok"),
                "detail": (f"{long_n} cümle, bant kitaplarındaki cümlelerin %99'undan uzun." if ref_key
                           else "Banda göre eşik yok (karşılaştırma derlemi yok).")})
    if wstats.get("reference"):
        p95 = wstats.get("rare_share_p95")
        over = p95 is not None and wstats.get("rare_share", 0) > p95
        out.append({"id": "kelime", "title": "Söz varlığı okurun seviyesine uygun", "source": "KRT 6.1.1; OKY m.10/1-b",
                    "kinds": [], "status": "warn" if over else ("info" if words else "ok"),
                    "detail": (f"{len(words)} kök bu yaş için yayımlanmış {wstats['books']} kitabın en çok "
                               f"{wstats['K']} tanesinde geçiyor (seyrek); içerik sözcükleri içindeki payı "
                               f"{_pc(wstats['rare_share'])}. "
                               + ("Bu pay bant kitaplarının %95'inden yüksek." if over else
                                  "Bu pay bant kitaplarının olağan aralığında."))})
    else:
        out.append({"id": "kelime", "title": "Söz varlığı okurun seviyesine uygun", "source": "KRT 6.1.1; OKY m.10/1-b",
                    "kinds": [], "status": "info",
                    "detail": "Bu yaş bandı için kelime derlemi yok; seyrek kelime listesi çıkarılmadı."})
    warn_s = sum(f["severity"] == "WARN" for f in sens)
    out.append({"id": "hassas", "title": "Korku, şiddet, hakaret, aşağılama, cinsel içerik ve bağımlılığı özendiren öğe yok",
                "source": "KRT 1.5.1; TDP madde 9; MUZ m.1", "kinds": ["SENSITIVE"],
                "status": "warn" if warn_s else ("info" if sens else "ok"),
                "detail": (f"{len(sens)} pasaj editörün dikkatine ({warn_s} yüksek olasılıklı)." if sens
                           else "Hassas içerik adayı bulunmadı (sözlük + Zeki AI sınıflaması).")})
    # punto (ders kitabı kuralı; bilgi)
    body = (pl or {}).get("page", {}).get("body_size") or spec.get("body_size")
    sizes = [x for pg in (pl or {}).get("pages", []) for x in [((pg.get("text") or {}).get("size"))] if x]
    smallest = min([body] + sizes) if body else None
    g = grade_for(band[0]) if band else None
    punto = {"id": "punto", "title": "Metin puntosu sınıf düzeyine uygun (ders kitabı ölçütü)",
             "source": "DKY m.8/6; KRT 7.5.4; KYT", "kinds": []}
    if g is None or smallest is None:
        out.append({**punto, "status": "info",
                    "detail": ("Okul öncesi yaş ya da hedef yaş yok: yönetmelikte karşılığı yok." if smallest
                               else "Punto bilgisi yok.")})
    else:
        need = PUNTO_MIN.get(g, PUNTO_UPPER)
        out.append({**punto, "status": "ok" if smallest >= need else "warn",
                    "detail": (f"En küçük metin puntosu {smallest:g}; {band[0]} yaşındaki okurun bulunabileceği en alt "
                               f"sınıf {g}. sınıf, ders kitabında en az {need} punto. Okul kütüphanesi kitabı için "
                               "bağlayıcı değildir.")})
    # iki yana yaslama
    nos = {p["pid"]: p["page_no"] for p in pages if p["pid"]}
    just = [p for p in (pl or {}).get("pages", []) if (p.get("text") or {}).get("align") == "justify"]
    if pl is not None:
        jd = (f"{len(just)} sayfada metin iki yana yaslı." if just else "Hiçbir sayfada iki yana yaslama yok.")
    else:
        jd = "Metin iki yana yaslı dizildi." if spec.get("justify") else "Metin sola dayalı dizildi."
    out.append({"id": "yaslama", "title": "Otomatik tam bloklama (iki yana yaslama) yok (ders kitabı ölçütü)",
                "source": "KRT 7.5.4", "kinds": [], "status": "warn" if (just or (pl is None and spec.get("justify"))) else "ok",
                "detail": jd, "pages": [{"page_no": nos.get(p["id"]), "pid": p["id"]} for p in just]})
    # vurgu için büyük harf (başlık ve ses sözcüğü dışında)
    caps = []
    for p in pages:
        paras, _ = age_fit.story_paragraphs(p)
        for para in paras:
            for m in _CAPS.finditer(para):
                caps.append({"page_no": p["page_no"], "pid": p["pid"], "word": m.group(0)})
    if pl is not None:          # planda ses sözcüğü bloğu vurgunun kendisidir, sayılmaz
        sound = {W.lower_tr(w) for pg in pl["pages"] for b in (pg.get("text") or {}).get("blocks", [])
                 if b.get("kind") == "sound" for w in T.words("".join(r.get("text", "") for r in b.get("runs", [])))}
        caps = [c for c in caps if W.lower_tr(c["word"]) not in sound]
    out.append({"id": "buyuk_harf", "title": "Vurgu için büyük harf kullanılmamış (ders kitabı ölçütü)", "source": "KRT 7.5.4",
                "kinds": [], "status": "info" if caps else "ok",
                "detail": (f"{len(caps)} yerde tamamı büyük harfli sözcük (kısaltma da olabilir; editör bakar)." if caps
                           else "Metinde tamamı büyük harfli sözcük yok."), "pages": caps})
    # «MEB tavsiyeli» / «100 Temel Eser» ibaresi
    hits = []
    for p in pages:
        for s in p["spans"]:
            for m in MEB_PHRASE.finditer(s["text"]):
                hits.append({"page_no": p["page_no"], "pid": p["pid"], "word": m.group(0)})
    fr = studio.read(d, "front.json") or {}
    for row in fr.get("kunye") or []:
        t = " ".join(str(x) for x in row) if isinstance(row, (list, tuple)) else str(row)
        for m in MEB_PHRASE.finditer(t):
            hits.append({"page_no": None, "pid": None, "word": m.group(0), "where": "künye"})
    out.append({"id": "meb_ibare", "title": "«MEB tavsiyeli» ya da «100 Temel Eser» ibaresi yok", "source": "TEM",
                "kinds": [], "status": "warn" if hits else "ok",
                "detail": ("Metinde/künyede ibare var; 100 Temel Eser listeleri 2018'de kaldırıldı, kaldırılma "
                           "gerekçelerinden biri izinsiz «MEB tavsiyeli» ibaresiydi." if hits
                           else "Metinde ve künyede böyle bir ibare yok."),
                "pages": hits})
    # yapay zekâ ile üretilen görsel (ders kitabı ölçütü: beyan)
    st = studio.studio_state(d)
    made = sum(1 for pg in st.get("pages", {}).values() if pg.get("selected"))
    figs = sum(1 for a in ((pl or {}).get("assets") or {}).values() if a.get("kind") == "figure")
    out.append({"id": "yz_beyan", "title": "Yapay zekâ ile üretilen içerik beyan edilmiş (ders kitabı ölçütü)",
                "source": "KRT 1.8.3", "kinds": [], "status": "info" if (made or figs) else "ok",
                "detail": (f"Kitapta Zeki AI ile üretilmiş {made} resim ve {figs} figür var; ders kitabında kaynakçada "
                           "«Yapay zekâ tarafından üretilmiştir.» ibaresi istenir." if (made or figs)
                           else "Zeki AI ile üretilmiş görsel yok.")})
    return out


# ====================================================================== rapor
def _fid(f: dict) -> str:
    k = json.dumps([(f.get("details") or {}).get("kind"), f.get("page"), f.get("quote") or "", f.get("message")],
                   ensure_ascii=False)
    return hashlib.sha1(k.encode()).hexdigest()[:12]


def _message(f: dict, ref_key: str | None) -> str:
    """Ekrana giden cümle: formül adı yok (ölçüler raporun ekinde, kaynaklarıyla)."""
    d = f.get("details") or {}
    if d.get("kind") == "HARD_PAGE":
        return (f"Sayfa metni {ref_key} yaş için yayımlanmış kitapların sayfalarının %99'undan zor: okunabilirlik "
                f"ölçülerinin {len(d.get('exceeds') or [])}'i bant eşiğini aşıyor (ortalama cümle "
                f"{d['measures']['asl']} kelime).")
    if d.get("kind") == "BOOK_MEASURES":
        m = d.get("measures") or {}
        return (f"Kitap geneli: {m.get('words')} kelime, {m.get('sentences')} cümle; ortalama cümle {m.get('asl')} kelime, "
                f"kelime başına {m.get('asw')} hece; konuşma payı {_pc(m.get('dialogue_share') or 0, 0)}.")
    return f["message"]


_PID = f"{time.time():.0f}-{id(object())}"
_running: set[str] = set()
_run_lock = threading.Lock()


def status(d: Path) -> dict:
    s = studio.read(d, STATUS) or {"state": "none"}
    if s.get("state") == "running" and d.name not in _running and time.time() - s.get("started", 0) > 60:
        s = {**s, "state": "failed", "error": "Koşu yarıda kaldı (servis yeniden başladı); raporu yeniden çıkarın."}
    return s


def claim(d: Path, by: str) -> bool:
    """Koşuyu başlatma hakkı (işte aynı anda tek koşu)."""
    with _run_lock:
        if d.name in _running:
            return False
        _running.add(d.name)
    studio.write(d, STATUS, {"state": "running", "by": by, "started": time.time(), "pid": _PID, "step": "Metin okunuyor",
                             "done": 0, "total": 0})
    return True


async def run(d: Path, by: str, llm=None) -> dict:
    """Raporu çıkarır (model çağrıları gateway üzerinden, kaydı işin provenance.jsonl'ına). `claim` önce alınmış olmalı."""
    try:
        return await _run(d, by, llm)
    except Exception:
        import traceback
        (d / "hata-yas-raporu.txt").write_text(traceback.format_exc())
        studio.write(d, STATUS, {"state": "failed", "by": by, "finished": time.time(),
                                 "error": "Rapor çıkarılamadı; Zeki AI'ye ulaşılamamış olabilir. Tekrar deneyin."})
        raise
    finally:
        with _run_lock:
            _running.discard(d.name)


async def _run(d: Path, by: str, llm) -> dict:
    t0 = time.time()
    st = {"state": "running", "by": by, "started": t0, "pid": _PID, "step": "", "done": 0, "total": 0}

    def step(name, done=None, total=None):
        st["step"] = name
        if done is not None:
            st["done"] = done
        if total is not None:
            st["total"] = total
        studio.write(d, STATUS, st)

    if llm is None:
        from .run import FileLlm
        llm = FileLlm(d / "provenance.jsonl")
    step("Metin okunuyor")
    pages, src = await asyncio.to_thread(job_pages, d)
    band, band_src = band_of(d)
    child = band is None or band[0] < ADULT
    ref_key, _ = reference_for(band)
    findings, rstats = await asyncio.to_thread(age_fit.readability, pages, band)
    sstats: dict = {"skipped": "çocuk/genç kitabı değil"}
    if child:
        step("Hassas içerik taranıyor")
        sens, sstats = await age_fit.sensitive(None, pages, band, llm=llm)
        findings += sens
    words, wstats = [], {"reference": None, "skipped": "çocuk/genç kitabı değil"}
    syn_stats: dict = {}
    if child:
        step("Kelime düzeyi ölçülüyor")
        words, wstats = await asyncio.to_thread(rare_words, pages, band)
        n = {"i": 0}

        def tick():
            n["i"] += 1
            step("Sade karşılıklar hazırlanıyor", n["i"], len(words))
        step("Sade karşılıklar hazırlanıyor", 0, len(words))
        syn_stats = await suggest(words, band, llm, tick)
    at_page = {p["page_no"]: p for p in pages}
    out_f = []
    for f in findings:
        det = f.get("details") or {}
        if det.get("kind") == "NO_BAND":
            continue
        pg = at_page.get(f.get("page"))
        out_f.append({"id": _fid(f), "kind": det.get("kind"), "severity": f["severity"], "page_no": f.get("page"),
                      "pid": pg["pid"] if pg else None, "label": pg["label"] if pg else None,
                      "quote": f.get("quote"), "message": _message(f, ref_key), "suggestion": f.get("suggestion"),
                      "details": det})
    for g in words:
        for p in g["pages"]:
            pg = at_page.get(p["page_no"])
            p["pid"], p["label"] = (pg["pid"], pg["label"]) if pg else (None, None)
    checks = await asyncio.to_thread(auto_checks, d, pages, band, out_f, words, wstats) if child else []
    title = studio.title_of(d)
    rep = {"version": VERSION, "at": time.time(), "by": by, "seconds": round(time.time() - t0, 1), "title": title,
           "text_hash": text_hash(pages), "text_source": src, "band": list(band) if band else None,
           "band_source": band_src, "child": child, "reference": ref_key,
           "reference_books": REFERENCE[ref_key]["books"] if ref_key else None,
           "pages": [{"page_no": p["page_no"], "pid": p["pid"], "label": p["label"]} for p in pages],
           "readability": {k: rstats.get(k) for k in ("book", "book_percentile_in_band", "pages_measured",
                                                      "dropped_paragraphs")},
           "findings": out_f, "words": words, "word_stats": wstats, "synonym_stats": syn_stats,
           "sensitive_stats": {k: v for k, v in sstats.items() if k != "results"},
           "checks": checks}
    studio.write(d, REPORT, rep)
    studio.write(d, STATUS, {"state": "done", "by": by, "started": t0, "finished": time.time()})
    return rep


# ---------------------------------------------------------------------- editör kararları
FINDING_STATES = ("dismissed", "fix")        # sorun değil | düzeltilecek
WORD_STATES = ("approved", "rejected")
CHECK_STATES = ("ok", "not_ok")
_ITEM = re.compile(r"[\w'’ -]{1,80}")


def decisions(d: Path) -> dict:
    return studio.read(d, DECISIONS) or {"finding": {}, "word": {}, "check": {}, "log": []}


def decide(d: Path, kind: str, item: str, state: str | None, by: str, note: str = "", choice: dict | None = None) -> dict:
    """Editör kararı; boş `state` kararı geri alır. Her karar günlüğe de yazılır (silinmez)."""
    allowed = {"finding": FINDING_STATES, "word": WORD_STATES, "check": CHECK_STATES}.get(kind)
    if allowed is None:
        raise ValueError("bilinmeyen karar türü")
    if state is not None and state not in allowed:
        raise ValueError("geçersiz karar")
    if kind == "check" and item not in {c[0] for c in CHECKLIST}:
        raise ValueError("kontrol listesinde böyle madde yok")
    if not _ITEM.fullmatch(item or ""):
        raise ValueError("geçersiz kayıt")
    note = " ".join((note or "").split())[:500]
    with _run_lock:
        dec = decisions(d)
        rec = {"state": state, "note": note, "by": by, "at": time.time()}
        if kind == "word" and choice:
            rec["choice"] = {W.lower_tr(str(k))[:80]: " ".join(str(v).split())[:80] for k, v in choice.items()
                             if str(v).strip()}
        if state is None:
            dec[kind].pop(item, None)
        else:
            old = dec[kind].get(item) or {}
            if "applied" in old:
                rec["applied"] = old["applied"]
            dec[kind][item] = rec
        dec["log"].append({"kind": kind, "item": item, **rec})
        studio.write(d, DECISIONS, dec)
    return dec


_UP = str.maketrans({"i": "İ", "ı": "I"})


def _cap(w: str) -> str:
    return w[:1].translate(_UP).upper() + w[1:]


def _word_re(form: str) -> re.Pattern:
    alts = sorted({form, _cap(form)}, key=len, reverse=True)
    return re.compile(r"(?<![^\W\d_])(" + "|".join(re.escape(a) for a in alts) + r")(?![^\W\d_])")


def replace_in_plan(plan: dict, form: str, to: str) -> tuple[int, list[str]]:
    """Sayfa planının yazı bloklarında ve balonlarında `form` biçimini `to` ile değiştirir (büyük harfle başlayan
    büyük harfle kalır). Dönen: (değişen yer, değişen sayfa kimlikleri)."""
    rx = _word_re(form)

    def sub(m):
        return _cap(to) if m.group(1)[:1].isupper() else to
    n, changed = 0, []
    for pg in plan["pages"]:
        hit = False
        for b in (pg.get("text") or {}).get("blocks", []):
            for r in b.get("runs") or []:
                new, k = rx.subn(sub, r["text"])
                if k:
                    r["text"], n, hit = new, n + k, True
        for bb in pg.get("bubbles") or []:
            new, k = rx.subn(sub, bb.get("text") or "")
            if k:
                bb["text"], n, hit = new, n + k, True
        if hit:
            changed.append(pg["id"])
    return n, changed


def apply_word(d: Path, lemma: str, form: str, to: str, by: str) -> dict:
    """Onaylanan karşılığı sayfa planının metnine uygular (bütün sayfalarda o biçim). Plan yoksa hata: metin sayfa
    düzeni ekranında değiştirilir. Plan sürümü artar (sürüm geçmişinden geri alınabilir)."""
    from . import plan as plan_mod
    form, to = W.lower_tr(form.strip()), " ".join(to.split())
    rec = decisions(d)["word"].get(lemma) or {}
    if rec.get("state") != "approved":
        raise ValueError("Önce öneriyi onaylayın.")
    if not form or not to or len(to) > 80:
        raise ValueError("Karşılık boş olamaz.")
    box: dict = {}

    def fn(plan):
        n, changed = replace_in_plan(plan, form, to)
        if not n:
            raise ValueError("Bu biçim metinde bulunamadı (sayfa düzeninde değişmiş olabilir).")
        box["pages"] = changed
        return n

    _plan, n = plan_mod.mutate(d, None, by, f"yaş raporu: «{form}» → «{to}»", fn)
    with _run_lock:
        dec = decisions(d)
        w = dec["word"].setdefault(lemma, {"state": "approved", "by": by, "at": time.time()})
        w.setdefault("applied", []).append({"form": form, "to": to, "count": n, "pages": box["pages"], "by": by,
                                            "at": time.time()})
        dec["log"].append({"kind": "word_apply", "item": lemma, "form": form, "to": to, "count": n, "by": by,
                           "at": time.time()})
        studio.write(d, DECISIONS, dec)
    return {"count": n, "pages": box["pages"]}


# ---------------------------------------------------------------------- görünüm (ekran, PDF, ön kontrol)
LEVELS = {
    "uygun": "Uygun", "sinirda": "Sınırda", "uyumsuz": "Uyumsuz", "belirtilmemis": "Hedef yaş belirtilmemiş",
    "degerlendirilemedi": "Banda göre değerlendirilemedi", "cocuk_degil": "Çocuk/genç kitabı değil",
}


def _page_txt(f: dict) -> str:
    return f.get("label") or (f"{f['page_no']}. sayfa" if f.get("page_no") else "kitap geneli")


def _nkey(s: str):
    m = re.match(r"(\d+)", s)
    return (int(m.group(1)) if m else 10**9, s)


def verdict(rep: dict, dec: dict) -> dict:
    """Bant uyumu, gerekçesiyle. Editörün «sorun değil» dediği bulgu sayılmaz; «düzeltilecek» dediği sayılır (metin
    değişip rapor yeniden çıkarılınca kendiliğinden düşer).
    - uyumsuz: açık yüksek olasılıklı hassas içerik (KRT 1.5.1 «bulunmamalıdır»);
    - sınırda: açık uzun cümle / zor sayfa, kitap geneli bant kitaplarının %95'inden zor, seyrek kelime payı bant
      kitaplarının %95'inden yüksek, ya da açık düşük olasılıklı hassas pasaj;
    - uygun: hiçbiri yok. Bant yoksa ya da derlemi yoksa bu adla söylenir."""
    if not rep.get("child"):
        return {"level": "cocuk_degil", "label": LEVELS["cocuk_degil"],
                "reasons": [f"Hedef yaş {rep['band'][0]}–{rep['band'][1]}: on sekiz yaşından küçükler için olan ölçütler "
                            "uygulanmadı."]}
    fd = dec.get("finding", {})
    open_f = [f for f in rep["findings"] if (fd.get(f["id"]) or {}).get("state") != "dismissed"]
    sens_w = [f for f in open_f if f["kind"] == "SENSITIVE" and f["severity"] == "WARN"]
    sens_i = [f for f in open_f if f["kind"] == "SENSITIVE" and f["severity"] != "WARN"]
    longs = [f for f in open_f if f["kind"] == "LONG_SENTENCE"]
    hards = [f for f in open_f if f["kind"] == "HARD_PAGE"]
    book = next((f for f in rep["findings"] if f["kind"] == "BOOK_MEASURES"), None)
    harder = ((book or {}).get("details") or {}).get("harder") or []
    ws = rep.get("word_stats") or {}
    rare_over = ws.get("rare_share_p95") is not None and ws.get("rare_share", 0) > ws["rare_share_p95"]
    reasons = []
    if sens_w:
        reasons.append(f"{len(sens_w)} pasajda bu yaş için dikkat gerektiren içerik (yüksek olasılık): "
                       + ", ".join(sorted({_page_txt(f) for f in sens_w}, key=_nkey)) + ".")
    if longs:
        reasons.append(f"{len(longs)} cümle bu yaş kitaplarındaki cümlelerin %99'undan uzun.")
    if hards:
        reasons.append(f"{len(hards)} sayfanın metni bu yaş kitaplarının sayfalarının %99'undan zor.")
    if harder:
        reasons.append(f"Kitap geneli {len(harder)} okunabilirlik ölçüsünde bu yaş kitaplarının %95'inden zor.")
    if rare_over:
        reasons.append(f"Seyrek kelime payı ({_pc(ws['rare_share'])}) bu yaş kitaplarının %95'inden yüksek.")
    if sens_i:
        reasons.append(f"{len(sens_i)} pasaj editörün bakması için işaretli (korku, yas ya da düşük olasılık).")
    if rep.get("band") is None:
        level = "belirtilmemis"
        reasons.insert(0, "Kitabın hedef yaşı belirtilmemiş; okunabilirlik ve kelime düzeyi banda göre yargılanmadı.")
    elif sens_w:
        level = "uyumsuz"
    elif rep.get("reference") is None:
        level = "degerlendirilemedi"
        reasons.insert(0, f"{rep['band'][0]}–{rep['band'][1]} yaş için yayımlanmış kitaplardan ölçülmüş karşılaştırma "
                          "yok; metin ölçüldü ama banda göre yargılanmadı.")
    elif longs or hards or harder or rare_over or sens_i:
        level = "sinirda"
    else:
        level = "uygun"
        reasons.append(f"Cümle uzunluğu, sayfa okunabilirliği ve kelime düzeyi {rep['reference']} yaş için yayımlanmış "
                       f"{rep.get('reference_books')} kitabın olağan aralığında; açık hassas içerik adayı yok.")
    return {"level": level, "label": LEVELS[level], "reasons": reasons}


def view(d: Path) -> dict:
    """Ekranın gördüğü: rapor + kararlar + karar sonrası hüküm + metin rapordan sonra değişti mi + koşu durumu."""
    rep = studio.read(d, REPORT)
    st = status(d)
    dec = decisions(d)
    out = {"status": {k: v for k, v in st.items() if k != "pid"}, "report": None, "sources": SOURCES,
           "checklist": [{"id": i, "title": t, "source": s, "decision": dec["check"].get(i)} for i, t, s in CHECKLIST]}
    if rep is None:
        return out
    pages, _ = job_pages(d)
    rep["stale"] = text_hash(pages) != rep["text_hash"]
    # sayfa sırası rapordan sonra değişmiş olabilir: kimlikle güncel sayfa numarası; silinen sayfa işaretlenir
    now = {p["pid"]: p for p in pages if p["pid"]}
    for f in rep["findings"]:
        f["decision"] = dec["finding"].get(f["id"])
        if f.get("pid"):
            if f["pid"] in now:
                f["label"] = now[f["pid"]]["label"]
            else:
                f["removed"] = True
    for g in rep["words"]:
        g["decision"] = dec["word"].get(g["lemma"])
        for p in g["pages"]:
            if p.get("pid") in now:
                p["label"] = now[p["pid"]]["label"]
    for c in rep.get("checks") or []:
        for p in c.get("pages") or []:
            if p.get("pid") in now:
                p["label"] = now[p["pid"]]["label"]
    rep["verdict"] = verdict(rep, dec)
    out["report"] = rep
    return out


def preflight_line(d: Path) -> dict:
    """Ön kontrol satırı: bilgi düzeyinde, baskıyı durdurmaz (OK ya da WARN; hiçbir zaman FAIL)."""
    name = "Yaş uygunluğu"
    v = view(d)
    rep = v["report"]
    if rep is None:
        return {"name": name, "status": "OK", "detail": "Rapor henüz çıkarılmadı (Sayfa stüdyosu → Yaş uygunluğu)."}
    vd = rep["verdict"]
    detail = vd["label"] + (f": {vd['reasons'][0]}" if vd["reasons"] else "")
    if rep.get("stale"):
        detail += " Metin rapordan sonra değişti; raporu yenileyin."
    open_checks = sum(1 for c in v["checklist"] if not c["decision"])
    if rep.get("child") and open_checks:
        detail += f" Editör kontrol listesinde {open_checks} madde işaretlenmedi."
    return {"name": name, "status": "WARN" if vd["level"] in ("sinirda", "uyumsuz") else "OK", "detail": detail[:600]}


# ---------------------------------------------------------------------- PDF (Typst)
KIND_TR = {"LONG_SENTENCE": "Uzun cümle", "HARD_PAGE": "Zor sayfa", "SENSITIVE": "Hassas içerik"}
CATEGORY_TR = {"VIOLENCE": "şiddet", "FEAR": "korku", "UNSAFE_IMITABLE": "taklit edilebilir tehlike",
               "SUBSTANCE": "madde kullanımı", "DEATH_GRIEF": "ölüm/yas", "INSULT_DISCRIMINATION": "aşağılama/ayrımcılık",
               "SEXUAL": "cinsellik"}
STATE_TR = {"dismissed": "Sorun değil", "fix": "Düzeltilecek", "approved": "Onaylandı", "rejected": "Reddedildi",
            "ok": "Uygun", "not_ok": "Uygun değil"}


def _when(t) -> str:
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(t)) if t else ""


def _dec_txt(x: dict | None) -> str:
    return f"{STATE_TR.get(x['state'], x['state'])} · {x['by']} · {_when(x['at'])}" if x else ""


def pdf_data(v: dict) -> dict:
    rep = v["report"]
    book = next((f for f in rep["findings"] if f["kind"] == "BOOK_MEASURES"), None)
    rows = sorted((f for f in rep["findings"] if f["kind"] != "BOOK_MEASURES"),
                  key=lambda f: (f.get("page_no") or 0, f["kind"]))
    return {
        "title": rep.get("title") or "", "at": _when(rep["at"]), "printed": _when(time.time()),
        "band": (f"{rep['band'][0]}–{rep['band'][1]} yaş" if rep.get("band") else "belirtilmemiş"),
        "band_source": rep.get("band_source") or "", "stale": bool(rep.get("stale")),
        "verdict": rep["verdict"], "book": _message(book, rep.get("reference")) if book else "",
        "findings": [{"page": _page_txt(f), "kind": KIND_TR.get(f["kind"], f["kind"])
                      + (f" ({CATEGORY_TR.get((f.get('details') or {}).get('category'), '')})" if f["kind"] == "SENSITIVE"
                         else ""),
                      "severity": f["severity"], "message": f["message"], "quote": f.get("quote") or "",
                      "suggestion": f.get("suggestion") or "", "decision": _dec_txt(f.get("decision"))} for f in rows],
        "words": [{"lemma": g["lemma"], "books": g["df"],
                   "pages": ", ".join(dict.fromkeys(p.get("label") or str(p["page_no"]) for p in g["pages"])),
                   "forms": ", ".join(g["forms"]), "meaning": (g.get("suggestion") or {}).get("meaning") or "",
                   "options": "; ".join(f"{f} → {', '.join(o)}"
                                        for f, o in ((g.get("suggestion") or {}).get("by_form") or {}).items() if o),
                   "decision": _dec_txt(g.get("decision")),
                   "applied": "; ".join(f"{a['form']} → {a['to']} ({a['count']} yer)"
                                        for a in (g.get("decision") or {}).get("applied", []))}
                  for g in rep["words"]],
        "word_stats": {k: v2 for k, v2 in (rep.get("word_stats") or {}).items() if k != "unknown"},
        "reference_books": rep.get("reference_books"), "reference": rep.get("reference"),
        "checks": [{"title": c["title"], "source": c["source"], "status": c["status"], "detail": c["detail"]}
                   for c in rep["checks"]],
        "checklist": [{"title": c["title"], "source": c["source"], "state": (c["decision"] or {}).get("state") or "",
                       "decision": _dec_txt(c["decision"]), "note": (c["decision"] or {}).get("note") or ""}
                      for c in v["checklist"]],
        "measures": ((book or {}).get("details") or {}).get("measures") or {},
        "percentile": ((book or {}).get("details") or {}).get("percentile_in_band") or {},
        "sources": [{"key": k, **s} for k, s in SOURCES.items()],
    }


def pdf(d: Path) -> Path:
    """Raporun indirilebilir PDF'i (templates/age_report.typ). Rapor ve kararlar aynıysa var olan döner."""
    v = view(d)
    if v["report"] is None:
        raise FileNotFoundError("rapor yok")
    import shutil

    import pymupdf
    import typst

    from .preflight import brand
    out_dir = d / PDF_DIR
    out_dir.mkdir(exist_ok=True)
    data = pdf_data(v)
    key = hashlib.sha256(json.dumps({**data, "printed": ""}, ensure_ascii=False, sort_keys=True,
                                    default=str).encode()).hexdigest()[:16]
    path = out_dir / f"yas-raporu-{key}.pdf"
    if path.exists():
        return path
    for old in out_dir.glob("yas-raporu-*.pdf"):
        old.unlink()
    shutil.copy(TEMPLATE, out_dir / TEMPLATE.name)
    (out_dir / "data.json").write_text(json.dumps(data, ensure_ascii=False, default=str))
    tmp = out_dir / "yas-raporu.tmp.pdf"
    typst.compile(str(out_dir / TEMPLATE.name), output=str(tmp), root=str(out_dir), font_paths=[str(studio.fonts())],
                  ignore_system_fonts=True, sys_inputs={"data": "data.json"})
    doc = pymupdf.open(tmp)
    brand(doc)
    doc.save(path)
    doc.close()
    tmp.unlink(missing_ok=True)
    return path


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4 and sys.argv[1] == "vocab":
        print(json.dumps(build_vocab(sys.argv[2], sys.argv[3]), ensure_ascii=False, indent=1))
    else:
        print("kullanım: python -m editor.production.age_report vocab <derlem kökü> <çıktı.json.gz>")
