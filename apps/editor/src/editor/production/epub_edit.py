"""E-kitap düzenleme katmanı: editörün e-kitaba özel kararları, basılı plana ve el yazmasına dokunmadan.

Kayıt iş klasöründe `epub/duzen.json`; e-kitap her üretildiğinde bölümlerin (`epub.flow_docs`) üstüne uygulanır.
Yalnız ev stiliyle (akışkan) üretilen e-kitapta geçerlidir: stil adları ev stilinin sınıflarıdır.

- **Paragraf stili** (`styles`): blok kimliği → ev stili sınıfı (epigraf, şiir, alıntı, ara işareti…) ya da «gizle».
  Kararla birlikte paragraf metninin özeti saklanır; metin sonradan değişirse karar uygulanmaz, uyarı çıkar (yanlış
  paragrafa stil düşmez).
- **Bölüm** (`titles`, `splits`, `merges`): bölüm adını değiştirme; bir paragraftan yeni bölüm başlatma; bölümü
  öncekine katma (başlığı metin içi ara başlık olur, yeni sayfa açmaz). Bölüm anahtarı başlık bloğunun kimliği,
  bölünmüş bölümde bölündüğü paragrafın kimliği, başlıksız bölümde sırası (`d<n>`).
- **Ön sayfalar** (`fronts`): iç kapak görseli, yayınevi imzası, kitap adı-logo-künye, yazar tanıtımı açık/kapalı.
- **Eklenen metin** (`extras`): basılı kitapta olup e-kitapta olmayan parça (karşılaştırmanın bulduğu sayfalar)
  okunmuş kitabın kendi paragraflarından eklenir — kitabın sonuna bölüm olarak ya da ön sayfalara tanıtım olarak
  (çevirmen tanıtımı gibi); metin uydurulmaz, kaynak sayfası saklanır.

Değişiklikler sıra numarasıyla (`rev`) yazılır; ekranın gördüğü sıra eskiyse yazım reddedilir (iki editör çakışmaz).
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

FILE = "duzen.json"
STYLES = {
    "e-paragraf": "Paragraf",
    "e-paragraf-sagdan": "Sağa yaslı paragraf",
    "e-epi": "Epigraf",
    "e-siir": "Şiir",
    "e-daryazi": "Alıntı (girintili)",
    "e-yildiz": "Ara işareti (* * *)",
    "e-2-baslik": "Ara başlık",
    "e-perde": "Perde başlığı",
    "e-perde-alti": "Perde altı yazısı",
    "e-resimalti": "Görsel altı yazısı",
    "gizle": "E-kitapta gösterme",
}
FRONTS = {"ic_kapak": "İç kapak görseli", "imza": "«iyi ki kitaplar var»", "kunye": "Kitap adı, logo ve künye",
          "yazar": "Yazar tanıtımı"}
PLACES = ("front", "end")                     # eklenen metin: ön sayfalarda (tanıtım) ya da kitabın sonunda
PREVIEW = 220
TITLE_MAX = 160


class Conflict(Exception):
    """Ekranın gördüğü düzen sırası eski."""


SOURCES = {"basili": "Basılı kitabın e-kitabı (yayınevinin kapağı ve künyesi)",
           "studyo": "Stüdyo tasarımı (stüdyonun kapağı, resimleri ve künyesi)"}


def empty() -> dict:
    return {"rev": 0, "styles": {}, "titles": {}, "splits": {}, "merges": [], "fronts": {}, "extras": [],
            "source": None}


def source_auto(d: Path) -> str:
    """Kaynak seçilmemişse: okunmuş yayınevi kitabından açılan işte basılı kitabın e-kitabı (yayınevinin kapağı
    kapak kütüphanesinde ve künyesi okunmuş kayıtta bulunuyorsa); Word'den gelen işte stüdyo tasarımı."""
    from . import studio
    from .epub_source import original_cover, print_kunye
    m = studio.read(d, "manuscript.json") or {}
    if (m.get("source") or {}).get("kind") != "generation":
        return "studyo"
    try:
        ok = bool(print_kunye(d)) and original_cover(studio._manuscript(d)) is not None
    except Exception:  # noqa: BLE001 - veritabanına ulaşılamazsa stüdyo tasarımı (e-kitap yine üretilir)
        ok = False
    return "basili" if ok else "studyo"


def source_mode(d: Path, e: dict) -> str:
    return e.get("source") if e.get("source") in SOURCES else source_auto(d)


def book_docs(plan: dict | None, ms, mode: str) -> list[dict]:
    """E-kitabın bölümleri: basılı kitabın e-kitabında okunmuş kitabın metni (basılı sayfa numaralarıyla, stüdyonun
    resimleri olmadan); stüdyo tasarımında sayfa planı (yoksa el yazması)."""
    from . import epub as E
    if mode == "basili" or not plan:
        return E._docs_from_manuscript(ms, pages=mode == "basili")
    return E.flow_docs(plan, ms)


