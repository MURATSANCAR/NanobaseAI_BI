"""M50 Zeki AI kalitesi — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, meta veritabanı).

Uçların verdiği sayılar köprü kodu kullanılmadan yazılmış doğrudan sorgularla (`referans.sql` R1–R9) karşılaştırılır:
karne (cevap türü, cevaplanan/ret, hüküm sayıları, SEO, çeviri kalite puanı, redaksiyon), koşu vaka durumları, sürüm
sayısı, eş anlamlı kuyruğu (bilgi). Yazma: (1) `--gate` verilirse okuma kapısı `--report` ile bir kez koşar (modelsiz);
(2) timasai'nin kısa oturumuyla bir soru sorulur ve cevabına «Yanlış + not» verilir. Oluşan bütün kimlikler `--out`
dosyasına yazılır; `cleanup.py` siler (soru kaydı, geri bildirim, koşu + vakalar, sürüm satırları, değişiklik kaydı).

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin 15 dk'lık oturum çerezi), SEMANTIC_CALLER_TOKEN,
SEMANTIC_STORE_DSN, SEMANTIC_TENANT_ID, SEMANTIC_DATASOURCE_ID, PYTHONPATH=<aday ağaç>/backend.
Kullanım: python kabul.py --out /tmp/claude-m50/kabul-kimlikler.json [--gate <aday ağaç kökü>] [--days 30]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
TOKEN = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
TENANT = os.environ.get("SEMANTIC_TENANT_ID", "default")
DS = os.environ.get("SEMANTIC_DATASOURCE_ID", "logo")
P = BASE + "/api/v1/model-quality"
results: list[tuple[str, bool, str]] = []
created: dict[str, list] = {"queries": [], "feedback": [], "runs": [], "versions": [], "since": None}


def http(method: str, url: str, body=None, *, cookie: str | None = None, token: bool = False, timeout: int = 900):
    headers = {"Content-Type": "application/json"}
    if cookie is None:
        cookie = COOKIE
    if cookie:
        headers["Cookie"] = cookie
    if token:
        headers["X-Semantic-Caller"] = TOKEN
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw[:300]


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("GEÇTİ " if ok else "KALDI ") + name + (f" — {detail}" if detail else ""), flush=True)
    if len(results) % 10 == 0:
        print(f"-- ara durum: {sum(1 for r in results if r[1])} geçti, {sum(1 for r in results if not r[1])} kaldı", flush=True)


def rows(eng, sql: str, **p):
    with eng.connect() as c:
        return [dict(r) for r in c.execute(sa.text(sql), p).mappings().all()]


def metric(row: dict, key: str):
    return next((m["value"] for m in row.get("metrics", []) if m["key"] == key), None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--gate", default="", help="okuma kapısını --report ile koşturmak için aday ağaç kökü")
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    eng = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])
    now = datetime.now(timezone.utc)
    created["since"] = now.isoformat()

    # --- okuma: karne ↔ doğrudan SQL
    st, card = http("GET", f"{P}/scorecard?days={a.days}", timeout=600)
    check("karne ucu 200", st == 200, str(st))
    if st != 200:
        return finish(a.out)
    since = datetime.fromisoformat(card["generatedAt"]) - timedelta(days=a.days)
    by_id = {r["id"]: r for r in card["rows"]}
    bi = by_id.get("bi")
    ref = {r["answer_type"] or "—": int(r["n"]) for r in rows(eng, """
        SELECT answer_type, count(*) AS n FROM sl_query_log WHERE tenant_id = :t AND datasource_id = :d AND created_at >= :s
          AND coalesce(answer_type, '') <> 'MODULE_INTRO' GROUP BY answer_type""", t=TENANT, d=DS, s=since)}
    if bi:
        # Karne hesaplanırken yeni soru gelmiş olabilir: fark varsa bir kez daha okunur.
        check("R1 cevap türü dağılımı", (bi.get("byType") or {}) == ref, f"api={bi.get('byType')} sql={ref}")
        r2 = rows(eng, """SELECT
            count(*) FILTER (WHERE answer_type = 'TEXT_TO_SQL' AND executed AND error IS NULL) AS ok,
            count(*) FILTER (WHERE answer_type IN ('INCOMPLETE_ANSWER','DATA_UNAVAILABLE','NON_SQL_QUERY','SQL_INVALID')) AS ret,
            count(*) AS n FROM sl_query_log WHERE tenant_id = :t AND datasource_id = :d AND created_at >= :s
            AND coalesce(answer_type, '') <> 'MODULE_INTRO'""", t=TENANT, d=DS, s=since)[0]
        n = int(r2["n"])
        check("R2 soru sayısı", metric(bi, "questions") == n, f"api={metric(bi, 'questions')} sql={n}")
        want_ok = round(int(r2["ok"]) / n, 4) if n else None
        want_ret = round(int(r2["ret"]) / n, 4) if n else None
        check("R2 cevaplanan oranı", metric(bi, "answeredRate") == want_ok, f"api={metric(bi, 'answeredRate')} sql={want_ok}")
        check("R2 ret oranı", metric(bi, "denyRate") == want_ret, f"api={metric(bi, 'denyRate')} sql={want_ret}")
        r3 = {r["verdict"]: int(r["n"]) for r in rows(eng, "SELECT verdict, count(*) AS n FROM semantic_mq_feedback WHERE tenant_id = :t AND at >= :s GROUP BY verdict", t=TENANT, s=since)}
        for key, v in (("wrong", "yanlis"), ("partial", "kismen"), ("correct", "dogru")):
            check(f"R3 «{v}» sayısı", metric(bi, key) == r3.get(v, 0), f"api={metric(bi, key)} sql={r3.get(v, 0)}")
    else:
        check("R1 soru-cevap satırı görünür", False, "timasai'de sayfa:genel-bakis yok mu?")

    seo = by_id.get("seo")
    if seo and seo["measured"]:
        r4 = {r["status"]: int(r["n"]) for r in rows(eng, "SELECT status, count(*) AS n FROM semantic_seo_proposals WHERE tenant_id = :t AND decided_at >= :s GROUP BY status", t=TENANT, s=since)}
        check("R4 SEO onaylanan", metric(seo, "approved") == r4.get("onaylandi", 0), f"api={metric(seo, 'approved')} sql={r4.get('onaylandi', 0)}")
        check("R4 SEO reddedilen", metric(seo, "rejected") == r4.get("reddedildi", 0), f"api={metric(seo, 'rejected')} sql={r4.get('reddedildi', 0)}")
    else:
        print("BİLGİ R4 SEO satırı ölçülmedi (pencerede karar yok ya da modül kurulu değil)")

    tr = by_id.get("ceviri")
    if tr and tr["measured"]:
        r5 = rows(eng, """WITH seg AS (SELECT s.id, s.words FROM semantic_translation_segments s JOIN semantic_translation_jobs j ON j.id = s.job_id
                  WHERE j.tenant_id = :t AND s.status = 'onaylandi' AND s.approved_at >= :s)
                SELECT (SELECT coalesce(sum(words), 0) FROM seg) AS w,
                       (SELECT coalesce(sum(CASE e.severity WHEN 'kucuk' THEN 1 WHEN 'buyuk' THEN 5 WHEN 'kritik' THEN 25 ELSE 0 END), 0)
                          FROM semantic_translation_errors e WHERE e.segment_id IN (SELECT id FROM seg)) AS p""", t=TENANT, s=since)[0]
        want = round((1 - int(r5["p"]) / int(r5["w"])) * 100, 2) if int(r5["w"]) else None
        check("R5 çeviri kalite puanı", metric(tr, "mqm") == want, f"api={metric(tr, 'mqm')} sql={want}")
        drafts = rows(eng, """SELECT s.draft, s.target FROM semantic_translation_segments s JOIN semantic_translation_jobs j ON j.id = s.job_id
                  WHERE j.tenant_id = :t AND s.status = 'onaylandi' AND s.approved_at >= :s AND coalesce(s.draft, '') <> ''""", t=TENANT, s=since)
        norm = lambda x: re.sub(r"\s+", " ", x or "").strip()  # noqa: E731
        changed = sum(1 for d in drafts if norm(d["draft"]) != norm(d["target"]))
        check("R5 taslağı düzeltilen", tr["primary"]["detail"] == f"{changed}/{len(drafts)}", f"api={tr['primary']['detail']} sql={changed}/{len(drafts)}")
    else:
        print("BİLGİ R5 çeviri satırı ölçülmedi (pencerede taslaklı onaylı segment yok)")

    rd = by_id.get("redaksiyon")
    if rd and rd["measured"]:
        r6 = {r["status"]: r for r in rows(eng, """SELECT g.status, count(*) AS n,
                count(*) FILTER (WHERE g.status = 'kabul' AND g.applied_text IS NOT NULL AND g.applied_text <> g.suggestion) AS m
                FROM semantic_editorial_suggestions g JOIN semantic_editorial_works w ON w.id = g.work_id
                WHERE w.tenant_id = :t AND g.decided_at >= :s GROUP BY g.status""", t=TENANT, s=since)}
        ac, rj = int((r6.get("kabul") or {}).get("n", 0)), int((r6.get("red") or {}).get("n", 0))
        check("R6 redaksiyon kabul/red", rd["primary"]["detail"] == f"{ac}/{ac + rj}", f"api={rd['primary']['detail']} sql={ac}/{ac + rj}")
    else:
        print("BİLGİ R6 redaksiyon satırı ölçülmedi")

    r8 = {r["status"]: int(r["n"]) for r in rows(eng, "SELECT status, count(*) AS n FROM sl_vocabulary WHERE tenant_id = :t AND datasource_id = :d GROUP BY status", t=TENANT, d=DS)}
    print(f"BİLGİ R8 eş anlamlı durumları (karar kuyruğu sonraki sürüm): {r8}")

    # --- yazma 1: okuma kapısı --report (modelsiz)
    if a.gate:
        before = {r["id"] for r in rows(eng, "SELECT id FROM semantic_mq_runs WHERE tenant_id = :t", t=TENANT)}
        v_before = {r["id"] for r in rows(eng, "SELECT id FROM semantic_mq_versions WHERE tenant_id = :t", t=TENANT)}
        out = subprocess.run([sys.executable, "tests/text2sql/resolver-gate.py", "tests/text2sql/set100.jsonl",
                              "--url", BASE, "--report", BASE], cwd=a.gate, capture_output=True, text=True, timeout=1800,
                             env={**os.environ, "PYTHONPATH": os.path.join(a.gate, "backend")})
        print(out.stdout[-1500:], out.stderr[-800:])
        new = [r["id"] for r in rows(eng, "SELECT id FROM semantic_mq_runs WHERE tenant_id = :t", t=TENANT) if r["id"] not in before]
        created["runs"] += new
        created["versions"] += [r["id"] for r in rows(eng, "SELECT id FROM semantic_mq_versions WHERE tenant_id = :t", t=TENANT) if r["id"] not in v_before]
        check("kapı raporu köprüye yazıldı", len(new) == 1, f"yeni koşu {new}")
        if new:
            m = re.search(r"okuması değişen (\d+)", out.stdout)
            st, run = http("GET", f"{P}/runs/{new[0]}")
            check("koşu bozuk sayısı = betik çıktısı", bool(m) and run["tally"].get("bozuk", 0) == int(m.group(1)),
                  f"api={run['tally']} betik={m.group(1) if m else '?'}")
            r7 = {r["status"]: int(r["n"]) for r in rows(eng, "SELECT status, count(*) AS n FROM semantic_mq_cases WHERE run_id = :r GROUP BY status", r=new[0])}
            check("R7 vaka durumları = API", r7 == {k: v for k, v in run["tally"].items() if v}, f"api={run['tally']} sql={r7}")
            st, vs = http("GET", f"{P}/versions")
            n_versions = int(rows(eng, "SELECT count(*) AS n FROM semantic_mq_versions WHERE tenant_id = :t", t=TENANT)[0]["n"])
            check("sürüm sayısı = tablo", st == 200 and vs["total"] == n_versions, f"api={vs.get('total')} sql={n_versions}")

    # --- yazma 2: geri bildirim (önce geçersiz gövde)
    st, _ = http("POST", f"{P}/feedback", {"queryId": "yok", "verdict": "belki"})
    check("geçersiz hüküm reddedilir", st in (404, 422), str(st))
    st, ans = http("POST", BASE + "/api/v1/ask", {"question": "2026 toplam net ciro nedir?", "sampleSize": 5}, timeout=600)
    qid = (ans or {}).get("queryId") if st == 200 else None
    check("soru kaydı kimliği döner", bool(qid), f"{st} {str(ans)[:200]}")
    if qid:
        created["queries"].append(qid)
        st, fb = http("POST", BASE + "/api/v1/feedback", {"queryId": qid, "verdict": "yanlis", "comment": "M50 kabul denemesi"})
        check("eski uç üzerinden «Yanlış + not»", st == 200 and fb.get("verdict") == "yanlis", f"{st} {fb}")
        r9 = rows(eng, "SELECT validated FROM sl_query_log WHERE id = :q", q=qid)
        check("R9 validated = false", bool(r9) and r9[0]["validated"] is False, str(r9))
        f = rows(eng, "SELECT id, verdict, comment, triage_state FROM semantic_mq_feedback WHERE query_id = :q", q=qid)
        check("R9 geri bildirim satırı", len(f) == 1 and f[0]["verdict"] == "yanlis" and f[0]["triage_state"] == "yeni", str(f))
        created["feedback"] += [x["id"] for x in f]
        st, q = http("GET", f"{P}/queue?verdict=yanlis&state=yeni")
        check("kuyrukta görünür", st == 200 and any(i["queryId"] == qid for i in q["items"]), f"{st} toplam={q.get('total') if isinstance(q, dict) else q}")
    return finish(a.out)


def finish(out_path: str) -> int:
    with open(out_path, "w") as fh:
        json.dump(created, fh)
    ok = sum(1 for r in results if r[1])
    print(f"== SONUÇ: {ok}/{len(results)} geçti; kimlikler {out_path} (cleanup.py ile silin)")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    t0 = time.time()
    code = main()
    print(f"süre {time.time() - t0:.0f} sn")
    sys.exit(code)
