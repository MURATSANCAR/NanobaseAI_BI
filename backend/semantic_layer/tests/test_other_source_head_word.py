"""ZEKI-54: öteki sunucudaki sertifikalı kavramın baş kelimesi, plan kapalıyken modele bırakılmaz.

«dünkü satış tutarı kitap adı yazar»: çıplak «yazar» katalogda tanımsız (eş anlamlısı ödeme/hakediş sorularını
bozduğu için geri alındı), CRM'de ise «kitap yazarı» sertifikalı. İki sunuculu plan kapalıyken kelime A044 yoluna
düşüyor, model Logo'da cari adını (CLCARD.DEFINITION_) «yazar» diye yazıyor, kapı da geçiriyordu: sessizce yanlış
cevap. Kolon olarak istenen, hiçbir okumaya çözülmeyen ve öteki kaynaktaki sertifikalı bir kavramın baş kelimesi
olan kelime cevaptan çıkarılır ve kavramın adıyla söylenir. Plan açıkken, kelime bir okumaya çözüldüğünde ya da
ölçünün kaynağında da aynı başla sertifikalı bir kavram varsa eski yol (A044) aynen kalır.
"""

from __future__ import annotations

from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ColumnProfile, Mapping, SchemaProfile, SemanticType
from semantic_layer.normalize import fold
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify

CRM = "Timas_MSCRM.dbo"
TODAY = date(2026, 9, 30)
QUESTION = "dünkü satış tutarı kitap adı yazar"


def _person():
    return SchemaProfile(datasource_id=DS, table_name="PersonBase", table_pattern="PERSONBASE", entity="PERSONBASE",
                         schema_name=CRM, primary_key=["PersonId"], row_count=1000,
                         columns=[ColumnProfile("PersonId", "uniqueidentifier", is_primary_key=True),
                                  ColumnProfile("FullName", "nvarchar(200)"), ColumnProfile("Description", "nvarchar(200)")])


