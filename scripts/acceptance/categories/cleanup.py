"""H1 Kategori ağacı kabulünün temizliği — test sunucusunda. `write_check.py`'nin kanıt dosyasıyla:

- `--propose` ile yazılan kitabın profil satırı yedeğe döner (öneri, durum, karar alanları);
- bu testin başladığı andan sonra o kitaba yazılmış `semantic_book_profile_events` satırları silinir;
- aynı andan sonra `--actor` (varsayılan timasai) adına yazılmış kategori değişiklik kaydı (`semantic_audit`, tür
  category_* / book_profile) satırları silinir;
- LLM kapısında bu kabulün açtığı biletler (modül `categories`, kullanıcı `--actor`) silinir.

Silinen satır sayıları JSON olarak yazılır; günlüğe geçirin. Başka oturumun kaydına dokunulmaz.

    python3 ../scripts/acceptance/categories/cleanup.py --evidence /tmp/claude-<oturum>/h1-write.json [--actor timasai]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import categories as C  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store import schema as S  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESTORE = ("status", "fields_json", "node_id", "proposed_at", "model_call_ids", "updated_by", "updated_at")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--actor", default="timasai")
    args = ap.parse_args()
    ev = json.loads(Path(args.evidence).read_text())
    since = datetime.fromisoformat(ev["startedAt"])
    s = SemanticSettings.from_env()
    engine = open_store(s.store_dsn, create=False).engine
    out: dict = {"since": ev["startedAt"]}
    backup = ev.get("backup")
    with engine.begin() as c:
        if backup:
            vals = {k: backup.get(k) for k in RESTORE}
            for k in ("proposed_at", "updated_at"):
                vals[k] = datetime.fromisoformat(vals[k]) if vals.get(k) else None
            out["profil"] = c.execute(C.PROFILES.update().where(C.PROFILES.c.tenant_id == ev["tenant"],
                                                                C.PROFILES.c.book_id == backup["book_id"]).values(**vals)).rowcount
            out["olay"] = c.execute(C.EVENTS.delete().where(C.EVENTS.c.tenant_id == ev["tenant"], C.EVENTS.c.book_id == backup["book_id"],
                                                            C.EVENTS.c.at >= since)).rowcount
        A = admin_mod.AUDIT.c
        out["degisiklikKaydi"] = c.execute(admin_mod.AUDIT.delete().where(
            A.actor == args.actor, A.at >= since,
            sa.or_(A.kind.like("category_%"), A.kind == "book_profile"))).rowcount
        Q = S.sl_llm_queue.c
        cols = S.sl_llm_queue.c.keys()
        if "module" in cols:
            cond = [Q.module == "categories", Q.status.in_(("DONE", "ABANDONED"))]
            if "enqueued_at" in cols:
                cond.append(Q.enqueued_at >= since)
            if "user_id" in cols:
                cond.append(Q.user_id == args.actor)
            out["llmBileti"] = c.execute(S.sl_llm_queue.delete().where(*cond)).rowcount
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
