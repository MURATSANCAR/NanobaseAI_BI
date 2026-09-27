"""SEO & GEO → CRM kitap kartı ve dijital hak kararı (semantic_bridge/seo_geo/crm.py)."""
from datetime import date

from semantic_bridge.seo_geo import crm

TODAY = date(2026, 9, 27)
ACTIVE = crm.ACTIVE_STATUS[0]


def c(**kw):
    base = {"status": ACTIVE, "ends": "2039-06-04", "open_ended": 0, "terminated": None, "internet": 1,
            "public_domain": 0, "rights_note": None, "parties": ["Yazar"]}
    return {**base, **kw}


def test_all_contracts_with_internet_right():
    assert crm.verdict([c(), c(parties=["Çizer"])], TODAY)[0] == "var"


def test_one_party_without_internet_right_names_the_party():
    decision, why = crm.verdict([c(), c(internet=0, parties=["Çevirmen X"])], TODAY)
    assert decision == "eksik" and "Çevirmen X" in why


def test_expired_or_terminated_contract_does_not_count():
    assert crm.verdict([c(ends="2020-01-01")], TODAY)[0] == "yok"
    assert crm.verdict([c(terminated="2025-01-01")], TODAY)[0] == "yok"
    assert crm.verdict([c(ends="2020-01-01", open_ended=1)], TODAY)[0] == "var"


def test_passive_status_does_not_count():
    assert crm.verdict([c(status=2)], TODAY)[0] == "yok"


def test_rights_note_asks_for_review():
    assert crm.verdict([c(rights_note="özel maddeler var")], TODAY)[0] == "incele"


def test_public_domain_without_contract():
    assert crm.verdict([c(status=2, public_domain=1)], TODAY)[0] == "koruma_disi"
    assert crm.verdict([], TODAY)[0] == "yok"


def test_status_flag_from_label_code():
    assert crm.status_flag("YS05 Artık Bizim Ürünümüz Değil") == "bizim_degil"
    assert crm.status_flag("YS11 Satıştan Çekildi") == "cekildi"
    assert crm.status_flag("YS04 Aktif") is None
    assert crm.status_flag(None) is None


def test_read_joins_books_contracts_and_parties():
    book_id, contract_id = "BB7C3A67-9C16-EF11-815C-00155D00A67C", "11111111-2222-3333-4444-555555555555"

    def execute(sql, limit):
        if "StringMap" in sql:
            rows = ([{"v": 100000004, "l": "YS04 Aktif"}] if "yayincilikstatusu" in sql
                    else [{"v": 1, "l": "Kitap"}] if "'new_tip'" in sql else [{"v": 1, "l": "Çocuk"}])
        elif "new_sozlesmetarafiBase" in sql:
            rows = [{"contract_id": contract_id.lower(), "person": "Metin Özdamarlar", "company": None}]
        elif "new_new_sozlesme_new_kitapBase" in sql:
            rows = [{"book_id": book_id.lower(), **c(parties=None), "id": contract_id, "name": "2024007147", "kind": 5,
                     "ebook": 1, "zbook": 1, "audiobook": 0}]
        else:
            rows = [{"id": book_id, "name": "İyilik Timi", "ean": "9786259834658", "isbn": "978-625-98346-5-8",
                     "status": 100000004, "kind": 1, "tsoft": 1, "audience": 1, "summary": "<p>İyilik&nbsp;peşinde</p>",
                     "preview_pdf": "https://cdn.timas.com.tr/preview/9786259834658.pdf",
                     "website": "https://www.youtube.com/embed/x", "youtube": None},
                    {"id": "x", "name": "Barkodsuz", "ean": "-", "status": None}]
        return [], rows, False

    out = crm.read("Timas_MSCRM.dbo", execute, TODAY)
    assert len(out) == 1
    b = out[0]
    assert b["ean"] == "9786259834658" and b["rights"] == "var" and b["statusFlag"] is None
    assert b["audience"] == "Çocuk" and b["summary"] == "İyilik peşinde"
    assert b["contracts"][0]["parties"] == ["Metin Özdamarlar"] and b["contracts"][0]["ebook"] is True
    assert b["video"] == "https://www.youtube.com/embed/x"


def test_truncated_crm_result_stops():
    import pytest

    with pytest.raises(RuntimeError):
        crm.read("Timas_MSCRM.dbo", lambda sql, limit: ([], [], True), TODAY)


def test_label_sql_scopes_by_entity():
    sql = crm.label_sql("Timas_MSCRM.dbo.", "new_hedefkitle")
    assert "Timas_MSCRM.MetadataSchema.Entity" in sql and "'new_kitap'" in sql


def test_non_book_and_set_kinds():
    assert crm.by_kind("yok", "x", "Pazarlama Materyalleri", "YS04 Aktif", False)[0] == "kitap_degil"
    assert crm.by_kind("yok", "x", "Kitap", "Ticari Ürün", False)[0] == "kitap_degil"
    assert crm.by_kind("yok", "x", "Set", "YS04 Aktif", False)[0] == "set"
    assert crm.by_kind("var", "x", "Set", "YS04 Aktif", True)[0] == "var"
    assert crm.by_kind("eksik", "x", "Kitap", "YS04 Aktif", True)[0] == "eksik"
