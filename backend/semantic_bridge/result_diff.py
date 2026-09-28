"""«Ne değişti» — bir sorgu sonucunun önceki sonuçla farkı (öneri 5). Pano kartı ve planlı rapor e-postası kullanır.

Fark **kodla** bulunur: satırlar anahtar kolonlarıyla (sayı olmayan kolonlar) eşlenir, sayı kolonlarının toplamı ve satır
bazındaki değişimi hesaplanır; yeni gelen ve düşen satırlar sayılır. Zeki AI yalnız bu olguları madde madde anlatır
(`zeki_text.interpret`, sayı denetimli); olmazsa aynı olgular kural metni olarak yazılır. Önceki sonuç yoksa «ilk koşu»
denir, fark uydurulmaz.

Tavan yok: bütün satırlar karşılaştırılır; olgulara en büyük N değişim yazılır ve toplam kaç satırın değiştiği ayrıca
söylenir (sessiz kesme yok).
"""
from __future__ import annotations

import math
from typing import Any, Optional

from semantic_bridge import zeki_text as Z

TOP = 5


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(float(v)) else None
    return None


def _names(cols: list[Any]) -> list[str]:
    return [c["name"] if isinstance(c, dict) else str(c) for c in cols or []]


def split_columns(cols: list[Any], rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """(anahtar kolonları, ölçü kolonları). Ölçü: dolu hücrelerinin hepsi sayı olan kolon. Tarih/metin anahtardır.
    Tek satırlık sonuçta anahtar yoktur (KPI)."""
    names = _names(cols) or (list(rows[0].keys()) if rows else [])
    keys, measures = [], []
    for n in names:
        vals = [r.get(n) for r in rows if r.get(n) is not None]
        if vals and all(_num(v) is not None for v in vals):
            measures.append(n)
        else:
            keys.append(n)
    # Anahtarsız çok satırlı sonuçta (yalnız sayı kolonları) ilk kolon anahtar sayılır: yıl/ay gibi sayı kodları.
    if not keys and measures and len(rows) > 1:
        keys, measures = measures[:1], measures[1:]
    return keys, measures


def _key(r: dict[str, Any], keys: list[str]) -> tuple:
    return tuple("" if r.get(k) is None else str(r.get(k)) for k in keys)


def diff(prev: Optional[dict[str, Any]], cur: dict[str, Any], top: int = TOP) -> dict[str, Any]:
    """`prev`/`cur`: {"columns", "records", "at"?}. Dönen: {"ilk": True} ya da toplam/satır farkları."""
    cur_rows = list(cur.get("records") or [])
    if not prev or prev.get("records") is None:
        return {"ilk": True, "satir": len(cur_rows)}
    prev_rows = list(prev.get("records") or [])
    keys, measures = split_columns(cur.get("columns") or [], cur_rows or prev_rows)
    _pk, pm = split_columns(prev.get("columns") or [], prev_rows)
    measures = [m for m in measures if m in pm or not prev_rows]
    if not measures:
        return {"ilk": False, "olcuYok": True, "satirOnceki": len(prev_rows), "satirSimdi": len(cur_rows)}
    lead = measures[0]
    totals = []
    for m in measures:
        a = sum(_num(r.get(m)) or 0.0 for r in prev_rows)
        b = sum(_num(r.get(m)) or 0.0 for r in cur_rows)
        totals.append({"kolon": m, "onceki": round(a, 2), "simdi": round(b, 2), "fark": round(b - a, 2),
                       "oran": round((b - a) / a, 4) if abs(a) > 1e-9 else None})
    changes: list[dict[str, Any]] = []
    new_keys: list[str] = []
    gone_keys: list[str] = []
    if keys:
        pmap = {_key(r, keys): r for r in prev_rows}
        cmap = {_key(r, keys): r for r in cur_rows}
        for k, r in cmap.items():
            label = " · ".join(x for x in k if x) or "—"
            if k not in pmap:
                new_keys.append(label)
                a = 0.0
            else:
                a = _num(pmap[k].get(lead)) or 0.0
            b = _num(r.get(lead)) or 0.0
            if abs(b - a) > 1e-9:
                changes.append({"satir": label, "onceki": round(a, 2), "simdi": round(b, 2), "fark": round(b - a, 2),
                                "yeni": k not in pmap})
        for k, r in pmap.items():
            if k not in cmap:
                label = " · ".join(x for x in k if x) or "—"
                gone_keys.append(label)
                a = _num(r.get(lead)) or 0.0
                if abs(a) > 1e-9:
                    changes.append({"satir": label, "onceki": round(a, 2), "simdi": 0.0, "fark": round(-a, 2), "dustu": True})
    changes.sort(key=lambda c: (-abs(c["fark"]), c["satir"]))
    return {"ilk": False, "anahtar": keys, "olcu": lead, "toplamlar": totals, "satirOnceki": len(prev_rows),
            "satirSimdi": len(cur_rows), "degisenSatir": len(changes), "enBuyuk": changes[:top],
            "yeni": new_keys[:top], "yeniSayisi": len(new_keys), "dusen": gone_keys[:top], "dusenSayisi": len(gone_keys),
            "oncekiZaman": prev.get("at"), "degisti": bool(changes) or any(abs(t["fark"]) > 1e-9 for t in totals)}


def _n(v: Optional[float]) -> str:
    if v is None:
        return "—"
    d = 0 if abs(v - round(v)) < 1e-9 else 2
    s = f"{abs(v):,.{d}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")
    return ("−" if v < 0 else "") + s


