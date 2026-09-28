"""H2 Okuyucu veri tabanı kabulünün temizliği — test sunucusunda. `kabul.py`'nin kimlik dosyasıyla:

- kabulün açtığı segmentler ve gece sayımları (`semantic_reader_segments`, `semantic_reader_segment_snapshots`);
- kabulün yüklediği etkinlik dosyası: başlık, satırlar ve o yüklemenin okur olayları (`semantic_reader_imports`,
  `semantic_reader_import_rows`, `semantic_reader_events.ref`);
- kabul başladıktan sonra `--actor` (varsayılan timasai) adına yazılmış okur değişiklik kaydı satırları
  (`semantic_audit`, tür reader_* ve readers_sync).

Okur/bağ/izin tabloları modülün kendi durumudur (CRM'den türetilir), silinmez. Silinen satır sayıları JSON olarak
yazılır; günlüğe geçirin. Başka oturumun kaydına dokunulmaz.

    python3 scripts/acceptance/H2/cleanup.py --ids /tmp/claude-h2/kabul-kimlikler.json [--actor timasai]
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
from semantic_bridge import readers as R  # noqa: E402
from semantic_bridge import readers_imports as I  # noqa: E402
from semantic_bridge import readers_segments as S  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--actor", default="timasai")
    args = ap.parse_args()
    ev = json.loads(Path(args.ids).read_text())
    since = datetime.fromisoformat(ev["startedAt"])
    st = SemanticSettings.from_env()
    engine = open_store(st.store_dsn, create=False).engine
    tenant = ev.get("tenant") or st.tenant_id
    segs, imps = ev.get("segments") or [], ev.get("imports") or []
    out: dict = {"since": ev["startedAt"]}
    with engine.begin() as c:
        out["segmentSayimi"] = c.execute(S.SNAPSHOTS.delete().where(sa.and_(
            S.SNAPSHOTS.c.tenant_id == tenant, S.SNAPSHOTS.c.segment_id.in_(segs or ["-"])))).rowcount
        out["segment"] = c.execute(S.SEGMENTS.delete().where(sa.and_(
            S.SEGMENTS.c.tenant_id == tenant, S.SEGMENTS.c.id.in_(segs or ["-"])))).rowcount
        out["yuklemeSatiri"] = c.execute(I.IMPORT_ROWS.delete().where(I.IMPORT_ROWS.c.import_id.in_(imps or ["-"]))).rowcount
        out["olay"] = c.execute(R.EVENTS.delete().where(sa.and_(
            R.EVENTS.c.tenant_id == tenant, R.EVENTS.c.ref.in_(imps or ["-"])))).rowcount
        out["yukleme"] = c.execute(I.IMPORTS.delete().where(sa.and_(
            I.IMPORTS.c.tenant_id == tenant, I.IMPORTS.c.id.in_(imps or ["-"])))).rowcount
        A = admin_mod.AUDIT.c
        out["degisiklikKaydi"] = c.execute(admin_mod.AUDIT.delete().where(
            A.actor == args.actor, A.at >= since, sa.or_(A.kind.like("reader_%"), A.kind == "readers_sync"))).rowcount
        R._stamp(c, tenant)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
