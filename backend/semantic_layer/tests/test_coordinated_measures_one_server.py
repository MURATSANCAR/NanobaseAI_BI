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


def test_with_plans_off_a_column_listed_among_columns_on_the_other_server_is_omitted_and_said(catalog, profiles, monkeypatch):
    """ZEKI-54 (a): "… kanal kitap yazarı …" — sütunların arasında sayılan, yalnız CRM'de olan kolon modele
    bırakılmaz (model onu bir süzgece çeviriyordu); cevap Logo'dan, kolon eklenmeden ve adıyla söylenerek."""
    monkeypatch.delenv("SEMANTIC_FEDERATED", raising=False)
    sq = _two_server_world(catalog, profiles).resolve("2026 satılan adet kanal kitap yazarı", today=TODAY)
    assert "NEW_KITAPBASE" not in {s.mapping.entity for s in list(sq.slots) + list(sq.group_by) if s.mapping}, sq.explanation
    assert not any("yazar" in fold(str(w)) for w in sq.unresolved), sq.unresolved
    sentences = {fold(o["term"]): o["sentence"] for o in sq.omitted}
    assert "kitap yazari" in sentences, sq.omitted
    assert "CRM verisinde" in sentences["kitap yazari"] and "eklenmedi" in sentences["kitap yazari"], sentences


def test_a_word_beside_the_measure_keeps_its_old_reading(catalog, profiles, monkeypatch):
    """Ölçünün yanında ("satılan adet ve kitap yazarı") kelime kolon listesinde değil: eski okuma (modele yorum)."""
    monkeypatch.delenv("SEMANTIC_FEDERATED", raising=False)
    sq = _two_server_world(catalog, profiles).resolve("2026 satılan adet ve kitap yazarı", today=TODAY)
    assert "kitap yazari" in sq.unresolved and not sq.omitted, (sq.unresolved, sq.omitted)


def test_an_unplaced_word_listed_as_a_column_takes_the_a044_path_with_plans_on_or_off(catalog, profiles, monkeypatch):
    """Katalogda hiç karşılığı olmayan "yazar" kolon sırasında ("kanal yazar") istendi. Öteki sunucuda da tanımlı
    değil, yani söylenecek bir "öteki sunucu" yok: A044 yolu (2026-09-29) — kelime fiil biçimi yüzünden grameri
    sayılıp atılmaz, tanımsız terim olarak modele kalır, istenen kırılımdır ve kapı onu kolon olarak tutar.
    Plan kapalı da açık da aynı; cevaptan çıkarma (omitted) yalnız öteki sunucuda sertifikalı terim içindir."""
    r = _sales_world(catalog, profiles)
    for plans in ("0", "1"):
        monkeypatch.setenv("SEMANTIC_FEDERATED", plans)
        sq = r.resolve("2026 satılan adet kanal yazar", today=TODAY)
        assert "yazar" in sq.unresolved and "yazar" not in sq.ignored, (plans, sq.unresolved, sq.ignored)
        assert "yazar" in sq.requested_breakdowns and "yazar" in sq.column_terms, (plans, sq.requested_breakdowns, sq.column_terms)
        assert not sq.omitted, (plans, sq.omitted)


def test_the_gate_refuses_a_column_the_model_turned_into_a_filter():
    """ZEKI-54 (b): kolon olarak istenen terimin yorumu, sorgunun satırları sabit bir değere daralttığı kolona
    iniyorsa cevap reddedilir; aynı kolon yalnız gösteriliyorsa reddedilmez."""
    from semantic_layer.history.sql_facts import parse_sql
    from semantic_layer.runtime.audit import _columns_turned_into_filters
    sq = SemanticQuery(question="dünkü satış adedi kanal kitap adı yazar", tenant_id=TENANT, datasource_id=DS)
    sq.column_terms = ["yazar"]
    filtered = ("-- yorum: 'yazar' → CLCARD.SPECODE = 'YAZARLAR' filtresi\n"
                "SELECT cl.SPECODE AS yazar, SUM(s.AMOUNT) AS adet FROM STLINE s JOIN CLCARD cl ON cl.LOGICALREF = s.CLIENTREF "
                "WHERE cl.SPECODE = 'YAZARLAR' GROUP BY cl.SPECODE")
    found = _columns_turned_into_filters(sq, filtered, parse_sql(filtered))
    assert found and found[0].kind == "column_filter" and "yazar" in found[0].text, found
    shown = ("-- yorum: 'yazar' → CLCARD.SPECODE kolonu\n"
             "SELECT cl.SPECODE AS yazar, SUM(s.AMOUNT) AS adet FROM STLINE s JOIN CLCARD cl ON cl.LOGICALREF = s.CLIENTREF "
             "WHERE s.TRCODE IN (7, 8) GROUP BY cl.SPECODE")
    assert _columns_turned_into_filters(sq, shown, parse_sql(shown)) == []
    sq.column_terms = []
    assert _columns_turned_into_filters(sq, filtered, parse_sql(filtered)) == []


def test_one_fault_one_reason_a_breakdown_made_a_filter_is_not_also_refused_as_ungrouped():
    """Kırılım olarak istenen kelime süzgece çevrilip hiçbir şeye gruplanmadıysa tek gerekçe: kolon süzgece çevrildi
    (onarım ipucu gruplamayı da söyler). Süzgeç yoksa A044'ün "hiçbir şeye göre gruplamıyor" gerekçesi aynen kalır."""
    from semantic_layer.runtime.audit import gate_report
    sq = SemanticQuery(question="satış adedi yazar bazında", tenant_id=TENANT, datasource_id=DS)
    sq.requested_breakdowns, sq.column_terms, sq.unresolved = ["yazar"], ["yazar"], ["yazar"]
    filtered = ("-- yorum: 'yazar' → CLCARD.SPECODE = 'YAZARLAR' filtresi\n"
                "SELECT SUM(s.AMOUNT) AS adet FROM STLINE s JOIN CLCARD cl ON cl.LOGICALREF = s.CLIENTREF "
                "WHERE cl.SPECODE = 'YAZARLAR'")
    kinds = [u.kind for u in gate_report(sq, filtered)]
    assert "column_filter" in kinds and "grain" not in kinds, kinds
    plain = ("-- yorum: 'yazar' → karşılığı yok\n"
             "SELECT SUM(s.AMOUNT) AS adet FROM STLINE s WHERE s.TRCODE IN (7, 8)")
    kinds = [u.kind for u in gate_report(sq, plain)]
    assert "grain" in kinds and "column_filter" not in kinds, kinds


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
