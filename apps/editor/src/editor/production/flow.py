"""Stüdyonun GPU işleri Temporal'da: kitabın hattı (BookProduction), tek resmin yeniden üretimi
(ArtRegenerate) ve sayfa planının işleri: serbest figür (FigureGenerate), kaliteyi artırma (AssetUpscale) ve
GPU'suz zemin ayıklama (AssetCutout; aynı sırada yürür, busy tutmaz). Kendi kuyruğu `editor-production` (analiz kuyruğundan ayrı: dizgi Typst, Ghostscript ve
fontlar ister, bunlar stüdyo imajında) ve kendi işçisi (worker.py, aynı anda tek etkinlik: görsel model
tek sırada). API yalnız başlatır ve iş klasörünü okur.

Dayanıklılık: etkinlikler nabız atar; işçi düşerse etkinlik zaman aşımıyla başka denemede kaldığı yerden
sürer (resimler sayfa sayfa kaydedilir, `run.finish` yalnız eksiği çizer). Ekrandaki durum iş klasöründe:
state.json (adımlar) ve busy.json (süren/sıradaki GPU işi).
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

QUEUE = os.environ.get("EDITOR_PRODUCTION_QUEUE", "editor-production")
BEAT = timedelta(minutes=3)
PLAN_RETRY = RetryPolicy(initial_interval=timedelta(seconds=30), maximum_attempts=2,
                         non_retryable_error_types=["ValueError", "KeyError", "FileNotFoundError"])
FINISH_RETRY = RetryPolicy(initial_interval=timedelta(seconds=30), backoff_coefficient=2.0, maximum_attempts=3,
                           non_retryable_error_types=["ValueError", "KeyError", "FileNotFoundError"])
ART_RETRY = RetryPolicy(initial_interval=timedelta(seconds=20), maximum_attempts=2,
                        non_retryable_error_types=["ValueError", "KeyError"])


# ------------------------------------------------------------------ etkinlikler (işçide koşar)
async def _beating(coro):
    """Uzun etkinlik boyunca nabız: işçi düşerse Temporal BEAT içinde anlar ve yeniden dener."""
    async def beat():
        while True:
            activity.heartbeat()
            await asyncio.sleep(20)
    t = asyncio.create_task(beat())
    try:
        return await coro
    finally:
        t.cancel()


def _started(d) -> None:
    from . import studio
    b = studio.busy(d) or {}
    studio.set_busy(d, {**b, "queued": False, "attempt": activity.info().attempt, "error": None})


def _last(policy: RetryPolicy) -> bool:
    return activity.info().attempt >= (policy.maximum_attempts or 1)


@activity.defn(name="production_plan")
async def plan_activity(job: str) -> None:
    from . import run, studio
    d = studio.job_dir(job)
    _started(d)
    try:
        await _beating(run.plan(d))
    except Exception as e:
        final = _last(PLAN_RETRY) or isinstance(e, (ValueError, KeyError, FileNotFoundError))
        run.fail(d, e, final)
        if final:
            studio.set_busy(d, None)
        raise


@activity.defn(name="production_finish")
async def finish_activity(job: str, seed: int) -> None:
    from . import run, studio
    d = studio.job_dir(job)
    _started(d)
    try:
        await _beating(run.finish(d, seed))
    except Exception as e:
        final = _last(FINISH_RETRY) or isinstance(e, (ValueError, KeyError, FileNotFoundError))
        run.fail(d, e, final)
        if final:
            studio.set_busy(d, None)
        raise
    studio.set_busy(d, None)


async def _release_if_idle(d) -> None:
    """Tek resmin üretimi bittiğinde sırada başka stüdyo işi yoksa görsel modeli hemen kapatır (kart ana
    modele döner); sırada iş varsa açık kalır, model iki iş arasında yeniden yüklenmez."""
    from . import studio
    from .images import Painter
    waiting = [j["id"] for j in studio.list_jobs() if j["id"] != d.name
               and (b := studio.busy(studio.root() / j["id"])) and not b.get("error")]
    if waiting:
        return
    painter = Painter(d / "resim", studio._plan(d))
    try:
        activity.logger.info("görsel model: %s", await painter.release())
    finally:
        await painter.close()


@activity.defn(name="production_regenerate")
async def regenerate_activity(job: str, key: str, mode: str, prompt: str, by: str, variants: int) -> None:
    from . import studio
    d = studio.job_dir(job)
    _started(d)
    try:
        await _beating(studio.regenerate(d, key, mode, prompt, by, variants))
    except Exception as e:
        if _last(ART_RETRY) or isinstance(e, (ValueError, KeyError)):
            b = studio.busy(d) or {}
            studio.set_busy(d, {**b, "error": str(e)[:300], "since": time.time()})   # ekran gösterir
            await _release_if_idle(d)
        raise
    studio.set_busy(d, None)
    await _release_if_idle(d)


async def _plan_job(job: str, jid: str, coro_fn, gpu: bool):
    """Sayfa planı işleri (figür, zemin ayıklama, kaliteyi artırma): durum plan-jobs/<jid>.json'da (ekran bekler).
    GPU işi busy.json'u tutar ve bitince sırada iş yoksa görsel modeli kapatır; zemin ayıklama GPU'suzdur."""
    from . import plan as plan_mod, studio
    d = studio.job_dir(job)
    if gpu:
        _started(d)
    plan_mod.job_record(d, jid, status="running", attempt=activity.info().attempt)
    try:
        res = await _beating(coro_fn(d))
    except Exception as e:
        final = _last(ART_RETRY) or isinstance(e, (ValueError, KeyError, FileNotFoundError))
        plan_mod.job_record(d, jid, status="fail" if final else "running", error=str(e)[:300])
        if gpu and final:
            b = studio.busy(d) or {}
            studio.set_busy(d, {**b, "error": str(e)[:300], "since": time.time()})
            await _release_if_idle(d)
        raise
    plan_mod.job_record(d, jid, status="done", result=res)
    if gpu:
        studio.set_busy(d, None)
        await _release_if_idle(d)


@activity.defn(name="production_figure")
async def figure_activity(job: str, jid: str, gid: str, prompt: str, characters: list[str], page: str | None,
                          by: str) -> None:
    from . import studio
    await _plan_job(job, jid, lambda d: studio.make_figure(d, gid, prompt, characters, page, by), gpu=True)


@activity.defn(name="production_cutout")
async def cutout_activity(job: str, jid: str, gid: str, new_gid: str, by: str) -> None:
    from . import studio

    async def run(d):
        return await asyncio.to_thread(studio.cutout_asset, d, gid, new_gid, by)
    await _plan_job(job, jid, run, gpu=False)


@activity.defn(name="production_upscale")
async def upscale_activity(job: str, jid: str, gid: str, new_gid: str, page: str, item: str, by: str) -> None:
    from . import studio
    await _plan_job(job, jid, lambda d: studio.upscale_asset(d, gid, new_gid, page, item, by), gpu=True)


@activity.defn(name="production_epub")
async def epub_activity(job: str, layout: str, by: str) -> None:
    """E-kitap (GPU'suz; alt metin önerisi model gateway'inden): durum epub/state.json'da (epub.build_job yazar)."""
    from . import epub, studio
    await _beating(epub.build_job(studio.job_dir(job), layout, by))


