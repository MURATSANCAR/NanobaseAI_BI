"""Seyrek ölçü kolonlarının kapsamı — VERİ NOTU beyanı, canlı ölçümden (2026-09-30, A044 sınıfı; soruya özel değil).

Neden: bir sertifikalı ölçü, kayıtların çok azında dolu bir kolonu topluyorsa cevabın sayısı yalnız o kayıtların toplamıdır
(CRM «crm etkinlik kartı gideri» = new_ToplamEtkinlikGideri: 57.000 etkinliğin 28'inde dolu). Kişi bunu cevabın
altında okumalı. Köprü (`column_facts.predicate_column_notes`) «VERİ NOTU:» ile başlayan kolon açıklamasını o kolonu
TOPLAYAN (SUM/AVG) ya da ona koşul/kırılım dayandıran her cevabın `dataNotes` alanına ve özetine taşır; model istemi
de tablonun kolon listesinde görür. Beyan yazılmamışsa köprü yalnız profilden «taramada boş görüldü, kapsam sınırlı»
der — kaç kayıt, hangi dönem bilgisi beyandan gelir.

Metin elle yazılmaz: bu betik sertifikalı METRIC kavramlarını gezer, formülün topladığı kolonlardan profil örneğinde
çoğunlukla boş görüneni (bütün kopyalarda null oranı ≥ PROFILE_HINT) aday alır, kaynağında ölçer (salt okuma):
ölçünün kendi koşullarıyla toplam kayıt, kolonun dolu (NULL değil, 0 değil) olduğu kayıt, dolu kayıtların toplamı ve
tarih aralığı (iş tarihi kolonu; yoksa kayıt oluşturma tarihi — notta hangisi olduğu yazar). Dolu pay SPARSE_SHARE'in
altındaysa beyan metni bu sayılardan kurulur.

Yalnız tek fiziksel tablolu (yıl kopyası olmayan) kalıplar ölçülür; yıl kopyalı Logo tabloları listede «atlandı»
diye görünür (her kopya ayrı ölçülmeli, ayrı iş).

Kullanım (sunucuda, köprünün ortamıyla):
    sudo systemd-run --pipe --wait --collect -p User=administrator \\
      -p EnvironmentFile=/etc/nanobase/semantic-bridge.env \\
      -E PYTHONPATH=/data/nanobaseai/bi/frontend/backend \\
      /data/nanobaseai/bi/semantic-venv/bin/python - [--apply] < 2026-09-30-seyrek-olcu-kapsami.py

  kuru koşu (varsayılan)  adayları, ölçümü ve yazılacak metni basar; hiçbir şey yazmaz.
  --apply                 beyanı `sl_schema_annotation`'a yazar (idempotent: aynı metin varsa yazmaz; eski VERİ NOTU'nu
                          yeni kayıt geçer — köprü en yeni açıklamayı okur). Köprü açıklamaları açılışta ve katalog
                          yenilemede okur.

Ortam: SEMANTIC_CONNECTION_FILE (Logo), SEMANTIC_CRM_CONNECTION_FILE (varsayılan
/data/nanobaseai/bi/secrets/crm-mssql-connection.json).
"""
from __future__ import annotations

import argparse
import os
import re
import sys

for p in ("/data/nanobaseai/bi/frontend/backend", os.environ.get("PYTHONPATH", "")):   # PYTHONPATH en önde
    if p:
        while p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)

WHO = "operator:claude (seyrek ölçü kapsamı, canlı ölçüm 2026-09-30)"
PROFILE_HINT = 0.9     # profil örneğinde en az bu oranda boş: ölçmeye değer aday
SPARSE_SHARE = 0.10    # canlı ölçümde dolu pay bunun altındaysa beyan yazılır
MARK = "VERİ NOTU:"


def _open():
    from semantic_layer.catalog import one_entity_per_pattern
    from semantic_layer.config import SemanticSettings
    from semantic_layer.store.catalog_store import open_store
    s = SemanticSettings.from_env()
    st = open_store(s.store_dsn, create=False)
    all_profiles = st.list_profiles(s.datasource_id)
    profiles = one_entity_per_pattern(all_profiles, st.concept_entities(s.tenant_id, s.datasource_id))
    return s, st, profiles


def _connector(schema_name: str, cache: dict):
    from semantic_layer.profiler.connectors import connector_from_file
    from semantic_layer.runtime.crm_active import is_crm_database
    crm = is_crm_database((schema_name or "").split(".")[0])
    key = "crm" if crm else "logo"
    if key not in cache:
        path = (os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
                if crm else os.environ["SEMANTIC_CONNECTION_FILE"])
        cache[key] = connector_from_file(path)      # CRM: etkin kayıt süzgeci bağlantıda (crm_active)
    return cache[key]


def _fmt(n) -> str:
    try:
        v = float(n)
    except (TypeError, ValueError):
        return str(n)
    s = f"{v:,.2f}" if abs(v - round(v)) > 1e-9 else f"{int(round(v)):,}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _day(v) -> str:
    return str(v or "")[:10]


