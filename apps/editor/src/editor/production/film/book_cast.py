"""Kitabın kendi çizimlerinden karakter kartı: film karakterleri kitaptaki gibi görünsün (kullanıcı kararı 2026-10-07,
«kitaptaki çizimlere sadık»; stüdyonun sıfırdan tasarım kuralı — art.py — bu yolda geçerli değil).

Yöntem (kitaptan bağımsız):
1. Okunmuş kitabın sayfa görüntüleri (`ed.page.render_path`) görsel okuyucuya (gateway `book-vision-fast`) sayfanın
   kendi metni ve filmin oyuncu listesiyle birlikte gider; okuyucu görünen her kişiyi adlandırır (metin + görsel ipucu:
   «Mert'in yüzü boya içinde»), bütün bedeninin kutusunu, saç ve kıyafetini ve emin olup olmadığını söyler.
2. Aynı ada gelen tespitlerde görünüşün çoğunluğu (saç rengi + üst giysi rengi) karakterin kimliğidir; ona uymayan
   tespit (yanlış adlandırma) elenir.
3. Kalan kırpıntılardan en büyük `REFS` tanesi farklı sayfalardan seçilir → dizinin kartına referans (ilki birincil).
4. Kartın İngilizce tarifi ve sabit renkleri birincil kırpıntıdan okunur; kart TASLAK kalır, editör onaylar.

Kart dizide tutulur (characters.py): serinin sonraki kitaplarında ve filmlerinde aynı kart kullanılır. Dizide aynı adlı
kart varsa dokunulmaz (önceki kitapta onaylanmış olabilir). Sonuç `<film>/karakter-kartlari.json`.
"""

from __future__ import annotations

import base64
import collections
import io
import json
from pathlib import Path

import httpx

from .. import characters as C
from .. import studio
from . import frames as F
from . import script as script_mod
from . import store

VISION = "book-vision-fast"
REFS = 4
MIN_AREA = 0.02            # sayfanın bu oranından küçük kutu referans olmaz
KIND = {"cocuk": "çocuk", "genc": "genç", "yetiskin": "yetişkin", "yasli": "yaşlı"}
# Senaryonun yaş sınıfı → tarifteki yaş gerçeği (görsel okuyucu çizgi film oranlarında yaşı yanlış tahmin ediyordu:
# anneyi «8 yaşında kız» okudu, 2026-10-07). Kardeş/küçük ayrımı rolden gelir (ROLE_EN).
AGE_EN = {("cocuk", "erkek"): "a boy (child)", ("cocuk", "kadin"): "a girl (child)", ("cocuk", "belirsiz"): "a child",
          ("genc", "erkek"): "a teenage boy", ("genc", "kadin"): "a teenage girl", ("genc", "belirsiz"): "a teenager",
          ("yetiskin", "erkek"): "an adult man", ("yetiskin", "kadin"): "an adult woman",
          ("yetiskin", "belirsiz"): "an adult", ("yasli", "erkek"): "an elderly man", ("yasli", "kadin"): "an elderly woman",
          ("yasli", "belirsiz"): "an elderly person"}
ROLE_EN = {"kahraman": "the main character", "kardeş": "the main character's younger sibling",
           "anne": "the mother", "baba": "the father", "dede": "the grandfather", "nine": "the grandmother",
           "öğretmen": "the teacher", "arkadaş": "the main character's friend"}

PAGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["people"], "properties": {"people": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["name", "sure", "box", "hair", "top", "bottom"],
                               "properties": {"name": {"type": "string"}, "sure": {"type": "boolean"},
                                              "box": {"type": "array", "items": {"type": "integer"},
                                                      "minItems": 4, "maxItems": 4},
                                              "hair": {"type": "string"}, "top": {"type": "string"},
                                              "bottom": {"type": "string"}}}}}}
LOOK_SCHEMA = {"type": "object", "additionalProperties": False,
               "required": ["look_en", "look_tr", "species_en", "hair", "skin", "eyes", "outfit"],
               "properties": {"look_en": {"type": "string"}, "look_tr": {"type": "string"},
                              "species_en": {"type": "string"},
                              **{k: {"type": "string", "pattern": "^#[0-9A-Fa-f]{6}$"}
                                 for k in ("hair", "skin", "eyes", "outfit")}}}


def pages_of(d: Path) -> list[tuple[int, str, str]]:
    """(sayfa no, görüntü yolu, sayfanın metni) — okunmuş neslin sayfaları."""
    import os

    import psycopg
    from psycopg.rows import dict_row
    gen = (studio.read(d, "job.json") or {}).get("source", {}).get("generation_id")
    if not gen:
        raise store.FilmError("Bu iş okunmuş bir kitaptan açılmamış; kitabın çizimleri yok.")
    with psycopg.connect(os.environ["EDITOR_DB_DSN"], row_factory=dict_row) as c:
        c.execute("SET default_transaction_read_only = on")
        rows = c.execute("SELECT p.page_no, p.render_path FROM ed.page p JOIN ed.generation g "
                         "ON g.book_version_id=p.book_version_id WHERE g.id=%s AND p.image_count > 0 "
                         "ORDER BY p.page_no", (gen,)).fetchall()
        texts = {r["page_no"]: r["t"] for r in c.execute(
            "SELECT page_no, string_agg(text, ' ' ORDER BY idx) t FROM ed.paragraph WHERE generation_id=%s "
            "GROUP BY page_no", (gen,)).fetchall()}
    return [(r["page_no"], r["render_path"], texts.get(r["page_no"], "")) for r in rows
            if r["render_path"] and Path(r["render_path"]).exists()]


