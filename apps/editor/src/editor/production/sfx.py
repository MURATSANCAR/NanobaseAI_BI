"""Sesli okumaya efekt sesleri: metinden efekt ipucu, havuzdan eşleştirme, anlatımın altına karışım.

Kullanıcı kararı (2026-09-27): «çocuk kitapları için kitap içinde patlama, vak vak, rüzgâr, ateş gibi şeyler için efekt
sesleri; ücretsiz kaynaklardan devasa bir havuz, ihtiyaç olanı doğrudan kullan». Her şey yerel: havuz GPU'da
(sfx_library), ipucu çıkarımı Zeki AI (gateway, `book-director`), karışım ffmpeg ile stüdyo kabında. Kitap metni
dışarı gitmez.

Akış (sayfa başına):
    1. İpucu (`suggest`): Zeki AI sayfa metnini okur → yansıma sözcük («vak vak», «güm», «şırıl şırıl»), sesi olan olay
       («kapı gıcırdadı», «rüzgâr esiyordu»), sahne ortamı («ormanda»). Her ipucu: tür (kapalı küme), metindeki alıntı
       (birebir geçmek ZORUNDA; geçmeyen atılır), kategori (kapalı küme: sfx_library.CATEGORIES), Türkçe arama tarifi
       ve İngilizce karşılığı, yer (kelimeyle birlikte | hemen ardından). Tek okuma gürültülüdür: sayfa VOTES kez okunur,
       en az VOTE_MIN destekli ipucu (aynı blokta örtüşen kelimeler) kalır; destek = okuma sayısı + dil kuralının
       (ikileme, ses fiili: `sound_hints`) aynı yeri bulması; güven = destek / okuma sayısı. Kuralın bulduğu ifadeler
       istemde «ayrıca karar ver» ipucu olarak da gider.
    2. Eşleştirme: tarif → havuzda en uygun ADAY adet ses; varsayılan birincisi. Editör adaylardan birini seçer,
       kütüphanede arar, ses düzeyini değiştirir, kaldırır ya da kelimeyi seçip elle yeni efekt ekler.
    3. Karışım (`mix_page`): anlatım olduğu gibi 0. saniyeden başlar (kelime zamanları DEĞİŞMEZ, e-kitap vurgusu
       bozulmaz). Anlık efekt kelimenin başında (birlikte) ya da alıntının bitiminde (ardından) girer; efekt yolu
       anlatım sürerken otomatik kısılır (sidechain: anlatım anahtar). Ortam sesi sayfa boyunca çok düşük, girişte ve
       çıkışta yumuşak geçiş. Son sayfa sesi LUFS hedefine (TARGET_LUFS, gerçek tepe TRUE_PEAK) iki geçişli
       normalleştirilir. Anlatım yeniden üretilmez: karışım anlatım dosyasından (önbellek) yapılır.

Varsayılan: çocuk kitabında (profildeki yaş bandı CHILD_MAX yaşın altında başlıyorsa) açık, yetişkin kitabında
kapalı; editör kitap başına açar/kapatır (`set_enabled`).

İş klasöründe (`<iş>/ses/efekt/`):
    ayar.json             {enabled, source: editor, by, at}  (yoksa yaş bandından)
    sayfa/<pid>.json      {page, cues: [...], ambience, suggested: {at, by, votes, text_hash}, updated_by, updated_at}
    karisim/<pid>.mp3     efektli sayfa sesi
    karisim/<pid>.json    {hash, narration_hash, placements: [...], ambience, duration, lufs, at}
    oneri.json            süren/son öneri koşusu {state, done, total, by, started, finished, error}

İpucu kaydı: {id, kind: anlik|ortam, type: yansima|olay|ortam, block, words: [ilk, son], quote, query, query_en,
category, candidates: [ses kimliği…], chosen, gain_db, place: birlikte|ardindan, source: zeki|editor, confidence,
lost (metin değişti, alıntı bulunamadı)}.

Sesli okumaya tek kanca: narration.py `_efekt_kancasi` (sayfa sesi yazılınca `after_narration`). E-kitap sayfa
sesini `page_audio` ile seçer.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import subprocess
import threading
import time
from pathlib import Path

from . import sfx_library as L

log = logging.getLogger(__name__)

DIR = "ses/efekt"
MIX_VERSION = 1
ALIAS = "book-director"
VOTES = 3
VOTE_MIN = 2
READ_TEMPERATURE = 0.7
CANDIDATES = 3
FIT_MIN = 0.35                    # bunun altında aday kendiliğinden seçilmez (deneme: 0,19 uygunlukla «makine dönüşü»)
CHILD_MAX = 12                    # yaş bandı bu yaşın altında başlıyorsa çocuk kitabı (efekt varsayılan açık)

# Karışım düzeyleri (LUFS; efekt dosyasının ölçülmüş yüksekliğinden kazanç hesaplanır)
TARGET_LUFS = -16.0               # son sayfa sesi (sesli kitap/podcast olağan düzeyi)
TRUE_PEAK = -1.5
FX_LUFS = -23.0                   # anlık efektin kendi düzeyi (anlatımdan ~3-5 LU alçak; kısma ayrıca)
AMB_LUFS = -38.0                  # ortam sesi: anlatımın çok altında
FX_MAX_SEC = 4.0                  # anlık efektin sayfaya giren en uzun kısmı (kuyruk yumuşak kısılır)
FX_FADE = 0.25
AMB_FADE = 1.5
DUCK = "threshold=0.03:ratio=8:attack=15:release=350:makeup=1"
GAIN_RANGE = (-18.0, 12.0)
MAX_BOOST = 18.0                  # çok sessiz kayıt en çok bu kadar yükseltilir (deneme: +27 dB gürültü tabanını da kaldırır)

TYPES = {"yansima": "Yansıma sözcük", "olay": "Olay", "ortam": "Ortam"}
PLACES = ("birlikte", "ardindan")
_ID = re.compile(r"^e_[0-9a-f]{8}$")


# ------------------------------------------------------------------ depo
def _dir(d: Path) -> Path:
    p = d / DIR
    (p / "sayfa").mkdir(parents=True, exist_ok=True)
    (p / "karisim").mkdir(parents=True, exist_ok=True)
    return p


def _read(p: Path, default=None):
    try:
        return json.loads(p.read_text()) if p.exists() else default
    except ValueError:
        return default


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    tmp.replace(p)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def new_id() -> str:
    import secrets
    return "e_" + secrets.token_hex(4)


# ------------------------------------------------------------------ açık / kapalı
def settings(d: Path) -> dict:
    cfg = _read(d / DIR / "ayar.json")
    if cfg and isinstance(cfg.get("enabled"), bool):
        return {**cfg, "source": "editor"}
    from .age_report import band_of
    band, src = band_of(d)
    if band is None:
        return {"enabled": False, "source": "auto", "reason": "Kitabın yaş bandı belli değil; efektler kapalı başlar."}
    child = band[0] < CHILD_MAX
    return {"enabled": child, "source": "auto", "band": list(band),
            "reason": (f"Çocuk kitabı ({band[0]}–{band[1]} yaş): efektler açık başlar." if child
                       else f"{band[0]}–{band[1]} yaş kitabı: efektler kapalı başlar.")}


def set_enabled(d: Path, on: bool, by: str) -> dict:
    cfg = {"enabled": bool(on), "by": by, "at": _now()}
    _write(_dir(d) / "ayar.json", cfg)
    return settings(d)


def enabled(d: Path) -> bool:
    return bool(settings(d)["enabled"])


# ------------------------------------------------------------------ sayfa metni
def _units(d: Path, pg: dict):
    from . import narration as N
    return N.page_units(pg, N.settings_of(d), N.lexicon(d))


def _norm(s: str) -> str:
    return " ".join(L.words(s))


def text_hash(units) -> str:
    return _hash([(u.id, u.text) for u in units])


def locate(units, quote: str, block: str | None = None) -> tuple[str, int, int] | None:
    """Alıntının metindeki yeri: (blok, ilk kelime, son kelime). Önce verilen blokta, sonra bütün sayfada; kelimeler
    noktalamasız ve büyük/küçük harf farkı gözetmeden birebir ardışık eşleşmeli."""
    q = L.words(quote)
    if not q:
        return None
    order = sorted(units, key=lambda u: 0 if u.id == block else 1)
    for u in order:
        toks = [L.words(w.text) for w in u.words]
        flat: list[tuple[str, int]] = []
        for k, ws in enumerate(toks):
            for w in ws:
                flat.append((w, k))
        n = len(q)
        for s in range(0, len(flat) - n + 1):
            if [f[0] for f in flat[s:s + n]] == q:
                return u.id, flat[s][1], flat[s + n - 1][1]
    return None


def _quote_ok(units, cue: dict) -> bool:
    for u in units:
        if u.id == cue.get("block"):
            a, b = cue["words"]
            if 0 <= a <= b < len(u.words):
                return _norm(" ".join(w.text for w in u.words[a:b + 1])) == _norm(cue["quote"])
    return False


# ------------------------------------------------------------------ sayfa efektleri
def page_file(d: Path, pid: str) -> Path:
    return d / DIR / "sayfa" / f"{pid}.json"


def page_effects(d: Path, pid: str, pg: dict | None = None) -> dict:
    """Sayfanın efektleri; metin değiştiyse alıntılar yeniden bulunur (bulunamayan `lost`)."""
    rec = _read(page_file(d, pid)) or {"page": pid, "cues": [], "ambience": None, "suggested": None}
    if pg is None:
        from . import plan as plan_mod
        pl = plan_mod.load(d)
        if pl is None:
            raise plan_mod.NoPlan(d.name)
        pg = plan_mod._page(pl, pid)
    units = _units(d, pg)
    for c in rec.get("cues", []):
        if _quote_ok(units, c):
            c.pop("lost", None)
            continue
        where = locate(units, c["quote"], c.get("block"))
        if where:
            c["block"], c["words"] = where[0], [where[1], where[2]]
            c.pop("lost", None)
        else:
            c["lost"] = True
    amb = rec.get("ambience")
    if amb and amb.get("quote"):
        amb["lost"] = locate(units, amb["quote"], amb.get("block")) is None
    rec["text_hash"] = text_hash(units)
    rec["blocks"] = [{"id": u.id, "kind": u.kind, "text": u.text, "words": [w.text for w in u.words]} for u in units]
    return rec


def _clean_cue(c: dict, units) -> dict:
    kind = "ortam" if c.get("kind") == "ortam" else "anlik"
    out = {"id": c.get("id") if _ID.match(str(c.get("id") or "")) else new_id(), "kind": kind,
           "type": c.get("type") if c.get("type") in TYPES else ("ortam" if kind == "ortam" else "olay"),
           "quote": str(c.get("quote") or "")[:200], "query": str(c.get("query") or "")[:200],
           "query_en": str(c.get("query_en") or "")[:200],
           "category": c.get("category") if c.get("category") in L.CATEGORIES else None,
           "candidates": [str(x)[:32] for x in (c.get("candidates") or [])][:20],
           "chosen": (str(c["chosen"])[:32] if c.get("chosen") else None),
           "gain_db": max(GAIN_RANGE[0], min(GAIN_RANGE[1], float(c.get("gain_db") or 0.0))),
           "place": c.get("place") if c.get("place") in PLACES else "birlikte",
           "source": c.get("source") if c.get("source") in ("zeki", "editor") else "editor",
           "confidence": c.get("confidence"), "fit": c.get("fit")}
    where = None
    if isinstance(c.get("words"), list) and len(c["words"]) == 2 and c.get("block"):
        out["block"], out["words"] = str(c["block"]), [int(c["words"][0]), int(c["words"][1])]
        if not _quote_ok(units, out):
            where = locate(units, out["quote"], out["block"])
            if where is None:
                raise ValueError(f"«{out['quote']}» sayfa metninde geçmiyor.")
            out["block"], out["words"] = where[0], [where[1], where[2]]
    else:
        where = locate(units, out["quote"], c.get("block"))
        if where is None:
            raise ValueError(f"«{out['quote']}» sayfa metninde geçmiyor.")
        out["block"], out["words"] = where[0], [where[1], where[2]]
    if out["chosen"] and L.available() and L.get(out["chosen"]) is None:
        raise ValueError("Seçilen efekt havuzda yok.")
    return out


def set_page(d: Path, pid: str, body: dict, by: str) -> dict:
    """Editörün sayfa efektleri (tamamı): {cues: [...], ambience: {...}|null}. Alıntı metinde geçmeli."""
    from . import plan as plan_mod
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    pg = plan_mod._page(pl, pid)
    units = _units(d, pg)
    old = _read(page_file(d, pid)) or {}
    cues = [_clean_cue(c, units) for c in (body.get("cues") or []) if isinstance(c, dict)]
    amb = body.get("ambience")
    amb_out = None
    if isinstance(amb, dict) and (amb.get("chosen") or amb.get("query")):
        amb_out = {"query": str(amb.get("query") or "")[:200], "query_en": str(amb.get("query_en") or "")[:200],
                   "category": amb.get("category") if amb.get("category") in L.CATEGORIES else None,
                   "candidates": [str(x)[:32] for x in (amb.get("candidates") or [])][:20],
                   "chosen": str(amb["chosen"])[:32] if amb.get("chosen") else None,
                   "gain_db": max(GAIN_RANGE[0], min(GAIN_RANGE[1], float(amb.get("gain_db") or 0.0))),
                   "quote": str(amb.get("quote") or "")[:200] or None, "block": amb.get("block"),
                   "source": amb.get("source") if amb.get("source") in ("zeki", "editor") else "editor",
                   "scope": "bolum" if amb.get("scope") == "bolum" else "sayfa"}
        if amb_out["chosen"] and L.available() and L.get(amb_out["chosen"]) is None:
            raise ValueError("Seçilen ortam sesi havuzda yok.")
    rec = {"page": pid, "cues": cues, "ambience": amb_out, "suggested": old.get("suggested"),
           "updated_by": by, "updated_at": _now()}
    _write(_dir(d) / "sayfa" / f"{pid}.json", rec)
    if amb_out and amb_out["scope"] == "bolum":
        _spread_ambience(d, pl, pg, amb_out, by)
    return page_view(d, pid)


def _spread_ambience(d: Path, pl: dict, pg: dict, amb: dict, by: str) -> None:
    """Bölüm başına ortam: aynı bölümdeki (plan sayfasının `chapter`'ı) öteki sayfalara da yazılır."""
    ch = pg.get("chapter")
    if ch is None:
        return
    for other in pl["pages"]:
        if other["id"] == pg["id"] or other.get("chapter") != ch:
            continue
        rec = _read(page_file(d, other["id"])) or {"page": other["id"], "cues": [], "ambience": None, "suggested": None}
        rec["ambience"] = {**amb, "quote": None, "block": None, "from_page": pg["id"]}
        rec["updated_by"], rec["updated_at"] = by, _now()
        _write(page_file(d, other["id"]), rec)


# ------------------------------------------------------------------ Zeki AI ile ipucu
_SCHEMA_ITEM = {
    "type": "object", "additionalProperties": False,
    "required": ["blok", "alinti", "tur", "kategori", "tarif", "tarif_en", "yer"],
    "properties": {
        "blok": {"type": "string"}, "alinti": {"type": "string"},
        "tur": {"type": "string", "enum": list(TYPES)},
        "kategori": {"type": "string", "enum": list(L.CATEGORIES) + ["diger"]},
        "tarif": {"type": "string"}, "tarif_en": {"type": "string"},
        "yer": {"type": "string", "enum": list(PLACES)},
    },
}

PROMPT = """Bir çocuk kitabının sesli okumasına efekt sesi yerleştiriyorsun. Aşağıda kitabın bir sayfasının (ya da
ardışık birkaç sayfasının) metni var; her blok köşeli parantez içindeki kimliğiyle verildi. Dinleyicinin duyacağı
sesleri bul:

1. yansima: sesi taklit eden sözcükler (ör. vak vak, hav hav, miyav, güm, pat, şırıl şırıl, tık tık, vızz).
2. olay: sesi olan somut bir olay (ör. kapı gıcırdadı, bir şey patladı, yere düştü, rüzgâr uğulduyordu, yağmur
   yağıyordu, ateş çıtırdıyordu, köpek havladı, zil çaldı, koşarak geldi, suya atladı).
3. ortam: sahne boyunca süren ortam sesi, yalnız metin sahneyi açıkça kuruyorsa (ör. ormanda, deniz kıyısında,
   okul bahçesinde, kalabalık bir çarşıda, gece vakti).

Kurallar:
- Konuşmanın ANLAMI, düşünce, duygu, görüntü, koku efekt DEĞİLDİR. Ama bir karakterin ağzından çıkan yansıma sözcük
  EFEKTTİR (ördeğin «Vak vak!» demesi, köpeğin «Hav hav!», gülüşün «Kıh kıh!», düşüşün «Pat!»): alıntı yansıma
  sözcüğün kendisidir. Olmayan ya da olumsuzlanan ses («hiç ses çıkmadı») efekt değildir. Yalnız benzetme olarak geçen
  sesi («gök gürültüsü gibi bağırdı») efekt yapma.
- «alinti», bloktaki metinden HARFİ HARFİNE kopyalanmış 1-6 kelimelik parçadır (sesi anlatan kelimeler). Metinde
  birebir geçmeyen alıntı geçersizdir.
- Aynı ses sayfada tekrar ediyorsa yalnız ilk geçtiği yeri yaz.
- «tarif»: kütüphanede aranacak sesin kısa Türkçe tarifi (ör. «ördek vaklıyor», «güçlü patlama», «çıtırdayan
  ateş», «uğuldayan rüzgâr»). «tarif_en»: aynı tarifin kısa İngilizce karşılığı (ör. "duck quacking").
- «kategori»: listeden en uygun anahtar; hiçbiri uymuyorsa "diger".
- «yer»: yansıma sözcükte ve anlık vuruşta "birlikte" (kelimeyle aynı anda); bir olayın sonucu olan seste
  (ör. kapı kapandı, düştü) "ardindan" (cümle o yeri okuyup bitirince).
- Hiç ses yoksa boş liste ver. Sayı sınırı yok; ama yalnız gerçekten duyulacak sesleri seç.

Kategoriler: {cats}
{hints}
Sayfa metni:
{text}"""

# Türkçede sesi anlatan fiil kökleri ve ikilemeler (dil bilgisi; kitaptan bağımsız). Yalnız modele «bunlara ayrıca bak»
# ipucu olarak gider: karar modelindir, ipucu listede diye efekt olmaz. Model boş liste vermeye yatkın (2026-09-28:
# «Vak vak!» geçen sayfada 3 okumanın 2'si boştu); aday gösterilince her birine tek tek karar veriyor.
SOUND_STEMS = ("havla", "miyavla", "mırla", "kükre", "gıcırda", "çıtırda", "patla", "gürle", "gümbürde", "uğulda",
               "vızılda", "vızla", "tıkırda", "şırılda", "cıvılda", "şakı", "öttü", "ötüyor", "öterek", "çınla",
               "şangırda", "fokurda", "hışırda", "kişne", "anır", "böğür", "mele", "gıdakla", "vakla", "ıslık",
               "horla", "hapşır", "öksür", "hıçkır", "kahkaha", "alkış", "çatırda", "takırda", "tıkla", "gürültü",
               "zil", "çaldı", "çalıyor", "düdük", "korna", "siren", "çarptı", "çarpıp", "düştü", "devrildi", "kırıldı",
               "zıpla", "sıçra", "kükreme", "havlama", "gök gürült", "yağmur", "rüzgâr", "rüzgar", "fırtına", "dalga")
_REDUP = re.compile(r"\b(\w{1,8})([ -])\1(?:\2\1)*\b", re.I)


def sound_hints(units) -> list[str]:
    """Sayfada ses olabilecek ifadeler: ikilemeler («vak vak», «pıt pıt pıt», «şırıl şırıl») ve ses fiilleri."""
    out: list[str] = []
    for u in units:
        for m in _REDUP.finditer(u.text):
            if len(m.group(1)) >= 2 and not m.group(1).isdigit():
                out.append(m.group(0))
        for w in u.words:
            f = L.tr_lower(w.text.strip(" ,.;:!?…\"'«»“”‘’()"))
            if any(f.startswith(s) for s in SOUND_STEMS):
                out.append(w.text.strip(" ,.;:!?…\"'«»“”‘’()"))
    return list(dict.fromkeys(x for x in out if x))


def _cats_line() -> str:
    return "; ".join(f"{k} ({c['label']})" for k, c in L.CATEGORIES.items())


def _page_prompt(units) -> tuple[str, list[str]]:
    lines, ids = [], []
    for u in units:
        ids.append(u.id)
        who = f" ({u.speaker})" if u.speaker else ""
        lines.append(f"[{u.id}]{who} {u.text}")
    hints = sound_hints(units)
    hint = ("\nMetinde ses olabilecek ifadeler (her birine ayrıca karar ver; efekt değilse alma): "
            + ", ".join(f"«{h}»" for h in hints) + "\n") if hints else ""
    return (PROMPT.replace("{cats}", _cats_line()).replace("{hints}", hint).replace("{text}", "\n".join(lines)), ids)


async def _read_page(llm, units, pid: str, temperature: float) -> list[dict]:
    from ..llm import PromptRef
    prompt, ids = _page_prompt(units)
    item = json.loads(json.dumps(_SCHEMA_ITEM))
    item["properties"]["blok"] = {"type": "string", "enum": ids}
    schema = {"type": "object", "additionalProperties": False, "required": ["ipuclari"],
              "properties": {"ipuclari": {"type": "array", "items": item}}}
    out, _ = await llm.chat(ALIAS, [{"role": "user", "content": prompt}], prompt=PromptRef("sfx.cues", "1"),
                            schema=schema, max_tokens=2500, temperature=temperature, thinking=False)
    return out.get("ipuclari") or []


def _vote(reads: list[list[dict]], units, min_votes: int = VOTE_MIN, hints: list[str] | None = None
          ) -> tuple[list[dict], dict]:
    """Okumaları birleştirir: aynı blokta kelimeleri örtüşen ipuçları tek ipucu; en az `min_votes` destekle kalır.
    Destek = ipucunu veren okuma sayısı + alıntı dil kuralının bulduğu bir ses ifadesiyle (sound_hints: ikileme ya da ses
    fiili) örtüşüyorsa 1 (kural ve model iki ayrı kanıttır). Alıntısı metinde birebir geçmeyen ipucu okumanın içinde
    atılır (sayılır)."""
    stats = {"reads": len(reads), "raw": 0, "not_in_text": 0, "kept": 0, "weak": 0}
    hint_words = [set(L.words(h)) for h in (hints or [])]
    groups: list[dict] = []
    for r_i, items in enumerate(reads):
        for it in items:
            stats["raw"] += 1
            where = locate(units, it.get("alinti", ""), it.get("blok"))
            if where is None:
                stats["not_in_text"] += 1
                continue
            b, a, z = where
            hit = None
            for g in groups:
                if g["block"] == b and not (z < g["words"][0] or a > g["words"][1]) and \
                        (g["type"] == "ortam") == (it["tur"] == "ortam"):
                    hit = g
                    break
            if hit is None:
                hit = {"block": b, "words": [a, z], "type": it["tur"], "reads": set(), "items": []}
                groups.append(hit)
            hit["reads"].add(r_i)
            hit["items"].append(it)
    out = []
    for g in groups:
        u = next(u for u in units if u.id == g["block"])
        span = set(L.words(" ".join(w.text for w in u.words[g["words"][0]:g["words"][1] + 1])))
        ruled = any(h and h <= span for h in hint_words)
        support = len(g["reads"]) + (1 if ruled else 0)
        if support < min_votes:
            stats["weak"] += 1
            continue
        items = g["items"]
        # en sık kategori/tür/yer; tarif ilk okumanınki (kategoriyle uyumlu olan)
        def most(key):
            vals = [x[key] for x in items]
            return max(set(vals), key=vals.count)
        cat, typ, place = most("kategori"), most("tur"), most("yer")
        best = next((x for x in items if x["kategori"] == cat), items[0])
        a, z = g["words"]
        quote = " ".join(w.text for w in u.words[a:z + 1]).strip(" ,.;:!?…\"'«»“”")
        out.append({"id": new_id(), "kind": "ortam" if typ == "ortam" else "anlik", "type": typ,
                    "block": g["block"], "words": [a, z], "quote": quote, "query": best["tarif"][:200],
                    "query_en": best["tarif_en"][:200], "category": cat if cat in L.CATEGORIES else None,
                    "place": place if typ != "ortam" else "birlikte", "source": "zeki",
                    "confidence": round(min(1.0, support / max(1, len(reads))), 2), "gain_db": 0.0,
                    "ruled": ruled,
                    # okumaların farklı tarifleri: eşleştirmede hangisi havuzda daha uygun ses bulursa o kalır
                    "alts": list(dict.fromkeys((x["tarif"][:200], x["tarif_en"][:200]) for x in items))})
        stats["kept"] += 1
    return out, stats


def match(cue: dict, exclude: set[str] | None = None, k: int = CANDIDATES) -> list[dict]:
    """İpucunun havuzdaki adayları (anlam + etiket araması; `k` adet)."""
    kind = "ortam" if cue.get("kind") == "ortam" else "anlik"
    res = L.search(cue.get("query") or cue.get("quote") or "", en=cue.get("query_en") or None,
                   category=None, kind=kind, k=k, exclude=exclude)
    return res


POOL_K = 16                       # aramanın Zeki AI'ye gösterdiği aday sayısı (seçim tek harf: A…P, X = hiçbiri);
#                                   kapsama ölçümü docs/analiz/efekt-sesleri-kaynaklar.md §4 (8 ve 16 aday)
_LETTERS = "ABCDEFGHIJKLMNOP"
PICK = """Bir çocuk kitabının sesli okumasına efekt konacak. Metindeki yer: «{quote}». İstenen ses: «{q}» ({en}).
Ses kütüphanesinde aramanın bulduğu adaylar (ad, klasör, etiketler, süre):
{rows}
İstenen sese en uygun adayın harfini yaz. Hiçbiri o sesi içermiyorsa X yaz. Yalnız tek harf."""


def _cand_line(letter: str, r: dict) -> str:
    full = L.get(r["id"]) or {}
    tags = ", ".join((full.get("tags_en") or [])[:14])
    return f"{letter}) {r['title']} | {full.get('group') or r.get('source')} | {tags} | {float(r.get('dur') or 0):.1f} sn"


async def rerank(llm, cue: dict, cands: list[dict]) -> tuple[list[dict], float | None]:
    """Aramanın ilk POOL_K adayını Zeki AI sıralar: kapalı kümede tek harf (A…P ya da X = hiçbiri), olasılıklar
    belirteç olasılığından (tek çağrı). Dönen: olasılığa göre sıralı adaylar ve «uygun ses var» olasılığı (1 − P(X)).
    Model yoksa aramanın sırası korunur. Yalnız adın/klasörün/etiketin görüldüğü, sesin dinlenmediği bir seçimdir."""
    if not cands:
        return [], 0.0
    from ..llm import PromptRef
    letters = _LETTERS[:len(cands)]
    msg = PICK.format(quote=cue.get("quote", ""), q=cue.get("query", ""), en=cue.get("query_en", ""),
                      rows="\n".join(_cand_line(a, r) for a, r in zip(letters, cands)))
    try:
        probs, _ = await llm.choose(ALIAS, [{"role": "user", "content": msg}], list(letters) + ["X"],
                                    prompt=PromptRef("sfx.pick", "1"))
    except Exception:  # noqa: BLE001 — model yoksa aramanın sırası
        return cands, None
    order = sorted(range(len(cands)), key=lambda i: (-probs.get(letters[i], 0.0), i))
    return [cands[i] for i in order], round(1.0 - probs.get("X", 0.0), 3)


async def suggest_page(d: Path, pid: str, by: str, llm=None, keep_editor: bool = True) -> dict:
    """Sayfanın efekt ipuçlarını Zeki AI ile çıkarır ve havuzda eşleştirir. Editörün elle eklediği/seçtiği ipuçları
    korunur (`keep_editor`); Zeki AI'nin eski önerileri yenileriyle değişir."""
    from . import plan as plan_mod
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    pg = plan_mod._page(pl, pid)
    units = _units(d, pg)
    if llm is None:
        from .run import FileLlm
        llm = FileLlm(d / "provenance.jsonl")
    if not any(u.text.strip() for u in units):
        reads = []
    else:
        # bağımsız örnekler aynı sıcaklıkta: 0,2'de model sık sık boş liste veriyordu (2026-09-28 ölçümü; dere
        # sayfasında 0,2 → 0 ipucu, 0,7 → «şırıl şırıl akan»), oylama gürültüyü süzer
        reads = await asyncio.gather(*[_read_page(llm, units, pid, READ_TEMPERATURE) for _ in range(VOTES)])
    cues, stats = _vote(list(reads), units, hints=sound_hints(units))
    old = _read(page_file(d, pid)) or {}
    kept = [c for c in old.get("cues", []) if keep_editor and c.get("source") == "editor"]
    taken = {(c["block"], tuple(c["words"])) for c in kept}
    ambience = old.get("ambience") if (old.get("ambience") or {}).get("source") == "editor" else None
    final = list(kept)
    lib_ok = L.available()
    for c in cues:
        if (c["block"], tuple(c["words"])) in taken:
            continue
        alts = c.pop("alts", None) or [(c["query"], c["query_en"])]
        if lib_ok:
            best = None
            for q, en in alts:                       # okumaların tarifleri; en uygun sesi bulan tarif kalır
                alt = {**c, "query": q, "query_en": en}
                cands = await asyncio.to_thread(match, alt, None, POOL_K)
                ranked, fit = await rerank(llm, alt, cands)
                if best is None or (fit or 0) > (best[2] or 0):
                    best = (alt, ranked, fit)
                if fit is not None and fit >= 0.8:
                    break
            alt, ranked, fit = best
            c["query"], c["query_en"] = alt["query"], alt["query_en"]
            c["candidates"] = [x["id"] for x in ranked[:CANDIDATES]]
            # Zeki AI adaylardan emin değilse ses kendiliğinden seçilmez (karışıma girmez); editör dinleyip seçer
            c["chosen"] = ranked[0]["id"] if ranked and (fit is None or fit >= FIT_MIN) else None
            c["fit"] = fit                           # Zeki AI'ye göre havuzda uygun ses olma olasılığı
        else:
            c["candidates"], c["chosen"] = [], None
        if c["kind"] == "ortam":
            if ambience is None:
                ambience = {"query": c["query"], "query_en": c["query_en"], "category": c["category"],
                            "candidates": c["candidates"], "chosen": c["chosen"], "gain_db": 0.0, "quote": c["quote"],
                            "block": c["block"], "source": "zeki", "scope": "sayfa", "confidence": c["confidence"]}
            continue
        final.append(c)
    rec = {"page": pid, "cues": final, "ambience": ambience,
           "suggested": {"at": _now(), "by": by, "votes": VOTES, "text_hash": text_hash(units), "stats": stats},
           "updated_by": old.get("updated_by"), "updated_at": old.get("updated_at")}
    _write(_dir(d) / "sayfa" / f"{pid}.json", rec)
    return rec


# ---- öneri koşusu (arka plan; ekran durumu okur)
_running: set[str] = set()
_run_lock = threading.Lock()


def run_state(d: Path) -> dict:
    s = _read(d / DIR / "oneri.json") or {"state": "none"}
    if s.get("state") == "running" and d.name not in _running and time.time() - s.get("started", 0) > 120:
        s = {**s, "state": "failed", "error": "Öneri yarıda kaldı (servis yeniden başladı); yeniden başlatın."}
    return s


def claim(d: Path, by: str, pages: list[str]) -> bool:
    with _run_lock:
        if d.name in _running:
            return False
        _running.add(d.name)
    _write(_dir(d) / "oneri.json", {"state": "running", "by": by, "started": time.time(), "done": 0, "total": len(pages)})
    return True


async def suggest_run(d: Path, pages: list[str], by: str, mix: bool = True, suggest: bool = True) -> dict:
    """Arka plan koşusu: sayfa sayfa öneri (Zeki AI) ve/veya karışım. `suggest=False`: yalnız karışım (anlatım ve
    öneriler yerinde; «güncel değil» sayfaları yeniden karıştırmak için)."""
    st = {"state": "running", "by": by, "started": time.time(), "done": 0, "total": len(pages),
          "kind": "suggest" if suggest else "mix"}
    try:
        from .run import FileLlm
        llm = FileLlm(d / "provenance.jsonl")
        for pid in pages:
            if suggest:
                await suggest_page(d, pid, by, llm)
            if mix:
                try:
                    await asyncio.to_thread(mix_page, d, pid)
                except NoNarration:
                    pass
            st["done"] += 1
            _write(_dir(d) / "oneri.json", st)
        st.update(state="done", finished=time.time())
    except Exception as e:  # noqa: BLE001
        log.exception("sfx suggest failed")
        st.update(state="failed", finished=time.time(),
                  error=("Efekt önerisi çıkarılamadı; Zeki AI'ye ulaşılamamış olabilir. Tekrar deneyin." if suggest
                         else "Efektli ses hazırlanamadı. Tekrar deneyin."))
        (d / "hata-efekt.txt").write_text(f"{type(e).__name__}: {e}")
    finally:
        with _run_lock:
            _running.discard(d.name)
        _write(_dir(d) / "oneri.json", st)
    return st


# ------------------------------------------------------------------ karışım
class NoNarration(RuntimeError):  # noqa: N818
    """Sayfanın anlatım sesi yok ya da güncel değil (önce seslendirilmeli)."""


def mix_path(d: Path, pid: str) -> Path:
    return d / DIR / "karisim" / f"{pid}.mp3"


def _active(rec: dict) -> tuple[list[dict], dict | None]:
    cues = [c for c in rec.get("cues", []) if c.get("chosen") and not c.get("lost") and c.get("kind") != "ortam"]
    amb = rec.get("ambience")
    amb = amb if amb and amb.get("chosen") and not amb.get("lost") else None
    return cues, amb


def mix_hash(nrec: dict, audio: Path, cues: list[dict], amb: dict | None) -> str:
    st = audio.stat()
    return _hash({"v": MIX_VERSION, "n": nrec.get("hash"), "a": [st.st_size, int(st.st_mtime)],
                  "c": [(c["chosen"], c["block"], c["words"], c["place"], c["gain_db"]) for c in cues],
                  "m": (amb["chosen"], amb["gain_db"]) if amb else None,
                  "L": [TARGET_LUFS, FX_LUFS, AMB_LUFS, FX_MAX_SEC, DUCK]})


def _word_time(nrec: dict, block: str, words: list[int]) -> tuple[float, float] | None:
    for b in nrec.get("blocks", []):
        if b["id"] != block:
            continue
        ts = [w for w in b["words"] if words[0] <= w["i"] <= words[1] and w.get("start") is not None]
        if ts:
            return float(ts[0]["start"]), float(ts[-1]["end"])
    return None


def plan_placements(nrec: dict, cues: list[dict]) -> list[dict]:
    out = []
    for c in cues:
        t = _word_time(nrec, c["block"], c["words"])
        if t is None:
            continue
        row = L.get(c["chosen"])
        if row is None:
            continue
        start = t[0] if c["place"] == "birlikte" else t[1]
        length = min(float(row.get("dur") or FX_MAX_SEC), FX_MAX_SEC)
        gain = FX_LUFS - float(row["lufs"]) if row.get("lufs") is not None else 0.0
        gain = max(-40.0, min(MAX_BOOST, gain)) + float(c.get("gain_db") or 0)
        out.append({"cue": c["id"], "sid": c["chosen"], "start": round(start, 3), "length": round(length, 3),
                    "gain_db": round(gain, 2), "place": c["place"], "quote": c["quote"], "title": row.get("title"),
                    "file": str(L.file_of(row))})
    return out


def _ffmpeg(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", *args], capture_output=True,
                          text=True, timeout=timeout, check=True)


def _loudnorm_measure(src: Path) -> dict:
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", str(src), "-af",
                        f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=600)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise RuntimeError("yükseklik ölçülemedi")
    return json.loads(m.group(0))


