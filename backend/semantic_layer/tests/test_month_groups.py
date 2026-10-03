"""K13 (tam kapı 2026-09-29, B072): 12 ay kolonunun açılımını derleyici yazar, kapı eksik/yanlış el açılımını onarıma yollar.

Sınıf sınanır, soru değil: ay adlı ve ay numaralı gruplar, sıra listelerinin elenmesi, sanal kolonların açılımı (nitelikli,
niteliksiz, JOIN'den önce), onarımda geri katlama, VALUES / UNION / CASE el açılımlarının denetimi, katalog beyanının
profillere dağıtılması. Veriler yapaydır; gerçek veri ve gerçek modelle ölçüm test sunucusunda (answer-gate).
"""
from __future__ import annotations

import json
import re

import sqlglot

from semantic_layer.models import ColumnProfile, Mapping, SchemaProfile
from semantic_layer.runtime import month_groups as MG
from semantic_layer.runtime.critic import review as critic_review

MONTH_COLS = ["new_ocak", "new_subat", "new_Mart", "new_Nisan", "new_mayis", "new_Haziran", "new_Temmuz", "new_agustos",
              "new_eylul", "new_Ekim", "new_kasim", "new_aralik"]
LABEL = "Timas_MSCRM_dbo_new_satishedefleriBase"


def _t(entity, name, cols, *, pattern=None, pk=None, schema="dbo"):
    return SchemaProfile(datasource_id="d", table_name=name, table_pattern=pattern or name, entity=entity, schema_name=schema,
                         columns=[ColumnProfile(name=n, data_type=dt, is_primary_key=(n == pk)) for n, dt in cols],
                         primary_key=[pk] if pk else [])


def _hedef(declared: bool = True) -> SchemaProfile:
    p = _t("NEW_SATISHEDEFLERIBASE", "new_satishedefleriBase",
           [("new_satishedefleriId", "uniqueidentifier"), ("statecode", "int"), ("new_StokKodu", "nvarchar"),
            ("new_yil", "int"), *[(c, "int") for c in MONTH_COLS], ("new_ToplamHedef", "int")],
           pk="new_satishedefleriId", schema="Timas_MSCRM.dbo")
    p.month_columns = {i: c for i, c in enumerate(MONTH_COLS, 1)} if declared else {}
    p.month_missing = MG.MISSING_NULL_OR_ZERO if declared else None
    return p


KITAP = _t("NEW_KITAPBASE", "new_kitapBase", [("new_kitapId", "uniqueidentifier"), ("new_stokkodu", "nvarchar"),
                                               ("new_name", "nvarchar")], pk="new_kitapId", schema="Timas_MSCRM.dbo")


def _apply_rows(sql: str):
    tree = sqlglot.parse_one(sql, read="tsql")
    lat = [j.this for j in tree.find_all(sqlglot.exp.Join) if isinstance(j.this, sqlglot.exp.Lateral)]
    return lat


# ---------------------------------------------------------------- tanıma

def test_detect_finds_a_month_named_group_and_drops_numbered_sequences():
    p = _hedef(declared=False)
    found, _ = MG.detect(p)
    assert len(found) == 1 and found[0]["month_columns"] == {str(i): c for i, c in enumerate(MONTH_COLS, 1)}
    seq = _t("L_MANDFLDS", "L_MANDFLDS", [(f"DOCTYPE{i}", "smallint") for i in range(1, 26)])
    found, dropped = MG.detect(seq)
    assert not found and any("kardeş" in d["why"] for d in dropped)
    groups = _t("L_CAPI", "L_CAPI", [(f"GROUPS{i}", "smallint") for i in range(1, 13)])
    found, dropped = MG.detect(groups)
    assert not found and any("dönem sözü değil" in d["why"] for d in dropped)


def test_detect_accepts_period_word_or_bare_numbers_and_requires_numeric_and_twelve():
    assert MG.detect(_t("V", "V", [(str(i), "decimal") for i in range(1, 13)]))[0]
    assert MG.detect(_t("V", "V", [(f"AY{i}", "float") for i in range(1, 13)]))[0]
    text = _t("V", "V", [(m, "nvarchar(20)") for m in ["Ocak", "Subat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
                                                       "Agustos", "Eylul", "Ekim", "Kasim", "Aralik"]])
    found, dropped = MG.detect(text)
    assert not found and any("sayısal değil" in d["why"] for d in dropped)
    eleven = _t("V", "V", [(c, "int") for c in MONTH_COLS[:11]])
    found, dropped = MG.detect(eleven)
    assert not found and any("12 ay yok" in d["why"] for d in dropped)


def test_normalize_rejects_an_incomplete_declaration():
    assert MG.normalize({str(i): c for i, c in enumerate(MONTH_COLS, 1)})[12] == "new_aralik"
    assert MG.normalize({str(i): c for i, c in enumerate(MONTH_COLS[:11], 1)}) == {}
    assert MG.normalize({"1": "a", **{str(i): "a" for i in range(2, 13)}}) == {}


