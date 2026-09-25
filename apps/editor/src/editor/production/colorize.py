"""Renkli yazı: sayfa bloklarından `runs` üretir (sayfa planı sözleşmesi, `run` alanları).

Kurallar (kitaptan bağımsız):
- Ses sözcüğü: dizginin `sound` bloğu (`typeset.block_kind`: en çok 3 kelime, aynı harf art arda 3+ kez) bütünüyle;
  paragraf içinde de aynı harfi art arda 3+ kez taşıyan en az 4 harfli kelime («Gıcııırrr»). Vurgu rengi, başlık fontu,
  800 kalınlık; `body_size` verilirse punto gövdenin 1,35 katı (dizgi şablonunun `sound` bloğuyla aynı oran).
- Karakter adı: adın kendisi ya da kesme işaretli eki («Elif'in», «Ayşe’ye», «ELİF'İN»), büyük harfle başlıyorsa
  (özel ad). Büyük/küçük harf Türkçe kuralıyla eşlenir (I/ı, İ/i). Eksiz bitişik yazım («Elifin») ve küçük harfle
  geçen aynı kelime («can», «ay») ad sayılmaz. Karakter rengi, 700 kalınlık.
- Konuşma bloğu (`dialogue`): konuşanı `bubbles.speakers` bulduysa metin o karakterin renginde.
- `source:"editor"` run'ına (ve kaynağı yazılmamış ama biçimi olan run'a) dokunulmaz; otomatik run'lar her
  seferinde düz metinden yeniden türetilir: aynı girdiye iki kez uygulamak bir kez uygulamakla aynıdır.
"""

from __future__ import annotations

import copy
import re

from .typeset import block_kind

SOUND_SCALE = 1.35
_APOS = "'’"
_SUFFIX = r"(?:['’][^\W\d_]+)?"
_INLINE_SOUND = re.compile(r"[^\W\d_]*([^\W\d_])\1\1[^\W\d_]*")
STYLE_KEYS = ("color", "weight", "size", "font")


# ------------------------------------------------------------------ Türkçe ad eşleme
def fold(s: str) -> str:
    """Türkçe küçük harf, uzunluk korunur (eşleşme konumları özgün metne birebir döner)."""
    out = []
    for c in s:
        if c == "I":
            out.append("ı")
        elif c == "İ":
            out.append("i")
        elif c == "’":
            out.append("'")
        else:
            lo = c.lower()
            out.append(lo if len(lo) == 1 else c)
    return "".join(out)


def name_pattern(name: str) -> str:
    """Katlanmış metinde adı (çok kelimeli adda araya boşluk) bulan desen; ek hariç."""
    return r"\s+".join(re.escape(w) for w in fold(name).split())


def find_names(text: str, names) -> list[tuple[int, int, str]]:
    """Metindeki ad geçişleri: (başlangıç, bitiş, ad); ek dahil, çakışmasız, uzun ad önce."""
    folded = fold(text)
    taken: list[tuple[int, int, str]] = []
    for name in sorted({n for n in names if n and n.strip()}, key=lambda n: (-len(n), n)):
        for m in re.finditer(rf"(?<![\w'])({name_pattern(name)}){_SUFFIX}(?![\w])", folded):
            s, e = m.start(), m.end()
            if not text[s].isupper():
                continue
            if any(s < te and ts < e for ts, te, _ in taken):
                continue
            taken.append((s, e, name))
    return sorted(taken)


# ------------------------------------------------------------------ run'lar
def _block_text(b) -> str:
    if isinstance(b, dict):
        if "runs" in b and b["runs"] is not None:
            return "".join(r.get("text", "") for r in b["runs"])
        return b.get("text", "") or ""
    return getattr(b, "text", "") or ""


def _derivable(r: dict) -> bool:
    """Kural yeniden türetebilir mi: düz run ya da otomatik run. Editörün ve kaynağı bilinmeyen biçimli run korunur."""
    src = r.get("source")
    if src == "editor":
        return False
    if src == "auto":
        return True
    return not any(r.get(k) is not None for k in STYLE_KEYS)


