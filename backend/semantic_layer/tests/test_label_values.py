"""2026-09-25, müşteri VM'i (K2, 16 soru): özel adlar veride bulunamıyordu.

- "Portakal Kitap", "antik kitap": Logo yayınevi kodu `ITEMS.SPECODE` alan genişliğinde kesik ("Portakal K",
  "Antik Kita"); tarama profili bu değerleri hiç görmemişti. "antik kitap" bir de CRM kişi bayrağı olarak
  sertifikalı → satış sorusu "iki sunucu" reddi aldı ya da filtre düştü.
- "Timaş Okul": bir yayınevi; "TİMAŞ" ürün yetki koduna, "OKUL" müşteri kanalına bölündü.
- "İstanbul": `CITYCODE`'da 132 kart, `CITY`'de 86.145 — küçük olan seçildi.
Etiket sözlüğü (label_values.py) her kopyadan tam değer listesini tutar; çözümleyici önce oraya bakar."""
from __future__ import annotations

from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ColumnProfile, Mapping, SchemaProfile, SemanticType
from semantic_layer.runtime import label_values as lv
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify, catalog  # noqa: F401

TODAY = date(2026, 9, 25)

DATA = {"columns": {
    "ITEMS.SPECODE": {"entity": "ITEMS", "column": "SPECODE", "source": "logo", "status": "ok", "maxlen": 10,
                      "values": [["Timaş Çocu", 1507], ["Portakal K", 126], ["Timaş Okul", 74], ["Antik Kita", 49], ["T", 3070]]},
    "ITEMS.SPECODE2": {"entity": "ITEMS", "column": "SPECODE2", "source": "logo", "status": "ok", "maxlen": 10,
                       "values": [["Antik Düny", 43], ["Antik Okul", 1]]},
    "CLCARD.CITY": {"entity": "CLCARD", "column": "CITY", "source": "logo", "status": "ok", "maxlen": 14,
                    "values": [["İSTANBUL", 86145], ["ANKARA", 9000]]},
    "CLCARD.SPECODE2": {"entity": "CLCARD", "column": "SPECODE2", "source": "logo", "status": "ok", "maxlen": 9,
                        "values": [["OKUL", 500], ["İSTANBUL", 132]]},
    "CLCARD.DEFINITION_": {"entity": "CLCARD", "column": "DEFINITION_", "source": "logo", "status": "serbest metin: 90000 farklı değer"},
}}


def test_matcher_reads_cut_values_names_and_row_counts():
    m = lv.LabelMatcher(DATA)
    assert [(h.column, h.value, h.how) for h in m.find(["portakal", "kitap"])] == [("SPECODE", "Portakal K", "cut")]
    assert [(h.column, h.value) for h in m.find(["antik", "kitap"])] == [("SPECODE", "Antik Kita")]
    assert m.find(["antik"]) == []                              # a cut never matches a shorter word
    # "antik yayınları": one publisher starts with "antik" in SPECODE; SPECODE2 has two and decides nothing
    assert [(h.column, h.value, h.how) for h in m.find(["antik", "yayinlari"])] == [("SPECODE", "Antik Kita", "name")]
    assert [(h.column, h.rows) for h in m.find(["istanbul"])] == [("CITY", 86145), ("SPECODE2", 132)]
    assert [h.value for h in m.find(["timas", "okul"])] == ["Timaş Okul"]
    assert m.find(["t"]) == []                                  # one-letter codes are not names


def test_build_sums_every_copy_and_says_why_a_column_was_left_out():
    class Conn:
        def __init__(self, by_table): self.by_table = by_table
        def execute(self, sql, limit):
            for t, rows in self.by_table.items():
                if f"[{t}]" in sql:
                    if rows == "err":
                        raise RuntimeError("timeout")
                    return [], rows, False
            return [], [], False
    P = lambda t: SchemaProfile(datasource_id=DS, table_name=t, table_pattern="LG_{n0}_ITEMS", entity="ITEMS", schema_name="dbo",
                                columns=[ColumnProfile(name="SPECODE", data_type="varchar")])
    specs = [{"entity": "ITEMS", "column": "SPECODE", "source": "logo", "tables": [P("LG_211_ITEMS"), P("LG_411_ITEMS")]},
             {"entity": "ITEMS", "column": "NAME", "source": "logo", "tables": [P("LG_911_ITEMS")]},
             {"entity": "ITEMS", "column": "SPECODE3", "source": "logo", "tables": [P("LG_811_ITEMS")]},
             {"entity": "X", "column": "Y", "source": "crm", "tables": [P("Z")]}]
    conn = Conn({"LG_211_ITEMS": [{"v": "T", "n": 5}, {"v": "Antik Kita", "n": 2}], "LG_411_ITEMS": [{"v": "Antik Kita", "n": 47}],
                 "LG_911_ITEMS": [{"v": str(i), "n": 1} for i in range(4)], "LG_811_ITEMS": "err"})
    out = lv.build(specs, lambda s: conn if s == "logo" else None, max_distinct=3)["columns"]
    assert out["ITEMS.SPECODE"]["status"] == "ok" and dict(map(tuple, out["ITEMS.SPECODE"]["values"])) == {"Antik Kita": 49, "T": 5}
    assert out["ITEMS.SPECODE"]["maxlen"] == 10
    assert out["ITEMS.NAME"]["status"].startswith("serbest metin")
    assert out["ITEMS.SPECODE3"]["status"].startswith("okunamadı")
    assert out["X.Y"]["status"].startswith("bağlantı yok")


