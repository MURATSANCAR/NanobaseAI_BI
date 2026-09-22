"""Süreklilik denetimlerinin (props, timeline, setting, dialogue) ortak parçaları.

Denetim modülü değildir (alt çizgi). Burada:
  - ayar okuma: `setting(name, default)` — env `EDITOR_<NAME>` → `settings()` alanı → varsayılan;
    config.py'ye dokunulmaz, her eşik belgesinde adıyla yazılır;
  - metin biçimi (INTRO + [sSAYFA pPARAGRAF] satırları), hikâye sayfası süzgeci;
  - iki sıralı kapalı yargı (`judge_both`): text_contradictions/appearance ile aynı biçim —
    kitabın bütün metni önek (önbellek), soru kapalı, cevap tek harf, olasılık logprobs'tan
    (Llm.choose); bulgu ancak iki sırada da "çelişki" olasılığı eşiği geçerse;
  - olaylar ve katılımcılar (usable_event + event_actor) ve kipe göre sayfa kümesi
    (MEMORY/DREAM sayfaları zaman çizelgesinde sıraya sokulmaz);
  - sahne sınırı: metindeki zaman/mekân geçişi kalıpları (genel Türkçe kalıp, kitaba özel değil).
"""

from __future__ import annotations

import asyncio
import os
import re

from .. import db, ledger

DIRECTOR = "book-director"
VISION = "book-vision-deep"

INTRO = ("Aşağıda resimli bir çocuk kitabının METNİ var. Her paragraf [sSAYFA pPARAGRAF] ile başlar. "
         "Künye, yazar/çizer tanıtımı ve arka kapak yazıları da metnin içinde olabilir; bunlar hikâye değildir.\n\n")

NON_STORY_ROLES = ("FRONT_MATTER", "NON_STORY")
# Gerçek olmayan kipler: bu kiplerdeki olayların sayfaları zaman sırasına sokulmaz, sahne sayılmaz.
UNREAL_MODALITIES = ("MEMORY", "DREAM", "IMAGINATION", "HYPOTHETICAL")


# ------------------------------------------------------------------ ayar
def setting(name: str, default):
    """Eşik: önce env `EDITOR_<NAME>`, sonra settings() alanı (varsa), sonra varsayılan.
    Tür varsayılandan gelir (float/int/bool/str). config.py değişmez."""
    raw = os.environ.get("EDITOR_" + name.upper())
    if raw is None:
        try:
            from ..config import settings
            raw = getattr(settings(), name, None)
        except Exception:  # noqa: BLE001 - ayar okunamıyorsa varsayılan
            raw = None
    if raw is None:
        return default
    if isinstance(default, bool):
        return str(raw).strip().lower() not in ("0", "false", "no", "")
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    return raw


# ------------------------------------------------------------------ metin
def story_pages(pages: list[dict]) -> list[dict]:
    """Editörün hikâye dışı işaretlediği sayfalar (künye, etkinlik) dışarıda; rolü bilinmeyen
    sayfa hikâye sayılır (page_role çoğu nesilde UNKNOWN)."""
    return [p for p in pages if p.get("page_role") not in NON_STORY_ROLES]


def paragraphs(pages: list[dict]) -> list[dict]:
    return [{"page": p["page_no"], "idx": s["idx"], "text": s["text"]} for p in pages for s in p["spans"]]


def book_text(pages: list[dict]) -> str:
    return "\n".join(f"[s{p['page_no']} p{s['idx']}] {s['text']}" for p in pages for s in p["spans"])


def by_no(pages: list[dict]) -> dict[int, dict]:
    return {p["page_no"]: p for p in pages}


# ------------------------------------------------------------------ yargı
async def judge_both(llm, body_fwd: str, body_rev: str, sem: asyncio.Semaphore, pages: list[int],
                     choices=("C", "U", "B"), yes: str = "C", alias: str = DIRECTOR) -> dict:
    """İki sıralı kapalı soru: her ikisi de tek harf cevap; `p` = iki sıranın "evet, çelişki"
    olasılığının küçüğü (biri bile 'açıklanıyor' derse bulgu düşer)."""
    async def ask(body: str) -> dict:
        async with sem:
            probs, _ = await llm.choose(alias, [{"role": "user", "content": body}], list(choices), pages=pages)
        return probs
    fwd, rev = await asyncio.gather(ask(body_fwd), ask(body_rev))
    return {"forward": fwd, "reverse": rev, "p": min(fwd[yes], rev[yes])}