# ---------------------------------------------------------------- derleyici: açılım

def test_virtual_month_columns_expand_to_all_twelve_months_in_order():
    sql = (f"-- yorum: 'girilmemiş' → ay değeri 0\nSELECT h.new_StokKodu, h.ay, h.ay_adi FROM {LABEL} h "
           "WHERE h.new_ToplamHedef > 0 AND ISNULL(h.ay_degeri, 0) = 0")
    out, notes = MG.expand(sql, [_hedef(), KITAP])
    assert out.startswith("-- yorum: 'girilmemiş' → ay değeri 0\n") and notes
    lat = _apply_rows(out)
    assert len(lat) == 1
    rows = lat[0].this.this.expressions
    assert [int(r.expressions[0].this) for r in rows] == list(range(1, 13))
    assert [r.expressions[2].name for r in rows] == MONTH_COLS
    assert [r.expressions[1].this for r in rows][2] == "Mart"
    assert not re.search(r"(?<![\w])h\.ay", out) and "nb_ay_h.ay_degeri" in out and "nb_ay_h.ay_adi" in out


def test_expansion_goes_right_after_the_table_so_a_later_join_can_read_the_month():
    sql = (f"SELECT k.new_name, h.ay FROM {LABEL} h LEFT JOIN Timas_MSCRM_dbo_new_kitapBase k "
           "ON k.new_stokkodu = h.new_StokKodu WHERE h.ay_degeri = 0")
    out, _ = MG.expand(sql, [_hedef(), KITAP])
    assert out.index("CROSS APPLY") < out.index("LEFT JOIN")


def test_unqualified_virtual_column_binds_only_when_one_grouped_table_is_read():
    out, notes = MG.expand(f"SELECT ay, COUNT(*) AS n FROM {LABEL} WHERE ay_degeri = 0 GROUP BY ay", [_hedef()])
    assert notes and "CROSS APPLY" in out
    same = "SELECT x.ay FROM (SELECT 1 AS ay) x"
    assert MG.expand(same, [_hedef()]) == (same, [])


def test_grouping_by_month_name_also_groups_by_month_number():
    """B072 (2026-09-30 tam kapı): `GROUP BY h.ay_adi ORDER BY h.ay` SQL Server'da 8127 ile düştü; ay ↔ ay_adi birebir."""
    sql = (f"SELECT h.ay_adi, COUNT(*) AS n FROM {LABEL} h WHERE ISNULL(h.ay_degeri, 0) = 0 "
           "GROUP BY h.ay_adi ORDER BY h.ay")
    out, _ = MG.expand(sql, [_hedef()])
    group = sqlglot.parse_one(out, read="tsql").args["group"].expressions
    assert {(c.table, c.name) for c in group} == {("nb_ay_h", "ay_adi"), ("nb_ay_h", "ay")}


def test_a_statement_without_virtual_columns_is_returned_untouched():
    sql = f"SELECT SUM(h.new_ocak) AS ocak FROM {LABEL} h  -- tek ay"
    assert MG.expand(sql, [_hedef()]) == (sql, [])
    assert MG.expand("SELECT h.ay FROM t h", [_hedef(declared=False)])[1] == []


def test_collapse_folds_the_compilers_expansion_back_for_a_repair():
    sql = f"SELECT h.new_StokKodu, h.ay FROM {LABEL} h WHERE ISNULL(h.ay_degeri, 0) = 0"
    out, _ = MG.expand(sql, [_hedef()])
    back = MG.collapse(out)
    assert "CROSS APPLY" not in back and "h.ay" in back
    assert MG.expand(back, [_hedef()])[0] == out


def test_existing_compiler_expands_model_sql_and_shows_the_note():
    from semantic_layer.runtime.compiler import ExistingCompiler
    comp = ExistingCompiler(None, [_hedef(), KITAP], {})
    out = comp._months(f"SELECT h.ay FROM {LABEL} h WHERE h.ay_degeri = 0")
    assert "CROSS APPLY" in out
    note = MG.prompt_note(_hedef(), LABEL)
    assert "ay_degeri" in note and "ISNULL(<takma ad>.ay_degeri, 0) = 0" in note
    assert MG.prompt_note(_hedef(declared=False), LABEL) == ""


# ---------------------------------------------------------------- kapı: el açılımı

def _values(months, wrong=None):
    rows = []
    for n in months:
        label = (wrong or {}).get(n, n)
        rows.append(f"({label}, h.{MONTH_COLS[n - 1]})")
    return f"SELECT h.new_StokKodu, v.ay FROM {LABEL} h CROSS APPLY (VALUES {', '.join(rows)}) v(ay, d) WHERE ISNULL(v.d, 0) = 0"


