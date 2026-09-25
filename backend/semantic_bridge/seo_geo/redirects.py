"""Anasayfaya giden 301 yönlendirmeleri için doğru hedef önerisi. Modelsiz, kurallı ve açıklanabilir.

Silinen bir kitabın eski adresi anasayfaya yönlenirse Google bunu "yumuşak 404" sayar: eski sayfanın gücü kaybolur,
okur aradığını bulamaz. Doğrusu eski adresi en yakın yaşayan sayfaya (aynı kitabın yeni baskısı, yazar, kategori)
yönlendirmektir. Öneriler yalnız kayıttır; T-soft'a yazılmaz (yazma yasak) — onaylananlar CSV olarak indirilir ve
T-soft panelinden elle girilir.

Eşleştirme sırası (ilk tutan kazanır, gerekçesi yazılır):
1. Kaynak adreste ISBN varsa ve o ISBN'li kitap aktifse → o kitap ("kesin").
2. ISBN'li kitap pasifse, aynı adlı aktif kitap (yeni baskı) → "yüksek".
3. `katilimci/<ad>-<guid>` → aynı adlı yazar sayfası → "yüksek"; `haber/…` → blog/haber sayfaları arasında.
4. Kişi (`katilimci/`) yalnız adın kelimeleri birebir aynıysa yazar sayfasına eşlenir — "oguz-demir" ile "arzu-demir"
   benzer görünür ama başka kişidir. Etkinlik/haber adresleri yalnız blog/içerik sayfalarına bakar.
5. Kelime kümesi aynıysa "yüksek"; hedefin en az 3 kelimesi eski adreste geçiyorsa "yüksek", 2 kelimesi "orta";
   yalnız karakter benzerliği (≥%85) en fazla "orta" — kısa adreste tek harf anlamı değiştirir ("kis"/"is" kitaplığı).
   Altı → "eşleşme yok" (öneri yapılmaz, insan karar verir).
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import defaultdict
from typing import Any, Iterable, Optional

from . import rules

HOME_TARGETS = {"anasayfa", "", "/", "index.php"}
_ISBN = re.compile(r"97[89]\d{10}")
_GUID = re.compile(r"-?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_STOP = {"ve", "ile", "bir", "the", "of", "ciltli", "karton", "kapak", "set", "seti", "kitap", "kitaplari", "sinif"}
#: Hedef olabilecek sayfa türleri ve eşit benzerlikte tercih sırası (kitap önce).
TYPE_RANK = {"product": 0, "model": 1, "category": 2, "brand": 3, "tag": 4, "blog": 5, "content": 6, "page": 7}


def _ascii(s: str) -> str:
    s = s.replace("ı", "i").replace("İ", "i")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def _tokens(slug: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _ascii(slug)) if t and len(t) > 1 and t not in _STOP and not t.isdigit()]


def _clean(link: str) -> str:
    s = link.strip().strip("/").lower()
    s = _GUID.sub("", s)
    s = _ISBN.sub("", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


def _norm_name(v: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", rules.text_of(v).casefold())).strip()


def is_home(target: Any) -> bool:
    return str(target or "").strip().strip("/").lower() in HOME_TARGETS


class Index:
    """Yaşayan sayfalar: T-soft `link/getLinks` (301 olmayanlar) + aktif ürünler."""

    def __init__(self, links: Iterable[dict[str, Any]], products: Iterable[dict[str, Any]]):
        self.pages: dict[str, str] = {}
        for l in links:
            t, link = str(l.get("Type") or ""), str(l.get("Link") or "").strip().strip("/")
            if link and t in TYPE_RANK and link not in self.pages:
                self.pages[link] = t
        self.by_isbn: dict[str, dict[str, Any]] = {}
        self.active_by_name: dict[str, str] = {}
        for p in products:
            active = str(p.get("IsActive", "1")).lower() not in ("0", "false")
            slug = str(p.get("SeoLink") or "").strip().strip("/")
            code = str(p.get("Barcode") or "").strip()
            if code:
                self.by_isbn[code] = {"slug": slug, "active": active, "name": p.get("ProductName")}
            if active and slug:
                self.pages.setdefault(slug, "product")
                self.active_by_name.setdefault(_norm_name(p.get("ProductName")), slug)
        self.token_index: dict[str, set[str]] = defaultdict(set)
        for link in self.pages:
            for t in _tokens(link):
                self.token_index[t].add(link)

    def candidates(self, clean: str, kinds: Optional[set[str]] = None, top: int = 3) -> list[dict[str, Any]]:
        toks = _tokens(clean)
        pool: set[str] = set()
        for t in toks:
            pool |= self.token_index.get(t, set())
        scored = []
        src = set(toks)
        for link in pool:
            kind = self.pages[link]
            if kinds and kind not in kinds:
                continue
            ltoks = set(_tokens(link))
            same = bool(ltoks) and ltoks == src
            contained = bool(ltoks) and ltoks <= src and len(ltoks) >= 2
            ratio = difflib.SequenceMatcher(None, _ascii(clean), _ascii(link)).ratio()
            score = 1.0 if same else max(ratio, 0.9 if contained else 0.0)
            scored.append((score, -TYPE_RANK.get(kind, 9), link, kind, contained, same, len(ltoks)))
        scored.sort(reverse=True)
        return [{"link": l, "type": k, "score": round(s, 2), "contained": c, "same": sm, "words": n}
                for s, _, l, k, c, sm, n in scored[:top]]


def suggest(source: str, idx: Index) -> dict[str, Any]:
    """Tek yönlendirme için öneri: hedef, güven, gerekçe, alternatifler."""
    link = source.strip().strip("/")
    m = _ISBN.search(link)
    if m:
        hit = idx.by_isbn.get(m.group(0))
        if hit and hit["active"] and hit["slug"]:
            return {"target": hit["slug"], "type": "product", "confidence": "kesin",
                    "reason": f"Adresteki ISBN {m.group(0)} aktif kitabın ISBN'i: «{rules.text_of(hit['name'])}».", "alternatives": []}
        if hit:
            same = idx.active_by_name.get(_norm_name(hit["name"]))
            if same:
                return {"target": same, "type": "product", "confidence": "yüksek",
                        "reason": f"ISBN {m.group(0)} pasif kitaba ait; aynı adlı aktif kitap var (yeni baskı olabilir).",
                        "alternatives": []}
    clean = _clean(link)
    kinds, person = None, False
    head = link.lower().split("/", 1)[0] if "/" in link else ""
    if head == "katilimci":
        clean, kinds, person = _clean(link.split("/", 1)[1]), {"model"}, True
    elif head in ("haber", "etkinlik", "duyuru"):
        clean, kinds = _clean(link.split("/", 1)[1]), {"blog", "content", "page"}
    cands = idx.candidates(clean, kinds)
    none = {"target": None, "type": None, "confidence": "yok", "alternatives": cands}
    if not cands:
        return {**none, "reason": "Benzer yaşayan sayfa bulunamadı; hedefe insan karar vermeli."}
    best = cands[0]
    kind_tr = {"product": "kitap", "model": "yazar", "category": "kategori", "brand": "yayınevi", "tag": "etiket",
               "blog": "blog", "content": "içerik", "page": "sayfa"}.get(best["type"], best["type"])
    if person:
        if best["same"]:
            return {"target": best["link"], "type": "model", "confidence": "yüksek",
                    "reason": "Eski katılımcı sayfası; aynı adlı yazar sayfası var.", "alternatives": cands[1:]}
        return {**none, "reason": f"Aynı adlı yazar sayfası yok (en yakın «{best['link']}» başka kişi olabilir)."}
    if best["same"]:
        conf, why = "yüksek", "adresin kelimeleri birebir aynı"
    elif best["contained"] and best["words"] >= 3:
        conf, why = "yüksek", f"hedef adresin {best['words']} kelimesi de eski adreste geçiyor"
    elif best["contained"]:
        conf, why = "orta", "hedef adresin iki kelimesi eski adreste geçiyor"
    elif best["score"] >= 0.85:
        conf, why = "orta", f"adres benzerliği %{int(best['score'] * 100)} (kelimeler farklı; kontrol edin)"
    else:
        return {**none, "reason": f"En yakın sayfa «{best['link']}» yalnız %{int(best['score'] * 100)} benzer; öneri yapılmadı."}
    if kinds and conf == "yüksek":
        conf = "orta"  # etkinlik/haber içeriği ile hedef sayfa aynı konu olmayabilir
    return {"target": best["link"], "type": best["type"], "confidence": conf,
            "reason": f"{kind_tr.capitalize()} sayfası; {why}.", "alternatives": cands[1:]}
