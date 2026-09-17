"""2026-09-17, soru 12: recalled examples were physicalised statements (dbo_LG_411_01_STLINE) and the
model copied the style — physical names pin one year's copy and bypass period resolution."""
from semantic_layer.naming import logicalize_sql


def test_physical_copies_read_back_as_entities():
    sql = ('SELECT it."CODE" FROM dbo_LG_411_01_STLINE sl JOIN dbo_LG_411_ITEMS it ON it."LOGICALREF" = sl."STOCKREF" '
           "JOIN dbo.LG_211_01_INVOICE i ON i.LOGICALREF = sl.INVOICEREF JOIN Timas_MSCRM.dbo.AccountBase a ON 1=1")
    out = logicalize_sql(sql)
    assert "FROM STLINE sl" in out and "JOIN ITEMS it" in out and "JOIN INVOICE i" in out, out
    assert "Timas_MSCRM.dbo.AccountBase" in out          # not a period copy: untouched


def test_columns_aliases_and_literals_stay():
    sql = "SELECT sl2.DATE_, sl2.TRCODE FROM STLINE sl2 WHERE sl2.DATE_ >= '2026-01-01' AND sl2.LINETYPE = 0"
    assert logicalize_sql(sql) == sql
