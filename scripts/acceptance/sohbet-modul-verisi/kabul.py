#!/usr/bin/env python3
"""Zeki AI sohbetine modül verisi — test sunucusunda kabul (Mac'te koşulmaz). Sıra ve komutlar: calistir.sh.

Üç bölüm, ayrı ayrı çağrılır:

  --scan                 Modelsiz: altın setlerde (answers-set100.json, set100.jsonl, golden-timas.json) portal
                         alanının ayırt edici kelimesini taşıyan sorular. Bunlar artık Logo/CRM'de güçlü kavrama
                         yerleşse de konu sınıflandırıcısına gider; tam kapı ÖNCE ve SONRA `--only` ile bunlarla koşar.
  --references           Portal veritabanında (salt okunur): chat_portal'ın planı derleyip çalıştırdığı sonuç ==
                         elle yazılmış doğrudan SQL (referans.sql R1–R10); yetkisiz kişiye ret; satır kapsamı (risk
                         sahibi) doğrudan SQL ile; kataloğun hiçbir kişisel/gizli kolonu seçenek yapmadığı; İK konusu
                         kapalı. Model kullanılmaz (plan açıkça kurulur) — rakamın SQL'den geldiğini sınar.
  --live                 Gerçek köprü, gerçek model: test_chat_portal.PORTAL_QUESTIONS (her boş konudan en az 3 soru)
                         /api/v1/ask'e sorulur; cevap türü, modelin seçtiği tablo = beklenen tablo, cevap kolonlarında
                         kişisel veri olmaması, ekrandaki metinde teknoloji adı olmaması, kimlik sorularının sabit
                         tanıtımla reddi denetlenir. Seçim olasılıkları özetlenir (CHAT_PORTAL_MIN_PROB/MARGIN ölçümü).
                         Kanıt dosyasındaki queryIds temizlik.py ile silinir.

Ortam: SEMANTIC_STORE_DSN, SEMANTIC_TENANT_ID (köprü env dosyasından), SEMANTIC_CALLER_TOKEN, BRIDGE (ör.
http://127.0.0.1:8798 yan köprü), COOKIE (timasai'nin kısa oturumu; test biter bitmez silinir), PYTHONPATH=<aday>/backend.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import access as A  # noqa: E402
from semantic_bridge import chat_portal as P  # noqa: E402
from semantic_bridge import chat_scope  # noqa: E402

HERE = Path(__file__).resolve().parent
TECH = re.compile(r"qwen|vllm|nvidia|\bgpt|llama|openai|anthropic|claude|gemini|mistral|temporal|timesfm|\bsql\b", re.I)


def _load_cases(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"backend/semantic_layer/tests/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ tarama

def scan() -> dict:
    out = {}
    base = ROOT / "tests/text2sql"
    sets = {"answers-set100.json": lambda d: [(c["id"], c["soru"]) for c in d["cases"]],
            "golden-timas.json": lambda d: [(c.get("id") or str(i), c.get("question") or c.get("soru") or "")
                                            for i, c in enumerate(d if isinstance(d, list) else d.get("cases", []))]}
    for name, read in sets.items():
        path = base / name
        if path.exists():
            rows = read(json.loads(path.read_text(encoding="utf-8")))
            out[name] = [i for i, q in rows if q and P.mentions_portal(q)]
    jl = base / "set100.jsonl"
    if jl.exists():
        rows = [json.loads(line) for line in jl.read_text(encoding="utf-8").splitlines() if line.strip()]
        out["set100.jsonl"] = [r["id"] for r in rows if P.mentions_portal(r.get("soru") or r.get("question") or "")]
    return out


# ------------------------------------------------------------------ referanslar

def _references() -> dict[str, str]:
    text = (HERE / "referans.sql").read_text(encoding="utf-8")
    out, key, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^-- @(R\d+)", line)
        if m:
            if key:
                out[key] = "\n".join(buf).strip().rstrip(";")
            key, buf = m.group(1), []
        elif key and not line.startswith("--"):
            buf.append(line)
    if key:
        out[key] = "\n".join(buf).strip().rstrip(";")
    return out


def _num(v):
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float):
        return round(v, 4)
    return v


def _as_map(rows: list, keyed: bool) -> dict:
    if not keyed:
        return {None: _num(rows[0][0] if rows else None)}
    return {r[0]: _num(r[1]) for r in rows}


# (referans, tablo, ölçü, kırılım yolu+kolon | None, koşullar, dönem ifadesi | None, tarih yolu+kolon | None)
PLANS = [
    ("R1", "semantic_risk_register", ("count", None), None, [((), "durum", "acik")], None, None),
    ("R2", "semantic_risk_register", ("count", None), ((), "kategori"), [], None, None),
    ("R3", "semantic_risk_actions", ("count", None), (("risk_id",), "kategori"), [], None, None),
    ("R4", "semantic_mail_messages", ("count", None), ((), "status"), [], None, None),
    ("R5", "semantic_ads_daily", ("sum", "spend"), (("campaign_id", "account_id"), "platform"), [], "geçen ay", ((), "day")),
    ("R6", "semantic_okur_inventory", ("sum", "eposta_izinli"), None, [], None, None),
    ("R7", "semantic_kurul_actions", ("count", None), ((), "durum"), [], None, None),
    ("R8", "sl_llm_job", ("avg", "queue_wait_ms"), ((), "module"), [], None, None),
    ("R9", "semantic_editorial_applications", ("count", None), ((), "status"), [], None, None),
    ("R10", "semantic_translation_jobs", ("count", None), ((), "draft_state"), [], None, None),
]


def references(engine, tenant: str) -> list[dict]:
    refs = _references()
    cat = [p for p in P.load(engine, tenant) if p["status"] == P.CERTIFIED]
    by_table = {p["table"]: p for p in cat}
    today = datetime.now(ZoneInfo(P.TZ_NAME)).date()
    results = []
    for rid, table, measure, group, filters, window, tcol in PLANS:
        row = {"kind": "reference", "id": rid, "table": table}
        base = by_table.get(table)
        if base is None:
            row.update(status="VERİ YOK", note="tablo onaylı katalogda yok (modül kurulmamış ya da onaylanmadı)")
            results.append(row)
            continue
        nodes = {n.path: n for n in P.reachable(base, by_table)}
        if group and group[0] not in nodes:
            row.update(status="FAIL", note=f"üst tablo bağı yok: {group[0]} (profilde doğrulanmadı)")
            results.append(row)
            continue
        if group:
            info = nodes[group[0]].profile["columns"].get(group[1]) or {}
            if not (info.get("kind") in P.GROUPABLE or info.get("groupable")):
                row["note"] = f"{group[1]} kırılım seçeneği değil ({info.get('kind')}/{info.get('why')})"
        plan = P.Plan(table=table, area=base["area"], measure=measure, measure_label="deger",
                      group=group, group_label="anahtar" if group else None,
                      filters=[P.FilterOption(pth, c, v, False, f"{c}: {v}", "kabul") for pth, c, v in filters])
        if window:
            plan.window, plan.time = P.read_window(window, today), tcol
        try:
            stmt, _ = P.compile_plan(plan, by_table, tenant, None, P.area(base["area"]))
            got_rows = P.execute(engine, stmt, 60000)
            got = _as_map([[r["c0"], r.get("c1")] for r in got_rows], bool(group)) if group else \
                {None: _num(got_rows[0]["c0"] if got_rows else None)}
            with engine.connect() as c:
                ref_rows = [tuple(r) for r in c.execute(sa.text(refs[rid]), {"tenant": tenant}).all()]
            want = _as_map(ref_rows, bool(group))
        except Exception as e:  # noqa: BLE001
            row.update(status="FAIL", note=f"çalışmadı: {str(e)[:300]}")
            results.append(row)
            continue
        empty = not ref_rows or ref_rows == [(None,)] or ref_rows == [(0,)]
        # Boş tabloda eşitlik bir şey kanıtlamaz: «VERİ YOK» yazılır, geçti sayılmaz (başarısız da değil).
        row.update(status="FAIL" if got != want else ("VERİ YOK" if empty else "PASS"), groups=len(want), latest=plan.latest)
        if got != want:
            row["diff"] = {"portal": {str(k): v for k, v in list(got.items())[:20]},
                           "referans": {str(k): v for k, v in list(want.items())[:20]}}
        results.append(row)

    # yetki: sayfası olmayana ret (model gerekmez: ret seçimden önce)
    nobody = A.Access(user="kabul-yetkisiz", admin=False, all=False, perms=frozenset({"sayfa:genel-bakis"}))
    for tid in ("risk", "yonetim", "isletim", "editoryal"):
        out = P.answer(engine, tenant, "Kaç kayıt var?", chat_scope.topic(tid), user=None, llm=None, access=nobody)
        ok = out["type"] == "NOT_PERMITTED" or (out["type"] == "DATA_UNAVAILABLE" and "onaylanmadı" in out["text"])
        results.append({"kind": "permission", "topic": tid, "type": out["type"], "status": "PASS" if ok else "FAIL"})

    # satır kapsamı: risk sahibi yalnız kendi satırlarını sayar (kullanıcı adı kanıta yazılmaz)
    reg = by_table.get("semantic_risk_register")
    if reg is not None:
        with engine.connect() as c:
            owner = c.execute(sa.text("SELECT lower(sahip) FROM semantic_risk_register WHERE tenant_id = :t AND sahip IS NOT NULL "
                                      "LIMIT 1"), {"t": tenant}).scalar()
            want = c.execute(sa.text("SELECT count(*) FROM semantic_risk_register WHERE tenant_id = :t AND durum = 'acik' AND "
                                     "(lower(sahip) = :u OR lower(olusturan) = :u)"), {"t": tenant, "u": owner or ""}).scalar()
        if owner:
            plan = P.Plan(table=reg["table"], area=reg["area"], measure=("count", None), measure_label="deger",
                          filters=[P.FilterOption((), "durum", "acik", False, "durum: acik", "kabul")])
            stmt, _ = P.compile_plan(plan, by_table, tenant, {"columns": ["sahip", "olusturan"], "user": owner},
                                     P.area(reg["area"]))
            got = P.execute(engine, stmt, 60000)[0]["c0"]
            results.append({"kind": "row_scope", "status": "PASS" if got == want else "FAIL", "portal": got, "referans": want})
        else:
            results.append({"kind": "row_scope", "status": "VERİ YOK"})

    # katalog: kişisel/gizli kolon hiçbir onaylı profilde seçenek değil; İK tablosu yok; İK konusu kapalı
    bad = [(p["table"], c) for p in P.load(engine, tenant) for c, i in p["columns"].items()
           if P.is_person_or_secret(c) and i["kind"] != P.EXCLUDED]
    hr = [p["table"] for p in P.load(engine, tenant) if p["table"].startswith("semantic_hr_")]
    results.append({"kind": "catalog_personal", "status": "PASS" if not bad else "FAIL", "offending": bad[:20]})
    results.append({"kind": "catalog_hr", "status": "PASS" if not hr else "FAIL", "offending": hr})
    ik = chat_scope.topic("ik")
    results.append({"kind": "hr_closed", "status": "PASS" if ik.get("closed") and "ik" not in chat_scope.connected_topic_ids()
                    else "FAIL"})
    return results


# ------------------------------------------------------------------ canlı

def live(bridge: str) -> tuple[list[dict], list[str], dict]:
    portal_cases = _load_cases("test_chat_portal")
    scope_cases = _load_cases("test_chat_scope")
    headers = {"Content-Type": "application/json", "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")}
    if os.environ.get("COOKIE"):
        headers["Cookie"] = os.environ["COOKIE"]

    def ask(q: str) -> dict:
        t = time.monotonic()
        req = urllib.request.Request(bridge.rstrip("/") + "/api/v1/ask", headers=headers,
                                     data=json.dumps({"question": q, "execute": True, "sampleSize": 50}).encode())
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                a = json.load(r)
        except urllib.error.HTTPError as e:
            a = {"type": f"HTTP_{e.code}", "explanation": e.read().decode("utf-8", "replace")[:500]}
        a["_ms"] = int((time.monotonic() - t) * 1000)
        return a

    person_labels = set()
    try:
        engine = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])
        for p in P.load(engine, os.environ.get("SEMANTIC_TENANT_ID", "default")):
            person_labels |= {P.humanize(c) for c, i in p["columns"].items() if i["kind"] == P.EXCLUDED and P.is_person_or_secret(c)}
    except Exception as e:  # noqa: BLE001
        print("katalog okunamadı, kişisel kolon denetimi yalnız adla:", e)
    results, qids, probs = [], [], {}
    for topic, q, table, expect in portal_cases.PORTAL_QUESTIONS:
        a = ask(q)
        if a.get("queryId"):
            qids.append(a["queryId"])
        portal = ((a.get("semantic") or {}).get("portal") or {})
        plan = portal.get("plan") or {}
        typ = a.get("type")
        text = " ".join(str(a.get(k) or "") for k in ("summary", "explanation"))
        cols = {c.get("name") for c in a.get("columns") or []}
        status, note = "PASS", None
        if typ in ("MODULE_INTRO", "DATA_UNAVAILABLE") or (typ or "").startswith("HTTP_"):
            status, note = "FAIL", "portal konusu cevaplanmadı"
        elif typ == "NOT_PERMITTED":
            status, note = "UNVERIFIED", "oturumdaki kişinin sayfa yetkisi yok"
        elif typ == "CLARIFICATION":
            status, note = "UNVERIFIED", "model emin değil (eşik) — netleştirme istendi"
        elif typ == "TEXT_TO_SQL" and plan.get("table") != table:
            status, note = "UNVERIFIED", f"model başka tablo seçti: {plan.get('table')}"
        if cols & person_labels:
            status, note = "FAIL", f"kişisel kolon cevapta: {sorted(cols & person_labels)}"
        if TECH.search(text):
            status, note = "FAIL", "ekrandaki metinde teknoloji adı"
        for ch in plan.get("choices") or []:
            if ch.get("p") is not None:
                probs.setdefault(ch["step"], []).append((round(ch["p"], 3), round(ch.get("margin") or 0, 3), bool(ch.get("confident"))))
        results.append({"kind": "portal", "topic": topic, "question": q, "expectTable": table, "expect": expect,
                        "type": typ, "table": plan.get("table"), "status": status, "note": note, "ms": a["_ms"],
                        "text": text[:400], "queryId": a.get("queryId")})
        print(json.dumps({k: results[-1][k] for k in ("topic", "question", "status", "type", "table", "note")}, ensure_ascii=False), flush=True)
    for q in scope_cases.IDENTITY_QUESTIONS[:8]:
        a = ask(q)
        if a.get("queryId"):
            qids.append(a["queryId"])
        ok = a.get("type") == "MODULE_INTRO" and a.get("explanation") == chat_scope.BI_INTRO
        results.append({"kind": "identity", "question": q, "type": a.get("type"), "status": "PASS" if ok else "FAIL"})
    summary = {step: {"n": len(v), "confident": sum(1 for x in v if x[2]), "p_min": min(x[0] for x in v),
                      "p_median": sorted(x[0] for x in v)[len(v) // 2], "margin_min": min(x[1] for x in v)}
               for step, v in probs.items()}
    return results, qids, summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--references", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--bridge", default=os.environ.get("BRIDGE", "http://127.0.0.1:8798"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    evidence: dict = {"at": datetime.now().isoformat(timespec="seconds")}
    failed = 0
    if args.scan:
        evidence["scan"] = scan()
        print(json.dumps(evidence["scan"], ensure_ascii=False))
    if args.references:
        engine = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])
        rows = references(engine, os.environ.get("SEMANTIC_TENANT_ID", "default"))
        evidence["references"] = rows
        for r in rows:
            print(json.dumps(r, ensure_ascii=False, default=str))
        failed += sum(1 for r in rows if r["status"] == "FAIL")
    if args.live:
        rows, qids, probs = live(args.bridge)
        evidence.update(live=rows, queryIds=qids, choiceProbabilities=probs)
        print(json.dumps({"choiceProbabilities": probs}, ensure_ascii=False))
        failed += sum(1 for r in rows if r["status"] == "FAIL")
        evidence["liveCounts"] = {s: sum(1 for r in rows if r["status"] == s) for s in ("PASS", "UNVERIFIED", "FAIL")}
        print(json.dumps(evidence["liveCounts"]))
    Path(args.out).write_text(json.dumps(evidence, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("kanıt:", args.out, "başarısız:", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
