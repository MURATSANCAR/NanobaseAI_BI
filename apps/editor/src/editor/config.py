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
    gpu_wait_seconds: int
    deep_concurrency: int
    text_visual_votes: int
    continuity_votes: int
    actor_min_probability: float
    actor_review: bool
    min_illustration_ink: float
    min_figure_ink: float
    min_figure_side: float
    vision_screen: str
    min_reference_px: int
    embed_url: str
    ccip_same_max: float
    cluster_name_support: float
    cluster_name_margin: float

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
        # The GPU is shared with processes the editor does not own and will not stop. "Busy"
        # is a condition of the machine, not of the book: wait this long for room before an
        # analysis that has already cost an hour is given up (measured: a foreign 40 GiB
        # container failed a job that retried for 70 seconds).
        gpu_wait_seconds=int(env("EDITOR_GPU_WAIT_SECONDS", "1800")),
        deep_concurrency=int(env("EDITOR_DEEP_CONCURRENCY", "4")),
        text_visual_votes=int(env("EDITOR_TEXT_VISUAL_VOTES", "3")),
        continuity_votes=int(env("EDITOR_CONTINUITY_VOTES", "3")),
        # who-did-what: a reading of (event, character) counts only from this probability up;
        # below it the pair is UNCERTAIN. Provisional: not yet measured on a book.
        actor_min_probability=float(env("EDITOR_ACTOR_MIN_PROBABILITY", "0.7")),
        # send events whose doer is unsettled, or where this reading and the extractor's
        # participant list disagree, to the editor queue ("0": record only)
        actor_review=env("EDITOR_ACTOR_REVIEW", "1") != "0",
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
        embed_url=env("EDITOR_EMBED_URL", "http://editor-embed:8000"),
        # CCIP's own threshold (0.2132) is calibrated on anime. Measured on this corpus
        # (three books, 194 named figures): same character ~0.11, different ~0.23, cleanest
        # split at 0.14-0.16; at 0.2132 nearly half the different-character pairs read as one.
        ccip_same_max=float(env("EDITOR_CCIP_SAME_MAX", "0.15")),
        # A cluster takes a name on evidence alone only if that evidence (story text on its
        # pages + the scans' own votes) reaches this and beats the next name by the margin;
        # otherwise the adjudicator decides, or the cluster stays unnamed.
        cluster_name_support=float(env("EDITOR_CLUSTER_NAME_SUPPORT", "0.5")),
        cluster_name_margin=float(env("EDITOR_CLUSTER_NAME_MARGIN", "0.2")),
    )
