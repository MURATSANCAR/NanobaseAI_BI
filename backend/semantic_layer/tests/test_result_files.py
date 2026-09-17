"""A result bigger than what is kept is returned in part and said to be a part — never an error."""
from __future__ import annotations

import os


def test_a_result_over_the_row_cap_is_kept_up_to_the_cap_and_marked_truncated(monkeypatch):
    monkeypatch.setenv("SEMANTIC_RESULT_MAX_ROWS", "3")
    from semantic_bridge.result_files import ResultFiles
    rf = ResultFiles()
    batches = iter([([{"name": "n"}], [{"n": i} for i in range(10)])])
    out = rf.write(batches, preview_size=2)
    assert out["truncated"] is True and out["totalRows"] == 3 and out["records"] == [{"n": 0}, {"n": 1}], out
    assert rf.read(out["_result_file"]) == [{"n": 0}, {"n": 1}, {"n": 2}]


def test_a_result_under_the_cap_is_whole(monkeypatch):
    monkeypatch.setenv("SEMANTIC_RESULT_MAX_ROWS", "100")
    from semantic_bridge.result_files import ResultFiles
    out = ResultFiles().write(iter([([{"name": "n"}], [{"n": 1}, {"n": 2}])]))
    assert out["truncated"] is False and out["totalRows"] == 2
