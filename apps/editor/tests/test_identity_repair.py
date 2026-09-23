"""identity.repair: sözleşmenin mekanik ihlalleri deterministik onarılır, içerik kararı verilmez."""
import importlib.util, sys, types, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))


class _Stub(types.ModuleType):
    """psycopg/httpx kurulu olmayan makinede (Mac) yalnız import için taklit; kuruluysa dokunulmaz."""
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


def _missing(root: str) -> bool:
    try:
        return importlib.util.find_spec(root) is None
    except ValueError:  # aynı oturumda önceden taklit edilmiş
        return False


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool", "httpx", "yaml"):
    if _missing(_mod.split(".")[0]) or _mod.split(".")[0] in sys.modules and isinstance(sys.modules[_mod.split(".")[0]], _Stub):
        sys.modules.setdefault(_mod, _Stub(_mod))
from editor.identity import repair, contract  # noqa: E402

IDS = {f"m{i}" for i in range(6)}


def _out(chars, unresolved=(), conflicts=()):
    return {"characters": [{"canonical_name": n, "mention_ids": ms} for n, ms in chars],
            "unresolved_mention_ids": list(unresolved), "conflicts": list(conflicts)}


def test_duplicate_goes_unresolved_not_to_first_group():
    out = _out([("Levent", ["m0", "m1", "m3"]), ("Mert", ["m2", "m3"])], ["m4", "m5"])
    fixed, notes = repair(out, IDS)
    assert contract(fixed, IDS) == []
    assert "m3" in fixed["unresolved_mention_ids"]
    assert all("m3" not in ch["mention_ids"] for ch in fixed["characters"])
    assert notes["duplicates_unresolved"] == ["m3"]


def test_missing_goes_unresolved_and_unknown_dropped():
    out = _out([("Levent", ["m0", "m9"])], ["m1"])
    fixed, notes = repair(out, IDS)
    assert contract(fixed, IDS) == []
    assert set(fixed["unresolved_mention_ids"]) == {"m1", "m2", "m3", "m4", "m5"}
    assert notes["unknown_dropped"] == ["m9"] and set(notes["missing_unresolved"]) == {"m2", "m3", "m4", "m5"}


def test_group_emptied_by_repair_is_dropped_and_valid_stays_untouched():
    out = _out([("A", ["m0", "m1"]), ("B", ["m1"])], ["m2", "m3", "m4", "m5"])
    fixed, notes = repair(out, IDS)
    assert [c["canonical_name"] for c in fixed["characters"]] == ["A"]
    assert fixed["characters"][0]["mention_ids"] == ["m0"] and notes["empty_groups_dropped"] == 1
    good = _out([("A", ["m0", "m1"]), ("B", ["m2"])], ["m3", "m4", "m5"], [{"mention_id": "m3"}])
    fixed2, notes2 = repair(good, IDS)
    assert fixed2 == good and notes2["duplicates_unresolved"] == [] and notes2["unknown_dropped"] == []


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"): v(); print("ok", k)
