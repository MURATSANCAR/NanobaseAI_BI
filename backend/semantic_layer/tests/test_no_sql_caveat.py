"""A refusal grounded in a documented caveat is explained in the operator's words, not the model's."""
from semantic_layer.runtime.compiler import caveat_for, no_sql_reason

RULES = """## Ölçüler
- **Gerçekleşen tahsilat süresi** = AVG(DATEDIFF(gün, fatura tarihi, kapatan ödemenin tarihi)); kaynak PAYTRANS (MODULENR 4, SIGN 0, CANCELLED 0) ödeme planı satırı, kapatan ödeme CROSSREF ile bağlı satır.

## Dikkat
- Fatura satır toplamı LINENET; başlık NETTOTAL ile karıştırma.
- **Açık alacak / alacak yaşlandırması bu veride fatura bazında yapılamaz (ölçüm 2026-09-16).** Logo yaşlandırması ödeme planı satırlarının kapatılmasına (PAYTRANS.CROSSREF / PAID, "borç kapama") dayanır. 2026 kopyasında plan satırlarının hiçbiri kapatılmamış. Bunlar sağlanamıyorsa NO_SQL.
- **Gerçekleşen tahsilat süresi 2026 için ölçülemez:** kapatan ödeme kaydı (CROSSREF) yok. Planlanan vade hesaplanabilir.
"""


def test_the_reason_is_read_from_wherever_the_model_put_it():
    assert no_sql_reason("NO_SQL: alacak yaşlandırması için borç kapama verisi yok") == "alacak yaşlandırması için borç kapama verisi yok"
    assert no_sql_reason("```sql\n-- yorum: 'alacak' → CLFLINE\nNO_SQL alacak yaşlandırması için borç kapama (PAYTRANS.CROSSREF) verisi yok\n```").startswith("alacak yaşlandırması")
    assert no_sql_reason("SELECT 1") == ""


def test_a_reason_resting_on_a_caveat_shows_that_caveat():
    out = caveat_for("alacak yaşlandırması için borç kapama verisi yok, plan satırları kapatılmamış", RULES)
    assert out.startswith("Açık alacak / alacak yaşlandırması bu veride fatura bazında yapılamaz")
    assert "Logo yaşlandırması ödeme planı satırlarının kapatılmasına" in out
    assert "NO_SQL" not in out and "**" not in out
    assert "2026 kopyasında plan satırlarının hiçbiri kapatılmamış" in out, "the second sentence carries the measurement"


def test_a_reason_the_pack_never_documented_shows_nothing():
    assert caveat_for("müşteri segmenti tanımı katalogda yok", RULES) == ""
    assert caveat_for("", RULES) == ""
    assert caveat_for("borç kapama verisi yok", "") == ""


def test_an_empty_result_is_explained_by_the_caveat_its_readings_point_at():
    from semantic_layer.runtime.compiler import empty_result_note
    sql = ("-- yorum: 'tahsilat' → kapatan ödeme kaydı (CROSSREF) ile fatura tarihi arasındaki gün farkı, gerçekleşen tahsilat süresi\n"
           "SELECT AVG(1) FROM PAYTRANS")
    note = empty_result_note(sql, RULES)
    assert note.startswith(" Muhtemel neden (bilgi paketi): Gerçekleşen tahsilat süresi 2026 için ölçülemez"), note
    assert empty_result_note("SELECT 1 FROM X", RULES) == ""
    assert empty_result_note("-- yorum: 'kanal' → CLCARD.SPECODE2\nSELECT 1", RULES) == ""


def test_a_caveat_beats_the_metric_definition_it_shares_words_with():
    out = caveat_for("gerçekleşen tahsilat süresi: kapatan ödeme CROSSREF ile fatura tarihi arasındaki gün farkı", RULES)
    assert out.startswith("Gerçekleşen tahsilat süresi 2026 için ölçülemez"), out


