"""CRM etkin kayıt süzgeci: pasif (`statecode = 1`) kayıt hiçbir ekrana gelmez."""
from __future__ import annotations

from semantic_layer.runtime import crm_active as ca

E = frozenset({"new_projebase", "contactbase", "new_sozlesmebase", "new_kitapbase"})
P = "Timas_MSCRM.dbo."


def test_alias_and_join_are_wrapped():
    sql = (f"SELECT j.new_name, a.FullName, u.FullName FROM {P}new_projeBase j"
           f" LEFT JOIN {P}ContactBase a ON a.ContactId = j.x"
           f" LEFT JOIN {P}SystemUserBase u ON u.SystemUserId = j.new_editoru WHERE j.statecode = 0")
    out = ca.rewrite(sql, E)
    assert f"(SELECT * FROM {P}new_projeBase WHERE statecode = 0) j" in out
    assert f"(SELECT * FROM {P}ContactBase WHERE statecode = 0) a" in out
    # kullanıcı hesabı süzülmez: kapalı hesap geçmiş kaydın editörüdür
    assert f"{P}SystemUserBase u" in out
    assert out.endswith("WHERE j.statecode = 0")


def test_unaliased_table_keeps_its_name_for_qualified_columns():
    sql = (f"SELECT COUNT(*) FROM {P}new_kitapBase WHERE EXISTS (SELECT 1 FROM {P}new_sozlesmeBase AS s"
           f" WHERE s.x = new_kitapBase.y)")
    out = ca.rewrite(sql, E)
    assert f"(SELECT * FROM {P}new_kitapBase WHERE statecode = 0) new_kitapBase" in out
    assert f"(SELECT * FROM {P}new_sozlesmeBase WHERE statecode = 0) s" in out
    assert "new_kitapBase.y" in out


def test_bracketed_names_and_untouched_text():
    sql = ("SELECT k.new_name AS [Ad], N'%yaz%' AS x FROM [Timas_MSCRM].[dbo].[new_kitapBase] k"
           " ORDER BY k.new_name OFFSET 50 ROWS FETCH NEXT 50 ROWS ONLY")
    out = ca.rewrite(sql, E)
    assert "(SELECT * FROM [Timas_MSCRM].[dbo].[new_kitapBase] WHERE statecode = 0) k" in out
    assert out.startswith("SELECT k.new_name AS [Ad], N'%yaz%' AS x FROM ")
    assert out.endswith("OFFSET 50 ROWS FETCH NEXT 50 ROWS ONLY")


def test_not_eligible_and_non_select_are_left_alone():
    assert ca.rewrite(f"SELECT * FROM {P}StringMapBase", E) == f"SELECT * FROM {P}StringMapBase"
    assert ca.rewrite(f"SELECT * FROM {P}new_new_sozlesme_new_kitapBase x", E) == f"SELECT * FROM {P}new_new_sozlesme_new_kitapBase x"
    assert ca.rewrite("SELEC broken ((", E) == "SELEC broken (("


def test_switch_off(monkeypatch):
    monkeypatch.setenv("CRM_ACTIVE_ONLY", "0")
    sql = f"SELECT * FROM {P}new_kitapBase k"
    assert ca.rewrite(sql, E) == sql


def test_wrap_only_crm_databases():
    class Fake:
        def __init__(self):
            self.seen = []

        def execute(self, sql, limit):
            self.seen.append(sql)
            if "sys.tables" in sql:
                return [], [{"name": "new_kitapBase"}], False
            return [], [], False

    logo = Fake()
    assert ca.wrap(logo, "TIGERDB") is logo
    inner = Fake()
    crm = ca.wrap(inner, "Timas_MSCRM")
    assert isinstance(crm, ca.ActiveOnly)
    crm.execute(f"SELECT * FROM {P}new_kitapBase k", 10)
    assert inner.seen[-1] == f"SELECT * FROM (SELECT * FROM {P}new_kitapBase WHERE statecode = 0) k"
    assert ca.wrap(crm, "Timas_MSCRM") is crm