def _candidates(st, s, profiles):
    """(concept, mapping, profile, column) — formülün topladığı, profilde bütün kopyalarda çoğunlukla boş kolon."""
    index = st.certified_index(s.tenant_id, s.datasource_id)
    by_entity: dict[str, list] = {}
    for p in profiles:
        by_entity.setdefault(p.entity.upper(), []).append(p)
    seen, out, skipped = set(), [], []
    for _, senses in index.items():
        for c, maps in senses:
            if c.semantic_type != "METRIC" or c.id in seen:
                continue
            seen.add(c.id)
            for m in maps:
                refs = {(e.upper(), col.upper()) for e, col in re.findall(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b", m.formula or "")}
                for e, col in sorted(refs):
                    copies = [p for p in by_entity.get(e, []) if p.column(col) is not None]
                    ratios = [p.column(col).null_ratio for p in copies if p.column(col).null_ratio is not None]
                    if not copies or not ratios or min(ratios) < PROFILE_HINT:
                        continue
                    if len(copies) > 1 or "{" in copies[0].table_pattern:
                        skipped.append((c.term, f"{e}.{col}", f"{len(copies)} kopya / kalıp {copies[0].table_pattern}"))
                        continue
                    out.append((c, m, copies[0], copies[0].column(col).name))
    return out, skipped


def _measure(conn, prof, column: str, mapping, conventions) -> dict:
    """Ölçünün kendi koşullarıyla (eşlemenin `conditions`'ı) toplam / dolu kayıt, dolu kayıtların toplamı ve tarih aralığı."""
    table = f"{prof.schema_name}.{prof.table_name}" if prof.schema_name else prof.table_name
    ent = prof.entity
    conds = []
    for cnd in (mapping.extra or {}).get("conditions") or []:
        conds.append(re.sub(rf"\b{re.escape(ent)}\.", "T.", cnd, flags=re.I))
    where = " AND ".join(conds) or "1 = 1"
    tcol = conventions.time_column(ent) or next((c.name for c in prof.columns if c.name.lower() == "createdon"), None)
    basis = "kayıt oluşturma tarihi" if (tcol or "").lower() in ("createdon", "created_on") else "iş tarihi"
    period = (f", MIN(CASE WHEN T.{column} IS NOT NULL AND T.{column} <> 0 THEN T.{tcol} END) AS ilk, "
              f"MAX(CASE WHEN T.{column} IS NOT NULL AND T.{column} <> 0 THEN T.{tcol} END) AS son") if tcol else ""
    sql = (f"SELECT COUNT(*) AS toplam, SUM(CASE WHEN T.{column} IS NOT NULL AND T.{column} <> 0 THEN 1 ELSE 0 END) AS dolu, "
           f"SUM(T.{column}) AS tutar{period} FROM {table} T WHERE {where}")
    row = dict(conn.execute(sql, 1)[1][0])
    row["_sql"], row["_basis"], row["_tcol"] = sql, basis, tcol
    return row


def _text(term: str, m: dict) -> str:
    when = (f"; dolu kayıtlar {_day(m.get('ilk'))} – {_day(m.get('son'))} arasında ({m['_basis']})"
            if m.get("ilk") and m.get("son") else "")
    return (f"{MARK} Bu alan {_fmt(m['toplam'])} kaydın yalnız {_fmt(m['dolu'])} tanesinde dolu{when}; dolu kayıtların "
            f"toplamı {_fmt(m['tutar'])}. '{term}' ölçüsü yalnız bu kayıtları kapsar, alanın boş olduğu kayıtlar ölçüye girmez "
            f"(canlı ölçüm, {WHO.split('ölçüm ')[-1].rstrip(')')}).")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    from semantic_layer.conventions import Conventions
    from semantic_layer.models import Annotation
    s, st, profiles = _open()
    conventions = Conventions.from_profiles(profiles)
    cands, skipped = _candidates(st, s, profiles)
    print(f"datasource: {s.datasource_id} | aday ölçü kolonu: {len(cands)} | yıl kopyalı, atlanan: {len(skipped)}")
    for term, ref, why in skipped:
        print(f"  atlandı: '{term}' {ref} ({why})")
    conns: dict = {}
    todo = []
    for c, m, prof, col in cands:
        try:
            got = _measure(_connector(prof.schema_name, conns), prof, col, m, conventions)
        except Exception as e:  # noqa: BLE001
            print(f"- '{c.term}' {prof.entity}.{col}: ölçülemedi: {str(e)[:200]}")
            continue
        total, filled = int(got.get("toplam") or 0), int(got.get("dolu") or 0)
        share = filled / total if total else 0.0
        print(f"- '{c.term}' {prof.entity}.{col}: {filled}/{total} dolu (%{share * 100:.3f}), tutar {got.get('tutar')}, "
              f"{got.get('_tcol') or '-'} {_day(got.get('ilk'))} – {_day(got.get('son'))}")
        print(f"    sorgu: {got['_sql']}")
        if not total or share >= SPARSE_SHARE:
            print("    seyrek değil — beyan yok")
            continue
        text = _text(c.term, got)
        existing = [x for x in st.list_annotations(s.datasource_id, prof.table_pattern) if (x.column or "").upper() == col.upper()]
        for x in existing:
            print(f"    MEVCUT açıklama: {x.id} {x.author} | {x.text[:160]}")
        if any(x.text == text for x in existing):
            print("    aynı beyan zaten var — yazılmaz")
            continue
        print(f"    YAZILACAK ({prof.table_pattern}.{col}): {text}")
        todo.append(Annotation(datasource_id=s.datasource_id, table_pattern=prof.table_pattern, column=col, text=text, author=WHO))
    if not a.apply:
        print(f"KURU KOŞU — {len(todo)} beyan yazılacaktı, hiçbir şey yazılmadı. Yazmak için --apply.")
        return 0
    for ann in todo:
        st.add_annotation(ann)
        print("yazıldı:", ann.table_pattern, ann.column, ann.id)
    print("Köprü açıklamaları açılışta / katalog yenilemede okur.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
