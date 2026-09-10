"""Unit tests for chat → widget inference."""

from __future__ import annotations

from nanobase_api.chat_widgets import widgets_from_query_result


def test_single_scalar_becomes_kpi():
    widgets = widgets_from_query_result(
        columns=["total"],
        rows=[{"total": 42}],
        sql="SELECT COUNT(*) AS total FROM orders",
        title="Sipariş sayısı",
    )
    assert len(widgets) == 1
    assert widgets[0]["type"] == "kpi"
    assert widgets[0]["value_key"] == "total"
    assert widgets[0]["sql"]


def test_category_value_becomes_bar():
    widgets = widgets_from_query_result(
        columns=["city", "amount"],
        rows=[
            {"city": "Ankara", "amount": 10},
            {"city": "İstanbul", "amount": 20},
            {"city": "İzmir", "amount": 15},
        ],
        sql="SELECT city, amount FROM sales",
        title="Şehirlere göre",
    )
    assert widgets[0]["type"] == "pie"  # <= 8 rows → pie
    assert widgets[0]["x_key"] == "city"
    assert widgets[0]["y_key"] == "amount"


def test_time_series_becomes_line():
    widgets = widgets_from_query_result(
        columns=["order_date", "revenue"],
        rows=[
            {"order_date": "2024-01-01", "revenue": 100},
            {"order_date": "2024-02-01", "revenue": 120},
            {"order_date": "2024-03-01", "revenue": 90},
        ],
        sql="SELECT order_date, revenue FROM t",
        title="Aylık ciro",
    )
    assert widgets[0]["type"] == "line"


def test_empty_result_returns_no_widgets():
    assert widgets_from_query_result(columns=["a"], rows=[], sql="SELECT 1") == []


def test_code_and_name_columns_label_by_name():
    """Kod + ad birlikte gelince eksen adla etiketlenir (Logo: cari_kodu + unvan)."""
    widgets = widgets_from_query_result(
        columns=["cari_kodu", "unvan", "iade_tutari"],
        rows=[
            {"cari_kodu": "120.01.0001", "unvan": "DR MAĞAZACILIK A.Ş.", "iade_tutari": 4_200_000},
            {"cari_kodu": "120.01.0002", "unvan": "KİTAPYURDU DAĞITIM", "iade_tutari": 3_100_000},
        ],
        sql="SELECT cari_kodu, unvan, iade_tutari FROM t",
        title="En çok iade alan müşteriler",
    )
    assert widgets[0]["x_key"] == "unvan"
    assert widgets[0]["label_key"] == "unvan"
    assert widgets[0]["y_key"] == "iade_tutari"


def test_two_code_like_columns_falls_back_to_first():
    """Açıklayıcı kolon yoksa davranış değişmez — ilk kategori kolonu kullanılır."""
    widgets = widgets_from_query_result(
        columns=["kanal", "sube", "net"],
        rows=[{"kanal": "BAYI", "sube": "A", "net": 10}, {"kanal": "WEB", "sube": "B", "net": 20}],
        sql="SELECT kanal, sube, net FROM t",
        title="Kanal",
    )
    assert widgets[0]["x_key"] == "kanal"