def render(narration_mp3: Path, duration: float, placements: list[dict], amb: dict | None, out: Path) -> dict:
    """Anlatım + efektler + ortam → out (mp3). Anlatım 0. saniyeden başlar, kesilmez; efekt kuyruğu sayfa sonunu
    geçerse sayfa sesi o kadar uzar (kelime zamanları aynı kalır)."""
    inputs = ["-i", str(narration_mp3)]
    filters = ["[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit=2[nar][key]"]
    fx_labels = []
    idx = 0
    for k, p in enumerate(placements):
        inputs += ["-i", p["file"]]
        idx += 1
        L_ = p["length"]
        ms = int(round(p["start"] * 1000))
        filters.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{L_:.3f},asetpts=PTS-STARTPTS,"
                       f"volume={p['gain_db']:.2f}dB,afade=t=in:d=0.01,afade=t=out:st={max(0.0, L_ - FX_FADE):.3f}:d={FX_FADE},"
                       f"adelay={ms}|{ms}[fx{k}]")
        fx_labels.append(f"[fx{k}]")
    end_fx = max([p["start"] + p["length"] for p in placements] + [duration])
    if amb:
        inputs += ["-stream_loop", "-1", "-i", amb["file"]]
        idx += 1
        filters.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,"
                       f"volume={amb['gain_db']:.2f}dB,afade=t=in:d={AMB_FADE},"
                       f"afade=t=out:st={max(0.0, duration - AMB_FADE):.3f}:d={AMB_FADE}[amb]")
        fx_labels.append("[amb]")
    if fx_labels:
        filters.append(f"{''.join(fx_labels)}amix=inputs={len(fx_labels)}:duration=longest:normalize=0[bus]")
        filters.append(f"[bus][key]sidechaincompress={DUCK}[ducked]")
        filters.append("[nar][ducked]amix=inputs=2:duration=longest:normalize=0[mix]")
    else:
        filters.append("[key]anullsink")
        filters.append("[nar]anull[mix]")
    tmp_wav = out.with_suffix(".tmp.wav")
    _ffmpeg([*inputs, "-filter_complex", ";".join(filters), "-map", "[mix]", "-t", f"{end_fx + 0.05:.3f}",
             "-c:a", "pcm_s16le", str(tmp_wav)])
    meas = _loudnorm_measure(tmp_wav)
    ln = (f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}"
          f":measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}"
          ":linear=true")
    tmp = out.with_suffix(".tmp.mp3")
    _ffmpeg(["-i", str(tmp_wav), "-af", f"{ln},aresample=44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "128k",
             str(tmp)])
    tmp_wav.unlink(missing_ok=True)
    tmp.replace(out)
    after = _loudnorm_measure(out)
    return {"lufs": float(after["input_i"]), "true_peak": float(after["input_tp"]), "duration": round(end_fx, 3)}