def load(d: Path) -> dict:
    from . import studio
    e = studio.read(d / "epub", FILE) or {}
    return {**empty(), **e}


def _save(d: Path, e: dict, by: str) -> dict:
    from . import studio
    (d / "epub").mkdir(exist_ok=True)
    e = {**e, "rev": int(e.get("rev") or 0) + 1, "by": by, "at": time.time()}
    studio.write(d / "epub", FILE, e)
    return e


def digest(text: str) -> str:
    return hashlib.sha1(" ".join((text or "").split()).encode()).hexdigest()[:10]


# ------------------------------------------------------------------ düğümler (epub.flow_docs biçimi)
def node_id(n) -> str | None:
    if n[0] == "h":
        return n[2]
    if n[0] == "p":
        return next((p[2] for p in n[2] if p[0] == "runs" and len(p) > 2 and p[2]), None)
    return None


def node_text(n) -> str:
    from .epub import runs_text
    if n[0] == "h":
        return n[1]
    if n[0] == "p":
        return "".join(runs_text(p[1]) for p in n[2] if p[0] == "runs")
    return ""


def _key(doc: dict, i: int) -> str:
    return doc.get("key") or next((n[2] for n in doc["nodes"] if n[0] == "h"), None) or f"d{i}"


def chapters(docs: list[dict], e: dict, warn: list[str] | None = None) -> list[dict]:
    """1. aşama: bölünmeler ve bölüm adları uygulanmış bölümler; her bölümde `key`. Metni değişmiş paragraftaki
    bölünme uygulanmaz (`warn`)."""
    splits = e.get("splits") or {}
    out: list[dict] = []
    for i, doc in enumerate(docs):
        cur = {"title": doc["title"], "key": _key(doc, i), "nodes": [], "split": False}
        out.append(cur)
        for n in doc["nodes"]:
            bid = node_id(n) if n[0] == "p" else None
            sp = splits.get(bid) if bid else None
            if sp and any(x[0] in ("p", "img") for x in cur["nodes"]):
                if sp.get("h") != digest(node_text(n)):
                    if warn is not None:
                        warn.append("Metni sonradan değişen bir paragraftaki bölüm başlangıcı uygulanmadı.")
                else:
                    cur = {"title": sp.get("title") or "Bölüm", "key": bid, "split": True,
                           "nodes": [("h", sp.get("title") or "Bölüm", f"{bid}-baslik", [{"text": sp.get("title") or ""}])]}
                    out.append(cur)
            cur["nodes"].append(n)
    for ch in out:
        t = (e.get("titles") or {}).get(ch["key"])
        if t:
            ch["title"] = t
            ch["nodes"] = [("h", t, n[2], [{"text": t}]) if n[0] == "h" and i == _first_h(ch["nodes"]) else n
                           for i, n in enumerate(ch["nodes"])]
    return out


def _first_h(nodes: list) -> int:
    return next((i for i, n in enumerate(nodes) if n[0] == "h"), -1)


def apply(docs: list[dict], e: dict, warn: list[str]) -> tuple[list[dict], dict[str, str]]:
    """E-kitaba girecek bölümler ve paragraf stilleri ({blok kimliği: sınıf | «gizle»})."""
    chs = chapters(docs, e, warn)
    styles: dict[str, str] = {}
    texts = {node_id(n): node_text(n) for ch in chs for n in ch["nodes"] if node_id(n)}
    stale = 0
    for bid, s in (e.get("styles") or {}).items():
        if s.get("style") not in STYLES or bid not in texts:
            continue
        if s.get("h") != digest(texts[bid]):
            stale += 1
            continue
        styles[bid] = s["style"]
    if stale:
        warn.append(f"Metni sonradan değişen {stale} paragrafın e-kitap stili uygulanmadı; düzenleme ekranından yeniden seçin.")
    merges = set(e.get("merges") or [])
    out: list[dict] = []
    for ch in chs:
        if ch["key"] in merges and out:
            for n in ch["nodes"]:
                if n[0] == "h":                      # katılan bölümün başlığı metin içi ara başlık olur
                    styles.setdefault(n[2], "e-2-baslik")
                    out[-1]["nodes"].append(("p", "para", [("runs", n[3] or [{"text": n[1]}], n[2])]))
                else:
                    out[-1]["nodes"].append(n)
        else:
            out.append({"title": ch["title"], "nodes": list(ch["nodes"])})
    for x in e.get("extras") or []:
        if x.get("place") == "front":              # ön sayfalara eklenen (tanıtım) epub.house_fronts'ta
            continue
        nodes = [("h", x["title"], x["id"], [{"text": x["title"]}])]
        nodes += [("p", "para", [("runs", [{"text": t}], f"{x['id']}-{k}")]) for k, t in enumerate(x.get("paras") or [])]
        out.append({"title": x["title"], "nodes": nodes})
    return out, styles