# ---------------------------------------------------------------- olaylar
def events(generation_id: str) -> list[dict]:
    """Kullanılabilir olaylar; katılımcılar event_actor'dan (ACTOR/INVOLVED, character_id),
    çıkarımın ad listesi (`participants`) yedek olarak yanında."""
    evs = db.all_rows("SELECT id, summary, modality, page_from, page_to, participants FROM usable_event"
                      " WHERE generation_id=%s ORDER BY page_from, page_to", generation_id)
    roles = db.all_rows("SELECT event_id, character_id, role FROM event_actor WHERE generation_id=%s"
                        " AND role IN ('ACTOR','INVOLVED')", generation_id)
    who: dict[str, set] = {}
    for r in roles:
        who.setdefault(str(r["event_id"]), set()).add(str(r["character_id"]))
    return [{"id": str(e["id"]), "summary": e["summary"], "modality": e["modality"],
             "page_from": e["page_from"], "page_to": e["page_to"],
             "participants": list(e["participants"] or []), "character_ids": sorted(who.get(str(e["id"]), ()))}
            for e in evs]


def text_mentions(generation_id: str) -> list[dict]:
    """Metinde adı geçen çözülmüş karakterler, sayfa sayfa."""
    return db.all_rows("SELECT page_no, character_id FROM character_mention WHERE generation_id=%s"
                       " AND character_id IS NOT NULL AND via IN ('TEXT','BOTH')", generation_id)


def unreal_pages(evs: list[dict]) -> set[int]:
    """Yalnız gerçek olmayan kipte (anı, rüya, hayal, varsayım) olay taşıyan sayfalar. Gerçek
    ve anı olayı birlikte olan sayfa gerçek sayılır (sinyal kaybolmasın; yargı ayırır)."""
    real: set[int] = set()
    unreal: set[int] = set()
    for e in evs:
        span = range(e["page_from"], e["page_to"] + 1)
        (unreal if e["modality"] in UNREAL_MODALITIES else real).update(span)
    return unreal - real


# ------------------------------------------------------------- sahne sınırı
# Zaman geçişi: "ertesi gün/sabah", "sonraki gün", "N gün/hafta/ay/yıl sonra", "günler sonra",
# "o gece/akşam olunca", "sabah olduğunda". Mekân geçişi: yola çıkmak, varmak, dönmek.
_NUM = r"(?:bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on|yirmi|otuz|kırk|elli|yüz|\d+)"
TIME_SHIFT_RX = re.compile(
    r"\b(ertesi\s+(?:gün|sabah|akşam|gece)|sonraki\s+(?:gün|sabah|akşam|hafta)|"
    rf"{_NUM}\s+(?:gün|hafta|ay|yıl|sene)\s+sonra|(?:günler|haftalar|aylar|yıllar)\s+sonra|"
    r"(?:sabah|akşam|gece)\s+ol(?:du(?:ğunda|ğu zaman)?|unca|muştu)|aradan\s+\S+\s+geç)", re.I)
PLACE_SHIFT_RX = re.compile(
    r"\b(yola\s+(?:çıktı|koyuldu)\w*|vardı(?:lar)?\b|ulaştı(?:lar)?\b|"
    r"(?:eve|evine|evlerine|geri|okula|köye|şehre)\s+döndü(?:ler)?\b)", re.I)


def scene_breaks(pages: list[dict]) -> dict[int, list[dict]]:
    """Sayfa -> o sayfada okunan geçiş kalıpları ({kind, quote, idx}). Kalıp genel Türkçe;
    sayfanın kendi kelimeleri kanıt olarak döner."""
    out: dict[int, list[dict]] = {}
    for p in pages:
        for s in p["spans"]:
            for kind, rx in (("ZAMAN", TIME_SHIFT_RX), ("MEKAN", PLACE_SHIFT_RX)):
                for m in rx.finditer(s["text"]):
                    out.setdefault(p["page_no"], []).append({"kind": kind, "quote": m.group(0), "idx": s["idx"]})
    return out


def scenes(pages: list[dict], breaks: dict[int, list[dict]]) -> dict[int, int]:
    """Sayfa -> sahne sırası. Geçiş kalıbı olan sayfa yeni sahnenin ilk sayfasıdır; hikâye dışı
    sayfa da sahneyi böler (bölüm başı/etkinlik sayfası gibi)."""
    out: dict[int, int] = {}
    n = 0
    prev_story = True
    for p in sorted(pages, key=lambda x: x["page_no"]):
        story = p.get("page_role") not in NON_STORY_ROLES
        if p["page_no"] in breaks or (story and not prev_story):
            n += 1
        out[p["page_no"]] = n
        prev_story = story
    return out


def norm(s: str) -> str:
    return ledger.norm(s or "")
