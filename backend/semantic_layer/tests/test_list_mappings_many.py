"""Toplu eşleme okuması, terim terim okumayla aynı sonucu vermeli (Veri sözlüğü bunu kullanıyor)."""
from semantic_layer.models import ConceptStatus, Mapping, SemanticType
from semantic_layer.store.catalog_store import open_store


def test_many_matches_one_by_one(tmp_path):
    st = open_store(f"sqlite:///{tmp_path / 'cat.db'}")
    ids = []
    for i, term in enumerate(["net ciro", "iade tutarı", "kanal"]):
        m = Mapping(concept_id="", entity="INVOICE", table_pattern="INVOICE", column=f"COL{i}")
        c, _ = st.upsert_concept("t", "d", term, SemanticType.METRIC, mapping=m, status=ConceptStatus.CERTIFIED)
        ids.append(c.id)
    st.replace_mappings(ids[2], [])  # eşlemesi olmayan terim de listede boş kalır

    many = st.list_mappings_many(ids + ["yok"])
    for cid in ids:
        assert [m.column for m in many[cid]] == [m.column for m in st.list_mappings(cid)]
    assert many[ids[2]] == [] and many["yok"] == []
