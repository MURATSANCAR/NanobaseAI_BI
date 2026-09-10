"""Bir aday, insana sorulmadan önce çürütülmeye çalışılmalı.

Motorun tamamı bir terime inanmak için sebep arar: sorgu kullanmış, belge anmış, veri uyuyor. Hiçbir
yeri inanmamak için sebep aramaz. Bu asimetri, onay kuyruğunu bir dakikalık kontrolle elenecek
iddialarla doldurdu — "mal alım" ORFICHE'yi gösteriyordu, oysa kaynağın o koda verdiği ad *Alınan
Sipariş*: işin tam öbür tarafı.

Buradaki testler çürütmenin iki yönünü de tutuyor: yanlışı yakalaması, ve doğruyu rahat bırakması.
İkincisi daha zor — bugün ilk yazdığım hâli 928 adayın 812'sini çürütüyordu.
"""

from __future__ import annotations

from semantic_layer.evidence.refute import Refuter
from semantic_layer.models import (ColumnProfile, ConceptStatus, Evidence, EvidenceType, Mapping,
                                   SchemaProfile, SemanticType)

TENANT, DS = "t1", "logo"

FATURA_TURU = ("Fatura türü (1=Mal alım faturası, 2=Perakende satış iade faturası, "
               "3=Toptan satış iade faturası, 4=Alınan hizmet faturası, 7=Perakende satış faturası, "
               "8=Toptan satış faturası)")
SIPARIS_TURU = "Fiş türü (1=Alınan Sipariş, 2=Verilen Sipariş)"


def _p(entity: str, col: str, desc: str, rel: list | None = None) -> SchemaProfile:
    return SchemaProfile(datasource_id=DS, table_name=f"LG_411_01_{entity}",
                         table_pattern="LG_{n0}_{n1}_" + entity, entity=entity, schema_name="dbo",
                         row_count=1000, relationships=rel or [],
                         columns=[ColumnProfile(name=col, data_type="int", distinct_count=8,
                                                description=desc,
                                                top_values=[("1", 10), ("4", 10), ("8", 10)])])


def _claim(store, term: str, entity: str, col: str, values: list[str], *, support: int = 2,
           kinds=(EvidenceType.DOC, EvidenceType.EXECUTION)):
    m = Mapping("", entity, "LG_{n0}_{n1}_" + entity, column=col, operator="IN", values=values)
    c, _ = store.upsert_concept(TENANT, DS, term, SemanticType.DIMENSION_VALUE, mapping=m,
                                status=ConceptStatus.CANDIDATE)
    for i, k in enumerate(kinds):
        store.add_evidence(Evidence(c.id, k, f"src{i}", support_count=support, weight=0.5))
    return c


def _refuter(store, profiles):
    return Refuter(store, TENANT, DS, profiles)


def test_a_copy_onto_an_unlinked_table_is_refuted(store):
    """Aynı kod listesinin iki tabloda aynı şeyi anlatması için bir sebep gerekir."""
    right = _claim(store, "mal alim", "INVOICE", "TRCODE", ["1"])
    wrong = _claim(store, "mal alim", "ORFICHE", "TRCODE", ["1"])
    out = _refuter(store, [_p("INVOICE", "TRCODE", FATURA_TURU),
                           _p("ORFICHE", "TRCODE", SIPARIS_TURU)]).run()
    ids = {x["id"] for x in out}
    assert wrong.id in ids and right.id not in ids


def test_a_copy_onto_a_joined_table_survives(store):
    """STLINE satırları bir INVOICE başlığına aittir ve TRCODE'ları milyon satırda birebir tutar.
    Bağlantı varsa kopya kopya değildir; ilk hâlim bunu çürütüyordu."""
    _claim(store, "satis iade", "INVOICE", "TRCODE", ["2", "3"])
    lines = _claim(store, "satis iade", "STLINE", "TRCODE", ["2", "3"])
    profiles = [_p("INVOICE", "TRCODE", FATURA_TURU),
                _p("STLINE", "TRCODE", "Bağlı olduğu fiş türü (15=User Defined Input Slip)",
                   rel=[{"column": "INVOICEREF", "ref_entity": "INVOICE", "ref_column": "LOGICALREF"}])]
    assert lines.id not in {x["id"] for x in _refuter(store, profiles).run()}


def test_the_sources_own_label_can_contradict_a_term(store):
    right = _claim(store, "alinan hizmet", "INVOICE", "TRCODE", ["4"])
    wrong = _claim(store, "alinan hizmet", "CLFICHE", "TRCODE", ["4"])
    out = _refuter(store, [_p("INVOICE", "TRCODE", FATURA_TURU),
                           _p("CLFICHE", "TRCODE", "Hareket türü (4=Kur farkı fişi)")]).run()
    assert wrong.id in {x["id"] for x in out} and right.id not in {x["id"] for x in out}


def test_a_term_the_source_does_not_name_is_left_alone(store):
    """Kaynağın sustuğu yerde çürütme yok. "satınalma" = mal alım + alınan hizmet doğrudur, ama
    Logo'nun kod etiketlerinde "satınalma" kelimesi geçmez — kelime örtüşmemesi tek başına delil
    değildir."""
    c = _claim(store, "satinalma", "INVOICE", "TRCODE", ["1", "4"])
    assert c.id not in {x["id"] for x in _refuter(store, [_p("INVOICE", "TRCODE", FATURA_TURU)]).run()}


def test_a_term_nobody_asked_is_only_refuted_when_a_model_made_it_up(store):
    """Sorulmamış olmak yanlış olmak değildir — bu, motorun puanlamada zaten kabul ettiği ayrım.
    Yalnızca modelin ürettiği ve kimsenin ağzına almadığı terim çürütülür."""
    from_docs = _claim(store, "alim iade", "INVOICE", "TRCODE", ["6"],
                       kinds=(EvidenceType.DOC, EvidenceType.PROFILE))
    invented = _claim(store, "sanal sube temsil edebilir", "INVOICE", "TRCODE", ["1"],
                      kinds=(EvidenceType.LLM_CANDIDATE, EvidenceType.PROFILE))
    out = {x["id"] for x in _refuter(store, [_p("INVOICE", "TRCODE", FATURA_TURU)]).run()}
    assert invented.id in out and from_docs.id not in out


def test_a_decision_a_person_made_is_never_refuted(store):
    from semantic_layer.evidence.engine import EvidenceEngine

    c = _claim(store, "mal alim", "ORFICHE", "TRCODE", ["1"])
    _claim(store, "mal alim", "INVOICE", "TRCODE", ["1"])
    EvidenceEngine(store, min_support=3, threshold=0.6).human_certify(c.id, "ayse", "biz böyle kullanıyoruz")
    out = _refuter(store, [_p("INVOICE", "TRCODE", FATURA_TURU),
                           _p("ORFICHE", "TRCODE", SIPARIS_TURU)]).run(
        statuses=[ConceptStatus.CANDIDATE, ConceptStatus.CERTIFIED])
    assert c.id not in {x["id"] for x in out}