def _cast_lines(cast: list[dict]) -> str:
    return "\n".join(f"- {c['name']}: {c.get('role', '')}, {KIND.get(c.get('age', ''), c.get('age', ''))}, "
                     f"{c.get('gender', '')}" for c in cast)


async def _ask(http, content: list, schema: dict, name: str, max_tokens: int = 900) -> dict | None:
    url, hd = F._gateway()
    body = {"model": VISION, "max_tokens": max_tokens, "temperature": 0.0,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}},
            "messages": [{"role": "user", "content": content}]}
    try:
        r = await http.post(f"{url}/v1/chat/completions", json=body, headers=hd, timeout=900)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception:  # noqa: BLE001 - okunamayan sayfa atlanır, sayısı sonuçta yazılır
        return None


async def detect(http, path: str, text: str, cast: list[dict]) -> list[dict]:
    ask = ("This is one page of an illustrated children's book. The book's characters:\n" + _cast_lines(cast) +
           f"\n\nThe text printed on this page (Turkish): «{text[:1500]}»\n\n"
           "List every PERSON visible in the illustration (ignore the printed text area). For each: `name` = one of "
           "the character names above, chosen from the page text and visual clues (who is older/younger, who is "
           "described doing what); `sure` = false if you are guessing; `box` = the whole visible body as "
           "[x0, y0, x1, y1] in 0–1000 coordinates of the image; `hair` = colour and style in 2–4 English words; "
           "`top` and `bottom` = garment colour and type in 2–4 English words. Do not invent people.")
    out = await _ask(http, [{"type": "text", "text": ask},
                            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," +
                                                                 C._jpeg_b64(path, side=1400)}}], PAGE_SCHEMA, "page")
    return (out or {}).get("people", [])


def _key(p: dict) -> tuple[str, str]:
    """Görünüş kimliği: saç ve üst giysinin ilk renk kelimesi (ışık/gölge farkı tek kelimeyi değiştirmez)."""
    def first(s: str) -> str:
        w = [x for x in (s or "").lower().replace("-", " ").split() if x.isalpha()]
        return w[0] if w else ""
    return first(p.get("hair", "")), first(p.get("top", ""))


def consolidate(found: list[dict]) -> dict[str, list[dict]]:
    """Ada göre topla; adın çoğunluk görünüşüne uymayanı ele (yanlış adlandırma). Emin olunmayan tespit yalnız
    çoğunluğa uyuyorsa kalır. Dönen: ad → tespitler (alana göre büyükten küçüğe)."""
    by = collections.defaultdict(list)
    for p in found:
        by[p["name"]].append(p)
    out = {}
    for name, ps in by.items():
        sure = [p for p in ps if p.get("sure")] or ps
        hair = collections.Counter(_key(p)[0] for p in sure).most_common(1)[0][0]
        top = collections.Counter(_key(p)[1] for p in sure).most_common(1)[0][0]
        keep = [p for p in ps if _key(p)[0] == hair and (_key(p)[1] == top or not top)]
        keep.sort(key=lambda p: p["area"], reverse=True)
        out[name] = keep
    return out


def crop(path: str, box: list[int], margin: float = 0.06) -> bytes:
    from PIL import Image
    im = Image.open(path).convert("RGB")
    W, H = im.size
    x0, y0, x1, y1 = (v / 1000 for v in box)
    mx, my = (x1 - x0) * margin, (y1 - y0) * margin
    im = im.crop((int(max(0, x0 - mx) * W), int(max(0, y0 - my) * H), int(min(1, x1 + mx) * W), int(min(1, y1 + my) * H)))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


async def describe(http, png: bytes, member: dict) -> dict | None:
    age = AGE_EN.get((member.get("age", ""), member.get("gender", "")), "")
    ask = (f"This is {member['name']}, {ROLE_EN.get((member.get('role') or '').casefold(), member.get('role', ''))} in a "
           f"children's book, as drawn by the book's illustrator. FACT (do not contradict): {member['name']} is {age}. "
           "Cartoon proportions (big head, round eyes) do not change the age. Describe the FIXED appearance so another "
           "illustrator can draw the same character in every picture: `look_en` one English paragraph ≤ 70 words "
           "starting with the age fact (body, face, eyes, hair colour and style, everyday clothes with colours, "
           f"drawing style cues); `look_tr` the same in Turkish; `species_en` = '{age}'; hex colours of hair, skin, "
           "eyes and main outfit as seen.")
    return await _ask(http, [{"type": "text", "text": ask},
                             {"type": "image_url", "image_url": {"url": "data:image/png;base64," +
                                                                  base64.b64encode(png).decode()}}],
                      LOOK_SCHEMA, "look", max_tokens=700)


