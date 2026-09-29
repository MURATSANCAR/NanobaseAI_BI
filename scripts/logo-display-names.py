#!/usr/bin/env python3
"""Logo tablo/kolon adlarının ekrandaki Türkçe karşılığı: configs/schemas/logo-ldds.json → src/canvas/components/logoNames.json.

Ön yüzdeki başlık çevirici (`src/canvas/components/readableName.ts`) ham Logo adını (`CELLPHONE`, `ACCOUNTEDCNT`,
`LG_411_01_STFICHE`) okunur yazmak için bu haritayı kullanır; elle yazılmış liste değil, Logo'nun kendi alan sözlüğüdür.
Bir kolon adı birçok tabloda farklı açıklamayla geçerse en sık görülen açıklama seçilir. «Kullanımda değil», İngilizce
kalmış ya da boş açıklama alınmaz. Açıklama cümle düzenine çevrilir («Malzeme Kartı Referansı» → «Malzeme kartı»).

Logo sözlüğü değişince yeniden üretilir:  python3 scripts/logo-display-names.py
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "configs" / "schemas" / "logo-ldds.json"
OUT = ROOT / "src" / "canvas" / "components" / "logoNames.json"

_SKIP = re.compile(r"(?i)kullan[ıi]mda de[ğg]il|^logical reference$|^fiziksel adres$|^rezerve|^reserved")
# «… Ref.», «… Log. Ref.», «… Referansı», «… Referansi»: kolon o kaydı gösterir; başlıkta kaydın adı yeter.
_RAW_WORD = re.compile(r"\b[A-Z]{5,}\b")
_REF = re.compile(r"\s*(?:log(?:ical)?\.?\s*)?(?:ref\.?|referans[ıi]|referans|reference)\s*$", re.I)


def _lower_tr(w: str) -> str:
    return w.replace("I", "ı").replace("İ", "i").lower()


def sentence(text: str) -> str:
    """«Malzeme Kartı Referansı» → «Malzeme kartı»; kısaltma (KDV, GSM) büyük kalır."""
    t = _REF.sub("", " ".join(text.split())).strip(" .:-")
    if not t:
        return ""
    words = t.split(" ")
    out = []
    for i, w in enumerate(words):
        letters = re.sub(r"[^\w]", "", w)
        if len(letters) >= 2 and letters.isupper():
            out.append(w)
        elif i == 0:
            out.append(w[:1] + "/".join(_lower_tr(p) for p in w[1:].split("/")) if "/" in w else w[:1] + _lower_tr(w[1:]))
        else:
            out.append(_lower_tr(w))
    return " ".join(out)


def build() -> dict[str, dict[str, str]]:
    data = json.loads(SRC.read_text(encoding="utf-8"))["tables"]
    tables: dict[str, str] = {}
    cols: dict[str, Counter[str]] = defaultdict(Counter)
    for name, t in data.items():
        tr = (t.get("description_tr") or "").strip()
        if tr and not _SKIP.search(tr) and tr.lower() != (t.get("description") or "").strip().lower():
            s = sentence(tr)
            if s:
                tables[name] = s
        for col, c in (t.get("columns") or {}).items():
            tr = (c.get("description_tr") or "").strip()
            if not tr or _SKIP.search(tr) or tr.lower() == (c.get("description") or "").strip().lower():
                continue
            s = sentence(tr)
            # Açıklamada başka bir Logo tablo adı kalmışsa («DEMANDFICHE / sipariş fişleri», «… ITEMS») alınmaz.
            if s and "_" not in s and not _RAW_WORD.search(s):
                cols[col][s] += 1
    columns = {k: v.most_common(1)[0][0] for k, v in sorted(cols.items())}
    return {"tables": dict(sorted(tables.items())), "columns": columns}


if __name__ == "__main__":
    out = build()
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(out['tables'])} tablo, {len(out['columns'])} kolon")
