"""Köprü modüllerinde tanımsız global ad yok.

2026-09-29 kabulünde kurul oturumu ekranı her açılışta 500 veriyordu: uç `IZ.izli(..., text=T_OTURUM)` çağırıyor, ama
modül ne `IZ`'yi içe aktarmış ne `T_OTURUM`'u tanımlamıştı. Python bunu yalnız satır koşunca fark eder; modülün testleri
uç katmanını çağırmadığı için hata canlıya çıktı. Bu test her modülün her fonksiyonunda okunan global adların modülde
tanımlı (içe aktarma, atama, def/class) ya da yerleşik olduğunu derleyicinin sembol tablosuyla denetler; uçlar çağrılmadan
aynı sınıftaki bütün hatalar yakalanır.
"""
from __future__ import annotations

import builtins
import symtable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "semantic_bridge"
BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__", "__package__", "__path__",
                                 "__builtins__", "__loader__", "__annotations__", "__dict__", "__module__",
                                 "__qualname__", "__class__"}


def _module_names(top: symtable.SymbolTable) -> set[str]:
    return {s.get_name() for s in top.get_symbols() if s.is_assigned() or s.is_imported() or s.is_namespace()}


def _walk(t: symtable.SymbolTable):
    yield t
    for c in t.get_children():
        yield from _walk(c)


def _undefined(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    if "import *" in src:
        return []
    top = symtable.symtable(src, str(path), "exec")
    defined = _module_names(top) | BUILTINS
    # Fonksiyon içinde `global x` ile atanan ad da modül adıdır.
    for t in _walk(top):
        for s in t.get_symbols():
            if s.is_declared_global() and s.is_assigned():
                defined.add(s.get_name())
    out = []
    for t in _walk(top):
        if t.get_type() == "module":
            continue
        for s in t.get_symbols():
            # Parametre hiçbir zaman tanımsız değildir. Python 3.12'nin sembol tablosu, adı «top» olan fonksiyonun
            # parametrelerini global işaretliyor (modül kapsamının iç adı da «top»): ilk_baski_pazar.top yanlış alarm verdi.
            if s.is_parameter():
                continue
            if s.is_referenced() and s.is_global() and not s.is_assigned() and s.get_name() not in defined:
                out.append(f"{path.name}:{t.get_name()}: {s.get_name()}")
    return out


MODULES = sorted(p for p in ROOT.rglob("*.py") if "tests" not in p.parts)


@pytest.mark.parametrize("path", MODULES, ids=lambda p: str(p.relative_to(ROOT)))
def test_module_has_no_undefined_globals(path: Path):
    assert _undefined(path) == []


def test_function_named_top_is_not_a_false_alarm(tmp_path: Path):
    ok = tmp_path / "ok.py"
    ok.write_text("def top(rows, n=3):\n    known = [r for r in rows if r]\n    return known[:n]\n", encoding="utf-8")
    assert _undefined(ok) == []


def test_checker_catches_the_board_session_bug(tmp_path: Path):
    bad = tmp_path / "bad.py"
    bad.write_text("import os\n\ndef f(engine):\n    return IZ.izli(engine, text=T_OTURUM), os.sep\n", encoding="utf-8")
    assert _undefined(bad) == ["bad.py:f: IZ", "bad.py:f: T_OTURUM"]
