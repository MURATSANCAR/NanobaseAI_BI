"""A mapping edit must be visible to readers without a restart.

Readers (the bridge) rebuild when `catalog_fingerprint` moves. The fingerprint watches the last
concept write; a mapping edit that did not touch the concept left the bridge on the old meaning."""
import time

from semantic_layer.models import ConceptStatus, Mapping, SemanticType
from semantic_layer.store.catalog_store import open_store


def _store(tmp_path):
    return open_store(f"sqlite:///{tmp_path / 'cat.db'}")


def test_replace_mappings_moves_the_fingerprint(tmp_path):
    st = _store(tmp_path)
    m = Mapping(concept_id="", entity="INVOICE", table_pattern="INVOICE", column="GRPCODE", operator="IN", values=["1"])
    c, _ = st.upsert_concept("t", "d", "alım faturası", SemanticType.DIMENSION_VALUE, mapping=m, status=ConceptStatus.CERTIFIED)
    before = st.catalog_fingerprint("t", "d")
    time.sleep(1.1)  # fingerprint resolves to whole seconds
    st.replace_mappings(c.id, [Mapping(concept_id=c.id, entity="INVOICE", table_pattern="INVOICE",
                                       column="TRCODE", operator="IN", values=["1", "4"])])
    after = st.catalog_fingerprint("t", "d")
    assert after != before, "eşleme değişti ama parmak izi aynı kaldı — okuyucu eski anlamla çalışır"
    assert [m.values for m in st.list_mappings(c.id)] == [["1", "4"]]
