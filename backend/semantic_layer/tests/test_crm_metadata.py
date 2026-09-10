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


def test_a_code_keeps_the_source_word_for_it():
    from scripts.enrich_crm_metadata import option_labels
    rows = [{'Value': '100000001', 'LanguageId': '1055', 'Label': 'İptal Edildi'},
            {'Value': '100000001', 'LanguageId': '1033', 'Label': 'Cancelled'},
            {'Value': '1', 'LanguageId': '1055', 'Label': 'Taslak'}]
    assert option_labels(rows) == ({'100000001': 'İptal Edildi', '1': 'Taslak'}, '1055')


def test_a_code_published_under_two_words_is_left_unnamed():
    """Choosing between them would put a wrong word in front of every question reading the column."""
    from scripts.enrich_crm_metadata import option_labels
    rows = [{'Value': '1', 'LanguageId': '1055', 'Label': 'Taslak'},
            {'Value': '1', 'LanguageId': '1055', 'Label': 'Yeni'},
            {'Value': '2', 'LanguageId': '1055', 'Label': 'Sipariş'}]
    assert option_labels(rows) == ({'2': 'Sipariş'}, '1055')


def test_english_is_used_only_when_turkish_is_absent():
    from scripts.enrich_crm_metadata import option_labels
    rows = [{'Value': '1', 'LanguageId': '1033', 'Label': 'Active'}]
    assert option_labels(rows) == ({'1': 'Active'}, '1033')
    assert option_labels([]) == ({}, 'NO_LABEL')
