from scripts.enrich_crm_metadata import label_text


def test_source_language_priority_and_conflicting_published_labels():
    rows = [{'LanguageId': '1055', 'ObjectColumnName': 'DisplayName', 'Label': 'Sipariş'},
            {'LanguageId': '1033', 'ObjectColumnName': 'DisplayName', 'Label': 'Order'}]
    assert label_text(rows, 'DisplayName') == ('Sipariş', '1055')
    rows.append({'LanguageId': '1055', 'ObjectColumnName': 'DisplayName', 'Label': 'Fatura'})
    assert label_text(rows, 'DisplayName') == (None, 'CONFLICT')


def test_empty_metadata_is_not_a_business_definition():
    assert label_text([{'LanguageId': '1055', 'ObjectColumnName': 'Description', 'Label': ' '}], 'DisplayName') == (None, 'NO_LABEL')


def test_conflicting_display_aliases_can_use_identical_source_description():
    rows = [{'LanguageId': '1055', 'ObjectColumnName': 'LocalizedName', 'Label': 'Firma'},
            {'LanguageId': '1055', 'ObjectColumnName': 'LocalizedName', 'Label': 'Cari'},
            {'LanguageId': '1055', 'ObjectColumnName': 'Description', 'Label': 'Faturalanan işletme.'}]
    assert label_text(rows, 'LocalizedName') == ('Faturalanan işletme.', '1055')
