"""Sürüm farkı (Kitap Tasarım Stüdyosu): iki sayfa planı sürümünü sayfa sayfa karşılaştırır.

Sürüm = (iş, rev). Kaynaklar: aynı işin `plan-history/<rev>.json` kayıtları (her yazım bir sürüm, silinmez) ve aynı
kitabın başka işleri (yeniden başlatılmış ya da yeniden açılmış iş: aynı `book_id`, Word'den gelende aynı dosya).

- **Eşleştirme:** önce kalıcı sayfa kimliğiyle (p_…); kimliği tutmayan sayfalar içerikle (kelime kümesi örtüşmesi,
  en iyi çift önce; eşik `PAIR_MIN`, son okumanın baskı farkıyla aynı gerekçe: aynı kitabın farklı sayfalarında
  örtüşme 0,23'ü geçmiyor), metinsiz sayfalar aynı resim/fotoğrafla. Kalanlar eklendi/silindi.
- **Metin farkı:** kelime düzeyinde (boşluk korunur), eklenen/silinen işaretli; sayfa metni, balonlar ve serbest
  yazılar ayrı ayrı (öğe kimliğiyle, tutmazsa sırayla).
- **Yerleşim farkı:** kutu taşındı / boyutu değişti (0,5 mm'den küçük oynama sayılmaz: ekranın yuvarlaması),
  öğe eklendi/silindi, yerleşim, punto, hizalama, resim değişti; kutular önizleme üstünde çizilsin diye döner.
- **Görsel farkı:** iki sürümün sayfa önizlemesi aynı genişlikte çizilir, gri düzeyde fark `PIXEL_DELTA`'yı aşan
  pikseller `CELL` px'lik hücrelerde toplanır, komşu hücreler bölgeye birleşir (oranla döner, ekran/rapor vurgular).
  Geçmiş sürümün önizlemesi o sürümün planıyla ayrı klasörde (`karsilastir/r<rev>/`) dizilir, bir kez: geçmiş
  değişmez. Resim sürümü seçimi geçmişte tutulmadığı için aynı işin eski sürümü bugün seçili resimle çizilir.
- **Rapor:** `templates/diff_report.typ` ile PDF (matbaa/yazar onayı): özet, değişen her sayfa için iki önizleme
  (değişen bölge işaretli), kelime farkı, yerleşim değişiklikleri; değişmeyen sayfalar aralık olarak tek satır.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import plan as plan_mod
from . import studio

DIR = "karsilastir"
PAIR_MIN = 0.5          # içerikle eşleşme için kelime kümesi örtüşmesi (bkz. modül belgesi)
MOVE_MM = 0.5           # bundan küçük kutu oynaması değişiklik sayılmaz
PIXEL_DELTA = 40        # gri düzeyde değişmiş sayılan piksel farkı (0..255)
CELL = 8                # px; değişen hücre
CELL_SHARE = 0.04       # hücrenin bu oranı değiştiyse hücre değişmiş sayılır (kenar yumuşatma gürültüsü altında)
VISUAL_W = 600          # görsel karşılaştırma genişliği (px; bir çizim ölçüsü, karar değil)

LAYOUT_TR = {"art-top": "resim üstte", "art-bottom": "resim altta", "art-full": "tam sayfa resim",
             "art-left": "resim solda", "art-right": "resim sağda", "text-over-art": "yazı resmin üstünde",
             "text-only": "yalnız yazı", "blank": "boş sayfa", "custom": "elle yerleşim"}
ALIGN_TR = {"left": "sola", "justify": "iki yana", "center": "ortaya", "right": "sağa"}
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


# ------------------------------------------------------------------ sürümler
def book_key(d: Path) -> str | None:
    src = (studio.read(d, "job.json") or {}).get("source") or {}
    if src.get("book_id"):
        return "kitap:" + str(src["book_id"])
    if src.get("file_name"):
        return "dosya:" + str(src["file_name"]).casefold()
    return None


def related_jobs(d: Path) -> list[Path]:
    """Bu iş ve aynı kitabın sayfa planı olan öteki işleri (yeniden başlatılmış/yeniden açılmış)."""
    key = book_key(d)
    out = []
    for j in studio.list_jobs():
        jd = studio.root() / j["id"]
        if jd == d or (key and book_key(jd) == key):
            if plan_mod.exists(jd):
                out.append(jd)
    if d not in out and plan_mod.exists(d):
        out.insert(0, d)
    return out


def versions(d: Path) -> dict:
    jobs = []
    for jd in related_jobs(d):
        j = studio.read(jd, "job.json") or {}
        cur = plan_mod.load(jd)
        jobs.append({"id": jd.name, "self": jd == d, "title": (studio.read(jd, "state.json") or {}).get("title"),
                     "created_at": j.get("created_at"), "created_by": j.get("created_by"),
                     "current": cur["rev"], "pages": len(cur["pages"]), "revs": plan_mod.history(jd)})
    return {"job": d.name, "jobs": jobs}


class Version:
    def __init__(self, d: Path, rev: int, plan: dict, current: bool, at: str | None, by: str | None):
        self.d, self.rev, self.plan, self.current, self.at, self.by = d, rev, plan, current, at, by

    @property
    def key(self) -> str:
        return f"{self.d.name}:{self.rev}"

    def label(self, ctx: Path) -> str:
        who = "bu iş" if self.d == ctx else f"iş {self.d.name}"
        return f"Sürüm {self.rev} ({who}{', şu an' if self.current else ''})"


def resolve(ctx: Path, spec: str) -> Version:
    """`iş:rev` (rev «current» ya da boş = işin şimdiki planı). İş, bağlam işi ya da aynı kitabın işi olmalı."""
    job, _, rev = (spec or "").partition(":")
    job = job or ctx.name
    jd = ctx if job == ctx.name else studio.job_dir(job)
    if jd != ctx and jd not in related_jobs(ctx):
        raise KeyError("bu kitabın sürümü değil")
    cur = plan_mod.load(jd)
    if cur is None:
        raise plan_mod.NoPlan(jd.name)
    if rev in ("", "current") or int(rev) == int(cur["rev"]):
        return Version(jd, int(cur["rev"]), cur, True, cur.get("updated_at"), cur.get("updated_by"))
    p = jd / plan_mod.HISTORY / f"{int(rev)}.json"
    if not p.exists():
        raise KeyError(f"sürüm yok: {rev}")
    h = json.loads(p.read_text())
    return Version(jd, int(rev), h["plan"], False, h.get("at"), h.get("by"))


# ------------------------------------------------------------------ eşleştirme
_WORD = re.compile(r"[^\W_]+", re.U)


def _runs(runs) -> str:
    return "".join(r.get("text", "") for r in runs or [])


def body_text(pg: dict) -> str:
    return "\n".join(_runs(b.get("runs")) for b in (pg.get("text") or {}).get("blocks", []))


def all_text(pg: dict) -> str:
    return " ".join([body_text(pg)] + [b.get("text", "") for b in pg.get("bubbles") or []] +
                    [_runs(x.get("runs")) for x in pg.get("texts") or []])


def _wordset(pg: dict) -> set[str]:
    return {w.casefold() for w in _WORD.findall(all_text(pg))}


def _art_key(pg: dict) -> str | None:
    a = pg.get("art") or {}
    return a.get("asset") or a.get("id")


def similarity(a: dict, b: dict) -> float:
    wa, wb = _wordset(a), _wordset(b)
    if wa or wb:
        return len(wa & wb) / max(1, len(wa | wb))
    ka, kb = _art_key(a), _art_key(b)
    if ka and ka == kb:
        return 1.0
    return 1.0 if not ka and not kb and a.get("layout") == b.get("layout") == "blank" else 0.0


def match(pa: list[dict], pb: list[dict]) -> list[tuple[int | None, int | None]]:
    """Sayfa çiftleri, yeni sürümün sırasıyla; eski sürümde olup yenide olmayan sayfa eski komşusunun ardına."""
    ida = {p["id"]: i for i, p in enumerate(pa)}
    pair: dict[int, int] = {}                       # ib -> ia
    for ib, p in enumerate(pb):
        if p["id"] in ida:
            pair[ib] = ida[p["id"]]
    used = set(pair.values())
    cands = []
    for ib, b in enumerate(pb):
        if ib in pair:
            continue
        for ia, a in enumerate(pa):
            if ia in used:
                continue
            s = similarity(a, b)
            if s >= PAIR_MIN:
                cands.append((-s, abs(ia - ib), ib, ia))
    for _s, _dist, ib, ia in sorted(cands):
        if ib in pair or ia in used:
            continue
        pair[ib] = ia
        used.add(ia)
    out: list[tuple[int | None, int | None]] = [(pair.get(ib), ib) for ib in range(len(pb))]
    b_of_a = {ia: ib for ib, ia in pair.items()}
    for ia in range(len(pa)):
        if ia in used:
            continue
        prev = next((b_of_a[j] for j in range(ia - 1, -1, -1) if j in b_of_a), None)
        at = 0 if prev is None else next(k for k, (_x, y) in enumerate(out) if y == prev) + 1
        while at < len(out) and out[at][1] is None:
            at += 1                                          # önceki silinmişlerin ardına
        out.insert(at, (ia, None))
    return out


# ------------------------------------------------------------------ fark
_TOK = re.compile(r"^\s+|\S+\s*")


def word_diff(a: str, b: str) -> list[dict]:
    """Kelime düzeyinde fark: [{"op": "eq"|"del"|"ins", "text"}], ardışık aynı işlem birleşik. Kelime ardındaki
    boşlukla tek parça; karşılaştırma boşluksuz (satır sonu/çift boşluk kelime farkı sayılmaz), eşit kısım yeni
    metinden."""
    ta, tb = _TOK.findall(a or ""), _TOK.findall(b or "")
    sm = difflib.SequenceMatcher(None, [t.strip() for t in ta], [t.strip() for t in tb], autojunk=False)
    out: list[dict] = []

    def add(op, toks):
        text = "".join(toks)
        if not text:
            return
        if out and out[-1]["op"] == op:
            out[-1]["text"] += text
        else:
            out.append({"op": op, "text": text})
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            add("eq", tb[j1:j2])
        else:
            add("del", ta[i1:i2])
            add("ins", tb[j1:j2])
    return out


def condense(segments: list[dict], keep: int = 8) -> list[dict]:
    """Rapor için: değişiklikten uzak eşit metin «…» ile kısalır (değişikliğin iki yanında `keep` kelime kalır)."""
    out = []
    for i, s in enumerate(segments):
        if s["op"] != "eq":
            out.append(s)
            continue
        toks = _TOK.findall(s["text"])
        first, last = i == 0, i == len(segments) - 1
        room = keep * (1 if first or last else 2)
        if len(toks) <= room + 2:
            out.append(s)
        elif first:
            out.append({"op": "eq", "text": "… " + "".join(toks[-keep:])})
        elif last:
            out.append({"op": "eq", "text": "".join(toks[:keep]).rstrip() + " …"})
        else:
            out.append({"op": "eq", "text": "".join(toks[:keep]) + "… " + "".join(toks[-keep:])})
    return out


def _mm(v: float) -> str:
    return f"{abs(v):.0f}" if abs(v) >= 10 else f"{abs(v):.1f}".replace(".", ",")


def box_change(what: str, a: dict | None, b: dict | None) -> list[dict]:
    if not a or not b:
        return []
    out = []
    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
    dw, dh = b["w"] - a["w"], b["h"] - a["h"]
    if abs(dw) > MOVE_MM or abs(dh) > MOVE_MM:
        out.append({"kind": "resized", "text": f"{what}: boyutu değişti ({_mm(a['w'])}×{_mm(a['h'])} → "
                                               f"{_mm(b['w'])}×{_mm(b['h'])} mm)", "a": a, "b": b})
    if abs(dx) > MOVE_MM or abs(dy) > MOVE_MM:
        parts = []
        if abs(dx) > MOVE_MM:
            parts.append(f"{_mm(dx)} mm {'sağa' if dx > 0 else 'sola'}")
        if abs(dy) > MOVE_MM:
            parts.append(f"{_mm(dy)} mm {'aşağı' if dy > 0 else 'yukarı'}")
        out.append({"kind": "moved", "text": f"{what}: taşındı ({', '.join(parts)})", "a": a, "b": b})
    return out


def _item_name(kind: str, x: dict, plan: dict) -> str:
    if kind == "bubble":
        return f"Balon «{_short(x.get('text', ''))}»"
    if kind == "figure":
        a = (plan.get("assets") or {}).get(x.get("asset")) or {}
        return "Fotoğraf" if a.get("kind") == "photo" else "Figür"
    if kind == "text":
        return f"Yazı «{_short(_runs(x.get('runs')))}»"
    return "Süs/şekil" + (f" ({x.get('kind')})" if x.get("kind") else "")


def _short(t: str, n: int = 28) -> str:
    t = " ".join((t or "").split())
    return t if len(t) <= n else t[:n].rstrip() + "…"


def layout_changes(pa: dict, pb: dict, plan_a: dict, plan_b: dict) -> list[dict]:
    out: list[dict] = []
    if pa.get("layout") != pb.get("layout"):
        out.append({"kind": "layout", "text": f"Yerleşim: {LAYOUT_TR.get(pa.get('layout'), pa.get('layout'))} → "
                                              f"{LAYOUT_TR.get(pb.get('layout'), pb.get('layout'))}"})
    aa, ab = pa.get("art"), pb.get("art")
    if aa and not ab:
        out.append({"kind": "removed", "text": "Resim kaldırıldı", "a": aa["box"]})
    elif ab and not aa:
        out.append({"kind": "added", "text": "Resim eklendi", "b": ab["box"]})
    elif aa and ab:
        if _art_key(aa) != _art_key(ab):
            out.append({"kind": "changed", "text": "Resim değişti" + (" (fotoğraf)" if ab.get("asset") else ""),
                        "a": aa["box"], "b": ab["box"]})
        out += box_change("Resim kutusu", aa["box"], ab["box"])
        if aa.get("fit") != ab.get("fit"):
            out.append({"kind": "changed", "text": "Resim sığdırma: " + ("kırp" if ab.get("fit") == "cover" else "tamamı görünsün")})
        fa, fb = aa.get("focus") or {}, ab.get("focus") or {}
        if abs(fa.get("x", .5) - fb.get("x", .5)) > .02 or abs(fa.get("y", .5) - fb.get("y", .5)) > .02:
            out.append({"kind": "changed", "text": "Resmin kırpma odağı değişti", "b": ab["box"]})
    ta, tb = pa.get("text"), pb.get("text")
    if ta and not tb:
        out.append({"kind": "removed", "text": "Yazı kutusu kaldırıldı", "a": ta["box"]})
    elif tb and not ta:
        out.append({"kind": "added", "text": "Yazı kutusu eklendi", "b": tb["box"]})
    elif ta and tb:
        out += box_change("Yazı kutusu", ta["box"], tb["box"])
        if (ta.get("size") or None) != (tb.get("size") or None):
            out.append({"kind": "changed", "text": f"Punto: {ta.get('size') or 'kitabın'} → {tb.get('size') or 'kitabın'}"})
        if ta.get("align") != tb.get("align"):
            out.append({"kind": "changed", "text": f"Hizalama: {ALIGN_TR.get(ta.get('align'), ta.get('align'))} → "
                                                   f"{ALIGN_TR.get(tb.get('align'), tb.get('align'))}"})
        if ta.get("background") != tb.get("background"):
            out.append({"kind": "changed", "text": "Yazı zemini değişti"})
        if body_text(pa) == body_text(pb) and _style(ta) != _style(tb):
            out.append({"kind": "changed", "text": "Yazı biçimi değişti (renk, kalınlık ya da punto)", "b": tb["box"]})
    for key, kind in (("bubbles", "bubble"), ("figures", "figure"), ("texts", "text"), ("shapes", "shape")):
        la = {x["id"]: x for x in pa.get(key) or []}
        lb = {x["id"]: x for x in pb.get(key) or []}
        for i, x in la.items():
            if i not in lb:
                out.append({"kind": "removed", "text": f"{_item_name(kind, x, plan_a)} silindi", "a": x.get("box")})
        for i, x in lb.items():
            if i not in la:
                out.append({"kind": "added", "text": f"{_item_name(kind, x, plan_b)} eklendi", "b": x.get("box")})
                continue
            y = la[i]
            name = _item_name(kind, x, plan_b)
            out += box_change(name, y.get("box"), x.get("box"))
            if (y.get("rotate") or 0) != (x.get("rotate") or 0):
                out.append({"kind": "changed", "text": f"{name}: döndürüldü ({y.get('rotate') or 0}° → {x.get('rotate') or 0}°)",
                            "b": x.get("box")})
            if bool(y.get("flip")) != bool(x.get("flip")):
                out.append({"kind": "changed", "text": f"{name}: aynalandı", "b": x.get("box")})
            if kind == "figure" and y.get("asset") != x.get("asset"):
                out.append({"kind": "changed", "text": f"{name}: görsel değişti", "b": x.get("box")})
            if kind == "bubble":
                if y.get("shape") != x.get("shape"):
                    out.append({"kind": "changed", "text": f"{name}: biçimi değişti", "b": x.get("box")})
                if (y.get("speaker") or "") != (x.get("speaker") or ""):
                    out.append({"kind": "changed", "text": f"{name}: konuşan {y.get('speaker') or 'yok'} → "
                                                           f"{x.get('speaker') or 'yok'}", "b": x.get("box")})
            if kind in ("text", "shape") and (y.get("effect") != x.get("effect") or y.get("fill") != x.get("fill")
                                              or y.get("stroke") != x.get("stroke") or y.get("params") != x.get("params")):
                out.append({"kind": "changed", "text": f"{name}: görünüşü değişti", "b": x.get("box")})
    return out


def _style(t: dict) -> list:
    return [[{k: r.get(k) for k in ("color", "weight", "size", "font")} for r in b.get("runs") or []]
            for b in t.get("blocks") or []]


def text_parts(pa: dict | None, pb: dict | None) -> list[dict]:
    """Metin farkı parçaları: sayfa metni, balonlar (kimlikle), serbest yazılar (kimlikle). Yalnız değişenler."""
    pa, pb = pa or {}, pb or {}
    out = []
    a, b = body_text(pa), body_text(pb)
    if a != b:
        out.append({"label": "Sayfa metni", "segments": word_diff(a, b)})
    for key, label, get in (("bubbles", "Balon", lambda x: x.get("text", "")),
                            ("texts", "Yazı", lambda x: _runs(x.get("runs")))):
        la = {x["id"]: x for x in pa.get(key) or []}
        lb = {x["id"]: x for x in pb.get(key) or []}
        for i in list(la) + [i for i in lb if i not in la]:
            ta = get(la[i]) if i in la else ""
            tb = get(lb[i]) if i in lb else ""
            if ta != tb:
                sp = (lb.get(i) or la.get(i) or {}).get("speaker")
                out.append({"label": f"{label}{f' ({sp})' if sp else ''}", "segments": word_diff(ta, tb)})
    return out


def compare(va: Version, vb: Version, ctx: Path) -> dict:
    A, B = va.plan, vb.plan
    pairs = match(A["pages"], B["pages"])
    matched = [(ia, ib) for ia, ib in pairs if ia is not None and ib is not None]
    order = [ia for ia, _ in matched]
    pages = []
    for k, (ia, ib) in enumerate(pairs):
        pa = A["pages"][ia] if ia is not None else None
        pb = B["pages"][ib] if ib is not None else None
        row = {"a": {"id": pa["id"], "no": plan_mod.FRONT + ia + 1} if pa else None,
               "b": {"id": pb["id"], "no": plan_mod.FRONT + ib + 1} if pb else None,
               "match": "id" if pa and pb and pa["id"] == pb["id"] else ("content" if pa and pb else None)}
        if pa and pb:
            text = text_parts(pa, pb)
            lay = layout_changes(pa, pb, A, B)
            pos = order.index(ia)
            moved = pos > 0 and order[pos - 1] > ia                    # önceki eşleşen sayfa eskiden sonradaydı
            if moved:
                lay.insert(0, {"kind": "order", "text": f"Sayfanın yeri değişti ({row['a']['no']}. → {row['b']['no']}. sayfa)"})
            row.update(status="changed" if text or lay else "same", text=text, layout=lay)
            row["overflow"] = bool(pb.get("overflow")) and not bool(pa.get("overflow"))
        elif pb:
            row.update(status="added", text=text_parts(None, pb), layout=[])
        else:
            row.update(status="removed", text=text_parts(pa, None), layout=[])
        pages.append(row)
    counts = {s: sum(1 for p in pages if p["status"] == s) for s in ("changed", "added", "removed", "same")}
    words = {"ins": 0, "del": 0}
    for p in pages:
        for t in p["text"]:
            for s in t["segments"]:
                if s["op"] in words:
                    words[s["op"]] += len(_WORD.findall(s["text"]))
    glob = []
    if (A.get("palette") or {}) != (B.get("palette") or {}):
        glob.append("Renk paleti değişti")
    if len(A["pages"]) != len(B["pages"]):
        glob.append(f"İç sayfa sayısı: {len(A['pages'])} → {len(B['pages'])}")
    if (A.get("page") or {}) != (B.get("page") or {}):
        glob.append("Sayfa ölçüsü değişti")
    return {"a": _vinfo(va, ctx), "b": _vinfo(vb, ctx), "pages": pages, "counts": counts, "words": words,
            "global": glob, "page": B.get("page") or A.get("page")}


def _vinfo(v: Version, ctx: Path) -> dict:
    return {"key": v.key, "job": v.d.name, "rev": v.rev, "current": v.current, "at": v.at, "by": v.by,
            "label": v.label(ctx), "pages": len(v.plan["pages"]),
            "title": (studio.read(v.d, "state.json") or {}).get("title")}


def unchanged_ranges(pages: list[dict]) -> list[tuple[int, int]]:
    """Değişmeyen sayfaların (yeni sürümün numarasıyla) ardışık aralıkları."""
    nos = sorted(p["b"]["no"] for p in pages if p["status"] == "same")
    out: list[tuple[int, int]] = []
    for n in nos:
        if out and n == out[-1][1] + 1:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return out


# ------------------------------------------------------------------ önizleme ve görsel fark
def version_pdf(v: Version) -> Path:
    """Sürümün iç sayfa PDF'i: şimdiki plan işin dizgisi; geçmiş sürüm kendi klasöründe bir kez dizilir."""
    if v.current:
        pdf = v.d / "dizgi" / "ic-sayfalar.pdf"
        if pdf.exists():
            return pdf
    wd = v.d / DIR / f"r{v.rev}"
    pdf = wd / "ic-sayfalar.pdf"
    if pdf.exists():
        return pdf
    with _lock(str(pdf)):
        if pdf.exists():
            return pdf
        from .typeset import PLAN_TEMPLATE, Typesetter
        data = plan_mod.render_data(v.d, v.plan)          # görseller işin dizgi klasörüne bağlanır
        dz = v.d / "dizgi"
        for pg in data["pages"]:
            rels = [(pg.get("art") or {}).get("path")] + [it.get("path") for it in pg.get("items", [])
                                                           if it.get("type") == "figure"]
            for rel in rels:
                if rel and (dz / rel).exists():
                    plan_mod._link(dz / rel, wd / rel)
        ts = Typesetter(wd, studio.fonts(), PLAN_TEMPLATE)
        tmp, _ = ts.build(data, "ic-sayfalar.pdf")
        os.replace(tmp, pdf)
    return pdf


