#!/usr/bin/env python3
"""Zeki AI sesli not kabulü — test sunucusunda, gerçek köprü (:8795 ya da yan port) ve gerçek GPU servisiyle.

Giriş: `timasai` hesabının kısa ömürlü oturum çerezi (AGENTS.md «Test kullanıcısı bırakılmaz»; bitince oturum satırı
silinir). Ses dosyaları: sahada telefonla okunmuş alan cümleleri (`deploy/tt-gpu/voice-note/olcum/alan-cumleleri.tsv`,
dosya adı = kimlik, biçim serbest). Betik hiçbir kayıt yazmaz (uç kayıt yazmaz; not kaydı M30/M31'in işi).

  TIMAS_COOKIE='timas_session=…' python3 kabul.py --base http://127.0.0.1:8795 --dir /tmp/claude-<oturum>/alan

Denetimler:
  K1  meta: açık, süre/boyut sınırı ayardaki değer
  K2  her kayıt: 200, metin boş değil; ham ve düzeltilmiş metnin WER/CER'i referansla (toplam ve kayıt başına)
  K3  düzeltme sayı değiştirmedi: referanstaki sayı değerleri düzeltilmiş metinde de var (ham metinde varsa)
  K4  süre sınırı: (sınır + 5) sn sessiz WAV → 413, servis çağrılmadan
  K5  bozuk gövde → 400
  K6  sessiz 5 sn WAV → 200 ve boş metin (uydurma cümle yok)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend"))
from semantic_bridge.voice_note import numbers  # noqa: E402


def wav(seconds: float) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(b"\0\0" * int(seconds * 16000))
    return b.getvalue()


def to_wav(path: str) -> bytes:
    if path.endswith(".wav"):
        return open(path, "rb").read()
    return subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "wav", "-"],
                          capture_output=True, check=True).stdout


def norm(s: str) -> list[str]:
    s = s.replace("İ", "i").replace("I", "ı").lower()
    s = re.sub(r"['’]", "", s)
    return re.sub(r"[^\w\s]", " ", s).split()


def lev(a, b) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, y in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y))
        prev = cur
    return prev[-1]


def req(base: str, path: str, data: bytes | None = None, method: str = "GET"):
    r = urllib.request.Request(base + path, data=data, method=method,
                               headers={"Cookie": os.environ.get("TIMAS_COOKIE", ""), "Content-Type": "audio/wav"})
    try:
        with urllib.request.urlopen(r, timeout=600) as f:
            return f.status, json.loads(f.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8795")
    ap.add_argument("--dir", required=True)
    a = ap.parse_args()
    fails = 0

    st, meta = req(a.base, "/api/v1/voice-note/meta")
    ok = st == 200 and meta.get("acik")
    print(f"K1 meta {st} {meta}  {'TAMAM' if ok else 'KALDI'}")
    fails += not ok

    refs = {}
    for i, line in enumerate(open(os.path.join(a.dir, "alan-cumleleri.tsv"), encoding="utf-8")):
        k, _, t = line.rstrip("\n").partition("\t")
        if i and t:
            refs[k] = t
    tot = {"raw": [0, 0], "fix": [0, 0], "rawc": [0, 0], "fixc": [0, 0]}
    for f in sorted(os.listdir(a.dir)):
        k = f.rsplit(".", 1)[0]
        if k not in refs:
            continue
        t0 = time.time()
        st, out = req(a.base, "/api/v1/voice-note?baglam=saha&duzelt=1", to_wav(os.path.join(a.dir, f)), "POST")
        if st != 200 or not out.get("metin"):
            print(f"K2 {k}: {st} {out}  KALDI")
            fails += 1
            continue
        r = norm(refs[k])
        for key, txt in (("raw", out["ham"]), ("fix", out["metin"])):
            h = norm(txt)
            tot[key][0] += lev(r, h); tot[key][1] += len(r)
            rc, hc = list("".join(r)), list("".join(h))
            tot[key + "c"][0] += lev(rc, hc); tot[key + "c"][1] += len(rc)
        num_ok = not (numbers(refs[k]) == numbers(out["ham"]) and numbers(out["ham"]) != numbers(out["metin"]))
        fails += not num_ok
        print(f"K2 {k}: {time.time() - t0:.1f} sn, düzeltme {out['duzeltme']['durum']}\n   ref: {refs[k]}\n   ham: {out['ham']}\n   son: {out['metin']}"
              + ("" if num_ok else "\n   K3 KALDI: düzeltme sayıyı değiştirdi"))
    for key in ("raw", "fix"):
        e, n = tot[key]; ec, nc = tot[key + "c"]
        print(f"K2 toplam {'ham' if key == 'raw' else 'düzeltilmiş'}: WER %{100 * e / max(1, n):.2f}  CER %{100 * ec / max(1, nc):.2f}")

    st, out = req(a.base, "/api/v1/voice-note", wav(meta.get("maxSaniye", 300) + 5), "POST")
    print(f"K4 süre sınırı {st}  {'TAMAM' if st == 413 else 'KALDI'}"); fails += st != 413
    st, out = req(a.base, "/api/v1/voice-note", b"bozuk" * 400, "POST")
    print(f"K5 bozuk gövde {st}  {'TAMAM' if st == 400 else 'KALDI'}"); fails += st != 400
    st, out = req(a.base, "/api/v1/voice-note", wav(5), "POST")
    ok = st == 200 and not out.get("metin")
    print(f"K6 sessiz kayıt {st} {out.get('metin')!r}  {'TAMAM' if ok else 'KALDI'}"); fails += not ok
    print("SONUÇ:", "TAMAM" if not fails else f"{fails} KALDI")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
