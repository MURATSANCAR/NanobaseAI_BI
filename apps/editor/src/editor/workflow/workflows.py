"""BookFullAnalysis: the 15 steps of NIHAI-KARAR.md §5 as one durable
Temporal workflow. Every step is an activity (retried, checkpointed); page and
chunk steps fan out in parallel. Imports stay minimal for the sandbox."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.exceptions import TimeoutError as ActivityTimeout

with workflow.unsafe.imports_passed_through():
    from .. import transient

RETRY = RetryPolicy(initial_interval=timedelta(seconds=10), backoff_coefficient=2.0,
                    maximum_interval=timedelta(minutes=5), maximum_attempts=4,
                    non_retryable_error_types=["ValueError", "KeyError"])
SHORT = timedelta(minutes=20)
LONG = timedelta(hours=2)

#: «Sessiz başarı yok» (2026-10-03): a required step (identity, final-read checks) that failed for an
#: infrastructure reason is run again by the workflow after these pauses (each run is a full activity
#: with its own retry policy); when the last one fails too, the job fails instead of ending SUCCEEDED
#: with the step missing. Histories recorded before this marker replay their old handling.
INFRA_STEP_RETRY = "infra-step-retry-v1"
INFRA_STEP_DELAYS = (timedelta(minutes=10), timedelta(minutes=30))

#: Liveness heartbeat timeout. 60 s until 2026-10-05: one 81–93 s stall of the worker's loop then killed every
#: activity running at that moment. The cure is keeping work off the loop (activities, editor.pdfproc); the
#: wider margin only keeps a single stall from costing an attempt. Activity options are not part of replay
#: checks, so running histories take it without a marker.
HEARTBEAT = timedelta(seconds=180)

#: Outputs could not be published because another process changed the generation while they were built
#: (SUPERSEDED: a correction, a batch fix). Not a verdict on the book: built again, a few times, after a pause.
OUTPUTS_SUPERSEDED_RETRY = "outputs-superseded-retry-v1"
SUPERSEDED_RETRIES = 3
SUPERSEDED_PAUSE = timedelta(minutes=2)

#: The whole-book person fold (editor.identity_fold) right after the identity step (2026-10-05). The reading's own
#: same-name join sees the model's names inside its windows; the names the book gives the records are settled only
#: when they are written (a model «Kanji» became «Kanju» after the join), and two records of one name stayed
#: («Devlerin Savaşı»: «Kanju» ×2). Until then the fold ran only by hand. It runs before visual identity and the
#: final-read checks: the appearance ledger those checks write (character_attribute) is append-only and keeps a
#: record from being folded, and visual identity then assigns figures to one record per person. Histories recorded
#: before the marker replay without the step; a failure never fails the reading (failures.identity_fold) and the
#: output validation folds again (rebuild.validate / archive.validate).
IDENTITY_FOLD = "identity-fold-v1"

#: Reading quality audit (2026-10-06, editor.read_audit): after the outputs and the category/age suggestion the reading
#: checks itself the way the manual audits did (failed steps, characters, final-read checks, unread/garbled pages,
#: imprint, summary, chapters, people records, events, suggestion, search index, two «Zeki'ye sor» questions), fixes
#: what a class has a fix for (at most two fix rounds, each action once per generation) and leaves the rest to the
#: editor («Gözden geçir» in Kitap Eczanesi). Full and archive profiles. A failure never fails the reading
#: (failures.quality_audit); a book that must be read again is queued after the job has ended (quality_reread).
#: Histories recorded before the marker replay without the step.
QUALITY_AUDIT = "quality-audit-v1"


def infrastructure_failure(e: ActivityError) -> bool:
    """The activity lost its worker (heartbeat / start-to-close timeout) or ended in a connection,
    database or model-availability error (editor.transient): the step may pass later. Anything else
    — the book's data, a rule, a request that cannot fit — fails the same way again."""
    cause = e.cause
    if isinstance(cause, ActivityTimeout):
        return True
    if isinstance(cause, ApplicationError):
        return transient.failure_type_transient(cause.type, cause.message or "")
    return False