def front_on(e: dict, key: str) -> bool:
    return (e.get("fronts") or {}).get(key, True)


# ------------------------------------------------------------------ ekran
def structure(d: Path) -> dict:
    """Düzenleme ekranı: bölümler (bölünme ve adlar uygulanmış; katılan bölüm işaretli), her bölümde paragraflar
    (kısa metin, seçili stil, kendiliğinden stil), ön sayfalar, eklenen metinler ve karşılaştırmanın bulduğu
    basılıda olup e-kitapta olmayan parçalar."""
    from . import epub as E
    from . import plan as plan_mod
    from . import studio
    e = load(d)
    plan = plan_mod.load(d)
    ms = studio._manuscript(d)
    mode = source_mode(d, e)
    docs = book_docs(plan, ms, mode)
    warn: list[str] = []
    chs = chapters(docs, e, warn)
    styles = e.get("styles") or {}
    merges = set(e.get("merges") or [])
    out = []
    for i, ch in enumerate(chs):
        blocks = []
        for n in ch["nodes"]:
            if n[0] != "p":
                continue
            bid = node_id(n)
            if not bid:
                continue
            text = node_text(n)
            s = styles.get(bid) or {}
            blocks.append({"id": bid, "kind": n[1], "text": text[:PREVIEW], "long": len(text) > PREVIEW,
                           "style": s.get("style") if s.get("h") == digest(text) else None,
                           "auto": "e-yildiz" if E.SECTION_BREAK.match(text) else "e-paragraf",
                           "split": bid == ch["key"] and ch["split"]})
        out.append({"key": ch["key"], "title": ch["title"], "merged": ch["key"] in merges and i > 0,
                    "split": ch["split"], "renamed": ch["key"] in (e.get("titles") or {}), "blocks": blocks})
    st = E.read_state(d)
    cmp = st.get("compare") or {}
    added = {tuple(x["pages"]) for x in e.get("extras") or []}
    missing = [{**m, "added": tuple(m["pages"]) in added} for m in cmp.get("missing") or [] if not m.get("expected")]
    return {"rev": e["rev"], "chapters": out, "styles": STYLES, "source": mode, "source_set": e.get("source") in SOURCES,
            "sources": [{"key": k, "label": v} for k, v in SOURCES.items()],
            "fronts": [{"key": k, "label": v, "on": front_on(e, k)} for k, v in FRONTS.items()],
            "extras": [{"id": x["id"], "title": x["title"], "pages": x["pages"], "place": x.get("place") or "end",
                        "words": sum(len(t.split()) for t in x["paras"])} for x in e.get("extras") or []],
            "missing": missing, "warnings": list(dict.fromkeys(warn)),
            "house": bool(E.house_key(d)), "by": e.get("by"), "at": e.get("at")}


def _text_of(d: Path, bid: str) -> str | None:
    from . import epub as E
    from . import plan as plan_mod
    from . import studio
    plan = plan_mod.load(d)
    ms = studio._manuscript(d)
    docs = book_docs(plan, ms, source_mode(d, load(d)))
    for doc in docs:
        for n in doc["nodes"]:
            if n[0] == "p" and node_id(n) == bid:
                return node_text(n)
    return None


def _title(v) -> str:
    t = " ".join(str(v or "").split())[:TITLE_MAX]
    if not t:
        raise ValueError("Bölüm adı boş olamaz.")
    return t


