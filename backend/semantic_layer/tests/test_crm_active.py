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
            if "sys.objects" in sql:
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


def test_active_record_with_passive_status_reason_is_filtered():
    """Etkin kayıt (statecode 0) durum nedeni «Pasif» taşıyorsa da gelmez (kullanıcı kuralı 2026-09-29)."""
    passive = ca.passive_codes([{"ent": "new_kitap", "code": 2}, {"ent": "new_kitap", "code": 100000003},
                                {"ent": "contact", "code": "2"}, {"ent": "", "code": 5}, {"ent": "x", "code": None}])
    assert passive == {"new_kitapbase": (2, 100000003), "new_kitap": (2, 100000003), "contactbase": (2,), "contact": (2,)}
    sql = f"SELECT b.new_name FROM {P}new_kitapBase b LEFT JOIN {P}new_projeBase j ON j.x = b.y"
    out = ca.rewrite(sql, E, passive)
    assert (f"(SELECT * FROM {P}new_kitapBase WHERE statecode = 0 AND (statuscode IS NULL OR statuscode NOT IN"
            f" (2, 100000003))) b") in out
    assert f"(SELECT * FROM {P}new_projeBase WHERE statecode = 0) j" in out
    assert "N'Pasif%'" in ca.passive_sql("Timas_MSCRM")


def test_wrapper_reads_passive_reasons_once_and_survives_failure():
    class Fake:
        def __init__(self, fail=False):
            self.seen, self.fail = [], fail

        def execute(self, sql, limit):
            self.seen.append(sql)
            if "sys.objects" in sql:
                return [], [{"name": "new_kitapBase"}], False
            if "StringMapBase" in sql:
                if self.fail:
                    raise RuntimeError("yetki yok")
                return [], [{"ent": "new_kitap", "code": 2}], False
            return [], [], False

    inner = Fake()
    crm = ca.wrap(inner, "Timas_MSCRM")
    crm.execute(f"SELECT * FROM {P}new_kitapBase k", 10)
    crm.execute(f"SELECT * FROM {P}new_kitapBase k", 10)
    assert sum("StringMapBase" in s for s in inner.seen) == 1
    assert "statuscode NOT IN (2)" in inner.seen[-1]
    bad = Fake(fail=True)
    crm2 = ca.wrap(bad, "Timas_MSCRM")
    crm2.execute(f"SELECT * FROM {P}new_kitapBase k", 10)
    assert bad.seen[-1] == f"SELECT * FROM (SELECT * FROM {P}new_kitapBase WHERE statecode = 0) k"


def test_settings_reach_the_inner_connector():
    """`conn.query_timeout = 1800` sarmalda kalırsa asıl bağlantı varsayılan 120 sn ile koşar."""
    class Inner:
        query_timeout = 120

    inner = Inner()
    crm = ca.ActiveOnly(inner, "Timas_MSCRM")
    crm.query_timeout = 1800
    assert inner.query_timeout == 1800 and crm.query_timeout == 1800
    assert "query_timeout" not in vars(crm) and crm.inner is inner


def test_views_of_entities_are_filtered_too():
    """`new_kitap` görünümünden okuyan modül süzgeçten kaçmaz; durum nedeni kodu görünüm adına da bağlanır."""
    class Fake:
        def __init__(self):
            self.seen = []

        def execute(self, sql, limit):
            self.seen.append(sql)
            if "sys.objects" in sql:
                return [], [{"name": "new_kitapBase"}, {"name": "new_kitap"}, {"name": "Account"}], False
            if "StringMapBase" in sql:
                return [], [{"ent": "new_kitap", "code": 2}], False
            return [], [], False

    inner = Fake()
    crm = ca.wrap(inner, "Timas_MSCRM")
    crm.execute(f"SELECT k.new_name FROM {P}new_kitap k JOIN {P}Account a ON a.AccountId = k.x", 10)
    assert inner.seen[-1] == (f"SELECT k.new_name FROM (SELECT * FROM {P}new_kitap WHERE statecode = 0 AND (statuscode IS NULL"
                              f" OR statuscode NOT IN (2))) k JOIN (SELECT * FROM {P}Account WHERE statecode = 0) a ON a.AccountId = k.x")
    assert ca.passive_codes([{"ent": "new_kitap", "code": 2}]) == {"new_kitapbase": (2,), "new_kitap": (2,)}

    # Power BI'dan birebir rapor SQL'i: görünüm aynen, temel tablo süzülür.
    pbi = ca.base_tables_only(ca.wrap(Fake(), "Timas_MSCRM"))
    pbi.execute(f"SELECT * FROM {P}new_kitap k", 10)
    assert pbi.inner.seen[-1] == f"SELECT * FROM {P}new_kitap k"
    pbi.execute(f"SELECT * FROM {P}new_kitapBase k", 10)
    assert "statecode = 0" in pbi.inner.seen[-1]
