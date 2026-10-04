"""Filmin adımları Temporal'da: stüdyo kuyruğu (`editor-production`, tek işçi, aynı anda tek GPU işi). API bir adımı
başlatır (`FilmStage`), ekran film.json'daki adım durumunu okur. Görsel/video işi bitince sırada stüdyo işi yoksa görsel
model kapanır ve ana model geri kalkar (production.flow._release_if_idle, gateway devri).

Adımlar arasında editör onayı olduğu için iş akışı tek adımdır; «hepsini sırayla» yalnız onay istemeyen ardışık adımlar
için (ses → kareler) API tarafında iki ayrı başlatmadır. Yarıda kalan adım kaldığı yerden sürer: kareler ve çekimler
tek tek kaydedilir, yeniden koşan adım yalnız eksiği üretir.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

BEAT = timedelta(minutes=3)
RETRY = RetryPolicy(initial_interval=timedelta(seconds=30), backoff_coefficient=2.0, maximum_attempts=3,
                    non_retryable_error_types=["ValueError", "KeyError", "FileNotFoundError", "FilmError"])
TIMEOUT = {"senaryo": timedelta(hours=2), "ses": timedelta(hours=2), "kareler": timedelta(hours=4),
           "cekim": timedelta(hours=12), "kurgu": timedelta(hours=1), "paylasim": timedelta(hours=1)}
GPU = {"ses", "kareler", "cekim"}


@activity.defn(name="production_film_stage")
async def film_stage_activity(job: str, fid: str, stage: str, by: str, opts: dict) -> None:
    from .. import studio
    from ..flow import _beating, _release_if_idle
    from . import dialogue, frames, mix, script, shoot, social, store
    d = studio.job_dir(job)
    f = store.fdir(d, fid)

    def progress(n, total, what=""):
        store.set_stage(f, stage, status="calisiyor", progress=[n, total], step=what,
                        attempt=activity.info().attempt)

    runs = {
        "senaryo": lambda: script.write(d, f, by, progress),
        "ses": lambda: dialogue.synth(d, f, by, progress),
        "kareler": lambda: frames.build(d, f, by, progress, only=opts.get("only"), direction=opts.get("direction", "")),
        "cekim": lambda: shoot.shoot(d, f, by, progress, only=opts.get("only")),
        "kurgu": lambda: _sync(mix.build, d, f, by, progress),
        "paylasim": lambda: social.build(d, f, by, opts.get("platforms") or [], progress),
    }
    if stage not in runs:
        raise ValueError(f"bilinmeyen adım: {stage}")
    try:
        await _beating(runs[stage]())
    except Exception as e:
        final = activity.info().attempt >= (RETRY.maximum_attempts or 1) or isinstance(
            e, (ValueError, KeyError, FileNotFoundError))
        if final:
            store.set_stage(f, stage, status="hata", error=str(e)[:300])
        raise
    finally:
        if stage in GPU:
            await _release_if_idle(d)


async def _sync(fn, *args):
    import asyncio
    return await asyncio.to_thread(fn, *args)


@workflow.defn(name="FilmStage")
class FilmStage:
    @workflow.run
    async def run(self, job: str, fid: str, stage: str, by: str, opts: dict) -> None:
        await workflow.execute_activity("production_film_stage", args=[job, fid, stage, by, opts],
                                        start_to_close_timeout=TIMEOUT.get(stage, timedelta(hours=2)),
                                        heartbeat_timeout=BEAT, retry_policy=RETRY)


ACTIVITIES = [film_stage_activity]
WORKFLOWS = [FilmStage]
