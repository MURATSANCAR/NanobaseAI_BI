#!/usr/bin/env python3
"""Sorgu bilgisi envanterinin menü ve rota listesine karşı denetimi.

Kullanım (depo kökünden):
  python3 scripts/analiz/sorgu_bilgisi_envanter.py --list     # rota + menü listesi (TSV)
  python3 scripts/analiz/sorgu_bilgisi_envanter.py            # envanteri denetle; eksik varsa çıkış kodu 1

Kaynaklar:
- `src/App.tsx` içindeki her `<Route path="…">` (ve kök `index` rotası «/»).
- `src/canvas/nav/navModel.ts` içindeki her menü öğesinin `to:` adresi (sorgu parçası atılır).
- `docs/analiz/sorgu-bilgisi-envanteri.md`: her ekran satırı `` `/rota` `` biçiminde, tablonun ilk kolonunda.

Denetim: her rota ve her menü adresi envanterde en az bir satırın ilk kolonunda birebir geçmeli; envanterde olup
artık rotası olmayan satır da raporlanır. Yalnız dosya okur; ağ, veritabanı, servis yok.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "App.tsx"
NAV = ROOT / "src" / "canvas" / "nav" / "navModel.ts"
DOC = ROOT / "docs" / "analiz" / "sorgu-bilgisi-envanteri.md"

_ROUTE = re.compile(r'<Route\s+path="([^"]+)"\s+element=\{<([A-Za-z0-9_]+)')
_INDEX = re.compile(r'<Route\s+index\s+element=\{<([A-Za-z0-9_]+)')
_NAV = re.compile(r"\bto:\s*'([^']+)'")
_ROW = re.compile(r"^\|\s*`(/[^`]*)`")


def routes() -> list[tuple[str, str]]:
    text = APP.read_text(encoding="utf-8")
    out: list[tuple[str, str]] = []
    for m in _INDEX.finditer(text):
        out.append(("/", m.group(1)))
    for m in _ROUTE.finditer(text):
        path = m.group(1)
        if path == "*":
            continue
        out.append(("/" + path.lstrip("/"), m.group(2)))
    return out


def nav_targets() -> list[str]:
    text = NAV.read_text(encoding="utf-8")
    seen: list[str] = []
    for m in _NAV.finditer(text):
        target = m.group(1).split("?")[0].split("#")[0] or "/"
        if target not in seen:
            seen.append(target)
    return seen


def doc_rows() -> set[str]:
    if not DOC.exists():
        return set()
    rows: set[str] = set()
    for line in DOC.read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line.strip())
        if m:
            rows.add(m.group(1))
    return rows


def matches(pattern: str, target: str) -> bool:
    """`/a/:x` kalıbı `/a/b` adresini karşılar mı (`*` sonrası her şeyi)."""
    ps, ts = pattern.strip("/").split("/"), target.strip("/").split("/")
    for i, seg in enumerate(ps):
        if seg == "*":
            return True
        if i >= len(ts):
            return False
        if not seg.startswith(":") and seg != ts[i]:
            return False
    return len(ps) == len(ts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="rota ve menü listesini yaz")
    args = ap.parse_args()
    rs = routes()
    nav = nav_targets()
    if args.list:
        for path, comp in rs:
            print(f"route\t{path}\t{comp}")
        for target in nav:
            print(f"nav\t{target}")
        return 0
    rows = doc_rows()
    route_paths = {p for p, _ in rs}
    missing_routes = sorted(p for p in route_paths if p not in rows)
    # Menü adresi ya birebir rotadır ya da parametreli bir rotaya düşer (/pazar-arastirma/rakipler → /:section);
    # ikinci durumda o rotanın satırı yeter.
    missing_nav = sorted(t for t in nav if t not in rows and not any(matches(p, t) and p in rows for p in route_paths))
    stale = sorted(r for r in rows if r not in route_paths)
    print(f"rota {len(route_paths)} · menü adresi {len(nav)} · envanter satırı {len(rows)}")
    for p in missing_routes:
        print(f"EKSİK rota: {p}")
    for t in missing_nav:
        print(f"EKSİK menü adresi: {t}")
    for r in stale:
        print(f"ROTASI YOK (envanterde fazla): {r}")
    ok = not missing_routes and not missing_nav and not stale
    print("TAMAM: eksik ekran yok" if ok else "EKSİK VAR")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
