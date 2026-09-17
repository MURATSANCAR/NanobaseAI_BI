"""Business rules read from what the business wrote: Logo views and CRM saved views."""
from __future__ import annotations

from semantic_layer.models import ColumnProfile, SchemaProfile, SemanticType
from semantic_layer.rule_miner import crm_queries, logo_views, probe
from semantic_layer.rule_miner.common import Catalog, clean_view_name, spoken_variants, term_from_alias


def _p(name, pattern, entity, cols, schema="dbo", ctx=None):
    return SchemaProfile(datasource_id="d", table_name=name, table_pattern=pattern, entity=entity, schema_name=schema,
                         columns=[ColumnProfile(name=n, data_type=t) for n, t in cols], context=ctx or {})


CLFLINE = _p("LG_211_01_CLFLINE", "LG_{n0}_{n1}_CLFLINE", "CLFLINE",
             [("CLIENTREF", "int"), ("SIGN", "smallint"), ("AMOUNT", "float"), ("DATE_", "datetime"), ("MODULENR", "smallint"), ("CANCELLED", "smallint")],
             ctx={"n0": "211", "n1": "01"})
CLFLINE_NEW = _p("LG_411_01_CLFLINE", "LG_{n0}_{n1}_CLFLINE", "CLFLINE", [("CLIENTREF", "int")], ctx={"n0": "411", "n1": "01"})
CLCARD = _p("LG_211_CLCARD", "LG_{n0}_CLCARD", "CLCARD", [("LOGICALREF", "int"), ("CODE", "varchar"), ("DEFINITION_", "varchar"), ("SPECODE2", "varchar")], ctx={"n0": "211"})
SOZLESME = _p("new_sozlesmeBase", "new_sozlesmeBase", "NEW_SOZLESMEBASE",
              [("statecode", "int"), ("new_sozlesmestatusu", "int"), ("ownerid", "uniqueidentifier")], schema="Timas_MSCRM.dbo")
CAT = Catalog([CLFLINE, CLCARD, SOZLESME], [CLFLINE, CLFLINE_NEW, CLCARD, SOZLESME])

VIEW = """CREATE VIEW [EOS_HAREKETLER] AS
SELECT C.CODE 'CARI_KOD', C.SPECODE2 KANAL, T.DATE_ 'VADE_TARİHİ',
 (CASE WHEN T.SIGN=0 THEN T.AMOUNT ELSE 0 END) 'BORC',
 (CASE WHEN T.MODULENR=4 THEN 'FATURALAR' WHEN T.MODULENR IN (6,61) THEN 'ÇEK SENET' WHEN T.MODULENR=4 AND T.SIGN=1 THEN 'TAHSİLAT' END) 'MODUL',
 (CASE WHEN LEFT(C.CODE,3)='101' THEN '12001'+C.CODE END) 'YENI_KOD'
FROM LG_211_01_CLFLINE T JOIN LG_211_CLCARD C ON C.LOGICALREF = T.CLIENTREF
WHERE T.CANCELLED=0 -- SELECT * FROM LG_211_01_CLFLINE WHERE MODULENR=99
"""


def test_words_are_read_from_aliases_and_labels():
    assert term_from_alias("VADE_TARİHİ") == "vade tarihi"
    assert term_from_alias("TOTALVAT") == "totalvat"          # English alias: I is i, not ı
    assert term_from_alias("SatırNo") == "satır no"
    assert clean_view_name("4 - YK Onayında Bekleyen Sözleşmeler") == "yk onayında bekleyen sözleşmeler"
    assert clean_view_name("Etkin Ürünler ( New )") == "etkin ürünler"
    assert clean_view_name("Bana Ait Segmentler") == "segmentler"


def test_a_logo_view_yields_labels_column_names_and_a_measure():
    got = {(c.term, c.semantic_type, c.key()) for c in logo_views.candidates("EOS_HAREKETLER", VIEW, CAT)}
    assert ("kanal", SemanticType.COLUMN, "CLCARD.SPECODE2 COLUMN ") in got
    assert ("vade tarihi", SemanticType.COLUMN, "CLFLINE.DATE_ COLUMN ") in got
    assert ("faturalar", SemanticType.DIMENSION_VALUE, "CLFLINE.MODULENR IN 4") in got
    assert ("çek senet", SemanticType.DIMENSION_VALUE, "CLFLINE.MODULENR IN 6,61") in got
    assert ("tahsilat", SemanticType.DIMENSION_VALUE, "CLFLINE.MODULENR IN 4 | CLFLINE.SIGN IN (1)") in got
    metrics = [c for c in logo_views.candidates("EOS_HAREKETLER", VIEW, CAT) if c.semantic_type == SemanticType.METRIC]
    assert [m.term for m in metrics] == ["borc"], metrics                      # the text CASE is not a measure
    assert metrics[0].formula == "SUM(CASE WHEN CLFLINE.SIGN = 0 THEN CLFLINE.AMOUNT ELSE 0 END)"


