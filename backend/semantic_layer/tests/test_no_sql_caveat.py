"""A refusal grounded in a documented caveat is explained in the operator's words, not the model's."""
from semantic_layer.runtime.compiler import caveat_for, no_sql_reason

RULES = """## Dikkat
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
