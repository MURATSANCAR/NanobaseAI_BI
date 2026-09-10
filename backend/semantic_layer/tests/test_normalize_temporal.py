from datetime import date

from semantic_layer.normalize import alias_tokens, clauses, fold, normalize_term, stem, tokenize
from semantic_layer.runtime.temporal import parse_temporal


def test_fold_and_tokenize_turkish():
    assert fold("Toptan SATIŞLARI İade") == "toptan satislari iade"
    assert tokenize("Kanal bazında, net ciro?") == ["kanal", "bazinda", "net", "ciro"]


def test_stem_is_symmetric_and_protects_short_terms():
    assert stem("toptan") == "toptan"
    assert stem("satislari") == stem("satis") == "satis"
    assert stem("musterinin") == stem("musteri")
    assert normalize_term("Net Ciroya") == normalize_term("net ciro")


def test_clauses_and_alias_tokens():
    assert clauses("iade tutarı, aynı müşterinin (2026) satış") == ["iade tutarı", "aynı müşterinin", "2026", "satış"]
    assert alias_tokens("perakende_toplam") == ["perakende", "toplam"]
    assert alias_tokens("netCiro") == ["net", "ciro"]


def test_temporal_primitives():
    today = date(2026, 9, 6)
    slots, grain = parse_temporal("Son 30 günde toptan satış", today)
    assert slots[0].primitive == "LAST_N_DAYS" and slots[0].start == date(2026, 8, 7) and slots[0].end == date(2026, 9, 7)
    slots, grain = parse_temporal("2026 Ocak–Ağustos için ay bazında iskonto oranı", today)
    assert slots[0].primitive == "MONTH_RANGE" and slots[0].start == date(2026, 1, 1) and slots[0].end == date(2026, 9, 1) and grain == "MONTH"
    slots, _ = parse_temporal("Temmuz 2026'da en çok satan 15 kitap", today)
    assert slots[0].primitive == "MONTH" and slots[0].start == date(2026, 7, 1) and slots[0].end == date(2026, 8, 1)
    slots, _ = parse_temporal("geçen ay net ciro", today)
    assert slots[0].primitive == "LAST_MONTH" and slots[0].start == date(2026, 8, 1) and slots[0].end == date(2026, 9, 1)
    slots, _ = parse_temporal("yıl başından beri ciro", today)
    assert slots[0].primitive == "YTD" and slots[0].start == date(2026, 1, 1)


def test_ambiguous_recent_is_not_guessed():
    slots, _ = parse_temporal("Günlük satış tutarı (son günler) nedir?", date(2026, 9, 6))
    amb = [s for s in slots if s.ambiguous]
    assert amb and amb[0].primitive == "AMBIGUOUS_RECENT" and amb[0].start is None
