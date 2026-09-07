from datetime import date
from semantic_layer.tests.test_runtime import *  # noqa
from semantic_layer.tests.test_runtime import DS, TENANT, FakeLlm, SemanticResolver


def test_zz_diag(catalog, profiles, settings):
    from semantic_bridge.app import Runtime
    from semantic_layer.models import ColumnProfile, SchemaProfile
    noise = [
        SchemaProfile(datasource_id=DS, table_name=f"LG_411_01_NOISE{i}", table_pattern="LG_{n0}_{n1}_NOISE" + str(i),
                      entity=f"NOISE{i}", schema_name="main",
                      columns=[ColumnProfile(name=f"C{j}", data_type="varchar(50)") for j in range(80)],
                      primary_key=["C0"], context={"n0": "411", "n1": "01"})
        for i in range(40)]
    for p in noise:
        catalog.upsert_profile(p)
    rt = Runtime(settings, store=catalog, connector=None, llm=FakeLlm([""]))
    r = SemanticResolver(catalog, TENANT, DS, rt.profiles)
    sq = r.resolve("Toptan satış tutarı ne kadar?", today=date(2026, 7, 20))
    c = rt.existing
    ents = c.relevant_entities(sq, [])
    print("\nmax_prompt_tables:", c.max_prompt_tables, "max_prompt_columns:", c.max_prompt_columns)
    print("profiles:", len(c.profiles), "entities in profiles:", len({p.entity for p in c.profiles}))
    print("relevant_entities:", len(ents), sorted(ents)[:20])
    print("one_per_entity(wanted):", len(c._one_per_entity(ents)))
    print("model_index len:", len(c.model_index(ents)))
    print("schema_context len:", len(c.schema_context(sq, [], ents)))
    print("rules_text len:", len(c.rules_text or ""))
    print("catalog_block len:", len(c.catalog_block(sq)))
    sc = c.schema_context(sq, [], ents)
    for line in sc.split("\n")[:6]:
        print("  SC:", len(line), line[:120])
