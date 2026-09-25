"""Pazarlama kiti: arka kapak yazısı, e-ticaret ürün sayfası, sosyal medya görselleri, öğretmen okuma kılavuzu.

Kaynak kitabın kendi metnidir (iş klasöründeki el yazması; sayfa planı varsa planın düzeltilmiş metni). Metni yalnız
stüdyo servisi görür, bu yüzden metin üretimi burada, editör motorunda yapılır: model çağrısı gateway'den
(`book-director`, `FileLlm` → iş klasörünün `provenance.jsonl`'u). Köprü yalnız vekildir; SEO önerisine kaydı köprü
yapar (seo_geo), T-soft'a hiçbir şey gönderilmez.

Kitap bütünüyle okunur, kesilmez: bölümler `WINDOW_CHARS`'lık pencerelere bölünür (paragraf sınırından), her pencere
bir kez özetlenir (`pazarlama/ozet.json`, pencere metninin özetiyle önbellek; yarıda kalan iş kaldığı yerden sürer).
Arka kapak, ürün sayfası ve kılavuzun genel bölümleri bu özetten; kılavuzun bölüm soruları bölümün kendi metninden
yazılır. Alıntılar ve kelimeler metinde birebir aranır; bulunmayan düşer, sayısı ekranda yazılır.

Her üretim taslaktır; editör düzeltir ve onaylar (kim, ne zaman kaydedilir, `pazarlama/kayit.jsonl`). Onaysız çıktı
indirilemez, kapağa uygulanamaz, SEO'ya öneri olarak gönderilemez. Onaydan sonra yapılan düzeltme onayı düşürür.

Sosyal medya görselleri modelsiz dizilir (Pillow; kapak açılımından ön kapak, seçili iç sayfa resimleri, paletten
renk). Model üretimi görsel kullanan görsel `draft` işaretlidir: ekranda «taslak — ticari kullanım izni bekleniyor»,
indirilen dosyanın adı TASLAK- ile başlar.

Klasör `<iş>/pazarlama/`: isler.json (arka plan işleri), ozet.json, arka-kapak.json, urun.json, sosyal.json +
sosyal/*.png, kilavuz.json + kilavuz/kilavuz.pdf, kayit.jsonl.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import io
import json
import logging
import re
import secrets
import threading
import time
import zipfile
from pathlib import Path

from .. import cover_text as ct
from . import studio

log = logging.getLogger(__name__)

DIR = "pazarlama"
ALIAS = "book-director"
WINDOW_CHARS = 12000          # tek model çağrısına giden metin penceresi; kitap pencere pencere, bütünüyle okunur
KINDS = ("back-cover", "product", "guide")
TEMPLATES = {"kare": (1080, 1080), "dikey": (1080, 1920), "yatay": (1200, 628)}
TEMPLATE_LABEL = {"kare": "Kare 1080×1080", "dikey": "Dikey 1080×1920", "yatay": "Yatay 1200×628"}
VISUALS = ("cover", "page", "quote")
EFFECTS = ("plain", "shadow", "outline", "burst", "rainbow")
DRAFT_NOTE = "Taslak — ticari kullanım izni bekleniyor"
SOCIAL_ID = re.compile(r"^s_[0-9a-f]{8}$")
GENRE_TR = {"RESIMLI_OYKU": "Resimli öykü", "ILK_OKUMA": "İlk okuma", "COCUK_ROMANI": "Çocuk romanı",
            "GENCLIK_ROMANI": "Gençlik romanı", "YETISKIN_ROMANI": "Roman", "OYKU_KITABI": "Öykü",
            "SIIR": "Şiir", "KURGU_DISI_COCUK": "Çocuklar için bilgi kitabı", "KURGU_DISI": "Kurgu dışı"}
FICTION = {"RESIMLI_OYKU", "ILK_OKUMA", "COCUK_ROMANI", "GENCLIK_ROMANI", "YETISKIN_ROMANI", "OYKU_KITABI", "SIIR"}
PAPER_TR = {"kuse_130": "130 g mat kuşe", "hamur_70": "70 g 2. hamur"}
BINDING_TR = {"tel_dikis": "Tel dikiş", "amerikan_cilt": "Amerikan cilt"}

_io_lock = threading.Lock()
_running: dict[str, asyncio.Task] = {}
_digest_locks: dict[str, asyncio.Lock] = {}


class NotReady(ValueError):
    """Onay ya da önkoşul eksik (API 409)."""


# ------------------------------------------------------------------ depo
def mdir(d: Path) -> Path:
    p = d / DIR
    p.mkdir(exist_ok=True)
    return p


def _read(d: Path, name: str, default=None):
    return studio.read(mdir(d), name, default)


def _write(d: Path, name: str, obj) -> None:
    studio.write(mdir(d), name, obj)


def _now() -> float:
    return time.time()


def log_event(d: Path, by: str, what: str, **extra) -> None:
    with _io_lock, (mdir(d) / "kayit.jsonl").open("a") as f:
        f.write(json.dumps({"at": _now(), "by": by, "what": what, **extra}, ensure_ascii=False) + "\n")


def events(d: Path) -> list[dict]:
    p = mdir(d) / "kayit.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()][::-1]


def make_llm(d: Path):
    from .run import FileLlm
    return FileLlm(d / "provenance.jsonl")


# ------------------------------------------------------------------ kaynak metin
class Section:
    def __init__(self, i: int, title: str, text: str):
        self.i, self.title, self.text = i, title, text


def sections(d: Path) -> list[Section]:
    """Kitabın bölümleri ve metni. Sayfa planı varsa planın (editörün düzelttiği) metni, bölüm dizinine göre
    toplanır; yoksa el yazması. Başlığı olmayan bölüm «N. bölüm», tek bölümlü kitap «Kitabın tamamı»."""
    ms = studio._manuscript(d)
    from . import plan as plan_mod
    pl = plan_mod.load(d)
    groups: list[tuple[int | None, list[str]]] = []
    if pl is not None:
        for pg in pl["pages"]:
            parts = [plan_mod.page_text(pg)] + [bb["text"] for bb in pg.get("bubbles", [])]
            text = "\n\n".join(p for p in parts if p.strip())
            ch = pg.get("chapter")
            if groups and (ch is None or ch == groups[-1][0]):
                groups[-1][1].append(text)
            else:
                groups.append((ch, [text]))
    else:
        for ci, c in enumerate(ms.chapters):
            groups.append((ci, [b.text for b in c.blocks]))
    out = []
    for n, (ci, texts) in enumerate(groups):
        text = "\n\n".join(t for t in texts if t.strip())
        if not text.strip():
            continue
        title = ms.chapters[ci].title if ci is not None and 0 <= ci < len(ms.chapters) else None
        out.append(Section(len(out), (title or "").strip() or f"{n + 1}. bölüm", text))
    if len(out) == 1 and out[0].title == "1. bölüm":
        out[0].title = "Kitabın tamamı"
    return out


def windows(text: str, size: int | None = None) -> list[str]:
    """Metni paragraf sınırından en çok `size` (varsayılan WINDOW_CHARS) harflik parçalara böler; tek paragraf daha
    uzunsa cümle sınırından, o da olmazsa boşluktan. Hiçbir kelime düşmez: parçaların birleşimi metnin tamamıdır."""
    size = size or WINDOW_CHARS
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for p in paras:
        while len(p) > size:
            cut = max(p.rfind(". ", 0, size), p.rfind("! ", 0, size), p.rfind("? ", 0, size))
            cut = cut + 1 if cut > size // 3 else (p.rfind(" ", 0, size) if p.rfind(" ", 0, size) > 0 else size)
            pieces.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            pieces.append(p)
    out: list[str] = []
    for p in pieces:
        if out and len(out[-1]) + 2 + len(p) <= size:
            out[-1] += "\n\n" + p
        else:
            out.append(p)
    return out


def norm(s: str) -> str:
    s = (s or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("«", '"').replace("»", '"').replace("…", "...")
    s = re.sub(r"[–—]", "-", s)
    return re.sub(r"\s+", " ", s).strip().casefold()


def clean_quote(q: str) -> str:
    q = re.sub(r"\s+", " ", q or "").strip()
    q = re.sub(r"^[-–—]\s*", "", q)
    return q.strip("\"'“”«»‘’ ").strip()


def in_book(quote: str, book_norm: str) -> bool:
    q = norm(clean_quote(quote))
    return len(q) >= 3 and q in book_norm


def sentence_with(word: str, text: str) -> str | None:
    """Kelimenin (ekleriyle) geçtiği ilk cümle, metinden aynen."""
    w = re.escape(word.strip().casefold())
    for s in re.split(r"(?<=[.!?…])\s+", re.sub(r"\s+", " ", text)):
        if re.search(rf"(?<!\w){w}", s.casefold()):
            return s.strip()
    return None


# ------------------------------------------------------------------ kitap bilgileri (kesin; modelden değil)
def age_band(age_min: int | None, age_max: int | None) -> dict:
    a = age_max or 99
    label = f"{age_min}–{age_max} yaş" if age_min else "yetişkin"
    if a <= 8:
        return {"key": "erken", "label": label,
                "language": "çok kısa, somut cümleler; günlük kelimeler; her soruda tek fikir; soyut kavram yok"}
    if a <= 12:
        return {"key": "ilkokul", "label": label,
                "language": "kısa ve açık cümleler; soyut kavramı somut örnekle anlat; neden-sonuç sorulabilir"}
    if a <= 15:
        return {"key": "ortaokul", "label": label,
                "language": "orta uzunlukta cümleler; yorum, karşılaştırma ve karakter çözümlemesi"}
    return {"key": "ileri", "label": label,
            "language": "akıcı ve zengin dil; eleştirel düşünme, bağlam, tema ve üslup"}


def _profile(d: Path) -> dict:
    return studio.read(d, "profile.json") or {}


def facts(d: Path) -> list[dict]:
    """Ürün sayfasının kesin bilgileri: kitap kaydından, profilden, dizgiden ve baskı kurallarından. Model bu
    değerleri yazmaz, yalnız kullanır."""
    ms, prof, sp = studio._manuscript(d), _profile(d), studio.read(d, "spec.json") or {}
    rows = []

    def add(key, label, value, source):
        if value not in (None, "", []):
            rows.append({"key": key, "label": label, "value": str(value), "source": source})
    add("title", "Kitap adı", ms.title, "kitap kaydı")
    add("author", "Yazar", ms.author, "kitap kaydı")
    add("illustrator", "Çizer", ms.illustrator, "kitap kaydı")
    add("publisher", "Yayınevi", ms.meta.get("PUBLISHER"), "kitap kaydı")
    add("series", "Dizi", ms.meta.get("SERIES"), "kitap kaydı")
    add("isbn", "ISBN", ms.meta.get("ISBN"), "kitap kaydı")
    if prof.get("age_min"):
        add("age", "Yaş grubu", f"{prof['age_min']}–{prof['age_max']} yaş", prof.get("age_source") or "profil")
    add("genre", "Tür", ms.meta.get("GENRE") or GENRE_TR.get(prof.get("genre", ""), ""),
        "kitap kaydı" if ms.meta.get("GENRE") else "profil")
    try:
        pages = studio.page_count(d)
    except Exception:  # noqa: BLE001 - dizgi yoksa sayfa sayısı yazılmaz
        pages = None
    if pages:
        add("pages", "Sayfa sayısı", pages, "dizgi")
    if sp.get("trim_w"):
        add("size", "Boyut", f"{sp['trim_w'] / 10:g} × {sp['trim_h'] / 10:g} cm".replace(".", ","), "baskı kuralları")
        if pages:
            spec = studio._spec(d)
            add("binding", "Cilt", BINDING_TR.get(spec.binding(pages)), "baskı kuralları")
        add("paper", "Kâğıt", PAPER_TR.get(sp.get("paper", "")), "baskı kuralları")
    return rows


def _facts_text(rows: list[dict]) -> str:
    return "\n".join(f"- {r['label']}: {r['value']}" for r in rows) or "(bilgi yok)"


def _crm(d: Path) -> str:
    return (studio._manuscript(d).meta.get("CRM_SUMMARY") or "").strip() or "(yok)"


# ------------------------------------------------------------------ arka plan işleri
def _task_key(d: Path, kind: str) -> str:
    return f"{d.name}:{kind}"


def _set_task(d: Path, kind: str, **fields) -> None:
    with _io_lock:
        st = studio.read(mdir(d), "isler.json", {})
        st[kind] = {**st.get(kind, {}), **fields}
        studio.write(mdir(d), "isler.json", st)


def tasks(d: Path) -> dict:
    """Arka plan işlerinin durumu. «Sürüyor» görünen ama bu süreçte koşmayan iş (servis yeniden başladı) yarıda
    kalmış sayılır; yeniden başlatılınca biten pencereler önbellekten gelir."""
    st = studio.read(mdir(d), "isler.json", {})
    for kind, t in st.items():
        if t.get("status") == "running" and _task_key(d, kind) not in _running:
            t.update(status="failed", error="Üretim yarıda kaldı (servis yeniden başladı); yeniden başlatın, "
                                            "okunan bölümler saklı.")
    return st


def _public_error(e: Exception) -> str:
    if isinstance(e, (ValueError, KeyError, FileNotFoundError)) and str(e):
        return str(e)[:300]
    return "Zeki AI şu an yanıt vermiyor; birazdan yeniden deneyin."


def start(d: Path, kind: str, by: str, work) -> dict:
    """`work(progress)` eşzamansız işini bu süreçte arka planda başlatır; aynı iş sürüyorsa NotReady."""
    key = _task_key(d, kind)
    if key in _running and not _running[key].done():
        raise NotReady("Bu üretim zaten sürüyor.")
    _set_task(d, kind, status="running", by=by, started=_now(), finished=None, error=None, progress=None)

    async def run():
        try:
            await work(lambda n, total, what="": _set_task(d, kind, progress=[n, total], step=what))
            _set_task(d, kind, status="done", finished=_now())
        except Exception as e:  # noqa: BLE001 - durum ekranda görünür, ayrıntı günlükte
            log.exception("marketing %s failed", kind)
            _set_task(d, kind, status="failed", finished=_now(), error=_public_error(e))
        finally:
            _running.pop(key, None)
    _running[key] = asyncio.get_running_loop().create_task(run())
    return tasks(d)[kind]


# ------------------------------------------------------------------ özet (pencere pencere)
DIGEST_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "quotes", "terms"],
    "properties": {"summary": {"type": "string"}, "quotes": {"type": "array", "items": {"type": "string"}},
                   "terms": {"type": "array", "items": {"type": "string"}}}}


async def _ask(llm, name: str, schema: dict, max_tokens: int = 3000, temperature: float = 0.4, **kw) -> dict:
    from ..prompts import render
    ref, prompt = render(name, **kw)
    out, _ = await llm.chat(ALIAS, [{"role": "user", "content": prompt}], prompt=ref, schema=schema,
                            max_tokens=max_tokens, thinking=False, temperature=temperature)
    return out


def _kind_text(d: Path) -> str:
    p = _profile(d)
    g = GENRE_TR.get(p.get("genre", ""), "kitap")
    return f"{g}, {age_band(p.get('age_min'), p.get('age_max'))['label']} okur"


async def digest(d: Path, llm, progress=lambda n, t, w="": None) -> dict:
    """Bütün kitabın pencere pencere özeti: {"sections": [{"i","title","summary","parts":[…]}], "quotes": […],
    "terms": […]}. Pencere özeti metnin özetiyle anahtarlıdır: metin değişmediyse model yeniden çağrılmaz."""
    lock = _digest_locks.setdefault(d.name, asyncio.Lock())
    async with lock:
        secs = sections(d)
        cache = _read(d, "ozet.json", {"windows": {}}).get("windows", {})
        plan = [(s, i, w) for s in secs for i, w in enumerate(windows(s.text))]
        title = studio._manuscript(d).title
        kind = _kind_text(d)
        done = 0
        for s, i, w in plan:
            key = hashlib.sha256(w.encode()).hexdigest()[:24]
            if key not in cache:
                parts = sum(1 for x in plan if x[0] is s)
                where = s.title + (f", {i + 1}/{parts}. parça" if parts > 1 else "")
                cache[key] = await _ask(llm, "production_marketing_digest", DIGEST_SCHEMA, 2000, 0.2,
                                        where=where, title=title, kind=kind, text=w)
                _write(d, "ozet.json", {"windows": cache, "at": _now()})
            done += 1
            progress(done, len(plan), "Kitap okunuyor")
        book_norm = norm("\n".join(s.text for s in secs))
        out_secs, quotes, terms, dropped = [], [], [], 0
        for s in secs:
            parts = [cache[hashlib.sha256(w.encode()).hexdigest()[:24]] for w in windows(s.text)]
            out_secs.append({"i": s.i, "title": s.title, "summary": " ".join(p["summary"].strip() for p in parts),
                             "parts": [p["summary"].strip() for p in parts]})
            for p in parts:
                for q in p["quotes"]:
                    q = clean_quote(q)
                    if in_book(q, book_norm):
                        if q not in (x["text"] for x in quotes):
                            quotes.append({"text": q, "section": s.title})
                    else:
                        dropped += 1
                for t in p["terms"]:
                    t = t.strip()
                    if t and re.search(rf"(?<!\w){re.escape(t.casefold())}", book_norm) and t not in terms:
                        terms.append(t)
        return {"sections": out_secs, "quotes": quotes, "terms": terms, "dropped_quotes": dropped}


def _summary_text(dg: dict) -> str:
    return "\n".join(f"{s['title']}: {s['summary']}" for s in dg["sections"])


# ------------------------------------------------------------------ arka kapak
def back_geometry(d: Path) -> dict:
    """cover.typ'nin arka kapak yazı alanı (mm): genişlik ve başlığın üstünden en alttaki öğeye (yaş rozeti, dizi,
    barkod, yayınevi satırı) kadar kullanılabilir yükseklik; aradaki 4 mm boşluk bırakılır."""
    sp, prof, ms = studio._spec(d), _profile(d), studio._manuscript(d)
    top = sp.bleed + sp.safe + 4
    bottom = sp.bleed + sp.trim_h - sp.safe - 8                       # yayınevi satırı
    if prof.get("age_min"):
        bottom = min(bottom, sp.bleed + sp.trim_h - sp.safe - 30)    # yaş rozeti
    if ms.meta.get("SERIES"):
        bottom = min(bottom, sp.bleed + sp.trim_h - sp.safe - 18)
    if ms.meta.get("ISBN"):
        bottom = min(bottom, sp.bleed + sp.trim_h - sp.safe - 26)    # barkod
    return {"width": round(sp.trim_w - 2 * sp.safe, 2), "height": round(bottom - 4 - top, 2),
            "title": ms.title, "body_font": sp.body_font, "heading_font": sp.heading_font}


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n|\n", text or "") if p.strip()]


def back_heights(d: Path, texts: list[str]) -> list[float]:
    """Her metnin arka kapakta başlıkla birlikte kapladığı yükseklik (mm), cover.typ ile aynı dizgiyle ölçülür."""
    import typst
    g = back_geometry(d)
    wd = mdir(d) / "olcu"
    wd.mkdir(exist_ok=True)
    (wd / "measure.typ").write_text((Path(__file__).parent / "templates" / "marketing" / "measure.typ").read_text())
    (wd / "olcu.json").write_text(json.dumps({**g, "texts": [paragraphs(t) for t in texts]}, ensure_ascii=False))
    raw = typst.query(str(wd / "measure.typ"), "<olcu>", field="value", one=True, root=str(wd),
                      font_paths=[str(studio.fonts())], ignore_system_fonts=True, sys_inputs={"data": "olcu.json"})
    return [float(x) for x in json.loads(raw)]


def back_capacity(d: Path, sample: str) -> dict:
    """Alana sığan yaklaşık kelime sayısı: kitabın kendi metninden bir örnek ölçülür, yükseklik oranıyla ölçeklenir."""
    g = back_geometry(d)
    words = sample.split()[:220]
    base, h = back_heights(d, ["", " ".join(words)])
    per_word = max(0.01, (h - base) / max(1, len(words)))
    n = int((g["height"] - base) / per_word)
    return {"words": max(20, n), "height_mm": g["height"], "width_mm": g["width"]}


def _fit_info(d: Path, texts: list[str]) -> list[dict]:
    g = back_geometry(d)
    hs = back_heights(d, texts)
    return [{"height_mm": round(h, 1), "fill": round(h / g["height"], 3), "fits": h <= g["height"] + 0.01}
            for h in hs]


BACK_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["options"],
    "properties": {"options": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["angle", "text"],
        "properties": {"angle": {"type": "string"}, "text": {"type": "string"}}}}}}


async def gen_back(d: Path, llm, by: str, progress=lambda n, t, w="": None) -> dict:
    dg = await digest(d, llm, progress)
    prof, ms = _profile(d), studio._manuscript(d)
    cap = back_capacity(d, " ".join(s.text for s in sections(d)))
    n = cap["words"]
    targets = [max(15, int(n * 0.55)), max(20, int(n * 0.75)), max(25, int(n * 0.92))]
    band = age_band(prof.get("age_min"), prof.get("age_max"))
    progress(0, 1, "Arka kapak yazılıyor")
    out = await _ask(llm, "production_back_cover", BACK_SCHEMA, 3000, 0.6,
                     title=ms.title, author=ms.author or "-", genre=GENRE_TR.get(prof.get("genre", ""), "-"),
                     age=band["label"], tone=", ".join(prof.get("tone") or []) or "-", language=band["language"],
                     crm=_crm(d), summary=_summary_text(dg), words_short=str(targets[0]), words_mid=str(targets[1]),
                     words_long=str(targets[2]))
    opts = [{"id": f"o{i + 1}", "angle": o["angle"].strip(), "text": "\n\n".join(paragraphs(o["text"]))}
            for i, o in enumerate(out["options"]) if o["text"].strip()]
    if not opts:
        raise ValueError("Zeki AI arka kapak yazısı üretemedi; yeniden deneyin.")
    # Alana sığmayan seçenek bir kez kısaltılır (ölçülen taşma oranıyla); yine sığmazsa işaretli kalır.
    for o, f in zip(opts, _fit_info(d, [o["text"] for o in opts])):
        if not f["fits"]:
            want = max(15, int(len(o["text"].split()) / f["fill"] * 0.92))
            again = await _ask(llm, "production_back_cover", BACK_SCHEMA, 2000, 0.4,
                               title=ms.title, author=ms.author or "-", genre=GENRE_TR.get(prof.get("genre", ""), "-"),
                               age=band["label"], tone=", ".join(prof.get("tone") or []) or "-",
                               language=band["language"], crm="(yok)", summary=o["text"],
                               words_short=str(want), words_mid=str(want), words_long=str(want))
            if again["options"]:
                o["text"] = "\n\n".join(paragraphs(again["options"][0]["text"])) or o["text"]
    for o, f in zip(opts, _fit_info(d, [o["text"] for o in opts])):
        o.update(words=len(o["text"].split()), **f)
    old = _read(d, "arka-kapak.json", {})
    _write(d, "arka-kapak.json", {**old, "options": opts, "capacity": cap, "generated_by": by, "generated_at": _now(),
                                  "draft": old.get("draft") or {"text": opts[0]["text"], "by": by, "at": _now(),
                                                                "from": opts[0]["id"],
                                                                **{k: opts[0][k] for k in ("height_mm", "fill", "fits")}}})
    log_event(d, by, "arka kapak üretildi", options=len(opts))
    progress(1, 1, "Arka kapak yazıldı")
    return _read(d, "arka-kapak.json")


def _clean_text(text: str) -> str:
    text = "\n\n".join(paragraphs(text))
    if not text:
        raise ValueError("Yazı boş olamaz.")
    return text


def save_back(d: Path, text: str, by: str) -> dict:
    """Editörün düzelttiği taslak; onay varsa düşer (onaylanan metin değiştiyse)."""
    st = _read(d, "arka-kapak.json", {})
    text = _clean_text(text)
    st["draft"] = {"text": text, "by": by, "at": _now(), **_fit_info(d, [text])[0]}
    if st.get("approved") and st["approved"]["text"] != text:
        st["approved"] = None
    _write(d, "arka-kapak.json", st)
    return back_view(d)


def approve_back(d: Path, text: str, by: str) -> dict:
    st = _read(d, "arka-kapak.json", {})
    text = _clean_text(text)
    fit = _fit_info(d, [text])[0]
    st["draft"] = {"text": text, "by": by, "at": _now(), **fit}
    st["approved"] = {"text": text, "by": by, "at": _now(), **fit}
    _write(d, "arka-kapak.json", st)
    log_event(d, by, "arka kapak onaylandı", words=len(text.split()))
    return back_view(d)


def apply_back(d: Path, by: str) -> dict:
    """Onaylı yazıyı kapağa uygular: kapak açılımı yeniden dizilir (cover.py bu dosyayı okur), ön kontrol yenilenir.
    Alana sığmıyorsa da uygulanır (engellemez), uyarı döner."""
    st = _read(d, "arka-kapak.json", {})
    if not st.get("approved"):
        raise NotReady("Önce yazıyı onaylayın; kapağa yalnız onaylı yazı uygulanır.")
    st["applied"] = {"text": st["approved"]["text"], "by": by, "at": _now()}
    _write(d, "arka-kapak.json", st)
    _rebuild_cover(d)
    log_event(d, by, "arka kapak kapağa uygulandı")
    return back_view(d)


def revert_back(d: Path, by: str) -> dict:
    st = _read(d, "arka-kapak.json", {})
    st["applied"] = None
    _write(d, "arka-kapak.json", st)
    _rebuild_cover(d)
    log_event(d, by, "arka kapak kayıtlı tanıtım metnine döndü")
    return back_view(d)


def _rebuild_cover(d: Path) -> None:
    from . import plan as plan_mod
    with plan_mod._locked(d):
        studio.build_cover(d)
    studio.refresh_preflight(d)


def applied_back_text(job_dir: Path) -> str | None:
    """cover.py'nin kancası: kapağa uygulanmış arka kapak yazısı (yoksa None → CRM tanıtım metni)."""
    p = job_dir / DIR / "arka-kapak.json"
    if not p.exists():
        return None
    a = (json.loads(p.read_text()) or {}).get("applied")
    return a["text"] if a and a.get("text") else None


