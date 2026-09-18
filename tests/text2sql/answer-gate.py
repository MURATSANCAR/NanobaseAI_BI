"""Tam kapı: doğrulanmış sorular hâlâ DOĞRU cevap veriyor mu?

    answer-gate.py [--gold tests/text2sql/answers-set100.json] [--repeat 3] [--only Q68,Q69]
                   [--holdout | --dev] [--out <rapor.json>] [--url http://127.0.0.1:8795]

Sunucuda, gerçek köprüye ve gerçek veritabanlarına karşı koşar. Her altın soru:
  1. gerçek API'den `--repeat` kez sorulur; cevabın TAMAMI `/api/v1/result/{id}` ile alınır
     (önizlemenin 50 satırı değil);
  2. sorunun dondurulmuş referans SQL'i AYNI ANDA canlı veritabanında bir kez koşar (köprünün ürettiği
     SQL değil, ondan bağımsız yazılmış sorgu) — canlı veri her gün değişir, fark değişmez;
  3. her deneme referansla `checks` üzerinden karşılaştırılır: satır sayısı, bir kolonun toplamı,
     anahtar→değer eşleşmesi, anahtar başına nokta sorgusu. SQL metninin eşleşmesi geçme koşulu
     DEĞİLDİR (çok GPU + spekülatif çözümlemeyle aynı SQL beklenemez); kaç farklı SQL yazıldığı not edilir.

Hüküm, tek deneme değil: SAĞLAM (hepsi geçti) · KARARSIZ (bir kısmı) · BOZUK (hiçbiri) · VERİ (referans
boş/hatalı döndü — bu bir test hatası değil, veri durumudur ve bozulma sayılmaz).
Üç sayaç ayrı tutulur: answer / deny (dürüst ret) / clarify (netleştirme). Altında `deny` beklenen yerde
cevap üretmek de, `answer` beklenen yerde ret de bozulmadır.

Çıkış kodu: `verified: true` olan bir soru SAĞLAM değilse 1. Holdout soruları (`holdout: true`) için
kural/kavram yazılmaz; kırılırlarsa eksik olan genel kuraldır.

Ortam: SEMANTIC_CALLER_TOKEN, SEMANTIC_CONNECTION_FILE (ana kaynak), SEMANTIC_CRM_CONNECTION_FILE.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _arg(name: str, default: str = "") -> str:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _close(a, b, tolerance: float) -> bool:
    x, y = _num(a), _num(b)
    if x is None or y is None:
        return str(a or "").strip() == str(b or "").strip()
    # Kuruş yuvarlaması büyük sayılarda kabul edilir; oranlarda (|değer| < 1) mutlak pay yoktur —
    # 0,01'lik sabit pay 0,1897 ile 0,1980'i "eşit" saymıştı.
    floor = 0.005 if min(abs(x), abs(y)) >= 1 else 1e-9
    return abs(x - y) <= max(floor, tolerance * max(abs(x), abs(y)))


class Bridge:
    def __init__(self, url: str, token: str):
        self.url, self.token = url.rstrip("/"), token

    def _call(self, path: str, body: dict | None = None, timeout: int = 900) -> dict:
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-Semantic-Caller": self.token, "Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=timeout))

    def ask(self, question: str) -> dict:
        for attempt in range(6):
            try:
                answer = self._call("/api/v1/ask", {"question": question})
                break
            except urllib.error.URLError as ex:          # köprü yeniden başlatılıyor: soru değil, kurulum
                if attempt == 5 or "refused" not in str(ex).lower():
                    return {"type": "HTTP_ERROR", "explanation": str(ex)[:300]}
                time.sleep(20)
            except Exception as ex:  # noqa: BLE001
                return {"type": "HTTP_ERROR", "explanation": str(ex)[:300]}
        result_id = answer.get("resultId") or answer.get("id")
        if answer.get("type") == "TEXT_TO_SQL" and result_id and (answer.get("rowCount") or 0) > len(answer.get("records") or []):
            try:
                whole = self._call(f"/api/v1/result/{result_id}", timeout=900)
                answer["records"] = whole.get("records") or answer.get("records")
            except Exception as ex:  # noqa: BLE001
                answer["_partial"] = str(ex)[:200]
        return answer


def _pick(row: dict, names):
    """Kolon adı model koşusuna göre değişir (barkod / barcode_key): ilk bulunan aday."""
    for name in ([names] if isinstance(names, str) else list(names or [])):
        if name == "*":                       # tek değerli cevap: ilk sayısal kolon, adı ne olursa olsun
            return next((v for v in row.values() if _num(v) is not None and not isinstance(v, bool)), None)
        if name in row:
            return row[name]
    return None


def _has(row: dict, names) -> bool:
    return any(n == "*" or n in row for n in ([names] if isinstance(names, str) else list(names or [])))


def kind_of(answer: dict) -> str:
    """answer / deny / clarify / error — sayaçlar ayrı tutulur."""
    t = answer.get("type")
    if t == "TEXT_TO_SQL":
        return "answer"
    if t == "CLARIFICATION" or answer.get("needs_clarification"):
        return "clarify"
    if t in ("NON_SQL_QUERY", "INCOMPLETE_ANSWER"):
        return "deny"
    return "error"


def check(case: dict, answer: dict, reference: list[dict], lookups, tolerance: float) -> list[str]:
    """Bu denemenin referansa uymayan yanları; boşsa geçti."""
    problems: list[str] = []
    records = answer.get("records") or []
    if answer.get("_partial"):
        problems.append(f"cevabın tamamı alınamadı: {answer['_partial']}")
    for spec in case.get("checks") or []:
        kind = spec["kind"]
        if kind == "rows":
            want = len(reference) if spec.get("reference", "count") == "count" else _num(reference[0][spec["reference"]])
            got = answer.get("rowCount") if answer.get("rowCount") is not None else len(records)
            if not _close(got, want, spec.get("tolerance", tolerance)):
                problems.append(f"satır sayısı {got}, referans {want}")
        elif kind == "empty":
            if (answer.get("rowCount") or 0) != 0 and any(any(v not in (None, 0, "") for v in r.values()) for r in records):
                problems.append(f"boş beklenirdi, {answer.get('rowCount')} satır geldi")
        elif kind == "sum":
            got = sum(_num(_pick(r, spec["answer"])) or 0 for r in records)
            want = sum(_num(r.get(spec["reference"])) or 0 for r in reference)
            if records and not _has(records[0], spec["answer"]):
                problems.append(f"cevapta '{spec['answer']}' kolonu yok: {sorted((records[0] if records else {}).keys())}")
            elif not _close(got, want, spec.get("tolerance", tolerance)):
                problems.append(f"{spec['answer']} toplamı {got:,.2f}, referans {want:,.2f}")
        elif kind == "value":
            got = _pick(records[0], spec["answer"]) if records else None
            want = reference[0].get(spec["reference"]) if reference else None
            if not _close(got, want, spec.get("tolerance", tolerance)):
                problems.append(f"{spec['answer']} = {got}, referans {want}")
        elif kind == "values_present":
            # Biçimden bağımsız: referanstaki her değer cevabın sayısal hücrelerinden birinde bulunmalı
            # (iki yıl bir satırda iki kolon da olabilir, iki satırda tek kolon da).
            cells = [v for r in records for v in r.values() if _num(v) is not None and not isinstance(v, bool)]
            for ref_row in reference:
                for column in spec["reference"]:
                    want = ref_row.get(column)
                    if want is not None and not any(_close(v, want, spec.get("tolerance", tolerance)) for v in cells):
                        problems.append(f"referans {column} = {want} cevapta yok")
        elif kind == "pairs":
            want = {str(r.get(spec["reference_key"]) or "").strip(): r.get(spec["reference_value"]) for r in reference}
            got = {str(_pick(r, spec["answer_key"]) or "").strip(): _pick(r, spec["answer_value"]) for r in records}
            for key in list(want)[: int(spec.get("top", 10))]:
                if key not in got:
                    problems.append(f"'{key[:40]}' cevapta yok")
                elif not _close(got[key], want[key], spec.get("tolerance", tolerance)):
                    problems.append(f"'{key[:40]}': {got[key]}, referans {want[key]}")
        elif kind == "lookup":
            for row in records[: int(spec.get("top", 3))]:
                key = re.sub(r"[^0-9A-Za-z._-]", "", str(_pick(row, spec["answer_key"]) or ""))
                if not key:
                    problems.append(f"cevapta '{spec['answer_key']}' anahtarı yok")
                    break
                found = lookups(spec["source"], spec["sql"].replace("{key}", key))
                want = found[0].get(spec["reference"]) if found else None
                if not _close(_pick(row, spec["answer_value"]), want, spec.get("tolerance", tolerance)):
                    problems.append(f"{key}: {spec['answer_value']} = {_pick(row, spec['answer_value'])}, referans {want}")
        else:
            problems.append(f"bilinmeyen kontrol türü: {kind}")
    return problems


def main() -> int:
    gold_path = Path(_arg("--gold", "tests/text2sql/answers-set100.json"))
    repeat = int(_arg("--repeat", "3"))
    tolerance = float(_arg("--tolerance", "0.0005"))
    only = {x.strip().upper() for x in _arg("--only").split(",") if x.strip()}
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    bridge = Bridge(_arg("--url", "http://127.0.0.1:8795"), os.environ.get("SEMANTIC_CALLER_TOKEN", ""))

    sys.path.insert(0, _arg("--backend", "/data/nanobaseai/bi/frontend/backend"))
    from semantic_layer.profiler.connectors import connector_from_file
    files = {"logo": os.environ.get("SEMANTIC_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/logo-mssql-connection.json"),
             "crm": os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")}
    connectors: dict[str, object] = {}

    def run(source: str, sql: str) -> list[dict]:
        if source not in connectors:
            connectors[source] = connector_from_file(files[source])
        return connectors[source].execute(sql, 1_000_000)[1]

    report, counters, failed = [], {"answer": 0, "deny": 0, "clarify": 0, "error": 0}, 0
    for case in gold["cases"]:
        label = f"Q{case['n']}"
        if only and label.upper() not in only and case["id"].upper() not in only:
            continue
        if ("--holdout" in sys.argv and not case.get("holdout")) or ("--dev" in sys.argv and case.get("holdout")):
            continue
        reference, data_note = [], ""
        if case.get("reference_sql"):
            try:
                reference = run(case.get("source", "logo"), case["reference_sql"])
            except Exception as ex:  # noqa: BLE001
                data_note = f"referans çalışmadı: {str(ex)[:160]}"
            if not data_note and not reference and case["expect"] == "answer" and not any(c["kind"] == "empty" for c in case.get("checks") or []):
                data_note = "referans boş döndü"
        attempts, sqls = [], set()
        for _ in range(repeat):
            started = time.time()
            answer = bridge.ask(case["soru"])
            got = kind_of(answer)
            counters[got] += 1
            sqls.add(re.sub(r"\s+", " ", (answer.get("sql") or "")).strip().lower())
            wanted = [case["expect"]] if isinstance(case["expect"], str) else list(case["expect"])
            if got not in wanted:
                problems = [f"beklenen {'/'.join(wanted)}, gelen {got}: {(answer.get('explanation') or answer.get('summary') or '')[:160]}"]
            elif got == "answer" and not data_note:
                problems = check(case, answer, reference, run, tolerance)
            else:
                problems = []
            attempts.append({"kind": got, "sec": round(time.time() - started, 1), "problems": problems,
                             "federated": bool(answer.get("federated")), "rows": answer.get("rowCount")})
        passed = sum(1 for a in attempts if not a["problems"])
        verdict = "VERİ" if data_note else "SAĞLAM" if passed == repeat else "BOZUK" if passed == 0 else "KARARSIZ"
        if case.get("verified") and verdict not in ("SAĞLAM", "VERİ"):
            failed += 1
        report.append({"n": case["n"], "id": case["id"], "verdict": verdict, "passed": f"{passed}/{repeat}",
                       "distinctSql": len(sqls - {""}), "holdout": bool(case.get("holdout")), "verified": bool(case.get("verified")),
                       "dataNote": data_note, "attempts": attempts})
        first = next((p for a in attempts for p in a["problems"]), data_note)
        print(f"{label:>4} {verdict:<9} {passed}/{repeat}  {len(sqls - {''})} farklı SQL  {case['soru'][:70]}" + (f"\n       ↳ {first}" if first else ""), flush=True)

    tally: dict[str, int] = {}
    for r in report:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print(f"\n{len(report)} soru × {repeat} · " + " · ".join(f"{k} {v}" for k, v in sorted(tally.items())) +
          f" · sayaçlar {counters} · doğrulanmışken sağlam olmayan {failed}")
    out = _arg("--out")
    if out:
        Path(out).write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "repeat": repeat,
                                         "tally": tally, "counters": counters, "cases": report}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