def mix_page(d: Path, pid: str) -> dict:
    """Sayfanın efektli sesini üretir (anlatım önbellekten). Efekt yoksa karışım silinir (sayfa anlatımla çalar)."""
    from . import narration as N
    nrec = N.page_record(d, pid)
    audio = N.audio_path(d, pid)
    if not nrec or not audio.exists():
        raise NoNarration(pid)
    rows = {r["id"]: r for r in N.status(d)}
    if rows.get(pid, {}).get("status") != "done":
        raise NoNarration(pid)
    rec = page_effects(d, pid)
    cues, amb = _active(rec)
    out = mix_path(d, pid)
    meta_p = out.with_suffix(".json")
    if not cues and not amb:
        out.unlink(missing_ok=True)
        meta_p.unlink(missing_ok=True)
        return {"page": pid, "status": "none"}
    h = mix_hash(nrec, audio, cues, amb)
    old = _read(meta_p)
    if old and old.get("hash") == h and out.exists():
        return {**old, "status": "done"}
    placements = plan_placements(nrec, cues)
    amb_p = None
    if amb:
        row = L.get(amb["chosen"])
        if row:
            gain = AMB_LUFS - float(row["lufs"]) if row.get("lufs") is not None else -20.0
            amb_p = {"sid": amb["chosen"], "file": str(L.file_of(row)), "title": row.get("title"),
                     "gain_db": round(max(-50.0, min(MAX_BOOST, gain)) + float(amb.get("gain_db") or 0), 2)}
    t0 = time.time()
    res = render(audio, float(nrec["duration"]), placements, amb_p, out)
    meta = {"version": MIX_VERSION, "page": pid, "hash": h, "narration_hash": nrec.get("hash"),
            "placements": [{k: v for k, v in p.items() if k != "file"} for p in placements],
            "ambience": {k: v for k, v in amb_p.items() if k != "file"} if amb_p else None,
            "narration_duration": nrec["duration"], **res, "target_lufs": TARGET_LUFS, "at": _now(),
            "seconds": round(time.time() - t0, 2)}
    _write(meta_p, meta)
    return {**meta, "status": "done"}