def back_view(d: Path) -> dict:
    st = _read(d, "arka-kapak.json", {})
    try:
        g = back_geometry(d)
    except Exception:  # noqa: BLE001 - spec yoksa alan bilgisi yok
        g = None
    crm = _crm(d)
    return {"options": st.get("options", []), "capacity": st.get("capacity"),
            "area": g and {"width_mm": g["width"], "height_mm": g["height"]}, "draft": st.get("draft"),
            "approved": st.get("approved"), "applied": st.get("applied"), "crm": "" if crm == "(yok)" else crm,
            "generated_by": st.get("generated_by"), "generated_at": st.get("generated_at")}


# ------------------------------------------------------------------ ürün sayfası
PRODUCT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["title", "seo_title", "short", "long", "highlights", "keywords", "meta", "faq"],
    "properties": {
        "title": {"type": "string"}, "seo_title": {"type": "string"}, "short": {"type": "string"},
        "long": {"type": "array", "items": {"type": "string"}},
        "highlights": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}}, "meta": {"type": "string"},
        "faq": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["q", "a"],
                                           "properties": {"q": {"type": "string"}, "a": {"type": "string"}}}}}}
DEFAULT_LIMITS = {"title_min": 30, "title_max": 65, "meta_min": 120, "meta_max": 160, "desc_min_words": 150}


