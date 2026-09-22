"""Denetim etiketleri (LABEL) — denetim modüllerini YÜKLEMEDEN.

Kart servisi (card_api, salt okuma) bulguları ekrana verirken her denetimin Türkçe adını
gösterir. Denetim modülleri PyMuPDF, numpy, httpx ve modelleri çeker; kart servisinin
bunları yüklemesi gerekmez. Bu yüzden etiket, modülün kaynak dosyasından `ast` ile okunur:
`NAME = "..."` ve `LABEL = "..."` sabitleri; kod çalıştırılmaz. Modül yoksa ya da ayrıştırılamıyorsa
etiket = denetim adı.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _string_constants(path: Path) -> dict[str, str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}
    out: dict[str, str] = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            out[node.targets[0].id] = node.value.value
    return out


@lru_cache(maxsize=1)
def labels() -> dict[str, str]:
    """{NAME: LABEL} — paketteki her denetim modülü (alt çizgiyle başlamayanlar)."""
    out: dict[str, str] = {}
    for f in sorted(_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        c = _string_constants(f)
        if "NAME" in c and "LABEL" in c:
            out[c["NAME"]] = c["LABEL"]
    return out


def label_of(name: str) -> str:
    return labels().get(name, name)
