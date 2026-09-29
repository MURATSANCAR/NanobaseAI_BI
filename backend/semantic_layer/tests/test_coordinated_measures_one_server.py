"""ZEKI-47 ve ZEKI-54 (müşteri Jira, 2026-09-29).

ZEKI-47 — "2025 eylül ayı toplam satış tutarı ve adedi nedir?" tek kolon (tutar) döndü; sıra çevrilince ("satış
adedi ve tutarı") yalnız adet. Türkçe ortak özneyi ikinci baş sözcükte yazmaz; tek başına "adedi"/"tutarı" hiçbir
şeye eşleşmiyor ve sessizce düşüyordu. İkinci baş, birincinin öznesiyle okunur ve YANINA eklenir.

ZEKI-54 — planlı rapor ara ara "Logo ve CRM artik ayri sunucularda" ile düştü. İki sunuculu plan kapalıyken
çözümleyici öteki veritabanındaki kelimeyi (plan okuyabilsin diye) tutuyor, derleyici modele iki veritabanını
birden gösterip tek ifade istiyordu; model bazen ikisini birleştiren (hiçbir sunucunun koşamayacağı) ifade yazdı.
Plan kapalıyken o kelime ölçünün tarafında modele bırakılır; iki tarafta ölçü kalırsa derleyici kesin reddeder.
"""
from __future__ import annotations

from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ColumnProfile, Mapping, ResolvedSlot, SchemaProfile, SemanticQuery, SemanticType
from semantic_layer.normalize import fold, normalize_term
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify, catalog  # noqa: F401

TODAY = date(2026, 9, 29)
STL = "LG_{n0}_{n1}_STLINE"


def _sales_world(catalog, profiles):
    # Satır seviyeli "satış tutarı" — canlıdaki sem_b62a0c853395'in (LINENET, INVOICEREF≠0) karşılığı. Test
    # fikstürünün STLINE profilinde LINENET/INVOICEREF kolonu yok; o kolonlarla yazılınca fiziksel eşleme
    # geçersiz sayılıp kavram hiç sertifikalanmıyor, katalogda yalnız fatura seviyeli anlam kalıyordu. Burada
    # fikstürün taşıdığı kolonlarla yazılır (anlam aynı: satır tutarı, satış türleri).
    _certify(catalog, "satış tutarı", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern=STL,
             formula="SUM(CASE WHEN STLINE.TRCODE IN (7, 8) THEN STLINE.TOTAL ELSE 0 END)",
             extra={"func": "SUM", "conditions": ["STLINE.LINETYPE IN (0)"]}), synonyms=["satış"])
    _certify(catalog, "kargo tutarı", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern=STL,
             formula="SUM(STLINE.TOTAL)", extra={"func": "SUM"}))
    # "satilan adet" (STLINE.AMOUNT, eş anlamlı "adet") ortak test kataloğunda zaten sertifikalı.
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    return SemanticResolver(catalog, TENANT, DS, profiles)


def _metrics(sq):
    return sorted(fold((s.explain or {}).get("canonical") or s.term) for s in sq.slots if s.semantic_type == SemanticType.METRIC)


def test_amount_and_then_quantity_are_both_answered(catalog, profiles):
    sq = _sales_world(catalog, profiles).resolve("2025 eylül ayı toplam satış tutarı ve adedi nedir?", today=TODAY)
    assert _metrics(sq) == ["satilan adet", "satis tutari"], (_metrics(sq), sq.explanation)
    assert not sq.clarification, sq.clarification


def test_quantity_and_then_amount_are_both_answered(catalog, profiles):
    r = _sales_world(catalog, profiles)
    senses = catalog.certified_index(TENANT, DS).get(normalize_term("satış tutarı")) or []
    assert any(m.entity == "STLINE" for _, maps in senses for m in maps), "satır seviyeli satış tutarı sertifikalı olmalı"
    sq = r.resolve("2025 eylül ayı toplam satış adedi ve tutarı nedir?", today=TODAY)
    assert _metrics(sq) == ["satilan adet", "satis tutari"], (_metrics(sq), sq.explanation)
    assert not sq.clarification, sq.clarification
    # ikinci ölçü birincinin tablosundaki anlamıyla okunur (satırdaki tutar, fatura başlığı değil)
    amount = next(s for s in sq.slots if fold((s.explain or {}).get("canonical") or "") == "satis tutari")
    assert amount.mapping.entity == "STLINE", amount.mapping