def mix_state(d: Path, pid: str, nrow: dict | None = None) -> str:
    """none (efekt yok) | done | stale (karışım eski/eksik) | no_audio (anlatım yok/güncel değil) | off (kapalı)."""
    from . import narration as N
    rec = _read(page_file(d, pid))
    if not rec:
        return "none"
    cues, amb = _active(rec)
    if not cues and not amb:
        return "none"
    st = (nrow or {}).get("status")
    if st is None:
        st = next((r["status"] for r in N.status(d) if r["id"] == pid), None)
    if st != "done":
        return "no_audio"
    try:
        rec = page_effects(d, pid)
    except Exception:  # noqa: BLE001
        return "stale"
    cues, amb = _active(rec)
    if not cues and not amb:
        return "none"
    out = mix_path(d, pid)
    meta = _read(out.with_suffix(".json"))
    nrec = N.page_record(d, pid) or {}
    if not meta or not out.exists():
        return "stale"
    return "done" if meta.get("hash") == mix_hash(nrec, N.audio_path(d, pid), cues, amb) else "stale"


def page_audio(job, pid: str, default: Path) -> Path:
    """Sayfanın çalınacak sesi: efektler açık ve karışım güncelse efektli dosya, değilse anlatım (`default`)."""
    from . import studio
    d = job if isinstance(job, Path) else studio.job_dir(str(job))
    try:
        if enabled(d) and mix_state(d, pid) == "done":
            return mix_path(d, pid)
    except Exception:  # noqa: BLE001 — efekt tarafı anlatımı asla düşürmez
        log.exception("sfx page_audio")
    return default