def _cut(text: str, limit: int) -> str:
    """Sınırı aşan metni cümle sonundan, yoksa kelime sınırından keser (seo_geo.propose._cut ile aynı kural)."""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[:limit]
    end = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    if end >= limit * 0.6:
        return head[:end + 1].strip()
    return head[:head.rfind(" ")].rstrip(" ,;:-–") if " " in head else head


def limits(raw: dict | None) -> dict:
    out = dict(DEFAULT_LIMITS)
    for k, v in (raw or {}).items():
        if k in out:
            out[k] = max(1, int(v))
    return out


def _clean_page(page: dict, lim: dict) -> dict:
    s = lambda v: re.sub(r"\s+", " ", str(v or "")).strip()  # noqa: E731
    title = s(page.get("seo_title"))
    if len(title) > lim["title_max"] and " | " in title:
        title = title.rsplit(" | ", 1)[0].strip()
    return {"title": s(page.get("title")), "seo_title": _cut(title, lim["title_max"]), "short": s(page.get("short")),
            "long": [s(p) for p in page.get("long") or [] if s(p)],
            "highlights": [s(p) for p in page.get("highlights") or [] if s(p)],
            "keywords": list(dict.fromkeys(s(k) for k in page.get("keywords") or [] if s(k))),
            "meta": _cut(s(page.get("meta")), lim["meta_max"]),
            "faq": [{"q": s(f.get("q")), "a": s(f.get("a"))} for f in page.get("faq") or [] if s(f.get("q")) and s(f.get("a"))],
            "facts": [{"key": s(r.get("key")), "label": s(r.get("label")), "value": s(r.get("value")),
                       "source": s(r.get("source"))} for r in page.get("facts") or [] if s(r.get("label")) and s(r.get("value"))]}


