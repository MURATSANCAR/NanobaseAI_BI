"""Uyarlama: kitaptan TV çizgi filmi bölümü (2026-10-08, kullanıcı: «gerçek çizgi film gibi, kitaba bağlı, uzun»).

script.write kitabı çekim çekim «okuyordu» (anlatım dış sesle, çekimler eşit uzunlukta): sesli kitap gibiydi. Uyarlama
iki aşamalıdır ve sadakati kodla denetler:

1. Olay örgüsü (beat listesi, istem `production_film_adapt_outline`): kitabın her cümlesi sırayla tam bir beat'e
   bağlanır; kapsama `COVERAGE_MIN` altındaysa ya da sıra bozuksa yeniden istenir.
2. Sahne sahne çekim listesi (istem `production_film_adapt_scene`): kitaptaki her konuşma bir karakterin ağzından
   kelimesi kelimesine; anlatım canlandırılır (iç ses yalnız gerektiğinde); eklenen kısa tepkiler `added` ile
   işaretli ve sınırlı. Çekim 1,5–6 sn, tepki çekimleri, kamera dili.

Kurallar kitaptan bağımsızdır (cümle bölme, konuşma tanıma `shoot.is_speech`); kitaba özel ad/eşik yoktur.
Çıktı script.SCHEMA ile aynı yapıdadır (çekime `beat`, satıra `added` eklenir): hattın geri kalanı değişmeden çalışır.
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import marketing as mk
from .. import studio
from . import spec, store
from . import script as script_mod

OUTLINE_PROMPT = "production_film_adapt_outline"
SCENE_PROMPT = "production_film_adapt_scene"
ATTEMPTS = 4
COVERAGE_MIN = 0.9            # kitabın (≥3 kelimelik) cümlelerinin en az bu kadarı bir beat'e bağlı
ADDED_MAX = 0.25              # eklenen satırların bütün satırlara oranı
ADDED_WORDS = 4               # eklenen satır en çok bu kadar kelime
SHOT_MIN, SHOT_MAX = 1.5, 6.0
PURPOSES = ("kanca", "isim", "olay", "tepki", "saka", "doruk", "kapanis")

_STR = {"type": "string"}
OUTLINE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["title", "logline", "cast", "beats"],
    "properties": {
        "title": _STR, "logline": _STR,
        "cast": spec.SCHEMA["properties"]["cast"],
        "beats": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["scene", "setting", "setting_en", "time", "purpose", "summary", "sentences", "seconds"],
            "properties": {
                "scene": {"type": "number"}, "setting": _STR, "setting_en": _STR,
                "time": {"type": "string", "enum": list(spec.TIMES)},
                "purpose": {"type": "string", "enum": list(PURPOSES)},
                "summary": _STR, "sentences": {"type": "array", "items": {"type": "number"}},
                "seconds": {"type": "number"}}}}}}

_SHOT_ITEM = spec.SCHEMA["properties"]["scenes"]["items"]["properties"]["shots"]["items"]
_LINE = {**_SHOT_ITEM["properties"]["lines"]["items"]}
_LINE = {**_LINE, "required": [*_LINE["required"], "added"],
         "properties": {**_LINE["properties"], "added": {"type": "boolean"}}}
SCENE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["shots"],
    "properties": {"shots": {"type": "array", "minItems": 1, "items": {
        **_SHOT_ITEM, "required": [*_SHOT_ITEM["required"], "beat"],
        "properties": {**_SHOT_ITEM["properties"], "beat": {"type": "number"},
                       "lines": {"type": "array", "items": _LINE}}}}}}

_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")


# Hikâyeden sonra gelen etkinlik/soru bölümü (çocuk kitaplarında yaygın): ilk işaretten sonrası hikâye değildir.
# 2026-10-08: «Aşağıdaki soruları hikâyeye göre cevaplayınız.» kitabın son cümlesi sanılıp filmin son repliği olmuştu.
_BACKMATTER = re.compile(r"^\s*(?:aşağıdaki\s+soru|sorular\s*$|etkinlik|soruları\s+.*cevaplayınız|"
                         r"haydi\s+cevaplayalım|okuduğunu\s+anlama)", re.I | re.M)


def story_text(text: str) -> str:
    """Kitap metninin hikâye kısmı: etkinlik/soru bölümü ve ayraçlar («* * *») düşer."""
    m = _BACKMATTER.search(text)
    t = text[:m.start()] if m else text
    return re.sub(r"(?m)^\s*(?:\*\s*){2,}\s*$", "", t).strip()


def sentences(text: str) -> list[str]:
    """Kitap metni → cümleler (en az 3 kelime; başlık ve tek kelimelik satırlar düşer). Konuşma tireleri korunur."""
    out = []
    for s in _SPLIT.split(story_text(text)):
        s = s.strip()
        if spec.words(s) >= 3:
            out.append(s)
    return out


def _n(s: str) -> str:
    return re.sub(r"\W+", " ", mk.norm(mk.clean_quote(s)).casefold()).strip()


_TAG = re.compile(r"[,!?…]?\s*\b(?:diye|de(?:d|r)i|dedi[mk]?|diyordu[mk]?|diyor\w*|sordu|bağırdı|seslendi)\b.*$",
                  re.I)
_QUOTED = re.compile(r"[«\"“]([^»\"”]{2,})[»\"”]")
_MARKS = ("-", "–", "—", "«", '"', "“")


def speech_lines(book: str) -> list[str]:
    """Kitaptaki konuşmalar, cümle cümle: tire/tırnakla başlayan cümle, «…: - söz» biçimi ya da «…, dedi» etiketli
    cümle; önceki cümle «:» ile bitiyorsa da konuşma. Etiket düşer: «Ressam olacak benim oğlum, diyordu.» →
    «Ressam olacak benim oğlum». Komşu cümleye taşmaz (2026-10-08: «İçeri girmek istedim. Ama Mert sinirle: - Appi
    diiiiit, diye bağırdı.» bütünüyle konuşma sanılıyordu)."""
    out, prev = [], ""
    for s in (x.strip() for x in _SPLIT.split(story_text(book))):
        if not s:
            continue
        after_colon = prev.rstrip().endswith(":")
        prev = s
        if s.endswith(":") and spec.words(s) <= 4:
            continue                                   # «Annem:» konuşmacı satırı
        quoted = _QUOTED.findall(s)
        if quoted and not s.lstrip().startswith(_MARKS):
            out += [mk.clean_quote(q).strip(" ,") for q in quoted]
            continue
        if ":" in s:
            core = s.rsplit(":", 1)[1].strip()
        elif s.lstrip().startswith(_MARKS) or after_colon or _TAG.search(s):
            core = s
        else:
            continue
        core = mk.clean_quote(_TAG.sub("", core).strip()).strip(" ,")
        if spec.words(core) >= 1:
            out.append(core)
    return out


def narration_of(quoted: list[str]) -> list[str]:
    """Kitap cümlelerinden konuşma olmayanlar (anlatım)."""
    talk = [_n(q) for q in speech_lines("\n".join(quoted))]
    return [q for q in quoted if not any(t and t in _n(q) for t in talk)]


def scene_problems(shots: list[dict], quoted: list[str], scene_sec: float, last: str | None = None) -> list[str]:
    """Bir sahnenin çekim listesi: kitaptaki konuşmalar kelimesi kelimesine, iç ses oranı, kitabın son cümlesi,
    ekleme sınırı, süre."""
    probs = []
    lines = [ln for s in shots for ln in s.get("lines", [])]
    spoken = " | ".join(_n(ln.get("text", "")) for ln in lines)
    narr = narration_of(quoted)
    kept = [q for q in narr if _n(q) and _n(q) in spoken]
    if len(narr) >= 3 and len(kept) > NARR_MAX * len(narr):
        probs.append(f"Anlatım cümlelerinin {len(kept)}/{len(narr)} tanesi iç seste: bu sesli kitaba döner. En "
                     f"önemli üçte biri–yarısı kalsın (en çok {int(NARR_MAX * len(narr))}), gerisini oyna.")
    if len(narr) >= 2 and len(kept) < NARR_MIN * len(narr):
        probs.append(f"Anlatım cümlelerinin yalnız {len(kept)}/{len(narr)} tanesi iç seste; en önemlilerinden (geçiş, "
                     "duygu, espri) en az üçte birini anlatıcının ağzından kelimesi kelimesine söylet.")
    if last and not any(_n(x) in spoken for x in (speech_lines(last) or [last])):
        probs.append(f"Kitabın son cümlesi bölümün son satırı olmalı, kelimesi kelimesine: «{last}»")
    probs += [f"Kitaptaki konuşma eksik ya da değişmiş: «{q}»" for q in speech_lines("\n".join(quoted))
              if _n(q) not in spoken]
    added = [ln for ln in lines if ln.get("added")]
    if len(added) > max(1, ADDED_MAX * len(lines)):
        probs.append(f"Eklenen satır {len(added)}/{len(lines)}; en çok %{ADDED_MAX * 100:.0f}. Ekleme yerine "
                     "sessiz tepki çekimi (yüz ifadesi, beden dili) kullan.")
    probs += [f"Eklenen satır en çok {ADDED_WORDS} kelime: «{ln.get('text')}»" for ln in added
              if spec.words(ln.get("text", "")) > ADDED_WORDS]
    long = [i for i, s in enumerate(shots, 1) if float(s.get("seconds") or 0) > SHOT_MAX + 1]
    if long:
        probs.append(f"{', '.join(map(str, long))}. çekim {SHOT_MAX:.0f} sn'den uzun: böl (genel plan + yakın + tepki); "
                     "çizgi filmde çekim 1,5–6 sn.")
    total = sum(float(s.get("seconds") or 0) for s in shots)
    if total < 0.85 * scene_sec:
        probs.append(f"Sahne {total:.0f} sn; hedef {scene_sec:.0f} sn. Kısaltma: sözsüz hareket, tepki ve geçiş "
                     "çekimleri ekle (beat başına 2–4 çekim).")
    return probs


NARR_MIN = 0.25              # kitabın anlatım cümlelerinin en az bu kadarı iç ses olarak kalır (çocuk izleyici takip etsin)
NARR_MAX = 0.6               # en çok bu kadarı: fazlası sesli kitaba döner (2026-10-08: 38/53 satır anlatımdı)


def check_outline(out: dict, sents: list[str], target: int) -> list[str]:
    """Olay örgüsünün sadakati: her cümle bir kez ve sırayla; kapsama; süre; açılış kancası + isim kartı + kapanış."""
    probs = []
    pur = [b.get("purpose") for b in out.get("beats", [])]
    if pur[:2] != ["kanca", "isim"] or (pur and pur[-1] != "kapanis"):
        probs.append("Bölüm 1. beat «kanca», 2. beat «isim» ile başlamalı ve son beat «kapanis» olmalı.")
    seen: list[int] = []
    for b in out.get("beats", []):
        seen += [int(x) for x in b.get("sentences", []) if isinstance(x, (int, float))]
    valid = [i for i in seen if 1 <= i <= len(sents)]
    if valid != sorted(valid):
        probs.append("Cümle numaraları sırayla artmalı: kitabın olay sırası bozulmuş.")
    if len(set(valid)) != len(valid):
        probs.append("Bir cümle birden çok beat'e bağlanmış; her cümle tek beat'e.")
    missing = [i for i in range(1, len(sents) + 1) if i not in set(valid)]
    if len(sents) and 1 - len(missing) / len(sents) < COVERAGE_MIN:
        probs.append("Kitabın şu cümleleri hiçbir beat'e bağlı değil (olaylar atlanmış): "
                     + ", ".join(str(i) for i in missing[:30]))
    total = sum(float(b.get("seconds") or 0) for b in out.get("beats", []))
    if abs(total - target) > target * 0.15:
        probs.append(f"Beat sürelerinin toplamı {total:.0f} sn; hedef {target} sn (±%10).")
    return probs


def check_episode(script: dict, book: str, target: int) -> list[spec.Problem]:
    """Bütün bölümün sadakati ve dili. Ölümcül: kitaptaki bir konuşmanın eksik olması, eklenen satırların sınırı
    aşması, sürenin hedeften çok sapması."""
    P = spec.Problem
    out: list[P] = []
    sh = spec.shots(script)
    lines = [ln for s in sh for ln in s.get("lines", [])]
    spoken = " | ".join(_n(ln.get("text", "")) for ln in lines)
    for q in speech_lines(book):
        if _n(q) and _n(q) not in spoken:
            out.append(P("senaryo", f"Kitaptaki konuşma bölümde yok ya da değiştirilmiş: «{q}»."))
    added = [ln for ln in lines if ln.get("added")]
    if lines and len(added) > max(2, ADDED_MAX * len(lines)):
        out.append(P("senaryo", f"Eklenen satır {len(added)}/{len(lines)}; en çok %{ADDED_MAX * 100:.0f}."))
    for s in sh:
        for ln in s.get("lines", []):
            if ln.get("added") and spec.words(ln.get("text", "")) > ADDED_WORDS:
                out.append(P(s["id"], f"Eklenen satır en çok {ADDED_WORDS} kelime: «{ln.get('text')}»."))
        secs = float(s.get("seconds") or 0)
        if not SHOT_MIN <= secs <= SHOT_MAX + 2:
            out.append(P(s["id"], f"Çekim {secs} sn; {SHOT_MIN}–{SHOT_MAX} sn olmalı.", fatal=False))
    total = spec.total_seconds(script)
    if abs(total - target) > target * 0.2:
        out.append(P("senaryo", f"Bölüm {total:.0f} sn; hedef {target} sn."))
    return out


async def _ask(llm, name: str, schema: dict, max_tokens: int, **kw) -> dict:
    """mk._ask'in düşünmeli hali: uyarlama çok kurallı (sadakat + ritim + ses dengesi); düşünmesiz model kuralları
    deneme deneme farklı çiğniyordu (2026-10-08, dört koşu)."""
    from ...prompts import render
    if not hasattr(llm, "chat"):                       # testte sahte
        return await mk._ask(llm, name, schema, max_tokens=max_tokens, **kw)
    ref, prompt = render(name, **kw)
    out, _ = await llm.chat(mk.ALIAS, [{"role": "user", "content": prompt}], prompt=ref, schema=schema,
                            max_tokens=max_tokens, thinking=True, think_budget=6000, temperature=0.6)
    return out


_FOLD = str.maketrans("ıİğĞüÜşŞöÖçÇâÂîÎûÛ", "iIgGuUsSoOcCaAiIuU")


def _fold(name: str) -> str:
    return re.sub(r"\s*\(.*?\)\s*$", "", name or "").translate(_FOLD).casefold().strip()


def normalize_names(script: dict, narrator: str) -> int:
    """Çekimdeki karakter ve konuşan adlarını oyuncu listesindeki yazıma bağlar (Türkçe harf/büyük-küçük/parantez
    farkı: «Boyaci» → «Boyacı», «Levent (Anlatıcı)» → «Levent»). Dönen: düzeltilen ad sayısı."""
    names = {_fold(c["name"]): c["name"] for c in script.get("cast", [])}
    names.setdefault(_fold(narrator), narrator)
    for alias in (spec.NARRATOR, "anlatici", "narrator", "ic ses", "iç ses"):       # «Anlatıcı» = kitabın anlatıcısı
        names[_fold(alias)] = narrator
    n = 0
    for sc in script.get("scenes", []):
        for sh in sc.get("shots", []):
            fixed = [names.get(_fold(c), c) for c in sh.get("characters", [])]
            n += sum(a != b for a, b in zip(fixed, sh.get("characters", [])))
            sh["characters"] = fixed
            for ln in sh.get("lines", []):
                v = names.get(_fold(ln.get("speaker", "")), ln.get("speaker", ""))
                n += v != ln.get("speaker")
                ln["speaker"] = v
    return n


def _key(s: str) -> str:
    return re.sub(r"\W+", " ", _fold(mk.norm(mk.clean_quote(s)))).strip()


def restore_book_spelling(script: dict, book: str) -> int:
    """Kitaptaki bir cümle (ya da konuşma) ile yalnız harf/noktalama farkı olan satırı kitabın yazımıyla değiştirir
    (model bazen Türkçe harfsiz yazıyordu: «sayfasina … ucak»; seslendirme yanlış okur). Dönen: düzeltilen satır."""
    ref = {}
    for x in sentences(book) + speech_lines(book):
        ref.setdefault(_key(x), mk.clean_quote(x))
    n = 0
    for sc in script.get("scenes", []):
        for sh in sc.get("shots", []):
            for ln in sh.get("lines", []):
                k = _key(ln.get("text", ""))
                if k in ref and ref[k] != ln.get("text"):
                    ln["text"] = ref[k]
                    n += 1
    return n


def _outline_text(o: dict) -> str:
    return "\n".join(f"{i}. [{b['purpose']}] sahne {int(b['scene'])} ({b['setting']}), {b['seconds']:.0f} sn: "
                     f"{b['summary']}" for i, b in enumerate(o["beats"], 1))


async def write(d: Path, f: Path, by: str, target: int, progress=lambda n, t, w="": None, llm=None) -> dict:
    m = store.meta(f)
    llm = llm or mk.make_llm(d)
    store.set_stage(f, "senaryo", status="calisiyor")
    book = script_mod.book_text(d)
    sents = sentences(book)
    known = script_mod.known_characters(d)
    base = dict(format=spec.FORMATS[m["format"]]["label"].lower(), title=studio._manuscript(d).title,
                kind=mk._kind_text(d), style=spec.STYLES[m["style"]]["label"], target_sec=str(target),
                known="\n".join(f"- {n}" for n in known) or "(yok)")
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(sents, 1))
    feedback, outline = "", None
    for attempt in range(1, ATTEMPTS + 1):
        progress(attempt, ATTEMPTS, "Olay örgüsü yazılıyor")
        outline = await _ask(llm, OUTLINE_PROMPT, OUTLINE_SCHEMA, 24000, feedback=feedback, sentences=numbered, **base)
        probs = check_outline(outline, sents, target)
        if not probs:
            break
        feedback = "Önceki denemendeki sorunlar (hepsini düzelt):\n" + "\n".join(f"- {p}" for p in probs)
    narrator = script_mod.narrator_of(outline, book)
    cast_names = ", ".join(c["name"] for c in outline.get("cast", []))
    beats = outline["beats"]
    scenes_no = sorted({int(b["scene"]) for b in beats})
    otext = _outline_text(outline)
    scenes = []
    for k, no in enumerate(scenes_no, 1):
        progress(k, len(scenes_no), "Sahneler çekim çekim yazılıyor")
        idx = [i for i, b in enumerate(beats, 1) if int(b["scene"]) == no]
        bs = [beats[i - 1] for i in idx]
        quoted = [sents[int(j) - 1] for b in bs for j in b["sentences"] if 1 <= int(j) <= len(sents)]
        dialog = [q for q in speech_lines("\n".join(quoted))] or ["(bu sahnede kitapta konuşma yok)"]
        btxt = "\n".join(f"Beat {i} [{b['purpose']}], {b['seconds']:.0f} sn: {b['summary']}\n  Kitap: "
                         + " ".join(f"«{sents[int(j) - 1]}»" for j in b["sentences"] if 1 <= int(j) <= len(sents))
                         for i, b in zip(idx, bs))
        fb, shots = "", []
        for attempt in range(1, ATTEMPTS + 1):
            out = await _ask(llm, SCENE_PROMPT, SCENE_SCHEMA, 16000, feedback=fb,
                                scene_no=str(no), outline=otext, setting=bs[0]["setting"],
                                setting_en=bs[0]["setting_en"], time=bs[0]["time"],
                                scene_sec=f"{sum(float(b['seconds']) for b in bs):.0f}", beats=btxt,
                                dialogue="\n".join(f"- {q}" for q in dialog), cast=cast_names, narrator=narrator,
                                narration_hint=(f"Kitabın son cümlesi («{sents[-1]}») bu sahnenin SON satırıdır."
                                                if k == len(scenes_no) else ""),
                                **{k2: base[k2] for k2 in ("title", "kind", "style")})
            shots = out.get("shots", [])
            for sh_ in shots:                     # «Levent (Anlatıcı)» → «Levent»: konuşan oyuncu adıdır
                for ln in sh_.get("lines", []):
                    ln["speaker"] = re.sub(r"\s*\(.*?\)\s*$", "", ln.get("speaker", "")).strip() or narrator
            probs = scene_problems(shots, quoted, sum(float(b["seconds"]) for b in bs),
                                   sents[-1] if k == len(scenes_no) else None)
            if not probs and not spec.shape_errors(out, SCENE_SCHEMA):
                break
            fb = "Önceki denemendeki sorunlar (hepsini düzelt):\n" + "\n".join(f"- {p}" for p in probs)
        scenes.append({"setting": bs[0]["setting"], "setting_en": bs[0]["setting_en"], "time": bs[0]["time"],
                       "shots": shots})
    script = {"title": outline.get("title", ""), "logline": outline.get("logline", ""), "cast": outline["cast"],
              "scenes": scenes, "outline": beats, "adapted": True, "target_sec": target}
    normalize_names(script, narrator)
    restore_book_spelling(script, book)
    problems = check_episode(script, book, target) + spec.check(
        script, m["format"], {c["name"] for c in outline["cast"]}, script_mod.book_checker(d))
    # uyarlamada çekim 1,5 sn'den başlar; toplam süre biçim aralığına değil hedefe göre (check_episode) denetlenir
    problems = [p for p in problems if "Çekim süresi" not in p.text and "Toplam süre" not in p.text]
    rec = script_mod.save(f, script, by, problems, attempts=attempt)
    store.set_stage(f, "senaryo", status="hazir" if not spec.fatal(problems) else "sorunlu",
                    seconds=spec.total_seconds(script), shots=len(spec.shots(script)))
    store.log(f, by, "uyarlama yazıldı", shots=len(spec.shots(script)), problems=len(problems))
    return rec
