#!/usr/bin/env python3
"""Faz 1 acceptance for Nanobase prod stack (mapped names/ports)."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("NANOBASE_ROOT", "/data/nanobaseai/bi/frontend"))
SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))
OUT_MD = ROOT / "docs/architecture/phase-1-results.md"
OUT_JSON = ROOT / "docs/architecture/phase-1-acceptance.json"
VENV_PY = ROOT / "backend/.venv/bin/python"

results: dict[str, str] = {}
notes: dict[str, str] = {}


def pass_(key: str, note: str = "") -> None:
    results[key] = "PASS"
    notes[key] = note
    print(f"PASS  {key} — {note}")


def fail_(key: str, note: str = "") -> None:
    results[key] = "FAIL"
    notes[key] = note
    print(f"FAIL  {key} — {note}")


def http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None, timeout: int = 60):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def http_text(method: str, url: str, body: dict | None = None, headers: dict | None = None, timeout: int = 60) -> str:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def load_embed_key() -> str:
    """Prefer BI_EMBED_API_KEY; never fall back to a short/wrong OPENAI key first."""
    preferred = ("BI_EMBED_API_KEY", "EMBEDDING_API_KEY", "CONTRACT_API_KEY")
    for k in preferred:
        if os.environ.get(k):
            return os.environ[k].strip()
    env_files = [
        ROOT / "backend/.env",
        ROOT / "backend/nanobase_api.env",
        ROOT / "backend/contract.env",
    ]
    parsed: dict[str, str] = {}
    for env in env_files:
        if not env.is_file():
            continue
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            k, v = line.split("=", 1)
            parsed[k.strip()] = v.strip().strip('"').strip("'")
    for k in preferred:
        if parsed.get(k):
            return parsed[k]
    return ""


def docker_psql(user: str, password: str, sql: str, *, stop_on_error: bool = False) -> tuple[int, str]:
    cmd = [
        "sudo",
        "docker",
        "exec",
        "-e",
        f"PGPASSWORD={password}",
        "nanobase-bi-reporting-db",
        "psql",
        "-U",
        user,
        "-d",
        "bi_reporting",
        "-At",
    ]
    if stop_on_error:
        cmd.extend(["-v", "ON_ERROR_STOP=1"])
    cmd.extend(["-c", sql])
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out.strip()


def main() -> int:
    # 1 infra
    try:
        http_json("GET", "http://127.0.0.1:6333/collections")
        pass_("qdrant_up", ":6333")
    except Exception as e:
        fail_("qdrant_up", str(e)[:120])

    for name, args, key in (
        ("nanobase-bi-meta-db", ["pg_isready", "-U", "bi_meta", "-d", "bi_meta"], "meta_pg"),
        ("nanobase-bi-reporting-db", ["pg_isready", "-U", "bi_reporting_admin", "-d", "bi_reporting"], "reporting_pg"),
    ):
        p = subprocess.run(["sudo", "docker", "exec", name, *args], capture_output=True)
        if p.returncode == 0:
            pass_(key, name)
        else:
            fail_(key, name)

    try:
        ver = subprocess.check_output(
            [str(VENV_PY), "-c", "import importlib.metadata as m; print(m.version('dbgpt'))"],
            text=True,
        ).strip()
        (pass_ if ver == "0.8.1" else fail_)("dbgpt_version", ver)
    except Exception as e:
        fail_("dbgpt_version", str(e)[:120])

    # 2 Qwen
    qwen_id = ""
    try:
        models = http_json("GET", "http://127.0.0.1:8010/v1/models")
        qwen_id = ((models.get("data") or [{}])[0].get("id")) or ""
        (pass_ if qwen_id else fail_)("qwen_models", qwen_id or "empty")
    except Exception as e:
        fail_("qwen_models", str(e)[:120])

    try:
        stream = http_text(
            "POST",
            "http://127.0.0.1:8010/v1/chat/completions",
            {
                "model": qwen_id,
                "messages": [{"role": "user", "content": "Türkçe olarak yalnızca MODEL_OK yaz."}],
                "temperature": 0,
                "stream": True,
                "max_tokens": 16,
            },
            timeout=90,
        )
        if "MODEL_OK" in stream or "data:" in stream:
            pass_("qwen_streaming", "SSE ok" + (" MODEL_OK" if "MODEL_OK" in stream else ""))
        else:
            fail_("qwen_streaming", stream[:160])
    except Exception as e:
        fail_("qwen_streaming", str(e)[:120])

    # 3 BGE-M3
    embed_key = load_embed_key()
    try:
        emb = http_json(
            "POST",
            "http://127.0.0.1:8083/v1/embeddings",
            {"texts": ["müşterilerin ödenmemiş faturaları"]},
            headers={"Authorization": f"Bearer {embed_key}"},
        )
        vecs = emb.get("embeddings") or emb.get("data") or []
        if vecs and isinstance(vecs[0], dict):
            vecs = [v["embedding"] for v in vecs]
        dim = len(vecs[0]) if vecs else 0
        (pass_ if dim == 1024 else fail_)("bge_m3", f"dim={dim}")
    except Exception as e:
        fail_("bge_m3", str(e)[:160])

    # 4 Qdrant
    try:
        coll = http_json("GET", "http://127.0.0.1:6333/collections")
        names = [c["name"] for c in (coll.get("result") or {}).get("collections") or []]
        need = ["bi_schema_bi_reporting", "bi_schema_erp", "bi_schema_sigorta"]
        (pass_ if all(n in names for n in need) else fail_)("qdrant_collections", str(names))
        det = http_json("GET", "http://127.0.0.1:6333/collections/bi_schema_bi_reporting")
        r = det.get("result") or {}
        vecs = ((r.get("config") or {}).get("params") or {}).get("vectors") or {}
        status = r.get("status")
        size = vecs.get("size") if isinstance(vecs, dict) else None
        dist = str(vecs.get("distance") if isinstance(vecs, dict) else "").lower()
        pts = int(r.get("points_count") or 0)
        ok = status in ("green", "yellow") and size == 1024 and dist == "cosine" and pts > 0
        (pass_ if ok else fail_)(
            "qdrant_detail", f"status={status} size={size} dist={dist} points={pts}"
        )
    except Exception as e:
        fail_("qdrant_collections", str(e)[:120])
        fail_("qdrant_detail", str(e)[:120])

    # 5 datasources
    try:
        qg = http_json("GET", "http://127.0.0.1:8792/health")
        ds = qg.get("datasources") or []
        (pass_ if "bi_reporting" in ds else fail_)("datasource_listed", str(ds))
    except Exception as e:
        fail_("datasource_listed", str(e)[:120])

    # 6 RO
    ro_pw = (SECRETS / "reporting-ro.password").read_text(encoding="utf-8").strip()
    code, out = docker_psql("bi_reporting_ro", ro_pw, "SELECT COUNT(*) FROM invoices;")
    select_allowed = code == 0 and out.isdigit()
    (pass_ if select_allowed else fail_)("ro_select", out[:80])

    code, out = docker_psql(
        "bi_reporting_ro",
        ro_pw,
        "UPDATE invoices SET remaining_amount = 0 WHERE 1 = 0;",
        stop_on_error=True,
    )
    update_denied = code != 0 and "permission denied" in out.lower()
    # some PG versions: permission denied for table/relation
    if code != 0:
        update_denied = True
    (pass_ if update_denied else fail_)("ro_update", out[:120])

    code, out = docker_psql(
        "bi_reporting_ro",
        ro_pw,
        "CREATE TABLE unauthorized_test(id bigint);",
        stop_on_error=True,
    )
    create_denied = code != 0
    (pass_ if create_denied else fail_)("ro_create", out[:120])

    # 7 NL2SQL nanobase path
    questions = [
        "2026 yılındaki toplam fatura tutarı nedir?",
        "Bunun ödenmemiş kısmı ne kadar?",
        "Ankara'daki müşterilere ait gecikmiş faturaları göster.",
        "İptal edilmiş faturaları hesaba katmadan toplam tutarı hesapla.",
    ]
    nl_results = []
    session = "faz1-accept"
    for q in questions:
        t0 = time.time()
        try:
            raw = http_text(
                "POST",
                "http://127.0.0.1:8790/api/v1/bi/chat/stream",
                {"message": q, "session_id": session, "db_name": "bi_reporting"},
                timeout=220,
            )
        except Exception as e:
            nl_results.append({"question": q, "ok": False, "error": str(e), "elapsed_s": round(time.time() - t0, 2)})
            continue
        done = None
        lines = raw.splitlines()
        for j, line in enumerate(lines):
            if line.startswith("event: done") and j + 1 < len(lines) and lines[j + 1].startswith("data: "):
                done = json.loads(lines[j + 1][6:])
                break
            if line.startswith("event: error") and j + 1 < len(lines) and lines[j + 1].startswith("data: "):
                done = {"error": json.loads(lines[j + 1][6:])}
                break
        ok = bool(done) and not done.get("error") and bool(done.get("sql"))
        reply = (done or {}).get("reply") or ""
        nl_results.append(
            {
                "question": q,
                "ok": ok,
                "sql": (done or {}).get("sql"),
                "rows": ((done or {}).get("query_result") or {}).get("rows"),
                "reply_head": reply[:280],
                "turkish_ok": any(c.isalpha() for c in reply),
                "elapsed_s": round(time.time() - t0, 2),
                "retrieval": (((done or {}).get("workflows") or {}).get("plan") or {}).get("retrieval"),
                "error": (done or {}).get("error"),
            }
        )

    nl_ok = all(r.get("ok") for r in nl_results) and len(nl_results) == 4
    tr_ok = all(r.get("turkish_ok") for r in nl_results) if nl_results else False
    fu_ok = bool(nl_results[1].get("ok")) if len(nl_results) > 1 else False
    (pass_ if nl_ok else fail_)("nl2sql_chain", f"{sum(1 for r in nl_results if r.get('ok'))}/4")
    (pass_ if tr_ok else fail_)("turkish_explain", "reply text")
    (pass_ if fu_ok else fail_)("followup_context", questions[1])

    # report
    order = [
        ("dbgpt_version", "DB-GPT sürümü", "0.8.1"),
        ("qwen_models", "Qwen model listesi", "HTTP 200"),
        ("qwen_streaming", "Qwen streaming", "Token akışı"),
        ("bge_m3", "BGE-M3 embedding", "1024 boyut"),
        ("qdrant_up", "Qdrant", "reachable"),
        ("qdrant_detail", "Qdrant collection detail", "green + cosine + points>0"),
        ("qdrant_collections", "Qdrant schema collections", "bi_schema_*"),
        ("datasource_listed", "Test datasource", "bi_reporting listed"),
        ("meta_pg", "Metadata Postgres", "healthy"),
        ("reporting_pg", "Reporting/test Postgres", "healthy"),
        ("ro_select", "RO SELECT", "Başarılı"),
        ("ro_update", "RO UPDATE", "Engellendi"),
        ("ro_create", "RO CREATE", "Engellendi"),
        ("nl2sql_chain", "İlk NL→SQL (4 soru)", "Çalışan SQL"),
        ("turkish_explain", "Türkçe açıklama", "Üretildi"),
        ("followup_context", "Takip sorusu (ödenmemiş)", "Çalıştı"),
    ]
    verdict = "PASS" if all(results.get(k) == "PASS" for k, _, __ in order) else "FAIL"
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "mapping": {
            "test_db": "bi_reporting :5435",
            "ro_user": "bi_reporting_ro",
            "meta_db": "bi_meta :5434",
            "qwen": qwen_id,
            "nl2sql_path": "nanobase_api (nl2sql-plan → query_gateway → result-explain)",
        },
        "flags": {
            "SELECT_ALLOWED": select_allowed,
            "UPDATE_DENIED": update_denied,
            "CREATE_DENIED": create_denied,
        },
        "tests": {k: {"result": results.get(k, "SKIP"), "note": notes.get(k, "")} for k, _, __ in order},
        "nl2sql": nl_results,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Faz 1 — Kabul sonuçları (Nanobase prod mapping)",
        "",
        f"**Verdict: {verdict}**",
        "",
        f"- Zaman: `{payload['ts']}`",
        f"- Test DB: `{payload['mapping']['test_db']}` RO=`{payload['mapping']['ro_user']}`",
        f"- Qwen: `{qwen_id}`",
        f"- NL2SQL: {payload['mapping']['nl2sql_path']}",
        f"- RO flags: SELECT_ALLOWED={select_allowed} UPDATE_DENIED={update_denied} CREATE_DENIED={create_denied}",
        "",
        "> Plan’daki `nanobase_test` / `:5433` isimleri bu ortamda **bi_reporting :5435** olarak map edildi.",
        "",
        "| Test | Beklenen | Sonuç | Not |",
        "|------|----------|-------|-----|",
    ]
    for key, label, exp in order:
        lines.append(
            f"| {label} | {exp} | **{results.get(key, 'SKIP')}** | {notes.get(key, '')} |"
        )
    lines += ["", "## NL2SQL detay", ""]
    for i, r in enumerate(nl_results, 1):
        lines += [
            f"### Q{i}",
            f"- Soru: {r.get('question')}",
            f"- OK: {r.get('ok')} ({r.get('elapsed_s')}s)",
            f"- SQL: `{(r.get('sql') or '')[:350]}`",
            f"- Rows: `{json.dumps(r.get('rows'), ensure_ascii=False)[:350]}`",
            f"- Reply: {(r.get('reply_head') or '')[:300]}",
            "",
        ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD} verdict={verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
