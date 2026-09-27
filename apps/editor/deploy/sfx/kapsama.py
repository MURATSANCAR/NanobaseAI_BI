#!/usr/bin/env python3
"""Efekt havuzunun kapsama ölçümü: yayınevinin çocuk kitaplarındaki bütün efekt ipuçları havuzda karşılanıyor mu?

GPU'da GEÇİCİ kapta (editor-py imajı, editor-net ağı, editor.env) çalışır; derlem YALNIZ OKUNUR. Model çağrıları
gateway üzerinden (Zeki AI, `book-director`), stüdyonun kullandığı istemle (production/sfx.py PROMPT) — kitaba özel
istem yok. Çıktılar /data/editor/sfx/_olcum/ altında.

    kapsama.py metin                 derlemden çocuk kitaplarının sayfa metni → sayfalar.jsonl
    kapsama.py ipucu [--ornek N]     sayfalar → ipuclari.jsonl (N verilirse kitaplardan eşit aralıklı N kitap)
    kapsama.py esle                  benzersiz ipuçları → havuzda en iyi 3 aday → esleme.jsonl
    kapsama.py secim                 stüdyonun seçim yolu: ilk 8 aday → Zeki AI tek harf ya da «hiçbiri» → secim.jsonl
    kapsama.py yargi                 her ipucu × ilk 3 aday: Zeki AI «bu dosya istenen ses mi» (E/H olasılığı)
    kapsama.py ayar                  benzerlik eşiği ↔ yargı doğruluğu tablosu, önerilen eşik → esik.json
    kapsama.py rapor [--esik X]      karşılanan %, karşılanmayanların en sık 50'si → rapor.json, karsilanmayan.json

Derlem: /data/organized/cocuk altındaki bütün PDF'ler + öteki klasörlerde künyesinde CHILD_MAX yaşın altında başlayan
bant yazan kitaplar (nonbook hariç); aynı metin tek sayılır. Sayfa metni okumadaki paragraf kurucuyla
(document.paragraphs_from_layout). Derlem çok büyük olduğu için ardışık PAGES_PER_CALL sayfa tek çağrıda okunur ve
her okuma turu ayrı dosyaya yazılır (`--etiket`); eşleştirme bütün turların BİRLEŞİMİNİ alır (stüdyodaki oylama kitap
içi kesinlik içindir; burada istenen, çocuk kitaplarının isteyebileceği seslerin eksiksiz listesidir). Alıntısı
metinde birebir geçmeyen ipucu her turda atılır.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

OUT = Path("/data/editor/sfx/_olcum")
CORPUS = Path("/data/organized")
PAGES_PER_CALL = 4
CONCURRENCY = 6


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------------ metin
def _book(path: str) -> dict | None:
    import pymupdf

    from editor.document import _garbled_ratio, paragraphs_from_layout
    from editor.proofing import _age_fit_text as T
    try:
        doc = pymupdf.open(path)
    except Exception:  # noqa: BLE001
        return None
    pages = []
    for i, page in enumerate(doc, start=1):
        try:
            if _garbled_ratio(page.get_text("text") or "") > 0.02:
                continue
            paras = [p for p in paragraphs_from_layout(page) if p.strip()]
        except Exception:  # noqa: BLE001
            continue
        if paras:
            pages.append({"page": i, "paras": paras})
    full = " ".join(p for pg in pages for p in pg["paras"])
    band = T.declared_band(full)
    return {"path": path, "band": list(band) if band else None, "pages": pages,
            "hash": hashlib.sha256(full.encode()).hexdigest()[:16], "words": len(full.split())}


def step_metin():
    from concurrent.futures import ProcessPoolExecutor

    from editor.production.sfx import CHILD_MAX
    OUT.mkdir(parents=True, exist_ok=True)
    paths = sorted(str(p) for p in CORPUS.rglob("*.pdf") if "/nonbook/" not in str(p))
    seen, n_child = set(), 0
    with ProcessPoolExecutor(32) as ex, (OUT / "sayfalar.jsonl").open("w") as f:
        for b in ex.map(_book, paths, chunksize=1):
            if not b or not b["pages"] or b["hash"] in seen:
                continue
            child = "/cocuk/" in b["path"] or (b["band"] and b["band"][0] < CHILD_MAX)
            if not child:
                continue
            seen.add(b["hash"])
            n_child += 1
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    log("PDF", len(paths), "çocuk kitabı", n_child)


# ------------------------------------------------------------------ ipucu
def _units(book: dict, pages: list[dict]):
    from editor.production import narration as N
    units = []
    for pg in pages:
        for k, t in enumerate(pg["paras"]):
            units.append(N.Unit(f"s{pg['page']}b{k}", "para", None, "anlatici-kadin", t, N.read(t)))
    return units


TEMPERATURE = 0.7                 # 0,2'de model çok sayfalı parçada çoğunlukla boş liste veriyordu (ölçüldü)


async def _chunk(llm, book: dict, pages: list[dict], sem: asyncio.Semaphore) -> list[dict]:
    from editor.production import sfx
    units = _units(book, pages)
    if not units:
        return []
    async with sem:
        try:
            items = await sfx._read_page(llm, units, "olcum", TEMPERATURE)
        except Exception as e:  # noqa: BLE001
            return [{"error": f"{type(e).__name__}: {str(e)[:200]}", "book": book["path"],
                     "pages": [p["page"] for p in pages]}]
    cues, stats = sfx._vote([items], units, min_votes=1)
    out = []
    for c in cues:
        out.append({"book": book["path"], "page": int(c["block"][1:].split("b")[0]), "kind": c["kind"], "type": c["type"],
                    "quote": c["quote"], "query": c["query"], "query_en": c["query_en"], "category": c["category"]})
    out.append({"_stats": stats, "book": book["path"], "pages": [p["page"] for p in pages]})
    return out


async def step_ipucu(sample: int | None, label: str = ""):
    from editor.production.run import FileLlm
    books = [json.loads(x) for x in (OUT / "sayfalar.jsonl").read_text().splitlines() if x.strip()]
    if sample:
        step = max(1, len(books) // sample)
        books = books[::step][:sample]
    done = set()
    outp = OUT / (f"ipuclari-{label}.jsonl" if label else "ipuclari.jsonl")
    if outp.exists():
        for line in outp.read_text().splitlines():
            r = json.loads(line)
            if "_stats" in r:
                done.add((r["book"], tuple(r["pages"])))
    llm = FileLlm(OUT / "provenance.jsonl")
    sem = asyncio.Semaphore(CONCURRENCY)
    jobs = []
    for b in books:
        pgs = b["pages"]
        for k in range(0, len(pgs), PAGES_PER_CALL):
            chunk = pgs[k:k + PAGES_PER_CALL]
            if (b["path"], tuple(p["page"] for p in chunk)) not in done:
                jobs.append((b, chunk))
    log("kitap", len(books), "çağrı", len(jobs), "(önceden", len(done), ")")
    t0 = time.time()
    n = 0
    with outp.open("a") as f:
        for coro in asyncio.as_completed([_chunk(llm, b, c, sem) for b, c in jobs]):
            rows = await coro
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
            if n % 50 == 0:
                el = time.time() - t0
                log(f"{n}/{len(jobs)} çağrı, {n / el * 60:.1f}/dk")
    log("ipucu bitti", n)


# ------------------------------------------------------------------ eşleştirme
def _key(r: dict) -> str:
    from editor.production import sfx_library as L
    return ("ortam|" if r["kind"] == "ortam" else "anlik|") + " ".join(L.words(r["query"]))


def step_esle():
    from editor.production import sfx_library as L
    cues = [json.loads(x) for f in sorted(OUT.glob("ipuclari*.jsonl")) for x in f.read_text().splitlines() if x.strip()]
    cues = [c for c in cues if "query" in c]
    groups: dict[str, dict] = {}
    for c in cues:
        g = groups.setdefault(_key(c), {"key": _key(c), "kind": c["kind"], "query": c["query"], "query_en": c["query_en"],
                                        "category": c["category"], "count": 0, "quotes": collections.Counter(),
                                        "books": set()})
        g["count"] += 1
        g["quotes"][c["quote"]] += 1
        g["books"].add(c["book"])
    log("ipucu", len(cues), "benzersiz", len(groups))
    t0 = time.time()
    with (OUT / "esleme.jsonl").open("w") as f:
        for k, g in enumerate(groups.values()):
            res = L.search(g["query"], en=g["query_en"], kind=g["kind"], k=3)
            f.write(json.dumps({**{x: y for x, y in g.items() if x not in ("quotes", "books")},
                                "quotes": g["quotes"].most_common(5), "books": len(g["books"]),
                                "top": [{"id": r["id"], "title": r["title"], "score": r["score"], "cats": r["cats"],
                                         "source": r["source"], "why": r["why"]} for r in res]},
                               ensure_ascii=False) + "\n")
            if (k + 1) % 2000 == 0:
                log(k + 1, "/", len(groups), f"{(k + 1) / (time.time() - t0):.0f}/sn")
    log("eşleştirme bitti")


def _rows():
    return [json.loads(x) for x in (OUT / "esleme.jsonl").read_text().splitlines() if x.strip()]


def step_ayar():
    """Eşik ayarı: benzerlik puanı eşiği yükseldikçe «karşılandı» sayılan ilk adayların kaçı yargıda (step_yargi)
    «evet» (p ≥ 0,5) alıyor (doğruluk), kaçı eşiği geçiyor (kapsama). Önerilen eşik: doğruluğun %90'ı geçtiği en düşük
    eşik. Dinleyerek doğrulama için her puan bandından ipucu-aday çiftleri yazılır (dinleme-ornekleri.json; aday
    kimliğiyle önizleme stüdyoda dinlenir)."""
    rows = [r for r in _rows() if r["top"]]
    jd = _judged()
    lab = [r for r in rows if any(j["rank"] == 0 for j in jd.get(r["key"], []))]
    p0 = {r["key"]: next(j["p"] for j in jd[r["key"]] if j["rank"] == 0) for r in lab}
    table, pick = [], None
    for t in [x / 100 for x in range(0, 51, 2)]:
        cov = [r for r in rows if r["top"][0]["score"] >= t]
        ok = [r for r in lab if r["top"][0]["score"] >= t]
        hit = [r for r in ok if p0[r["key"]] >= 0.5]
        prec = len(hit) / max(1, len(ok))
        table.append({"esik": t, "kapsama": round(len(cov) / max(1, len(rows)), 4), "dogruluk": round(prec, 4),
                      "n": len(ok)})
        if pick is None and prec >= 0.9 and len(ok) >= 20:
            pick = t
    bands = collections.defaultdict(list)
    for r in lab:
        s = r["top"][0]["score"]
        bands[round(s * 20) / 20].append({"tarif": r["query"], "en": r["query_en"], "aday": r["top"][0]["title"],
                                          "aday_id": r["top"][0]["id"], "yargi_p": p0[r["key"]]})
    (OUT / "dinleme-ornekleri.json").write_text(json.dumps({str(k): v[:10] for k, v in sorted(bands.items())},
                                                           ensure_ascii=False, indent=1))
    (OUT / "esik.json").write_text(json.dumps({"onerilen": pick, "tablo": table}, ensure_ascii=False, indent=1))
    print(json.dumps({"onerilen_esik": pick, "tablo": table}, ensure_ascii=False))


JUDGE = """Bir çocuk kitabının sesli okumasına efekt konacak. İstenen ses: «{q}» ({en}).
Kütüphanedeki aday dosyanın bilgileri:
- başlık: {title}
- klasör/koleksiyon: {group}
- etiketler: {tags}
Bu dosya büyük olasılıkla istenen sesi içeriyor mu (aynı ses kaynağı ve olay)? Yalnız E (evet) ya da H (hayır)."""


async def step_yargi():
    """Eşik ayarı ve kapsama için bağımsız yargı: her benzersiz ipucunun ilk 3 adayı için Zeki AI «bu dosya istenen
    sesi içeriyor mu» sorusunu kapalı kümede (E/H, belirteç olasılığı) cevaplar. Yalnız dosyanın adı/klasörü/etiketi
    görülür (ses dinlenmez): üst verisi zayıf dosyada «hayır» çıkar, yani ölçüm kapsamayı olduğundan DÜŞÜK gösterir."""
    from editor.llm import PromptRef
    from editor.production import sfx_library as L
    from editor.production.run import FileLlm
    rows = _rows()
    outp = OUT / "yargi.jsonl"
    done = set()
    if outp.exists():
        done = {(json.loads(x)["key"], json.loads(x)["id"]) for x in outp.read_text().splitlines() if x.strip()}
    llm = FileLlm(OUT / "provenance.jsonl")
    sem = asyncio.Semaphore(CONCURRENCY * 2)

    async def one(r, c):
        full = L.get(c["id"]) or {}
        msg = JUDGE.format(q=r["query"], en=r["query_en"], title=full.get("title") or c["title"],
                           group=full.get("group") or c.get("source"), tags=", ".join((full.get("tags_en") or [])[:25]))
        async with sem:
            try:
                p, _ = await llm.choose("book-director", [{"role": "user", "content": msg}], ["E", "H"],
                                        prompt=PromptRef("sfx.judge", "1"))
                return {"key": r["key"], "id": c["id"], "rank": c["rank"], "score": c["score"], "p": round(p["E"], 4)}
            except Exception as e:  # noqa: BLE001
                return {"key": r["key"], "id": c["id"], "rank": c["rank"], "score": c["score"], "error": str(e)[:200]}

    jobs = [one(r, {**c, "rank": k}) for r in rows for k, c in enumerate(r["top"][:3]) if (r["key"], c["id"]) not in done]
    log("yargı", len(jobs))
    n = 0
    with outp.open("a") as f:
        for coro in asyncio.as_completed(jobs):
            res = await coro
            if "error" not in res:
                f.write(json.dumps(res) + "\n")
            n += 1
            if n % 500 == 0:
                f.flush()
                log(n, "/", len(jobs))
    log("yargı bitti")


async def step_secim():
    """Stüdyonun seçimiyle aynı yol (sfx.match + sfx.rerank): her benzersiz ipucu için aramanın ilk 8 adayı Zeki AI'ye
    gösterilir, tek harfle en uygunu ya da «hiçbiri» (X) seçilir. KARŞILANDI = P(uygun ses var) ≥ 0,5. Model yalnız
    ad/klasör/etiket görür: üst verisi zayıf ama sesi doğru dosyaya «hiçbiri» diyebilir (ölçüm kapsamayı düşük gösterir)."""
    from editor.production import sfx
    from editor.production.run import FileLlm
    rows = _rows()
    outp = OUT / "secim.jsonl"
    done = {}
    if outp.exists():
        for x in outp.read_text().splitlines():
            if x.strip():
                r = json.loads(x)
                done[r["key"]] = r
    stamp = (Path("/data/editor/sfx/_dizin/katalog.jsonl").stat().st_mtime)
    todo = [r for r in rows if r["key"] not in done or done[r["key"]].get("stamp") != stamp]
    llm = FileLlm(OUT / "provenance.jsonl")
    sem = asyncio.Semaphore(CONCURRENCY * 2)

    async def one(r):
        cue = {"kind": r["kind"], "query": r["query"], "query_en": r["query_en"],
               "quote": (r.get("quotes") or [[""]])[0][0]}
        async with sem:
            cands = await asyncio.to_thread(sfx.match, cue, None, sfx.POOL_K)
            ranked, fit = await sfx.rerank(llm, cue, cands)
        return {"key": r["key"], "stamp": stamp, "fit": fit, "best": ranked[0]["id"] if ranked else None,
                "best_title": ranked[0]["title"] if ranked else None, "best_source": ranked[0]["source"] if ranked else None,
                "n": len(cands)}

    log("seçim", len(todo), "önceden", len(rows) - len(todo))
    n = 0
    with outp.open("a") as f:
        for coro in asyncio.as_completed([one(r) for r in todo]):
            res = await coro
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            n += 1
            if n % 500 == 0:
                f.flush()
                log(n, "/", len(todo))
    log("seçim bitti")


def _selected() -> dict[str, dict]:
    p = OUT / "secim.jsonl"
    out: dict[str, dict] = {}
    if p.exists():
        for x in p.read_text().splitlines():
            if x.strip():
                r = json.loads(x)
                out[r["key"]] = r                 # sonraki satır öncekini ezer (havuz değişince yeniden seçilir)
    return out


def _judged() -> dict[str, list[dict]]:
    """İpucu → ŞU ANKİ ilk 3 adayın yargısı (sırasıyla). Havuz değişince eski adayların yargısı sayılmaz."""
    p = OUT / "yargi.jsonl"
    pk: dict[tuple[str, str], float] = {}
    if p.exists():
        for x in p.read_text().splitlines():
            if x.strip():
                r = json.loads(x)
                pk[(r["key"], r["id"])] = r["p"]
    out: dict[str, list[dict]] = {}
    for r in _rows():
        js = [{"rank": k, "id": c["id"], "p": pk[(r["key"], c["id"])]} for k, c in enumerate(r["top"][:3])
              if (r["key"], c["id"]) in pk]
        if js:
            out[r["key"]] = js
    return out


def step_rapor(esik: float | None):
    """Kapsama: bir ipucu KARŞILANDI = ilk 3 adaydan en az biri yargıda «evet» (p ≥ 0,5; editör adaylardan seçer).
    Ayrıca: varsayılan (1.) aday doğru mu, ve yalnız benzerlik eşiğiyle (esik.json'daki önerilen ya da --esik) kapsama."""
    rows = _rows()
    jd = _judged()
    if esik is None:
        e = OUT / "esik.json"
        esik = (json.loads(e.read_text()).get("onerilen") if e.exists() else None) or 0.2

    sel = _selected()

    def judged_ok(r, first_only=False):
        js = [j for j in jd.get(r["key"], []) if not first_only or j["rank"] == 0]
        return any(j["p"] >= 0.5 for j in js)

    def ok(r):
        s = sel.get(r["key"])
        return bool(s and s.get("fit") is not None and s["fit"] >= 0.5) if sel else judged_ok(r)
    total_occ = sum(r["count"] for r in rows)
    covered = [r for r in rows if ok(r)]
    miss = [r for r in rows if not ok(r)]
    first = [r for r in rows if judged_ok(r, True)]
    by_src = collections.Counter((sel.get(r["key"]) or {}).get("best_source") for r in covered)
    by_score = [r for r in rows if r["top"] and r["top"][0]["score"] >= esik]
    occ_cov = sum(r["count"] for r in covered)
    by_kind = collections.Counter(r["kind"] for r in rows)
    cats = collections.Counter(r.get("category") or "diger" for r in rows)
    rep = {"benzersiz": len(rows), "gecis": total_occ, "yargilanan": sum(1 for r in rows if jd.get(r["key"])),
           "karsilanan_benzersiz": len(covered), "karsilanan_yuzde": round(100 * len(covered) / max(1, len(rows)), 2),
           "karsilanan_gecis_yuzde": round(100 * occ_cov / max(1, total_occ), 2),
           "olcu": (f"Zeki AI seçimi (ilk {max((s.get('n') or 0) for s in sel.values())} aday, P(uygun) ≥ 0,5)"
                    if sel else "aday yargısı (ilk 3)"),
           "karsilayan_kaynak": dict(by_src.most_common()),
           "ilk_3_yargi_yuzde": round(100 * sum(1 for r in rows if judged_ok(r)) / max(1, len(rows)), 2),
           "ilk_aday_dogru_yuzde": round(100 * len(first) / max(1, len(rows)), 2),
           "esik": esik, "esikle_kapsama_yuzde": round(100 * len(by_score) / max(1, len(rows)), 2),
           "tur": dict(by_kind), "kategori": dict(cats.most_common()),
           "karsilanmayan_en_sik_50": [{"tarif": r["query"], "en": r["query_en"], "kez": r["count"], "kitap": r["books"],
                                        "tur": r["kind"], "ilk_aday": r["top"][0] if r["top"] else None}
                                       for r in sorted(miss, key=lambda r: -r["count"])[:50]]}
    (OUT / "karsilanmayan.json").write_text(json.dumps(
        [{"query": r["query"], "query_en": r["query_en"], "kind": r["kind"], "category": r.get("category"),
          "count": r["count"]} for r in miss], ensure_ascii=False, indent=1))
    (OUT / "rapor.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in rep.items() if k != "karsilanmayan_en_sik_50"}, ensure_ascii=False, indent=1))
    for m in rep["karsilanmayan_en_sik_50"][:50]:
        print(m["kez"], m["tur"], m["tarif"], "|", m["en"], "|", (m["ilk_aday"] or {}).get("title"),
              (m["ilk_aday"] or {}).get("score"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("adim")
    ap.add_argument("--ornek", type=int, default=None)
    ap.add_argument("--etiket", default="")          # ek okuma turu: ipuclari-<etiket>.jsonl (eşleştirme hepsini birleştirir)
    ap.add_argument("--esik", type=float, default=None)
    a = ap.parse_args()
    if a.adim == "metin":
        step_metin()
    elif a.adim == "ipucu":
        asyncio.run(step_ipucu(a.ornek, a.etiket))
    elif a.adim == "esle":
        step_esle()
    elif a.adim == "yargi":
        asyncio.run(step_yargi())
    elif a.adim == "secim":
        asyncio.run(step_secim())
    elif a.adim == "ayar":
        step_ayar()
    elif a.adim == "rapor":
        step_rapor(a.esik)
