"""Did the mined rules land? Questions built from them are resolved and the slot is checked.

    rule_probe.py [--per-term 6] [--sample 400] [--out report.jsonl]

For every concept the rule miner certified, several questions are written the way people ask
(technical and everyday phrasing, with a breakdown and a period), resolved without the model, and
counted as reached when a slot lands on the concept's own entity and column/formula.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter, defaultdict
from datetime import date

from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.config import SemanticSettings
from semantic_layer.conventions import Conventions
from semantic_layer.models import ConceptStatus, SemanticType
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.store.catalog_store import open_store

BREAKDOWNS = ["kanal bazında", "müşteri bazında", "aylara göre", "ürün bazında", ""]
PERIODS = ["2026", "bu yıl", "geçen yıl", "son üç ay", "2025 yılında", ""]

TEMPLATES = {
    SemanticType.DIMENSION_VALUE: [
        "{p} {t} kaç tane?", "{t} sayısı {p} {b}", "{p} {b} {t} listesi", "{t} olanların toplamı {p}",
        "{t} kayıtları {b} göster", "kaç {t} var {p}?",
    ],
    SemanticType.METRIC: [
        "{p} {b} {t}", "{t} ne kadar {p}?", "{b} {t} toplamı {p}", "{t} geçen yıla göre arttı mı?",
        "en yüksek {t} olan on müşteri", "{p} {t} kırılımı {b}",
    ],
    SemanticType.COLUMN: [
        "{t} bazında satış {p}", "{t} nedir, listele", "{t} göre fatura sayısı {p}", "{b} {t} dağılımı",
        "{t} kırılımında ciro {p}", "{t} boş olan kayıtlar",
    ],
}


def questions(term: str, stype: str, k: int, rnd: random.Random) -> list[str]:
    out = []
    for tpl in rnd.sample(TEMPLATES[stype], min(k, len(TEMPLATES[stype]))):
        q = tpl.format(t=term, b=rnd.choice(BREAKDOWNS), p=rnd.choice(PERIODS))
        out.append(" ".join(q.split()))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--per-term", type=int, default=4)
    ap.add_argument("--sample", type=int, default=0, help="probe only N concepts (random)")
    ap.add_argument("--out", default="")
    ap.add_argument("--seed", type=int, default=16)
    args = ap.parse_args()
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn, create=False)
    profiles = one_entity_per_pattern(store.list_profiles(s.datasource_id), store.concept_entities(s.tenant_id, s.datasource_id))
    resolver = SemanticResolver(store, s.tenant_id, s.datasource_id, profiles, conventions=Conventions.from_profiles(profiles))
    mined = []
    for c in store.find_concepts(s.tenant_id, s.datasource_id, status=ConceptStatus.CERTIFIED, limit=100000):
        if (c.explain or {}).get("human_certified_by") != "rule-miner":
            continue
        maps = store.list_mappings(c.id)
        if maps:
            mined.append((c, maps[0]))
    rnd = random.Random(args.seed)
    if args.sample and len(mined) > args.sample:
        mined = rnd.sample(mined, args.sample)
    t0 = time.time()
    rows, tally = [], defaultdict(Counter)
    for c, m in mined:
        for q in questions(c.term, c.semantic_type, args.per_term, rnd):
            sq = resolver.resolve(q, today=date(2026, 9, 16))
            hit = any(sl.mapping is not None and sl.mapping.entity == m.entity
                      and (sl.mapping.formula == m.formula if m.formula else (sl.mapping.column or "").upper() == (m.column or "").upper())
                      for sl in list(sq.slots) + list(sq.group_by))
            elsewhere = sorted({sl.mapping.entity for sl in sq.slots if sl.mapping is not None and sl.mapping.entity != m.entity
                                and sl.semantic_type != SemanticType.DEFAULT_FILTER})
            tally[c.semantic_type]["hit" if hit else "miss"] += 1
            rows.append({"term": c.term, "type": c.semantic_type, "entity": m.entity, "q": q, "hit": hit,
                         "other_entities": elsewhere, "unresolved": sq.unresolved})
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = {t: {"hit": v["hit"], "miss": v["miss"], "rate": round(v["hit"] / max(1, v["hit"] + v["miss"]), 3)} for t, v in tally.items()}
    print(json.dumps({"concepts": len(mined), "questions": len(rows), "by_type": summary, "seconds": round(time.time() - t0, 1)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
