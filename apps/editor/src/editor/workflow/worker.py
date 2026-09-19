"""Temporal worker for the editor task queue. Applies DB migrations and makes
sure the `editor` namespace exists before polling."""

from __future__ import annotations

import asyncio
import logging

from google.protobuf.duration_pb2 import Duration
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest, RegisterNamespaceRequest
from temporalio.client import Client
from temporalio.worker import Worker

from .. import db
from ..config import settings
from .activities import ALL
from .workflows import BookFullAnalysis

log = logging.getLogger("editor.worker")


async def ensure_namespace(address: str, namespace: str) -> None:
    c = await Client.connect(address, namespace="default")
    try:
        await c.workflow_service.describe_namespace(DescribeNamespaceRequest(namespace=namespace))
    except Exception:  # noqa: BLE001 - NotFound
        await c.workflow_service.register_namespace(RegisterNamespaceRequest(
            namespace=namespace, workflow_execution_retention_period=Duration(seconds=90 * 86400)))
        log.info("registered namespace %s", namespace)
        await asyncio.sleep(12)  # namespace cache refresh


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    s = settings()
    log.info("migrations: %s", await asyncio.to_thread(db.migrate) or "up to date")
    await ensure_namespace(s.temporal_address, s.temporal_namespace)
    client = await Client.connect(s.temporal_address, namespace=s.temporal_namespace)
    worker = Worker(client, task_queue=s.task_queue, workflows=[BookFullAnalysis], activities=ALL,
                    max_concurrent_activities=48)
    log.info("worker polling %s/%s", s.temporal_namespace, s.task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
