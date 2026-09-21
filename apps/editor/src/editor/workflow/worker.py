"""Temporal worker for the editor task queue. Applies DB migrations and makes
sure the `editor` namespace exists before polling."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import timedelta

from google.protobuf.duration_pb2 import Duration
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest, RegisterNamespaceRequest
from temporalio import activity
from temporalio.client import Client
from temporalio.worker import ActivityInboundInterceptor, ExecuteActivityInput, Interceptor, Worker

from .. import db, foundation
from ..config import settings
from .activities import ALL
from .workflows import BookFullAnalysis

log = logging.getLogger("editor.worker")


class HeartbeatActivityInterceptor(ActivityInboundInterceptor):
    """Report worker liveness; retries still resume through durable DB checkpoints.

    This is not analytical progress. Start-to-close remains the execution limit.
    Older workflow activities without a heartbeat timeout remain unchanged.
    """

    async def execute_activity(self, input: ExecuteActivityInput):
        info = activity.info()
        if not info.heartbeat_timeout:
            return await self.next.execute_activity(input)
        interval = min(20.0, info.heartbeat_timeout.total_seconds() / 3)
        details = {"kind": "worker_liveness", "activity": info.activity_type, "attempt": info.attempt}
        activity.heartbeat(details)

        async def pulse() -> None:
            while True:
                await asyncio.sleep(interval)
                activity.heartbeat(details)

        task = asyncio.create_task(pulse())
        try:
            return await self.next.execute_activity(input)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


class HeartbeatInterceptor(Interceptor):
    def intercept_activity(self, next: ActivityInboundInterceptor) -> ActivityInboundInterceptor:
        return HeartbeatActivityInterceptor(next)


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
    # A restart must not resume the old workflow while foundation work is paused.
    await asyncio.to_thread(foundation.assert_enabled)
    await ensure_namespace(s.temporal_address, s.temporal_namespace)
    client = await Client.connect(s.temporal_address, namespace=s.temporal_namespace)
    worker = Worker(client, task_queue=s.task_queue, workflows=[BookFullAnalysis], activities=ALL,
                    max_concurrent_activities=48, interceptors=[HeartbeatInterceptor()],
                    max_heartbeat_throttle_interval=timedelta(seconds=20),
                    default_heartbeat_throttle_interval=timedelta(seconds=20))
    log.info("worker polling %s/%s", s.temporal_namespace, s.task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
