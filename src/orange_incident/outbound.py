"""Durable outbound workflow. Notification failures never rewrite investigation results."""
import asyncio
from .channels import DeliveryFailure, LinearClient, SlackClient


def enabled(value):
    return str(value or 'false').lower()=='true'


from .presentation import linear_description as description, slack_fallback as slack_text, slack_blocks


class OutboundIntegrations:
    def __init__(self,store,config=None,clients=None):
        self.store=store
        self.clients=dict(clients or {})
        self.status={name:{'enabled':name in self.clients,'status':'configured' if name in self.clients else 'disabled'} for name in ('linear','slack')}
        config=config or {}
        requirements={'linear':('LINEAR_API_KEY','LINEAR_TEAM_ID'),'slack':('SLACK_BOT_TOKEN','SLACK_CHANNEL_ID')}
        for name,keys in requirements.items():
            if name in self.clients or not enabled(config.get(name.upper()+'_ENABLED')):
                continue
            if not all(config.get(key) for key in keys):
                self.status[name]={'enabled':False,'status':'setup_required'}
                continue
            self.clients[name]=(LinearClient(config[keys[0]],config[keys[1]]) if name=='linear' else SlackClient(config[keys[0]],config[keys[1]]))
            self.status[name]={'enabled':True,'status':'configured'}

    def enqueue(self,ticket,stage):
        for provider in self.clients:
            self.store.enqueue_delivery(ticket['id'],provider,stage)

    async def process_one(self,ticket_id=None):
        job=self.store.claim_delivery(self.clients.keys(),ticket_id=ticket_id)
        if job is None:
            return False
        provider,stage=job['provider'],job['stage']
        ticket=self.store.get(job['ticket_id'])
        reference=self.store.delivery_reference(ticket['id'],provider)
        try:
            if stage=='intake' and reference is not None:
                self.store.delivery_complete(job,reference)
                return True
            if stage!='intake' and reference is None:
                self.store.delivery_failed(job,'blocked','Resolve the initial delivery before posting updates.')
                return True
            if provider=='linear':
                result=await (self.clients[provider].create(ticket,description(ticket)) if stage=='intake' else self.clients[provider].update(reference,description(ticket)))
            else:
                linear=self.store.delivery_reference(ticket['id'],'linear')
                if stage.startswith('summary-'):
                    result=await self.clients[provider].update(reference,slack_text(ticket,stage,linear),blocks=slack_blocks(ticket,stage,linear))
                else:
                    result=await self.clients[provider].post(slack_text(ticket,stage,linear),thread_ts=reference['ts'] if reference else None,channel_id=reference['channel'] if reference else None,blocks=slack_blocks(ticket,stage,linear))
            self.store.delivery_complete(job,result)
            if provider=='slack' and stage!='intake' and not stage.startswith('summary-'):
                self.store.enqueue_delivery(ticket['id'],'slack','summary-'+stage)
        except DeliveryFailure as exc:
            self.store.delivery_failed(job,'attention_required' if exc.uncertain else 'failed',str(exc))
        except asyncio.CancelledError:
            raise
        except Exception:
            self.store.delivery_failed(job,'attention_required','Delivery could not be confirmed; inspect the destination.')
        return True

    async def close(self):
        for client in self.clients.values():
            await client.close()