def test_a_crm_saved_view_is_a_named_state():
    xml = ('<fetch><entity name="new_sozlesme"><attribute name="new_name"/><filter type="and">'
           '<condition attribute="statecode" operator="eq" value="0"/><condition attribute="new_sozlesmestatusu" operator="eq" value="4"/>'
           '</filter></entity></fetch>')
    (c,) = crm_queries.candidates("4 - YK Onayında Bekleyen Sözleşmeler", xml, CAT)
    assert c.term == "yk onayında bekleyen sözleşmeler" and c.entity == "NEW_SOZLESMEBASE"
    assert c.column == "STATUSCODE" or c.column == "STATECODE"
    assert c.conditions == ["NEW_SOZLESMEBASE.NEW_SOZLESMESTATUSU IN (4)"]
    assert CAT.physical_for(SOZLESME) == "[Timas_MSCRM].[dbo].[new_sozlesme]", "the logical view, not the Base table"
    mine = xml.replace('<condition attribute="new_sozlesmestatusu" operator="eq" value="4"/>',
                       '<condition attribute="ownerid" operator="eq-userid"/>')
    assert crm_queries.candidates("Bana Ait Sözleşmeler", mine, CAT) == [], "a personal list is not a business state"


def test_the_probe_reads_the_newest_copy_and_the_policy_certifies_only_survivors():
    (c,) = crm_queries.candidates("Etkin", '<fetch><entity name="new_sozlesme"><filter type="and"><condition attribute="statecode" operator="eq" value="0"/></filter></entity></fetch>', CAT)
    g = probe.group([c, c])
    assert len(g) == 1 and g[0].sources == ["saved_query:Etkin"]
    fat = next(x for x in logo_views.candidates("V", VIEW, CAT) if x.term == "faturalar")
    sql = probe.probe_sql(fat, CAT, CLFLINE)
    assert sql == "SELECT COUNT(*) AS n FROM [dbo].[LG_411_01_CLFLINE] WHERE [MODULENR] IN (4)"
    (yk,) = crm_queries.candidates("YK Onayında", '<fetch><entity name="new_sozlesme"><filter type="and"><condition attribute="statecode" operator="eq" value="0"/><condition attribute="new_sozlesmestatusu" operator="eq" value="4"/></filter></entity></fetch>', CAT)
    assert probe.probe_sql(yk, CAT, SOZLESME) == "SELECT COUNT(*) AS n FROM [Timas_MSCRM].[dbo].[new_sozlesme] WHERE [statecode] IN (0) AND [new_sozlesmestatusu] IN (4)", "CRM spells its columns in lower case and compares case-sensitively"
    assert probe.decide(probe.group([fat])[0], True, conflict=False) == "CANDIDATE", "one word from one view waits for a person"
    three = probe.group([fat, logo_views.Candidate(**{**fat.__dict__, "source": "V2"}), logo_views.Candidate(**{**fat.__dict__, "source": "V3"})])[0]
    assert probe.decide(three, True, conflict=False) == "CERTIFIED", "one word three views agree on is certified"
    two_words = probe.group([logo_views.Candidate(**{**fat.__dict__, "term": "çek senet"})])[0]
    assert probe.decide(two_words, True, conflict=False) == "CERTIFIED"
    assert probe.decide(three, True, conflict=True) == "CANDIDATE"
    assert probe.decide(three, True, conflict=False, ambiguous=True) == "CANDIDATE"
    kanal = next(x for x in logo_views.candidates("V", VIEW, CAT) if x.term == "kanal")
    assert probe.decide(probe.group([kanal])[0], True, conflict=False) == "CANDIDATE", "one view's column alias waits for a person"
    tutar = probe.group([logo_views.Candidate("tutar", "COLUMN", "CLFLINE", "LG_{n0}_{n1}_CLFLINE", "AMOUNT", "COLUMN", kind="label_map")])[0]
    assert probe.decide(tutar, True, conflict=False) == "CANDIDATE", "a generic word is never self-certified"


def test_a_status_label_gets_the_forms_people_ask_it_in():
    assert "devam eden" in spoken_variants("devam ediyor")
    assert spoken_variants("yk onayında bekliyor") == ["yk onayında bekleyen"]
    assert spoken_variants("kanal") == []


def test_a_view_named_after_its_own_table_is_not_a_business_state():
    fl = _p("new_fiyatlistesiBase", "new_fiyatlistesiBase", "NEW_FIYATLISTESIBASE", [("statecode", "int"), ("statuscode", "int")], schema="Timas_MSCRM.dbo")
    fl.description = "Fiyat Listesi Yeni"
    cat = Catalog([fl], [fl])
    xml = '<fetch><entity name="new_fiyatlistesi"><filter type="and"><condition attribute="statecode" operator="eq" value="0"/></filter></entity></fetch>'
    (own,) = crm_queries.candidates("Fiyat Listeleri", xml, cat)
    assert probe.names_its_own_entity(probe.group([own])[0], cat)
    two = xml.replace('value="0"/>', 'value="0"/><condition attribute="statuscode" operator="eq" value="2"/>')
    (state,) = crm_queries.candidates("Onay Bekleyen Fiyat Listeleri", two, cat)
    assert not probe.names_its_own_entity(probe.group([state])[0], cat)
