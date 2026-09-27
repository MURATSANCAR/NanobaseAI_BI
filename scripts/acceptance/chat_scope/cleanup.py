#!/usr/bin/env python3
"""Zeki AI sohbet kapsamı kabulünün izlerini siler (kural: test verisi bırakılmaz).

`run_acceptance.py` her soruyu gerçek `/api/v1/ask` ucundan sorar; köprü her cevabı promt izleyiciye
(`sl_query_log`) yazar. Bu betik yalnız kanıt dosyasındaki `queryIds` satırlarını siler, başka satıra dokunmaz.
Sonuç önbelleği dosyaları köprünün kendi saklama süresiyle düşer; model kuyruğu satırları iş bitince kapanır.

  sudo systemd-run --wait --pipe -p EnvironmentFile=/etc/nanobase/semantic-bridge.env \
    -p WorkingDirectory=<kaynak>/backend python3 <kaynak>/scripts/acceptance/chat_scope/cleanup.py \
    --evidence /tmp/claude-<oturum>/chat-scope-evidence.json [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    ids = sorted({i for i in json.loads(Path(args.evidence).read_text(encoding="utf-8")).get("queryIds", []) if i})
    import sqlalchemy as sa
    from semantic_layer.config import SemanticSettings
    from semantic_layer.store import schema as S

    engine = sa.create_engine(SemanticSettings.from_env().store_dsn)
    with engine.begin() as c:
        found = c.execute(sa.select(sa.func.count()).select_from(S.sl_query_log)
                          .where(S.sl_query_log.c.id.in_(ids))).scalar() if ids else 0
        deleted = 0
        if ids and not args.dry_run:
            deleted = c.execute(sa.delete(S.sl_query_log).where(S.sl_query_log.c.id.in_(ids))).rowcount
        left = c.execute(sa.select(sa.func.count()).select_from(S.sl_query_log)
                         .where(S.sl_query_log.c.id.in_(ids))).scalar() if ids else 0
    print(json.dumps({"queryIds": len(ids), "found": found, "deleted": deleted, "left": left,
                      "dryRun": args.dry_run}, ensure_ascii=False))
    return 0 if args.dry_run or left == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
