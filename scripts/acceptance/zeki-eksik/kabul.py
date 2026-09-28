"""Eksik tamamlama kabulü (test sunucusunda; yerelde koşulmaz): öneri 18 hak haritası, finansal denetim bulgu açıklaması +
istisna kümeleme, ihale risk koşulu işaretleme, telif kapak e-postası + koşu özeti, SEO fırsat sorgusundan ürün önerisi.

Referanslar köprü kodunu kullanmaz: köprü veritabanı doğrudan SQL ile (R1, R2, R6, R7, R9), Logo doğrudan bağlantı
dosyasıyla (R3), şartname dosyası diskten okunur (R5; metni aynı okuyucu çıkarır — denetlenen alıntı, okuyucu değil).

Yazma: hak haritası çıkarımı (uygulama çıktısı, onaylanmaz — kalır), finansal denetim açıklama/küme dosyaları (temizlikte
silinir), ihale risk işaretleri (`ZE_IHALE` verilirse; o ihalenin önceki işaretleri yenisiyle değişir, kararlar korunur),
koşu özeti (`ozet_json.anlatim`; temizlikte silinir), SEO önerisi + hedef sorgu kaydı (temizlikte silinir). Kimlikler
`--out` dosyasına.
Ortam: BASE (yan port köprüsü), COOKIE (timasai 15 dk oturumu), SEMANTIC_STORE_DSN, SEMANTIC_CONNECTION_FILE (Logo),
PYTHONPATH=<aday ağaç>/backend. İsteğe bağlı: ZE_IHALE (şartnamesi yüklü ihale kimliği), ZE_TENANT (varsayılan köprünün).
Kullanım: python kabul.py --out /tmp/claude-ze/kabul-kimlikler.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import sqlalchemy as sa

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
TECH = ("qwen", "vllm", "llm", "timesfm", "temporal", "openai", "dil modeli")
results: list[tuple[str, bool, str]] = []


def http(method: str, path: str, body=None, timeout=1800):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Cookie": COOKIE, "Content-Type": "application/json", "X-Semantic-Caller": "kabul"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("GEÇTİ " if ok else "KALDI ") + name + (f" — {detail}" if detail else ""), flush=True)


def fold(s) -> str:
    t = str(s or "").translate(str.maketrans("İIıŞşĞğÜüÖöÇçÂâÎîÛû’'", "iiissgguuooccaaiiuu  ")).lower()
    return " ".join(t.split())


def no_tech(text: str) -> bool:
    f = fold(text)
    return not any(re.search(r"(?<![a-z0-9])" + re.escape(t), f) for t in TECH)


def wait(path: str, done, tries: int = 900, every: float = 2.0):
    for _ in range(tries):
        st, j = http("GET", path)
        if st == 200 and done(j):
            return j
        time.sleep(every)
    return None


def logo():
    from semantic_layer.profiler.connectors import connector_from_file

    conn = connector_from_file(os.environ["SEMANTIC_CONNECTION_FILE"])
    conn.query_timeout = 1800

    def run(sql: str):
        _cols, rows, _t = conn.execute(sql, 2_000_000)
        return rows
    return run


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    created: dict[str, list] = {"auditFiles": [], "runNote": [], "seoProposal": []}
    eng = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])

    # ---------------------------------------------------------------- R1–R2: hak haritası ↔ ortak not tablosu
    st, j = http("POST", "/api/v1/rights/map/extract", {})
    check("R0 hak haritası çıkarımı başladı", st == 202, str(st))
    wait("/api/v1/rights/map/extract", lambda x: not x.get("running"))
    with eng.connect() as c:
        notes = {r.contract_key: r for r in c.execute(sa.text(
            "SELECT contract_key, metin, metin_hash FROM semantic_rights_notes"))}
        maps = list(c.execute(sa.text("SELECT id, contract_key, metin_hash, alanlar FROM semantic_rights_map")))
    bad_quote, bad_hash, n_items = [], [], 0
    for m in maps:
        note = notes.get(m.contract_key)
        fields = m.alanlar if isinstance(m.alanlar, dict) else json.loads(m.alanlar or "{}")
        if note is None or note.metin_hash != m.metin_hash:
            bad_hash.append(m.id)
            continue
        text = fold(note.metin)
        for k, v in fields.items():
            for x in (v if isinstance(v, list) else [v] if v else []):
                n_items += 1
                if x.get("kaynak") != "insan" and fold(x.get("alinti")) not in text:
                    bad_quote.append((m.id, k, x.get("deger")))
    check("R1 her harita değeri notun metninde birebir alıntılı", not bad_quote, f"{n_items} değer, alıntısız {bad_quote[:5]}")
    check("R2 harita ↔ not metin özeti ve eksik harita yok", not bad_hash and len(maps) >= len(notes),
          f"not {len(notes)}, harita {len(maps)}, özet uyuşmayan {bad_hash[:5]}")
    st, j = http("GET", "/api/v1/rights/notes?status=")
    shown = [n for n in (j.get("items") or []) if n.get("map")] if st == 200 else []
    check("R2b not listesi haritayı gösteriyor", st == 200 and (bool(shown) or not maps), f"{len(shown)} notta harita")

    # ---------------------------------------------------------------- R3–R4: finansal denetim
    st, ov = http("GET", "/api/v1/financial-audit/overview")
    if st == 200:
        run_id = ov["runId"]
        deep = [c for c in ov.get("deepAudit", {}).get("checks", []) if c.get("status") == "finding"]
        if deep:
            cid = deep[0]["id"]
            http("POST", f"/api/v1/financial-audit/runs/{run_id}/clusters/{cid}")
            created["auditFiles"] += [f"{run_id}-{cid}.clusters.json"]
            cl = wait(f"/api/v1/financial-audit/runs/{run_id}/clusters/{cid}", lambda x: x.get("state") in ("ready", "error"))
            from semantic_bridge.financial_audit_deep import exception_sql, source_sql, DEFINITIONS

            d = DEFINITIONS[cid]
            ref = logo()(f"SELECT COUNT(*) AS n FROM ({source_sql(d[1], ov['year'], ov['lastDate'])}) S WHERE {d[2]}")
            n = int(ref[0]["n"]) if ref else -1
            ok = bool(cl) and cl.get("state") == "ready" and cl.get("totalRows") == n == deep[0]["affected"]
            check("R3 küme satır toplamı = doğrudan Logo istisna sayısı = rapor bulgusu", ok,
                  f"{cid}: küme {cl and cl.get('totalRows')}, Logo {n}, rapor {deep[0]['affected']}, sql={'var' if cl and cl.get('sql') else 'yok'}")
        else:
            check("R3 küme (bulgu veren derin kontrol yok)", True, "atlandı")
        fnd = [c for c in ov.get("checks", []) if c.get("status") == "finding"] or deep
        if fnd:
            cid = fnd[0]["id"]
            st, ex = http("POST", f"/api/v1/financial-audit/runs/{run_id}/explain/{cid}")
            created["auditFiles"].append(f"{run_id}-{cid}.explain.json")
            from semantic_bridge import zeki_text as Z

            bad = Z.unsupported(ex.get("metin") or "", [ex.get("olgular"), ex.get("metin") if ex.get("kaynak") == "kural" else None],
                                free_upto=3) if st == 200 else ["hata"]
            check("R4 bulgu açıklaması sayı denetimli, teknoloji adı yok", st == 200 and not bad and no_tech(ex.get("metin") or ""),
                  f"{cid} kaynak={ex.get('kaynak') if st == 200 else st} olgu dışı={bad}")
    else:
        check("R3–R4 finansal denetim raporu", False, f"overview {st}")

    # ---------------------------------------------------------------- R5: ihale risk işaretleri ↔ şartname metni
    tid = os.environ.get("ZE_IHALE")
    if tid:
        st, job = http("POST", f"/api/v1/tenders/{tid}/risk-flags", {})
        if st == 202:
            wait(f"/api/v1/tenders/{tid}/jobs/{job['id']}", lambda x: x.get("durum") not in ("calisiyor", "sirada"))
        st, rl = http("GET", f"/api/v1/tenders/{tid}/risk-flags")
        from semantic_bridge import tenders as T

        with eng.connect() as c:
            f = c.execute(sa.text("SELECT id, ad FROM semantic_tender_files WHERE tender_id = :t AND tur = 'sartname' "
                                  "ORDER BY zaman DESC"), {"t": tid}).first()
        if f:
            path, name, _ = T.file_of(eng, os.environ.get("ZE_TENANT", "default"), tid, f.id)
            text = T.fold(T.document_text(name, Path(path).read_bytes()))
            miss = [i["alinti"][:60] for i in rl.get("items", []) if T.fold(i["alinti"]) not in text]
            with eng.connect() as c:
                n_db = c.execute(sa.text("SELECT COUNT(*) FROM semantic_tender_risks WHERE tender_id = :t"), {"t": tid}).scalar()
            check("R5 her risk işareti şartnamede birebir; tablo = ekran", st == 200 and not miss and n_db == len(rl.get("items", [])),
                  f"{len(rl.get('items', []))} işaret, tabloda {n_db}, alıntısız {miss[:3]}")
        else:
            check("R5 ihale risk", False, "şartname dosyası bulunamadı")
    else:
        check("R5 ihale risk (ZE_IHALE verilmedi)", True, "atlandı")

    # ---------------------------------------------------------------- R6–R7: telif koşu özeti + kapak e-postası
    with eng.connect() as c:
        run = c.execute(sa.text("SELECT id, no FROM semantic_royalty_runs WHERE durum = 'onayli' ORDER BY donem_bit DESC")).first()
    if run:
        st, note = http("POST", f"/api/v1/royalty/runs/{run.id}/summary-note")
        created["runNote"].append(run.id)
        with eng.connect() as c:
            ref = {r.para or "TRY": float(r.net or 0) for r in c.execute(sa.text(
                "SELECT para, SUM(net) AS net FROM semantic_royalty_run_lines WHERE run_id = :r AND durum = 'hesaplandi' "
                "GROUP BY para"), {"r": run.id})}
        from semantic_bridge import contracts_terms as CT

        want = {CT.CURRENCIES.get(k, k): CT.money(round(v, 2), k) for k, v in ref.items()}
        got = {k: v.get("ödenecek") for k, v in ((note.get("olgular") or {}).get("toplamlar") or {}).items()} if st == 200 else {}
        check("R6 koşu özeti toplamları = doğrudan SQL, sorgu dönüyor", st == 200 and got == want and bool(note.get("sql")),
              f"{run.no}: ekran {got} / SQL {want}")
        with eng.connect() as c:
            party = c.execute(sa.text("SELECT party_key, ad, toplam_json FROM semantic_royalty_party_statements WHERE run_id = :r "
                                      "ORDER BY ad"), {"r": run.id}).first()
        if party:
            st, em = http("POST", f"/api/v1/royalty/runs/{run.id}/parties/{party.party_key}/cover-email")
            tot = party.toplam_json if isinstance(party.toplam_json, dict) else json.loads(party.toplam_json or "{}")
            from semantic_bridge import zeki_text as Z

            body = (em.get("metin") or "").replace(party.ad or "", "") if st == 200 else ""
            bad = Z.unsupported(body, [tot, em.get("olgular")], free_upto=0) if st == 200 else ["hata"]
            check("R7 kapak e-postası: sayılar beyanname toplamında, ad yerinde, teknoloji adı yok",
                  st == 200 and not bad and (em.get("metin") or "").startswith(f"Sayın {party.ad}") and no_tech(em.get("metin") or ""),
                  f"kaynak={em.get('kaynak') if st == 200 else st} olgu dışı={bad}")
    else:
        check("R6–R7 telif (onaylı koşu yok)", True, "atlandı")

    # ---------------------------------------------------------------- R8–R9: SEO fırsat sorgusundan öneri
    st, op = http("GET", "/api/v1/seo-geo/opportunities?kind=dusuk_tiklama&brand=0&limit=200")
    item = next((i for i in (op.get("items") or []) if i.get("productId") and not i.get("targetProposal")), None) if st == 200 else None
    if item:
        with eng.connect() as c:
            before = {r.id for r in c.execute(sa.text("SELECT id FROM semantic_seo_proposals WHERE product_id = :p"),
                                              {"p": item["productId"]})}
        st, pr = http("POST", f"/api/v1/seo-geo/products/{item['productId']}/propose",
                      {"query": item["query"], "page": item["page"], "position": item["position"],
                       "impressions": item["impressions"], "clicks": item["clicks"], "kind": "dusuk_tiklama"})
        if st == 200:
            created["seoProposal"].append({"id": pr["id"], "product": item["productId"], "had": sorted(before)})
        with eng.connect() as c:
            t = c.execute(sa.text("SELECT query FROM semantic_seo_proposal_targets WHERE proposal_id = :i"),
                          {"i": pr.get("id") if st == 200 else ""}).first()
            p = c.execute(sa.text("SELECT status, sent_at FROM semantic_seo_proposals WHERE id = :i"),
                          {"i": pr.get("id") if st == 200 else ""}).first()
        check("R8 öneri hazır, gönderim yok, hedef sorgu kayıtlı", st == 200 and p is not None and p.status == "hazir"
              and p.sent_at is None and t is not None, f"sorgu «{item['query']}» → {t and t.query}")
        st, op2 = http("GET", "/api/v1/seo-geo/opportunities?kind=dusuk_tiklama&brand=0&limit=200")
        again = next((i for i in op2.get("items", []) if i["query"] == item["query"] and i.get("productId") == item["productId"]), None)
        check("R9 fırsat satırı önerinin durumunu gösteriyor", bool(again and again.get("targetProposal")),
              str(again and again.get("targetProposal")))
    else:
        check("R8–R9 SEO (ürüne bağlı fırsat yok)", True, "atlandı")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(created, ensure_ascii=False, indent=1))
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} geçti; kimlikler {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