def page_png(v: Version, pid: str, width: int) -> Path:
    import pymupdf
    no = plan_mod.page_no(v.plan, pid)
    pdf = version_pdf(v)
    out = pdf.parent / "onizleme" / f"s{no}-{width}.png" if not v.current else \
        v.d / DIR / "simdi" / f"{v.rev}-s{no}-{width}.png"
    if out.exists() and out.stat().st_mtime >= pdf.stat().st_mtime:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(pdf) as doc:
        if not 1 <= no <= doc.page_count:
            raise FileNotFoundError(no)
        page = doc[no - 1]
        zoom = width / page.rect.width
        tmp = out.with_suffix(".tmp.png")
        page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(tmp)
        os.replace(tmp, out)
    return out


def changed_regions(a_png: Path, b_png: Path) -> dict:
    """İki önizlemenin değişen bölgeleri (0–1 oranla, yeni sürümün görüntüsüne göre) ve değişen hücre oranı."""
    import numpy as np
    from PIL import Image
    ia = Image.open(a_png).convert("L")
    ib = Image.open(b_png).convert("L")
    if ia.size != ib.size:
        ia = ia.resize(ib.size, Image.Resampling.LANCZOS)
    a = np.asarray(ia, dtype=np.int16)
    b = np.asarray(ib, dtype=np.int16)
    h, w = b.shape
    diff = np.abs(a - b) > PIXEL_DELTA
    gh, gw = -(-h // CELL), -(-w // CELL)
    pad = np.zeros((gh * CELL, gw * CELL), dtype=bool)
    pad[:h, :w] = diff
    cells = pad.reshape(gh, CELL, gw, CELL).mean(axis=(1, 3)) > CELL_SHARE
    share = float(cells.mean()) if cells.size else 0.0
    return {"regions": _components(cells, gw, gh), "share": round(share, 4), "size": [w, h]}


def _components(cells, gw: int, gh: int) -> list[dict]:
    """Değişen hücrelerin bitişik (bir hücre boşluk dahil) kümeleri → oran kutuları."""
    seen = set()
    out = []
    on = {(int(y), int(x)) for y, x in zip(*cells.nonzero())}
    for start in sorted(on):
        if start in seen:
            continue
        stack, seen_here = [start], [start]
        seen.add(start)
        while stack:
            y, x = stack.pop()
            for dy in (-2, -1, 0, 1, 2):
                for dx in (-2, -1, 0, 1, 2):
                    n = (y + dy, x + dx)
                    if n in on and n not in seen:
                        seen.add(n)
                        stack.append(n)
                        seen_here.append(n)
        ys = [p[0] for p in seen_here]
        xs = [p[1] for p in seen_here]
        out.append({"x": round(min(xs) / gw, 4), "y": round(min(ys) / gh, 4),
                    "w": round((max(xs) + 1 - min(xs)) / gw, 4), "h": round((max(ys) + 1 - min(ys)) / gh, 4)})
    return sorted(out, key=lambda r: (r["y"], r["x"]))


def visual(va: Version, vb: Version, pa: str | None, pb: str | None, width: int = VISUAL_W) -> dict:
    """Bir sayfa çiftinin görsel farkı. Yalnız bir tarafta olan sayfa: tamamı değişmiş sayılır."""
    if pa and pb:
        return changed_regions(page_png(va, pa, width), page_png(vb, pb, width))
    return {"regions": [{"x": 0, "y": 0, "w": 1, "h": 1}], "share": 1.0, "size": None}


# ------------------------------------------------------------------ rapor (PDF)
def _fmt(at: str | None) -> str | None:
    """ISO zamanı (UTC) yerel «gg.aa.yyyy ss:dd»."""
    if not at:
        return None
    try:
        return datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone().strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return at


REPORT_TEMPLATE = Path(__file__).resolve().parent / "templates" / "diff_report.typ"
REPORT_W = 520


def report(ctx: Path, va: Version, vb: Version, by: str) -> Path:
    """Değişiklik raporu PDF'i (işin `karsilastir/rapor-<özet>/` klasöründe; aynı iki sürüm için bir kez)."""
    import shutil
    diff = compare(va, vb, ctx)
    digest = hashlib.sha1(f"{va.key}|{vb.key}|{va.at}|{vb.at}".encode()).hexdigest()[:12]
    wd = ctx / DIR / f"rapor-{digest}"
    pdf = wd / "degisiklik-raporu.pdf"
    if pdf.exists():
        return pdf
    with _lock(str(pdf)):
        if pdf.exists():
            return pdf
        wd.mkdir(parents=True, exist_ok=True)
        rows = []
        for i, p in enumerate(diff["pages"]):
            if p["status"] == "same":
                continue
            row = {**p, "img_a": None, "img_b": None, "regions": [],
                   "text": [{**t, "segments": condense(t["segments"])} for t in p["text"]]}
            for side, v in (("a", va), ("b", vb)):
                if p[side]:
                    try:
                        src = page_png(v, p[side]["id"], REPORT_W)
                        rel = f"s{i}-{side}.png"
                        shutil.copy(src, wd / rel)
                        row[f"img_{side}"] = rel
                    except Exception:  # noqa: BLE001 - önizlemesi çizilemeyen sayfa raporda yazıyla kalır
                        row[f"img_{side}"] = None
            try:
                row["regions"] = visual(va, vb, p["a"] and p["a"]["id"], p["b"] and p["b"]["id"], REPORT_W)["regions"]
            except Exception:  # noqa: BLE001
                row["regions"] = []
            rows.append(row)
        title = (studio.read(vb.d, "state.json") or {}).get("title") or (studio.read(ctx, "state.json") or {}).get("title") or ctx.name
        for side in ("a", "b"):
            diff[side] = {**diff[side], "at": _fmt(diff[side]["at"])}
        data = {"title": title, "a": diff["a"], "b": diff["b"], "counts": diff["counts"], "words": diff["words"],
                "global": diff["global"], "pages": rows,
                "same": [f"{x}" if x == y else f"{x}–{y}" for x, y in unchanged_ranges(diff["pages"])],
                "by": by, "at": datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M"),
                "ratio": (diff["page"]["h"] / diff["page"]["w"]) if diff.get("page") else 1.4}
        (wd / "data.json").write_text(json.dumps(data, ensure_ascii=False))
        shutil.copy(REPORT_TEMPLATE, wd / REPORT_TEMPLATE.name)
        import typst
        tmp = wd / "rapor.yeni.pdf"
        typst.compile(str(wd / REPORT_TEMPLATE.name), output=str(tmp), root=str(wd), font_paths=[str(studio.fonts())],
                      ignore_system_fonts=True, sys_inputs={"data": "data.json"})
        os.replace(tmp, pdf)
    return pdf
