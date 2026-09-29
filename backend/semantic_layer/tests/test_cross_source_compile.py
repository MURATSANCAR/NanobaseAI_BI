"""Ölçülmüş bir veritabanları arası bağ.

Test ilk yazıldığında (2026-09-16, 3d2818f7) iki veritabanı tek T-SQL'de birleştiriliyordu ve üç şey
sessizce bozuluyordu: metinde saklı sayı ile tamsayı anahtar karşılaştırması (dönüştürme hatası), iki
farklı harmanlamanın karşılaştırılması (SQL Server reddeder) ve yıl kopyalı hedefe yalnız bir yılın
bağlanması. Aynı gün CRM ayrı sunucuya taşındı (kullanıcı kararı: ayrı datasource, tek SQL'de
cross-join yok) ve 2026-09-18'den beri (7921ae0a) deterministik derleyici iki veritabanına yayılan
soruyu tek ifade olarak yazmaz — yazdığında öteki yarıyı yok sayıp daha dar bir soruyu cevaplıyordu;
iş iki sunuculu plana kalır. Burada sınanan: bu ret, ve bağın nasıl karşılaştırılacağının (TRY_CAST,
COLLATE, hedefin dönem anlamı) katalogdan doğru okunması — modele giden not da bundan yazılır.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ColumnProfile, Mapping, SchemaProfile, SemanticType, TemporalSlot, utcnow
from semantic_layer.conventions import Conventions
from semantic_layer.runtime.compiler import DeterministicCompiler, Dialect
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.normalize import fold
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify

OTHER_DB = "OtherDb.dbo"


def _world(store, profiles):
    inv = next(p for p in profiles if p.entity == "INVOICE")
    old_inv = deepcopy(inv)
    old_inv.table_name, old_inv.context, old_inv.scanned_at = "LG_211_01_INVOICE", {"n0": "211", "n1": "01"}, utcnow()
    old_inv.time_window = ("2021-01-01", "2025-12-31")
    inv.time_window = ("2026-01-01", "2026-12-31")
    old_card = deepcopy(next(p for p in profiles if p.entity == "CLCARD"))
    old_card.table_name, old_card.context, old_card.scanned_at = "LG_211_CLCARD", {"n0": "211"}, utcnow()
    ship = SchemaProfile(
        datasource_id=DS, table_name="ShipmentBase", table_pattern="SHIPMENTBASE", entity="SHIPMENTBASE", schema_name=OTHER_DB,
        columns=[ColumnProfile("ShipmentId", "uniqueidentifier", is_primary_key=True), ColumnProfile("invoice_no", "nvarchar(100)"),
                 ColumnProfile("createdon", "datetime"), ColumnProfile("qty", "int")],
        primary_key=["ShipmentId"], row_count=1000, time_window=("2019-01-01", "2026-09-01"),
        relationships=[{"column": "invoice_no", "ref_entity": "INVOICE", "ref_column": "FICHENO", "source": "cross-source-overlap",
                        "join_cast": None, "join_collate": True, "period_semantics": "periodic"}])
    acc = SchemaProfile(
        datasource_id=DS, table_name="AccountBase", table_pattern="ACCOUNTBASE", entity="ACCOUNTBASE", schema_name=OTHER_DB,
        columns=[ColumnProfile("AccountId", "uniqueidentifier", is_primary_key=True), ColumnProfile("erp_ref", "nvarchar(100)"),
                 ColumnProfile("creditlimit", "money")],
        primary_key=["AccountId"], row_count=100,
        relationships=[{"column": "erp_ref", "ref_entity": "CLCARD", "ref_column": "LOGICALREF", "source": "cross-source-overlap",
                        "join_cast": "int", "join_collate": False, "period_semantics": "replicated"}])
    allp = profiles + [old_inv, old_card, ship, acc]
    for p in allp:
        store.upsert_profile(p)
    _certify(store, "sevkiyat adedi", SemanticType.METRIC, Mapping(concept_id="", entity="SHIPMENTBASE", table_pattern="SHIPMENTBASE", formula="SUM(SHIPMENTBASE.qty)"))
    _certify(store, "fatura turu", SemanticType.COLUMN, Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE", column="TRCODE", operator="COLUMN"))
    _certify(store, "kredi limiti", SemanticType.METRIC, Mapping(concept_id="", entity="ACCOUNTBASE", table_pattern="ACCOUNTBASE", formula="SUM(ACCOUNTBASE.creditlimit)"))
    _certify(store, "kanal", SemanticType.COLUMN, Mapping(concept_id="", entity="CLCARD", table_pattern="LG_{n0}_CLCARD", column="SPECODE2", operator="COLUMN"))
    EvidenceEngine(store, min_support=3).run(TENANT, DS, allp)
    return allp


TWO_SERVERS = "question names things on two servers"


def test_a_reference_into_period_tables_is_not_written_as_one_statement_across_databases(store, profiles, monkeypatch):
    """Sevkiyat öteki veritabanında, fatura türü Logo'nun dönem tablolarında: tek ifade yazılmaz."""
    monkeypatch.setenv("SEMANTIC_FEDERATED", "1")        # iki sunuculu plan açık: öteki yarı plana kalır
    allp = _world(store, profiles)
    r = SemanticResolver(store, TENANT, DS, allp)
    c = DeterministicCompiler(allp, {}, "tsql")
    sq = r.resolve("fatura turu bazında sevkiyat adedi", today=date(2026, 7, 20))
    sq.temporal = [TemporalSlot(text="2025-2026", primitive="RANGE", start=date(2025, 1, 1), end=date(2027, 1, 1))]
    assert c.plan(sq) == (None, TWO_SERVERS), (c.plan(sq), sq.explanation)
    assert c.compile(sq, store) is None


