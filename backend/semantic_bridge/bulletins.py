"""Kampüs sesli bülteni: sunucuda üretilen ses dosyaları Kampüs'teki oynatıcıda çalar.

Ses dosyası diskte durur (`KAMPUS_BULLETIN_DIR`, varsayılan `/data/nanobaseai/bi/var/bulletins`), bilgisi
`semantic_kampus_bulletins` tablosunda. İki giriş yolu var, ikisi de aynı `add`'e varır:

- Yönetim → Sesli bülten: yönetici dosyayı yükler (ham gövde, `POST /api/v1/admin/bulletins`).
- Sunucuda üretilen ses: `python -m semantic_bridge.bulletins add dosya.mp3 --title "…" --publish`
  (köprünün ortamıyla; bkz. `main`).

Eklenen bülten taslaktır; yayınlanınca Kampüs'te görünür. Kampüs en son yayınlananı çalar. Ses Range ile
verilir: iOS Safari aralık desteklemeyen adresteki sesi çalmaz, uzun bültende ileri sarmak da buna bağlı.
Biçim dosyanın ilk baytlarından anlaşılır (uzantıya güvenilmez). Süreyi ekleyen verir (ekran yüklerken
tarayıcıda ölçer, komut satırında `--duration`); sunucuda ffprobe yok. Süre bilinmese de ses çalar.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import sqlalchemy as sa
from starlette.responses import Response

_md = sa.MetaData()

BULLETINS = sa.Table(
    "semantic_kampus_bulletins", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("summary", sa.Text),
    sa.Column("episode", sa.Integer),
    sa.Column("voice", sa.String(200)),
    sa.Column("duration_sec", sa.Float),
    sa.Column("mime", sa.String(40), nullable=False),
    sa.Column("size", sa.BigInteger, nullable=False),
    sa.Column("sha256", sa.String(64), nullable=False),
    sa.Column("file_name", sa.String(200), nullable=False),
    sa.Column("original_name", sa.String(300)),
    sa.Column("source", sa.String(20), nullable=False),          # yükleme | sunucu
    sa.Column("status", sa.String(20), nullable=False),          # taslak | yayinda
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("published_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_semantic_kampus_bulletins_pub", "tenant_id", "status", "published_at"),
)

DRAFT, PUBLISHED = "taslak", "yayinda"
SOURCES = ("yükleme", "sunucu")
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")

_ready: set[int] = set()
_lock = threading.Lock()


class BulletinError(ValueError):
    """Ekrana olduğu gibi gidecek düz Türkçe hata."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def root() -> Path:
    return Path(os.environ.get("KAMPUS_BULLETIN_DIR") or "/data/nanobaseai/bi/var/bulletins")


def max_bytes() -> int:
    try:
        mb = int(os.environ.get("BULLETIN_MAX_MB") or 60)
    except ValueError:
        mb = 60
    return max(1, mb) * 1024 * 1024


def sniff(head: bytes) -> Optional[tuple[str, str]]:
    """(mime, uzantı) — ilk baytlardan; tanınmazsa None."""
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "audio/mpeg", "mp3"
    if head[4:8] == b"ftyp":
        return "audio/mp4", "m4a"
    if head[:4] == b"OggS":
        return "audio/ogg", "ogg"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav", "wav"
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(v: Any, n: int) -> Optional[str]:
    s = " ".join(str(v or "").split())
    return s[:n] or None


def _title_from(name: Optional[str]) -> str:
    stem = Path(name or "").stem.replace("_", " ").replace("-", " ").strip()
    return _clean(stem, 300) or "Sesli bülten"


def _duration(v: Any) -> Optional[float]:
    try:
        d = float(v)
    except (TypeError, ValueError):
        return None
    return round(d, 1) if 0 < d < 24 * 3600 else None


def to_api(row: Any) -> dict[str, Any]:
    r = dict(row._mapping if hasattr(row, "_mapping") else row)
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {
        "id": r["id"], "title": r["title"], "summary": r["summary"], "episode": r["episode"],
        "voice": r["voice"], "durationSec": r["duration_sec"], "mime": r["mime"], "size": r["size"],
        "source": r["source"], "status": r["status"], "originalName": r["original_name"],
        "createdBy": r["created_by"], "createdAt": iso(r["created_at"]), "publishedAt": iso(r["published_at"]),
        "updatedAt": iso(r["updated_at"]),
        # Sürüm parçası dosya değişince adresi değiştirir; tarayıcı eski sesi önbellekten çalmaz.
        "audioPath": f"/api/v1/bulletins/{r['id']}/audio?v={r['sha256'][:12]}",
    }


