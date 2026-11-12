import asyncio,json,sys,hashlib
from pathlib import Path
from dotenv import dotenv_values
from orange_incident.plain import PlainClient
from orange_incident.benchmark import load_dataset,score
from orange_incident.contracts import Submission
R=Path.cwd();frozen=R/'runs/composio-v3/frozen-v30';matched=json.loads((R/'runs/plain-input-matching/results.json').read_text());checks=[]
for version in ['composio-v3','composio-v31']:
 fixtures,truth=load_dataset(frozen if version=='composio-v3' else R)
 for item in [x for x in matched['cases'] if x['version']==version]:
  submission=Submission.model_validate_json((R/'runs'/version/'single_agent_plain_matched'/item['id']/(item['id']+'.json')).read_text())
  assert score(submission,fixtures[item['id']],truth[item['id']])==item['single_agent']['metrics'];checks.append(version+'/'+item['id'])
async def live():
 client=PlainClient(dotenv_values(R/'.env')['PLAIN_API_KEY'])
 try:
  row=json.loads((R/'runs/composio-v3/comparison.json').read_text())['cases'][2];thread=await client.read_thread(row['plain_thread_id']);fixture=json.loads((frozen/'data/incidents'/f"{row['id']}.json").read_text());assert any(m['text']==fixture['incident']['description'] for m in thread['original_messages']);return {'case':row['id'],'original_plain_message_verified':True,'summary_differs_from_original':thread['description']!=fixture['incident']['description']}
 finally:await client.close()
report={'matched_baseline_scores_reproduced':len(checks),'plain_read_probe':asyncio.run(live())};(R/'runs/plain-input-matching/final-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
