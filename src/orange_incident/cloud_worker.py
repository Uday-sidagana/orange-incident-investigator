"""One bounded job per invocation; paid investigations are never blindly replayed."""
import asyncio
import tempfile
from pathlib import Path
from uuid import UUID
from .hosted import create_service,publish_work


async def investigate(ticket_id,*,root=None,store=None,factory=None,publish=None):
    ticket_id=str(UUID(ticket_id));root=Path(root or Path.cwd())
    with tempfile.TemporaryDirectory(prefix='orange-investigation-') as scratch:
        app=(factory or create_service)(root,store=store,output_root=Path(scratch))
        store=app.state.store
        async def dispatch(kind):
            if publish:await publish(ticket_id,kind)
            else:await publish_work(store,ticket_id,kind)
        try:
            store.expire_hosted_work(ticket_id)
            ticket=store.get(ticket_id)
            if ticket is None:return
            if ticket['status']=='investigating':raise RuntimeError('Another invocation holds the investigation lease; redeliver later.')
            if ticket['status'] in ('queued','awaiting_plain_read'):
                # 240s model deadline leaves time for Plain, persistence and dispatch.
                async with asyncio.timeout(275):await app.state.process_next(ticket_id)
            finished=store.get(ticket_id)
            if finished['status']=='investigating':raise RuntimeError('Investigation still holds a lease; wait for expiry before redelivery.')
            if finished['status'] in ('needs_review','reviewed','changes_requested','failed'):
                app.state.notifications.enqueue(finished,'report' if finished['status']!='failed' else 'failure')
                await dispatch('deliver')
        finally:await app.state.close_resources()


async def deliver(ticket_id,*,root=None,store=None,factory=None):
    ticket_id=str(UUID(ticket_id));root=Path(root or Path.cwd())
    app=(factory or create_service)(root,store=store)
    store=app.state.store
    try:
        store.expire_hosted_deliveries(ticket_id)
        async with asyncio.timeout(110):
            for _ in range(20):
                if not await app.state.process_delivery(ticket_id):break
        ticket=store.get(ticket_id)
        if ticket and any(j['status'] in ('pending','sending') for j in ticket['deliveries']):
            raise RuntimeError('Notification delivery remains pending; redeliver later.')
    finally:await app.state.close_resources()
