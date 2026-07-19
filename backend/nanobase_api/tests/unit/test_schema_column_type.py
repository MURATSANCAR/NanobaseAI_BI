from nanobase_api.schema_api import format_column_type


def test_varchar_length():
    assert (
        format_column_type(
            data_type="character varying",
            udt_name="varchar",
            character_maximum_length=50,
        )
        == "varchar(50)"
    )


def test_char_length():
    assert (
        format_column_type(data_type="character", udt_name="bpchar", character_maximum_length=3)
        == "char(3)"
    )


def test_numeric_precision_scale():
    assert (
        format_column_type(
            data_type="numeric",
            udt_name="numeric",
            numeric_precision=18,
            numeric_scale=2,
        )
        == "numeric(18,2)"
    )


def test_integer_no_size():
    assert format_column_type(data_type="integer", udt_name="int4") == "integer"


def test_text_ignores_length():
    assert (
        format_column_type(data_type="text", udt_name="text", character_maximum_length=None) == "text"
    )
