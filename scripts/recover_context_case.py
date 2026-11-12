"""One operational recovery; deliberately excluded from both frozen comparisons."""
import asyncio,json,hashlib
from pathlib import Path
import httpx
from orange_incident.llm_agents import configuration
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runs/context-recovery';OUT.mkdir(exist_ok=True)
async def main():
    original=json.loads((ROOT/'runs/composio-v3/comparison-original.json').read_text());row=next(r for r in original['cases'] if r['id']=='github-token-036')
    _,models=configuration(ROOT)
    (OUT/'manifest.json').write_text(json.dumps({'purpose':'Post-benchmark operational recovery, not a replacement benchmark score','case_id':row['id'],'ticket_id':row['ticket_id'],'models':models,'model_requests':24,'tool_attempts':24,'deadline_seconds':360,'max_total_context_chars':700000,'changes':['Canonical observation deduplication','Reuse native collection summary instead of another model request','Reserve context capacity before critic follow-ups'],'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['src/orange_incident/llm_agents.py','src/orange_incident/context_projection.py']}},indent=2)+'\n')
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=40) as c:
        response=await c.post('/api/tickets/'+row['ticket_id']+'/reinvestigate',headers={'Idempotency-Key':'bounded-context-v1:'+row['id']},json={'reason':'Recover the prior context-budget execution failure using deduplicated observations, reused collection summaries and reserved reporting capacity; original benchmark result retained.'})
        response.raise_for_status();print(json.dumps({'recovery_queued':row['id'],'same_plain_thread':True}),flush=True)
        previous=None
        for _ in range(85):
            ticket=(await c.get('/api/tickets/'+row['ticket_id'])).json()
            value=(ticket['status'],len(ticket['events']))
            if value!=previous:print(json.dumps({'status':value[0],'events':value[1]}),flush=True);previous=value
            if sum(e['type']=='investigation_started' for e in ticket['events'])>=2 and ticket['status'] in ('needs_review','failed','reviewed','changes_requested'):break
            await asyncio.sleep(5)
        (OUT/'ticket.json').write_text(json.dumps(ticket,indent=2)+'\n')
        log=(await c.get('/api/tickets/'+row['ticket_id']+'/agent-log')).json();(OUT/'agent-log.json').write_text(json.dumps(log,indent=2)+'\n')
        result=ticket.get('result') or {};report=result.get('report') or {}
        summary={'id':row['id'],'ticket_id':row['ticket_id'],'status':ticket['status'],'run_status':result.get('run_status'),'outcome':report.get('outcome'),'top_cause':next(iter(result.get('ranked_cause_codes',[])),None),'input_tokens':result.get('input_tokens'),'output_tokens':result.get('output_tokens'),'latency_seconds':result.get('latency_seconds'),'original_benchmark_result_retained':True}
        (OUT/'comparison.json').write_text(json.dumps({'status':'complete','cases':[summary]},indent=2)+'\n')
        print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':asyncio.run(main())