def add(engine: sa.engine.Engine, tenant: str, user: str, data: bytes, *, original_name: Optional[str] = None,
        title: Optional[str] = None, summary: Optional[str] = None, episode: Optional[int] = None,
        voice: Optional[str] = None, duration_sec: Any = None, source: str = "yükleme",
        publish: bool = False) -> dict[str, Any]:
    ensure(engine)
    if not data:
        raise BulletinError(422, "Ses dosyası boş.")
    if len(data) > max_bytes():
        raise BulletinError(413, f"Ses dosyası {max_bytes() // (1024 * 1024)} MB'tan büyük olamaz.")
    kind = sniff(data[:16])
    if not kind:
        raise BulletinError(415, "Bu bir ses dosyası değil ya da biçimi desteklenmiyor (mp3, m4a, ogg, wav).")
    mime, ext = kind
    bid = uuid.uuid4().hex[:16]
    folder = root()
    folder.mkdir(parents=True, exist_ok=True)
    fname = f"{bid}.{ext}"
    tmp = folder / f".{fname}.yaziliyor"
    tmp.write_bytes(data)
    tmp.replace(folder / fname)
    now = _now()
    row = {
        "id": bid, "tenant_id": tenant, "title": _clean(title, 300) or _title_from(original_name),
        "summary": _clean(summary, 2000), "episode": int(episode) if episode else None,
        "voice": _clean(voice, 200), "duration_sec": _duration(duration_sec),
        "mime": mime, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "file_name": fname,
        "original_name": _clean(original_name, 300), "source": source if source in SOURCES else "yükleme",
        "status": PUBLISHED if publish else DRAFT, "created_by": user[:120], "created_at": now,
        "published_at": now if publish else None, "updated_at": now,
    }
    try:
        with engine.begin() as c:
            c.execute(BULLETINS.insert().values(**row))
    except Exception:
        (folder / fname).unlink(missing_ok=True)
        raise
    return to_api(row)


def listing(engine: sa.engine.Engine, tenant: str, *, published_only: bool) -> list[dict[str, Any]]:
    ensure(engine)
    q = sa.select(BULLETINS).where(BULLETINS.c.tenant_id == tenant)
    if published_only:
        q = q.where(BULLETINS.c.status == PUBLISHED).order_by(BULLETINS.c.published_at.desc())
    else:
        q = q.order_by(BULLETINS.c.created_at.desc())
    with engine.connect() as c:
        return [to_api(r) for r in c.execute(q)]


def current(engine: sa.engine.Engine, tenant: str) -> Optional[dict[str, Any]]:
    items = listing(engine, tenant, published_only=True)
    return items[0] if items else None


def _row(engine: sa.engine.Engine, tenant: str, bid: str) -> Any:
    ensure(engine)
    with engine.connect() as c:
        row = c.execute(sa.select(BULLETINS).where(BULLETINS.c.id == bid, BULLETINS.c.tenant_id == tenant)).first()
    if row is None:
        raise BulletinError(404, "Bülten bulunamadı.")
    return row


def update(engine: sa.engine.Engine, tenant: str, bid: str, patch: dict[str, Any]) -> dict[str, Any]:
    row = _row(engine, tenant, bid)
    vals: dict[str, Any] = {"updated_at": _now()}
    if "title" in patch:
        title = _clean(patch["title"], 300)
        if not title:
            raise BulletinError(422, "Başlık boş olamaz.")
        vals["title"] = title
    if "summary" in patch:
        vals["summary"] = _clean(patch["summary"], 2000)
    if "voice" in patch:
        vals["voice"] = _clean(patch["voice"], 200)
    if "episode" in patch:
        ep = patch["episode"]
        try:
            vals["episode"] = int(ep) if ep not in (None, "") else None
        except (TypeError, ValueError):
            raise BulletinError(422, "Bölüm numarası sayı olmalı.") from None
    if "durationSec" in patch:
        vals["duration_sec"] = _duration(patch["durationSec"])
    if "status" in patch:
        st = patch["status"]
        if st not in (DRAFT, PUBLISHED):
            raise BulletinError(422, "Durum «taslak» ya da «yayinda» olmalı.")
        vals["status"] = st
        if st == PUBLISHED and row._mapping["status"] != PUBLISHED:
            vals["published_at"] = _now()
    with engine.begin() as c:
        c.execute(BULLETINS.update().where(BULLETINS.c.id == bid).values(**vals))
    return to_api(_row(engine, tenant, bid))