async def after_narration(d: Path, pid: str, by: str = "Zeki AI") -> None:
    """Sayfa sesi yeni yazıldı (narration kancası): efektler açıksa, sayfa hiç önerilmemişse önce öneri çıkarılır,
    sonra karışım yenilenir. Hata anlatımı düşürmez (çağıran yakalar)."""
    if not enabled(d):
        return
    rec = _read(page_file(d, pid))
    if (rec is None or not rec.get("suggested")) and L.available():
        await suggest_page(d, pid, by)
    try:
        await asyncio.to_thread(mix_page, d, pid)
    except NoNarration:
        pass


# ------------------------------------------------------------------ Türkçe arama → İngilizce karşılık
_TR_LOCK = threading.Lock()


def _tr_cache() -> Path:
    from . import studio
    return studio.root() / "_sfx" / "ceviri.json"


async def translate(text: str) -> str | None:
    """Kütüphane aramasında Türkçe tarifin kısa İngilizce karşılığı (Zeki AI; yayınevi düzeyinde önbellek). Model
    yoksa None: arama etiketlerle sürer."""
    key = " ".join(L.words(text))
    if not key:
        return None
    with _TR_LOCK:
        cache = _read(_tr_cache(), {}) or {}
    if key in cache:
        return cache[key]
    from ..llm import PromptRef
    from .run import FileLlm
    p = _tr_cache().parent
    p.mkdir(parents=True, exist_ok=True)
    llm = FileLlm(p / "provenance.jsonl")
    schema = {"type": "object", "additionalProperties": False, "required": ["en"],
              "properties": {"en": {"type": "string"}}}
    msg = ("Aşağıdaki ifade bir ses efekti kütüphanesinde aranacak. Sesin kısa İngilizce tarifini yaz "
           "(ör. «ördek vaklıyor» → \"duck quacking\", «uğuldayan rüzgâr» → \"howling wind\"). İfade zaten "
           "İngilizceyse olduğu gibi yaz. Yalnız tarif.\n\n" + text[:200])
    try:
        out, _ = await llm.chat(ALIAS, [{"role": "user", "content": msg}], prompt=PromptRef("sfx.translate", "1"),
                                schema=schema, max_tokens=60, temperature=0.0, thinking=False)
        en = str(out.get("en") or "").strip()[:120] or None
    except Exception:  # noqa: BLE001 — model yoksa etiket araması
        return None
    with _TR_LOCK:
        cache = _read(_tr_cache(), {}) or {}
        cache[key] = en
        _write(_tr_cache(), cache)
    return en


