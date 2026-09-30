"""Sesli okumada ifade katmanı: cümle başına ifade (ton, hız, duraklama) ve vurgulanacak kelime.

Kullanıcı kararı (2026-09-27): «ZEKİ AI metni önceden okuyup her cümleyi işaretler: heyecan, merak, korku, neşe,
fısıltı, üzüntü, ya da vurgulanacak kelime. Ses bu işaretle o cümleyi farklı tonda, hızda ve duraklamayla okur.
Editör işareti ekranda cümle cümle değiştirebilir.»

Ölçüm ve seçim: docs/analiz/sesli-okuma-ifade-katmani.md. Özet:
- Tam klonda (referans sesi + metni, devam kipi; kitabın bugünkü okuması) ton talimatı metne girerse model talimatı
  **sesli okuyor** (harf hatası %45–111): bu yol kullanılmaz.
- Referans-yalnız klonda talimat dinleniyor ama ses kimliği kayıyor (talimatsız bile perde +%16, «aynı ses» dense de
  +%13–43) ve kısa parçada anlaşılırlık düşüyor. Yalnız fısıltıda kullanılır (gerçek fısıltı: enerji −15 dB, sesli
  oranı 0,89 → 0,68, uzun cümlede harf hatası 0).
- **İfade örneği**: aynı sesin referans cümlesi bir kez talimatla okunur (üç aday, ölçülüp seçilir; yayınevi düzeyinde
  saklanır), cümle tam klonla bu örneğin devamı olarak üretilir; kimlik referanstan, ton örnekten, talimat metne girmez.
  Uzun nötr cümlede ölçülü (heyecan perde +%15, merak/neşe +%12, üzüntü −9 dB hız −%22; harf hatası tabanla aynı) ama
  gerçek sayfanın ünlemli cümlesinde yükselen tonlar aştı (canlı erkek seslerde +%48–65, harf hatası %10–12). Üründe
  yalnız **üzüntü** bu yolla (alçalan ton, kısa cümlede de harf hatası tabanla aynı); yükselen tonlar hız ve duraklamayla.
- Kısa parçada (5 kelimeden az; «Yaşasın!», «Vak vak!») hiçbir yol güvenilir değil (perde ortalama +%40–50, en çok
  +%120; harf hatası 2–4 kat): orada ifade yalnız hız ve duraklamayla verilir, tonu metnin kendi noktalaması taşır.
- Hız talimatla değişmiyor (±%6): hız üretimden sonra perdeyi koruyan zaman esnetmeyle verilir.
- Vurgu talimatı kelimeyi öne çıkarmıyor; kelimeden önce kısa durak («...») çıkarıyor (bkz. `EMPHASIS`).

Cümle: sayfa planındaki okuma biriminin (yazı bloğu, balon, serbest yazı) cümlesi; sınır sesli okumanın parça
sınırıyla aynıdır (okunuşu . ! ? … ile biten kelime; `narration.pieces`). Kimlik `<blok id>:<cümle sırası>`; kayıt
cümlenin metin parmak izini taşır, metin değişince o cümlenin işareti düşer (nötr okunur, ekranda «metin değişti»).

Kayıt iş klasöründe `ses/ifade.json`:
    {"version": 1, "pages": {<pid>: {"sentences": {<blok:i>: {label, emphasis: [kelime], source: ai|editor,
     by, at, fp, probs?}}, "suggested": {by, at, seconds}}}}
Sayfa sesi `narration.page_input`'taki kancayla ifadeyi okur: ifade değişen sayfanın sesi «güncel değil» olur, yalnız o
sayfa yeniden seslendirilir. Kelime zamanları yine hizalayıcıdan gelir (değişmez).

ZEKİ AI önerisi (`suggest`): ana model (`book-director`, `FileLlm` → işin `provenance.jsonl`'u), kitaba özel istem
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
# Ekrandaki açıklama, sesin gerçekte ne yaptığını söyler (TABLE).
LABEL_NOTE = {"notr": "düz anlatım", "heyecan": "daha hızlı, kısa duraklar", "merak": "biraz yavaş, önce ve sonra durak",
              "korku": "yavaş, uzun duraklar", "nese": "biraz hızlı", "fisilti": "fısıltı: alçak, nefesli",
              "uzuntu": "alçak, ağır, yavaş", "ofke": "hızlı, kısa duraklar", "saskinlik": "önce durak, sonra uzun durak"}

# ------------------------------------------------------------------ etiket → üretim (tek tablo; ölçümle ayarlandı)
# method: ornek (ifade örneğinin devamı, tam klon) | talimat (referans-yalnız klon + talimat) | None (yalnız hız ve
# duraklama). style: talimat (İngilizce; örnek üretiminde ya da talimat yolunda metnin başına «(…)»). target: ifade
# örneği adayı seçiminde referansa göre hedef perde kayması (%) ve enerji farkı (dB). rate: konuşma hızı (sonradan
# zaman esnetme; > 1 hızlı). before_ms: cümleden önce sessizlik. after: cümle sonu duraklamasının çarpanı
# (noktalamaya göre olan `narration.PAUSE` üzerinden). Kitaba özel değil; ölçüm tablosu analiz belgesinde.
# Tonu yükselten ifadelerde (heyecan, neşe, şaşkınlık, merak, korku, öfke) ton verilmez: ifade örneği uzun nötr
# cümlede ölçülü çalıştı (perde +%11–15) ama gerçek sayfada ünlemli cümlede aştı (canlı erkek seslerde +%48–65,
# harf hatası %10–12; talimat yolu da kısa ünlemde +%40–50, en çok +%120). Bu ifadeler hız ve duraklamayla verilir.
TABLE: dict[str, dict] = {
    "notr":      {"method": None, "style": None, "rate": 1.0, "before_ms": 0, "after": 1.0},
    "heyecan":   {"method": None, "style": None, "rate": 1.08, "before_ms": 0, "after": 0.75},
    "merak":     {"method": None, "style": None, "rate": 0.96, "before_ms": 150, "after": 1.35},
    "korku":     {"method": None, "style": None, "rate": 0.94, "before_ms": 250, "after": 1.35},
    "nese":      {"method": None, "style": None, "rate": 1.04, "before_ms": 0, "after": 0.9},
    "fisilti":   {"method": "talimat", "style": "whispering, very soft and breathy",
                  "rate": 1.15, "before_ms": 300, "after": 1.4, "gain_db": -10.0, "gain_tone_db": -5.0},
    "uzuntu":    {"method": "ornek", "style": "sad, slow, low and soft voice",
                  "target": (-3, -5.0), "rate": 1.0, "before_ms": 200, "after": 1.5},
    "ofke":      {"method": None, "style": None, "rate": 1.05, "before_ms": 0, "after": 0.85},
    "saskinlik": {"method": None, "style": None, "rate": 1.0, "before_ms": 250, "after": 1.2},
}
MIN_STYLE_WORDS = 5       # bundan kısa parçada ton yok (yalnız hız/duraklama): kısa ünlemde ton güvenilmez
# İfade örneği adayları: üç tohum; kabul: harf hatası ≤ %6, perde kayması ±%30 içinde (ses kimliği). Hiçbiri tutmazsa
# o ses+ifade için ton verilmez (yalnız hız/duraklama) ve kayıtta nedeni yazar.
EXAMPLE_SEEDS = (11, 22, 33)
EXAMPLE_MAX_CER = 0.06
EXAMPLE_MAX_SHIFT = 30.0
# Vurgu: hedef kelimeden önce kısa durak; talimatla vurgu ölçümde kelimeyi öne çıkarmadı (enerji +0,8 dB, taban +1,1),
# duraklama çıkardı (+3,0 dB, perde +1,6 yarım ton, harf hatası %0,3). İşaret önce «...» idi; tam kitap dinlemesinde
# (2026-09-28, 1.392 kelime) durak 0,8–1,5 sn'ye uzayıp takılma gibi duyuldu (45 yer): virgülün kısa durağı yeter.
# Birleşik fiilin yardımcısı («yardım etmedi») ve büyük harfli başlık/bağırış içindeki kelime vurgulanmaz (bölünür);
# ZEKİ AI önerisinde cümle başına tek vurgu.
EMPHASIS = {"method": "pause", "mark": ","}
_AUX = re.compile(r"^(et|ed|eyle|ol|yap|kıl)(me|mi|mı|mek|mak|ti|tı|di|du|dı|ip|up|ıp|er|ar|ur|en|an|ecek|acak|eceğ|"
                  r"acağ|iyor|ıyor|uyor|ince|unca|ınca|erek|arak|il|ebil|abil|mez|maz|miş|mış|muş|sun|sın|se|sa)")
# Durak öbeği bölmesin (2026-09-28 ikinci dinleme: erkek seste virgül 0,7–0,8 sn; «en, korkak», «aslanın, kükremesiydi»,
# «dönmüştü, bile»): önündeki kelime niteleyici ya da tamlayan (-ın/-in…) ise, ya da kelimenin kendisi ilgeç/ek-kelimeyse
# vurgu durağı konmaz. Dil bilgisi; kitaptan bağımsız.
_MODIFIERS = {"en", "çok", "pek", "daha", "biraz", "hiç", "az", "ya", "o", "bu", "şu", "bir", "her", "hep", "ne", "tam",
              "gayet", "bayağı", "epey", "oldukça", "fazla", "kocaman", "küçücük", "bütün", "tüm"}
_PARTICLES = {"bile", "de", "da", "dahi", "mi", "mı", "mu", "mü", "ki", "gibi", "kadar", "için", "ile", "diye", "dek"}
_GENITIVE = re.compile(r"\w{2,}(ın|in|un|ün)$")
EMPH_AI_MAX = 1
RATE_MIN_WORDS = 5        # bundan kısa parçada hızlandırma yok: «O da ne!» 0,46 sn'de bitiyordu

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
    for k, _w in enumerate(u.words):
        cur.append(k)
        if N.sentence_mark(u.words, k):
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
def emph_ok(prev: str | None, word: str) -> bool:
    """Kelimeden önce vurgu durağı konabilir mi (öbeği bölmeden). `prev`: önceki kelimenin çekirdeği (yoksa None)."""
    c = N.tr_lower(word)
    if _AUX.match(c) or (len(word) > 1 and word.isupper()) or c in _PARTICLES:
        return False
    if prev is None:
        return True
    pv = N.tr_lower(prev)
    return pv not in _MODIFIERS and not _GENITIVE.match(pv)


def _emphasize(text: str, words: list[str]) -> str:
    """Vurgulanacak kelimeden önce kısa duraklama işareti (okunuş metninde; hizalanan kelimeler değişmez). Kelime
    parçanın ilk kelimesiyse, önünde zaten duraklama (noktalama) varsa ya da durak öbeği bölecekse (`emph_ok`)
    işaret eklenmez."""
    mark = EMPHASIS["mark"]
    toks = text.split(" ")
    for w in words:
        for i in range(1, len(toks)):
            if core(toks[i]) != core(w) or not toks[i].startswith(w):
                continue
            if toks[i - 1][-1:] in ",;:.!?…" or not toks[i - 1]:
                break
            if emph_ok(core(toks[i - 1]), core(w)):
                toks[i - 1] += mark
            break
    return " ".join(toks)


def _quoted(u) -> set[int]:
    """Birimde tırnak içindeki kelimelerin sıraları (konuşma). Düz tırnak (") aç/kapa sırasıyla."""
    out, inside = set(), False
    for k, w in enumerate(u.words):
        pre, _c, post = N._split_punct(w.text)
        if any(ch in "“«‘\"" for ch in pre):
            inside = True
        if inside:
            out.add(k)
        if any(ch in "”»’\"" for ch in post):
            inside = False
    return out


def apply(d: Path, pg: dict, units: list, plist: list) -> tuple[list, list | None]:
    """Parçalara cümlenin ifadesini işler (senkron; `narration.page_input` kancası): `p.extra` = {label, tone, rate,
    pause_before_ms} (tonu `prepare` servis gövdesine çevirir), cümle sonu duraklaması ve vurgu. Dönen ikinci değer
    sayfa özetine (hash) girer; işaret yoksa None (eski sayfaların özeti değişmez)."""
    marks = page_marks(d, pg["id"])
    if not marks:
        return plist, None
    sent_of: dict[tuple[int, int], tuple[str, str]] = {}          # (birim, kelime) → (cümle anahtarı, parmak izi)
    for ui, u in enumerate(units):
        for i, ks in enumerate(unit_sentences(u)):
            a, b = u.words[ks[0]].start, u.words[ks[-1]].end
            for k in ks:
                sent_of[(ui, k)] = (f"{u.id}:{i}", fp(u.text[a:b]))

    def key_of(p):
        return sent_of.get((p.unit, p.words[0]), (None, None)) if p.words else (None, None)

    quoted = [_quoted(u) for u in units]
    sent_words: dict[str, set[int]] = {}
    for (_ui, k), (key, _f) in sent_of.items():
        sent_words.setdefault(key, set()).add(k)
    sig, prev_key = [], None
    for j, p in enumerate(plist):
        key, sfp = key_of(p)
        m = marks.get(key) if key else None
        if not m or m.get("fp") != sfp:
            sig.append(None)
            prev_key = key
            continue
        label = m.get("label") if m.get("label") in TABLE else "notr"
        row = TABLE[label]
        # Konuşma içeren cümlede ifade konuşmanındır: anlatıcının tırnak dışındaki parçası nötr okunur (fısıltı
        # «İçinden bir ses fısıldıyordu:» kısmına da geçiyordu). Cümle sonu duraklaması yine uygulanır.
        q = quoted[p.unit]
        speech_only = bool(q & sent_words.get(key, set())) and not (q & set(p.words))
        extra: dict = {}
        if label != "notr" and not speech_only:
            words = sum(len(units[p.unit].words[k].say) for k in p.words)
            extra["label"] = label
            extra["tone"] = bool(row["method"]) and words >= MIN_STYLE_WORDS
            if row["rate"] != 1.0 and (row["rate"] < 1.0 or words >= RATE_MIN_WORDS):
                extra["rate"] = row["rate"]
            if row["before_ms"] and key != prev_key:
                extra["pause_before_ms"] = row["before_ms"]
            # Düzey (2026-09-28 ölçümü, docs/analiz/sesli-okuma-erkek-anlatici-ve-kisa-fisilti.md): talimat yolu 5+ kelimede
            # çoğu kez yalnız «alçak ses» veriyor (enerji −5…−6,5 dB; gerçek fısıltı −15 dB), kısa parçada ton hiç yok.
            # Üretimden sonra kısılır: tonlu parçada kalan fark, tonsuzda tamamı. Anlaşılırlığı değiştirmez.
            g = row.get("gain_tone_db") if extra["tone"] else row.get("gain_db")
            if g:
                extra["gain_db"] = g
        nxt = plist[j + 1] if j + 1 < len(plist) else None
        if (nxt is None or key_of(nxt)[0] != key) and row["after"] != 1.0:
            p.pause_ms = int(round(p.pause_ms * row["after"]))
        emph = [w for w in m.get("emphasis", []) if w]
        if m.get("source") == "ai":
            emph = emph[:EMPH_AI_MAX]
        if emph:
            p.text = _emphasize(p.text, emph)
        p.extra = extra
        sig.append([label, emph, extra, p.pause_ms, row.get("method"), row.get("style")])
        prev_key = key
    return plist, (sig if any(sig) else None)


async def prepare(body: dict, plist: list) -> None:
    """Servis gövdesine ifadeyi yazar (`narration.narrate_page` kancası; `apply`'dan sonra): tonlu parçada ifade örneği
    (`voice.prompt_audio`) ya da fısıltıda talimat (`style` + `clone: ref`); hız ve önceki duraklama her ifadeli
    parçada. Gövdedeki parçalar `plist` ile aynı sıradadır."""
    for p, seg in zip(plist, body["segments"]):
        ex = getattr(p, "extra", None)
        if not ex:
            continue
        row = TABLE[ex["label"]]
        if ex.get("tone"):
            voice = seg["voice"]
            if row["method"] == "ornek" and voice.get("ref_text"):
                ex_audio = await example(p.voice, ex["label"], voice)
                if ex_audio:
                    seg["voice"] = {**voice, "prompt_audio": ex_audio}
            elif row["style"]:
                # talimat yolu; metinsiz referanslı (yüklenmiş) ses zaten referans-yalnız klonla okunur
                seg.update(style=row["style"], clone="ref")
        for k in ("rate", "pause_before_ms", "gain_db"):
            if k in ex:
                seg[k] = ex[k]


def _example_dir(vid: str) -> Path:
    return N._root() / "ifade" / vid


def _wav_slices(data: bytes, spans: list[tuple[float, float]]) -> list[bytes]:
    import io
    import wave
    with wave.open(io.BytesIO(data)) as w:
        sr, sw, ch = w.getframerate(), w.getsampwidth(), w.getnchannels()
        frames = w.readframes(w.getnframes())
    out = []
    for a, b in spans:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as o:
            o.setnchannels(ch)
            o.setsampwidth(sw)
            o.setframerate(sr)
            o.writeframes(frames[int(a * sr) * sw * ch:int(b * sr) * sw * ch])
        out.append(buf.getvalue())
    return out


def pick_example(label: str, base: dict, cands: list[dict]) -> dict | None:
    """Adaylardan hedefe en yakını: harf hatası ≤ EXAMPLE_MAX_CER ve perde kayması ±EXAMPLE_MAX_SHIFT içinde."""
    tf0, tdb = TABLE[label]["target"]
    ok = []
    for c in cands:
        m = c["measure"]
        if not m.get("f0") or not base.get("f0") or m.get("cer", 1) > EXAMPLE_MAX_CER:
            continue
        shift = 100 * (m["f0"] / base["f0"] - 1)
        if abs(shift) > EXAMPLE_MAX_SHIFT:
            continue
        ddb = (m.get("energy_db") or 0) - (base.get("energy_db") or 0)
        ok.append((abs(shift - tf0) / 10 + abs(ddb - tdb) / 3, {**c, "shift": round(shift, 1), "ddb": round(ddb, 2)}))
    return min(ok, key=lambda t: t[0])[1] if ok else None


async def example(vid: str, label: str, ref: dict) -> str | None:
    """Sesin bu ifadedeki örneği (base64 WAV; yoksa None). Yayınevi düzeyinde bir kez: referans cümlesi talimatla üç
    tohumda okunur, ölçülür (servisin `measure`'ı), `pick_example` seçer; referans ya da talimat değişince yenilenir."""
    import base64
    row = TABLE[label]
    ref_sha = hashlib.sha256(ref["ref_audio"].encode()).hexdigest()[:16]
    dd = _example_dir(vid)
    meta_p, wav_p = dd / f"{label}.json", dd / f"{label}.wav"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else None
    if meta and meta.get("ref") == ref_sha and meta.get("style") == row["style"] and meta.get("version") == VERSION:
        return base64.b64encode(wav_p.read_bytes()).decode() if meta.get("chosen") and wav_p.exists() else None
    text = ref["ref_text"]
    segs = [{"text": text, "voice": ref, "pause_ms": 0, "clone": "full", "seed": N.REF_SEED}]
    segs += [{"text": text, "voice": {"ref_audio": ref["ref_audio"], "ref_text": text}, "pause_ms": 0, "clone": "ref",
              "style": row["style"], "seed": s} for s in EXAMPLE_SEEDS]
    out = await N._call({"segments": segs, "format": "wav", "align": False, "measure": True})
    parts = out["segments"]
    base = parts[0].get("measure") or {}
    cands = [{"seed": s, "measure": parts[i + 1].get("measure") or {}, "span": (parts[i + 1]["start"], parts[i + 1]["end"])}
             for i, s in enumerate(EXAMPLE_SEEDS)]
    best = pick_example(label, base, cands)
    dd.mkdir(parents=True, exist_ok=True)
    rec = {"version": VERSION, "voice": vid, "label": label, "style": row["style"], "ref": ref_sha, "base": base,
           "candidates": [{k: c[k] for k in ("seed", "measure")} for c in cands], "at": _now(),
           "chosen": {k: best[k] for k in ("seed", "shift", "ddb")} if best else None}
    if best:
        wav = _wav_slices(base64.b64decode(out["audio"]), [best["span"]])[0]
        tmp = wav_p.with_suffix(".tmp")
        tmp.write_bytes(wav)
        tmp.replace(wav_p)
    else:
        rec["reason"] = "Adayların hiçbiri anlaşılırlık ve ses kimliği sınırına uymadı; bu ifade yalnız hız ve duraklamayla."
    N._write(meta_p, rec)
    return base64.b64encode(wav_p.read_bytes()).decode() if best else None


# ------------------------------------------------------------------ ZEKİ AI önerisi
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
            sw = rows[n - 1]["words"]
            for w in clean_emphasis(it.get("words") or [], sw):
                k = sw.index(w)
                if not emph_ok(sw[k - 1] if k else None, w):     # üretimde uygulanmayacak vurgu kayda da girmez
                    continue
                if (n, w) not in seen:
                    seen.add((n, w))
                    votes.setdefault(n, {})[w] = votes.setdefault(n, {}).get(w, 0) + 1
    return {n: [w for w, c in ws.items() if c >= EMPH_AGREE] for n, ws in votes.items()}


async def suggest(d: Path, pid: str, llm, by: str, replace_editor: bool = False) -> dict:
    """ZEKİ AI önerisi: sayfanın her cümlesine ifade + vurgu. Editörün işaretine dokunmaz (`replace_editor` hariç)."""
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
        marks[row["key"]] = {"label": lab, "emphasis": emph.get(n, []), "source": "ai", "by": "ZEKİ AI", "at": _now(),
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
    for j, p in enumerate(mine):
        if emph:
            p.text = _emphasize(p.text, emph)
        if j == len(mine) - 1:
            p.pause_ms = 0
        extra: dict = {}
        if label != "notr":
            extra = {"label": label, "tone": bool(row["method"])
                     and sum(len(units[p.unit].words[k].say) for k in p.words) >= MIN_STYLE_WORDS}
            if row["rate"] != 1.0:
                extra["rate"] = row["rate"]
        p.extra = extra
    refs = {v: await N.voice_ref(v) for v in {p.voice for p in mine}}
    body = {"segments": [{"text": p.text, "voice": refs[p.voice], "pause_ms": p.pause_ms} for p in mine],
            "format": "mp3", "align": False}
    await prepare(body, mine)
    k = N._hash({"v": N.VERSION, "x": VERSION, "seg": [
        {**sg, "voice": hashlib.sha256(json.dumps(sg["voice"], sort_keys=True).encode()).hexdigest()} for sg in body["segments"]]})
    cache = N._root() / "ornek" / f"ifade-{k}.mp3"
    if cache.exists():
        return cache.read_bytes()
    out = await N._call(body, timeout=600)
    data = base64.b64decode(out["audio"])
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(cache)
    return data
