"""Resumable, first-attempt paired evaluation with real Plain intake.

Agents never receive evaluator labels. Scoring runs outside the investigation
runtime. This runner never replays failed model runs to select a better answer.
"""
import asyncio
import hashlib
import json
from pathlib import Path
from datetime import datetime,timezone
from statistics import mean,median
import httpx
from orange_incident.single_agent import run_single_agent
from orange_incident.tools import Simulation
from orange_incident.contracts import Submission
from orange_incident.benchmark import load_dataset,score

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runs/composio-v3'
IDS=json.loads((ROOT/'evaluation/splits.json').read_text())['prospective_comparison']
SOURCE_PATHS=['src/orange_incident/llm_agents.py','src/orange_incident/single_agent.py','src/orange_incident/engine.py','src/orange_incident/tools.py','src/orange_incident/models.py','src/orange_incident/contracts.py','data/rubric.json']

def stamp():return datetime.now(timezone.utc).isoformat()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(path)
def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCE_PATHS+[f'data/incidents/{i}.json' for i in IDS]}
def complaint(case_id):
    incident=json.loads((ROOT/f'data/incidents/{case_id}.json').read_text())['incident']
    return {'name':'Synthetic Customer '+case_id[-3:],'email':f'composio-demo-{case_id[-3:]}@example.invalid','company':'Cedar Demo '+case_id[-3:],
            'title':'[DEMO C'+case_id[-3:]+'] '+incident['title'],'description':incident['description'],'scenario_id':case_id}

