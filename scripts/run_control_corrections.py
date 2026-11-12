"""Paired reruns of five independently documented fixture corrections.

Original 20-case scores remain unchanged. Same prompts/models/limits; corrected
telemetry only. Reuses the existing Plain threads and external issue references.
"""
import asyncio,json,hashlib
from pathlib import Path
from statistics import mean
import httpx
from run_composio_campaign import ROOT,SOURCE_PATHS,complaint,write
from orange_incident.llm_agents import configuration
from orange_incident.single_agent import run_single_agent
from orange_incident.tools import Simulation
from orange_incident.contracts import Submission
from orange_incident.benchmark import load_dataset,score
OUT=ROOT/'runs/composio-v31'

async def main():
    original=json.loads((ROOT/'runs/composio-v3/comparison-original.json').read_text())
    original_manifest=json.loads((ROOT/'runs/composio-v3/manifest.json').read_text())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==original_manifest['hashes'][p] for p in SOURCE_PATHS),'Matched agent runtime changed before corrected-data evaluation'
    _,models=configuration(ROOT);assert set(models.values())=={'gpt-5.4'}
    ids=[c['id'] for c in json.loads((OUT/'control-corrections.json').read_text())]
    previous=json.loads((OUT/'comparison.json').read_text()) if (OUT/'comparison.json').exists() else {}
    old={r['id']:r for r in previous.get('cases',[])};mapping={r['id']:r for r in original['cases']}
    rows=[old.get(i,{'id':i,'ticket_id':mapping[i]['ticket_id'],'status':'queued'}) for i in ids]
    fixtures,truth=load_dataset(ROOT)
    write(OUT/'manifest.json',{'dataset_version':'3.1','case_ids':ids,'model':'gpt-5.4','models':models,'runtime_hashes':{p:original_manifest['hashes'][p] for p in SOURCE_PATHS},
        'fixture_hashes':{i:hashlib.sha256((ROOT/f'data/incidents/{i}.json').read_bytes()).hexdigest() for i in ids},'changes':'Only the documented successful-control fields changed. Original first-attempt results retained separately.','global_limits':{k:original_manifest[k] for k in ('model_requests_per_run','tool_attempts_per_run','deadline_seconds','output_tokens_per_request','max_total_context_chars')}})
    def publish(status='running'):
        summary={}
        for arm in ('multi_agent','single_agent'):
            metrics=[r[arm]['metrics'] for r in rows if arm in r]
            if metrics:summary[arm]={'evaluated_cases':len(metrics),'root_cause_accuracy':mean(float(m['root_cause_top1']) for m in metrics),'grounded_top1':mean(float(m['grounded_top1']) for m in metrics),'mean_latency_seconds':mean(m['latency_seconds'] for m in metrics),'total_tokens':sum((m['input_tokens'] or 0)+(m['output_tokens'] or 0) for m in metrics)}
        write(OUT/'comparison.json',{'status':status,'expected_cases':len(ids),'completed_pairs':sum('multi_agent' in r and 'single_agent' in r for r in rows),'summary':summary,'cases':rows})
    def evaluate(case,result):return {'outcome':result.report.outcome,'run_status':result.run_status,'top_cause':next(iter(result.ranked_cause_codes),None),'metrics':score(result,fixtures[case],truth[case])}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=40) as client:
        for row in rows:
            response=await client.post('/api/tickets/'+row['ticket_id']+'/reinvestigate',json={'reason':'Reevaluate documented corrected sandbox-control fields in synthetic dataset version 3.1; preserve the original result.'},headers={'Idempotency-Key':'control-v31:'+row['id']})
            response.raise_for_status();publish();print(json.dumps({'reinvestigation_queued':row['id'],'new_plain_thread':False}),flush=True)
        async def singles():
            for row in rows:
                case=row['id'];target=OUT/'single_agent'/case/f'{case}.json'
                if target.exists():result=Submission.model_validate_json(target.read_text())
                else:
                    simulation=Simulation(ROOT/f'data/incidents/{case}.json');body=complaint(case);simulation.incident.title=body['title'];simulation.incident.description=body['description']
                    result=await run_single_agent(simulation,target.parent,root=ROOT)
                write(OUT/'single_agent/submissions'/f'{case}.json',result.model_dump());row['single_agent']=evaluate(case,result);publish();print(json.dumps({'corrected_baseline':case,'outcome':result.report.outcome,'correct':row['single_agent']['metrics']['root_cause_top1']}),flush=True)
        baseline=asyncio.create_task(singles());done={r['id'] for r in rows if 'multi_agent' in r}
        while len(done)<len(rows):
            listed=(await client.get('/api/tickets',params={'summary':'true'})).json();index={t['id']:t for t in listed}
            for row in rows:
                if row['id'] in done:continue
                status=index[row['ticket_id']]['status'];row['status']=status
                if status not in ('needs_review','reviewed','changes_requested','failed'):continue
                ticket=(await client.get('/api/tickets/'+row['ticket_id'])).json()
                if sum(e['type']=='investigation_started' for e in ticket['events'])<2:continue
                payload={k:v for k,v in ticket['result'].items() if k!='workflow'};result=Submission.model_validate(payload)
                write(OUT/'multi_agent/submissions'/f"{row['id']}.json",payload);write(OUT/'multi_agent'/row['id']/'ticket.json',ticket)
                row['multi_agent']=evaluate(row['id'],result);row['integrations']=ticket['integrations'];done.add(row['id']);publish()
                print(json.dumps({'corrected_multi':row['id'],'outcome':result.report.outcome,'correct':row['multi_agent']['metrics']['root_cause_top1']}),flush=True)
            if len(done)<len(rows):await asyncio.sleep(5)
        await baseline;publish('complete')
        print(json.dumps({'corrected_pairs_complete':len(rows),'summary':json.loads((OUT/'comparison.json').read_text())['summary']}),flush=True)

if __name__=='__main__':asyncio.run(main())
