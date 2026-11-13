"""Notification work is independent of paid investigation execution."""
from vercel.queue import Message,subscribe
from .cloud_worker import deliver

@subscribe(topic='orange-deliveries',consumer_group='orange-deliveries-v1',max_concurrency=1,max_attempts=5,retry_after=60)
async def run_deliveries(message:Message[dict[str,str]]) -> None:
    await deliver(message.payload['ticket_id'])
