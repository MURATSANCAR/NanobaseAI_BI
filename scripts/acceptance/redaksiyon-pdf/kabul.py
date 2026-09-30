#!/usr/bin/env python3
"""Redaksiyon PDF okuması — gerçek kitap dosyalarıyla kabul (2026-09-30).

Klasördeki her PDF, yükleme ucunun kullandığı giriş noktasından (`editorial_desk.structure_of`) okunur; ortaya çıkan
metinde okuma kusuru sınıfları sayılır. Sayılar kitaba özel değildir, metnin kendisinden çıkar:

  unreadable      özel alan (PUA) ve «�» karakteri — fontun harf eşlemesi onarılamamış
  foreign         Latin/Yunan/Kiril dışı yazı karakteri (yanlış tablodan anlamsız harf; aday)
  glyph_names     metne sızmış glif adı («/quoteleft.alt2»)
  split_hyphen    iki küçük harfli parçanın arasında boşluklu tire («birlik - te»); gerçek konuşma çizgisi de sayılır,
                  bu yüzden aday sayısıdır — önceki koşuya göre artış kusurdur
  line_hyphen     satır sonunda kalmış tire + küçük harfle süren satır (birleşmemiş heceleme)
  lone_cap        tek büyük harften oluşan satır, ardından küçük harfle başlayan satır (kopuk büyük ilk harf)
  dotless_i       büyük harfli kelimede «I»: İ ile okununca kitabın kendi küçük harfli sözlüğünde var, ı ile yok
                  («FILIN» → «filin» var, «fılın» yok) — noktalı İ «I» diye eşlenmiş
  spaced_letters  harf harf ayrılmış kelime («B A Ş L I K»)
  glued           30+ harfli «kelime» (boşlukları kaybolmuş satır; Türkçede 25 harfli gerçek kelime var)
  empty_pages     metin satırı çıkmayan sayfa (resimli sayfa da olabilir; bilgi)

Kullanım (test sunucusunda, köprünün sanal ortamıyla):
  python kabul.py --dir /data/nanobaseai/bi/kabul/redaksiyon-pdf --backend <ağaç>/backend \
      --out /data/nanobaseai/bi/kabul/redaksiyon-pdf-sonuc/<sha>.json [--baseline <önceki>.json] [--jobs 6]
Çıkış kodu: önceki koşuya göre herhangi bir kitapta kusur sayısı arttıysa 1.
Kitap dosyaları müşteri içeriğidir: depoya girmez, yalnız sunucudaki klasörde durur.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

DEFECTS = ("unreadable", "foreign", "glyph_names", "split_hyphen", "line_hyphen", "lone_cap", "dotless_i",
           "spaced_letters", "glued")
LOW = "a-zçğıöşüâîû"
UP = "A-ZÇĞİÖŞÜÂÎÛ"
PATTERNS = {
    "unreadable": re.compile(r"[\ue000-\uf8ff\ufffd]"),
    # Latin/Yunan/Kiril dışı yazı (harf tablosu yanlış fonttan anlamsız harf); kitapta gerçekten geçebilir, adaydır
    "foreign": re.compile(r"[\u0590-\u1fff\u2c00-\u2dff\u3000-\ud7ff\uf900-\ufaff]"),
    # adres ve yol parçası («https://…/x.html», «…dir/kemalidir.34») glif adı değildir
    "glyph_names": re.compile(r"(?<![\w/:.])/[A-Za-z]+\.[A-Za-z]+[0-9]*"),
    "split_hyphen": re.compile(rf"[{LOW}]{{2,}} [-\u00ad\u2010] [{LOW}]{{2,}}"),
    "line_hyphen": re.compile(rf"[{LOW}][-\u00ad\u2010]\n[{LOW}]"),
    # dizindeki harf ara başlığı («D» + «damga resmi») aynı harfle sürer; kopuk büyük ilk harf sürmez
    "lone_cap": re.compile(rf"(?m)^[“\"‘'«]?([{UP}])\n(?!(?i:\1))[{LOW}]"),
    "spaced_letters": re.compile(rf"(?<!\S)(?:[{UP}{LOW}] ){{4,}}[{UP}{LOW}](?!\S)"),
    "glued": re.compile(rf"[{UP}{LOW}]{{30,}}"),
}


def tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def dotless_i(text: str) -> list[str]:
    vocab = Counter(w for w in re.findall(rf"[{LOW}]+", text))
    out = []
    for w in re.findall(rf"\b[{UP}]*I[{UP}]*\b", text):
        if len(w) < 3:
            continue
        dotted, dotless = tr_lower(w.replace("I", "İ")), tr_lower(w)
        if vocab[dotted] and not vocab[dotless]:
            out.append(w)
    return out


def measure(args: tuple[str, str]) -> dict:
    path, backend = args
    sys.path.insert(0, backend)
    from pypdf import PdfReader

    from semantic_bridge import editorial_desk as desk
    from semantic_bridge import editorial_desk_structure as st

    t0 = time.time()
    data = Path(path).read_bytes()
    try:
        s = desk.structure_of(Path(path).name, data)
    except Exception as e:  # noqa: BLE001 — okunamayan dosya da sonuçtur
        return {"file": Path(path).name, "error": f"{type(e).__name__}: {e}"}
    text = "\n".join(f"{t}\n{b}" for t, b in s.chapters)
    reader = PdfReader(path)
    pages_with_text = {ln.page for ln in st.pdf_lines(reader)}
    counts, samples = {}, {}
    for k, rx in PATTERNS.items():
        hits = [m.group(0) for m in rx.finditer(text)]
        counts[k] = len(hits)
        samples[k] = [text[max(0, m.start() - 40):m.end() + 40] for m in list(rx.finditer(text))[:6]]
    di = dotless_i(text)
    counts["dotless_i"] = len(di)
    samples["dotless_i"] = sorted(set(di))[:12]
    words = [len(b.split()) for _, b in s.chapters]
    return {"file": Path(path).name, "pages": len(reader.pages), "seconds": round(time.time() - t0, 1),
            "structure": s.source, "chapters": len(s.chapters), "words": sum(words),
            "chapter_words_min": min(words) if words else 0, "chapter_words_max": max(words) if words else 0,
            "titles": [t for t, _ in s.chapters][:60], "empty_pages": len(reader.pages) - len(pages_with_text),
            "defects": counts, "samples": samples}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--backend", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--baseline")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    files = sorted(str(p) for p in Path(a.dir).glob("*.pdf") if not p.name.startswith("._"))
    with ProcessPoolExecutor(a.jobs) as ex:
        rows = list(ex.map(measure, [(f, a.backend) for f in files]))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"backend": a.backend, "at": time.strftime("%Y-%m-%d %H:%M"), "books": rows},
                                      ensure_ascii=False, indent=1))
    base = {}
    if a.baseline and os.path.exists(a.baseline):
        base = {r["file"]: r for r in json.loads(Path(a.baseline).read_text())["books"]}
    worse = 0
    head = f"{'kitap':42} {'sf':>4} {'yapı':10} {'böl':>4} " + " ".join(f"{k[:7]:>7}" for k in DEFECTS) + "  boş"
    print(head)
    total = Counter()
    for r in rows:
        if "error" in r:
            print(f"{r['file'][:42]:42} HATA {r['error']}")
            worse += 1
            continue
        d = r["defects"]
        total.update(d)
        marks = []
        for k in DEFECTS:
            prev = base.get(r["file"], {}).get("defects", {}).get(k)
            cell = str(d[k]) if prev is None or prev == d[k] else f"{prev}→{d[k]}"
            if prev is not None and d[k] > prev:
                worse += 1
                cell += "!"
            marks.append(f"{cell:>7}")
        print(f"{r['file'][:42]:42} {r['pages']:>4} {r['structure'][:10]:10} {r['chapters']:>4} " + " ".join(marks)
              + f"  {r['empty_pages']:>3}")
    print("TOPLAM", dict(total))
    print(f"sonuç: {a.out}" + (f" · önceki koşuya göre artan kusur: {worse}" if base else ""))
    return 1 if worse else 0


if __name__ == "__main__":
    raise SystemExit(main())
