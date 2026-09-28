"""H1 Kategori ağacı: kitap profili önerisi (K2 — Zeki AI önerir, editör onaylar).

Kural: **beyan varsa beyan kazanır.** Kitabın CRM sınıflamaları yürürlükteki ağaçta tek bir düğüme eşleniyorsa
kategori önerisi odur (model çağrılmaz); hedef kitle, tür, yaş CRM'de doluysa öneri CRM değeridir. Model yalnız boş
ya da belirsiz alanda ve yalnız **kapalı kümede** seçer (`QueuedLlm.choose`: seçenekler harf etiketli, tek token +
olasılık; uydurma kategori imkânsızdır):

- **Kategori:** ağaçta hiyerarşik seçim — kitabın markasına eşlenen düğümden (yoksa köklerden) başlanır, her düzeyde
  çocuklar + «bu düzeyde kal» seçeneği sorulur; olasılık eşiğin altına düşünce inilmez. CRM sınıflamaları birden çok
  düğüme eşit düşüyorsa yalnız o adaylar sorulur.
- **Hedef kitle:** CRM'in seçenek etiketleri. **Tür:** CRM tür sözlüğü (`new_turBase`, 26'dan çoksa eleme turu).
  **Yaş:** CRM'de kullanılan yaş aralıkları (yetişkin kitabında sorulmaz).
- **Tema ve etiket (çok değerli):** her aday için ayrı evet/hayır. Adaylar kitaptan bağımsız, veriden türetilir:
  (a) adı kitabın metninde (arka kapak, spot, anahtar kelime metni) geçen sözlük kaydı — kanıt cümlesi deterministik
  olarak metinde aranır ve gösterilir; (b) aynı düğümdeki kitapların en az `CATEGORY_COOCCUR_SHARE` payında kullanılan
  kayıt. Sözlük dışı etiket model tarafından üretilmez; editörün yazdığı yeni etiket «yeni etiket önerisi» kuyruğuna
  düşer.

Eşikler (`CATEGORY_SUGGEST_MIN_PROB`, `CATEGORY_SUGGEST_MIN_MARGIN`; başlangıç 0,70 / 0,30 — golden set ile
ölçülecek) altında kalan öneri «Zeki AI emin değil» işaretiyle gösterilir, «tümünü onayla» ile kabul edilmez.
Rakam, ad, tarih model tarafından üretilmez.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from typing import Any, Optional

from semantic_bridge import categories as C

log = logging.getLogger("semantic.categories.propose")

SYSTEM = ("Sen bir yayınevinin katalog editörüsün. Yalnız verilen künye ve metne dayanarak karar verirsin; "
          "bilmediğin bir şeyi varsaymazsın.")
STAY = "Hiçbiri — üst kategoride kalsın"
YES, NO = "evet", "hayır"
PROMPT_TEXT = 2500   # istemdeki arka kapak metni uzunluğu (kanıtta «kırpıldı» yazılır)


def _clip(s: Optional[str], n: int) -> tuple[Optional[str], bool]:
    if not s:
        return None, False
    return (s[: n - 1].rstrip() + "…", True) if len(s) > n else (s, False)


def context_text(book: dict[str, Any], texts: dict[str, Any], ctx: Optional[C.TreeCtx] = None) -> tuple[str, list[str]]:
    """İstemin künye bölümü ve kullanılan kaynak alanlar (kanıt listesi)."""
    lines, used = [], []

    def add(label: str, v: Any, key: str) -> None:
        if v in (None, "", []):
            return
        lines.append(f"{label}: {v}")
        used.append(key)

    add("Kitap", book.get("ad"), "Kitap adı")
    add("Yazar", book.get("yazar"), "Yazar")
    add("Yayınevi", (book.get("marka") or {}).get("name"), "Yayınevi")
    add("Dizi", (book.get("dizi") or {}).get("name"), "Dizi")
    add("Kitaplık (CRM)", (book.get("kitaplik") or {}).get("name"), "Kitaplık")
    add("Hedef kitle (CRM)", (book.get("hedefKitle") or {}).get("label"), "Hedef kitle")
    age = book.get("yas") or {}
    if age:
        add("Yaş (CRM)", f"{age.get('bas') or ''}-{age.get('bit') or ''}", "Yaş")
    add("Tür (CRM)", ", ".join(x["name"] for x in book.get("tur") or []) or book.get("turMetni"), "Tür")
    add("Web kategorisi (CRM)", book.get("web"), "Web kategorisi")
    add("Anahtar kelimeler", ", ".join(x["name"] for x in book.get("anahtarkelime") or []) or texts.get("anahtarMetin"),
        "Anahtar kelimeler")
    add("Sayfa sayısı", texts.get("sayfa"), "Sayfa sayısı")
    spot, _ = _clip(texts.get("spot"), 800)
    add("Kitap spotu", spot, "Kitap spotu")
    ozet, cut = _clip(texts.get("ozet"), PROMPT_TEXT)
    add("Arka kapak metni", ozet, "Arka kapak metni (kırpıldı)" if cut else "Arka kapak metni")
    return "\n".join(lines), used


def corpus_stats(snapshots: list[dict[str, Any]], ctx: C.TreeCtx) -> dict[str, Any]:
    """Düğüm başına tema / anahtar kelime kullanımı (ata düğümler dahil) ve CRM'de kullanılan yaş aralıkları."""
    node: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "tema": Counter(), "etiket": Counter()})
    ages: Counter = Counter()
    for b in snapshots:
        age = b.get("yas") or {}
        if age.get("bas") is not None and age.get("bit") is not None and age["bas"] <= age["bit"]:
            ages[f"{age['bas']}-{age['bit']}"] += 1
        if ctx.empty:
            continue
        nid = C.resolve(ctx, b)["nodeId"]
        if not nid:
            continue
        for x in (nid, *ctx.ancestors(nid)):
            s = node[x]
            s["n"] += 1
            for t in b.get("tema") or []:
                s["tema"][t["name"]] += 1
            for t in b.get("anahtarkelime") or []:
                s["etiket"][t["name"]] += 1
    return {"node": node, "ages": ages}


