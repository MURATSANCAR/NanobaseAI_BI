"""Sesli okumada ifade katmanı: cümle başına ifade (ton, hız, duraklama) ve vurgulanacak kelime.

Kullanıcı kararı (2026-09-27): «Zeki AI metni önceden okuyup her cümleyi işaretler: heyecan, merak, korku, neşe,
fısıltı, üzüntü, ya da vurgulanacak kelime. Ses bu işaretle o cümleyi farklı tonda, hızda ve duraklamayla okur.
Editör işareti ekranda cümle cümle değiştirebilir.»

Ölçüm ve seçim: docs/analiz/sesli-okuma-ifade-katmani.md. Özet: seslendirme modeli ton talimatını yalnız
**referans-yalnız klonda** dinler (tam klonda — referans sesi + metni, devam kipi — talimatı sesli okuyor, harf
hatası %45–111); hızı talimatla değiştirmiyor (±%6), hız üretim sonrası perdeyi koruyan zaman esnetmeyle verilir;
vurgu talimatı kelimeyi öne çıkarmıyor (bkz. `EMPHASIS`).

Cümle: sayfa planındaki okuma biriminin (yazı bloğu, balon, serbest yazı) cümlesi; sınır sesli okumanın parça
sınırıyla aynıdır (okunuşu . ! ? … ile biten kelime; `narration.pieces`). Kimlik `<blok id>:<cümle sırası>`; kayıt
cümlenin metin parmak izini taşır, metin değişince o cümlenin işareti düşer (nötr okunur, ekranda «metin değişti»).

Kayıt iş klasöründe `ses/ifade.json`:
    {"version": 1, "pages": {<pid>: {"sentences": {<blok:i>: {label, emphasis: [kelime], source: ai|editor,
     by, at, fp, probs?}}, "suggested": {by, at, seconds}}}}
Sayfa sesi `narration.page_input`'taki kancayla ifadeyi okur: ifade değişen sayfanın sesi «güncel değil» olur, yalnız o
sayfa yeniden seslendirilir. Kelime zamanları yine hizalayıcıdan gelir (değişmez).

Zeki AI önerisi (`suggest`): ana model (`book-director`, `FileLlm` → işin `provenance.jsonl`'u), kitaba özel istem
yok. Etiket kapalı küme: cümle başına tek harf (A–I) + harflerin olasılığı (`Llm.choose`, vLLM structured choice +
logprobs); seçeneklerin sırası değiştirilerek iki okuma, olasılıklar ortalanır. En olası etiket `MIN_PROB`'un altında
ya da nötrün önünde `MARGIN`'dan az ise nötr. Vurgu: üç bağımsız okuma (yapılandırılmış çıktı), en az ikisinde geçen
ve cümlede birebir bulunan kelime kalır.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from . import narration as N

FILE = "ifade.json"
VERSION = 1
LABELS = ("notr", "heyecan", "merak", "korku", "nese", "fisilti", "uzuntu", "ofke", "saskinlik")
LABEL_TR = {"notr": "Nötr", "heyecan": "Heyecan", "merak": "Merak", "korku": "Korku", "nese": "Neşe",
            "fisilti": "Fısıltı", "uzuntu": "Üzüntü", "ofke": "Öfke", "saskinlik": "Şaşkınlık"}
LABEL_NOTE = {"notr": "düz anlatım", "heyecan": "canlı, hızlı, yükselen", "merak": "soru tonu, düşünceli",
              "korku": "gergin, kısık", "nese": "gülümseyen, sıcak", "fisilti": "alçak, yumuşak, yavaş",
              "uzuntu": "alçak, yavaş, ağır", "ofke": "sert, kararlı", "saskinlik": "şaşıran, yükselen"}

# ------------------------------------------------------------------ etiket → üretim (tek tablo; ölçümle ayarlandı)
# style: modele giden ton talimatı (İngilizce; referans-yalnız klonda metnin başına «(…)»). rate: konuşma hızı
# (üretim sonrası zaman esnetme; > 1 hızlı). before_ms: cümleden önce sessizlik. after: cümle sonu duraklamasının
# çarpanı (noktalamaya göre olan `narration.PAUSE` üzerinden). Değerler ve ölçüm tablosu
# docs/analiz/sesli-okuma-ifade-katmani.md; kitaba özel değil.
TABLE: dict[str, dict] = {
    "notr":      {"style": None, "rate": 1.0, "before_ms": 0, "after": 1.0},
    "heyecan":   {"style": "excited and energetic, rising pitch", "rate": 1.08, "before_ms": 0, "after": 0.8},
    "merak":     {"style": "curious and wondering, questioning intonation", "rate": 0.96, "before_ms": 120, "after": 1.3},
    "korku":     {"style": "scared, trembling, tense hushed voice", "rate": 0.94, "before_ms": 250, "after": 1.3},
    "nese":      {"style": "cheerful and happy, smiling voice", "rate": 1.04, "before_ms": 0, "after": 0.9},
    "fisilti":   {"style": "whispering, very soft and breathy", "rate": 0.9, "before_ms": 300, "after": 1.4},
    "uzuntu":    {"style": "sad, slow, low and soft voice", "rate": 0.88, "before_ms": 150, "after": 1.5},
    "ofke":      {"style": "angry, stern and firm voice", "rate": 1.04, "before_ms": 0, "after": 0.9},
    "saskinlik": {"style": "surprised and astonished", "rate": 1.0, "before_ms": 200, "after": 1.2},
}
# Vurgu: hedef kelimeden önce kısa duraklama (okunuş metninde «…»); talimatla vurgu ölçümde kelimeyi öne çıkarmadı.
EMPHASIS = {"method": "pause", "mark": "..."}

MIN_PROB = 0.5            # en olası ifade bundan düşükse nötr
MARGIN = 0.15             # nötrün önünde bundan az farkla öndeyse nötr
EMPH_READS = 3            # vurgu okuması sayısı
EMPH_AGREE = 2            # kelime en az bu kadar okumada geçmeli
PROMPT_LABEL = ("studio_expression_label", "1")
PROMPT_EMPH = ("studio_expression_emphasis", "1")


# ------------------------------------------------------------------ cümleler
def fp(text: str) -> str:
    """Cümle metninin parmak izi (boşluk farkı sayılmaz)."""
    return hashlib.sha256(re.sub(r"\s+", " ", text.strip()).encode()).hexdigest()[:12]


def unit_sentences(u) -> list[list[int]]:
    """Birimin cümleleri: kelime sıraları; sınır sesli okumanın parça sınırıyla aynı (okunuşu . ! ? … ile biten)."""
    out, cur = [], []
    for k, w in enumerate(u.words):
        cur.append(k)
        sp = w.spoken.rstrip()
        if sp[-1:] in ".!?…":
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [s for s in out if any(u.words[k].say for k in s)]


def core(word: str) -> str:
    """Kelimenin çekirdeği (baştaki/sondaki noktalama ve tırnak atılır)."""
    return N._split_punct(word)[1].rstrip(".") if word else ""


def sentences(d: Path, pg: dict) -> list[dict]:
    """Sayfanın cümleleri okuma sırasıyla: {key, block, i, kind, speaker, voice, text, words: [çekirdek], fp}."""
    units = N.page_units(pg, N.settings_of(d), N.lexicon(d))
    out = []
    for u in units:
        for i, ks in enumerate(unit_sentences(u)):
            a, b = u.words[ks[0]].start, u.words[ks[-1]].end
            text = u.text[a:b]
            out.append({"key": f"{u.id}:{i}", "block": u.id, "i": i, "kind": u.kind, "speaker": u.speaker,
                        "voice": u.voice, "text": text, "words": [core(u.words[k].text) for k in ks], "fp": fp(text)})
    return out


# ------------------------------------------------------------------ kayıt
def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _path(d: Path) -> Path:
    return d / N.DIR / FILE


def store(d: Path) -> dict:
    p = _path(d)
    return json.loads(p.read_text()) if p.exists() else {"version": VERSION, "pages": {}}


def _save(d: Path, s: dict) -> None:
    N._write(N.ses_dir(d) / FILE, s)


def page_marks(d: Path, pid: str) -> dict:
    """Sayfanın geçerli işaretleri: {anahtar: kayıt}; metni değişmiş cümlenin kaydı dışarıda kalır."""
    return (store(d).get("pages", {}).get(pid) or {}).get("sentences") or {}


def clean_emphasis(words: list[str], sentence_words: list[str]) -> list[str]:
    """Vurgu kelimeleri cümlede birebir (çekirdek, büyük/küçük harf dahil) olmalı; yoksa atılır. Sıra cümledeki sıra."""
    want = {core(str(w).strip()) for w in words if str(w).strip()}
    seen, out = set(), []
    for w in sentence_words:
        if w in want and w not in seen:
            out.append(w)
            seen.add(w)
    return out


def view(d: Path, pid: str) -> dict:
    """Ekran: cümleler + işaret (geçerli ya da metni değiştiği için düşmüş) + tablo."""
    from . import plan as plan_mod
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    pg = plan_mod._page(pl, pid)
    marks = page_marks(d, pid)
    sug = (store(d).get("pages", {}).get(pid) or {}).get("suggested")
    rows = []
    for s in sentences(d, pg):
        m = marks.get(s["key"])
        ok = bool(m) and m.get("fp") == s["fp"]
        rows.append({**{k: s[k] for k in ("key", "block", "i", "kind", "speaker", "voice", "text", "words")},
                     "label": m["label"] if ok else "notr", "emphasis": m.get("emphasis", []) if ok else [],
                     "source": m.get("source") if ok else None, "by": m.get("by") if ok else None,
                     "at": m.get("at") if ok else None, "probs": m.get("probs") if ok else None,
                     "dropped": bool(m) and not ok})
    status = next((r for r in N.status(d) if r["id"] == pid), None)
    return {"page": pid, "no": plan_mod.page_no(pl, pid), "sentences": rows, "suggested": sug,
            "narration": status, "labels": [{"id": k, "label": LABEL_TR[k], "note": LABEL_NOTE[k]} for k in LABELS]}


def set_marks(d: Path, pid: str, items: list[dict], by: str) -> dict:
    """Editörün işaretleri (yalnız verilen cümleler değişir). Nötr + vurgusuz = işaret kaldırılır."""
    from . import plan as plan_mod
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    pg = plan_mod._page(pl, pid)
    by_key = {s["key"]: s for s in sentences(d, pg)}
    s = store(d)
    page = s.setdefault("pages", {}).setdefault(pid, {"sentences": {}})
    marks = page.setdefault("sentences", {})
    for it in items:
        key, label = str(it.get("key", "")), str(it.get("label", "notr"))
        if key not in by_key:
            raise KeyError(key)
        if label not in LABELS:
            raise ValueError(f"Bilinmeyen ifade: {label}")
        sen = by_key[key]
        emph = clean_emphasis(list(it.get("emphasis") or []), sen["words"])
        bad = [w for w in (it.get("emphasis") or []) if core(str(w).strip()) not in emph]
        if bad:
            raise ValueError("Vurgulanacak kelime cümlede yok: " + ", ".join(map(str, bad)))
        old = marks.get(key)
        if old and old.get("fp") == sen["fp"] and old.get("label") == label and old.get("emphasis", []) == emph:
            continue
        marks[key] = {"label": label, "emphasis": emph, "source": "editor", "by": by, "at": _now(), "fp": sen["fp"]}
    # metni değişmiş cümlelerin eski kayıtları ve bu sayfada artık olmayan cümleler temizlenir
    for k in [k for k, m in marks.items() if k not in by_key or m.get("fp") != by_key[k]["fp"]]:
        marks.pop(k)
    _save(d, s)
    return view(d, pid)


# ------------------------------------------------------------------ üretime yansıma (narration.page_input kancası)
def _emphasize(text: str, words: list[str]) -> str:
    """Vurgulanacak kelimeden önce kısa duraklama işareti (okunuş metninde; hizalanan kelimeler değişmez). Kelime
    parçanın ilk kelimesiyse ya da önünde zaten duraklama (noktalama) varsa işaret eklenmez."""
    mark = EMPHASIS["mark"]
    for w in words:
        text = re.sub(rf"(?<=[^\s,;:.!?…])(\s+)({re.escape(w)})(?=[\s,;:.!?…'’]|$)", rf"{mark}\1\2", text, count=1)
    return text


def apply(d: Path, pg: dict, units: list, plist: list) -> tuple[list, list | None]:
    """Parçalara cümlenin ifadesini işler: `p.extra` (style, clone, rate, pause_before_ms), cümle sonu duraklaması ve
    vurgu. Dönen ikinci değer sayfa özetine (hash) girer; işaret yoksa None (eski sayfaların özeti değişmez)."""
    marks = page_marks(d, pg["id"])
    if not marks:
        return plist, None
    # birim → kelime → cümle sırası
    sent_of: dict[tuple[int, int], tuple[str, str, list[str]]] = {}
    for ui, u in enumerate(units):
        for i, ks in enumerate(unit_sentences(u)):
            a, b = u.words[ks[0]].start, u.words[ks[-1]].end
            info = (f"{u.id}:{i}", fp(u.text[a:b]), [core(u.words[k].text) for k in ks])
            for k in ks:
                sent_of[(ui, k)] = info
    sig, prev_key = [], None
    for j, p in enumerate(plist):
        info = sent_of.get((p.unit, p.words[0])) if p.words else None
        key, sfp, _ = info or (None, None, [])
        m = marks.get(key) if key else None
        if not m or m.get("fp") != sfp:
            sig.append(None)
            prev_key = key
            continue
        row = TABLE[m.get("label", "notr")] if m.get("label") in TABLE else TABLE["notr"]
        extra: dict = {}
        if row["style"]:
            extra.update(style=row["style"], clone="ref")
            if row["rate"] != 1.0:
                extra["rate"] = row["rate"]
            if row["before_ms"] and key != prev_key:
                extra["pause_before_ms"] = row["before_ms"]
        nxt = plist[j + 1] if j + 1 < len(plist) else None
        last_of_sentence = nxt is None or (sent_of.get((nxt.unit, nxt.words[0]))[0] if nxt.words else None) != key
        if last_of_sentence and row["after"] != 1.0:
            p.pause_ms = int(round(p.pause_ms * row["after"]))
        emph = [w for w in m.get("emphasis", []) if w]
        if emph:
            p.text = _emphasize(p.text, emph)
        p.extra = extra
        sig.append([m.get("label"), emph, extra, p.pause_ms])
        prev_key = key
    return plist, (sig if any(sig) else None)


# ------------------------------------------------------------------ Zeki AI önerisi
def _page_listing(rows: list[dict]) -> str:
    out = []
    for n, s in enumerate(rows, 1):
        who = f" ({s['speaker']} konuşuyor)" if s.get("speaker") else ""
        out.append(f"[{n}]{who} {s['text']}")
    return "\n".join(out)


def _label_prompt(listing: str, n: int, sentence: str, order: list[str]) -> str:
    opts = "\n".join(f"{chr(65 + i)}) {LABEL_TR[lab]} — {LABEL_NOTE[lab]}" for i, lab in enumerate(order))
    return (
        "Bir kitap sesli okunacak. Aşağıda bir sayfanın metni cümle cümle numaralı.\n"
        f"Seslendiren kişi [{n}] numaralı cümleyi hangi ifadeyle okumalı?\n"
        "Yalnız metne bak: cümlenin kendisi ve çevresi açıkça bir duygu ya da okuma biçimi göstermiyorsa «Nötr» seç. "
        "Konuşmayı aktaran kısım («dedi», «diye sordu») ve olay anlatımı genellikle nötrdür. Fısıltı yalnız metin "
        "fısıldandığını ya da sessiz konuşulduğunu söylüyorsa.\n\n"
        f"Sayfa:\n{listing}\n\nCümle [{n}]: «{sentence}»\n\nSeçenekler:\n{opts}\n\nYalnız seçeneğin harfini yaz."
    )


def _emph_prompt(listing: str) -> str:
    return (
        "Bir kitap sesli okunacak. Aşağıda bir sayfanın metni cümle cümle numaralı.\n"
        "Sesli okurken anlam için özellikle vurgulanması gereken kelime var mı? Çoğu cümlede vurgu gerekmez; yalnız "
        "cümlenin anlamını taşıyan, karşıtlık ya da şaşkınlık yaratan, okurun kaçırmaması gereken kelimeyi seç. "
        "Kelimeyi metinde geçtiği gibi (ekleriyle, büyük/küçük harfiyle) aynen yaz; vurgu gerekmeyen cümleyi yazma.\n\n"
        f"Sayfa:\n{listing}"
    )


EMPH_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {
    "items": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["n", "words"],
                                         "properties": {"n": {"type": "integer"},
                                                        "words": {"type": "array", "items": {"type": "string"}}}}}}}


def decide(probs: dict[str, float]) -> str:
    best = max(probs, key=probs.get)
    if best == "notr" or probs[best] < MIN_PROB or probs[best] - probs.get("notr", 0.0) < MARGIN:
        return "notr"
    return best


async def label_probs(llm, listing: str, n: int, sentence: str, page_no: int | None) -> dict[str, float]:
    """İki okuma (seçenek sırası düz ve ters), etiket olasılıkları ortalanır."""
    from ..llm import PromptRef
    ref = PromptRef(*PROMPT_LABEL)
    total = {lab: 0.0 for lab in LABELS}
    orders = [list(LABELS), list(reversed(LABELS))]
    for order in orders:
        letters = [chr(65 + i) for i in range(len(order))]
        probs, _ = await llm.choose("book-director", [{"role": "user", "content": _label_prompt(listing, n, sentence, order)}],
                                    letters, prompt=ref, pages=[page_no] if page_no else None)
        for i, lab in enumerate(order):
            total[lab] += probs.get(letters[i], 0.0) / len(orders)
    return total


async def emphasis_votes(llm, listing: str, rows: list[dict], page_no: int | None) -> dict[int, list[str]]:
    from ..llm import PromptRef
    ref = PromptRef(*PROMPT_EMPH)
    votes: dict[int, dict[str, int]] = {}
    for _ in range(EMPH_READS):
        out, _ = await llm.chat("book-director", [{"role": "user", "content": _emph_prompt(listing)}], prompt=ref,
                                schema=EMPH_SCHEMA, max_tokens=1200, temperature=0.7, thinking=False,
                                pages=[page_no] if page_no else None)
        seen: set[tuple[int, str]] = set()
        for it in (out or {}).get("items") or []:
            n = int(it.get("n") or 0)
            if not 1 <= n <= len(rows):
                continue
            for w in clean_emphasis(it.get("words") or [], rows[n - 1]["words"]):
                if (n, w) not in seen:
                    seen.add((n, w))
                    votes.setdefault(n, {})[w] = votes.setdefault(n, {}).get(w, 0) + 1
    return {n: [w for w, c in ws.items() if c >= EMPH_AGREE] for n, ws in votes.items()}


async def suggest(d: Path, pid: str, llm, by: str, replace_editor: bool = False) -> dict:
    """Zeki AI önerisi: sayfanın her cümlesine ifade + vurgu. Editörün işaretine dokunmaz (`replace_editor` hariç)."""
    from . import plan as plan_mod
    t0 = time.time()
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    pg = plan_mod._page(pl, pid)
    no = plan_mod.page_no(pl, pid)
    rows = sentences(d, pg)
    if not rows:
        return view(d, pid)
    listing = _page_listing(rows)
    labels = []
    for n, s in enumerate(rows, 1):
        probs = await label_probs(llm, listing, n, s["text"], no)
        labels.append((decide(probs), {k: round(v, 3) for k, v in probs.items() if v >= 0.005}))
    emph = await emphasis_votes(llm, listing, rows, no)
    s = store(d)
    page = s.setdefault("pages", {}).setdefault(pid, {"sentences": {}})
    marks = page.setdefault("sentences", {})
    for n, (row, (lab, probs)) in enumerate(zip(rows, labels), 1):
        old = marks.get(row["key"])
        if old and old.get("source") == "editor" and old.get("fp") == row["fp"] and not replace_editor:
            continue
        marks[row["key"]] = {"label": lab, "emphasis": emph.get(n, []), "source": "ai", "by": "Zeki AI", "at": _now(),
                             "fp": row["fp"], "probs": probs}
    keys = {r["key"]: r["fp"] for r in rows}
    for k in [k for k, m in marks.items() if keys.get(k) != m.get("fp")]:
        marks.pop(k)
    page["suggested"] = {"by": by, "at": _now(), "seconds": round(time.time() - t0, 1)}
    _save(d, s)
    return view(d, pid)


# ------------------------------------------------------------------ «bu cümleyi dinle»
async def sample_sentence(d: Path, pid: str, key: str, label: str, emphasis: list[str]) -> bytes:
    """Bir cümlenin kısa örneği, verilen (kaydedilmemiş olabilir) ifadeyle; ses ve okunuş başına bir kez üretilir,
    yayınevi düzeyinde saklanır (`_ses/ornek/`)."""
    import base64
    from . import plan as plan_mod
    if label not in LABELS:
        raise ValueError(f"Bilinmeyen ifade: {label}")
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    pg = plan_mod._page(pl, pid)
    units = N.page_units(pg, N.settings_of(d), N.lexicon(d))
    plist = N.pieces(units)
    target = None
    for ui, u in enumerate(units):
        for i, ks in enumerate(unit_sentences(u)):
            if f"{u.id}:{i}" == key:
                target = (ui, set(ks), [core(u.words[k].text) for k in ks])
    if target is None:
        raise KeyError(key)
    ui, ks, words = target
    emph = clean_emphasis(emphasis, words)
    mine = [p for p in plist if p.unit == ui and p.words and p.words[0] in ks]
    if not mine:
        raise ValueError("Okunacak metin yok")
    row = TABLE[label]
    segs = []
    for j, p in enumerate(mine):
        seg = {"text": _emphasize(p.text, emph) if emph else p.text, "voice": None,
               "pause_ms": 0 if j == len(mine) - 1 else p.pause_ms}
        if row["style"]:
            seg.update(style=row["style"], clone="ref", rate=row["rate"])
        segs.append((p.voice, seg))
    refs = {v: await N.voice_ref(v) for v in {v for v, _ in segs}}
    body = [{**seg, "voice": refs[v]} for v, seg in segs]
    k = N._hash({"v": N.VERSION, "x": VERSION, "seg": [{**b, "voice": hashlib.sha256(b["voice"]["ref_audio"].encode()).hexdigest()}
                                                         for b in body]})
    cache = N._root() / "ornek" / f"ifade-{k}.mp3"
    if cache.exists():
        return cache.read_bytes()
    out = await N._call({"segments": body, "format": "mp3", "align": False}, timeout=600)
    data = base64.b64decode(out["audio"])
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(cache)
    return data
