"""Publish explicit assistant review notes; never generates or guesses a review."""
import json
import argparse
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--run',choices=['composio-v3','composio-v31','context-recovery'],default='composio-v3');args=parser.parse_args()
OUT=ROOT/'runs'/args.run
reviews=json.loads((OUT/'reviews.json').read_text());comparison=json.loads((OUT/'comparison.json').read_text())
ids={row['id']:row['ticket_id'] for row in comparison['cases'] if row.get('ticket_id')}
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=30) as client:
    for case_id,review in reviews.items():
        if case_id not in ids:continue
        ticket=client.get('/api/tickets/'+ids[case_id]).json()
        if ticket['status'] not in ('needs_review','reviewed','changes_requested'):
            print(json.dumps({'review_pending':case_id,'status':ticket['status']}));continue
        latest_start=max((e['sequence'] for e in ticket['events'] if e['type']=='investigation_started'),default=-1)
        matching=[e for e in ticket['events'] if e['sequence']>latest_start and e['type']=='review_recorded' and e['payload'].get('reviewer')=='assistant' and e['payload']['notes']==review['notes']]
        if not matching:
            response=client.post('/api/tickets/'+ids[case_id]+'/reviews',json={'reviewer':'assistant','verdict':review['verdict'],'notes':review['notes']})
            response.raise_for_status();ticket=response.json()
        review['ticket_id']=ids[case_id];review['published']=True
        print(json.dumps({'reviewed':case_id,'verdict':review['verdict']}))
(OUT/'reviews.json').write_text(json.dumps(reviews,indent=2)+'\n')
