"""What a proposed reading may claim, checked against what was measured.

Every case here is one our own model actually produced on a live schema. They are kept as the
measurements that refute them, not as the columns they came from — the same shapes appear in any
database, and the check has to hold there too.
"""

from semantic_layer.candidates.generator import CandidateGenerator as G
from semantic_layer.models import ColumnProfile


def col(name, values, distinct=None, sentinels=()):
    return ColumnProfile(name=name, data_type="smallint", top_values=list(values),
                         distinct_count=distinct if distinct is not None else len(values),
                         sentinel_values=list(sentinels))


def test_gloss_that_only_repeats_its_own_code_is_dropped():
    c = col("MODIFIEDBY", [("47", 1304621), ("3", 937134), ("15", 815303)], distinct=51)
    _, glosses, _, notes = G._vet_reading(c, "Kaydı değiştiren kullanıcı",
                                          {"47": "Kullanıcı ID 47", "3": "Kullanıcı ID 3"}, 0.7)
    assert glosses == {}
    assert any("tekrar" in n for n in notes)


def test_free_text_column_gets_no_code_list():
    # thousands of distinct values: the eight we saw are examples, not a code list
    c = col("SPECODE", [("", 1800228), (".", 797), ("15201.01.5323", 114)], distinct=65)
    _, glosses, _, notes = G._vet_reading(c, "Özel kod", {"15201.01.5323": "Özel Referans Kodu"}, 0.85)
    assert glosses == {}
    assert any("serbest alan" in n for n in notes)


def test_two_codes_seen_equally_often_are_flagged_as_one_movement():
    # the transfer pair: an out-leg and an in-leg, equal by construction
    c = col("IOCODE", [("4", 9427120), ("1", 1350464), ("2", 627518), ("3", 627096)], distinct=5)
    _, glosses, conf, notes = G._vet_reading(
        c, "Hareketin yönü", {"2": "Çıkış", "3": "Transfer", "1": "Giriş", "4": "Sayım"}, 0.85)
    assert any("iki ayağı" in n for n in notes)
    assert conf <= 0.4


def test_reading_that_passes_over_most_of_the_column_says_so():
    c = col("CALCTYPE", [("0", 1699329), ("1", 10760), ("2", 10053)], distinct=3, sentinels=["0"])
    _, _, conf, notes = G._vet_reading(c, "Maliyet yöntemi",
                                       {"1": "ortalama maliyet", "2": "gerçek maliyet"}, 0.85)
    assert any("bu okumada yok" in n for n in notes)
    assert conf <= 0.5


def test_filler_glosses_are_dropped_but_the_real_ones_stay():
    c = col("LOGTYPE", [("7", 8672757), ("1", 692535), ("19", 570)], distinct=7)
    _, glosses, _, _ = G._vet_reading(c, "Kayıt türü",
                                      {"7": "Stok Hareketi", "1": "Sipariş Hareketi", "19": "Diğer"}, 0.7)
    assert glosses == {"7": "Stok Hareketi", "1": "Sipariş Hareketi"}


def test_a_hedged_reading_cannot_come_back_confident():
    c = col("TRCODE", [("4", 1809416), ("2", 11130)], distinct=6)
    _, _, conf, _ = G._vet_reading(c, "İşlem türü; 4 muhtemelen nakit işlemini temsil edebilir", {}, 0.6)
    assert conf <= 0.35


def test_a_sound_reading_passes_through_untouched():
    c = col("CANCELLED", [("0", 1828005), ("1", 2)], distinct=2)
    meaning, glosses, conf, notes = G._vet_reading(c, "Satırın iptal edilip edilmediği", {"1": "iptal edilmiş"}, 0.9)
    assert (meaning, glosses, conf, notes) == ("Satırın iptal edilip edilmediği", {"1": "iptal edilmiş"}, 0.9, [])
