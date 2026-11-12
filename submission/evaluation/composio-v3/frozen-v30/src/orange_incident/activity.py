"""Reviewer-facing work logs assembled from persisted, observable workflow events."""

def agent_log(ticket):
    tasks={}
    def get(key,role='unknown'):
        return tasks.setdefault(key,{'id':key,'role':role,'question':'','dependencies':[],'available_evidence_ids':[],
                                     'status':'pending','queries':[],'model_calls':[],'validation_errors':[],'retries':[],'notes':[],'candidates':[],'objections':[],'report':None})
    attempt=0
    for event in ticket.get('events',[]):
        payload=event['payload']; kind=event['type']; key=payload.get('task')
        if kind=='investigation_started':attempt+=1
        if not key:continue
        task=get(str(max(1,attempt))+':'+key,payload.get('role','unknown'))
        task['id']=key;task['attempt']=max(1,attempt)
        if kind=='task_started':
            for field in ('role','question','dependencies','available_evidence_ids'):
                if field in payload:task[field]=payload[field]
            task['status']='running';task['started_at']=event['created_at']
        elif kind=='task_finished':
            task['status']=payload['status'];task['finished_at']=event['created_at'];task['error']=payload.get('error')
        elif kind=='tool_started':
            task['queries'].append({'query':payload['query'],'status':'running','result':None})
        elif kind=='tool_finished':
            result=payload.get('result')
            match=next((q for q in reversed(task['queries']) if q['status']=='running' and q['query']['tool']==payload['tool']),None)
            # A retry is a separate started/finished attempt, not an overwritten success.
            if match:match.update({'status':payload['status'],'result':result,'evidence_id':payload['evidence_id']})
        elif kind=='model_started':task['model_calls'].append({'model':payload['model'],'status':'running'})
        elif kind=='model_finished':
            match=next((m for m in reversed(task['model_calls']) if m['status']=='running'),None)
            if match:match.update({'model':payload['model'],'status':payload['status'],'usage':payload.get('usage')})
        elif kind=='decision_rejected':task['validation_errors'].append({'reason':payload.get('reason'),'rejected_output':payload.get('rejected_output')})
        elif kind=='model_retry':task['retries'].append({'attempt':payload.get('attempt'),'delay_seconds':payload.get('delay_seconds')})
        elif kind=='agent_result':
            result=payload['result']
            for field in ('notes','candidates','objections','report'):
                if result.get(field) is not None:task[field]=result[field]
        elif kind=='critique_decision':task['critique']={k:payload[k] for k in ('approved','blocking_checks','notes') if k in payload}
    # Older tickets retain their original event granularity; never invent per-task data.
    return {'ticket_id':ticket['id'],'tasks':list(tasks.values()),'notice':'Observable decisions and evidence, not private chain-of-thought. Earlier tickets may lack per-task model/tool attribution.'}
