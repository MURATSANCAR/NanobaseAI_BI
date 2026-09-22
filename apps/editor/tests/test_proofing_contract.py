"""Son okuma denetimlerinin sözleşmesi — modülleri yüklemeden, kaynak üstünde.

Her denetim modülü (editor/proofing/<ad>.py, alt çizgisiz) şunları taşımalı:
  NAME (dosya adıyla aynı), VERSION, LABEL (Türkçe, boş değil) ve `async def run(generation_id)`.
Etiket okuyucu (`_labels.labels`) bu modülleri yüklemeden aynı sözlüğü vermeli.
Modüller PyMuPDF/numpy/psycopg çektiği için burada import edilmez; ölçüm GPU'da gerçek kitapla
yapılır (`python -m editor.proofing <gen> --dry`). Çalıştırma:

    python3 apps/editor/tests/test_proofing_contract.py   (ya da pytest)
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

PROOFING = Path(__file__).resolve().parents[1] / "src" / "editor" / "proofing"


def _load_labels_module():
    spec = importlib.util.spec_from_file_location("proofing_labels", PROOFING / "_labels.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_modules() -> list[Path]:
    return sorted(f for f in PROOFING.glob("*.py") if not f.name.startswith("_"))


def _constants_and_run(path: Path) -> tuple[dict[str, str], ast.AsyncFunctionDef | None]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    consts: dict[str, str] = {}
    run = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            consts[node.targets[0].id] = node.value.value
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            run = node
    return consts, run


def test_every_check_keeps_the_contract():
    mods = check_modules()
    assert mods, "denetim modülü bulunamadı"
    for f in mods:
        consts, run = _constants_and_run(f)
        assert consts.get("NAME") == f.stem, (f.name, consts.get("NAME"))
        assert re.fullmatch(r"\d+(\.\d+)*", consts.get("VERSION", "")), (f.name, consts.get("VERSION"))
        assert consts.get("LABEL", "").strip(), f.name
        assert run is not None, f"{f.name}: async def run yok"
        assert [a.arg for a in run.args.args] == ["generation_id"], (f.name, [a.arg for a in run.args.args])


def test_labels_read_without_importing_checks():
    labels = _load_labels_module().labels()
    expected = {f.stem: _constants_and_run(f)[0]["LABEL"] for f in check_modules()}
    assert labels == expected
    # denetim modüllerinden hiçbiri yüklenmedi
    assert not any(m.startswith("editor.proofing.") for m in sys.modules)


def test_no_book_specific_page_numbers_in_rules():
    """Bir sayfa numarasına bağlı koşul, tek kitaba oturtulmuş kuraldır."""
    rx = re.compile(r"page(?:_no)?\s*(?:==|!=|in\s*\()\s*\d")
    for f in list(check_modules()) + sorted(PROOFING.glob("_*.py")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            assert not rx.search(line), f"{f.name}:{i}: {line.strip()}"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