def test_a_missing_date_column_is_answered_with_the_tables_real_dates():
    """2026-09-17, soru 10: the model wrote DATE_ and CANCELLED on a work-order table that has neither;
    two repairs guessed again. The hint now names the table's date columns and says there is no state column."""
    from semantic_layer.models import ColumnProfile, SchemaProfile
    from semantic_layer.runtime.compiler import ExistingCompiler
    prof = SchemaProfile(datasource_id="d", table_name="LG_411_DISPLINE", table_pattern="LG_{n0}_DISPLINE", entity="DISPLINE", schema_name="dbo",
                         columns=[ColumnProfile(name=n, data_type=t) for n, t in [("LOGICALREF", "int"), ("WSREF", "int"), ("PLNDURATION", "float"),
                                  ("ACTDURATION", "float"), ("ACTBEGDATE", "datetime"), ("OPDUEDATE", "datetime")] + [(f"C{i}", "float") for i in range(70)]],
                         context={"n0": "411"})
    c = ExistingCompiler(llm=None, profiles=[prof], context={})
    hint = c.column_hint("SELECT SUM(d.ACTDURATION) FROM DISPLINE d WHERE d.DATE_ >= '2026-08-01' AND d.CANCELLED = 0",
                         "Invalid column name 'DATE_'. Invalid column name 'CANCELLED'.")
    assert "ACTBEGDATE" in hint and "OPDUEDATE" in hint and "tarih kolonları" in hint, hint
    assert "durum kolonu bulunmuyor" in hint, hint
    # the model's own (wrong) copy spelling still reaches the entity's columns
    hint2 = c.column_hint("SELECT SUM(d.ACTDURATION) FROM [dbo].[LG_211_01_DISPLINE] AS d WHERE d.CANCELLED = 0", "Invalid column name 'CANCELLED'.")
    assert "durum kolonu bulunmuyor" in hint2, hint2


def test_an_unclosed_sql_fence_is_still_the_models_sql():
    """2026-09-17, soru 12: a correct two-subquery statement ran past the token budget; without the
    closing fence it was read as 'no SQL' and the question refused."""
    from semantic_layer.runtime.compiler import extract_sql
    cut = "```sql\n-- yorum: 'devir' → stok devir hızı\nSELECT TOP 20 it.CODE FROM ITEMS it LEFT JOIN (SELECT s.STOCKREF FROM STLINE s"
    out = extract_sql(cut)
    assert out is not None and out.startswith("-- yorum") and "SELECT TOP 20" in out, out
    assert extract_sql("```sql\nNO_SQL: tanım yok\n```") is None


def test_the_caveat_that_shares_the_distinctive_words_wins_not_the_longest():
    """2026-09-18, soru 26: a minimum-stock question was answered with the receivables-ageing caveat — both
    share 'veride', 'ölçüm', 'yapılamaz'; only one speaks of 'asgari stok seviyesi'."""
    from semantic_layer.runtime.compiler import caveat_for
    rules = ("- Açık alacak / alacak yaşlandırması bu veride fatura bazında yapılamaz (ölçüm 2026-09-16): Logo yaşlandırması ödeme planı "
             "satırlarının kapatılmasına dayanır. 2026 kopyasında plan satırlarının hiçbiri kapatılmamış; veride tanımlı değil.\n"
             "- Asgari / azami stok seviyesi bu veride tanımlı değil (ölçüm 2026-09-18): INVDEF.MINLEVEL malzeme–ambar satırlarının "
             "hiçbirinde sıfırdan büyük değil. Asgari stok seviyesinin altına düşen malzemeler sorusu bu yüzden boş döner.\n")
    reason = "Asgari stok seviyesi bu veride tanımlı değil (ölçüm): INVDEF.MINLEVEL hiçbir malzeme satırında sıfırdan büyük değil, hesaplanamaz."
    assert caveat_for(reason, rules).startswith("Asgari"), caveat_for(reason, rules)
