"""BookFullAnalysis: the 15 steps of NIHAI-KARAR.md §5 as one durable
Temporal workflow. Every step is an activity (retried, checkpointed); page and
chunk steps fan out in parallel. Imports stay minimal for the sandbox."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

RETRY = RetryPolicy(initial_interval=timedelta(seconds=10), backoff_coefficient=2.0,
                    maximum_interval=timedelta(minutes=5), maximum_attempts=4,
                    non_retryable_error_types=["ValueError", "KeyError"])
SHORT = timedelta(minutes=20)
LONG = timedelta(hours=2)


@workflow.defn(name="BookFullAnalysis")
class BookFullAnalysis:
    def __init__(self) -> None:
        self.job_id = ""
        self.activity_heartbeats = False
        self.strict_coverage = False

    async def act(self, name: str, *args, timeout: timedelta = LONG):
        options = {"heartbeat_timeout": timedelta(seconds=60)} if self.activity_heartbeats else {}
        return await workflow.execute_activity(name, args=list(args), start_to_close_timeout=timeout,
                                               retry_policy=RETRY, **options)

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
        """
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
            ident = await self.act("resolve_identity", gid)
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
            if workflow.patched("proofreading-v1"):
                await self.step(10, "Son okuma denetimleri")
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
                vis, cont, tv = await self._visual_phase(gid, ident, tv, [], failures)
            # All visual identity/continuity writes have completed here. The
            # rebuild activity verifies facts and actors before freezing inputs.
            await self.step(13, "Doğrulama → sürümlü özet, rapor ve indeks")
            produced = None
            # When several books are read at once they take turns on the card, and a book
            # that reaches this step while another holds it cannot start its models. That
            # is a queue, not a defect: the book waits for its turn instead of failing.
            # Without this it failed outright («kahramanini-yutan-kitap», 2026-09-23).
            if workflow.patched("rebuild-capacity-wait-v1"):
                waited = 0
                for attempt in range(40):
                    produced = await self.act("rebuild_outputs", gid, timeout=timedelta(hours=6))
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
                    break
            else:
                for attempt in range(3):
                    produced = await self.act("rebuild_outputs", gid, timeout=timedelta(hours=6))
                    if produced["technical_status"] in ("SUCCEEDED", "ALREADY_CURRENT"):
                        break
                    if produced["technical_status"] == "BUSY":
                        await workflow.sleep(timedelta(seconds=30))
            if produced["technical_status"] not in ("SUCCEEDED", "ALREADY_CURRENT"):
                raise ApplicationError(
                    f"Output revision did not stabilize ({produced['technical_status']})",
                    non_retryable=True)
            summary = {"generation_id":gid,"pages":len(pages),"outputs":produced,
                "step_order":"verified-revision-outputs-v1","accepted":False,
                "analytical_status":"NEEDS_REVIEW",
                "failures":{k:v for k,v in failures.items() if v}}
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
            ident = await self.act("resolve_identity", gid)
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

    async def _visual_phase(self, gid: str, ident: dict, tv: dict, key_pages: list,
                            failures: dict) -> tuple[dict, dict, dict]:
        """Everything the deep vision model does once the characters are known."""
        await self.step(8, "Görsel kimlik (kümeleme ve hakem)", {"characters": ident.get("characters")})
        vis = await self.act("visual_identity", gid)
        await self.step(8, "Karakter sürekliliği", vis)
        cont = await self.act("continuity_checks", gid)
        if key_pages:
            await self.step(9, "Önemli olay sayfalarının derin taraması", {"pages": key_pages})
            _, failures["key_event_scan"] = await self.fan_out("scan_page_deep_key", key_pages, gid)
            await self.act("persist_visual", gid, "all")
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