def checks(page: dict, lim: dict) -> list[dict]:
    """Uzunluk sayaçları (ekranda yeşil/kırmızı): SEO kurallarıyla aynı eşikler."""
    words = len(" ".join(page["long"]).split())
    return [
        {"field": "seo_title", "label": "SEO başlığı", "value": len(page["seo_title"]), "unit": "karakter",
         "min": lim["title_min"], "max": lim["title_max"],
         "ok": lim["title_min"] <= len(page["seo_title"]) <= lim["title_max"]},
        {"field": "meta", "label": "Meta açıklama", "value": len(page["meta"]), "unit": "karakter",
         "min": lim["meta_min"], "max": lim["meta_max"], "ok": lim["meta_min"] <= len(page["meta"]) <= lim["meta_max"]},
        {"field": "long", "label": "Uzun açıklama", "value": words, "unit": "kelime", "min": lim["desc_min_words"],
         "max": None, "ok": words >= lim["desc_min_words"]},
        {"field": "keywords", "label": "Anahtar kelime", "value": len(page["keywords"]), "unit": "adet", "min": 5,
         "max": None, "ok": len(page["keywords"]) >= 5},
    ]


async def gen_product(d: Path, llm, by: str, lim: dict, progress=lambda n, t, w="": None) -> dict:
    dg = await digest(d, llm, progress)
    prof = _profile(d)
    rows = facts(d)
    band = age_band(prof.get("age_min"), prof.get("age_max"))
    progress(0, 1, "Ürün sayfası yazılıyor")
    out = await _ask(llm, "production_product_page", PRODUCT_SCHEMA, 4000, 0.5, facts=_facts_text(rows),
                     language=band["language"], crm=_crm(d), summary=_summary_text(dg),
                     **{k: str(v) for k, v in lim.items()})
    page = _clean_page({**out, "facts": rows}, lim)
    old = _read(d, "urun.json", {})
    _write(d, "urun.json", {**old, "page": page, "limits": lim, "approved": None, "generated_by": by,
                            "generated_at": _now()})
    log_event(d, by, "ürün sayfası üretildi")
    progress(1, 1, "Ürün sayfası yazıldı")
    return product_view(d)


def save_product(d: Path, page: dict, by: str, approve: bool = False) -> dict:
    st = _read(d, "urun.json", {})
    if not st.get("page"):
        raise NotReady("Önce ürün sayfasını üretin.")
    lim = limits(st.get("limits"))
    clean = _clean_page(page, lim)
    if not clean["title"] or not clean["long"]:
        raise ValueError("Başlık ve uzun açıklama boş olamaz.")
    changed = clean != st["page"]
    st["page"], st["edited_by"], st["edited_at"] = clean, by, _now()
    if approve:
        st["approved"] = {"by": by, "at": _now()}
        log_event(d, by, "ürün sayfası onaylandı")
    elif changed:
        st["approved"] = None
    _write(d, "urun.json", st)
    return product_view(d)


def product_html(page: dict) -> str:
    e = html.escape
    out = [f"<p><strong>{e(page['short'])}</strong></p>"] if page["short"] else []
    out += [f"<p>{e(p)}</p>" for p in page["long"]]
    if page["highlights"]:
        out.append("<h3>Öne çıkanlar</h3><ul>" + "".join(f"<li>{e(h)}</li>" for h in page["highlights"]) + "</ul>")
    if page["facts"]:
        out.append("<h3>Kitap bilgileri</h3><ul>" + "".join(
            f"<li><strong>{e(r['label'])}:</strong> {e(r['value'])}</li>" for r in page["facts"]) + "</ul>")
    if page["faq"]:
        out.append("<h3>Sıkça Sorulan Sorular</h3>" + "".join(
            f"<p><strong>{e(f['q'])}</strong><br>{e(f['a'])}</p>" for f in page["faq"]))
    return "\n".join(out)


