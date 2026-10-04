import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from import_logo_additions import ADDITIONS, merge


BASE = {"tables": {
    "INVOICE": {"physical": "LG_INVOICE", "level": "period", "scope": "period", "columns": {
        "EINVOICE": {"type": "Integer", "description": "e-Invoice", "values": {"0": "No", "1": "Yes"}},
        "GENEXP1": {"type": "String", "description_tr": "Açıklama 1", "description": "Explanation 1"}}}}}
ADD = {"generated_at": "2026-10-03", "tables": {
    "INVOICE": {"scope": "period", "physical": "LG_INVOICE", "columns": {
        "EINVOICE": {"description_tr": "Faturanın kesiliş biçimi", "confidence": "verified", "verified": "kanıt",
                     "values_tr": {"0": "Kağıt fatura", "1": "e-Fatura", "2": "e-Arşiv fatura"}},
        "GENEXP1": {"description_tr": "Web açıklaması", "confidence": "medium", "web_source": "https://x"},
        "TOTALSERVICES": {"description_tr": "Hizmet satırları toplamı", "confidence": "verified", "verified": "kanıt"}}},
    "EARCHIVEDET": {"scope": "period", "physical": "LG_EARCHIVEDET", "description_tr": "e-Arşiv ayrıntısı",
                    "web_source": "https://y", "confidence": "high",
                    "columns": {"SENDMOD": {"description_tr": "Gönderim şekli", "confidence": "verified", "verified": "kanıt",
                                            "values_tr": {"1": "Kağıt", "2": "Elektronik"}}}}}}


def test_documented_text_fills_gaps_but_never_displaces_existing_words():
    data = copy.deepcopy(BASE)
    merge(data, ADD)
    assert data["tables"]["INVOICE"]["columns"]["GENEXP1"]["description_tr"] == "Açıklama 1"
    assert data["tables"]["INVOICE"]["columns"]["TOTALSERVICES"]["description_tr"] == "Hizmet satırları toplamı"


def test_codes_read_from_live_data_replace_the_vendor_guess_and_are_audited():
    data = copy.deepcopy(BASE)
    audit = merge(data, ADD)
    col = data["tables"]["INVOICE"]["columns"]["EINVOICE"]
    assert col["values_tr"]["2"] == "e-Arşiv fatura" and "values" not in col and col["verified"] == "kanıt"
    assert audit["replaced_codes"]["INVOICE.EINVOICE"] == {"0": "No", "1": "Yes"}


def test_new_tables_keep_their_scope_and_source_and_rerun_is_a_no_op():
    data = copy.deepcopy(BASE)
    merge(data, ADD)
    t = data["tables"]["EARCHIVEDET"]
    assert (t["physical"], t["scope"], t["description_tr"]) == ("LG_EARCHIVEDET", "period", "e-Arşiv ayrıntısı")
    once = copy.deepcopy(data)
    audit = merge(data, ADD)
    assert data == once and not audit["tables_added"] and audit["columns_added"] == 0


def test_the_checked_in_additions_file_keeps_codes_numeric():
    additions = json.loads(ADDITIONS.read_text())
    for table in additions["tables"].values():
        assert table["scope"] in ("system", "firm", "period")
        for col in table["columns"].values():
            for code in col.get("values_tr", {}):
                int(code)
