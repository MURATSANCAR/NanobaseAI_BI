"""A breakdown asked together with its total states the total of the rows it shows."""
from semantic_layer.runtime.compiler import fast_summary


def _rows():
    return [{"unvan": "A", "tutar": 10.0}, {"unvan": "B", "tutar": 5.5}]


def test_total_is_stated_when_the_question_asks_for_it():
    out = fast_summary("bekleyen toplam tutar ve en çok bekleyen müşteri", ["unvan", "tutar"], _rows(), 2)
    assert "Genel toplam (Tutar): 15,50" in out


def test_no_total_without_the_word_or_with_partial_rows():
    assert "Genel toplam" not in fast_summary("müşteri bazında tutar", ["unvan", "tutar"], _rows(), 2)
    assert "Genel toplam" not in fast_summary("toplam tutar", ["unvan", "tutar"], _rows(), 40)


def test_a_ratio_is_never_summed():
    rows = [{"unvan": "A", "iade_orani": 0.1}, {"unvan": "B", "iade_orani": 0.2}]
    assert "Genel toplam" not in fast_summary("toplam iade oranı", ["unvan", "iade_orani"], rows, 2)
