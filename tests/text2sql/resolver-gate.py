"""Hızlı kapı: bir değişiklik soruların OKUNMASINI değiştirdi mi? Model yok, VPN yok, ~1 dakika.

    resolver-gate.py <questions.jsonl> [--baseline tests/text2sql/resolver-baseline-set100.json]
                     [--record] [--url http://127.0.0.1:8795]

Gerçek köprünün `/api/v1/semantic/resolve` ucunu her soru için çağırır ve yalnız çözücünün çıktısını
kayıtlı anlık görüntüyle karşılaştırır: hangi kaynak, hangi kavramlar hangi role yerleşti, ne düştü ve
neden, ne modele bırakıldı. 2026-09-18'de doğrulanmış 17 cevabın bozulduğu ancak 100 soru yeniden
sorulunca (1,5 saat, model + VPN) görüldü; bozulmaların çoğu çözücü çıktısında zaten duruyordu — yanlış
kaynak, düşürülen kavram, sıradan kelimeyi kapan eş anlamlı. Bu kapı onları eklenme anında gösterir.

Bu kapı cevabın doğru olduğunu İDDİA ETMEZ: kaynak ve slotlar doğruyken SQL şişik toplam yazabilir.
Onu tam kapı (referans SQL + tekrar) yakalar. İkisi tek skora çevrilmez.

Çıkış kodu: okuması değişen soru varsa 1. `--record` yeni temel çizgiyi yazar; yazarken köprünün
katalog/dil havuzu özetlerini ve (verilmişse) kural ve istem dosyalarının özetlerini de saklar —
"neye göre doğruydu" sorusunun cevabı budur. SEMANTIC_CALLER_TOKEN ortamdan okunur; SEMANTIC_STORE_DSN
varsa tabloların kaynağı (ERP/CRM) profil kaydından okunur.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

#: çözücünün açıklama izinde bir kavramın elendiğini söyleyen cümleler → gerekçe kodu
_DROPS = (
    (re.compile(r"'(.+?)' katalogda .*? tarafında .*? olarak tanımlı; .*modele?l? o kaynakta yorumlayacak"), "OTHER_SOURCE_LEFT_TO_MODEL"),
    (re.compile(r"'(.+?)' bir belge türü olarak okundu"), "METRIC_READ_AS_DOCUMENT_NAME"),
    (re.compile(r"'(.+?)' sayım sözcüğü olarak okundu"), "MEASURE_READ_AS_COUNT_WORD"),
    (re.compile(r"'(.+?)' .*?ölçüsünün birimi olarak okundu"), "MEASURE_READ_AS_UNIT"),
    (re.compile(r"'(.+?)' sıralama sayısı olarak okundu"), "WORD_READ_AS_ROW_LIMIT"),
    (re.compile(r"varsayılan dönem geri alındı"), "DEFAULT_PERIOD_WITHDRAWN"),
    (re.compile(r"dönem belirtilmedi → varsayılan"), "DEFAULT_PERIOD_APPLIED"),
    (re.compile(r"→ o kaynak seçildi"), "SOURCE_CHOSEN_BY_TALLY"),
)


def _arg(name: str, default: str = "") -> str:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _sources() -> dict[str, str]:
    dsn = os.environ.get("SEMANTIC_STORE_DSN")
    if not dsn:
        return {}
    import sqlalchemy as sa
    out: dict[str, str] = {}
    with sa.create_engine(dsn).connect() as conn:
        for entity, schema in conn.execute(sa.text("select upper(entity), schema_name from sl_schema_profile")):
            source = (schema or "").split(".")[0].upper() if "." in (schema or "") else "ANA"
            out[entity] = source
            # katalog aynı tabloyu iki yazımla adlandırır (STLINE / LG_STLINE / DBO_LG_STLINE)
            out.setdefault(re.sub(r"^(DBO_)?(LG_)?", "", entity), source)
    return out


def _slot(slot: dict, source_of: dict[str, str]) -> dict:
    m = slot.get("mapping") or {}
    what = m.get("column") or (("f:" + _sha(m.get("formula") or "")) if m.get("formula") else "")
    entity = (m.get("entity") or "")
    return {"term": slot.get("term"), "type": slot.get("semanticType"), "status": slot.get("status"),
            "concept": slot.get("conceptId") or "", "entity": entity, "what": what,
            "values": sorted(m.get("values") or []), "role": (slot.get("explain") or {}).get("role") or "",
            "source": (source_of.get(entity.upper()) or source_of.get(re.sub(r"^(DBO_)?(LG_)?", "", entity.upper()), "?")) if entity else ""}


def snapshot(query: dict, source_of: dict[str, str]) -> dict:
    slots = sorted((_slot(s, source_of) for s in query.get("slots") or []), key=lambda s: (s["type"] or "", s["entity"], s["what"], s["term"] or ""))
    drops = []
    for line in query.get("explanation") or []:
        for pattern, code in _DROPS:
            found = pattern.search(line)
            if found:
                drops.append({"code": code, "term": found.group(1) if found.groups() else ""})
    return {
        "sources": sorted({s["source"] for s in slots if s["source"] and s["type"] != "DEFAULT_FILTER"}),
        "slots": slots,
        "groupBy": sorted(f"{(g.get('mapping') or {}).get('entity')}.{(g.get('mapping') or {}).get('column')}" for g in query.get("groupBy") or []),
        "unresolved": sorted(query.get("unresolved") or []),
        "unhandled": sorted(query.get("unhandled") or []),
        "leftToModel": sorted(m.get("token", "") for m in query.get("modelQualifiers") or []),
        "qualifierColumns": sorted(f"{c.get('token')}→{c.get('entity')}.{c.get('column')}" for c in query.get("qualifierColumns") or []),
        "drops": sorted(drops, key=lambda d: (d["code"], d["term"])),
        "shape": query.get("shape"), "grain": query.get("grain"), "limit": query.get("limit"),
        "ratio": bool(query.get("ratio")), "comparison": bool(query.get("comparison")),
        # dönemin tarihi her gün değişir; ilkel (THIS_YEAR, LAST_MONTH…) değişmez
        "temporal": sorted(t.get("primitive") or "" for t in query.get("temporal") or []),
        "clarification": bool(query.get("clarification")), "outOfScope": bool(query.get("outOfScope")),
        "state": query.get("state"),
    }


def _diff(old: dict, new: dict) -> list[str]:
    out = []
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        if a == b:
            continue
        if key == "slots":
            sig = lambda s: f"{s['term']}→{s['type']}:{s['source']}:{s['entity']}.{s['what']}{s['values'] or ''}{'/' + s['role'] if s['role'] else ''}"
            gone, came = sorted({sig(s) for s in a} - {sig(s) for s in b}), sorted({sig(s) for s in b} - {sig(s) for s in a})
            out += [f"slot −  {g}" for g in gone] + [f"slot +  {c}" for c in came]
        else:
            out.append(f"{key}: {json.dumps(a, ensure_ascii=False)} → {json.dumps(b, ensure_ascii=False)}")
    return out


def main() -> int:
    questions = Path(sys.argv[1])
    baseline = Path(_arg("--baseline", "tests/text2sql/resolver-baseline-set100.json"))
    url = _arg("--url", "http://127.0.0.1:8795").rstrip("/") + "/api/v1/semantic/resolve"
    token = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
    source_of = _sources()
    started, shots, state = time.time(), {}, {}
    cases = [json.loads(line) for line in questions.read_text(encoding="utf-8").splitlines() if line.strip()]
    for n, case in enumerate(cases, 1):
        req = urllib.request.Request(url, data=json.dumps({"question": case["soru"]}).encode(),
                                     headers={"X-Semantic-Caller": token, "Content-Type": "application/json"})
        query = json.load(urllib.request.urlopen(req, timeout=120))["query"]
        state = {"catalogHash": query.get("catalogHash"), "languagePoolHash": query.get("languagePoolHash"),
                 "catalogVersion": query.get("catalogVersion")}
        shots[case["id"]] = {"n": n, "soru": case["soru"], "kaynak": case.get("kaynak"), "read": snapshot(query, source_of)}
    for label, path in (("rules", _arg("--rules-dir")), ("prompt", _arg("--prompt-file"))):
        if path and Path(path).exists():
            p = Path(path)
            files = sorted(p.rglob("*.md")) if p.is_dir() else [p]
            state[label + "Hash"] = _sha("".join(f.read_text(encoding="utf-8") for f in files))
    took = round(time.time() - started, 1)

    if "--record" in sys.argv:
        baseline.write_text(json.dumps({"recordedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "state": state,
                                        "cases": shots}, ensure_ascii=False, indent=1), encoding="utf-8")
        def mismatch(label: str, read: list[str]) -> bool:
            crm = [x for x in read if x not in ("ANA", "?")]
            if label == "logo":
                return bool(crm)
            if label == "crm":
                return "ANA" in read
            return label == "ikisi" and not ("ANA" in read and crm)
        wrong = [f"Q{s['n']} {cid}: etiket {s['kaynak']}, okunan {s['read']['sources']}" for cid, s in shots.items()
                 if mismatch(s["kaynak"] or "", s["read"]["sources"])]
        print(f"temel çizgi yazıldı: {len(shots)} soru, {took} sn → {baseline}")
        print(f"durum: {state}")
        print(f"sorunun etiketiyle uyuşmayan kaynak okuması: {len(wrong)} (temel çizgi bunları DOĞRU saymaz, yalnız kaydeder)")
        for line in wrong:
            print("  ?", line)
        return 0

    recorded = json.loads(baseline.read_text(encoding="utf-8"))
    changed = 0
    for cid, shot in sorted(shots.items(), key=lambda kv: kv[1]["n"]):
        old = (recorded["cases"].get(cid) or {}).get("read")
        if old is None:
            print(f"Q{shot['n']} {cid}: temel çizgide yok")
            continue
        lines = _diff(old, shot["read"])
        if lines:
            changed += 1
            print(f"Q{shot['n']} {cid}: {shot['soru'][:90]}")
            for line in lines:
                print("     ", line)
    moved = {k: (recorded["state"].get(k), v) for k, v in state.items() if recorded["state"].get(k) != v}
    print(f"\n{len(shots)} soru, {took} sn · okuması değişen {changed} · temel çizgi {recorded.get('recordedAt')}")
    if moved:
        print("değişen durum:", json.dumps(moved, ensure_ascii=False))
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
