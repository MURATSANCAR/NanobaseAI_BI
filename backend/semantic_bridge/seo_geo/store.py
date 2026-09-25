"""SEO & GEO tabloları (meta veritabanı). Göç yok: `ensure()` eksik tabloyu kurar.

- semantic_seo_products: T-soft'tan okunan ürünün son hâli, denetim puanı ve sorunları.
- semantic_seo_proposals: model önerisi → insan kararı (onay/ret). Hiçbir yere gönderilmez; öneri anındaki değerler
  `before_json`'da durur.
- semantic_seo_runs: eşitleme turları (ne zaman, kaç ürün, hata).
- semantic_seo_gsc: Search Console'dan okunan özetler (tür başına son hâl).
- semantic_seo_questions: yapay zekâ görünürlüğü için izlenen sorular.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Optional

import sqlalchemy as sa

_md = sa.MetaData()
PRODUCTS = sa.Table(
    "semantic_seo_products", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("product_id", sa.String(40), primary_key=True),
    sa.Column("code", sa.String(120)),
    sa.Column("name", sa.String(500)),
    sa.Column("brand", sa.String(300)),
    sa.Column("active", sa.Boolean, nullable=False, default=True),
    sa.Column("score", sa.Integer, nullable=False),
    sa.Column("issues_json", sa.Text, nullable=False),
    sa.Column("rules", sa.String(400), nullable=False, default=""),   # ",meta_missing,desc_short," — filtre için
    sa.Column("data_json", sa.Text, nullable=False),
    sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
)
PROPOSALS = sa.Table(
    "semantic_seo_proposals", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("product_id", sa.String(40), nullable=False, index=True),
    sa.Column("status", sa.String(16), nullable=False),     # hazir | onaylandi | reddedildi (eski: gonderildi/hata/geri_alindi — yazma kapandı)
    sa.Column("fields_json", sa.Text, nullable=False),      # önerilen alanlar (onayda düzenlenmiş hâli yazılır)
    sa.Column("before_json", sa.Text, nullable=False),      # öneri anındaki T-soft değerleri
    sa.Column("score_before", sa.Integer),
    sa.Column("score_after", sa.Integer),
    sa.Column("model", sa.String(120)),
    sa.Column("created_by", sa.String(120)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("note", sa.String(1000)),
    sa.Column("sent_at", sa.DateTime(timezone=True)),
    sa.Column("result", sa.String(1000)),
)
RUNS = sa.Table(
    "semantic_seo_runs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("kind", sa.String(16), nullable=False),        # tsoft | gsc
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.Column("count", sa.Integer),
    sa.Column("error", sa.String(1000)),
    sa.Column("started_by", sa.String(120)),
)
GSC = sa.Table(
    "semantic_seo_gsc", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kind", sa.String(24), primary_key=True),       # daily | queries | pages
    sa.Column("start_date", sa.String(10), nullable=False),
    sa.Column("end_date", sa.String(10), nullable=False),
    sa.Column("rows_json", sa.Text, nullable=False),
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)
QUESTIONS = sa.Table(
    "semantic_seo_questions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("text", sa.String(500), nullable=False),
    sa.Column("category", sa.String(80)),
    sa.Column("created_by", sa.String(120)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
_lock = threading.Lock()
_ready: set[int] = set()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.isoformat()


def loads(raw: Optional[str], default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except ValueError:
        return default


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)
