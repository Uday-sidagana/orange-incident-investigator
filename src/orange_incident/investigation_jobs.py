"""Private native Vercel Queue subscriber; no public worker URL."""
from vercel.queue import Message,subscribe
from .cloud_worker import investigate

@subscribe(topic='orange-investigations',consumer_group='orange-investigations-v1',max_concurrency=1,max_attempts=8,retry_after=60)
async def run_investigation(message:Message[dict[str,str]]) -> None:
    await investigate(message.payload['ticket_id'])
