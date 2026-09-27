#!/usr/bin/env python3
"""Efekt havuzunun kapsama ölçümü: yayınevinin çocuk kitaplarındaki bütün efekt ipuçları havuzda karşılanıyor mu?

GPU'da GEÇİCİ kapta (editor-py imajı, editor-net ağı, editor.env) çalışır; derlem YALNIZ OKUNUR. Model çağrıları
gateway üzerinden (Zeki AI, `book-director`), stüdyonun kullandığı istemle (production/sfx.py PROMPT) — kitaba özel
istem yok. Çıktılar /data/editor/sfx/_olcum/ altında.

    kapsama.py metin                 derlemden çocuk kitaplarının sayfa metni → sayfalar.jsonl
    kapsama.py ipucu [--ornek N]     sayfalar → ipuclari.jsonl (N verilirse kitaplardan eşit aralıklı N kitap)
    kapsama.py esle                  benzersiz ipuçları → havuzda en iyi 3 aday → esleme.jsonl
    kapsama.py ayar                  eşik ayarı: kategorisi belli ipuçlarında ilk adayın kategorisi tutuyor mu
    kapsama.py rapor [--esik X]      karşılanan %, karşılanmayanların en sık 50'si → rapor.json

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
    """Eşik ayarı (vekil ölçü): kategorisi belli ipuçlarında ilk adayın kategorileri ipucunun kategorisini içeriyor
    mu. Eşik yükseldikçe «karşılandı» sayılanların doğruluğu artar, kapsama düşer; tablo her iki eğriyi verir.
    Dinleyerek ayar için her eşik bandından örnek ipucu-aday çiftleri ayrıca yazılır (dinleme-ornekleri.json)."""
    rows = [r for r in _rows() if r["top"]]
    lab = [r for r in rows if r.get("category")]
    table = []
    for t in [x / 100 for x in range(0, 41, 2)]:
        cov = [r for r in rows if r["top"][0]["score"] >= t]
        ok = [r for r in lab if r["top"][0]["score"] >= t]
        hit = [r for r in ok if r["category"] in (r["top"][0]["cats"] or [])]
        table.append({"esik": t, "kapsama": round(len(cov) / max(1, len(rows)), 4),
                      "kategori_tutma": round(len(hit) / max(1, len(ok)), 4), "n": len(ok)})
    bands = collections.defaultdict(list)
    for r in lab:
        s = r["top"][0]["score"]
        bands[round(s * 20) / 20].append({"query": r["query"], "query_en": r["query_en"], "top": r["top"][0]})
    (OUT / "dinleme-ornekleri.json").write_text(json.dumps({str(k): v[:8] for k, v in sorted(bands.items())},
                                                           ensure_ascii=False, indent=1))
    print(json.dumps(table, ensure_ascii=False, indent=1))


def step_rapor(esik: float):
    rows = _rows()
    total_occ = sum(r["count"] for r in rows)
    covered = [r for r in rows if r["top"] and r["top"][0]["score"] >= esik]
    miss = [r for r in rows if not (r["top"] and r["top"][0]["score"] >= esik)]
    occ_cov = sum(r["count"] for r in covered)
    by_kind = collections.Counter(r["kind"] for r in rows)
    cats = collections.Counter(r.get("category") or "diger" for r in rows)
    rep = {"esik": esik, "benzersiz": len(rows), "gecis": total_occ,
           "karsilanan_benzersiz": len(covered), "karsilanan_yuzde": round(100 * len(covered) / max(1, len(rows)), 2),
           "karsilanan_gecis_yuzde": round(100 * occ_cov / max(1, total_occ), 2), "tur": dict(by_kind),
           "kategori": dict(cats.most_common()),
           "karsilanmayan_en_sik_50": [{"tarif": r["query"], "en": r["query_en"], "kez": r["count"], "kitap": r["books"],
                                        "tur": r["kind"], "ilk_aday": r["top"][0] if r["top"] else None}
                                       for r in sorted(miss, key=lambda r: -r["count"])[:50]]}
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
    ap.add_argument("--esik", type=float, default=0.2)
    a = ap.parse_args()
    if a.adim == "metin":
        step_metin()
    elif a.adim == "ipucu":
        asyncio.run(step_ipucu(a.ornek, a.etiket))
    elif a.adim == "esle":
        step_esle()
    elif a.adim == "ayar":
        step_ayar()
    elif a.adim == "rapor":
        step_rapor(a.esik)
