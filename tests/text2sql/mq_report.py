"""Kapı betiklerinin ortak `--report` parçası (M50 Zeki AI kalitesi).

`--report <köprü adresi>` verilince betik bitince özet + vaka listesini `POST /api/v1/model-quality/report`'a yazar
(SEMANTIC_CALLER_TOKEN ortamdan). Seçenek verilmezse betiğin davranışı aynen kalır. Rapor yazılamazsa betik yalnız
uyarı basar; çıkış kodu kapının kendi hükmüdür (rapor hatası kapıyı kırmaz).

Özetler köprüdeki `model_quality.digest_of` ile aynı hesaptır (sha256, sıralı anahtarlı JSON, ilk 32 karakter).
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request


def arg(name: str, default: str = "") -> str:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:32]


def rows_digest(rows) -> str | None:
    """Sonuç satırlarının sıradan bağımsız özeti (aynı sonuç farklı sırayla gelse de aynı)."""
    if rows is None:
        return None
    return digest(sorted(json.dumps(r, ensure_ascii=False, sort_keys=True, default=str) for r in rows))


def wanted() -> bool:
    return "--report" in sys.argv


def post(payload: dict) -> dict | None:
    """Raporu gönderir; köprünün döndürdüğü koşu görünümü ya da None."""
    base = arg("--report").rstrip("/")
    if not base:
        print("rapor: --report köprü adresi boş; gönderilmedi", file=sys.stderr)
        return None
    payload.setdefault("host", f"{socket.gethostname()}:{os.environ.get('USER', '?')}")
    if arg("--request"):
        payload["requestId"] = arg("--request")
    if arg("--code-sha"):
        payload["codeSha"] = arg("--code-sha")
    req = urllib.request.Request(base + "/api/v1/model-quality/report", method="POST",
                                 data=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                                 headers={"X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", ""),
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            out = json.load(r)
        print(f"rapor yazıldı: koşu {out.get('id')} · {out.get('total')} soru · bozulan {out.get('broken')} · "
              f"düzelen {out.get('fixed')}" + (" · UYARI: ölçüm sırasında kurulum/değişiklik var" if out.get("polluted") else ""))
        return out
    except urllib.error.HTTPError as e:
        print(f"UYARI: rapor yazılamadı ({e.code}): {e.read()[:400]!r}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"UYARI: rapor yazılamadı: {e}", file=sys.stderr)
    return None