def _resolver(catalog, profiles):
    crm = SchemaProfile(datasource_id=DS, table_name="ContactBase", table_pattern="CONTACTBASE", entity="CONTACTBASE",
                        schema_name="Timas_MSCRM.dbo", description="Kişi",
                        columns=[ColumnProfile(name="new_portakalkitap", data_type="bit")], row_count=100)
    catalog.upsert_profile(crm)
    _certify(catalog, "portakal kitap", SemanticType.COLUMN, Mapping(concept_id="", entity="CONTACTBASE", table_pattern="CONTACTBASE",
             column="new_portakalkitap", operator="COLUMN"))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, list(profiles) + [crm])
    r = SemanticResolver(catalog, TENANT, DS, list(profiles) + [crm])
    r.label_matcher = lv.LabelMatcher(DATA)
    return r


def _filters(sq):
    return [(s.mapping.entity, s.mapping.column, s.mapping.values) for s in sq.slots
            if s.semantic_type == SemanticType.DIMENSION_VALUE and s.mapping]


def test_a_publisher_name_on_the_measures_database_wins_over_a_flag_on_the_other(catalog, profiles):
    sq = _resolver(catalog, profiles).resolve("Portakal Kitap 2024 satış tutarı", today=TODAY)
    assert ("ITEMS", "SPECODE", ["Portakal K"]) in _filters(sq), (_filters(sq), sq.explanation)
    assert not any(s.mapping and s.mapping.entity == "CONTACTBASE" for s in sq.slots), [(s.term, s.mapping.entity) for s in sq.slots if s.mapping]


def test_a_two_word_publisher_is_one_value_and_the_bigger_column_is_the_city(catalog, profiles):
    r = _resolver(catalog, profiles)
    sq = r.resolve("Timaş Okul 2024 satış tutarı", today=TODAY)
    assert _filters(sq) == [("ITEMS", "SPECODE", ["Timaş Okul"])], (_filters(sq), sq.explanation)
    sq = r.resolve("İstanbul'da 2026 satış tutarı", today=TODAY)
    assert ("CLCARD", "CITY", ["İSTANBUL"]) in _filters(sq), (_filters(sq), sq.explanation)
    sq = r.resolve("antik yayınları 2026 toplam satış tutarı", today=TODAY)
    assert ("ITEMS", "SPECODE", ["Antik Kita"]) in _filters(sq), (_filters(sq), sq.unresolved, sq.explanation)
    assert "yayinlari" not in sq.unresolved, sq.unresolved


def test_without_a_dictionary_nothing_changes(catalog, profiles):
    r = _resolver(catalog, profiles)
    r.label_matcher = lv.LabelMatcher({"columns": {}})
    sq = r.resolve("2024 satış tutarı", today=TODAY)
    assert not _filters(sq), _filters(sq)


def test_the_database_filter_applies_before_word_for_word_values_decide():
    """Gerçek sözlükte "Portakal Kitap" bir CRM alanında birebir var; Logo sorusu yine Logo'daki kesik koda gider."""
    data = {"columns": dict(DATA["columns"], **{"NEW_WEBYAYINEVI.new_name": {
        "entity": "NEW_WEBYAYINEVI", "column": "new_name", "source": "crm", "status": "ok", "maxlen": 20,
        "values": [["Portakal Kitap", 3], ["Antik Yayınları", 2]]}})}
    m = lv.LabelMatcher(data)
    assert [(h.source, h.value) for h in m.find(["portakal", "kitap"], {"logo"})] == [("logo", "Portakal K")]
    assert [(h.source, h.value) for h in m.find(["antik", "yayinlari"], {"logo"})] == [("logo", "Antik Kita")]
    assert [h.value for h in m.find(["portakal", "kitap"], {"crm"})] == ["Portakal Kitap"]
    assert [h.entity for h in m.find(["istanbul"], None, {"CLCARD"})] == ["CLCARD", "CLCARD"]
    assert m.find(["istanbul"], None, {"ITEMS"}) == []
