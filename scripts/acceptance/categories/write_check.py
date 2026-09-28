"""H1 Kategori ağacı: yazma uçlarının kabulü — test sunucusunda, `timasai` kısa ömürlü oturumuyla. Mac'te koşulmaz.

Kural (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»): yazma uçları önce boş / geçersiz gövdeyle denenir
(4xx beklenir). Gerçek yazma yalnız `--propose <CRM kitap GUID>` verilirse yapılır: o kitabın profil satırı önce
kanıt dosyasına yedeklenir, öneri üretilir (Zeki AI gerçek model kapısından), sonuç raporlanır; `cleanup.py
--evidence <dosya>` profili yedeğe döndürür, bu testte yazılan olay ve değişiklik kaydı satırlarını siler.

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && python3 ../scripts/acceptance/categories/write_check.py --cookie 'timas_session=…' \
         [--propose <kitap GUID>] --evidence /tmp/claude-<oturum>/h1-write.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import categories as C  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

BRIDGE = os.environ.get("CATEGORY_ACCEPT_BRIDGE", "http://127.0.0.1:8795")


def call(method: str, path: str, cookie: str, body=None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BRIDGE + path, data=data, method=method,
                                 headers={"cookie": cookie, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:  # noqa: S310 — yerel köprü
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cookie", required=True)
    ap.add_argument("--propose", default="")
    ap.add_argument("--evidence", required=True)
    args = ap.parse_args()
    s = SemanticSettings.from_env()
    engine = open_store(s.store_dsn, create=False).engine
    started = datetime.now(timezone.utc)
    report: dict = {"startedAt": started.isoformat(), "checks": [], "failures": []}

    def expect(name: str, method: str, path: str, body, codes: tuple[int, ...]) -> None:
        code, out = call(method, path, args.cookie, body)
        ok = code in codes
        report["checks"].append({"name": name, "status": code, "beklenen": codes, "ok": ok,
                                 "mesaj": (out.get("detail") or {}).get("message") if isinstance(out.get("detail"), dict) else out.get("detail")})
        if not ok:
            report["failures"].append(name)

    # Geçersiz gövdeler: hiçbir şey yazılmamalı. 403 de kabul (rolde yetki yoksa kapı önce durdurur).
    expect("agac-gecersiz", "PUT", "/api/v1/categories/tree", {"nodes": "x"}, (400, 403, 409))
    expect("agac-bos-ad", "PUT", "/api/v1/categories/tree", {"nodes": [{"id": "k1", "level": "ana", "name": " "}]}, (400, 403, 409))
    expect("karar-bilinmeyen-alan", "POST", "/api/v1/categories/books/00000000-0000-0000-0000-000000000000/decision",
           {"fields": {"yok": {"action": "kabul"}}}, (400, 403, 404))
    expect("bulgu-bos-secim", "POST", "/api/v1/categories/findings/apply", {"ids": []}, (400, 403))
    expect("eslemede-bilinmeyen-sistem", "PUT", "/api/v1/categories/mappings", {"nodeId": "x", "system": "yok", "items": []}, (400, 403, 409))
    expect("kural-bilinmeyen", "PUT", "/api/v1/categories/rules/yok", {"enabled": False}, (403, 404))
    expect("etiket-bilinmeyen", "POST", "/api/v1/categories/tags/decision", {"tag": "__yok__", "status": "aktif"}, (403, 404))
    expect("onay-taslak-yok-ya-da-yetki", "POST", "/api/v1/categories/tree/approve", {"version": -1}, (403, 404, 409))
    expect("run-due-oturumla", "POST", "/api/v1/categories/run-due", None, (403,))
    # Okuma uçları 200
    for path in ("/api/v1/categories/meta", "/api/v1/categories/overview", "/api/v1/categories/tree",
                 "/api/v1/categories/books?page=0", "/api/v1/categories/findings", "/api/v1/categories/crm-diff",
                 "/api/v1/categories/rules", "/api/v1/categories/tags", "/api/v1/categories/nodes", "/api/v1/categories/options"):
        expect(f"oku {path}", "GET", path, None, (200,))

    backup = None
    if args.propose:
        bid = args.propose.strip().upper()
        with engine.connect() as c:
            row = c.execute(sa.select(C.PROFILES).where(C.PROFILES.c.tenant_id == s.tenant_id, C.PROFILES.c.book_id == bid)).mappings().first()
        if not row:
            report["failures"].append("oneri: kitap profili yok")
        else:
            backup = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(row).items()}
            code, out = call("POST", f"/api/v1/categories/books/{bid}/propose", args.cookie, {})
            ok = code == 200
            report["propose"] = {"status": code, "fields": {k: {x: v.get(x) for x in ("proposed", "proposedPath", "method", "probability", "confident", "source")}
                                                            for k, v in (out.get("fields") or {}).items()} if ok else out,
                                 "modelCalls": out.get("modelCalls") if ok else None}
            if not ok:
                report["failures"].append("oneri")
            else:
                live = C.tree_ctx(engine, C.in_force(engine, s.tenant_id))
                k = (out.get("fields") or {}).get("kategori") or {}
                if k.get("proposed") and not live.active(k["proposed"]):
                    report["failures"].append("oneri: kategori ağaçta değil")
    Path(args.evidence).write_text(json.dumps({"startedAt": started.isoformat(), "tenant": s.tenant_id, "backup": backup,
                                               "report": report}, ensure_ascii=False, indent=2, default=str))
    report["ok"] = not report["failures"]
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"\nTemizlik: python3 ../scripts/acceptance/categories/cleanup.py --evidence {args.evidence}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
