#!/usr/bin/env python3
"""Zeki AI sohbet kapsamı (2026-09-28) — test sunucusunda kabul: gerçek köprü, gerçek model, gerçek Logo.

Mac'te koşulmaz. Sıra (docs/GELISTIRME-GUNLUGU.md 2026-09-28 «Zeki AI sohbet kapsamı» kabul listesi):

  1. cd <kaynak>/backend && python3 -m pytest semantic_layer/tests/test_chat_scope.py -q
  2. hızlı kapı: tests/text2sql/resolver-gate.py set100.jsonl  (çözücü değişmedi → fark 0)
  3. bu betik, köprü ortamıyla (LLM_EXTRA_BODY_JSON ve çağıran anahtarı yüklensin):
       sudo systemd-run --wait --pipe -p EnvironmentFile=/etc/nanobase/semantic-bridge.env \
         -p WorkingDirectory=<kaynak>/backend python3 <kaynak>/scripts/acceptance/chat_scope/run_acceptance.py \
         --out /tmp/claude-<oturum>/chat-scope-evidence.json
  4. cleanup.py --evidence <aynı dosya>   (kabulün sl_query_log satırları silinir; test verisi bırakılmaz)
  5. tam kapı: tests/text2sql/answer-gate.py --repeat 3 — bozulan 0 değilse iş bitmedi.

Denetimler:
  - kimlik/model soruları → MODULE_INTRO, metin birebir BI_INTRO, SQL/kayıt yok;
  - şirket dışı sohbet → MODULE_INTRO, metin BI_REDIRECT (model kararı; sapma ayrı sayılır);
  - analiz belgelerinden modül soruları → hiçbiri MODULE_INTRO değil; DATA_UNAVAILABLE ise metin
    «Bu konuda henüz veri bağlı değil» ile başlar; bağlı olmayan konuda SQL cevabı «incelenecek» listesine düşer;
  - ekrana giden bütün metinlerde teknoloji adı yok;
  - bağlı konuda doğrudan-SQL referansı (6 soru): köprünün tam sonucu == Logo'ya doğrudan sorgu. Referansın kendisi
    önce 2026-09-10 ölçümüyle (bellekte) karşılaştırılır; tutmazsa «referans doğrulanamadı» yazılır, geçti sayılmaz.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from semantic_bridge import chat_scope  # noqa: E402

_spec = importlib.util.spec_from_file_location("chat_scope_cases", ROOT / "backend/semantic_layer/tests/test_chat_scope.py")
cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cases)

TECH = re.compile(r"qwen|vllm|nvidia|\bgpt|llama|openai|anthropic|claude|gemini|mistral|temporal|timesfm", re.IGNORECASE)

# 2026 (canlı Logo .25; 2026-09-29 öncesi çapalar 2026-08-17'de donmuş eski kopyadandır). Çapa: 2026-09-10 canlı ölçümü (bellek live-bi-numbers-2026,
# invoice-count-sales-scope). Referans SQL önce çapayla tutmalı; tutmazsa kendisi yanlıştır.
_Y = "DATE_ >= '20260101' AND DATE_ < '20270101' AND CANCELLED = 0"
REFERENCES = [
    {"question": "2026 toptan satış tutarı",
     "sql": f"SELECT SUM(NETTOTAL) AS v FROM dbo.LG_411_01_INVOICE WHERE TRCODE = 8 AND {_Y}",
     "anchor": Decimal("874600000"), "anchor_tol": Decimal("100000")},
    {"question": "2026 perakende satış tutarı",
     "sql": f"SELECT SUM(NETTOTAL) AS v FROM dbo.LG_411_01_INVOICE WHERE TRCODE = 7 AND {_Y}",
     "anchor": Decimal("42100000"), "anchor_tol": Decimal("100000")},
    {"question": "2026 fatura sayısı",
     "sql": f"SELECT COUNT(*) AS v FROM dbo.LG_411_01_INVOICE WHERE TRCODE IN (2,3,7,8,9) AND {_Y}",
     "anchor": Decimal("73660"), "anchor_tol": Decimal("0")},
    {"question": "2026 toptan satış faturası sayısı",
     "sql": f"SELECT COUNT(*) AS v FROM dbo.LG_411_01_INVOICE WHERE TRCODE = 8 AND {_Y}",
     "anchor": Decimal("21009"), "anchor_tol": Decimal("0")},
    {"question": "2026 perakende satış faturası sayısı",
     "sql": f"SELECT COUNT(*) AS v FROM dbo.LG_411_01_INVOICE WHERE TRCODE = 7 AND {_Y}",
     "anchor": Decimal("49548"), "anchor_tol": Decimal("0")},
    {"question": "2026 net ciro",
     "sql": ("SELECT SUM(CASE WHEN TRCODE IN (2,3) THEN -NETTOTAL ELSE NETTOTAL END) AS v "
             f"FROM dbo.LG_411_01_INVOICE WHERE TRCODE IN (2,3,7,8,9) AND {_Y}"),
     "anchor": Decimal("848110178.82"), "anchor_tol": Decimal("0.01")},
]


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--bridge", default=os.environ.get("BRIDGE", "http://127.0.0.1:8795"))
    ap.add_argument("--live", default="/data/nanobaseai/bi/frontend/backend/semantic_bridge",
                    help="köprünün çalıştığı ağaç; dosya özetleri kanıta yazılır")
    ap.add_argument("--skip-references", action="store_true")
    args = ap.parse_args()
    token = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
    headers = {"Content-Type": "application/json", "X-Semantic-Caller": token}

    def call(path: str, body=None):
        req = urllib.request.Request(args.bridge + path, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)

    def ask(q: str) -> dict:
        t = time.monotonic()
        try:
            a = call("/api/v1/ask", {"question": q, "execute": True, "sampleSize": 50})
        except urllib.error.HTTPError as e:
            a = {"type": f"HTTP_{e.code}", "explanation": e.read().decode("utf-8", "replace")[:500]}
        a["_ms"] = int((time.monotonic() - t) * 1000)
        return a

    results: list[dict] = []
    query_ids: list[str] = []
    counters = {"passed": 0, "failed": 0, "unverified": 0}

    def record(row: dict) -> None:
        results.append(row)
        if row.get("queryId"):
            query_ids.append(row["queryId"])
        counters["passed" if row["status"] == "PASS" else "failed" if row["status"] == "FAIL" else "unverified"] += 1
        print(json.dumps({k: row.get(k) for k in ("kind", "question", "status", "type", "topic", "note")}, ensure_ascii=False), flush=True)
        if len(results) % 10 == 0:
            print(json.dumps({"progress": len(results), **counters}, ensure_ascii=False), flush=True)

    def screen_text(a: dict) -> str:
        return " ".join(str(a.get(k) or "") for k in ("explanation", "summary"))

    connected = chat_scope.connected_topic_ids()

    for q in cases.IDENTITY_QUESTIONS:
        a = ask(q)
        ok = (a.get("type") == "MODULE_INTRO" and a.get("explanation") == chat_scope.BI_INTRO
              and not any(a.get(k) for k in ("sql", "records", "semantic")))
        record({"kind": "identity", "question": q, "type": a.get("type"), "status": "PASS" if ok else "FAIL",
                "explanation": a.get("explanation"), "queryId": a.get("queryId"), "ms": a["_ms"]})

    for q in cases.OFFTOPIC_QUESTIONS:
        a = ask(q)
        intro = a.get("type") == "MODULE_INTRO" and not a.get("sql")
        exact = a.get("explanation") == chat_scope.BI_REDIRECT
        record({"kind": "offtopic", "question": q, "type": a.get("type"),
                "status": "PASS" if intro and exact else "FAIL",
                "note": None if exact else "model şirket dışı demedi" if not intro else "metin BI_REDIRECT değil",
                "explanation": a.get("explanation"), "queryId": a.get("queryId"), "ms": a["_ms"]})

    for module, q, expected in cases.MODULE_QUESTIONS:
        a = ask(q)
        scope = a.get("chatScope") or (a.get("semantic") or {}).get("chatScope") or {}
        typ = a.get("type")
        note = None
        status = "PASS"
        if typ == "MODULE_INTRO":
            status, note = "FAIL", "modül sorusu reddedildi"
        elif typ == "DATA_UNAVAILABLE" and scope and not (
                str(a.get("explanation", "")).startswith("Bu konuda henüz veri bağlı değil")
                or a.get("explanation") == (chat_scope.topic(scope.get("topic")) or {}).get("closed")):  # İK: bilerek kapalı
            status, note = "FAIL", "veri bağlı değil metni beklenen biçimde değil"
        elif expected not in connected and typ == "TEXT_TO_SQL":
            status, note = "UNVERIFIED", "bağlı olmayan konuda SQL cevabı — elle incelenecek"
        elif typ and typ.startswith("HTTP_"):
            status, note = "FAIL", "köprü hatası"
        record({"kind": "module", "module": module, "question": q, "expectedTopic": expected,
                "topic": scope.get("topic"), "type": typ, "status": status, "note": note,
                "explanation": a.get("explanation"), "sql": a.get("sql"), "queryId": a.get("queryId"), "ms": a["_ms"]})

    # Teknoloji adı: bütün cevap metinleri
    leaks = [r["question"] for r in results if TECH.search(str(r.get("explanation") or ""))]

    refs: list[dict] = []
    if not args.skip_references:
        from semantic_layer.config import SemanticSettings
        from semantic_layer.profiler.connectors import connector_from_file
        conn = connector_from_file(SemanticSettings.from_env().connection_file)
        try:
            for ref in REFERENCES:
                expected = Decimal(str(list(conn.execute(ref["sql"], 1)[1][0].values())[0] or 0))
                anchor_ok = abs(expected - ref["anchor"]) <= ref["anchor_tol"]
                a = ask(ref["question"])
                full = None
                if a.get("resultId"):
                    try:
                        full = call(f"/api/v1/result/{a['resultId']}")
                    except urllib.error.HTTPError as e:
                        full = {"error": e.code}
                rows = (full or {}).get("records") or []
                values = []
                if len(rows) == 1:
                    for v in rows[0].values():
                        try:
                            values.append(Decimal(str(v)))
                        except Exception:  # noqa: BLE001
                            pass
                equal = any(abs(v - expected) < Decimal("0.01") for v in values)
                complete = full is not None and not full.get("truncated") and full.get("totalRows", len(rows)) == 1
                status = "UNVERIFIED" if not anchor_ok else "PASS" if (equal and complete) else "FAIL"
                row = {"kind": "reference", "question": ref["question"], "type": a.get("type"), "status": status,
                       "note": None if anchor_ok else "referans 2026-09-10 ölçümüyle tutmadı — referans doğrulanamadı",
                       "referenceSQL": ref["sql"], "expected": str(expected), "anchor": str(ref["anchor"]),
                       "actualColumns": (full or {}).get("columns"), "actualRows": rows, "sql": a.get("sql"),
                       "queryId": a.get("queryId"), "ms": a["_ms"]}
                record(row)
                refs.append(row)
        finally:
            conn.close()

    live = Path(args.live)
    summary = {
        **counters, "total": len(results), "techNameLeaks": leaks,
        "moduleRejected": sum(1 for r in results if r["kind"] == "module" and r["type"] == "MODULE_INTRO"),
        "moduleNotConnected": sum(1 for r in results if r["kind"] == "module" and r["type"] == "DATA_UNAVAILABLE"),
        "topicAgreement": sum(1 for r in results if r["kind"] == "module" and r.get("topic") == r["expectedTopic"]),
        "connectedTopics": sorted(connected),
    }
    evidence = {
        "summary": summary, "results": results, "queryIds": query_ids,
        "files": {name: {"source": _sha(ROOT / "backend/semantic_bridge" / name), "live": _sha(live / name)}
                  for name in ("chat_scope.py", "chat_topics.json", "app.py", "admin.py")},
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if counters["failed"] == 0 and not leaks else 1


if __name__ == "__main__":
    raise SystemExit(main())