@workflow.defn(name="BookFullAnalysis")
class BookFullAnalysis:
    def __init__(self) -> None:
        self.job_id = ""
        self.activity_heartbeats = False
        self.strict_coverage = False

    async def act(self, name: str, *args, timeout: timedelta = LONG):
        options = {"heartbeat_timeout": HEARTBEAT} if self.activity_heartbeats else {}
        return await workflow.execute_activity(name, args=list(args), start_to_close_timeout=timeout,
                                               retry_policy=RETRY, **options)

    async def required(self, key: str, name: str, *args, failures: dict, retry_args: tuple = (),
                       timeout: timedelta = LONG):
        """A step the book must not silently lose (INFRA_STEP_RETRY). An infrastructure failure is run
        again after INFRA_STEP_DELAYS (`retry_args` appended on those runs), and when it still fails the
        job fails (ApplicationError, non-retryable: the job's FAILED status brings the self-repair /
        «Yeniden okut»). Any other failure is recorded in `failures[key]` and returned as None — the
        old handling. Only called where INFRA_STEP_RETRY is patched."""
        for round_ in range(len(INFRA_STEP_DELAYS) + 1):
            try:
                return await self.act(name, *args, *(retry_args if round_ else ()), timeout=timeout)
            except ActivityError as e:
                error = str(e.cause or e)[:500]
                if not infrastructure_failure(e):
                    failures[key] = [error]
                    return None
                if round_ == len(INFRA_STEP_DELAYS):
                    raise ApplicationError(
                        f"{key}: altyapı hatası {round_ + 1} turda da geçmedi, adım atlanmadı: {error}",
                        non_retryable=True) from e
                workflow.logger.warning("%s failed for an infrastructure reason (round %d): %s; retrying in %s",
                                        key, round_ + 1, error, INFRA_STEP_DELAYS[round_])
                await workflow.sleep(INFRA_STEP_DELAYS[round_])
        return None

    async def _superseded_again(self, status: str, so_far: int) -> bool:
        """SUPERSEDED (another process changed the generation while the outputs were built, e.g. a batch
        fix): build again after SUPERSEDED_PAUSE, at most SUPERSEDED_RETRIES times (OUTPUTS_SUPERSEDED_RETRY).
        Until 2026-10-05 the reading failed at once («Output revision did not stabilize (SUPERSEDED)»); the
        marker is recorded only when this happens, so other histories replay unchanged."""
        if status != "SUPERSEDED" or so_far >= SUPERSEDED_RETRIES:
            return False
        if not workflow.patched(OUTPUTS_SUPERSEDED_RETRY):
            return False
        workflow.logger.warning("outputs superseded (%d/%d); building again in %s", so_far + 1,
                                SUPERSEDED_RETRIES, SUPERSEDED_PAUSE)
        await workflow.sleep(SUPERSEDED_PAUSE)
        return True

    async def step(self, n: int, label: str, extra: dict | None = None) -> None:
        await self.act("set_step", self.job_id, n, label, extra or {}, timeout=SHORT)

    async def fan_out(self, name: str, items: list, *fixed) -> tuple[list, list]:
        """Run one activity per item in parallel; failures are collected, not fatal."""
        async def one(it):
            try:
                return await self.act(name, *fixed, it)
            except ActivityError as e:
                return {"failed": it, "error": str(e.cause or e)[:500]}
        res = await asyncio.gather(*(one(i) for i in items))
        failed = [r for r in res if isinstance(r, dict) and "failed" in r]
        if failed and (self.strict_coverage or len(failed) == len(items)):
            # every page failed (e.g. gpu_busy): stop instead of sealing an empty generation
            raise ApplicationError(f"{name}: {len(items)}/{len(items)} failed: {failed[0]['error']}",
                                   non_retryable=True)
        return [r for r in res if not (isinstance(r, dict) and "failed" in r)], \
               [r for r in res if isinstance(r, dict) and "failed" in r]

    @workflow.run
    async def run(self, job_id: str) -> dict:
        self.job_id = job_id
        # Record the choice once at workflow entry. Histories without this marker
        # retain their original activity options, including after replay resumes.
        self.activity_heartbeats = workflow.patched("activity-heartbeats-v1")
        # A page that cannot be read is reported as not analysed (`failures`, the coverage
        # reads) and the book goes on; only a stage where EVERY item fails stops the job.
        # Stopping on one page turned "page 17 is unreadable" into "no analysis at all".
        self.strict_coverage = workflow.patched("complete-stage-coverage-v1") and \
            not workflow.patched("partial-coverage-reported-v1")
        # Jobs that started under the old step order replay it; new jobs take the order
        # that loads the director once.
        if workflow.patched("verified-revision-outputs-v1"):
            return await self._run_verified(job_id)
        if workflow.patched("director-single-phase-v1"):
            return await self._run_single_phase(job_id)
        return await self._run_v1(job_id)

    async def _run_verified(self, job_id: str) -> dict:
        """Canonical producers and verification precede every derived output.

        Old histories retain their original patched branch. New jobs use only
        revision-bound producers and keep analytical acceptance separate.

        Profile 'archive' (editor.archive): read for questions only — the vision model sees only
        the cover and the pages with a picture; final-read checks, text-visual confirmation,
        continuity and contradiction detection are left to a later 'redaction' job.
        """
        failures: dict[str, list] = {}
        try:
            await self.step(1, "Kitap ve içerik sürümü")
            ctx = await self.act("prepare_generation", job_id, timeout=SHORT)
            gid, bv = ctx["generation_id"], ctx["book_version_id"]
            # The job's profile is in prepare_generation's recorded result: histories from before it
            # carry none and replay the full reading; only the new kinds of job take a marker.
            if ctx.get("profile") == "redaction" and workflow.patched("redaction-profile-v1"):
                return await self._run_redaction(job_id, gid)
            archive = ctx.get("profile") == "archive" and workflow.patched("archive-profile-v1")
            await self.step(2, "Sayfa manifesti", {"generation_id": gid})
            man = await self.act("page_manifest", bv)
            pages = list(range(1, man["page_count"] + 1))
            await self.step(3, "PDF metin katmanı")
            await self.act("text_layer", gid, bv)
            await self.step(4, "OCR", {"pages": man["needs_ocr"]})
            _, failures["ocr"] = await self.fan_out("ocr_page", man["needs_ocr"], gid, bv)
            scan = pages
            if archive:
                # only the cover and the pages that carry a picture go to the vision model
                scan = (await self.act("archive_visual_pages", bv, timeout=SHORT))["pages"]
            await self.step(5, "Hızlı görsel tarama", {"pages": len(scan), "of": len(pages)} if archive
                            else {"pages": len(pages)})
            fast, failures["fast_scan"] = await self.fan_out("scan_page_fast", scan, gid)
            uncertain = [r["page_no"] for r in fast if r.get("uncertain")]
            # ---- deep vision, first visit: everything that needs only the pages themselves
            await self.step(6, "Derin görsel inceleme", {"uncertain_pages": uncertain})
            await self.act("release_models", ["book-vision-fast"], timeout=SHORT)
            _, failures["deep_scan"] = await self.fan_out("scan_page_deep", uncertain, gid)
            await self.act("persist_visual", gid, "deep")
            tv: dict = {}
            if not archive:
                await self.step(6, "Metin–görsel bulguların teyidi")
                tv = await self.act("confirm_text_visual", gid)     # reads scans and page text only
            await self.act("release_models", ["book-vision-deep"], timeout=SHORT)
            # ---- director phase
            await self.step(7, "Karakter ve olay adayları")
            chunks = await self.act("text_chunks", gid, timeout=SHORT)
            ext, failures["extract"] = await self.fan_out("extract_chunk", chunks, gid)
            await self.step(8, "Karakter kimlikleri")
            ident = await self._identity(gid, failures)
            fold = await self._identity_fold(gid, failures)
            await self.step(9, "Olay kipleri")
            mod = await self.act("verify_modality", gid)
            mrg = await self.act("merge_events", gid)
            await self.step(9, "Önemli olay sayfaları")
            roles = await self.act("narrative_roles", gid)
            key_pages = roles["pages"]
            if archive:
                # a text-only page has nothing for the deep model to see
                shown = set(scan)
                key_pages = [p for p in key_pages if p in shown]
            vis = cont = None
            if key_pages:
                # more deep scans are needed and the Critic must see their scene claims:
                # the visual work goes here and the director loads a second time
                vis, cont, tv = await self._visual_phase(gid, ident, tv, key_pages, failures, archive=archive)
            await self.act("persist_visual", gid, "all")
            await self.step(10, "Duygu ve tema")
            emo = await self.act("emotions_themes", gid)
            if not archive and workflow.patched("proofreading-v1"):
                await self.step(10, "Son okuma denetimleri")
                if workflow.patched(INFRA_STEP_RETRY):
                    await self._proofreading(gid, failures)
                else:
                    try:
                        failures["proofreading"] = []
                        await self.act("proofreading", gid, timeout=LONG)
                    except ActivityError as e:
                        failures["proofreading"] = [str(e.cause or e)[:500]]
            await self.step(15, "Künye")
            try:
                await self.act("book_metadata", gid)
            except ActivityError as e:
                failures["book_metadata"] = [str(e.cause or e)[:500]]
            # ---- deep vision, second visit (unless it already happened above)
            if vis is None:
                vis, cont, tv = await self._visual_phase(gid, ident, tv, [], failures, archive=archive)
            # All visual identity/continuity writes have completed here. The
            # rebuild activity verifies facts and actors before freezing inputs.
            await self.step(13, "Doğrulama → sürümlü özet, rapor ve indeks")
            # archive: same outputs, validated without contradiction detection and the editor's queue
            outputs_activity = "archive_outputs" if archive else "rebuild_outputs"
            produced = None
            # When several books are read at once they take turns on the card, and a book
            # that reaches this step while another holds it cannot start its models. That
            # is a queue, not a defect: the book waits for its turn instead of failing.
            # Without this it failed outright («kahramanini-yutan-kitap», 2026-09-23).
            if workflow.patched("rebuild-capacity-wait-v1"):
                waited = superseded = 0
                for attempt in range(40):
                    produced = await self.act(outputs_activity, gid, timeout=timedelta(hours=6))
                    status = produced["technical_status"]
                    if status in ("SUCCEEDED", "ALREADY_CURRENT"):
                        break
                    if status == "BUSY":
                        await workflow.sleep(timedelta(seconds=30))
                        continue
                    if status == "CAPACITY_WAIT" and waited < 12:      # up to ~1 saat
                        waited += 1
                        await workflow.sleep(timedelta(minutes=5))
                        continue
                    if await self._superseded_again(status, superseded):
                        superseded += 1
                        continue
                    break
            else:
                for attempt in range(3):
                    produced = await self.act(outputs_activity, gid, timeout=timedelta(hours=6))
                    if produced["technical_status"] in ("SUCCEEDED", "ALREADY_CURRENT"):
                        break
                    if produced["technical_status"] == "BUSY":
                        await workflow.sleep(timedelta(seconds=30))
            if produced["technical_status"] not in ("SUCCEEDED", "ALREADY_CURRENT"):
                raise ApplicationError(
                    f"Output revision did not stabilize ({produced['technical_status']})",
                    non_retryable=True)
            recommendation = None
            # The full reading suggests too (2026-10-03); its marker is separate so histories recorded
            # before it replay without the step. `patched` is only evaluated on its own profile's path.
            if (archive and workflow.patched("archive-recommend-v1")) or \
                    (not archive and workflow.patched("full-recommend-v1")):
                # category and age suggestion from the summaries just built; a failure leaves the book
                # without a suggestion, it never fails the reading
                await self.step(14, "Kategori ve yaş önerisi")
                try:
                    recommendation = await self.act("archive_recommend", gid, timeout=SHORT)
                except ActivityError as e:
                    failures["recommend"] = [str(e.cause or e)[:500]]
            audit = await self._quality_audit(job_id, gid, "archive" if archive else "full", failures)
            summary = {"generation_id":gid,"pages":len(pages),"outputs":produced,
                "step_order":"verified-revision-outputs-v1","accepted":False,
                "analytical_status":"NEEDS_REVIEW",
                "failures":{k:v for k,v in failures.items() if v}}
            if recommendation is not None:
                summary["recommendation"] = recommendation
            if audit is not None:
                summary["quality_audit"] = {k: v for k, v in audit.items() if k not in ("cleared", "reread")}
            if fold is not None:
                summary["identity_fold"] = fold
            if archive:
                summary.update(profile="archive", visual_pages=len(scan),
                               deferred=["proofreading", "confirm_text_visual", "continuity_checks",
                                         "detect_contradictions", "queue_contradictions"])
            await self.act("finish_job", job_id, "SUCCEEDED", summary, timeout=SHORT)
            if audit is not None and audit.get("reread"):
                # the book is read again only after this job has ended (one QUEUED/RUNNING job per book version);
                # a failure here leaves the audit's «Yeniden okunacak» record for the editor, the reading stands
                try:
                    await self.act("quality_reread", job_id, timeout=SHORT)
                except ActivityError as e:
                    workflow.logger.warning("quality reread not queued: %s", str(e.cause or e)[:300])
            return summary
        except BaseException as e:
            status = "CANCELLED" if isinstance(e, asyncio.CancelledError) else "FAILED"
            await workflow.execute_activity("finish_job", args=[job_id, status, {"error": str(e)[:2000]}],
                                            start_to_close_timeout=SHORT, retry_policy=RETRY)
            raise
        finally:
            await workflow.execute_activity("release_models", args=[[]], start_to_close_timeout=SHORT,
                                            retry_policy=RETRY)

    async def _quality_audit(self, job_id: str, gid: str, profile: str, failures: dict) -> dict | None:
        """QUALITY_AUDIT: the reading audits and repairs itself (editor.read_audit.run_step). The steps it repaired
        leave `failures`; None when the history predates the marker or the audit itself failed (recorded in
        `failures.quality_audit`, the reading goes on)."""
        if not workflow.patched(QUALITY_AUDIT):
            return None
        await self.step(15, "Kalite denetimi")
        try:
            out = await self.act("quality_audit", job_id, gid, profile,
                                 {k: v for k, v in failures.items() if v}, timeout=timedelta(hours=6))
        except ActivityError as e:
            failures["quality_audit"] = [str(e.cause or e)[:500]]
            return None
        out = out or {}
        for key in out.get("cleared") or []:
            failures.pop(key, None)
        return out

    async def _run_redaction(self, job_id: str, gid: str) -> dict:
        """A book read in the archive profile, opened for redaction: the steps the archive reading
        left out, on that same generation. Text-visual confirmation and continuity read the deep
        scans already there (the archive scanned every page with a picture); contradictions are
        detected over the full knowledge and queued with everything else; the outputs then rebuild
        through the normal path. Word alternatives are produced when the editor opens the findings."""
        failures: dict[str, list] = {}

        async def soft(key: str, name: str, timeout: timedelta = LONG):
            try:
                return await self.act(name, gid, timeout=timeout)
            except ActivityError as e:
                failures[key] = [str(e.cause or e)[:500]]
                return None

        # an archive generation read before identity-fold-v1: its records are folded before the checks write the
        # appearance ledger (which would keep them apart)
        fold = await self._identity_fold(gid, failures)
        await self.step(10, "Son okuma denetimleri", {"generation_id": gid})
        if workflow.patched(INFRA_STEP_RETRY):
            await self._proofreading(gid, failures)
        else:
            await soft("proofreading", "proofreading")
        await self.step(6, "Metin–görsel bulguların teyidi")
        tv = await soft("text_visual", "confirm_text_visual")
        await self.step(8, "Karakter sürekliliği")
        cont = await soft("continuity", "continuity_checks")
        await self.act("release_models", ["book-vision-deep"], timeout=SHORT)
        await self.step(14, "Çelişkiler")
        found = await self.act("detect_contradictions", gid)
        await self.step(14, "Editör kuyruğu")
        con = {**found, **await self.act("queue_contradictions", gid, timeout=SHORT)}
        await self.step(13, "Doğrulama → sürümlü özet, rapor ve indeks")
        produced, waited, superseded = None, 0, 0
        for attempt in range(40):
            produced = await self.act("rebuild_outputs", gid, timeout=timedelta(hours=6))
            status = produced["technical_status"]
            if status in ("SUCCEEDED", "ALREADY_CURRENT"):
                break
            if status == "BUSY":
                await workflow.sleep(timedelta(seconds=30))
                continue
            if status == "CAPACITY_WAIT" and waited < 12:
                waited += 1
                await workflow.sleep(timedelta(minutes=5))
                continue
            if await self._superseded_again(status, superseded):
                superseded += 1
                continue
            break
        if produced["technical_status"] not in ("SUCCEEDED", "ALREADY_CURRENT"):
            raise ApplicationError(f"Output revision did not stabilize ({produced['technical_status']})",
                                   non_retryable=True)
        summary = {"generation_id": gid, "profile": "redaction", "outputs": produced, "text_visual": tv,
                   "continuity": cont, "contradictions": con, "step_order": "redaction-profile-v1",
                   "accepted": False, "failures": {k: v for k, v in failures.items() if v}}
        if fold is not None:
            summary["identity_fold"] = fold
        await self.act("finish_job", job_id, "SUCCEEDED", summary, timeout=SHORT)
        return summary

    async def _run_single_phase(self, job_id: str) -> dict:
        """Same activities, same inputs per model call, other order. The director (0.48 of
        the card) and the deep vision model (0.90) cannot be loaded together, so every
        switch between them is a cold start of ~6 minutes. The old order went
        deep -> director -> deep -> director (-> deep -> director when key-event pages
        needed a scan). What forces a switch: the extractor reads the deep scans, and
        visual identity reads the characters the director resolved. Nothing the director
        does later reads what visual identity, continuity or text-visual confirmation
        write (the Critic skips their claim kinds), so that visual work moves behind the
        whole director phase: deep -> director -> deep. Only when narrative roles ask for
        more deep scans does the director load a second time, because the Critic must see
        the scene claims of those pages."""
        failures: dict[str, list] = {}
        try:
            await self.step(1, "Kitap ve içerik sürümü")
            ctx = await self.act("prepare_generation", job_id, timeout=SHORT)
            gid, bv = ctx["generation_id"], ctx["book_version_id"]
            await self.step(2, "Sayfa manifesti", {"generation_id": gid})
            man = await self.act("page_manifest", bv)
            pages = list(range(1, man["page_count"] + 1))
            await self.step(3, "PDF metin katmanı")
            await self.act("text_layer", gid, bv)
            await self.step(4, "OCR", {"pages": man["needs_ocr"]})
            _, failures["ocr"] = await self.fan_out("ocr_page", man["needs_ocr"], gid, bv)
            await self.step(5, "Hızlı görsel tarama", {"pages": len(pages)})
            fast, failures["fast_scan"] = await self.fan_out("scan_page_fast", pages, gid)
            uncertain = [r["page_no"] for r in fast if r.get("uncertain")]
            # ---- deep vision, first visit: everything that needs only the pages themselves
            await self.step(6, "Derin görsel inceleme", {"uncertain_pages": uncertain})
            await self.act("release_models", ["book-vision-fast"], timeout=SHORT)
            _, failures["deep_scan"] = await self.fan_out("scan_page_deep", uncertain, gid)
            await self.act("persist_visual", gid, "deep")
            await self.step(6, "Metin–görsel bulguların teyidi")
            tv = await self.act("confirm_text_visual", gid)     # reads scans and page text only
            await self.act("release_models", ["book-vision-deep"], timeout=SHORT)
            # ---- director phase
            await self.step(7, "Karakter ve olay adayları")
            chunks = await self.act("text_chunks", gid, timeout=SHORT)
            ext, failures["extract"] = await self.fan_out("extract_chunk", chunks, gid)
            await self.step(8, "Karakter kimlikleri")
            ident = await self._identity(gid, failures)
            await self.step(9, "Olay kipleri")
            mod = await self.act("verify_modality", gid)
            mrg = await self.act("merge_events", gid)
            await self.step(9, "Önemli olay sayfaları")
            roles = await self.act("narrative_roles", gid)
            vis = cont = None
            if roles["pages"]:
                # more deep scans are needed and the Critic must see their scene claims:
                # the visual work goes here and the director loads a second time
                vis, cont, tv = await self._visual_phase(gid, ident, tv, roles["pages"], failures)
            await self.act("persist_visual", gid, "all")
            await self.step(10, "Duygu ve tema")
            emo = await self.act("emotions_themes", gid)
            await self.step(12, "Özetler")
            chs = await self.act("list_chapters", gid, timeout=SHORT)
            _, failures["chapter_summary"] = await self.fan_out("chapter_summary", chs, gid)
            book = await self.act("book_summary", gid)
            await self.step(13, "Critic Agent")
            crit = await self.act("critic", gid)
            await self.step(13, "Kim ne yaptı")
            actors = await self.act("event_actors", gid)
            await self.step(14, "Çelişkiler")
            found = await self.act("detect_contradictions", gid)
            await self.step(15, "Künye")
            try:
                await self.act("book_metadata", gid)
            except ActivityError as e:
                failures["book_metadata"] = [str(e.cause or e)[:500]]
            # ---- deep vision, second visit (unless it already happened above)
            if vis is None:
                vis, cont, tv = await self._visual_phase(gid, ident, tv, [], failures)
            await self.step(14, "Editör kuyruğu")
            con = {**found, **await self.act("queue_contradictions", gid, timeout=SHORT)}
            await self.step(11, "Arama indeksi")
            idx = await self.act("embed_index", gid)
            await self.step(15, "Regresyon ve rapor")
            reg = await self.act("regression", gid)
            rep = await self.act("report", gid)
            await self.step(15, "Katalog kartı")
            try:
                card = await self.act("build_card", gid)
            except ActivityError as e:
                card, failures["catalog_card"] = None, [str(e.cause or e)[:500]]
            summary = {"generation_id": gid, "pages": len(pages), "ocr_pages": len(man["needs_ocr"]),
                       "uncertain_pages": uncertain, "extract": ext, "identity": ident, "visual_identity": vis,
                       "continuity": cont, "text_visual": tv, "modality": mod, "merge": mrg,
                       "narrative_roles": roles, "emotions_themes": emo, "index": idx, "book_summary": book,
                       "critic": crit, "event_actors": actors, "contradictions": con,
                       "regression_passed": reg["passed"], "report_id": rep["report_id"], "catalog_card": card,
                       "step_order": "director-single-phase-v1",
                       "failures": {k: v for k, v in failures.items() if v}}
            await self.act("finish_job", job_id, "SUCCEEDED", summary, timeout=SHORT)
            return summary
        except BaseException as e:
            status = "CANCELLED" if isinstance(e, asyncio.CancelledError) else "FAILED"
            await workflow.execute_activity("finish_job", args=[job_id, status, {"error": str(e)[:2000]}],
                                            start_to_close_timeout=SHORT, retry_policy=RETRY)
            raise
        finally:
            await workflow.execute_activity("release_models", args=[[]], start_to_close_timeout=SHORT,
                                            retry_policy=RETRY)

    async def _identity(self, gid: str, failures: dict) -> dict:
        """Step 8. Five books ended here on 2026-09-23/24 («Activity task failed»: an identity
        request over the model's context). The activity now falls back to smaller windows and,
        when nothing can be read, to the editor's queue (knowledge.resolve_character_identity).
        This is the last resort for what it cannot catch — a timeout, a crash after every
        retry: the mentions stay unresolved, the editor gets the question, the book goes on.
        On success nothing here adds a command; a replayed history that ended here before this
        branch existed has no marker and fails exactly as it did."""
        if workflow.patched(INFRA_STEP_RETRY):
            # strict: the activity raises infrastructure failures instead of asking the editor on its
            # last attempt; the workflow runs it again, and fails the job if it never passes (a book
            # with 0 characters because of a heartbeat timeout ended SUCCEEDED, 2026-10-03)
            ident = await self.required("identity", "resolve_identity", gid, True, failures=failures)
            if ident is None:
                return await self.act("identity_unresolved", gid, failures["identity"][0], timeout=SHORT)
            return ident
        try:
            return await self.act("resolve_identity", gid)
        except ActivityError as e:
            if not workflow.patched("identity-never-ends-reading-v1"):
                raise
            failures["identity"] = [str(e.cause or e)[:500]]
            return await self.act("identity_unresolved", gid, failures["identity"][0], timeout=SHORT)

    async def _identity_fold(self, gid: str, failures: dict) -> dict | None:
        """IDENTITY_FOLD: one person, one record over the whole book (editor.identity_fold, same guards as the
        reading). Its own activity, its own thread; batch_guard is not asked (this job's generation). None when
        the history predates the marker or the step failed (recorded in `failures`, the reading goes on)."""
        if not workflow.patched(IDENTITY_FOLD):
            return None
        await self.step(8, "Kişi kayıtları: bütün kitapta birleştirme")
        try:
            out = await self.act("fold_identities", gid, timeout=LONG)
        except ActivityError as e:
            failures["identity_fold"] = [str(e.cause or e)[:500]]
            return None
        return {k: out.get(k) for k in ("characters", "records_folded", "records_blocked", "characters_after")}

    async def _proofreading(self, gid: str, failures: dict) -> None:
        """Final-read checks under INFRA_STEP_RETRY: an infrastructure failure is retried and then fails
        the job; a workflow retry round resumes (checks already recorded are not run again). A check
        that failed for a problem of its own does not fail the book (as before) but is named in
        `failures.proofreading_checks` instead of disappearing."""
        res = await self.required("proofreading", "proofreading", gid, failures=failures, retry_args=(True,))
        lost = sorted(k for k, v in (res or {}).items() if isinstance(v, dict) and "failed" in v)
        if lost:
            failures["proofreading_checks"] = lost

    async def _visual_phase(self, gid: str, ident: dict, tv: dict, key_pages: list,
                            failures: dict, archive: bool = False) -> tuple[dict, dict | None, dict]:
        """Everything the deep vision model does once the characters are known. Archive profile:
        who each drawn figure is, and the key pages' scans; continuity and text-visual
        confirmation wait for redaction."""
        await self.step(8, "Görsel kimlik (kümeleme ve hakem)", {"characters": ident.get("characters")})
        vis = await self.act("visual_identity", gid)
        cont = None
        if not archive:
            await self.step(8, "Karakter sürekliliği", vis)
            cont = await self.act("continuity_checks", gid)
        if key_pages:
            await self.step(9, "Önemli olay sayfalarının derin taraması", {"pages": key_pages})
            _, failures["key_event_scan"] = await self.fan_out("scan_page_deep_key", key_pages, gid)
            await self.act("persist_visual", gid, "all")
            if not archive:
                more = await self.act("confirm_text_visual", gid)   # only the pages scanned just now
                tv = {**tv, **{k: tv[k] + more[k] for k in ("pages", "proposed", "confirmed",
                                                            "confirmed_pages", "pages_failed")}}
        await self.act("release_models", ["book-vision-deep"], timeout=SHORT)
        return vis, cont, tv

    async def _run_v1(self, job_id: str) -> dict:
        """The step order before director-single-phase-v1; kept for jobs that started under it."""
        failures: dict[str, list] = {}
        try:
            # 1. Kitap ve içerik sürümü, yeni generation_id
            await self.step(1, "Kitap ve içerik sürümü")
            ctx = await self.act("prepare_generation", job_id, timeout=SHORT)
            gid, bv = ctx["generation_id"], ctx["book_version_id"]
            # 2. Sayfa manifesti
            await self.step(2, "Sayfa manifesti", {"generation_id": gid})
            man = await self.act("page_manifest", bv)
            pages = list(range(1, man["page_count"] + 1))
            # 3. PDF metin katmanı
            await self.step(3, "PDF metin katmanı")
            await self.act("text_layer", gid, bv)
            # 4. Gerekli sayfalarda OCR
            await self.step(4, "OCR", {"pages": man["needs_ocr"]})
            _, failures["ocr"] = await self.fan_out("ocr_page", man["needs_ocr"], gid, bv)
            # 5. Qwen3-VL-8B-Instruct ile hızlı görsel tarama
            await self.step(5, "Hızlı görsel tarama", {"pages": len(pages)})
            fast, failures["fast_scan"] = await self.fan_out("scan_page_fast", pages, gid)
            uncertain = [r["page_no"] for r in fast if r.get("uncertain")]
            # 6. Belirsiz sayfalar Qwen3-VL-32B-Thinking'e
            await self.step(6, "Derin görsel inceleme", {"uncertain_pages": uncertain})
            await self.act("release_models", ["book-vision-fast"], timeout=SHORT)
            _, failures["deep_scan"] = await self.fan_out("scan_page_deep", uncertain, gid)
            await self.act("persist_visual", gid, "deep")
            # 7. Karakter ve olay adayları
            await self.step(7, "Karakter ve olay adayları")
            chunks = await self.act("text_chunks", gid, timeout=SHORT)
            ext, failures["extract"] = await self.fan_out("extract_chunk", chunks, gid)
            # 8. Karakter kimliklerini birleştirme (+ süreklilik kontrolü, derin model)
            await self.step(8, "Karakter kimlikleri")
            ident = await self.act("resolve_identity", gid)
            await self.step(8, "Görsel kimlik (kümeleme ve hakem)", {"characters": ident.get("characters")})
            vis = await self.act("visual_identity", gid)
            await self.step(8, "Karakter sürekliliği", vis)
            cont = await self.act("continuity_checks", gid)
            await self.step(8, "Metin–görsel bulguların teyidi")
            tv = await self.act("confirm_text_visual", gid)
            await self.act("release_models", ["book-vision-deep"], timeout=SHORT)
            # 9. Gerçekleşmiş olay / plan / hayal / şaka ayrımı
            await self.step(9, "Olay kipleri")
            mod = await self.act("verify_modality", gid)
            mrg = await self.act("merge_events", gid)
            # "Önemli olaylarda" -> deep model: importance comes from the whole timeline
            await self.step(9, "Önemli olay sayfaları")
            roles = await self.act("narrative_roles", gid)
            if roles["pages"]:
                _, failures["key_event_scan"] = await self.fan_out("scan_page_deep_key", roles["pages"], gid)
                await self.act("persist_visual", gid, "all")
                more = await self.act("confirm_text_visual", gid)   # only the pages scanned just now
                tv = {**tv, **{k: tv[k] + more[k] for k in ("pages", "proposed", "confirmed",
                                                            "confirmed_pages", "pages_failed")}}
                await self.act("release_models", ["book-vision-deep"], timeout=SHORT)
            await self.act("persist_visual", gid, "all")
            # 10. Duygu ve tema
            await self.step(10, "Duygu ve tema")
            emo = await self.act("emotions_themes", gid)
            # 11. Embedding + reranker indeksi
            await self.step(11, "Arama indeksi")
            idx = await self.act("embed_index", gid)
            # 12. Bölüm ve kitap özetleri
            await self.step(12, "Özetler")
            chs = await self.act("list_chapters", gid, timeout=SHORT)
            _, failures["chapter_summary"] = await self.fan_out("chapter_summary", chs, gid)
            book = await self.act("book_summary", gid)
            # 13. Critic Agent
            await self.step(13, "Critic Agent")
            crit = await self.act("critic", gid)
            # who did what: after the Critic, so rejected events are not read, and while the
            # director is still loaded. Jobs started before this step existed replay without it.
            actors = None
            if workflow.patched("event-actors-v1"):
                await self.step(13, "Kim ne yaptı")
                actors = await self.act("event_actors", gid)
            # 14. Çelişkiler -> NEEDS_REVIEW
            await self.step(14, "Çelişkiler ve editör kuyruğu")
            con = await self.act("contradictions", gid)
            # 15. Regresyon, rapor, nesli mühürle
            await self.step(15, "Künye")
            try:
                await self.act("book_metadata", gid)
            except ActivityError as e:
                failures["book_metadata"] = [str(e.cause or e)[:500]]
            await self.step(15, "Regresyon ve rapor")
            reg = await self.act("regression", gid)
            rep = await self.act("report", gid)
            # catalog card + cover from the sealed generation; a card failure is reported,
            # it does not undo a finished analysis
            await self.step(15, "Katalog kartı")
            try:
                card = await self.act("build_card", gid)
            except ActivityError as e:
                card, failures["catalog_card"] = None, [str(e.cause or e)[:500]]
            summary = {"generation_id": gid, "pages": len(pages), "ocr_pages": len(man["needs_ocr"]),
                       "uncertain_pages": uncertain, "extract": ext, "identity": ident, "visual_identity": vis,
                       "continuity": cont, "text_visual": tv, "modality": mod, "merge": mrg, "narrative_roles": roles, "emotions_themes": emo,
                       "index": idx, "book_summary": book, "critic": crit, "event_actors": actors, "contradictions": con,
                       "regression_passed": reg["passed"], "report_id": rep["report_id"], "catalog_card": card,
                       "failures": {k: v for k, v in failures.items() if v}}
            await self.act("finish_job", job_id, "SUCCEEDED", summary, timeout=SHORT)
            return summary
        except BaseException as e:
            status = "CANCELLED" if isinstance(e, asyncio.CancelledError) else "FAILED"
            await workflow.execute_activity("finish_job", args=[job_id, status, {"error": str(e)[:2000]}],
                                            start_to_close_timeout=SHORT, retry_policy=RETRY)
            raise
        finally:
            await workflow.execute_activity("release_models", args=[[]], start_to_close_timeout=SHORT,
                                            retry_policy=RETRY)
