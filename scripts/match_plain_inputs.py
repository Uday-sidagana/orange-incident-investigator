"""Correct the comparison input mismatch caused by Plain-generated summaries.

Uses the preserved original runtime, exact saved multi-agent complaint text, and
corresponding original/corrected telemetry. Never selects between repeat answers.
"""
import sys,json,asyncio,hashlib,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];FROZEN=ROOT/'runs/composio-v3/frozen-v30'
sys.path.insert(0,str(FROZEN/'src'))
from dotenv import dotenv_values
from orange_incident.single_agent import run_single_agent
from orange_incident.llm_agents import AgentProvider,ModelLimits
from orange_incident.tools import Simulation
from orange_incident.contracts import Submission
from orange_incident.benchmark import load_dataset,score
import orange_incident
assert Path(orange_incident.__file__).resolve().is_relative_to(FROZEN)

def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)

async def main():
 key=dotenv_values(ROOT/'.env')['OPENAI_API_KEY'];semaphore=asyncio.Semaphore(3)
 original=json.loads((ROOT/'runs/composio-v3/comparison-original.json').read_text());corrected=json.loads((ROOT/'runs/composio-v31/comparison.json').read_text())
 tasks=[];matched=[]
 async def one(version,row):
  async with semaphore:
   directory=ROOT/'runs'/version;case=row['id'];ticket=json.loads((directory/'multi_agent'/case/'ticket.json').read_text());body=ticket['complaint']
   source=FROZEN if version=='composio-v3' else ROOT
   old=Submission.model_validate_json((directory/'single_agent'/case/f'{case}.json').read_text())
   fixture=json.loads((source/f'data/incidents/{case}.json').read_text())
   portal_title='[DEMO C'+case[-3:]+'] '+fixture['incident']['title']
   same=body['title']==portal_title and body['description']==fixture['incident']['description']
   target=directory/'single_agent_plain_matched'/case/f'{case}.json'
   if target.exists():result=Submission.model_validate_json(target.read_text())
   elif same:
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(directory/'single_agent'/case/f'{case}.json',target);result=old
   else:
    simulation=Simulation(source/f'data/incidents/{case}.json');simulation.incident.title=body['title'];simulation.incident.description=body['description']
    provider=AgentProvider(key,{'single_agent':'gpt-5.4'},limits=ModelLimits(max_collection_rounds=20,max_queries_per_task=24))
    try:result=await run_single_agent(simulation,target.parent,root=source,provider=provider)
    finally:await provider.close()
   write(directory/'single_agent_plain_matched/submissions'/f'{case}.json',result.model_dump())
   fixtures,truth=load_dataset(source)
   item={'version':version,'id':case,'same_as_portal_text':same,'rerun_required':not same,'exact_plain_input_hash':hashlib.sha256(json.dumps({'title':body['title'],'description':body['description']},sort_keys=True).encode()).hexdigest(),
         'single_agent':{'outcome':result.report.outcome,'run_status':result.run_status,'top_cause':next(iter(result.ranked_cause_codes),None),'metrics':score(result,fixtures[case],truth[case])}}
   matched.append(item);write(ROOT/'runs/plain-input-matching/progress.json',{'completed':len(matched),'expected':25,'cases':matched})
   print(json.dumps({'input_matched':version+'/'+case,'reused_original':same,'outcome':result.report.outcome,'correct':item['single_agent']['metrics']['root_cause_top1']}),flush=True)
 for version,data in [('composio-v3',original),('composio-v31',corrected)]:
  for row in data['cases']:tasks.append(one(version,row))
 await asyncio.gather(*tasks)
 write(ROOT/'runs/plain-input-matching/results.json',{'status':'complete','matched_pairs':25,'note':'Two baseline inputs were already exact and reused; other baselines rerun once with exact saved Plain descriptions using frozen original runtime. Preliminary portal-text baseline results retained.','cases':matched})

if __name__=='__main__':asyncio.run(main())