ACTIVITIES = [plan_activity, finish_activity, regenerate_activity, figure_activity, cutout_activity, upscale_activity,
              epub_activity]


# ------------------------------------------------------------------ iş akışları
@workflow.defn(name="BookProduction")
class BookProduction:
    @workflow.run
    async def run(self, job: str, resume: bool = False, seed: int = 42) -> None:
        if not resume:
            await workflow.execute_activity("production_plan", job, start_to_close_timeout=timedelta(hours=1),
                                            heartbeat_timeout=BEAT, retry_policy=PLAN_RETRY)
        await workflow.execute_activity("production_finish", args=[job, seed],
                                        start_to_close_timeout=timedelta(hours=4),
                                        heartbeat_timeout=BEAT, retry_policy=FINISH_RETRY)


@workflow.defn(name="ArtRegenerate")
class ArtRegenerate:
    @workflow.run
    async def run(self, job: str, key: str, mode: str, prompt: str, by: str, variants: int) -> None:
        await workflow.execute_activity("production_regenerate", args=[job, key, mode, prompt, by, variants],
                                        start_to_close_timeout=timedelta(minutes=45),
                                        heartbeat_timeout=BEAT, retry_policy=ART_RETRY)


@workflow.defn(name="FigureGenerate")
class FigureGenerate:
    @workflow.run
    async def run(self, job: str, jid: str, gid: str, prompt: str, characters: list[str], page: str | None,
                  by: str) -> None:
        await workflow.execute_activity("production_figure", args=[job, jid, gid, prompt, characters, page, by],
                                        start_to_close_timeout=timedelta(minutes=45),
                                        heartbeat_timeout=BEAT, retry_policy=ART_RETRY)


@workflow.defn(name="AssetCutout")
class AssetCutout:
    @workflow.run
    async def run(self, job: str, jid: str, gid: str, new_gid: str, by: str) -> None:
        await workflow.execute_activity("production_cutout", args=[job, jid, gid, new_gid, by],
                                        start_to_close_timeout=timedelta(minutes=20),
                                        heartbeat_timeout=BEAT, retry_policy=ART_RETRY)


@workflow.defn(name="AssetUpscale")
class AssetUpscale:
    @workflow.run
    async def run(self, job: str, jid: str, gid: str, new_gid: str, page: str, item: str, by: str) -> None:
        await workflow.execute_activity("production_upscale", args=[job, jid, gid, new_gid, page, item, by],
                                        start_to_close_timeout=timedelta(minutes=30),
                                        heartbeat_timeout=BEAT, retry_policy=ART_RETRY)


@workflow.defn(name="EpubBuild")
class EpubBuild:
    @workflow.run
    async def run(self, job: str, layout: str, by: str) -> None:
        await workflow.execute_activity("production_epub", args=[job, layout, by],
                                        start_to_close_timeout=timedelta(minutes=60),
                                        heartbeat_timeout=BEAT, retry_policy=ART_RETRY)


WORKFLOWS = [BookProduction, ArtRegenerate, FigureGenerate, AssetCutout, AssetUpscale, EpubBuild]

# Seri karakter kartı (characters.py): denetim (CharacterCheck) ve öneri/çeviri (CharacterCards) aynı kuyrukta.
from .characters import ACTIVITIES as _CARD_ACTIVITIES, WORKFLOWS as _CARD_WORKFLOWS  # noqa: E402
ACTIVITIES += _CARD_ACTIVITIES
WORKFLOWS += _CARD_WORKFLOWS
