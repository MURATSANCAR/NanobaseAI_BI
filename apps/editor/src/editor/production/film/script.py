"""Senaryo: ana model kitabın özetinden çekim listesini yazar; denetim (spec.check) geçmezse sorunlarıyla yeniden ister.

Kaynak pazarlama kitinin pencere pencere özetidir (marketing.digest; önbellekli, kitap bütünüyle okunur). Model kitabın
kendisini değil özetini ve özetten süzülmüş birebir alıntıları görür; her çekim bir alıntıya bağlanır, alıntı kitapta
birebir aranır (marketing.in_book). Bilinen karakterler dizinin onaylı kartlarından (characters.py) ve işin sanat
planından gelir; model aynı adları kullanır, yeni karakteri `cast`a ekler.
"""

from __future__ import annotations

from pathlib import Path

from .. import marketing as mk
from .. import studio
from ..characters import CardSet
from . import spec, store

PROMPT = "production_film_script"
ATTEMPTS = 3
SUMMARY_CHARS = 24000          # özet bu uzunluğu aşarsa her bölümün özeti orantılı kısaltılır
QUOTES = 80


def known_characters(d: Path) -> list[str]:
    names: list[str] = []
    for c in CardSet.for_job(d).cards:
        if c["name"] not in names:
            names.append(c["name"])
    for c in (studio.read(d, "artplan.json") or {}).get("characters", []):
        n = c.get("name")
        if n and n not in names:
            names.append(n)
    return names


def summary_text(dg: dict, limit: int = SUMMARY_CHARS) -> str:
    secs = dg.get("sections", [])
    full = "\n".join(f"{s['title']}: {s['summary']}" for s in secs)
    if len(full) <= limit or not secs:
        return full
    share = max(200, limit // len(secs))
    return "\n".join(f"{s['title']}: {s['summary'][:share].rsplit(' ', 1)[0]}…" for s in secs)


def book_checker(d: Path):
    book = mk.norm("\n".join(s.text for s in mk.sections(d)))
    return lambda q: mk.in_book(mk.clean_quote(q), book)


async def write(d: Path, f: Path, by: str, progress=lambda n, t, w="": None, llm=None) -> dict:
    m = store.meta(f)
    fmt, style = spec.FORMATS[m["format"]], spec.STYLES[m["style"]]
    llm = llm or mk.make_llm(d)
    store.set_stage(f, "senaryo", status="calisiyor")
    dg = await mk.digest(d, llm, progress)
    known = known_characters(d)
    in_book = book_checker(d)
    hook = (f"İlk {fmt['hook_sec']:.0f} saniye izleyiciyi yakalamalı: en çarpıcı an ya da soru ilk çekimde."
            if fmt["hook_sec"] else "")
    kw = dict(format=fmt["label"].lower(), title=studio._manuscript(d).title, kind=mk._kind_text(d),
              min_sec=str(fmt["min_sec"]), max_sec=str(fmt["max_sec"]), style=style["label"], hook=hook,
              summary=summary_text(dg), quotes="\n".join(f"- {q['text']}" for q in dg["quotes"][:QUOTES]) or "(yok)",
              known="\n".join(f"- {n}" for n in known) or "(yok)",
              min_shot=f"{spec.MIN_SHOT:.0f}", max_shot=f"{spec.MAX_SHOT:.0f}")
    feedback, out, problems = "", None, []
    for attempt in range(1, ATTEMPTS + 1):
        progress(attempt, ATTEMPTS, "Senaryo yazılıyor")
        out = await mk._ask(llm, PROMPT, spec.SCHEMA, max_tokens=16000, temperature=0.5, feedback=feedback, **kw)
        problems = spec.check(out, m["format"], {c["name"] for c in out.get("cast", [])}, in_book)
        bad = spec.fatal(problems)
        if not bad:
            break
        feedback = ("Önceki denemendeki sorunlar (hepsini düzelt):\n" +
                    "\n".join(f"- {p.where}: {p.text}" for p in bad))
    rec = save(f, out, by, problems, attempts=attempt)
    store.set_stage(f, "senaryo", status="hazir" if not spec.fatal(problems) else "sorunlu",
                    seconds=spec.total_seconds(out), shots=len(spec.shots(out)))
    store.log(f, by, "senaryo yazıldı", attempts=attempt, problems=len(problems))
    return rec


def save(f: Path, script: dict, by: str, problems: list, attempts: int | None = None, rev: int | None = None) -> dict:
    old = store.read(f, "senaryo.json") or {"rev": 0}
    if rev is not None and rev != old["rev"]:
        raise store.FilmError("Senaryo bu arada değişti; sayfayı yenileyin.")
    rec = {"rev": old["rev"] + 1, "script": script, "problems": [p.as_dict() for p in problems],
           "by": by, "at": store.now(), **({"attempts": attempts} if attempts else {})}
    store.write(f, "senaryo.json", rec)
    return rec


def edit(d: Path, f: Path, script: dict, rev: int, by: str) -> dict:
    """Editörün düzeltmesi: şemaya uymalı; denetim yeniden koşar, onay düşer."""
    m = store.meta(f)
    problems = spec.check(script, m["format"], {c["name"] for c in script.get("cast", [])}, book_checker(d))
    rec = save(f, script, by, problems, rev=rev)
    store.set_stage(f, "senaryo", status="hazir" if not spec.fatal(problems) else "sorunlu",
                    seconds=spec.total_seconds(script), shots=len(spec.shots(script)))
    store.log(f, by, "senaryo düzeltildi", rev=rec["rev"])
    return rec


def load(f: Path) -> dict:
    rec = store.read(f, "senaryo.json")
    if not rec:
        raise store.FilmError("Senaryo yok.")
    return rec["script"]