def _snippet(text: str, term: str) -> Optional[str]:
    text = " ".join(text.split())
    tf = C.fold(term)
    if len(tf) < 3:
        return None
    ft = C.fold(text)
    m = re.search(r"(?<!\w)" + re.escape(tf) + r"(?!\w)", ft)
    if not m:
        return None
    # fold uzunluğu korur (İ→i, I→ı tek karakter); boşluk sıkıştırması yüzünden kayma olabilir, metin önce sıkıştırılır
    a, b = max(0, m.start() - 70), min(len(text), m.end() + 70)
    return ("…" if a else "") + text[a:b].strip() + ("…" if b < len(text) else "")


def _entry(proposed: Any, *, source: str, method: str, confident: bool, probability: Optional[float] = None,
           margin: Optional[float] = None, evidence: Optional[list[dict[str, Any]]] = None, **extra: Any) -> dict[str, Any]:
    return {"proposed": proposed, "source": source, "method": method, "confident": confident,
            "probability": None if probability is None else round(float(probability), 4),
            "margin": None if margin is None else round(float(margin), 4), "evidence": evidence or [], **extra}


class Proposer:
    def __init__(self, llm: Any, ctx: C.TreeCtx, *, vocab: dict[str, Any], labels: dict[str, Any], stats: dict[str, Any],
                 th: dict[str, float], user_id: Optional[str] = None):
        self.llm = llm if llm is not None and hasattr(llm, "choose") else None
        self.ctx, self.vocab, self.labels, self.stats, self.th = ctx, vocab, labels, stats, th
        self.user_id = user_id
        self.calls = 0

    def _choose(self, prompt: str, choices: list[str]):
        r = self.llm.choose(prompt, choices, system=SYSTEM, user_id=self.user_id)
        self.calls += r.calls
        return r

    def _ok(self, r: Any) -> bool:
        return bool(r.choice is not None and r.confident(self.th["minProb"], min_margin=self.th["minMargin"]))

    # ------------------------------------------------------------------ alanlar

    def kategori(self, book: dict[str, Any], head: str, used: list[str]) -> Optional[dict[str, Any]]:
        ctx = self.ctx
        if ctx.empty:
            return None
        res = C.resolve(ctx, book)
        hits = [{"kind": "crm", "text": f"{h['systemLabel']}: {h['value']}"} for h in res["hits"] if h["nodeId"] == res["nodeId"]]
        if res["nodeId"]:
            return _entry(res["nodeId"], source=res["reason"], method="beyan", confident=True, evidence=hits)
        if self.llm is None:
            return None
        ev = [{"kind": "girdi", "text": ", ".join(used)}]
        if res["candidates"]:
            labels = [ctx.path(n) or n for n in res["candidates"]]
            r = self._choose(f"{head}\n\nBu kitap aşağıdaki kategorilerden hangisine girer?", labels)
            if r.choice is None:
                return _entry(None, source="Zeki AI önerisi", method=r.method, confident=False, evidence=ev)
            alts = _alts(r, res["candidates"], labels)
            return _entry(res["candidates"][r.index], source="Zeki AI önerisi (CRM sınıflamaları birden çok düğüme düşüyordu)",
                          method=r.method, confident=self._ok(r), probability=r.probability, margin=r.margin,
                          evidence=ev + [{"kind": "aday", "text": " · ".join(labels)}], alternatives=alts)
        start = ctx.start_nodes(book)
        current: Optional[str] = start[0] if len(start) == 1 else None
        options = [n for n in start] if len(start) > 1 else list(ctx.children.get(current, []))
        chosen, prob, conf, steps, last_r, last_opts = current, 1.0, True, [], None, None
        if current:
            ev.append({"kind": "crm", "text": f"Başlangıç: {ctx.path(current)} (yayınevi eşlemesi)"})
        while options:
            labels = [ctx.nodes[n]["name"] for n in options]
            if len({C.fold(x) for x in labels}) < len(labels):
                labels = [ctx.path(n) or n for n in options]
            if chosen:
                labels.append(STAY)
            where = f"Kategori ağacında «{ctx.path(chosen)}» altındayız." if chosen else "Kategori ağacının en üst düzeyindeyiz."
            r = self._choose(f"{head}\n\n{where} Bu kitap aşağıdakilerden hangisine girer?", labels)
            steps.append({"secenekler": labels, "secim": r.choice, "olasilik": r.probability, "marj": r.margin,
                          "yontem": r.method})
            if r.choice is None or r.choice == STAY:
                conf = conf and r.choice == STAY and self._ok(r)
                break
            last_r, last_opts = r, (options, labels)
            prob *= float(r.probability or 0.0)
            chosen = options[r.index]
            if not self._ok(r):
                conf = False
                break
            options = list(ctx.children.get(chosen, []))
        if not chosen:
            return _entry(None, source="Zeki AI önerisi", method="none", confident=False, evidence=ev, steps=steps)
        alts = _alts(last_r, *last_opts) if last_r is not None else []
        ev.append({"kind": "adim", "text": " → ".join(f"{s['secim'] or '?'} (%{round((s['olasilik'] or 0) * 100)})" for s in steps)})
        return _entry(chosen, source="Zeki AI önerisi (ağaçta düzey düzey seçim)", method=(steps[-1]["yontem"] if steps else "beyan"),
                      confident=conf, probability=prob if steps else None,
                      margin=(last_r.margin if last_r else None), evidence=ev, alternatives=alts, steps=steps)

    def hedef_kitle(self, book: dict[str, Any], head: str) -> Optional[dict[str, Any]]:
        declared = (book.get("hedefKitle") or {}).get("label")
        if declared:
            return _entry(declared, source="CRM beyanı", method="beyan", confident=True,
                          evidence=[{"kind": "crm", "text": f"Hedef kitle: {declared}"}])
        labels = [v for _, v in sorted(((int(k), v) for k, v in (self.labels.get("hedefKitle") or {}).items()))]
        if not labels or self.llm is None:
            return None
        r = self._choose(f"{head}\n\nBu kitabın hedef kitlesi hangisi?", labels)
        if r.choice is None:
            return None
        return _entry(r.choice, source="Zeki AI önerisi", method=r.method, confident=self._ok(r), probability=r.probability,
                      margin=r.margin, evidence=[{"kind": "girdi", "text": "Künye ve arka kapak metni"}])

    def tur(self, book: dict[str, Any], head: str) -> Optional[dict[str, Any]]:
        declared = [x["name"] for x in book.get("tur") or []]
        if not declared and book.get("turMetni"):
            from semantic_bridge.categories_sources import split_text

            declared = split_text(book["turMetni"])
        if declared:
            return _entry(declared, source="CRM beyanı", method="beyan", confident=True,
                          evidence=[{"kind": "crm", "text": f"Tür: {', '.join(declared)}"}])
        names = sorted({v["name"] for v in (self.vocab.get("tur") or {}).values() if v.get("active") and v.get("name") not in (None, "—")},
                       key=C.fold)
        if not names or self.llm is None:
            return None
        r = self._choose(f"{head}\n\nBu kitabın türü hangisi?", names)
        if r.choice is None:
            return None
        return _entry([r.choice], source="Zeki AI önerisi (CRM tür sözlüğünden)", method=r.method, confident=self._ok(r),
                      probability=r.probability, margin=r.margin,
                      evidence=[{"kind": "girdi", "text": f"{len(names)} türlük CRM sözlüğü"}])

    def yas(self, book: dict[str, Any], head: str, audience: Optional[str]) -> Optional[dict[str, Any]]:
        age = book.get("yas") or {}
        if age.get("bas") is not None or age.get("bit") is not None:
            v = f"{age.get('bas') if age.get('bas') is not None else ''}-{age.get('bit') if age.get('bit') is not None else ''}"
            return _entry(v, source="CRM beyanı", method="beyan", confident=True, evidence=[{"kind": "crm", "text": f"Yaş: {v}"}])
        adult = next((v for v in (self.labels.get("hedefKitle") or {}).values() if C.fold(v) == C.fold("Yetişkin")), None)
        if not audience or (adult and C.fold(audience) == C.fold(adult)) or self.llm is None:
            return None
        ranges = sorted(self.stats.get("ages") or {}, key=lambda s: tuple(int(x) for x in s.split("-")))
        if not ranges:
            return None
        r = self._choose(f"{head}\n\nHedef kitle: {audience}. Bu kitap hangi yaş aralığına uygundur?", ranges)
        if r.choice is None:
            return None
        return _entry(r.choice, source="Zeki AI önerisi (CRM'de kullanılan yaş aralıklarından)", method=r.method,
                      confident=self._ok(r), probability=r.probability, margin=r.margin,
                      evidence=[{"kind": "girdi", "text": f"{len(ranges)} yaş aralığı"}])

    def many(self, field: str, book: dict[str, Any], head: str, text: str, node_id: Optional[str],
             vocab_names: list[str]) -> Optional[dict[str, Any]]:
        key = "tema" if field == "tema" else "anahtarkelime"
        current = [x["name"] for x in book.get(key) or []]
        cur_f = {C.fold(x) for x in current}
        cands: dict[str, dict[str, Any]] = {}
        for name in vocab_names:
            if C.fold(name) in cur_f:
                continue
            snip = _snippet(text, name) if text else None
            if snip:
                cands[name] = {"kind": "metin", "text": snip}
        stat = (self.stats.get("node") or {}).get(node_id or "") if node_id else None
        if stat and stat["n"]:
            vocab_f = {C.fold(v) for v in vocab_names}
            for name, k in stat[field].items():
                share = k / stat["n"]
                if share >= self.th["coShare"] and C.fold(name) not in cur_f and name not in cands and C.fold(name) in vocab_f:
                    cands[name] = {"kind": "benzer", "text": f"Aynı kategorideki {stat['n']} kitabın %{round(share * 100)}'inde"}
        if not cands:
            if current:
                return _entry(current, source="CRM beyanı", method="beyan", confident=True,
                              evidence=[{"kind": "crm", "text": ", ".join(current)}])
            return None
        if self.llm is None:
            return None
        label = "temasını taşıyor" if field == "tema" else "etiketiyle aranmalı"
        added, ev, weak = [], [], []
        for name, why in sorted(cands.items(), key=lambda kv: C.fold(kv[0])):
            r = self._choose(f"{head}\n\nBu kitap «{name}» {label} mı?", [YES, NO])
            if r.choice == YES and self._ok(r):
                added.append(name)
                ev.append({**why, "term": name, "probability": r.probability})
            elif r.choice == YES:
                weak.append({"term": name, "probability": r.probability, **why})
        proposed = current + added
        if not added and not current:
            return _entry([], source="Zeki AI önerisi", method="logprobs", confident=False, evidence=[], weak=weak,
                          candidates=len(cands))
        return _entry(proposed, source="CRM beyanı + Zeki AI önerisi" if current else "Zeki AI önerisi",
                      method="logprobs" if added else "beyan", confident=True, evidence=ev, weak=weak, added=added,
                      candidates=len(cands))

    # ------------------------------------------------------------------ hepsi

    def run(self, book: dict[str, Any], texts: dict[str, Any], tag_vocab: list[str]) -> dict[str, dict[str, Any]]:
        head, used = context_text(book, texts, self.ctx)
        out: dict[str, dict[str, Any]] = {}
        k = self.kategori(book, head, used)
        if k is not None and k.get("proposed"):
            out["kategori"] = k
        h = self.hedef_kitle(book, head)
        if h is not None:
            out["hedef_kitle"] = h
        t = self.tur(book, head)
        if t is not None:
            out["tur"] = t
        y = self.yas(book, head, (h or {}).get("proposed"))
        if y is not None:
            out["yas"] = y
        text = " ".join(x for x in (texts.get("ozet"), texts.get("spot"), texts.get("anahtarMetin")) if x)
        node = (k or {}).get("proposed") if (k or {}).get("confident") else C.resolve(self.ctx, book)["nodeId"] if not self.ctx.empty else None
        themes = sorted({v["name"] for v in (self.vocab.get("tema") or {}).values() if v.get("active") and v.get("name") not in (None, "—")}, key=C.fold)
        m = self.many("tema", book, head, text, node, themes)
        if m is not None:
            out["tema"] = m
        e = self.many("etiket", book, head, text, node, tag_vocab)
        if e is not None:
            out["etiket"] = e
        return out


def _alts(r: Any, ids: list[str], labels: list[str]) -> list[dict[str, Any]]:
    if not r or not r.probs:
        return []
    by = dict(zip(labels, ids))
    top = sorted(((p, lab) for lab, p in r.probs.items() if lab in by), reverse=True)[:3]
    return [{"nodeId": by[lab], "label": lab, "probability": round(float(p), 4)} for p, lab in top]
