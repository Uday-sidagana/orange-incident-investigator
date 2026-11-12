"""Read-only audit of all twenty live demo workflows and frozen results."""
from pathlib import Path
import json,hashlib
import httpx
from run_composio_campaign import complaint
ROOT=Path(__file__).resolve().parents[1]
original=json.loads((ROOT/'runs/composio-v3/comparison-original.json').read_text())
checks=[]
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=30) as client:
    health=client.get('/api/health').json()
    assert health['runtime']=='openai' and health['plain_mode']=='live'
    assert all(v['enabled'] for v in health['integrations'].values())
    for row in original['cases']:
        ticket=client.get('/api/tickets/'+row['ticket_id']).json()
        events=ticket['events'];result=ticket.get('result') or {};workflow=result.get('workflow') or {}
        log=client.get('/api/tickets/'+row['ticket_id']+'/agent-log').json()
        expected_hash=next(x['exact_plain_input_hash'] for x in json.loads((ROOT/'runs/plain-input-matching/results.json').read_text())['cases'] if x['version']=='composio-v3' and x['id']==row['id'])
        item={'case_id':row['id'],'ticket_id':row['ticket_id'],
              'plain_created_once':sum(e['type']=='plain_thread_created' for e in events)==1,
              'plain_read_verified':any(e['type']=='plain_thread_read' and e['payload'].get('mode')=='live' for e in events),
              'same_plain_thread':ticket['plain']['thread_id']==row['plain_thread_id'],
              'same_question_as_baseline':hashlib.sha256(json.dumps({k:ticket['complaint'][k] for k in ('title','description')},sort_keys=True).encode()).hexdigest()==expected_hash,
              'latest_report_completed':result.get('run_status')=='completed',
              'all_six_roles_complete':{t['role'] for t in workflow.get('tasks',[])}=={'orchestrator','observability','dependency','reasoning','critic','reporting'} and all(t['status']=='complete' for t in workflow.get('tasks',[])),
              'same_linear_issue':ticket['integrations']['linear']['id']==row['integrations']['linear']['id'],
              'same_slack_root':ticket['integrations']['slack']==row['integrations']['slack'],
              'all_deliveries_acknowledged':all(j['status']=='complete' for j in ticket['deliveries']),
              'logs_have_questions_and_tool_results':any(t['question'] and any(q.get('result') for q in t['queries']) for t in log['tasks']),
              'customer_reply_not_sent':all(not e['payload'].get('sent',False) for e in events if e['type']=='response_drafted') and all(not e['payload'].get('response_sent',False) for e in events if e['type']=='review_recorded'),
              'linear_url':ticket['integrations']['linear']['url'],'latest_outcome':result.get('report',{}).get('outcome'),'latest_top_cause':next(iter(result.get('ranked_cause_codes',[])),None),'attempts':sum(e['type']=='investigation_started' for e in events)}
        flags=[value for value in item.values() if isinstance(value,bool)]
        assert all(flags),(row['id'],{k:v for k,v in item.items() if v is False})
        checks.append(item)
    data=client.get('/api/comparison').json();assert data['completed_pairs']==20 and data['control_correction']['completed_pairs']==5
    assert data['operational_recovery']['cases'][0]['run_status']=='completed'
    assert client.get('/').status_code==200
report={'case_count':20,'all_checks_passed':True,'health':health,'cases':checks,
        'notice':'Workflow success is separate from diagnostic accuracy. Original first-attempt metrics and reviewer exceptions remain unchanged.'}
(ROOT/'runs/composio-v3/workflow-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'audited_cases':len(checks),'all_checks_passed':True,'latest_completed_reports':sum(c['latest_report_completed'] for c in checks),'same_plain_threads':sum(c['same_plain_thread'] for c in checks),'same_linear_issues':sum(c['same_linear_issue'] for c in checks),'same_slack_roots':sum(c['same_slack_root'] for c in checks)},indent=2))