def test_a_breakdown_read_from_the_other_database_is_not_written_as_one_statement(store, profiles, monkeypatch):
    """Kredi limiti öteki veritabanında, kanal Logo'nun cari kartında: öteki yarı düşürülüp tek
    kaynaklı (daha dar) bir cevap yazılmaz."""
    monkeypatch.setenv("SEMANTIC_FEDERATED", "1")
    allp = _world(store, profiles)
    r = SemanticResolver(store, TENANT, DS, allp)
    c = DeterministicCompiler(allp, {}, "tsql")
    sq = r.resolve("kanal bazında kredi limiti", today=date(2026, 7, 20))
    assert c.plan(sq) == (None, TWO_SERVERS), (c.plan(sq), sq.explanation)
    assert c.compile(sq, store) is None


def test_with_plans_off_the_other_half_is_answered_without_it_and_said(store, profiles, monkeypatch):
    """ZEKI-54: iki sunuculu plan kapalıyken öteki veritabanındaki kırılım ("kanal bazında") modele BIRAKILMAZ —
    model onu bir süzgece çeviriyordu. Soru ölçünün veritabanından cevaplanır, kırılım cevaba alınmaz ve bu,
    terimin adıyla düz bir cümlede söylenir. İki sunucuyu okuyan tek ifade hiç istenmez."""
    monkeypatch.delenv("SEMANTIC_FEDERATED", raising=False)
    allp = _world(store, profiles)
    r = SemanticResolver(store, TENANT, DS, allp)
    sq = r.resolve("kanal bazında kredi limiti", today=date(2026, 7, 20))
    assert "CLCARD" not in {s.mapping.entity for s in list(sq.slots) + list(sq.group_by) if s.mapping}, sq.explanation
    assert "kanal" not in sq.unresolved, (sq.unresolved, sq.explanation)
    omitted = {fold(o["term"]): o["sentence"] for o in sq.omitted}
    assert "kanal" in omitted and "iki ayrı sunucu" in omitted["kanal"] and "eklenmedi" in omitted["kanal"], sq.omitted
    assert omitted["kanal"] in sq.explanation


def test_a_measured_link_is_compared_with_its_cast_collation_and_period_meaning(store, profiles):
    """Metinde saklı tamsayı TRY_CAST ile, farklı harmanlama COLLATE ile karşılaştırılır; hedefin dönem
    anlamı (her dönem ayrı anahtar mı, kopya mı) bağla birlikte taşınır."""
    hints = Conventions.from_profiles(_world(store, profiles)).join_hints
    ship = hints[("SHIPMENTBASE", "INVOICE_NO", "INVOICE", "FICHENO")]
    acc = hints[("ACCOUNTBASE", "ERP_REF", "CLCARD", "LOGICALREF")]
    d = Dialect("tsql")
    assert d.join_on("SHIPMENTBASE.[INVOICE_NO]", "INVOICE.[FICHENO]", ship) == "SHIPMENTBASE.[INVOICE_NO] COLLATE DATABASE_DEFAULT = INVOICE.[FICHENO]"
    assert d.join_on("ACCOUNTBASE.[ERP_REF]", "CLCARD.[LOGICALREF]", acc) == "TRY_CAST(ACCOUNTBASE.[ERP_REF] AS int) = CLCARD.[LOGICALREF]"
    assert ship["period_semantics"] == "periodic" and acc["period_semantics"] == "replicated"
    assert Dialect("sqlite").join_on("A.x", "B.y", ship) == "A.x = B.y"      # harmanlama yalnız SQL Server'da


def test_the_model_is_told_how_to_compare_a_measured_link():
    from semantic_layer.runtime.compiler import _join_note
    note = _join_note({"column": "erp_ref", "join_cast": "int", "join_collate": True, "period_semantics": "periodic"})
    assert "TRY_CAST(erp_ref AS int)" in note and "COLLATE DATABASE_DEFAULT" in note and "dönem" in note
    assert _join_note({"column": "x"}) == ""
