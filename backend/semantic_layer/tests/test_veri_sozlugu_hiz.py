"""Veri sözlüğü hızı (2026-09-29): eksik açıklama listesi, kalıp ayrıntısı ve envanter eski hesapla birebir aynı.

Eski hesap (aşağıda olduğu gibi korunmuş): liste bütün envanteri kolon sözlükleriyle kuruyor, kalıbı birleştirip
sayıyordu. Yeni hesap kolon durumlarını doğrudan profillerden sayar ve katalog işaretlerini (açıklama, öneri,
terim eşlemesi) katalog sürümü başına bir kez okur. Terim listesi terim damgasına bağlı hatırlanır; damga her terim
ya da eşleme yazımıyla değişir.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Any, Optional

import pytest

from semantic_layer.candidates.llm_client import FakeLlm
from semantic_layer.data_source import CRM, LOGO, data_source
from semantic_layer.models import Annotation, ConceptStatus, Evidence, EvidenceType, Mapping, SemanticType
from semantic_layer.naming import label_context
from semantic_layer.tests.conftest import DS, TENANT


# ------------------------------------------------------------------ eski hesap (2026-09-29 öncesi, birebir)


def _old_inventory(rt, *, with_columns: bool = True) -> dict[str, Any]:
    from semantic_bridge.app import _table_scope

    s = rt.settings
    anns = rt.store.list_annotations(s.datasource_id)
    suggested = {(x["tablePattern"], (x["column"] or "").upper() or None): x for x in rt.store.list_suggestions(s.datasource_id)}
    by_key: dict = {}
    for a in anns:
        by_key.setdefault((a.table_pattern, (a.column or "").upper() or None), []).append(a)
    concepts_by_col: dict = {}
    live = [c for c in rt.store.find_concepts(s.tenant_id, s.datasource_id, limit=100000) if c.status not in (ConceptStatus.REJECTED,)]
    maps = rt.store.list_mappings_many([c.id for c in live])
    for c in live:
        for m in maps.get(c.id, []):
            if m.column:
                concepts_by_col.setdefault((m.entity, m.column.upper()), []).append({"id": c.id, "term": c.term, "type": c.semantic_type, "status": c.status, "operator": m.operator, "values": m.values, "confidence": round(c.confidence, 2)})
            elif m.formula:
                for ref in re.findall(r"\b([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\b", m.formula):
                    concepts_by_col.setdefault((ref[0], ref[1]), []).append({"id": c.id, "term": c.term, "type": c.semantic_type, "status": c.status, "formula": m.formula, "confidence": round(c.confidence, 2)})
    wanted = list(rt.profiles)
    scopes: dict[str, int] = {}
    for prof in rt.profiles:
        code = _table_scope(prof.table_name)[0]
        if code:
            scopes[code] = scopes.get(code, 0) + 1
    wanted.sort(key=lambda p: (-(p.row_count or 0), p.entity))
    total = len(wanted)
    tables = []
    undefined_cols = 0
    for p in wanted:
        cols = []
        for c in p.columns:
            cons = concepts_by_col.get((p.entity, c.name.upper()), [])
            col_anns = [{"id": a.id, "text": a.text, "author": a.author, "createdAt": a.created_at.isoformat()} for a in by_key.get((p.table_pattern, c.name.upper()), [])]
            defined = bool(c.description) or bool(col_anns) or any(x["status"] == ConceptStatus.CERTIFIED for x in cons)
            if not defined:
                undefined_cols += 1
            cols.append({
                "name": c.name, "type": c.data_type, "nullable": c.nullable, "isPrimaryKey": c.is_primary_key,
                "ref": f"{c.ref_entity}.{c.ref_column}" if c.ref_entity else None,
                "sensitive": c.sensitive, "sensitivityReason": c.sensitivity_reason,
                "sentinelValues": list(c.sentinel_values),
                "distinct": c.distinct_count, "topValues": [] if c.sensitive else [[v, n] for v, n in c.top_values[:12]],
                "description": c.description, "derived": list(c.derived), "unit": c.unit,
                "suggestion": suggested.get((p.table_pattern, c.name.upper())),
                "annotations": col_anns, "concepts": cons,
                "status": "CERTIFIED" if any(x["status"] == ConceptStatus.CERTIFIED for x in cons) else ("CANDIDATE" if cons else ("DESCRIBED" if defined else "UNDEFINED")),
            })
        scope_code, scope_sub = _table_scope(p.table_name)
        tables.append({
            "entity": p.entity, "tableName": p.table_name, "tablePattern": p.table_pattern, "schema": p.schema_name,
            "scope": scope_code or None, "scopeSub": scope_sub or None,
            "context": label_context(p.context, s.pattern_labels),
            "description": p.description, "rowCount": p.row_count, "primaryKey": p.primary_key, "relationships": p.relationships,
            "annotations": [{"id": a.id, "text": a.text, "author": a.author, "createdAt": a.created_at.isoformat()} for a in by_key.get((p.table_pattern, None), [])],
            "columns": cols if with_columns else [],
            "columnCount": len(cols),
            "certifiedColumns": sum(1 for c in cols if c["status"] == "CERTIFIED"),
            "undefinedColumns": sum(1 for c in cols if c["status"] == "UNDEFINED"),
            "scannedAt": p.scanned_at.isoformat(),
        })
    return {"datasourceId": s.datasource_id, "tables": tables, "tableCount": len(tables), "total": total,
            "scopes": [{"code": c, "tables": n} for c, n in sorted(scopes.items(), key=lambda kv: kv[0])],
            "columnCount": sum(t["columnCount"] for t in tables), "undefinedColumns": undefined_cols,
            "catalog": rt.store.status_counts(s.tenant_id, s.datasource_id), "version": rt.store.latest_version(s.tenant_id, s.datasource_id)}


def _old_merged(tables):
    rank = {"CERTIFIED": 3, "CANDIDATE": 2, "DESCRIBED": 1, "UNDEFINED": 0}
    out: dict = {}
    for t in tables:
        for c in t.get("columns") or []:
            k = c["name"].upper()
            cur = out.get(k)
            if cur is None or rank.get(c["status"], 0) > rank.get(cur["status"], 0):
                out[k] = c
            elif not cur.get("topValues") and c.get("topValues"):
                out[k] = {**cur, "topValues": c["topValues"]}
    return list(out.values())


def _old_gaps(rt) -> dict[str, Any]:
    inv = _old_inventory(rt)
    groups: dict = {}
    for t in inv["tables"]:
        groups.setdefault(t.get("tablePattern") or t["tableName"], []).append(t)
    items = []
    total_cols = undefined_cols = 0
    for pattern, tables in groups.items():
        tables.sort(key=lambda t: -(t.get("rowCount") or 0))
        rep = tables[0]
        cols = _old_merged(tables)
        missing = [c for c in cols if c["status"] == "UNDEFINED"]
        table_desc = rep.get("description") or ((rep.get("annotations") or [{}])[-1].get("text") if rep.get("annotations") else None)
        rows = sum(t.get("rowCount") or 0 for t in tables)
        total_cols += len(cols)
        undefined_cols += len(missing)
        items.append({
            "tablePattern": pattern, "example": rep["tableName"], "copies": len(tables),
            "source": data_source(rep.get("schema")),
            "description": table_desc, "tableMissing": not table_desc, "rows": rows,
            "columns": len(cols), "missing": len(missing),
            "suggestions": sum(1 for c in missing if c.get("suggestion")),
        })
    items.sort(key=lambda x: (x["rows"] == 0, -(x["missing"] + (1 if x["tableMissing"] else 0) > 0), -x["rows"], x["example"]))
    with_gaps = [x for x in items if x["missing"] or x["tableMissing"]]
    return {
        "summary": {"patterns": len(items), "patternsWithGaps": len(with_gaps),
                    "tablesWithoutDescription": sum(1 for x in items if x["tableMissing"]),
                    "columns": total_cols, "missingColumns": undefined_cols,
                    "suggestions": sum(x["suggestions"] for x in items),
                    "bySource": {src: sum(1 for x in items if x["source"] == src) for src in (LOGO, CRM)}},
        "items": items,
    }


def _old_gap_detail(rt, table_pattern: str) -> Optional[dict[str, Any]]:
    inv = _old_inventory(rt)
    tables = [t for t in inv["tables"] if (t.get("tablePattern") or t["tableName"]) == table_pattern]
    if not tables:
        return None
    tables.sort(key=lambda t: -(t.get("rowCount") or 0))
    rep = tables[0]
    cols = _old_merged(tables)

    def view(c):
        said = (c.get("annotations") or [])
        return {"name": c["name"], "type": c.get("type"), "status": c["status"], "isPrimaryKey": c.get("isPrimaryKey"),
                "ref": c.get("ref"), "sensitive": c.get("sensitive"), "distinct": c.get("distinct"),
                "topValues": c.get("topValues") or [], "unit": c.get("unit"), "derived": c.get("derived") or [],
                "description": said[-1]["text"] if said else c.get("description"),
                "annotationId": said[-1]["id"] if said else None,
                "suggestion": c.get("suggestion")}
    table_ann = rep.get("annotations") or []
    return {
        "tablePattern": table_pattern, "example": rep["tableName"], "source": data_source(rep.get("schema")),
        "tables": [{"name": t["tableName"], "rows": t.get("rowCount") or 0, "context": t.get("context")} for t in tables],
        "description": table_ann[-1]["text"] if table_ann else rep.get("description"),
        "tableAnnotationId": table_ann[-1]["id"] if table_ann else None,
        "rows": sum(t.get("rowCount") or 0 for t in tables),
        "scannedAt": max((t.get("scannedAt") or "" for t in tables), default="") or None,
        "primaryKey": rep.get("primaryKey"),
        "missing": [view(c) for c in cols if c["status"] == "UNDEFINED"],
        "described": [view(c) for c in cols if c["status"] != "UNDEFINED"],
    }


# ------------------------------------------------------------------ düzen


def _certify(store, term, stype, mapping):
    c, _ = store.upsert_concept(TENANT, DS, term, stype, mapping=mapping, status=ConceptStatus.CANDIDATE)
    store.add_evidence(Evidence(c.id, EvidenceType.VALIDATED_SQL, "hm", support_count=3, payload={"pairs": ["a", "b", "c"], "precision": 1.0}))
    return c


@pytest.fixture
def rich(store, profiles):
    """Kopyalı kalıplar (aynı kalıp, farklı yıl/satır), kaynak ve portal açıklaması, öneri, sertifikalı ve aday terim,
    formül eşlemesi, satırsız tablo."""
    for p in profiles:
        store.upsert_profile(p)
    inv = next(p for p in profiles if p.entity == "INVOICE")
    stl = next(p for p in profiles if p.entity == "STLINE")
    cl = next(p for p in profiles if p.entity == "CLCARD")
    # iki eski yıl kopyası: biri daha dolu (temsilci değişir), biri boş; birinde kolon açıklaması var
    old = dataclasses.replace(inv, table_name=inv.table_name.replace("411", "211"), row_count=(inv.row_count or 0) + 50,
                              columns=[dataclasses.replace(c, description=("fatura türü" if c.name == "TRCODE" else c.description),
                                                           top_values=[]) for c in inv.columns])
    empty = dataclasses.replace(stl, table_name=stl.table_name.replace("411", "311"), row_count=0)
    store.upsert_profile(old)
    store.upsert_profile(empty)
    store.add_annotation(Annotation(datasource_id=DS, table_pattern=cl.table_pattern, column=None, text="cari kartı", author="portal"))
    store.add_annotation(Annotation(datasource_id=DS, table_pattern=cl.table_pattern, column="CITY", text="şehir", author="portal"))
    store.add_suggestion(DS, stl.table_pattern, "AMOUNT", "miktar", confidence=0.7, model="m")
    store.add_suggestion(DS, inv.table_pattern, "NETTOTAL", "net tutar", confidence=0.7, model="m")
    c1 = _certify(store, "toptan", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, column="TRCODE", operator="IN", values=["8"]))
    store.update_concept(c1.id, status=ConceptStatus.CERTIFIED)
    _certify(store, "adet", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern=stl.table_pattern, formula="SUM(STLINE.AMOUNT)"))
    _certify(store, "iptal", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="STLINE", table_pattern=stl.table_pattern, column="CANCELLED", operator="=", values=["1"]))
    return store


def _runtime(store, logo_connector, settings):
    from semantic_bridge.app import Runtime

    return Runtime(settings, store=store, connector=logo_connector, llm=FakeLlm([""]))


Z = {"cookie": "timas_session=z"}


def _client(monkeypatch, rt):
    """Yönetici oturumu (veri sözlüğü uçları yöneticiye açık)."""
    from fastapi.testclient import TestClient

    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import create_app

    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: "zekiai" if cookie == Z["cookie"] else None)
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": "zekiai", "displayName": "Z"} if cookie == Z["cookie"] else None)
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    monkeypatch.delenv("SEMANTIC_ADMIN_TOKEN", raising=False)
    return TestClient(create_app(rt))


def test_liste_ayrinti_ve_envanter_eski_hesapla_ayni(rich, logo_connector, settings):
    rt = _runtime(rich, logo_connector, settings)
    assert len({p.table_pattern for p in rt.profiles}) < len(rt.profiles), "kopyalı kalıp kurulmadı"
    old = _old_gaps(rt)
    assert rt.gaps() == old
    assert old["summary"]["suggestions"] >= 1 and old["summary"]["missingColumns"] > 0
    for item in old["items"]:
        assert rt.gap_detail(item["tablePattern"]) == _old_gap_detail(rt, item["tablePattern"]), item["tablePattern"]
    assert rt.gap_detail("YOK_BOYLE_KALIP") is None
    assert rt.inventory() == _old_inventory(rt)
    assert rt.inventory(with_columns=False) == _old_inventory(rt, with_columns=False)


def test_liste_hatirlanir_ve_yazinca_duser(rich, logo_connector, settings, profiles):
    rt = _runtime(rich, logo_connector, settings)
    first, ran = rt.gaps_with_queries()
    assert ran, "listeyi üreten katalog okumaları sorgu bilgisi için saklanır"
    assert rt.gaps_with_queries()[0] is first, "aynı katalogda yeniden kurulmaz"
    cl = next(p for p in rt.profiles if p.entity == "CLCARD")
    assert "CODE" in [c["name"].upper() for c in rt.gap_detail(cl.table_pattern)["missing"]]
    rt.add_annotation(cl.table_pattern, "CODE", "cari kodu", "portal")   # portal yazımı listeyi düşürür
    after = rt.gaps()
    assert after is not first and after == _old_gaps(rt)
    assert "CODE" not in [c["name"].upper() for c in rt.gap_detail(cl.table_pattern)["missing"]]


def test_uc_cevaplari_ve_sorgu_bilgisi(rich, logo_connector, settings, monkeypatch):
    from semantic_bridge import provenance as PV

    rt = _runtime(rich, logo_connector, settings)
    client = _client(monkeypatch, rt)
    for _ in range(2):                                    # ilk: hesap, ikinci: hatırlanan — cevap ve sorgu bilgisi aynı
        body = client.get("/api/v1/schema/gaps", headers=Z).json()
        assert {k: v for k, v in body.items() if k != "kaynaklar"} == _old_gaps(rt)
        k = body["kaynaklar"]
        assert not k.get("error") and any("sl_concept" in (s.get("sql") or "") for s in k["sources"].values())
        assert not PV.uncovered_numbers(body)
    pattern = body["items"][0]["tablePattern"]
    detail = client.get("/api/v1/schema/gaps/detail", params={"tablePattern": pattern}, headers=Z).json()
    assert {k: v for k, v in detail.items() if k != "kaynaklar"} == _old_gap_detail(rt, pattern)
    assert not detail["kaynaklar"].get("error") and not PV.uncovered_numbers(detail)


def test_terim_listesi_damgaya_bagli_hatirlanir(rich, logo_connector, settings, monkeypatch):
    from semantic_bridge import provenance as PV
    from semantic_layer.data_source import source_by_entity

    rt = _runtime(rich, logo_connector, settings)
    client = _client(monkeypatch, rt)

    def old(status):
        rows = rt.store.find_concepts(TENANT, DS, status=status, limit=5000)
        src = source_by_entity(rt.profiles)
        maps = rt.store.list_mappings_many([c.id for c in rows])
        return {"items": [{"concept": c.to_dict(), "mappings": [{**m.to_dict(), "source": src.get(m.entity)} for m in maps.get(c.id, [])]} for c in rows]}

    url = "/api/v1/semantic/concepts?status=CERTIFIED&limit=5000"
    a = client.get(url, headers=Z).json()
    assert {k: v for k, v in a.items() if k != "kaynaklar"} == old("CERTIFIED") and len(a["items"]) == 1
    assert not a["kaynaklar"].get("error") and not PV.uncovered_numbers(a)
    b = client.get(url, headers=Z).json()
    assert {k: v for k, v in b.items() if k != "kaynaklar"} == {k: v for k, v in a.items() if k != "kaynaklar"}
    assert [x.get("sql") for x in b["kaynaklar"]["sources"].values()] == [x.get("sql") for x in a["kaynaklar"]["sources"].values()], \
        "damga değişmedi: hatırlanan cevap, onu üreten okumayla"
    # bir terim sertifikalanınca damga değişir, liste yeniden okunur
    cand = next(c for c in rt.store.find_concepts(TENANT, DS, status=ConceptStatus.CANDIDATE, limit=100))
    rt.store.update_concept(cand.id, status=ConceptStatus.CERTIFIED)
    c = client.get(url, headers=Z).json()
    assert {k: v for k, v in c.items() if k != "kaynaklar"} == old("CERTIFIED") and len(c["items"]) == 2
    # eşleme değişikliği de (terimi dokunarak) damgayı değiştirir
    stamp = rt.store.concept_stamp(TENANT, DS)
    m = rt.store.list_mappings(cand.id)[0]
    rt.store.replace_mappings(cand.id, [dataclasses.replace(m, values=["2"])])
    assert rt.store.concept_stamp(TENANT, DS) != stamp
    d = client.get(url, headers=Z).json()
    assert {k: v for k, v in d.items() if k != "kaynaklar"} == old("CERTIFIED")