async def main():
    from orange_incident.llm_agents import configuration
    _,models=configuration(ROOT)
    if set(models.values())!={'gpt-5.4'}:raise RuntimeError('Freeze the matched GPT-5.4 model profile before running')
    manifest_path=OUT/'manifest.json'
    current=hashes()
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text())
        if manifest['hashes']!=current:raise RuntimeError('Frozen agent/data configuration changed. Use a new run version.')
    else:
        manifest={'run_id':'composio-v3','created_at':stamp(),'model':'gpt-5.4','models':models,'reasoning_effort':'low','case_ids':IDS,
                  'hashes':current,'replicates_per_arm':1,'model_requests_per_run':24,'output_tokens_per_request':4000,'tool_attempts_per_run':24,
                  'deadline_seconds':360,'model_provider_attempts':2,'tool_attempts_per_query':2,'max_total_context_chars':700000,
                  'multi_workers':2,'baseline_workers':1,'same_tools':True,'synthetic':True,'holdout_note':'New author-visible prospective cohort; no prompt adaptation during this run. Original held-out partition untouched.',
                  'latency_note':'Measured investigation time excludes Plain queue and outbound delivery. Runs share local and provider resources; latency is not an isolated-service benchmark.'}
        write(manifest_path,manifest)
    previous=json.loads((OUT/'comparison.json').read_text()) if (OUT/'comparison.json').exists() else {}
    indexed={c['id']:c for c in previous.get('cases',[])}
    rows=[indexed.get(i,{'id':i,'status':'queued'}) for i in IDS]
    fixtures,truth=load_dataset(ROOT)
    completed=set()
    def publish(status='running'):
        summary={}
        for arm in ('multi_agent','single_agent'):
            scored=[r[arm]['metrics'] for r in rows if r.get(arm,{}).get('metrics')]
            if not scored:continue
            summary[arm]={'evaluated_cases':len(scored),'root_cause_accuracy':mean(float(m['root_cause_top1']) for m in scored),
                          'outcome_accuracy':mean(float(m['outcome_correct']) for m in scored),'citation_validity':mean(m['citation_validity'] for m in scored),
                          'grounded_top1':mean(float(m['grounded_top1']) for m in scored),'finding_precision':mean(m['finding_precision'] for m in scored),
                          'finding_recall':mean(m['finding_recall'] for m in scored),'action_precision':mean(m['action_precision'] for m in scored),
                          'mean_tool_calls':mean(m['tool_calls'] for m in scored),'mean_latency_seconds':mean(m['latency_seconds'] for m in scored),
                          'median_latency_seconds':median(m['latency_seconds'] for m in scored),
                          'input_tokens':sum(m['input_tokens'] or 0 for m in scored),'output_tokens':sum(m['output_tokens'] or 0 for m in scored),
                          'total_tokens':sum((m['input_tokens'] or 0)+(m['output_tokens'] or 0) for m in scored)}
        pairs=sum(bool(r.get('multi_agent') and r.get('single_agent')) for r in rows)
        write(OUT/'comparison.json',{'status':status,'updated_at':stamp(),'expected_cases':len(IDS),'completed_pairs':pairs,'model':'gpt-5.4','summary':summary,'cases':rows})
    def scored(case_id,result):
        return {'outcome':result.report.outcome,'run_status':result.run_status,'top_cause':next(iter(result.ranked_cause_codes),None),
                'metrics':score(result,fixtures[case_id],truth[case_id])}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=45) as client:
        health=(await client.get('/api/health')).json()
        assert health['runtime']=='openai' and health['plain_mode']=='live' and health['worker_count']==2
        assert all(v['enabled'] for v in health['integrations'].values())
        publish()
        # A created/uncertain Plain thread is never blindly created again.
        for row in rows:
            if row.get('ticket_id'):continue
            response=await client.post('/api/tickets',json=complaint(row['id']),headers={'Idempotency-Key':'composio-v3:'+row['id']})
            response.raise_for_status();ticket=response.json()['ticket'];row['ticket_id']=ticket['id'];row['plain_thread_id']=ticket['plain']['thread_id'];row['status']=ticket['status']
            publish();print(json.dumps({'submitted':row['id'],'ticket_id':ticket['id'],'status':ticket['status']}),flush=True)
        async def baselines():
            for row in rows:
                case_id=row['id'];target=OUT/'single_agent'/case_id/f'{case_id}.json'
                if target.exists():result=Submission.model_validate_json(target.read_text())
                else:
                    simulation=Simulation(ROOT/f'data/incidents/{case_id}.json');body=complaint(case_id)
                    simulation.incident.title=body['title'];simulation.incident.description=body['description']
                    result=await run_single_agent(simulation,target.parent,root=ROOT,model='gpt-5.4')
                write(OUT/'single_agent/submissions'/f'{case_id}.json',result.model_dump())
                row['single_agent']=scored(case_id,result);publish()
                print(json.dumps({'baseline_done':case_id,'outcome':result.report.outcome,'correct':row['single_agent']['metrics']['root_cause_top1']}),flush=True)
        baseline_task=asyncio.create_task(baselines())
        observed={}
        while len(completed)<len(rows):
            summaries=(await client.get('/api/tickets',params={'summary':'true'})).json();by_id={t['id']:t for t in summaries}
            for row in rows:
                if row['id'] in completed:continue
                state=by_id.get(row['ticket_id'],{})
                if observed.get(row['id'])!=state.get('status'):
                    row['status']=state.get('status','unknown');observed[row['id']]=row['status'];publish()
                    print(json.dumps({'multi_status':row['id'],'status':row['status']}),flush=True)
                if state.get('status') not in ('needs_review','reviewed','changes_requested','failed','plain_attention_required'):continue
                ticket=(await client.get('/api/tickets/'+row['ticket_id'])).json()
                write(OUT/'multi_agent'/row['id']/'ticket.json',ticket)
                result=ticket.get('result')
                if result:
                    payload={k:v for k,v in result.items() if k!='workflow'};submission=Submission.model_validate(payload)
                    write(OUT/'multi_agent/submissions'/f"{row['id']}.json",payload);row['multi_agent']=scored(row['id'],submission)
                else:
                    row['multi_agent']={'outcome':'execution_failed','run_status':'failed','error':ticket.get('error')}
                row['deliveries']=ticket['deliveries'];row['integrations']=ticket['integrations']
                row['agent_log_url']='/api/tickets/'+row['ticket_id']+'/agent-log'
                log=(await client.get(row['agent_log_url'])).json();write(OUT/'multi_agent'/row['id']/'agent-log.json',log)
                completed.add(row['id']);publish()
                print(json.dumps({'multi_done':row['id'],'outcome':row['multi_agent']['outcome'],'correct':row['multi_agent'].get('metrics',{}).get('root_cause_top1')}),flush=True)
            if len(completed)<len(rows):await asyncio.sleep(5)
        await baseline_task
        # Check outbound completion separately; model latency and accuracy exclude notification time.
        for _ in range(36):
            all_done=True
            for row in rows:
                t=(await client.get('/api/tickets/'+row['ticket_id'])).json();row['deliveries']=t['deliveries'];row['integrations']=t['integrations']
                if any(j['status'] in ('pending','sending','blocked') for j in t['deliveries']):all_done=False
            publish()
            if all_done:break
            await asyncio.sleep(5)
        publish('complete')
        print(json.dumps({'complete_pairs':len(rows),'artifact':str(OUT/'comparison.json')}),flush=True)

if __name__=='__main__':asyncio.run(main())