async def refresh_looks(d: Path, f: Path, by: str, names: list[str] | None = None) -> list[str]:
    """Kitaptan çıkarılmış TASLAK kartların tarifini birincil referansından yeniden yazar (referanslar aynı kalır)."""
    sc = script_mod.load(f)
    series = C.job_series(d)
    data = C.load(series["id"])
    done = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=10.0)) as http:
        for m in sc.get("cast", []):
            card = next((c for c in data["cards"] if C.fold(c["name"]) == C.fold(m["name"])), None)
            if (names and m["name"] not in names) or not card or card.get("status") == "approved" or \
                    (card.get("origin") or {}).get("from") != "kitabın çizimleri":
                continue
            refs = C.CardSet(series, [card]).refs(card)
            if not refs:
                continue
            look = await describe(http, refs[0].read_bytes(), m) or {}
            if not look:
                continue
            upd = {**card, "species_en": look.get("species_en", card.get("species_en", "")),
                   "look_tr": look.get("look_tr") or card.get("look_tr", ""),
                   "look_en": look.get("look_en") or card.get("look_en", ""),
                   "colors": {k: look[k] for k in ("hair", "skin", "eyes", "outfit") if look.get(k)}}
            C.update_card(series, None, card["id"], upd, by)
            done.append(m["name"])
    return done


async def build(d: Path, f: Path, by: str, series_name: str | None = None,
                progress=lambda n, t, w="": None) -> dict:
    sc = script_mod.load(f)
    cast = sc.get("cast", [])
    if not cast:
        raise store.FilmError("Senaryoda oyuncu yok.")
    series = C.job_series(d)
    if (not series or not series.get("exists")) and series_name:
        series = C.set_job_series(d, series_name, by)
    if not series:
        raise store.FilmError("Kitabın dizisi bulunamadı; dizi adını yazın.")
    pages = pages_of(d)
    found, failed = [], 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=10.0)) as http:
        for n, (no, path, text) in enumerate(pages, 1):
            progress(n, len(pages) + len(cast), "Kitabın çizimleri okunuyor")
            people = await detect(http, path, text, cast)
            if not people:
                failed += 1
            for p in people:
                x0, y0, x1, y1 = (min(max(v, 0), 1000) for v in p["box"])
                area = max(0, x1 - x0) * max(0, y1 - y0) / 1e6
                if p["name"] in {c["name"] for c in cast} and area >= MIN_AREA:
                    found.append({**p, "box": [x0, y0, x1, y1], "area": round(area, 4), "page": no, "path": path})
        groups = consolidate(found)
        have = C.load(series["id"])
        made, skipped, summary = [], [], {}
        for i, m in enumerate(cast, 1):
            progress(len(pages) + i, len(pages) + len(cast), "Kartlar hazırlanıyor")
            dets, seen, picks = groups.get(m["name"], []), set(), []
            for p in dets:
                if p["page"] not in seen:
                    picks.append(p)
                    seen.add(p["page"])
                if len(picks) == REFS:
                    break
            summary[m["name"]] = {"found": len(dets), "pages": sorted(p["page"] for p in dets),
                                  "refs": [{"page": p["page"], "box": p["box"], "area": p["area"]} for p in picks]}
            if any(C.fold(m["name"]) in {C.fold(x["name"]), *map(C.fold, x.get("aliases", []))} for x in have["cards"]):
                skipped.append(m["name"])
                continue
            if not picks:
                continue
            pngs = [crop(p["path"], p["box"]) for p in picks]
            look = await describe(http, pngs[0], m) or {}
            card_in = {"name": m["name"], "kind": KIND.get(m.get("age", ""), "diğer"), "age": "",
                       "species_en": look.get("species_en", ""), "look_tr": look.get("look_tr", ""),
                       "look_en": look.get("look_en") or m.get("look_en", ""),
                       "colors": {k: look[k] for k in ("hair", "skin", "eyes", "outfit") if look.get(k)}}
            _, card = C.create_card(series, None, card_in, by,
                                    origin={"job": d.name, "from": "kitabın çizimleri", "pages": summary[m["name"]]["pages"]})
            for j, (png, p) in enumerate(zip(pngs, picks)):
                C.add_ref(series, card["id"], png, {"kind": "book", "job": d.name, "page": p["page"], "box": p["box"]}, by)
            made.append(m["name"])
    rec = {"series": series["id"], "made": made, "skipped": skipped, "pages": len(pages), "unread_pages": failed,
           "characters": summary, "by": by, "at": store.now()}
    store.write(f, "karakter-kartlari.json", rec)
    store.log(f, by, "karakter kartları kitabın çizimlerinden hazırlandı", made=made, skipped=skipped)
    return rec