# ------------------------------------------------------------------ ekran
def page_view(d: Path, pid: str) -> dict:
    rec = page_effects(d, pid)
    lib = L.available()
    ids = {x for c in rec.get("cues", []) for x in ([c.get("chosen")] + (c.get("candidates") or [])) if x}
    amb = rec.get("ambience") or {}
    ids |= {x for x in [amb.get("chosen")] + (amb.get("candidates") or []) if x}
    sounds = {}
    if lib:
        for sid in ids:
            r = L.get(sid)
            if r:
                sounds[sid] = L.public(r)
    meta = _read(mix_path(d, pid).with_suffix(".json"))
    return {**rec, "sounds": sounds, "mix": {"state": mix_state(d, pid), "meta": meta}, "library": lib}


def overview(d: Path) -> dict:
    from . import narration as N
    from . import plan as plan_mod
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    rows = {r["id"]: r for r in N.status(d)}
    pages = []
    for pg in pl["pages"]:
        r = rows.get(pg["id"], {})
        if r.get("status") == "empty":
            continue
        rec = _read(page_file(d, pg["id"])) or {}
        cues, amb = _active(rec)
        pages.append({"id": pg["id"], "no": r.get("no"), "chapter": pg.get("chapter"),
                      "cues": len([c for c in rec.get("cues", []) if c.get("kind") != "ortam"]),
                      "active": len(cues), "ambience": bool(amb), "suggested": bool(rec.get("suggested")),
                      "lost": sum(1 for c in rec.get("cues", []) if c.get("lost")),
                      "mix": mix_state(d, pg["id"], r)})
    s = settings(d)
    lib = None
    if L.available():
        try:
            lib = L.stats()
        except Exception:  # noqa: BLE001
            lib = None
    return {"settings": s, "pages": pages, "run": run_state(d), "library": lib,
            "summary": {k: sum(1 for p in pages if p["mix"] == k) for k in ("done", "stale", "no_audio", "none")},
            "credits": credits(d)}


def used_sounds(d: Path) -> list[str]:
    ids = []
    for f in sorted((d / DIR / "sayfa").glob("*.json")):
        rec = _read(f) or {}
        cues, amb = _active(rec)
        ids += [c["chosen"] for c in cues]
        if amb:
            ids.append(amb["chosen"])
    return list(dict.fromkeys(ids))


def kunye_rows(d: Path) -> list[tuple[str, str]]:
    """Sesli e-kitabın künyesine: kullanılan efekt kaynakları (lisansıyla) ve atıf gereken her efekt ayrı satır."""
    if not enabled(d):
        return []
    c = credits(d)
    if not c["sources"]:
        return []
    rows = [("Ses efektleri", "; ".join(f"{s['label']} ({s['license']})" for s in c["sources"]))]
    rows += [("Ses efekti kaynağı", it["text"]) for it in c["items"]]
    return rows


def credits(d: Path) -> dict:
    """Kitap sonu «ses efektleri kaynakçası»: atıf gereken efektler + kullanılan kaynaklar."""
    if not L.available():
        return {"items": [], "sources": []}
    ids = used_sounds(d)
    return {"items": L.credits(ids), "sources": L.sources_used(ids)}
