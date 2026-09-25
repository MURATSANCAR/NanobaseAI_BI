"""Stüdyo işçisi: `editor-production` kuyruğunu dinler (flow.py). Aynı anda tek etkinlik; görsel model ve
ana model aynı kartı paylaştığı için GPU işleri sırayla yürür, sıra Temporal'da kalıcıdır.

    python -m editor.production.worker
"""

from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from ..config import settings
from ..workflow.worker import ensure_namespace
from .flow import ACTIVITIES, QUEUE, WORKFLOWS

log = logging.getLogger("editor.production.worker")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    s = settings()
    await ensure_namespace(s.temporal_address, s.temporal_namespace)
    client = await Client.connect(s.temporal_address, namespace=s.temporal_namespace)
    worker = Worker(client, task_queue=QUEUE, workflows=WORKFLOWS, activities=ACTIVITIES,
                    max_concurrent_activities=1)
    log.info("studio worker polling %s/%s", s.temporal_namespace, QUEUE)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
