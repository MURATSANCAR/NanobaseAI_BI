"""Ay kolonu gruplarını katalogda beyan eder (`extra.month_columns`) — tam kapı 2026-09-29, sınıf K13 (B072 / Q65).

Sorun: bazı tablolar bir kaydın 12 ay değerini 12 ayrı kolonda tutar (CRM satış hedefi: new_ocak … new_aralik). «Ay
bazında», «hiç girilmemiş aylar» sorusunda 12 kolonun satıra açılması modele kalıyordu ve her denemede başka yazıldı.
Beyan edilen grubun açılımını derleyici yazar (`semantic_layer.runtime.month_groups.expand`): model tablonun takma
adıyla `ay`, `ay_adi`, `ay_degeri` sanal kolonlarını kullanır; kapı eksik/yanlış el açılımını onarıma yollar.

Adaylar profilden (`month_groups.detect`): aynı ad kalıbında ay adıyla (new_ocak…new_aralik, A_Ocak…) ya da dönem
sözlü önek + 1…12 sonekiyle (AY1…AY12, «1»…«12») tam 12 kolon, her ay bir kolon, hepsi sayısal. Sıra listeleri
(DOCTYPE1…12, GROUPS1…12) önek dönem sözü olmadığı ya da 13+ kardeşi olduğu için elenir; kuru koşu elenenleri de basar.

«Girilmemiş ay» okuması VERİDEN (`--olc` olmadan da ölçülür; ölçülemeyen grup yazılmaz):
  en az bir ayı dolu kayıtlarda boş ay NULL mı 0 mı?
    - NULL hiç yoksa (boş ay 0 olarak durur, NULL yalnız hiç doldurulmamış kayıtta) → `null_or_zero`
    - 0 hiç yoksa → `null_or_zero` (ikisi aynı küme)
    - ikisi birden varsa → `null_only` (0 girilmiş bir değerdir, boş değildir)

Beyanın yeri: tablonun sertifikalı ENTITY kavramının eşlemesi; yoksa tablonun ilk sertifikalı kavram eşlemesi (beyan tablo
düzeyindedir, eşlemenin okunuşunu değiştirmez). Tabloya hiçbir sertifikalı kavram bağlı değilse yazılmaz (yer yok).

  kuru koşu (varsayılan)   adayları, elenenleri, ölçümü ve yazılacak yeri basar; yazmaz.
  --json YOL               yazılacak beyanları JSON'a yazar (yan köprüde SEMANTIC_MONTH_GROUPS_FILE ile bellekte denemek için).
  --only ad,ad / --exclude ad,ad   tablo adı, varlık ya da kalıp (büyük/küçük harf fark etmez) — yanlış aday elenir.
  --apply                  beyanı yazar (idempotent), kanıt notu, human_certify, semantic_audit («ZEKİ AI»).

Koşu (sunucuda, köprünün ortamıyla):

    sudo systemd-run --pipe --wait --collect -p User=administrator \\
      -p EnvironmentFile=/etc/nanobase/semantic-bridge.env \\
      -E PYTHONPATH=/data/nanobaseai/bi/frontend/backend \\
      /data/nanobaseai/bi/semantic-venv/bin/python - [--json /tmp/ay.json] [--exclude …] [--apply] < betik.py

Sonra: köprü kataloğu 60 sn içinde tazeler (ay grupları profillere dağıtılır) → resolver-gate (okuma değişmez) →
answer-gate --only Q65,Q69 --repeat 3 → tam kapı.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

for p in ("/data/nanobaseai/bi/frontend/backend", os.environ.get("PYTHONPATH", "")):   # PYTHONPATH en önde
    if p:
        while p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)

WHO = "operator:claude (tam kapı 2026-09-29, K13 ay kolonu grupları)"
SRC = "operator:2026-09-29:ay-kolonu-gruplari"
CRM_FILE = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")


def _open():
    from semantic_layer.catalog import one_entity_per_pattern
    from semantic_layer.config import SemanticSettings
    from semantic_layer.store.catalog_store import open_store
    s = SemanticSettings.from_env()
    st = open_store(s.store_dsn, create=False)
    profiles = one_entity_per_pattern(st.list_profiles(s.datasource_id), st.concept_entities(s.tenant_id, s.datasource_id))
    return s, st, profiles


def _home(st, s, prof):
    """Beyanın yazılacağı (kavram, eşleme): sertifikalı ENTITY önce, sonra tablonun ilk sertifikalı eşlemesi."""
    from semantic_layer.models import SemanticType
    index = st.certified_index(s.tenant_id, s.datasource_id)
    want_p, want_e = (prof.table_pattern or "").upper(), (prof.entity or "").upper()
    hits = []
    seen = set()
    for senses in index.values():
        for c, maps in senses:
            if c.id in seen:
                continue
            for m in maps:
                if (m.table_pattern or "").upper() == want_p or (m.entity or "").upper() == want_e:
                    seen.add(c.id)
                    hits.append((0 if c.semantic_type == SemanticType.ENTITY else 1, c.term, c, m))
                    break
    hits.sort(key=lambda x: (x[0], x[1]))
    return (hits[0][2], hits[0][3]) if hits else (None, None)


def _physical(prof) -> str:
    schema = prof.schema_name or "dbo"
    return f"{schema}.[{prof.table_name}]"


def _measure(prof, cols: dict[int, str]) -> dict:
    """Doldurulmuş kayıtlarda boş ay NULL mı 0 mı — salt okuma, canlı kaynak (CRM .28 ya da Logo .25)."""
    from semantic_layer.profiler.connectors import connector_from_file
    crm = "MSCRM" in (prof.schema_name or "").upper()
    conn = connector_from_file(CRM_FILE if crm else os.environ["SEMANTIC_CONNECTION_FILE"])
    c = [f"[{cols[n]}]" for n in range(1, 13)]
    filled = " OR ".join(f"({x} IS NOT NULL AND {x} <> 0)" for x in c)
    allnull = " AND ".join(f"{x} IS NULL" for x in c)
    nulls = " + ".join(f"CASE WHEN {x} IS NULL THEN 1 ELSE 0 END" for x in c)
    zeros = " + ".join(f"CASE WHEN {x} = 0 THEN 1 ELSE 0 END" for x in c)
    active = " AND statecode = 0" if prof.column("statecode") is not None else ""
    sql = (f"SELECT COUNT(*) AS satir, SUM(CASE WHEN {allnull} THEN 1 ELSE 0 END) AS hic_doldurulmamis, "
           f"SUM(CASE WHEN {filled} THEN 1 ELSE 0 END) AS dolu_kayit, "
           f"SUM(CASE WHEN {filled} THEN {nulls} ELSE 0 END) AS dolu_kayitta_null_ay, "
           f"SUM(CASE WHEN {filled} THEN {zeros} ELSE 0 END) AS dolu_kayitta_sifir_ay "
           f"FROM {_physical(prof)} WHERE 1 = 1{active}")
    _, rows, *_ = conn.execute(sql, 5)
    r = {k: int(v or 0) for k, v in (rows[0] if rows else {}).items()}
    if not r.get("dolu_kayit"):
        r["karar"], r["gerekce"] = None, "dolu kayıt yok — karar verilemez"
    elif r["dolu_kayitta_null_ay"] == 0:
        r["karar"], r["gerekce"] = "null_or_zero", "dolu kayıtlarda boş ay 0 olarak duruyor; NULL yalnız hiç doldurulmamış kayıtta"
    elif r["dolu_kayitta_sifir_ay"] == 0:
        r["karar"], r["gerekce"] = "null_or_zero", "dolu kayıtlarda boş ay NULL; 0 hiç yok (iki okuma aynı küme)"
    else:
        r["karar"], r["gerekce"] = "null_only", "dolu kayıtlarda hem NULL hem 0 var: 0 girilmiş değer, boş ay NULL"
    r["kaynak"] = "CRM" if crm else "Logo"
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--exclude", default="")
    a = ap.parse_args()
    from semantic_layer.runtime import month_groups

    names = lambda x: {w.strip().upper() for w in x.split(",") if w.strip()}  # noqa: E731
    only, exclude = names(a.only), names(a.exclude)
    s, st, profiles = _open()
    picked, dropped, seen = [], [], set()
    for prof in profiles:
        found, lost = month_groups.detect(prof)
        dropped += lost
        for g in found:
            key = ((prof.table_pattern or "").upper(), g["key"])
            if key in seen:
                continue
            seen.add(key)
            ids = {prof.table_name.upper(), (prof.entity or "").upper(), (prof.table_pattern or "").upper()}
            if (only and not ids & only) or ids & exclude:
                dropped.append({**g, "why": "--only/--exclude ile elendi"})
                continue
            picked.append((prof, g))

    print(f"katalog: {s.tenant_id}/{s.datasource_id} · profil {len(profiles)} · aday {len(picked)} · elenen {len(dropped)}")
    out = []
    for prof, g in picked:
        cols = {int(k): v for k, v in g["month_columns"].items()}
        concept, mapping = _home(st, s, prof)
        try:
            m = _measure(prof, cols)
        except Exception as e:  # noqa: BLE001
            m = {"karar": None, "gerekce": f"ölçülemedi: {str(e)[:160]}"}
        where = f"{concept.id} '{concept.term}' ({concept.semantic_type})" if concept else "YOK — tabloya sertifikalı kavram bağlı değil"
        print(f"  ADAY  {prof.entity} ({prof.table_name}, kalıp {prof.table_pattern}) [{g['kind']}] {g['types']}\n"
              f"        ay → kolon: {', '.join(f'{n}={cols[n]}' for n in range(1, 13))}\n"
              f"        ölçüm: {json.dumps({k: v for k, v in m.items() if k not in ('karar', 'gerekce')}, ensure_ascii=False)}\n"
              f"        girilmemiş ay: {m.get('karar')} — {m.get('gerekce')}\n"
              f"        beyanın yeri: {where}")
        if concept is None or not m.get("karar"):
            print("        → YAZILMAZ" + (" (yer yok)" if concept is None else " (karar yok)"))
            continue
        out.append({"entity": prof.entity, "table_pattern": prof.table_pattern, "table_name": prof.table_name,
                    "month_columns": {str(n): cols[n] for n in range(1, 13)}, "month_missing": m["karar"],
                    "measured": {k: v for k, v in m.items() if k not in ("karar",)},
                    "concept": concept.id, "mapping": mapping.id})
    shown: set[tuple] = set()
    for d in dropped:
        k = (d["entity"], d["key"], d["why"])
        if k in shown:                      # yıl/firma kopyaları aynı gerekçeyle bir kez
            continue
        shown.add(k)
        print(f"  elendi: {d['entity']} ({d['table_name']}) grup '{d['key']}' [{d['kind']}]: {d['why']}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"groups": out}, f, ensure_ascii=False, indent=1)
        print(f"JSON: {a.json} ({len(out)} beyan)")
    if not a.apply:
        print(f"KURU KOŞU — yazılmadı ({len(out)} beyan yazılacak). Yanlış aday varsa --exclude ile çıkarın, sonra --apply.")
        return 0

    from semantic_layer.evidence.engine import EvidenceEngine
    from semantic_layer.models import ConceptStatus, Evidence, EvidenceType
    for g in out:
        c = st.get_concept(g["concept"])
        extra_new = {"month_columns": g["month_columns"], "month_missing": g["month_missing"]}
        maps = st.list_mappings(c.id)
        new = [dataclasses.replace(x, extra={**(x.extra or {}), **extra_new}) if x.id == g["mapping"] else x for x in maps]
        if any(x.id == g["mapping"] and all((x.extra or {}).get(k) == v for k, v in extra_new.items()) for x in maps):
            print("ZATEN YAZILI:", c.id, g["entity"])
            continue
        st.replace_mappings(c.id, new)
        why = (f"{g['entity']} 12 ay kolonu tek ay boyutudur ({g['month_columns']['1']} … {g['month_columns']['12']}); açılımı "
               f"derleyici yazar. Girilmemiş ay: {g['month_missing']} — {g['measured'].get('gerekce')} "
               f"(ölçüm: {json.dumps({k: v for k, v in g['measured'].items() if k != 'gerekce'}, ensure_ascii=False)})")
        st.add_evidence(Evidence(c.id, EvidenceType.HUMAN_ANNOTATION, SRC, support_count=1, weight=1.0,
                                 payload={"snippet": why, "by": WHO}))
        c = st.get_concept(c.id)
        if c.status != ConceptStatus.CERTIFIED or not (c.explain or {}).get("human_certified_by"):
            EvidenceEngine(st).human_certify(c.id, WHO, reason=why)
        print("YAZILDI:", c.id, c.term, g["entity"], g["month_missing"])
    try:
        from semantic_bridge import admin

        admin.audit(st.engine, "ZEKİ AI", "update", "catalog_concept", s.datasource_id,
                    f"ay kolonu grupları beyan edildi ({len(out)})",
                    {"groups": [{k: g[k] for k in ("entity", "concept", "month_missing")} for g in out], "rule": "K13 month_columns"})
    except Exception as e:  # noqa: BLE001
        print("UYARI: değişiklik kaydı yazılamadı:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