def remove(engine: sa.engine.Engine, tenant: str, bid: str) -> dict[str, Any]:
    row = _row(engine, tenant, bid)
    with engine.begin() as c:
        c.execute(BULLETINS.delete().where(BULLETINS.c.id == bid))
    (root() / row._mapping["file_name"]).unlink(missing_ok=True)
    return to_api(row)


def audio(engine: sa.engine.Engine, tenant: str, bid: str, range_header: Optional[str], *,
          published_only: bool) -> Response:
    """Tek aralıklı `Range` → 206; aralıksız → 200 bütün dosya. Taslak yalnız yöneticiye çalar."""
    row = _row(engine, tenant, bid)._mapping
    if published_only and row["status"] != PUBLISHED:
        raise BulletinError(404, "Bülten bulunamadı.")
    path = root() / row["file_name"]
    if not path.is_file():
        raise BulletinError(404, "Ses dosyası sunucuda yok.")
    size = path.stat().st_size
    base = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=86400"}
    m = RANGE.match((range_header or "").strip())
    if not m or (not m[1] and not m[2]) or size == 0:
        return Response(path.read_bytes(), media_type=row["mime"], headers=base)
    if m[1]:
        start = int(m[1])
        end = min(int(m[2]), size - 1) if m[2] else size - 1
    else:
        start, end = max(0, size - int(m[2])), size - 1
    if start >= size or start > end:
        return Response(status_code=416, headers={**base, "Content-Range": f"bytes */{size}"})
    with path.open("rb") as f:
        f.seek(start)
        chunk = f.read(end - start + 1)
    return Response(chunk, status_code=206, media_type=row["mime"],
                    headers={**base, "Content-Range": f"bytes {start}-{end}/{size}"})


# ------------------------------------------------------------------ komut satırı (sunucuda üretilen ses)

def main(argv: Optional[list[str]] = None) -> int:
    """Sunucuda üretilen sesi bülten olarak ekler ya da listeler. Köprünün ortamıyla koşar:

        set -a; . /etc/nanobase/semantic-bridge.env; set +a
        cd /data/nanobaseai/bi/frontend/backend
        /data/nanobaseai/bi/semantic-venv/bin/python -m semantic_bridge.bulletins add bulten.mp3 \\
            --title "…" --duration 842 --publish
    """
    from semantic_layer.config import SemanticSettings
    from semantic_layer.store.catalog_store import open_store

    p = argparse.ArgumentParser(prog="python -m semantic_bridge.bulletins")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="ses dosyasını bülten olarak ekle")
    a.add_argument("file")
    a.add_argument("--title")
    a.add_argument("--summary")
    a.add_argument("--episode", type=int)
    a.add_argument("--voice", help="seslendiren (ekranda yazar)")
    a.add_argument("--duration", type=float, help="saniye; verilmezse ekran çalınca gösterir")
    a.add_argument("--publish", action="store_true", help="hemen Kampüs'te yayınla")
    a.add_argument("--by", default="sunucu")
    sub.add_parser("list", help="bültenleri listele")
    args = p.parse_args(argv)

    s = SemanticSettings.from_env()
    engine = open_store(s.store_dsn).engine
    if args.cmd == "list":
        for b in listing(engine, s.tenant_id, published_only=False):
            print(f"{b['id']}  {b['status']:8}  {b['title']}  ({b['durationSec'] or '?'} sn, {b['size']} B)")
        return 0
    path = Path(args.file)
    try:
        out = add(engine, s.tenant_id, args.by, path.read_bytes(), original_name=path.name, title=args.title,
                  summary=args.summary, episode=args.episode, voice=args.voice, duration_sec=args.duration,
                  source="sunucu", publish=args.publish)
    except BulletinError as e:
        print(f"hata: {e}", file=sys.stderr)
        return 1
    print(f"eklendi: {out['id']} · {out['status']} · {out['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
