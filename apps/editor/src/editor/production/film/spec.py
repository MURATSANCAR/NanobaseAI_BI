"""Filmin kuralları: biçimler, üslup, senaryo şeması ve denetimi. Modelsiz ve deterministik (testler bunu çağırır).

Biçim (`FORMATS`) filmin bütün ölçülerini taşır: çıktı boyutu, üretim boyutu (video modeli 720p üretir, büyütme
kurgudan sonra), süre aralığı, altyazının görüntüye basılıp basılmayacağı. Sosyal medya kesitleri (`PLATFORMS`) bitmiş
filmden alınır; yeni üretim istemez.

Senaryo çekimlerden oluşur. Bir çekim 2–10 sn'dir (video modelinin tek seferde tutarlı ürettiği süre); uzun sahne
art arda çekimdir. Her çekim kitaptan birebir bir cümleye (`quote`) bağlanır — bulunmayan çekim «kanıtsız» işaretlenir,
editör görür. Replik çekim süresine sığmalıdır (Türkçe okuma hızı `WORDS_PER_SEC`); sığmayan replik çekimi uzatır
(`fit_seconds`), çekim üst sınırı aşarsa denetim bunu hata sayar ve senaryo yeniden istenir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ------------------------------------------------------------------ biçimler
FORMATS = {
    "cizgi-film": {"label": "Çizgi film", "aspect": "16:9", "out": (1920, 1080), "gen": (1280, 720),
                   "min_sec": 60, "max_sec": 600, "burn_subtitles": False, "hook_sec": None, "lufs": -16.0},
    "fragman": {"label": "Kitap fragmanı", "aspect": "16:9", "out": (1920, 1080), "gen": (1280, 720),
                "min_sec": 45, "max_sec": 120, "burn_subtitles": False, "hook_sec": 5.0, "lufs": -14.0},
    "reels": {"label": "Sosyal medya kısa video", "aspect": "9:16", "out": (1080, 1920), "gen": (720, 1280),
              "min_sec": 15, "max_sec": 90, "burn_subtitles": True, "hook_sec": 3.0, "lufs": -14.0},
}

STYLES = {
    "2b": {"label": "2B çizgi film", "en": "2D hand-drawn animation, clean bold outlines, flat cel shading, vivid "
                                            "harmonious colours, expressive faces"},
    "3b": {"label": "3B animasyon", "en": "high-end 3D animated family feature film, cinematic CGI, soft global "
                                          "illumination, subsurface skin, detailed hair and fabric, richly detailed "
                                          "lived-in set, cinematic lighting and depth of field, appealing rounded "
                                          "character design; fully 3D-rendered characters, no outlines, no 2D "
                                          "drawing or cel shading"},
    "suluboya": {"label": "Suluboya", "en": "animated watercolour storybook, soft paper texture, gentle washes"},
    "gercekci": {"label": "Gerçekçi", "en": "cinematic live-action film look, natural light, shallow depth of field, "
                                                "film grain"},
}

# Bitmiş filmden alınan paylaşım kesitleri. Süre üst sınırı bizim kuralımızdır (platform sınırının altında kalır).
PLATFORMS = {
    "instagram-reels": {"label": "Instagram Reels", "aspect": "9:16", "size": (1080, 1920), "max_sec": 90},
    "tiktok": {"label": "TikTok", "aspect": "9:16", "size": (1080, 1920), "max_sec": 90},
    "youtube-shorts": {"label": "YouTube Shorts", "aspect": "9:16", "size": (1080, 1920), "max_sec": 60},
    "youtube": {"label": "YouTube", "aspect": "16:9", "size": (1920, 1080), "max_sec": None},
    "instagram-kare": {"label": "Instagram gönderi (kare)", "aspect": "1:1", "size": (1080, 1080), "max_sec": 60},
}

# ------------------------------------------------------------------ çekim dili (kapalı kümeler)
FRAMINGS = {"genel": "extreme wide establishing shot", "boy": "full shot", "bel": "medium shot",
            "yakin": "close-up", "cok-yakin": "extreme close-up", "omuz-ustu": "over-the-shoulder shot (the character whose shoulder is in the foreground is seen only from behind and is NOT drawn a second time facing the camera)",
            "kus-bakisi": "high-angle bird's-eye view"}
MOVES = {"sabit": "static camera", "yaklasma": "slow dolly-in", "uzaklasma": "slow dolly-out",
         "kaydirma": "smooth lateral tracking", "takip": "camera follows the character",
         "yukari": "camera tilts up", "dairesel": "slow orbit around the subject"}
EMOTIONS = ("notr", "neseli", "heyecanli", "uzgun", "korkmus", "ofkeli", "bagirarak", "fisiltiyla", "aglayarak",
            "gulerek", "saskin", "merakli", "yorgun")
TIMES = ("sabah", "gunduz", "aksam", "gece")
NARRATOR = "anlatıcı"

MIN_SHOT = 2.0
MAX_SHOT = 10.0
WORDS_PER_SEC = 2.4          # Türkçe doğal okuma (seslendirme ölçümü 2,3–2,6); replik süresi tahmini
LINE_GAP = 0.35              # iki replik arası sessizlik
SHOT_TAIL = 0.6              # replikten sonra çekimin nefes payı

AGES = ("cocuk", "genc", "yetiskin", "yasli")
GENDERS = ("kadin", "erkek", "belirsiz")

_STR = {"type": "string"}
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["title", "logline", "cast", "scenes"],
    "properties": {
        "title": _STR, "logline": _STR,
        "cast": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "role", "look_en", "age", "gender"],
            "properties": {"name": _STR, "role": _STR, "look_en": _STR,
                           "age": {"type": "string", "enum": list(AGES)},
                           "gender": {"type": "string", "enum": list(GENDERS)}}}},
        "scenes": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["setting", "setting_en", "time", "shots"],
            "properties": {
                "setting": _STR, "setting_en": _STR, "time": {"type": "string", "enum": list(TIMES)},
                "shots": {"type": "array", "minItems": 1, "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["seconds", "framing", "move", "characters", "action", "action_en", "quote", "lines",
                                 "sfx", "ambience"],
                    "properties": {
                        "seconds": {"type": "number"},
                        "framing": {"type": "string", "enum": list(FRAMINGS)},
                        "move": {"type": "string", "enum": list(MOVES)},
                        "characters": {"type": "array", "items": _STR},
                        "action": _STR, "action_en": _STR, "quote": _STR,
                        "lines": {"type": "array", "items": {
                            "type": "object", "additionalProperties": False,
                            "required": ["speaker", "text", "emotion"],
                            "properties": {"speaker": _STR, "text": _STR,
                                           "emotion": {"type": "string", "enum": list(EMOTIONS)}}}},
                        "sfx": {"type": "array", "items": _STR}, "ambience": _STR}}}}}}}}


def shape_errors(obj, schema: dict | None = None, at: str = "senaryo") -> list[str]:
    """Şemanın kullandığımız alt kümesiyle yapı denetimi (tür, zorunlu alan, fazla alan, kapalı küme, en az öğe)."""
    schema = SCHEMA if schema is None else schema
    t = schema.get("type")
    kinds = {"object": dict, "array": list, "string": str, "boolean": bool}
    if t == "number":
        if isinstance(obj, bool) or not isinstance(obj, (int, float)):
            return [f"{at}: sayı olmalı"]
        return []
    if t in kinds and not isinstance(obj, kinds[t]):
        return [f"{at}: {t} olmalı"]
    if "enum" in schema and obj not in schema["enum"]:
        return [f"{at}: izinli değerlerden biri olmalı"]
    out: list[str] = []
    if t == "object":
        props = schema.get("properties", {})
        out += [f"{at}.{k}: eksik" for k in schema.get("required", []) if k not in obj]
        if schema.get("additionalProperties") is False:
            out += [f"{at}.{k}: tanımsız alan" for k in obj if k not in props]
        for k, v in obj.items():
            if k in props:
                out += shape_errors(v, props[k], f"{at}.{k}")
    if t == "array":
        if len(obj) < schema.get("minItems", 0):
            out.append(f"{at}: en az {schema['minItems']} öğe")
        for i, v in enumerate(obj):
            out += shape_errors(v, schema.get("items", {}), f"{at}[{i}]")
    return out


# ------------------------------------------------------------------ yardımcılar
_WORD = re.compile(r"[\wçğıöşüâîûÇĞİÖŞÜ']+", re.UNICODE)


def words(text: str) -> int:
    return len(_WORD.findall(text or ""))


def speech_seconds(text: str) -> float:
    """Replik okunuş süresi tahmini (gerçek süre seslendirmeden sonra `fit_seconds`'a girer)."""
    return round(words(text) / WORDS_PER_SEC, 2)


MIN_VOICED = 3.0             # konuşmalı çekimin alt sınırı
ACTION_PAD = 1.5             # repliğin üstüne senaryonun süresinden en çok bu kadar hareket payı


def fit_seconds(planned: float, line_secs: list[float]) -> float:
    """Çekim süresi. Sessiz çekim: senaryonun süresi (alt sınır MIN_SHOT). Konuşmalı çekim: replikler + nefes payı;
    senaryo daha uzun istediyse en çok ACTION_PAD kadar hareket payı. Eskiden senaryonun süresi her zaman alınıyordu:
    3 sn'lik cümleden sonra 5 sn kimse bir şey yapmadan bekliyordu (2026-10-08, filmde toplam ~40 sn ölü süre)."""
    if not line_secs:
        return round(max(MIN_SHOT, float(planned or 0)), 2)
    need = sum(line_secs) + LINE_GAP * max(len(line_secs) - 1, 0) + SHOT_TAIL
    return round(max(MIN_VOICED, need, min(float(planned or 0), need + ACTION_PAD)), 2)


# Rolün İngilizce tarifte geçen adları (dil sözlüğü; kitaba özel değil).
ROLE_WORDS_EN = {"anne": ("mother", "mom", "mum"), "baba": ("father", "dad"), "dede": ("grandfather", "grandpa"),
                 "nine": ("grandmother", "grandma"), "babaanne": ("grandmother", "grandma"),
                 "anneanne": ("grandmother", "grandma"), "öğretmen": ("teacher",), "boyacı": ("painter",)}


def on_screen(shot: dict, cast: list[dict]) -> list[str]:
    """Karede görünen oyuncular: çekimin `characters` listesi + `action_en`'de adıyla ya da rolüyle özne/nesne olarak
    geçenler («Levent's drawings» gibi iyelik sayılmaz). Model listeyi eksik yazıyordu; listede olmayan karakter
    kartsız çiziliyor, başka saç ve giysiyle ya da ikinci kopya olarak çıkıyordu (2026-10-08: 35 karede 6)."""
    out = list(shot.get("characters", []))
    text = shot.get("action_en", "")
    for m in cast:
        if m["name"] in out:
            continue
        words = (re.escape(m["name"]),) + tuple(ROLE_WORDS_EN.get((m.get("role") or "").casefold(), ()))
        if re.search(r"\b(?:" + "|".join(words) + r")\b(?!['’]s\b)", text, re.I):
            out.append(m["name"])
    return out


def shots(script: dict) -> list[dict]:
    """Senaryonun çekimleri sırayla, sahne bilgisiyle düzleştirilmiş: id `s{sahne}c{çekim}`; `characters` karede
    görünen herkes (on_screen)."""
    out = []
    cast = script.get("cast", [])
    for si, sc in enumerate(script.get("scenes", []), 1):
        for ci, sh in enumerate(sc.get("shots", []), 1):
            out.append({**sh, "characters": on_screen(sh, cast), "id": f"s{si:02d}c{ci:02d}", "scene": si,
                        "setting": sc.get("setting", ""), "setting_en": sc.get("setting_en", ""),
                        "time": sc.get("time", "gunduz")})
    return out


def total_seconds(script: dict) -> float:
    return round(sum(float(s.get("seconds") or 0) for s in shots(script)), 2)


@dataclass
class Problem:
    where: str
    text: str
    fatal: bool = True

    def as_dict(self) -> dict:
        return {"where": self.where, "text": self.text, "fatal": self.fatal}


def check(script: dict, fmt: str, cast: set[str], in_book=None, target: int | None = None,
          grounded_min: float | None = None, voiced_min: float | None = None) -> list[Problem]:
    """Senaryo denetimi. `cast`: oyuncu adları; `in_book(quote) -> bool` verilirse alıntılar kitapta aranır.
    Ölümcül sorun senaryonun yeniden istenmesini gerektirir; ölümcül olmayan (kanıtsız alıntı) editöre gösterilir."""
    f = FORMATS[fmt]
    known = {c.casefold() for c in cast}
    out: list[Problem] = []
    sh = shots(script)
    if not sh:
        return [Problem("senaryo", "Senaryoda çekim yok.")]
    total = total_seconds(script)
    if total < f["min_sec"] * 0.8 or total > f["max_sec"] * 1.1:
        out.append(Problem("senaryo", f"Toplam süre {total:.0f} sn; bu biçim {f['min_sec']}–{f['max_sec']} sn ister."))
    if target and total < target * 0.75:
        out.append(Problem("senaryo", f"Film {total:.0f} sn; kitabı kısaltmadan anlatmak için hedef yaklaşık {target} sn. "
                                      "Kitaptaki olayların hepsini sırasıyla çek, atlama."))
    if f["hook_sec"] and float(sh[0].get("seconds") or 0) > f["hook_sec"]:
        out.append(Problem(sh[0]["id"], f"İlk çekim {f['hook_sec']:.0f} sn'yi geçmemeli (izleyiciyi ilk saniyelerde "
                                        "yakalamak için).", fatal=False))
    for s in sh:
        secs = float(s.get("seconds") or 0)
        if not MIN_SHOT <= secs <= MAX_SHOT:
            out.append(Problem(s["id"], f"Çekim süresi {secs} sn; {MIN_SHOT:.0f}–{MAX_SHOT:.0f} sn olmalı."))
        for c in s.get("characters", []):
            if c.casefold() not in known:
                out.append(Problem(s["id"], f"«{c}» oyuncu listesinde yok."))
        line_secs = []
        for ln in s.get("lines", []):
            who = (ln.get("speaker") or "").strip()
            if who.casefold() != NARRATOR and who.casefold() not in known:
                out.append(Problem(s["id"], f"Konuşan «{who}» oyuncu listesinde yok."))
            if not (ln.get("text") or "").strip():
                out.append(Problem(s["id"], "Boş replik."))
            line_secs.append(speech_seconds(ln.get("text", "")))
        if fit_seconds(secs, line_secs) > MAX_SHOT:
            out.append(Problem(s["id"], f"Replikler {MAX_SHOT:.0f} sn'lik çekime sığmıyor; repliği kısalt ya da "
                                        "çekimi ikiye böl."))
        if not (s.get("action_en") or "").strip():
            out.append(Problem(s["id"], "Çekimin görüntü tarifi boş."))
        q = (s.get("quote") or "").strip()
        if in_book is not None and (not q or not in_book(q)):
            out.append(Problem(s["id"], "Çekimin dayandığı cümle kitapta bulunamadı (kanıtsız).", fatal=False))
    if voiced_min is not None:
        voiced = sum(1 for s in sh if any((x.get("text") or "").strip() for x in s.get("lines", [])))
        if voiced < voiced_min * len(sh):
            out.append(Problem("senaryo", f"Çekimlerin yalnız {voiced}/{len(sh)} tanesinde ses var. Kitabın anlatım "
                                          "cümlelerini dış ses satırı olarak ekle (birinci tekil anlatımda konuşan "
                                          "anlatan karakterdir); sessiz çekim yalnız kısa geçiş ve tepki için."))
        run = 1
        for a, b in zip(sh, sh[1:]):
            run = run + 1 if a.get("framing") == b.get("framing") else 1
            if run > 3:
                out.append(Problem(b["id"], f"Aynı çekim türü ({b['framing']}) üst üste {run} kez; çekim türünü değiştir."))
                break
    if grounded_min is not None and in_book is not None:
        ok = sum(1 for s in sh if (s.get("quote") or "").strip() and in_book(s["quote"]))
        if ok < grounded_min * len(sh):
            out.append(Problem("senaryo", f"Çekimlerin yalnız {ok}/{len(sh)} tanesi kitaptaki bir cümleye birebir "
                                          "bağlı. Her çekimin `quote`'u metinden kelimesi kelimesine kopyalanmalı."))
    return out


def target_seconds(fmt: str, book_words: int) -> int:
    """Biçimin hedef süresi. Çizgi film kitabı kısaltmadan anlatır: konuşma (kelime ÷ okuma hızı, çocuk temposu
    biraz yavaş) + sözsüz anlar (konuşmanın ~%40'ı) + açılış/kapanış; biçimin aralığına sıkıştırılır. Fragman ve
    reels kitabı özetler: aralığın ortası."""
    f = FORMATS[fmt]
    if fmt != "cizgi-film":
        return int((f["min_sec"] + f["max_sec"]) / 2)
    speech = book_words / (WORDS_PER_SEC * 0.92)
    return int(min(f["max_sec"], max(f["min_sec"], speech * 1.4 + 25)))


def fatal(problems: list[Problem]) -> list[Problem]:
    return [p for p in problems if p.fatal]


# ------------------------------------------------------------------ istem
_KISS = re.compile(r"\bkiss", re.I)
KISS_RULE = "Any kiss is a gentle family kiss on the cheek, never on the lips."


def shot_prompt(shot: dict, style: str, cast_lines: dict[str, str]) -> str:
    """Çekimin görsel istemi (ilk kare ve video için aynı tarif). `cast_lines`: oyuncu → kart satırı (İngilizce).
    Öpme geçen çekimde öpücük yanaktan (çocuk kitabı; 2026-10-08 video modeli dudaktan öptürdü)."""
    who = " ".join(cast_lines[c] for c in shot.get("characters", []) if c in cast_lines)
    light = {"sabah": "soft morning light", "gunduz": "daylight", "aksam": "warm golden-hour light",
             "gece": "night, moonlight and lamp light"}[shot.get("time", "gunduz")]
    return (f"{FRAMINGS[shot['framing']]}, {MOVES[shot['move']]}. {shot['action_en'].strip()} "
            f"Setting: {shot.get('setting_en', '').strip()}, {light}. {who} "
            f"{KISS_RULE + ' ' if _KISS.search(shot.get('action_en', '')) else ''}"
            f"Style: {STYLES[style]['en']}. No text, letters, subtitles or watermarks.").replace("  ", " ")