def product_text(page: dict) -> str:
    out = [page["title"], "", page["short"], ""] + [p + "\n" for p in page["long"]]
    if page["highlights"]:
        out += ["Öne çıkanlar:"] + [f"• {h}" for h in page["highlights"]] + [""]
    if page["facts"]:
        out += ["Kitap bilgileri:"] + [f"{r['label']}: {r['value']}" for r in page["facts"]] + [""]
    if page["faq"]:
        out += ["Sıkça sorulan sorular:"] + [f"{f['q']}\n{f['a']}\n" for f in page["faq"]]
    out += [f"SEO başlığı: {page['seo_title']}", f"Meta açıklama: {page['meta']}",
            f"Anahtar kelimeler: {', '.join(page['keywords'])}"]
    return "\n".join(out).strip() + "\n"


def seo_fields(page: dict) -> dict[str, str]:
    """SEO modülünün öneri alanları (seo_geo.propose.FIELDS)."""
    return {"SeoTitle": page["seo_title"], "SeoDescription": page["meta"],
            "SearchKeywords": ", ".join(page["keywords"]), "Details": product_html(page)}


def link_seo(d: Path, product_id: str, proposal_id: str, by: str) -> dict:
    st = _read(d, "urun.json", {})
    if not st.get("approved"):
        raise NotReady("Önce ürün sayfasını onaylayın.")
    st.setdefault("seo", []).append({"product_id": product_id, "proposal_id": proposal_id, "by": by, "at": _now()})
    _write(d, "urun.json", st)
    log_event(d, by, "ürün sayfası SEO önerisi olarak kaydedildi", product=product_id, proposal=proposal_id)
    return product_view(d)


def product_view(d: Path) -> dict:
    st = _read(d, "urun.json", {})
    page = st.get("page")
    lim = limits(st.get("limits"))
    return {"page": page, "facts": facts(d) if page is None else page["facts"], "limits": lim,
            "checks": checks(page, lim) if page else [], "approved": st.get("approved"),
            "generated_by": st.get("generated_by"), "generated_at": st.get("generated_at"),
            "seo": st.get("seo", []), "seo_fields": seo_fields(page) if page and st.get("approved") else None,
            "html": product_html(page) if page else None}


def product_export(d: Path, fmt: str) -> tuple[bytes, str, str]:
    st = _read(d, "urun.json", {})
    if not st.get("approved"):
        raise NotReady("Onaylanmamış ürün sayfası indirilemez.")
    page = st["page"]
    if fmt == "html":
        doc = (f"<!doctype html><html lang=\"tr\"><head><meta charset=\"utf-8\"><title>{html.escape(page['seo_title'])}"
               f"</title><meta name=\"description\" content=\"{html.escape(page['meta'])}\">"
               f"<meta name=\"keywords\" content=\"{html.escape(', '.join(page['keywords']))}\"></head><body>"
               f"<h1>{html.escape(page['title'])}</h1>\n{product_html(page)}\n</body></html>\n")
        return doc.encode(), "text/html; charset=utf-8", "urun-sayfasi.html"
    if fmt == "json":
        return (json.dumps({**page, "details_html": product_html(page)}, ensure_ascii=False, indent=1).encode(),
                "application/json", "urun-sayfasi.json")
    return product_text(page).encode(), "text/plain; charset=utf-8", "urun-sayfasi.txt"


# ------------------------------------------------------------------ öğretmen kılavuzu
GUIDE_BOOK_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "values", "outcomes", "vocabulary", "activities"],
    "properties": {
        "summary": {"type": "array", "items": {"type": "string"}},
        "values": {"type": "array", "items": {"type": "string"}},
        "outcomes": {"type": "array", "items": {"type": "string"}},
        "vocabulary": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                  "required": ["word", "meaning"],
                                                  "properties": {"word": {"type": "string"},
                                                                 "meaning": {"type": "string"}}}},
        "activities": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                  "required": ["title", "steps", "duration"],
                                                  "properties": {"title": {"type": "string"}, "steps": {"type": "string"},
                                                                 "duration": {"type": "string"}}}}}}
GUIDE_SECTION_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["before", "during", "after"],
    "properties": {k: {"type": "array", "items": {"type": "string"}} for k in ("before", "during", "after")}}


def guide_sections(d: Path) -> list[tuple[str, str]]:
    """Kılavuzun «bölüm bölüm» birimleri: kitabın bölümleri; tek bölümlü uzun kitapta pencereler («1. kısım» …)."""
    secs = sections(d)
    if len(secs) == 1:
        parts = windows(secs[0].text)
        if len(parts) > 1:
            return [(f"{i + 1}. kısım", w) for i, w in enumerate(parts)]
    out = []
    for s in secs:
        parts = windows(s.text)
        out += [(s.title if len(parts) == 1 else f"{s.title} ({i + 1}. kısım)", w) for i, w in enumerate(parts)]
    return out


async def gen_guide(d: Path, llm, by: str, progress=lambda n, t, w="": None) -> dict:
    dg = await digest(d, llm, progress)
    prof, ms = _profile(d), studio._manuscript(d)
    band = age_band(prof.get("age_min"), prof.get("age_max"))
    units = guide_sections(d)
    total = len(units) + 1
    progress(0, total, "Kılavuz yazılıyor")
    book = await _ask(llm, "production_guide_book", GUIDE_BOOK_SCHEMA, 5000, 0.5, title=ms.title,
                      author=ms.author or "-", genre=GENRE_TR.get(prof.get("genre", ""), "-"), age=band["label"],
                      language=band["language"], summary=_summary_text(dg), terms=", ".join(dg["terms"]) or "(yok)")
    progress(1, total, "Kılavuz yazılıyor")
    cached = {s["key"]: s for s in (_read(d, "kilavuz.json", {}).get("section_cache") or [])}
    secs = []
    for i, (title, text) in enumerate(units):
        key = hashlib.sha256((band["key"] + text).encode()).hexdigest()[:24]
        if key not in cached:
            out = await _ask(llm, "production_guide_section", GUIDE_SECTION_SCHEMA, 2000, 0.5, title=ms.title,
                             age=band["label"], language=band["language"], section=title, text=text)
            cached[key] = {"key": key, **{k: [q.strip() for q in out[k] if q.strip()] for k in ("before", "during", "after")}}
            _write(d, "kilavuz.json", {**_read(d, "kilavuz.json", {}), "section_cache": list(cached.values())})
        secs.append({"title": title, **{k: cached[key][k] for k in ("before", "during", "after")}})
        progress(i + 2, total, "Kılavuz yazılıyor")
    full = "\n".join(s.text for s in sections(d))
    vocab, dropped = [], []
    for v in book["vocabulary"]:
        sent = sentence_with(v["word"], full)
        if sent:
            vocab.append({"word": v["word"].strip(), "meaning": v["meaning"].strip(), "sentence": sent})
        else:
            dropped.append(v["word"])
    guide = {"summary": [p.strip() for p in book["summary"] if p.strip()], "values": book["values"],
             "outcomes": book["outcomes"], "vocabulary": vocab, "activities": book["activities"], "sections": secs,
             "band": band}
    st = _read(d, "kilavuz.json", {})
    st.update(guide=guide, approved=None, generated_by=by, generated_at=_now(),
              notes=[f"Kitapta geçmeyen {len(dropped)} kelime çıkarıldı: {', '.join(dropped)}"] if dropped else [])
    _write(d, "kilavuz.json", st)
    (mdir(d) / "kilavuz" / "kilavuz.pdf").unlink(missing_ok=True)
    log_event(d, by, "öğretmen kılavuzu üretildi", sections=len(secs))
    return guide_view(d)


def _clean_guide(g: dict) -> dict:
    s = lambda v: re.sub(r"[ \t]+", " ", str(v or "")).strip()  # noqa: E731
    lst = lambda v: [s(x) for x in v or [] if s(x)]  # noqa: E731
    return {"summary": lst(g.get("summary")), "values": lst(g.get("values")), "outcomes": lst(g.get("outcomes")),
            "vocabulary": [{"word": s(v.get("word")), "meaning": s(v.get("meaning")), "sentence": s(v.get("sentence"))}
                           for v in g.get("vocabulary") or [] if s(v.get("word"))],
            "activities": [{"title": s(a.get("title")), "steps": s(a.get("steps")), "duration": s(a.get("duration"))}
                           for a in g.get("activities") or [] if s(a.get("title"))],
            "sections": [{"title": s(x.get("title")), **{k: lst(x.get(k)) for k in ("before", "during", "after")}}
                         for x in g.get("sections") or [] if s(x.get("title"))],
            "band": g.get("band")}