def test_a_second_head_the_catalog_cannot_place_is_asked_back_not_dropped(catalog, profiles):
    sq = _sales_world(catalog, profiles).resolve("2026 kargo tutarı ve adedi", today=TODAY)
    assert sq.clarification and any("kargo adedi" in c for c in sq.clarification), (sq.clarification, sq.explanation)


def _crm_book():
    return SchemaProfile(datasource_id=DS, table_name="new_kitapBase", table_pattern="NEW_KITAPBASE", entity="NEW_KITAPBASE",
                         schema_name="Timas_MSCRM.dbo", description="Kitap",
                         columns=[ColumnProfile(name="new_kitapId", data_type="uniqueidentifier"),
                                  ColumnProfile(name="new_yazaradi", data_type="nvarchar(200)"),
                                  ColumnProfile(name="new_hedef", data_type="money")],
                         row_count=5000)


def _two_server_world(catalog, profiles):
    crm = _crm_book()
    catalog.upsert_profile(crm)
    _certify(catalog, "kitap yazarı", SemanticType.COLUMN, Mapping(concept_id="", entity="NEW_KITAPBASE",
             table_pattern="NEW_KITAPBASE", column="NEW_YAZARADI", operator="COLUMN"))
    allp = list(profiles) + [crm]
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, allp)
    return SemanticResolver(catalog, TENANT, DS, allp)


def test_with_plans_off_a_phrase_on_the_other_server_is_read_on_the_measures_side(catalog, profiles, monkeypatch):
    monkeypatch.delenv("SEMANTIC_FEDERATED", raising=False)
    sq = _two_server_world(catalog, profiles).resolve("2026 satılan adet ve kitap yazarı", today=TODAY)
    assert "NEW_KITAPBASE" not in {s.mapping.entity for s in sq.slots if s.mapping}, sq.explanation
    assert "kitap yazari" in sq.unresolved, (sq.unresolved, sq.explanation)
    assert any("iki sunuculu sorgu kapalı" in e for e in sq.explanation), sq.explanation


def test_with_plans_on_the_same_phrase_stays_for_the_plan(catalog, profiles, monkeypatch):
    monkeypatch.setenv("SEMANTIC_FEDERATED", "1")
    sq = _two_server_world(catalog, profiles).resolve("2026 satılan adet ve kitap yazarı", today=TODAY)
    assert "NEW_KITAPBASE" in {s.mapping.entity for s in sq.slots if s.mapping}, sq.explanation


def test_measures_on_two_servers_are_refused_before_any_model_call_when_plans_are_off(profiles, monkeypatch):
    from semantic_layer.runtime.compiler import ExistingCompiler
    crm = _crm_book()
    c = ExistingCompiler.__new__(ExistingCompiler)
    c.by_entity = {p.entity: p for p in list(profiles) + [crm]}
    q = SemanticQuery(question="2026 satılan adet ve kitap hedefi", tenant_id=TENANT, datasource_id=DS)
    q.slots = [
        ResolvedSlot(term="satılan adet", semantic_type=SemanticType.METRIC, status="CERTIFIED",
                     mapping=Mapping(concept_id="", entity="STLINE", table_pattern=STL, formula="SUM(STLINE.AMOUNT)")),
        ResolvedSlot(term="kitap hedefi", semantic_type=SemanticType.METRIC, status="CERTIFIED",
                     mapping=Mapping(concept_id="", entity="NEW_KITAPBASE", table_pattern="NEW_KITAPBASE",
                                     formula="SUM(NEW_KITAPBASE.NEW_HEDEF)")),
    ]
    q.sources = ["", "TIMAS_MSCRM"]
    monkeypatch.delenv("SEMANTIC_FEDERATED", raising=False)
    msg = c._unrunnable_on_one_server(q)
    assert msg and "iki ayrı sunucu" in msg and "'satılan adet'" in msg and "'kitap hedefi'" in msg, msg
    monkeypatch.setenv("SEMANTIC_FEDERATED", "1")
    assert c._unrunnable_on_one_server(q) is None
    q.sources = [""]
    monkeypatch.delenv("SEMANTIC_FEDERATED", raising=False)
    assert c._unrunnable_on_one_server(q) is None
