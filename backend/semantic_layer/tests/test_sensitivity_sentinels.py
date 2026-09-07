"""Personal data never leaves the database, and 'no value' markers are never read as values."""

from __future__ import annotations

import sqlite3

import pytest

from semantic_layer.conventions import Conventions
from semantic_layer.profiler import sensitivity
from semantic_layer.profiler.connectors import SQLiteConnector
from semantic_layer.profiler.profiler import Profiler
from semantic_layer.runtime.compiler import ExistingCompiler
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.candidates.llm_client import FakeLlm
from semantic_layer.store.catalog_store import open_store


@pytest.fixture
def pii_profiles():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.executescript(
        """
        CREATE TABLE contacts (id INTEGER PRIMARY KEY, code TEXT, tckno TEXT, emailaddr TEXT,
                               contact_field TEXT, segment TEXT, owner_ref INTEGER, discount REAL);
        """
    )
    rows = []
    for i in range(1, 13):
        rows.append((i, f"C{i}", f"{10000000000 + i}", f"user{i}@example.com", f"+90 532 111 22 {i:02d}",
                     "PERAKENDE" if i % 2 else "TOPTAN", 0 if i % 3 else i, 0.0 if i % 2 else 12.5))
    c.executemany("INSERT INTO contacts VALUES (?,?,?,?,?,?,?,?)", rows)
    c.commit()
    return Profiler(SQLiteConnector(conn=c), enum_max_distinct=32).profile("d", "main", None), c


def test_name_and_value_shapes_are_detected():
    assert sensitivity.classify("TCKNO")
    assert sensitivity.classify("EMAILADDR")
    assert sensitivity.classify("TELNRS1")
    assert sensitivity.classify("contact_field", ["+90 532 111 22 33", "+90 532 111 22 34", "+90 555 000 11 22"])
    assert sensitivity.classify("segment", ["TOPTAN", "PERAKENDE"]) is None
    assert sensitivity.classify("net_amount", ["100", "200"]) is None


def test_sensitive_columns_are_never_sampled(pii_profiles):
    profiles, _ = pii_profiles
    contacts = profiles[0]
    tckno, email, phone, segment = (contacts.column(n) for n in ("tckno", "emailaddr", "contact_field", "segment"))
    assert tckno.sensitive and email.sensitive
    assert phone.sensitive and "telefon" in (phone.sensitivity_reason or "")   # innocuous name, telling values
    assert tckno.top_values == [] and email.top_values == [] and phone.top_values == []
    assert segment.top_values and not segment.sensitive
    conv = Conventions.from_profiles(profiles)
    assert conv.is_sensitive("CONTACTS", "tckno") and not conv.is_sensitive("CONTACTS", "segment")
    assert "TCKNO" not in conv.enum_columns["CONTACTS"]                        # cannot become a scope column either


def test_sentinels_are_recorded_and_excluded(pii_profiles):
    profiles, _ = pii_profiles
    contacts = profiles[0]
    discount = contacts.column("discount")
    assert "0" in discount.sentinel_values                                     # dominant zero in a measure
    assert discount.null_ratio == 0.0                                          # measured from the row sample
    owner = contacts.column("owner_ref")
    assert owner.sentinel_values == ["0", "-1"] if owner.ref_entity else "0" in owner.sentinel_values
    conv = Conventions.from_profiles(profiles)
    assert conv.sentinel_values("CONTACTS", "discount") == {"0"}


def test_prompt_hides_values_and_states_the_rules(pii_profiles):
    profiles, _ = pii_profiles
    store = open_store("sqlite://")
    for p in profiles:
        store.upsert_profile(p)
    llm = FakeLlm(replies=["NO_SQL: test"])
    comp = ExistingCompiler(llm, profiles, {}, dialect="sqlite")
    q = SemanticResolver(store, "t", "d", profiles).resolve("segment bazında indirim")
    comp.compile(q, store)
    prompt = llm.calls[0][0]["content"]
    assert "kişisel veri" in prompt and "TOPTAN" in prompt                     # business values stay, personal ones go
    for leaked in ("10000000001", "user1@example.com", "+90 532 111 22 01"):
        assert leaked not in prompt
    assert "= değer yok" in prompt                                            # sentinel meaning is stated


def test_everything_the_profile_knows_survives_the_store(store, profiles):
    """A column detected as personal data came back from the store unmarked, because the reader named
    its fields one by one and the ones added later were dropped in silence. The protection that keeps
    personal data out of value lookups and out of prompts was then only ever true in memory."""
    import dataclasses

    from semantic_layer.models import ColumnProfile

    p = profiles[0]
    col = p.columns[0]
    col.sensitive = True
    col.sensitivity_reason = "test"
    col.sentinel_values = ["0"]
    col.unit = "KDV hariç"
    col.derived = ["2026-08-17 tarihine kadar dolu"]
    store.upsert_profile(p)

    back = next(x for x in store.list_profiles(p.datasource_id) if x.entity == p.entity)
    c = back.column(col.name)
    assert c.sensitive and c.sensitivity_reason == "test"
    assert c.sentinel_values == ["0"] and c.unit == "KDV hariç"
    assert c.derived == ["2026-08-17 tarihine kadar dolu"]
    # and nothing the dataclass carries is quietly left behind
    for f in dataclasses.fields(ColumnProfile):
        assert hasattr(c, f.name), f.name
