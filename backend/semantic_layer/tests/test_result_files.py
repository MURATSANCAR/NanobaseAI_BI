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


def test_evicted_cache_results_leave_the_disk_and_space_is_freed(monkeypatch):
    """Önbellekten düşen sonuç dosyası silinir; alan dolunca en eski sonuçlar ve sahipsiz dosyalar temizlenir."""
    import threading
    import time
    from collections import OrderedDict
    from pathlib import Path
    from types import SimpleNamespace

    from semantic_bridge.app import Runtime
    from semantic_bridge.result_files import ResultFiles

    monkeypatch.setenv('SEMANTIC_RESULT_DISK_BYTES', '4000')
    monkeypatch.setenv('SEMANTIC_RESULT_MAX_BYTES', '1000')
    rf = ResultFiles()
    rt = SimpleNamespace(result_files=rf, _results=OrderedDict(), _complete_cache=OrderedDict(),
                         _results_lock=threading.RLock(), _result_ttl=1800.0)
    for name in ('_result_file_in_use', '_forget_cached', '_free_result_space', '_discard_result'):
        setattr(rt, name, getattr(Runtime, name).__get__(rt))

    def fill(tag):
        return rf.write(iter([(['x'], [{'x': tag * 900}])]))

    a, b, c = fill('a'), fill('b'), fill('c')
    rt._complete_cache['ka'] = (time.time(), a)
    rt._complete_cache['kb'] = (time.time(), b)
    rt._results['r'] = {'_result_file': b['_result_file'], 'at': time.time()}
    rt._forget_cached(*rt._complete_cache.popitem(last=False))      # a: yalnız önbellekte → silinir
    assert not Path(a['_result_file']).exists()
    rt._forget_cached(*rt._complete_cache.popitem(last=False))      # b: sonuç kaydı kullanıyor → kalır
    assert Path(b['_result_file']).exists()
    assert Path(c['_result_file']).exists()                          # c: sahipsiz
    fill('d'); fill('e')                                             # alan dolmak üzere
    rt._free_result_space()
    assert not Path(c['_result_file']).exists()                      # sahipsiz dosya önce gider
    used = sum(p.stat().st_size for p in Path(rf.directory.name).glob('*.jsonl'))
    assert used + rf.max_bytes <= rf.disk_budget
    fill('f')                                                        # yer açıldı: yazılabilir
