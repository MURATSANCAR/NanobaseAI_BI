"""Runtime settings, all from the environment (secrets/editor.env on the host)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root: Path
    db_dsn: str
    gateway_url: str
    gateway_key: str
    gateway_internal_key: str
    qdrant_url: str
    qdrant_key: str
    temporal_address: str
    temporal_namespace: str
    task_queue: str
    models_yaml: Path
    page_concurrency: int
    deep_concurrency: int
    text_visual_votes: int
    continuity_votes: int
    min_illustration_ink: float
    min_figure_ink: float
    min_figure_side: float
    vision_screen: str
    min_reference_px: int

    @property
    def storage(self) -> Path:
        return self.root / "storage"

    @property
    def inbox(self) -> Path:
        return self.storage / "inbox"


@lru_cache(maxsize=1)
def settings() -> Settings:
    env = os.environ.get
    return Settings(
        root=Path(env("EDITOR_ROOT", "/data/editor")),
        db_dsn=env("EDITOR_DB_DSN", ""),
        gateway_url=env("EDITOR_GATEWAY_URL", "http://editor-gateway:8000"),
        gateway_key=env("EDITOR_GATEWAY_KEY", ""),
        gateway_internal_key=env("EDITOR_GATEWAY_INTERNAL_KEY", ""),
        qdrant_url=env("EDITOR_QDRANT_URL", "http://editor-qdrant:6333"),
        qdrant_key=env("QDRANT__SERVICE__API_KEY", ""),
        temporal_address=env("EDITOR_TEMPORAL_ADDRESS", "editor-temporal:7233"),
        temporal_namespace=env("EDITOR_TEMPORAL_NAMESPACE", "editor"),
        task_queue=env("EDITOR_TASK_QUEUE", "editor-book-analysis"),
        models_yaml=Path(env("EDITOR_MODELS_YAML", "/app/deploy/models.yaml")),
        page_concurrency=int(env("EDITOR_PAGE_CONCURRENCY", "16")),
        deep_concurrency=int(env("EDITOR_DEEP_CONCURRENCY", "4")),
        text_visual_votes=int(env("EDITOR_TEXT_VISUAL_VOTES", "3")),
        continuity_votes=int(env("EDITOR_CONTINUITY_VOTES", "3")),
        # below this share of non-text ink a page has nothing to look at (no vision call)
        min_illustration_ink=float(env("EDITOR_MIN_ILLUSTRATION_INK", "0.02")),
        # a figure's bbox must contain at least this share of ink to count as seen
        min_figure_ink=float(env("EDITOR_MIN_FIGURE_INK", "0.05")),
        # a box whose short side is under this share of the page is page furniture (a folio
        # ornament, a bullet), not a drawn character
        min_figure_side=float(env("EDITOR_MIN_FIGURE_SIDE", "0.05")),
        # "deep": illustrated pages go straight to book-vision-deep (default, user decision
        # 2026-09-19); "fast": book-vision-fast screens first, deep only where evidence asks.
        vision_screen=env("EDITOR_VISION_SCREEN", "deep"),
        # a reference crop's shorter side, in pixels of the rendered page (1600 px long side)
        min_reference_px=int(env("EDITOR_MIN_REFERENCE_PX", "100")),
    )