def _world(store, profiles, *, logo_head=False, logo_value=False, crm_value=False):
    person = _person()
    allp = list(profiles) + [person]
    for p in allp:
        store.upsert_profile(p)
    _certify(store, "satis tutari", SemanticType.METRIC,
             Mapping(concept_id="", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE", formula="SUM(STLINE.TOTAL)"))
    _certify(store, "kitap adi", SemanticType.COLUMN,
             Mapping(concept_id="", entity="ITEMS", table_pattern="LG_{n0}_ITEMS", column="NAME", operator="COLUMN"))
    # CRM'de sertifikalı kavram; çıplak «yazar» eş anlamlısı YOK (canlı katalogdaki gibi).
    _certify(store, "kitap yazarı", SemanticType.COLUMN,
             Mapping(concept_id="", entity="PERSONBASE", table_pattern="PERSONBASE", column="FULLNAME", operator="COLUMN"))
    if logo_head:
        # ölçünün kaynağında aynı başla sertifikalı kavram: kelime orada da okunabilir
        _certify(store, "stok yazarı", SemanticType.COLUMN,
                 Mapping(concept_id="", entity="ITEMS", table_pattern="LG_{n0}_ITEMS", column="SPECODE", operator="COLUMN"))
    if logo_value:
        # Logo cari grubu okuması (ödeme/hakediş sorularındaki gibi)
        _certify(store, "yazar", SemanticType.DIMENSION_VALUE,
                 Mapping(concept_id="", entity="CLCARD", table_pattern="LG_{n0}_CLCARD", column="SPECODE2", operator="IN",
                         values=["YAZARLAR"]))
    if crm_value:
        # CRM kişi kartı okuması (Description = 'Yazar ')
        _certify(store, "yazar", SemanticType.DIMENSION_VALUE,
                 Mapping(concept_id="", entity="PERSONBASE", table_pattern="PERSONBASE", column="DESCRIPTION", operator="IN",
                         values=["Yazar "]))
    EvidenceEngine(store, min_support=3).run(TENANT, DS, allp)
    return SemanticResolver(store, TENANT, DS, allp)


def _omitted(sq):
    return {fold(o["term"]): o["sentence"] for o in sq.omitted}


def test_with_plans_off_the_head_of_a_crm_concept_is_left_out_and_named(store, profiles, monkeypatch):
    monkeypatch.delenv("SEMANTIC_FEDERATED", raising=False)
    sq = _world(store, profiles).resolve(QUESTION, today=TODAY)
    omitted = _omitted(sq)
    assert "yazar" in omitted, (sq.omitted, sq.unresolved, sq.requested_breakdowns, sq.explanation)
    sentence = omitted["yazar"]
    assert "kitap yazari" in fold(sentence) and "CRM verisinde" in sentence and "eklenmedi" in sentence, sentence
    assert sentence in sq.explanation
    assert "yazar" not in [fold(w) for w in sq.unresolved], sq.unresolved
    assert "yazar" not in sq.requested_breakdowns and "yazar" not in sq.column_terms, (sq.requested_breakdowns, sq.column_terms)
    assert not any(p.get("word") == "yazar" for p in sq.breakdown_paths), sq.breakdown_paths
    # öteki taraf okunmaz; ölçü ve Logo kolonu yerinde
    assert "PERSONBASE" not in {s.mapping.entity for s in list(sq.slots) + list(sq.group_by) if s.mapping}, sq.explanation
    assert any(s.semantic_type == SemanticType.METRIC and s.mapping.entity == "STLINE" for s in sq.slots if s.mapping)


def test_inflected_forms_of_the_head_are_the_same_word(store, profiles, monkeypatch):
    monkeypatch.delenv("SEMANTIC_FEDERATED", raising=False)
    r = _world(store, profiles)
    for word in ("yazarı", "yazarlar"):
        sq = r.resolve(f"dünkü satış tutarı kitap adı {word}", today=TODAY)
        assert any(fold(o["term"]).startswith("yazar") for o in sq.omitted), (word, sq.omitted, sq.unresolved, sq.explanation)


def test_with_plans_on_the_word_stays_on_the_a044_path(store, profiles, monkeypatch):
    monkeypatch.setenv("SEMANTIC_FEDERATED", "1")
    sq = _world(store, profiles).resolve(QUESTION, today=TODAY)
    assert "yazar" in sq.unresolved and "yazar" in sq.requested_breakdowns, (sq.unresolved, sq.requested_breakdowns, sq.explanation)
    assert "yazar" in sq.column_terms, sq.column_terms
    assert "yazar" not in _omitted(sq), sq.omitted


def test_a_word_read_as_a_value_is_not_taken_out(store, profiles, monkeypatch):
    """«yazar» Logo'da bir DIMENSION_VALUE'ya (cari grubu) çözüldü: okuması var, kural devreye girmez."""
    monkeypatch.delenv("SEMANTIC_FEDERATED", raising=False)
    sq = _world(store, profiles, logo_value=True).resolve(QUESTION, today=TODAY)
    assert any(s.semantic_type == SemanticType.DIMENSION_VALUE and s.mapping and s.mapping.entity == "CLCARD" for s in sq.slots), \
        (sq.slots, sq.explanation)
    assert "yazar" not in _omitted(sq), sq.omitted


def test_a_column_word_the_source_rule_handed_over_is_still_taken_out(store, profiles, monkeypatch):
    """«yazar» CRM'de bir DIMENSION_VALUE'ya (etiket) çözüldü ve kaynak kuralı onu modele bıraktı — ama kelime kolon
    listesinde duruyor, orada süzgeç değil. Test sunucusunda (2026-09-30) model bu durumda müşteri adını yazar diye
    yazdı: kelime yine cevaptan çıkar ve söylenir."""
    monkeypatch.delenv("SEMANTIC_FEDERATED", raising=False)
    sq = _world(store, profiles, crm_value=True).resolve(QUESTION, today=TODAY)
    assert "yazar" in _omitted(sq), (sq.omitted, sq.unresolved, sq.explanation)
    assert "yazar" not in [fold(w) for w in sq.unresolved], (sq.unresolved, sq.explanation)


def test_a_head_also_certified_on_the_measures_side_is_left_to_the_model(store, profiles, monkeypatch):
    """Ölçünün kaynağında (Logo) da «… yazarı» sertifikalı: kelime orada okunabilir, A044 yolu aynen kalır."""
    monkeypatch.delenv("SEMANTIC_FEDERATED", raising=False)
    sq = _world(store, profiles, logo_head=True).resolve(QUESTION, today=TODAY)
    assert "yazar" not in _omitted(sq), sq.omitted
    assert "yazar" in sq.unresolved and "yazar" in sq.requested_breakdowns, (sq.unresolved, sq.requested_breakdowns, sq.explanation)