def save_guide(d: Path, guide: dict, by: str, approve: bool = False) -> dict:
    st = _read(d, "kilavuz.json", {})
    if not st.get("guide"):
        raise NotReady("Önce kılavuzu üretin.")
    clean = _clean_guide({**guide, "band": st["guide"].get("band")})
    if not clean["summary"]:
        raise ValueError("Özet boş olamaz.")
    changed = clean != st["guide"]
    st["guide"], st["edited_by"], st["edited_at"] = clean, by, _now()
    if approve:
        st["approved"] = {"by": by, "at": _now()}
    elif changed:
        st["approved"] = None
        (mdir(d) / "kilavuz" / "kilavuz.pdf").unlink(missing_ok=True)
    _write(d, "kilavuz.json", st)
    if approve:
        try:
            build_guide_pdf(d)
        except Exception as e:
            log.exception("guide pdf failed")
            st["approved"] = None
            _write(d, "kilavuz.json", st)
            raise ValueError(f"Kılavuz PDF'i dizilemedi, onay kaydedilmedi: {str(e)[:200]}") from None
        log_event(d, by, "öğretmen kılavuzu onaylandı, PDF dizildi")
    return guide_view(d)


def _tr_time(t: float) -> str:
    """Türkiye saati (UTC+3, yaz saati uygulaması yok)."""
    from datetime import datetime, timedelta, timezone
    return datetime.fromtimestamp(t, timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M")


def _accent(d: Path) -> str:
    ap = studio.read(d, "artplan.json") or {}
    return ((ap.get("style") or {}).get("accent")) or "#1F3B73"


def build_guide_pdf(d: Path) -> Path:
    import typst
    st = _read(d, "kilavuz.json", {})
    if not st.get("approved"):
        raise NotReady("Önce kılavuzu onaylayın; PDF onaylı içerikten dizilir.")
    g, ms, sp, prof = st["guide"], studio._manuscript(d), studio._spec(d), _profile(d)
    wd = mdir(d) / "kilavuz"
    wd.mkdir(exist_ok=True)
    (wd / "guide.typ").write_text((Path(__file__).parent / "templates" / "marketing" / "guide.typ").read_text())
    cover = None
    try:
        _cover_front(d, 900).save(wd / "kapak-on.png")
        cover = "kapak-on.png"
    except Exception:  # noqa: BLE001 - kapak henüz dizilmediyse kılavuz kapaksız çıkar
        pass
    rows = {r["key"]: r["value"] for r in facts(d)}
    reading = prof.get("reading") or {}
    chips = [x for x in (rows.get("age"), rows.get("genre"), f"{rows['pages']} sayfa" if rows.get("pages") else None) if x]
    read_rows = [{"label": "Hedef yaş", "value": rows.get("age") or "belirtilmemiş"},
                 {"label": "Dil düzeyi", "value": (g.get("band") or {}).get("language", "")}]
    if reading.get("words"):
        read_rows.append({"label": "Kelime sayısı", "value": f"{reading['words']:,}".replace(",", ".")})
    if reading.get("words_per_sentence"):
        read_rows.append({"label": "Ortalama cümle", "value": f"{reading['words_per_sentence']:g} kelime".replace(".", ",")})
    if reading.get("chapters"):
        read_rows.append({"label": "Bölüm sayısı", "value": str(reading["chapters"])})
    ap = st["approved"]
    data = {"title": ms.title, "author": ms.author or "", "publisher": ms.meta.get("PUBLISHER") or "",
            "accent": _accent(d), "body_font": sp.body_font, "heading_font": sp.heading_font,
            "label": ct.tr_upper("Öğretmen okuma kılavuzu"), "chips": chips, "cover_image": cover,
            "reading": read_rows, **{k: g[k] for k in ("summary", "values", "outcomes", "vocabulary", "activities",
                                                        "sections")},
            "approval": f"Hazırlayan: Zeki AI · Editör onayı: {ap['by']}, {_tr_time(ap['at'])}"}
    (wd / "kilavuz.json").write_text(json.dumps(data, ensure_ascii=False))
    out = wd / "kilavuz.pdf"
    typst.compile(str(wd / "guide.typ"), output=str(out), root=str(wd), font_paths=[str(studio.fonts())],
                  ignore_system_fonts=True, sys_inputs={"data": "kilavuz.json"})
    return out


def guide_pdf(d: Path) -> Path:
    st = _read(d, "kilavuz.json", {})
    if not st.get("approved"):
        raise NotReady("Onaylanmamış kılavuzun PDF'i yok.")
    out = mdir(d) / "kilavuz" / "kilavuz.pdf"
    return out if out.exists() else build_guide_pdf(d)


def guide_view(d: Path) -> dict:
    st = _read(d, "kilavuz.json", {})
    return {"guide": st.get("guide"), "approved": st.get("approved"), "notes": st.get("notes", []),
            "generated_by": st.get("generated_by"), "generated_at": st.get("generated_at"),
            "pdf": bool(st.get("approved")) and (mdir(d) / "kilavuz" / "kilavuz.pdf").exists()}


# ------------------------------------------------------------------ sosyal medya görselleri (modelsiz)
def palette_colors(d: Path) -> list[str]:
    from . import plan as plan_mod
    pl = plan_mod.load(d) or {}
    ap = studio.read(d, "artplan.json") or {}
    cols = [c["hex"] for c in (pl.get("palette") or {}).get("colors", []) if c.get("hex")]
    cols += list((ap.get("style") or {}).get("palette") or [])
    cols += [(ap.get("style") or {}).get("accent") or "#1F3B73", "#2C2C2A", "#FBF7EE"]
    return [c.upper() for c in dict.fromkeys(c.upper() for c in cols if re.fullmatch(r"#[0-9A-Fa-f]{6}", c or ""))]


def _cover_front(d: Path, height: int):
    """Kapak açılımının ön kapağı (kesim kutusu), yazısıyla birlikte, PDF'ten dizildiği gibi."""
    import pymupdf
    from PIL import Image
    pdf = d / "kapak" / "kapak.pdf"
    info = studio.read(d, "cover.json")
    if not pdf.exists() or not info:
        raise FileNotFoundError("Kapak henüz dizilmedi.")
    sp = studio._spec(d)
    mm = 72 / 25.4
    W = info["size_mm"][0]
    x0 = W - sp.bleed - sp.trim_w
    clip = pymupdf.Rect(x0 * mm, sp.bleed * mm, (x0 + sp.trim_w) * mm, (sp.bleed + sp.trim_h) * mm)
    zoom = height / clip.height
    pix = pymupdf.open(pdf)[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def social_sources(d: Path) -> list[dict]:
    """Seçilebilir görseller: ön kapak, basılan iç sayfa resimleri (seçili sürüm), yüklenen fotoğraflar. `draft`:
    görsel modelin ürettiği (ticari kullanım izni bekleniyor)."""
    from . import plan as plan_mod
    out = []
    art = studio.selected_art(d)
    if (d / "kapak" / "kapak.pdf").exists():
        out.append({"key": "kapak", "label": "Ön kapak", "kind": "cover", "draft": "kapak" in art})
    pl = plan_mod.load(d)
    if pl is not None:
        for no, aid in plan_mod.printed_art(pl):
            if aid in art:
                out.append({"key": aid, "label": f"Sayfa {no} resmi", "kind": "art", "draft": True})
        for gid, a in (pl.get("assets") or {}).items():
            if a.get("kind") == "photo" and not a.get("derived_from"):
                out.append({"key": gid, "label": a.get("name") or "Fotoğraf", "kind": "photo", "draft": False})
            elif a.get("kind") == "figure":
                out.append({"key": gid, "label": f"Figür: {a.get('prompt') or gid}"[:60], "kind": "figure",
                            "draft": True})
    else:
        try:
            printed = studio._pagemap(d).art_pages()
        except Exception:  # noqa: BLE001 - sayfa haritası yoksa iç resim yok
            printed = set()
        for key in sorted((k for k in art if k.isdigit() and int(k) in printed), key=int):
            out.append({"key": key, "label": f"Sayfa {key} resmi", "kind": "art", "draft": True})
    return out


def source_image(d: Path, key: str, height: int = 1600):
    from PIL import Image

    from . import plan as plan_mod
    src = {s["key"]: s for s in social_sources(d)}
    if key not in src:
        raise KeyError("Görsel bulunamadı.")
    if key == "kapak":
        return _cover_front(d, height)
    if src[key]["kind"] in ("photo", "figure"):
        pl = plan_mod.load(d)
        im = Image.open(d / pl["assets"][key]["path"])
        if im.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", im.size, "#FFFFFF")
            im = im.convert("RGBA")
            bg.paste(im, (0, 0), im)
            return bg
        return im.convert("RGB")
    return Image.open(studio.selected_art(d)[key]).convert("RGB")


def _font(face: ct.Face, size: int):
    return ct._font(face, max(8, int(size)))


def _wrap(text: str, font, width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split():
            t = f"{cur} {w}".strip()
            if not cur or ct._width(font, t) <= width:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return lines


def _fit(text: str, face: ct.Face, box_w: int, box_h: int, leading: float, max_size: int, min_size: int):
    size = max_size
    while size >= min_size:
        f = _font(face, size)
        lines = _wrap(text, f, box_w)
        if all(ct._width(f, ln) <= box_w for ln in lines) and len(lines) * size * leading <= box_h:
            return size, lines
        size = int(size * 0.94)
    raise ValueError("Yazı görsele sığmıyor; daha kısa bir yazı seçin.")


def _rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def _ink_on(bg: str) -> str:
    from .palette import contrast
    return "#FFFFFF" if contrast(bg) >= 4.5 else "#2C2C2A"


def _faces(d: Path) -> tuple[ct.Style, ct.Face]:
    prof, ms = _profile(d), studio._manuscript(d)
    style = ct.STYLES[ct.style_for(prof.get("age_max"), ms.meta.get("GENRE"))]
    body = ct.Face("Andika-Regular.ttf", 400) if (prof.get("age_max") or 99) <= 12 else ct.Face("NotoSerif[wdth,wght].ttf", 500)
    return style, body


def _draw_headline(img, text: str, face: ct.Face, box: tuple[int, int, int, int], effect: str, colors: list[str],
                   color: str, max_size: int) -> None:
    """Başlık yazısı efektle: plain | shadow | outline | burst | rainbow. Harfler fonttan (Türkçe doğru)."""
    from PIL import ImageDraw, ImageFilter
    from PIL import Image
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    pad = int(bh * 0.12) if effect == "burst" else 0
    size, lines = _fit(text, face, bw - 2 * pad, bh - 2 * pad, 1.08, max_size, 18)
    f = _font(face, size)
    lh = int(size * 1.08)
    top = y0 + (bh - lh * len(lines)) // 2
    dr = ImageDraw.Draw(img)
    if effect == "burst":
        import math
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rx, ry = bw / 2, bh / 2
        pts = []
        for i in range(36):
            r = 1.0 if i % 2 == 0 else 0.8
            a = math.pi * 2 * i / 36
            pts.append((cx + math.cos(a) * rx * r, cy + math.sin(a) * ry * r))
        dr.polygon(pts, fill=_rgb(colors[0]), outline=_rgb("#2C2C2A"), width=max(2, size // 18))
        color = _ink_on(colors[0])
    for i, ln in enumerate(lines):
        w = ct._width(f, ln)
        l0 = f.getbbox(ln)[0]
        x = x0 + (bw - w) // 2 - l0
        y = top + i * lh
        if effect == "shadow":
            sh = Image.new("L", img.size, 0)
            ImageDraw.Draw(sh).text((x + size // 14, y + size // 14), ln, font=f, fill=170)
            sh = sh.filter(ImageFilter.GaussianBlur(max(1, size // 30)))
            img.paste(Image.new("RGB", img.size, (20, 18, 16)), (0, 0), sh)
            dr = ImageDraw.Draw(img)
        if effect == "rainbow":
            cx = x
            for j, ch in enumerate(ln):
                if not ch.isspace():
                    dr.text((cx, y), ch, font=f, fill=_rgb(colors[j % len(colors)]), stroke_width=max(2, size // 16),
                            stroke_fill=(255, 255, 255))
                cx += f.getlength(ch)
            continue
        stroke = max(2, size // 12) if effect == "outline" else 0
        stroke_fill = _rgb(_ink_on(color)) if effect == "outline" else None
        dr.text((x, y), ln, font=f, fill=_rgb(color), stroke_width=stroke, stroke_fill=stroke_fill)


def _cover_fit(im, w: int, h: int):
    from PIL import ImageOps
    return ImageOps.fit(im, (w, h), method=3, centering=(0.5, 0.45))


def render_social(d: Path, template: str, visual: str, source: str | None, headline: str, effect: str,
                  color: str | None, quote: str | None):
    """Tek görsel (PNG, RGB). Dönen: (Image, draft). Yerleşim şablona göre: kare ve dikeyde üstte başlık, ortada
    görsel, altta kitap adı/yazar; yatayda görsel solda (alıntıda kapak sağda), yazı öbür yarıda."""
    from PIL import Image, ImageDraw, ImageFilter
    if template not in TEMPLATES:
        raise ValueError("Şablon: kare, dikey ya da yatay.")
    if visual not in VISUALS:
        raise ValueError("Görsel türü: kapak, sayfa ya da alıntı.")
    if effect not in EFFECTS:
        raise ValueError("Bilinmeyen yazı efekti.")
    cols = palette_colors(d)
    bg = (color or cols[0]).upper()
    if bg not in cols:
        raise ValueError("Renk kitabın paletinden seçilmeli.")
    W, H = TEMPLATES[template]
    wide = template == "yatay"
    ms = studio._manuscript(d)
    style, body = _faces(d)
    headline = re.sub(r"\s+", " ", headline or "").strip()
    accents = [c for c in cols if c != bg] or [bg]
    img = Image.new("RGB", (W, H), _rgb(bg))
    ink = _ink_on(bg)
    srcs = {s["key"]: s for s in social_sources(d)}
    m = int(min(W, H) * 0.06)
    byline = ms.title + (f" · {ms.author}" if ms.author else "")
    by_size = int(min(W, H) * 0.04)
    by_h = int(by_size * 1.2 * 2)

    def small(text, x0, x1, y, size_max=by_size):
        size, lines = _fit(text, body, x1 - x0, int(size_max * 2.4), 1.15, size_max, 14)
        f = _font(body, size)
        dr = ImageDraw.Draw(img)
        for i, ln in enumerate(lines):
            dr.text((x0 + (x1 - x0 - ct._width(f, ln)) // 2 - f.getbbox(ln)[0], y + i * int(size * 1.15)), ln,
                    font=f, fill=_rgb(ink))

    def shadowed(pic, x, y):
        sh = Image.new("L", img.size, 0)
        off = max(6, pic.height // 60)
        ImageDraw.Draw(sh).rectangle((x + off, y + off * 2, x + pic.width + off, y + pic.height + off * 2), fill=140)
        sh = sh.filter(ImageFilter.GaussianBlur(off * 2))
        img.paste(Image.new("RGB", img.size, (15, 12, 10)), (0, 0), sh)
        img.paste(pic, (x, y))

    def scaled(pic, max_w, max_h):
        k = min(max_w / pic.width, max_h / pic.height)
        return pic.resize((max(1, int(pic.width * k)), max(1, int(pic.height * k))), Image.Resampling.LANCZOS)

    if visual == "quote":
        q = clean_quote(quote or "")
        if not q:
            raise ValueError("Alıntı boş olamaz.")
        if not in_book(q, norm("\n".join(s.text for s in sections(d)))):
            raise ValueError("Bu alıntı kitabın metninde birebir geçmiyor; kitaptan aynen alın.")
        draft = False
        cover = _cover_front(d, 1200) if "kapak" in srcs else None
        if cover is not None:
            draft = srcs["kapak"]["draft"]
        qf = style.subtitle
        if wide:
            cv = scaled(cover, W * 0.3, H - 2 * m) if cover else None
            x1 = W - m - (cv.width + m if cv else 0)
            qbox = (m * 2, m * 2, x1 - m, H - m - by_h - m // 2)
            if cv:
                shadowed(cv, W - m - cv.width, (H - cv.height) // 2)
        else:
            cv = scaled(cover, W * 0.5, H * (0.2 if template == "kare" else 0.22)) if cover else None
            low = H - m - (cv.height + m // 2 if cv else 0) - by_h
            qbox = (m * 2, int(H * 0.14), W - m * 2, low - m // 2)
            if cv:
                shadowed(cv, (W - cv.width) // 2, H - m - cv.height)
        size, lines = _fit(f"“{q}”", qf, qbox[2] - qbox[0], qbox[3] - qbox[1], 1.25, int(min(W, H) * 0.085), 22)
        f = _font(qf, size)
        dr = ImageDraw.Draw(img)
        y = qbox[1] + (qbox[3] - qbox[1] - len(lines) * int(size * 1.25)) // 2
        for i, ln in enumerate(lines):
            dr.text((qbox[0] + (qbox[2] - qbox[0] - ct._width(f, ln)) // 2 - f.getbbox(ln)[0], y + i * int(size * 1.25)),
                    ln, font=f, fill=_rgb(ink))
        cx = (qbox[0] + qbox[2]) // 2
        dr.rectangle((cx - m, qbox[1] - m // 2, cx + m, qbox[1] - m // 2 + max(4, m // 6)), fill=_rgb(accents[0]))
        small("— " + byline, qbox[0], qbox[2], qbox[3] + m // 3)
        return img, draft

    key = source or ("kapak" if visual == "cover" else None)
    if not key or key not in srcs:
        raise ValueError("Görsel seçin (kapak ya da iç sayfa resmi).")
    draft = srcs[key]["draft"]
    pic = source_image(d, key, 1800)
    if visual == "cover":
        if wide:
            cv = scaled(pic, W * 0.42, H - 2 * m)
            shadowed(cv, m * 2, (H - cv.height) // 2)
            x0 = m * 2 + cv.width + m * 2
            if headline:
                _draw_headline(img, headline, style.title, (x0, m, W - m, H - m - by_h - m // 2), effect, accents,
                               ink, int(H * 0.16))
                small(byline, x0, W - m, H - m - by_h)
            else:
                small(byline, x0, W - m, (H - by_h) // 2)
        else:
            head_h = int(H * (0.22 if template == "dikey" else 0.24)) if headline else 0
            room = H - 2 * m - head_h - by_h - m
            cv = scaled(pic, W - 2 * m, room)
            y = m + head_h + (room - cv.height) // 2 + (m // 2 if headline else 0)
            if headline:
                _draw_headline(img, headline, style.title, (m, m, W - m, m + head_h), effect, accents, ink,
                               int(W * 0.12))
            shadowed(cv, (W - cv.width) // 2, y)
            small(byline, m, W - m, H - m - by_h)
        return img, draft

    # visual == "page": resim zemini doldurur, yanda ya da altta yazı bandı
    if wide:
        pw = int(W * 0.58)
        img.paste(_cover_fit(pic, pw, H), (0, 0))
        if headline:
            _draw_headline(img, headline, style.title, (pw + m, m, W - m, H - m - by_h - m // 2), effect, accents,
                           ink, int(H * 0.14))
        small(byline, pw + m, W - m, H - m - by_h if headline else (H - by_h) // 2)
    else:
        band = int(H * (0.30 if template == "kare" else 0.24)) if headline else by_h + 2 * m
        img.paste(_cover_fit(pic, W, H - band), (0, 0))
        if headline:
            _draw_headline(img, headline, style.title, (m, H - band + m // 2, W - m, H - m - by_h - m // 3), effect,
                           accents, ink, int(band * 0.42))
        small(byline, m, W - m, H - m - by_h)
    return img, draft


def social_view(d: Path) -> dict:
    st = _read(d, "sosyal.json", {"items": []})
    return {"items": st["items"], "sources": social_sources(d), "palette": palette_colors(d),
            "templates": [{"key": k, "label": TEMPLATE_LABEL[k], "w": v[0], "h": v[1]} for k, v in TEMPLATES.items()],
            "effects": list(EFFECTS), "draft_note": DRAFT_NOTE}


def add_social(d: Path, body: dict, by: str) -> dict:
    img, draft = render_social(d, body.get("template", ""), body.get("visual", ""), body.get("source"),
                               body.get("headline", ""), body.get("effect", "plain"), body.get("color"),
                               body.get("quote"))
    sid = f"s_{secrets.token_hex(4)}"
    out = mdir(d) / "sosyal" / f"{sid}.png"
    out.parent.mkdir(exist_ok=True)
    img.save(out, "PNG", optimize=True)
    item = {"id": sid, "template": body["template"], "visual": body["visual"], "source": body.get("source"),
            "headline": (body.get("headline") or "").strip(), "effect": body.get("effect", "plain"),
            "color": (body.get("color") or "").upper() or None, "quote": clean_quote(body.get("quote") or "") or None,
            "w": img.width, "h": img.height, "draft": draft, "by": by, "at": _now(), "approved": None}
    with _io_lock:
        st = studio.read(mdir(d), "sosyal.json", {"items": []})
        st["items"].insert(0, item)
        studio.write(mdir(d), "sosyal.json", st)
    log_event(d, by, "sosyal medya görseli dizildi", item=sid, draft=draft)
    return item


def _social_item(d: Path, sid: str) -> dict:
    if not SOCIAL_ID.match(sid or ""):
        raise KeyError("Görsel bulunamadı.")
    it = next((x for x in _read(d, "sosyal.json", {"items": []})["items"] if x["id"] == sid), None)
    if it is None:
        raise KeyError("Görsel bulunamadı.")
    return it


def approve_social(d: Path, sid: str, ok: bool, by: str) -> dict:
    _social_item(d, sid)
    with _io_lock:
        st = studio.read(mdir(d), "sosyal.json", {"items": []})
        for it in st["items"]:
            if it["id"] == sid:
                it["approved"] = {"by": by, "at": _now()} if ok else None
                item = it
        studio.write(mdir(d), "sosyal.json", st)
    log_event(d, by, "sosyal medya görseli " + ("onaylandı" if ok else "onayı geri alındı"), item=sid)
    return item


def delete_social(d: Path, sid: str, by: str) -> None:
    _social_item(d, sid)
    with _io_lock:
        st = studio.read(mdir(d), "sosyal.json", {"items": []})
        st["items"] = [x for x in st["items"] if x["id"] != sid]
        studio.write(mdir(d), "sosyal.json", st)
    (mdir(d) / "sosyal" / f"{sid}.png").unlink(missing_ok=True)
    log_event(d, by, "sosyal medya görseli silindi", item=sid)


def social_path(d: Path, sid: str) -> Path:
    _social_item(d, sid)
    return mdir(d) / "sosyal" / f"{sid}.png"


def _file_name(d: Path, it: dict) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", ct.tr_upper(studio._manuscript(d).title).casefold()
                  .translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))).strip("-")[:40] or "kitap"
    kind = {"cover": "kapak", "page": "sayfa", "quote": "alinti"}[it["visual"]]
    return f"{'TASLAK-' if it['draft'] else ''}{slug}-{kind}-{it['template']}-{it['id'][2:]}.png"


def social_download(d: Path, sid: str) -> tuple[Path, str]:
    it = _social_item(d, sid)
    if not it.get("approved"):
        raise NotReady("Onaylanmamış görsel indirilemez.")
    return social_path(d, sid), _file_name(d, it)


def social_zip(d: Path) -> bytes:
    items = [x for x in _read(d, "sosyal.json", {"items": []})["items"] if x.get("approved")]
    if not items:
        raise NotReady("İndirilecek onaylı görsel yok.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for it in items:
            p = mdir(d) / "sosyal" / f"{it['id']}.png"
            if p.exists():
                z.write(p, _file_name(d, it))
        if any(it["draft"] for it in items):
            z.writestr("OKUYUN.txt", "TASLAK- ile başlayan görsellerde görsel model üretimi resim var; ticari kullanım "
                                     "izni gelene kadar yayımlanmaz.\n")
    return buf.getvalue()


# ------------------------------------------------------------------ bütün görünüm
def view(d: Path) -> dict:
    ms, prof = studio._manuscript(d), _profile(d)
    dg_quotes = []
    try:
        dg = _read(d, "ozet.json")
        if dg:
            book_norm = norm("\n".join(s.text for s in sections(d)))
            for w in dg.get("windows", {}).values():
                for q in w.get("quotes", []):
                    q = clean_quote(q)
                    if in_book(q, book_norm) and q not in dg_quotes:
                        dg_quotes.append(q)
    except Exception:  # noqa: BLE001 - alıntı listesi yalnız öneridir
        log.exception("quote list failed")
    return {"title": ms.title, "author": ms.author, "band": age_band(prof.get("age_min"), prof.get("age_max")),
            "tasks": tasks(d), "back_cover": back_view(d), "product": product_view(d), "social": social_view(d),
            "quotes": dg_quotes, "guide": guide_view(d), "events": events(d)}