def test_an_incomplete_hand_unpivot_is_sent_to_repair():
    f = [x for x in critic_review(_values([1, 2, 3, 4, 5, 6, 8, 9, 10, 12]), [_hedef()]) if x.kind == "MONTH_UNPIVOT"]
    assert f and f[0].severity == "block" and "Temmuz" in f[0].message and "Kasım" in f[0].message


def test_a_wrongly_mapped_hand_unpivot_is_sent_to_repair():
    f = MG.review(_values(range(1, 13), wrong={3: 4, 4: 3}), [_hedef()])
    assert f and "yanlış eşleme" in f[0][1] and "new_Mart → 4" in f[0][1]


def test_a_month_name_label_is_read_too():
    rows = ", ".join(f"(N'{MG.MONTH_LABELS[i]}', h.{c})" for i, c in enumerate(MONTH_COLS))
    rows = rows.replace("N'Mart', h.new_Mart", "N'Nisan', h.new_Mart")
    sql = f"SELECT v.ay FROM {LABEL} h CROSS APPLY (VALUES {rows}) v(ay, d)"
    assert any("new_Mart → 4" in m for _, m in MG.review(sql, [_hedef()]))


def test_a_complete_hand_unpivot_and_the_compilers_own_pass():
    assert not MG.review(_values(range(1, 13)), [_hedef()])
    out, _ = MG.expand(f"SELECT h.ay FROM {LABEL} h WHERE h.ay_degeri = 0", [_hedef()])
    assert not [x for x in critic_review(out, [_hedef()]) if x.kind == "MONTH_UNPIVOT"]


def test_union_and_case_unpivots_are_checked_but_filters_are_not():
    union = " UNION ALL ".join(f"SELECT h.new_StokKodu, {n} AS ay, h.{MONTH_COLS[n - 1]} AS d FROM {LABEL} h"
                               for n in range(1, 12))
    assert any("Aralık" in m for _, m in MG.review(union, [_hedef()]))
    case = ("SELECT CASE m.n " + " ".join(f"WHEN {n} THEN h.{MONTH_COLS[n - 1]}" for n in range(1, 11))
            + f" END AS d FROM {LABEL} h CROSS JOIN (SELECT 1 AS n) m")
    assert MG.review(case, [_hedef()])
    flt = ("SELECT SUM(CASE WHEN h.new_ocak > 0 THEN 1 WHEN h.new_subat > 0 THEN 1 ELSE 0 END) AS n "
           f"FROM {LABEL} h")
    assert not MG.review(flt, [_hedef()])
    one = f"SELECT SUM(h.new_eylul) AS eylul, SUM(h.new_ToplamHedef) AS yil FROM {LABEL} h"
    assert not MG.review(one, [_hedef()])


def test_no_declaration_no_finding():
    assert not MG.review(_values([1, 2, 3]), [_hedef(declared=False)])


# ---------------------------------------------------------------- beyan → profil

class _Store:
    def __init__(self, maps):
        self.maps = maps

    def certified_index(self, tenant, ds):
        return {"satış hedefi": [(object(), self.maps)]}


class _S:
    tenant_id, datasource_id = "t", "d"


def test_apply_hands_the_catalog_declaration_to_every_copy_and_rejects_a_mismatch(tmp_path, monkeypatch):
    monkeypatch.delenv("SEMANTIC_MONTH_GROUPS_FILE", raising=False)
    decl = {str(i): c for i, c in enumerate(MONTH_COLS, 1)}
    m = Mapping(concept_id="c", entity="NEW_SATISHEDEFLERIBASE", table_pattern="new_satishedefleriBase",
                extra={"month_columns": decl, "month_missing": "null_or_zero"})
    a, b = _hedef(declared=False), _hedef(declared=False)
    assert MG.apply([a, b, KITAP], _Store([m]), _S()) == 2
    assert MG.of(a)[3] == "new_Mart" and MG.of(KITAP) == {}
    bad = Mapping(concept_id="c", entity="NEW_SATISHEDEFLERIBASE", table_pattern="new_satishedefleriBase",
                  extra={"month_columns": {**decl, "3": "new_yok"}})
    c = _hedef(declared=False)
    assert MG.apply([c], _Store([bad]), _S()) == 0 and MG.of(c) == {}
    path = tmp_path / "ay.json"
    path.write_text(json.dumps({"groups": [{"entity": "NEW_SATISHEDEFLERIBASE", "table_pattern": "new_satishedefleriBase",
                                            "month_columns": decl, "month_missing": "null_or_zero"}]}), encoding="utf-8")
    monkeypatch.setenv("SEMANTIC_MONTH_GROUPS_FILE", str(path))
    d = _hedef(declared=False)
    assert MG.apply([d], _Store([]), _S()) == 1 and MG.of(d)[12] == "new_aralik"
