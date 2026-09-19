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

    async def act(self, name: str, *args, timeout: timedelta = LONG):
        return await workflow.execute_activity(name, args=list(args), start_to_close_timeout=timeout,
                                               retry_policy=RETRY)

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
        if items and len(failed) == len(items):
            # every page failed (e.g. gpu_busy): stop instead of sealing an empty generation
            raise ApplicationError(f"{name}: {len(items)}/{len(items)} failed: {failed[0]['error']}",
                                   non_retryable=True)
        return [r for r in res if not (isinstance(r, dict) and "failed" in r)], \
               [r for r in res if isinstance(r, dict) and "failed" in r]

    @workflow.run
    async def run(self, job_id: str) -> dict:
        self.job_id = job_id
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
            await self.step(8, "Karakter sürekliliği", {"characters": ident.get("characters")})
            cont = await self.act("continuity_checks", gid)
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
            # 14. Çelişkiler -> NEEDS_REVIEW
            await self.step(14, "Çelişkiler ve editör kuyruğu")
            con = await self.act("contradictions", gid)
            # 15. Regresyon, rapor, nesli mühürle
            await self.step(15, "Regresyon ve rapor")
            reg = await self.act("regression", gid)
            rep = await self.act("report", gid)
            summary = {"generation_id": gid, "pages": len(pages), "ocr_pages": len(man["needs_ocr"]),
                       "uncertain_pages": uncertain, "extract": ext, "identity": ident,
                       "continuity": cont, "modality": mod, "merge": mrg, "narrative_roles": roles, "emotions_themes": emo,
                       "index": idx, "book_summary": book, "critic": crit, "contradictions": con,
                       "regression_passed": reg["passed"], "report_id": rep["report_id"],
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