def change(d: Path, rev: int, ops: list[dict], by: str, source=None) -> dict:
    """Düzenleme işlemleri (sırayla, hepsi ya da hiçbiri). `source(sayfa_a, sayfa_b) -> [paragraf]`: basılı kitabın
    paragrafları (eklenen metin için; varsayılan okunmuş kitabın kaydı)."""
    e = load(d)
    if int(rev) != int(e["rev"]):
        raise Conflict("Düzen başka bir yerde değişti; ekranı yenileyin.")
    if not isinstance(ops, list) or not ops or len(ops) > 200:
        raise ValueError("İşlem listesi geçersiz.")
    for op in ops:
        kind = op.get("op")
        if kind == "style":
            bid, style = str(op.get("block") or ""), op.get("style") or ""
            if style and style not in STYLES:
                raise ValueError("Stil geçersiz.")
            text = _text_of(d, bid)
            if text is None:
                raise ValueError("Paragraf bulunamadı.")
            if style:
                e["styles"][bid] = {"style": style, "h": digest(text)}
            else:
                e["styles"].pop(bid, None)
        elif kind == "title":
            e["titles"][str(op.get("chapter") or "")] = _title(op.get("title"))
        elif kind == "split":
            bid = str(op.get("block") or "")
            if op.get("on", True):
                text = _text_of(d, bid)
                if text is None:
                    raise ValueError("Paragraf bulunamadı.")
                e["splits"][bid] = {"title": _title(op.get("title")), "h": digest(text)}
            else:
                e["splits"].pop(bid, None)
                e["titles"].pop(bid, None)
        elif kind == "merge":
            key = str(op.get("chapter") or "")
            e["merges"] = [k for k in e["merges"] if k != key] + ([key] if op.get("on", True) else [])
        elif kind == "front":
            key = op.get("key")
            if key not in FRONTS:
                raise ValueError("Ön sayfa geçersiz.")
            e["fronts"][key] = bool(op.get("on"))
        elif kind == "add_missing":
            pages = [int(x) for x in (op.get("pages") or [])][:2]
            if len(pages) != 2 or pages[0] > pages[1] or pages[1] - pages[0] > 40:
                raise ValueError("Sayfa aralığı geçersiz.")
            title = _title(op.get("title"))
            paras = _clean(_not_in_epub(d, (source or _source_paras)(d, pages[0], pages[1])), title)
            if not paras:
                raise ValueError("Bu sayfalarda basılı metin bulunamadı.")
            place = op.get("place") or "end"
            if place not in PLACES:
                raise ValueError("Yer geçersiz.")
            e["extras"] = [x for x in e["extras"] if x["pages"] != pages]
            e["extras"].append({"id": f"ek-{pages[0]}-{pages[1]}", "title": title, "pages": pages, "paras": paras,
                                "place": place})
        elif kind == "remove_extra":
            e["extras"] = [x for x in e["extras"] if x["id"] != op.get("id")]
        elif kind == "source":
            v = op.get("source")
            if v not in SOURCES and v is not None:
                raise ValueError("Kaynak geçersiz.")
            e["source"] = v
        elif kind == "reset":
            e = {**empty(), "rev": e["rev"]}
        else:
            raise ValueError("İşlem geçersiz.")
    _save(d, e, by)
    return structure(d)


def _not_in_epub(d: Path, paras: list[str]) -> list[str]:
    """Yalnız e-kitapta olmayan paragraflar: aynı basılı sayfada e-kitaba zaten girmiş metin (ör. çevirmen tanıtımıyla
    aynı sayfadaki yazar tanıtımı) yeniden eklenmez. Ölçü karşılaştırmanınki: 6 kelimelik dizilerin yarısı e-kitapta."""
    from . import epub as E
    from .epub_compare import _grams, epub_text, words
    path = d / E.DIR / E.FILE
    if not path.exists():
        return paras
    have = _grams(words(epub_text(path)))
    new: list[bool | None] = []
    for t in paras:
        g = _grams(words(t))
        new.append(None if not g else sum(1 for x in g if x in have) / len(g) < 0.5)
    for i in range(len(new) - 1, -1, -1):          # N kelimeden kısa satır (ad, başlık) ardındaki paragrafla gider
        if new[i] is None:
            new[i] = new[i + 1] if i + 1 < len(new) else True
    return [t for t, keep in zip(paras, new) if keep]


def _clean(paras: list[str], title: str) -> list[str]:
    """Eklenen metin: bölüm adını tekrar eden ilk satır düşer (başlık zaten bölüm adı; «SELEN DEMİRTAŞ» satırı
    «Çeviren: Selen Demirtaş» başlığının içinde geçer); yayınevi tanıtımı/reklam satırından (basılı kitabın baskı
    kuralındaki tanım) sonrası alınmaz."""
    from .manuscript import _PROMO, _fold
    out = list(paras)
    if out and _fold(out[0]) and _fold(out[0]) in _fold(title):
        out = out[1:]
    cut = next((i for i, t in enumerate(out) if _PROMO.search(t)), None)
    return out[:cut] if cut is not None else out


def _source_paras(d: Path, first: int, last: int) -> list[str]:
    """Okunmuş kitabın o sayfalardaki paragrafları (sayfa sonunda bölünen paragraf birleştirilir)."""
    from . import studio
    from .epub_compare import source_pages
    from .manuscript import TERMINAL
    src = (studio.read(d, "manuscript.json") or {}).get("source") or {}
    if src.get("kind") != "generation" or not src.get("generation_id"):
        return []
    out: list[str] = []
    for no, text in source_pages(src["generation_id"]):
        if not first <= no <= last:
            continue
        for t in (x.strip() for x in text.split("\n")):
            if not t or re.fullmatch(r"\d{1,4}", t):          # sayfa numarası
                continue
            if out and not out[-1].endswith(TERMINAL) and t[:1].islower():
                out[-1] = re.sub(r"-$", "", out[-1]) + ("" if out[-1].endswith("-") else " ") + t
            else:
                out.append(t)
    return out
