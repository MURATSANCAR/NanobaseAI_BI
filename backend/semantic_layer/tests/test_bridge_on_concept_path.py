"""ZEKI-54: ölçülmüş bağ kavramın kendi yolunda.

Kitabın yazarı CRM'de kişi kartında (ContactBase), kitap kartından iki birleştirme ötede (eser katılımı üzerinden).
Logo'nun malzeme kodu CRM'in kitap kartına ölçülerek bağlandı (stok kodu). Çözümleyici bağı yalnız kavramın
eşlendiği tabloda arıyordu: kişi kartında bağ yok → «yazar» öteki tarafta sayılıp modele bırakılıyordu, model de
CRM'de olmayan kolon uyduruyordu. Kavram koşullarında ve beyan ettiği yolda adı geçen tablolardan biri ölçülmüş
bağla ölçünün tarafına ulaşıyorsa soru iki tarafı da okuyabilir; yolunu beyan etmeyen kavram eskisi gibi kalır.
"""

from __future__ import annotations

from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ColumnProfile, Mapping, SchemaProfile, SemanticType
from semantic_layer.normalize import fold
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify

CRM = "Crm.dbo"
TODAY = date(2026, 9, 30)
PATH = ("BOOKBASE.BOOKID = PARTBASE.BOOK; PARTBASE.PERSON = PERSONBASE.PERSONID; "
        "Logo: BOOKBASE.STOCKCODE = ITEMS.CODE")


def _p(name, cols, rels=(), pk=None):
    return SchemaProfile(datasource_id=DS, table_name=name, table_pattern=name.upper(), entity=name.upper(), schema_name=CRM,
                         columns=[ColumnProfile(c, t, is_primary_key=(c == pk)) for c, t in cols],
                         primary_key=[pk] if pk else [], row_count=1000, relationships=list(rels))


def _world(store, profiles, *, with_path: bool):
    items = next(p for p in profiles if p.entity == "ITEMS")
    items.relationships = list(items.relationships or []) + [{
        "column": "CODE", "ref_entity": "BOOKBASE", "ref_column": "StockCode", "ref_schema": CRM, "ref_pattern": "BOOKBASE",
        "source": "declared-join-key", "cross_source": True, "join_collate": True, "value_family": "code", "confidence": 0.98}]
    book = _p("BookBase", [("BookId", "uniqueidentifier"), ("StockCode", "nvarchar(50)"), ("statecode", "int")], pk="BookId")
    person = _p("PersonBase", [("PersonId", "uniqueidentifier"), ("FullName", "nvarchar(200)")], pk="PersonId")
    part = _p("PartBase", [("PartId", "uniqueidentifier"), ("Book", "uniqueidentifier"), ("Person", "uniqueidentifier"), ("statecode", "int")],
              rels=[{"column": "Book", "ref_entity": "BOOKBASE", "ref_column": "BookId"},
                    {"column": "Person", "ref_entity": "PERSONBASE", "ref_column": "PersonId"}], pk="PartId")
    allp = profiles + [book, person, part]
    for p in allp:
        store.upsert_profile(p)
    _certify(store, "satis tutari", SemanticType.METRIC,
             Mapping(concept_id="", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE", formula="SUM(STLINE.TOTAL)"))
    _certify(store, "kitap adi", SemanticType.COLUMN,
             Mapping(concept_id="", entity="ITEMS", table_pattern="LG_{n0}_ITEMS", column="NAME", operator="COLUMN"))
    extra = {"conditions": ["PARTBASE.STATECODE IN (0)", "BOOKBASE.STATECODE IN (0)"], "path": PATH} if with_path else {}
    _certify(store, "kitap yazari", SemanticType.COLUMN,
             Mapping(concept_id="", entity="PERSONBASE", table_pattern="PERSONBASE", column="FULLNAME", operator="COLUMN", extra=extra),
             synonyms=["yazar"])
    EvidenceEngine(store, min_support=3).run(TENANT, DS, allp)
    return allp


def _author(sq):
    return next((s for s in list(sq.slots) + list(sq.group_by) if s.mapping and s.mapping.entity == "PERSONBASE"), None)


def test_mapping_tables_are_the_concepts_own_path_on_its_own_source(store, profiles):
    allp = _world(store, profiles, with_path=True)
    r = SemanticResolver(store, TENANT, DS, allp)
    m = Mapping(concept_id="", entity="PERSONBASE", table_pattern="PERSONBASE", column="FULLNAME", operator="COLUMN",
                extra={"conditions": ["PARTBASE.STATECODE IN (0)"], "path": PATH})
    assert r._mapping_tables(m) == {"PARTBASE", "BOOKBASE"}          # ITEMS (öteki kaynak) sayılmaz
    assert r._mapping_tables(Mapping(concept_id="", entity="PERSONBASE", table_pattern="PERSONBASE", column="FULLNAME")) == set()


def test_with_plans_on_an_author_whose_path_reaches_the_measured_bridge_is_read(store, profiles, monkeypatch):
    monkeypatch.setenv("SEMANTIC_FEDERATED", "1")
    allp = _world(store, profiles, with_path=True)
    sq = SemanticResolver(store, TENANT, DS, allp).resolve("dünkü satış tutarı kitap adı yazar", today=TODAY)
    assert _author(sq) is not None, (sq.unresolved, sq.explanation)
    assert "yazar" not in [fold(u) for u in sq.unresolved], sq.explanation


def test_without_a_declared_path_the_author_is_still_the_other_sides_word(store, profiles, monkeypatch):
    """Yolunu beyan etmeyen kavram için davranış değişmez: bağ kişi kartında değil, kelime ölçünün tarafında okunmaz."""
    monkeypatch.setenv("SEMANTIC_FEDERATED", "1")
    allp = _world(store, profiles, with_path=False)
    sq = SemanticResolver(store, TENANT, DS, allp).resolve("dünkü satış tutarı kitap adı yazar", today=TODAY)
    assert _author(sq) is None, sq.explanation


def test_with_plans_off_the_author_is_left_out_and_said(store, profiles, monkeypatch):
    """Müşteri VM'i: iki sunuculu plan kapalı. Bağ olsa da tek soruda iki sunucu okunmaz; yazar cevaba alınmaz ve söylenir."""
    monkeypatch.delenv("SEMANTIC_FEDERATED", raising=False)
    allp = _world(store, profiles, with_path=True)
    sq = SemanticResolver(store, TENANT, DS, allp).resolve("dünkü satış tutarı kitap adı yazar", today=TODAY)
    assert _author(sq) is None, sq.explanation
    assert any(fold(o["term"]) == "yazar" for o in sq.omitted), (sq.omitted, sq.unresolved, sq.explanation)
