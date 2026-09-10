"""How a limited budget is spent when a source repeats the same tables per company or per year."""

from semantic_layer.profiler.profiler import _one_per_pattern


class _LT:
    def __init__(self, pattern): self.table_pattern = pattern


def setup(spec):
    """spec: {physical_table: (pattern, score)}"""
    tables = [("dbo", t) for t in spec]
    return tables, {t: sc for t, (_, sc) in spec.items()}, {t: _LT(pat) for t, (pat, _) in spec.items()}


def test_every_shape_is_read_before_any_shape_is_read_twice():
    # the same two shapes in three companies; the big one outranks the small one everywhere
    spec = {f"LG_{f}_INVOICE": ("INVOICE", 90 - f) for f in (1, 2, 3)}
    spec.update({f"LG_{f}_CLCARD": ("CLCARD", 10 - f) for f in (1, 2, 3)})
    tables, score, logical = setup(spec)
    picked = [t for _, t in _one_per_pattern(tables, score, logical, 2)]
    assert set(picked) == {"LG_1_INVOICE", "LG_1_CLCARD"}, picked


def test_within_a_shape_the_fullest_copy_is_the_one_read():
    spec = {"LG_1_INVOICE": ("INVOICE", 5), "LG_2_INVOICE": ("INVOICE", 50), "LG_3_INVOICE": ("INVOICE", 20)}
    tables, score, logical = setup(spec)
    assert [t for _, t in _one_per_pattern(tables, score, logical, 1)] == ["LG_2_INVOICE"]


def test_leftover_budget_goes_to_second_copies_biggest_first():
    spec = {"A1": ("A", 100), "A2": ("A", 80), "B1": ("B", 10)}
    tables, score, logical = setup(spec)
    picked = [t for _, t in _one_per_pattern(tables, score, logical, 3)]
    assert picked[:2] == ["A1", "B1"] and picked[2] == "A2"


def test_a_budget_larger_than_the_schema_keeps_everything():
    spec = {"A1": ("A", 1), "B1": ("B", 2)}
    tables, score, logical = setup(spec)
    assert len(_one_per_pattern(tables, score, logical, 99)) == 2
