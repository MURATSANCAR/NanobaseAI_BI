"""Yönlendirme ölçümü: yonlendirme-seti.jsonl (1.100 soru) beklenen_yol ↔ API'nin gerçekten gittiği kaynak yolu.

Varsayılan kuru çalışmadır (--dry-run): yalnız seti okur, alanları denetler, dağılımı basar; ağ ve veritabanı yok.
--live yalnız test sunucusunda, geri döngü API'ye (http://127.0.0.1:8795) soru başına bir istek gönderir; timasai
için kısa ömürlü oturum açar ve finally'de siler. Uzun koşudur, başka oturumların köprüsünü yorar: koordinatör çalıştırır.

Gerçek yol API cevabından çıkarılır (ürün kodu import edilmez):
  - type MODULE_INTRO                         → finans_disi (kimlik/selam/finans dışı reddi)
  - semantic.portal var                        → portal (chat_portal modül verisi)
  - semantic.engine == finance_contract_v1     → semantic.executions[].source kümesi: {logo}→logo, {crm}→crm, ikisi→karma.
    Veri okunmadıysa (netleştirme/hata) plan'dan: crm/crm_report/relational_query → crm; ölçü/logo_report → logo;
    CRM kırılımı (author/publisher/subbrand/author_group) ya da cross_book_sales_quality → karma; sections birleşimi.
  - aksi: bilinmiyor
Netleştirme: belirsizlik.netlestirme_gerekir=true sorularda doğru davranış CLARIFICATION'dır; ayrı sayılır.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import time
import urllib.error
import urllib.request

ROUTES = ("logo", "crm", "karma", "portal", "finans_disi")
CRM_DIMENSIONS = {"author", "publisher", "subbrand", "author_group"}
DEFAULT_SET = Path(__file__).resolve().parents[3] / "docs/kaynak-sozlugu/yonlendirme-seti.jsonl"


def load(path):
    rows = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        for field in ("id", "soru", "beklenen_yol"):
            if not row.get(field):
                raise ValueError(f"satır {n}: {field} eksik")
        if row["beklenen_yol"] not in ROUTES:
            raise ValueError(f"satır {n}: tanımsız beklenen_yol {row['beklenen_yol']!r}")
        rows.append(row)
    ids = Counter(r["id"] for r in rows)
    dup = [k for k, v in ids.items() if v > 1]
    if dup:
        raise ValueError("yinelenen kimlik: " + ", ".join(dup[:10]))
    return rows


def plan_sources(plan):
    """Veri okunmamış cevapta plan alanlarından beklenen kaynak kümesi."""
    if not isinstance(plan, dict):
        return set()
    out = set()
    if plan.get("crm") or plan.get("crm_report") or plan.get("relational_query"):
        out.add("crm")
    report = plan.get("logo_report") or {}
    if report:
        out.add("logo")
        if report.get("mode") == "cross_book_sales_quality":
            out.add("crm")
    if plan.get("metrics"):
        out.add("logo")
    if set(plan.get("dimensions") or ()) & CRM_DIMENSIONS:
        out.add("crm")
    for child in plan.get("sections") or ():
        out |= plan_sources(child)
    return out


def actual_route(answer):
    """API cevabından gerçek yol ve dayanağı."""
    kind = answer.get("type")
    semantic = answer.get("semantic") or {}
    if kind == "MODULE_INTRO":
        return "finans_disi", "type=MODULE_INTRO"
    if semantic.get("portal") is not None:
        return "portal", "semantic.portal"
    if semantic.get("engine") == "finance_contract_v1":
        sources = {str(run.get("source")) for run in semantic.get("executions") or [] if run.get("source")}
        basis = "semantic.executions"
        if not sources:
            sources, basis = plan_sources(semantic.get("plan")), "semantic.plan"
        sources &= {"logo", "crm"}
        if sources == {"logo", "crm"}:
            return "karma", basis
        if sources:
            return next(iter(sources)), basis
        return "cozulemedi", basis
    return "bilinmiyor", "semantic alanı tanınmadı"


def distribution(rows):
    out = {"toplam": len(rows), "beklenen_yol": Counter(r["beklenen_yol"] for r in rows),
           "set": Counter(r.get("set") for r in rows),
           "etiket_duzeyi": Counter(r.get("etiket_duzeyi") for r in rows),
           "netlestirme_gerekir": Counter(bool((r.get("belirsizlik") or {}).get("netlestirme_gerekir")) for r in rows),
           "set_etiketinden_farkli": Counter(bool(r.get("set_etiketinden_farkli")) for r in rows)}
    cross = defaultdict(Counter)
    for r in rows:
        cross[r.get("set")][r["beklenen_yol"]] += 1
    out["set_x_yol"] = {k: dict(v) for k, v in cross.items()}
    return {k: (dict(v) if isinstance(v, Counter) else v) for k, v in out.items()}


def score(results):
    """Doğruluk, karışıklık matrisi ve netleştirme ölçüsü."""
    matrix = defaultdict(Counter)
    for r in results:
        matrix[r["expected"]][r["actual"]] += 1
    scored = [r for r in results if r["actual"] not in ("hata",)]
    correct = sum(r["expected"] == r["actual"] for r in scored)
    clar = [r for r in results if r.get("clarificationExpected")]
    return {"answered": len(scored), "correct": correct,
            "accuracy": round(correct / len(scored), 4) if scored else None,
            "byExpected": {k: {"n": sum(v.values()), "correct": v.get(k, 0)} for k, v in matrix.items()},
            "confusion": {k: dict(v) for k, v in matrix.items()},
            "clarification": {"expected": len(clar), "asked": sum(r.get("answerType") == "CLARIFICATION" for r in clar)},
            "unexpectedClarification": sum(r.get("answerType") == "CLARIFICATION" and not r.get("clarificationExpected") for r in results)}


def live_session(base):
    """timasai için kısa ömürlü oturum (bellek: test-login-as-timasai); (call, close) döner."""
    sys.path.insert(0, str(Path(__file__).parent))
    from composable_live import environment
    env = environment("nanobase-semantic-bridge")
    login = environment("timas-login")
    db = sqlite3.connect(login.get("SESSION_DB", "/var/lib/timas-login/sessions.sqlite"))
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    db.execute("INSERT INTO sessions(token,username,expires) VALUES(?,?,?)", (digest, "timasai", time.time() + 900))
    db.commit()
    cookie = ("__Secure-timas_session" if login.get("COOKIE_SECURE", "1") != "0" else "timas_session") + "=" + token
    headers = {"Content-Type": "application/json", "X-Semantic-Caller": env.get("SEMANTIC_CALLER_TOKEN", ""), "Cookie": cookie}

    def call(path, body=None, timeout=240):
        db.execute("UPDATE sessions SET expires=? WHERE token=?", (time.time() + 900, digest))
        db.commit()
        req = urllib.request.Request(base + path, data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)

    def close():
        removed = db.execute("DELETE FROM sessions WHERE token=?", (digest,)).rowcount
        db.commit()
        db.close()
        return removed
    return call, close


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--set", default=str(DEFAULT_SET))
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="varsayılan: yalnız seti oku, dağılımı bas")
    mode.add_argument("--live", action="store_true", help="API'ye gerçek gönderim (yalnız test sunucusu)")
    p.add_argument("--out", help="--live için boş kanıt klasörü")
    p.add_argument("--only", default="", help="virgülle soru kimlikleri")
    p.add_argument("--limit", type=int, default=0, help="ilk N soru (0 = hepsi)")
    p.add_argument("--base", default="http://127.0.0.1:8795")
    p.add_argument("--sleep", type=float, default=0.0, help="sorular arası bekleme (sn)")
    a = p.parse_args()
    rows = load(a.set)
    if a.only:
        wanted = set(a.only.split(","))
        rows = [r for r in rows if r["id"] in wanted]
    if a.limit:
        rows = rows[:a.limit]
    if not a.live:
        print(json.dumps({"mode": "dry-run", "set": a.set, "distribution": distribution(rows)}, ensure_ascii=False, indent=1))
        return 0
    if sys.platform != "linux" or not Path("/proc").is_dir():
        raise SystemExit("--live yalnız test sunucusunda")
    if not a.base.startswith("http://127.0.0.1:"):
        raise SystemExit("Yalnız geri döngü API")
    if not a.out:
        raise SystemExit("--live için --out gerekli")
    os.umask(0o077)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise SystemExit("Boş kanıt klasörü kullanın")
    call, close = live_session(a.base)
    results, removed = [], 0
    try:
        for row in rows:
            item = {"id": row["id"], "expected": row["beklenen_yol"], "question": row["soru"],
                    "clarificationExpected": bool((row.get("belirsizlik") or {}).get("netlestirme_gerekir"))}
            started = time.time()
            try:
                answer = call("/api/v1/ask", {"question": row["soru"], "sampleSize": 3,
                                              "threadId": "routing-" + row["id"] + "-" + secrets.token_hex(4)})
                item["actual"], item["basis"] = actual_route(answer)
                item["answerType"] = answer.get("type")
                item["plan"] = (answer.get("semantic") or {}).get("plan")
                item["executions"] = [{"source": r.get("source"), "status": r.get("status")}
                                      for r in (answer.get("semantic") or {}).get("executions") or []]
            except (urllib.error.URLError, TimeoutError) as exc:
                item.update(actual="hata", error=type(exc).__name__ + ": " + str(exc)[:300])
                results.append(item)
                print(json.dumps(item, ensure_ascii=False), flush=True)
                print("DUR: API erişilemedi; tekrar gönderim yapılmadı", flush=True)
                break
            except Exception as exc:  # noqa: BLE001
                item.update(actual="hata", error=type(exc).__name__ + ": " + str(exc)[:300])
            item["seconds"] = round(time.time() - started, 1)
            results.append(item)
            (out / f"{row['id']}.json").write_text(json.dumps(item, ensure_ascii=False, indent=1, default=str))
            print(json.dumps({k: item.get(k) for k in ("id", "expected", "actual", "answerType", "seconds")}, ensure_ascii=False), flush=True)
            if a.sleep:
                time.sleep(a.sleep)
    finally:
        removed = close()
        report = {"set": a.set, "planned": len(rows), "completed": len(results), "sessionsDeleted": removed,
                  "score": score(results), "results": [{k: r.get(k) for k in ("id", "expected", "actual", "answerType", "basis", "error")} for r in results]}
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
        print("FINAL", json.dumps(report["score"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