def _merge(runs: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in runs:
        if not r.get("text") and _derivable(r):
            continue
        same = out and {k: v for k, v in out[-1].items() if k != "text"} == {k: v for k, v in r.items() if k != "text"}
        if same and _derivable(r) and _derivable(out[-1]):          # editör run'ları birleştirilmez
            out[-1] = {**out[-1], "text": out[-1]["text"] + r["text"]}
        else:
            out.append(dict(r))
    return out


def _style(text: str, **kw) -> dict:
    return {"text": text, **{k: v for k, v in kw.items() if v is not None}, "source": "auto"}


def _sound_run(text: str, accent: str, body_size: float | None) -> dict:
    size = round(body_size * SOUND_SCALE, 1) if body_size else None
    return _style(text, color=accent, weight=800, font="heading", size=size)


def _derive(text: str, kind: str, chars: dict[str, str], accent: str, body_size: float | None,
            speaker_color: str | None) -> list[dict]:
    if kind == "sound":
        return [_sound_run(text, accent, body_size)]
    marks: list[tuple[int, int, dict]] = [
        (s, e, _style(text[s:e], color=chars[n], weight=700)) for s, e, n in find_names(text, chars)]
    for m in _INLINE_SOUND.finditer(text):
        if len(m.group(0)) >= 4 and not any(m.start() < e and s < m.end() for s, e, _ in marks):
            marks.append((m.start(), m.end(), _sound_run(m.group(0), accent, body_size)))
    marks.sort(key=lambda t: t[0])
    runs, at = [], 0
    plain = (lambda t: _style(t, color=speaker_color)) if speaker_color else (lambda t: {"text": t})
    for s, e, r in marks:
        if s > at:
            runs.append(plain(text[at:s]))
        runs.append(r)
        at = e
    if at < len(text):
        runs.append(plain(text[at:]))
    return runs


def _kind(kind: str, text: str) -> str:
    """Dizginin ses bloğu kuralı (`typeset.block_kind`), üstüne tekrarın harf olması şartı: «Yıl 2000 idi.» ses değil."""
    k = block_kind(kind, text)
    if k == "sound" and kind != "sound" and not _INLINE_SOUND.search(text):
        return kind
    return k


def _accent(palette, char_colors: set[str]) -> str:
    from .palette import TIMAS_KIDS
    if isinstance(palette, dict):
        if palette.get("accent"):
            return palette["accent"]
        colors = palette.get("colors") or []
    else:
        colors = palette or []
    hexes = [(c.get("hex") if isinstance(c, dict) else str(c)).upper() for c in colors]
    free = [h for h in hexes if h not in char_colors]
    return (free or hexes or [t["hex"] for t in TIMAS_KIDS if t["hex"] not in char_colors] or ["#B0341C"])[0]


def apply(blocks: list, characters: dict[str, str], palette, *, body_size: float | None = None) -> list[dict]:
    """Bloklar → `runs`'lı bloklar (yeni liste; girdi değişmez). Girdi bloğu {"id","kind","text"} ya da
    {"id","kind","runs"} olabilir; çıktıda `text` alanı yerine `runs` vardır, öteki alanlar korunur.
    Vurgu rengi: palette'te "accent" varsa o, yoksa paletin karakterlere verilmemiş ilk rengi."""
    from .bubbles import speakers as find_speakers
    chars = {n: c.upper() for n, c in (characters or {}).items() if n and c}
    accent = _accent(palette, set(chars.values()))
    who = find_speakers(blocks, list(chars))
    out = []
    for b, spk in zip(blocks, who):
        nb = copy.deepcopy(b) if isinstance(b, dict) else {"kind": getattr(b, "kind", "para"), "text": _block_text(b)}
        text = _block_text(nb)
        kind = _kind(nb.get("kind", "para"), text)
        runs_in = nb.get("runs") if nb.get("runs") is not None else [{"text": text}]
        runs: list[dict] = []
        pending: list[str] = []

        def flush():
            if pending:
                runs.extend(_derive("".join(pending), kind, chars, accent, body_size,
                                    chars.get(spk) if kind == "dialogue" and spk else None))
                pending.clear()
        for r in runs_in:
            if _derivable(r):
                pending.append(r.get("text", ""))
            else:
                flush()
                runs.append(dict(r))
        flush()
        nb.pop("text", None)
        nb["kind"] = kind
        nb["runs"] = _merge(runs)
        out.append(nb)
    return out