def bullets(d: dict[str, Any]) -> list[str]:
    """Kural maddeleri (olgular). Model yoksa ya da denetimden geçmezse bunlar gösterilir."""
    if d.get("ilk"):
        return ["İlk koşu: karşılaştırılacak önceki sonuç yok."]
    if d.get("olcuYok"):
        return [f"Satır sayısı {_n(d['satirOnceki'])} → {_n(d['satirSimdi'])}; sayı kolonu olmadığı için tutar karşılaştırılmadı."]
    if not d.get("degisti"):
        return ["Önceki sonuca göre değişiklik yok."]
    out = []
    for t in d["toplamlar"][:3]:
        pct = f" (%{_n(round(abs(t['oran']) * 100, 1))} {'artış' if t['fark'] > 0 else 'azalış'})" if t.get("oran") is not None and t["fark"] else ""
        out.append(f"{t['kolon']} toplamı {_n(t['onceki'])} → {_n(t['simdi'])}{pct}.")
    if d["satirOnceki"] != d["satirSimdi"]:
        out.append(f"Satır sayısı {_n(d['satirOnceki'])} → {_n(d['satirSimdi'])}.")
    if d.get("enBuyuk"):
        parts = [f"{c['satir']} {_n(c['onceki'])} → {_n(c['simdi'])}" for c in d["enBuyuk"][:3]]
        more = f" (toplam {_n(d['degisenSatir'])} satır değişti)" if d["degisenSatir"] > 3 else ""
        out.append(f"En büyük {d['olcu']} değişimleri: " + "; ".join(parts) + more + ".")
    if d.get("yeniSayisi"):
        out.append(f"Yeni gelen {_n(d['yeniSayisi'])} satır: " + ", ".join(d["yeni"][:3]) + ("…" if d["yeniSayisi"] > 3 else "") + ".")
    if d.get("dusenSayisi"):
        out.append(f"Listeden düşen {_n(d['dusenSayisi'])} satır: " + ", ".join(d["dusen"][:3]) + ("…" if d["dusenSayisi"] > 3 else "") + ".")
    return out


TASK = ("Bir raporun önceki sonucuna göre ne değiştiğini yöneticiye 2–4 kısa cümleyle anlat; her cümle ayrı bir madde "
        "olacak. En büyük değişimle başla. Yalnız olgulardaki sayıları kullan, neden uydurma.")


def explain(d: dict[str, Any], title: str, *, llm: Any = None, rt: Any = None, module: str = "fark",
            priority: Optional[int] = None) -> dict[str, Any]:
    """{"maddeler": [...], "kaynak": zeki|kural, "neden"}. İlk koşu ya da değişiklik yoksa model çağrılmaz."""
    rule = bullets(d)
    if d.get("ilk") or d.get("olcuYok") or not d.get("degisti"):
        return {"maddeler": rule, "kaynak": "kural", "neden": None}
    facts = [f"Rapor: {title}.", *rule]
    it = Z.interpret(facts, " ".join(rule), llm=llm, rt=rt, module=module, priority=priority, task=TASK,
                     min_sentences=2, max_sentences=4, max_chars=900)
    items = Z.sentences(it.metin) if it.kaynak == "zeki" else rule
    return {"maddeler": items, "kaynak": it.kaynak, "neden": it.neden}
