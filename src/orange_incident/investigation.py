"""Deterministic investigation policies, NOT LLM agents or benchmark answers.

Policies inspect returned records only. No fixture ID, expected-answer file, or
customer wording selects a diagnosis. This is a finite, explicit diagnostic
rule set for exercising the production workflow before model policies replace it.
"""
import asyncio
from pathlib import Path
from time import monotonic
from .contracts import Candidate, Citation, Finding, Submission
from .engine import AgentResult, Engine, Limits, Task
from .models import Hypothesis, InvestigationReport, Query


class EvidenceView:
    def __init__(self,evidence):
        self.rows={}
        self.failed=[]
        self.partial=[]
        for result in evidence:
            if result.status=='error':
                self.failed.append(result.query.tool)
                continue
            if not result.complete:
                self.partial.append(result.query.tool)
            for record in result.records:
                rid=record.get('record_id')
                if rid and record.get('source_kind') != 'derived_view':
                    self.rows[rid]=(result.evidence_id,record)

    def select(self, predicate):
        return [(eid,row) for eid,row in self.rows.values() if predicate(row)]

    @staticmethod
    def finding(code,statement,rows):
        return Finding(code=code,statement=statement,citations=[Citation(evidence_id=eid,record_id=row['record_id']) for eid,row in rows])


def analyze(evidence):
    view=EvidenceView(evidence)
    candidates=[]
    background=[]

    def add(code,description,groups,actions,action_codes,missing=(),contradictions=(),strength=8):
        findings=[view.finding(name,text,rows) for name,text,rows in groups if rows]
        support=sorted({c.evidence_id for f in findings for c in f.citations})
        candidates.append(Candidate(code=code,hypothesis=Hypothesis(description=description,
            supporting_evidence=support,contradicting_evidence=sorted({e for e,r in contradictions}),
            confidence='medium' if missing else ('high' if strength>=8 else 'low'),
            assumptions=['Observations are synthetic and apply only to the selected environment.']),
            findings=findings,actions=actions,action_codes=action_codes,missing_checks=list(missing),strength=strength))

    # Recipient normalization failures must occur before the provider, despite input and grants.
    bad=view.select(lambda r:r.get('input_recipient_present') is True and r.get('provider_called') is False
                    and r.get('status')==400 and 'recipient' in str(r.get('error','')).lower())
    if bad:
        versions={r.get('version') for e,r in bad}
        old=view.select(lambda r:r.get('status')==200 and r.get('version') not in versions and r.get('tool') in {b.get('tool') for _,b in bad})
        grants=[(e,r) for e,r in bad if any(str(s).endswith('gmail.send') for s in r.get('granted_scopes',[]))]
        repro=view.select(lambda r:r.get('same_input') is True and r.get('provider_mock') is True)
        control=repro if {r.get('status') for _,r in repro}>={200,400} else []
        add('recipient_mapping_regression','Recipient normalization is dropping provided recipient data before provider execution.',
            [('version_specific_failure','The affected version fails while another version succeeds.',bad+old),
             ('pre_provider_failure','Validation fails before a provider request.',bad),
             ('scope_present','The failing execution has a send scope.',grants),
             ('version_control','Controlled identical-input reproduction differs across versions.',control)],
            ['Roll back the affected executor version or repair recipient normalization; run regression checks before deployment.'],
            ['rollback_executor','repair_recipient_mapping'],missing=[] if control else ['controlled version reproduction'])

    missing_scope=view.select(lambda r:r.get('required_scope') is not None and isinstance(r.get('granted_scopes'),list)
                              and r['required_scope'] not in r['granted_scopes'] and r.get('status')==403)
    if missing_scope:
        controlled=view.select(lambda r:r.get('tenant')=='sandbox' and 'granted_scopes' in r)
        control=controlled if {r.get('status') for _,r in controlled}>={200,403} else []
        tenants={r.get('tenant') for _,r in missing_scope}
        cohort=view.select(lambda r:'failures' in r and 'requests' in r and r.get('tenant') is not None)
        add('missing_grant','The selected connection lacks a scope required by the failing action.',
            [('scope_mismatch','Actual grants do not satisfy the required scope.',missing_scope),
             ('tenant_isolation','Failure counts differ by tenant.',cohort),
             ('grant_control','Changing the sandbox grant changes the outcome.',control)],
            ['Confirm the intended connected account, reconnect with the required approved scope, and retest the action.'],
            ['reconnect_required_scope'],missing=[] if control else ['controlled grant comparison'])

    upstream=view.select(lambda r:r.get('provider_called') is True and r.get('provider_status',0)>=500)
    if upstream:
        cohort=view.select(lambda r:'provider' in r and 'failures' in r)
        repro=view.select(lambda r:r.get('provider_mock') is False and r.get('status',0)>=500)
        cross=repro if len({r.get('version') for _,r in repro})>=2 else []
        add('provider_failure','The upstream provider fails across executor versions.',
            [('upstream_errors','The provider itself returns server errors.',upstream),
             ('provider_isolation','Error counts differ by provider.',cohort),
             ('cross_version_failure','Both tested executor versions receive upstream errors.',cross)],
            ['Use bounded backoff, monitor the provider, and verify recovery before replaying eligible requests.'],
            ['backoff_provider','monitor_provider'],missing=[] if cross else ['cross-version provider comparison'])

    limited=view.select(lambda r:r.get('provider_status')==429 and r.get('retry_after_seconds',0)>0)
    if limited:
        overloaded=view.select(lambda r:r.get('requests_per_minute',0)>r.get('provider_limit_per_minute',float('inf')))
        cohort=view.select(lambda r:'requests_per_minute' in r and 'tenant' in r)
        add('provider_rate_limit','A tenant workload exceeds the provider quota.',
            [('rate_limit_response','Provider rate limits include Retry-After.',limited),
             ('load_exceeds_quota','Observed request load exceeds the configured quota.',overloaded),
             ('tenant_isolation','Load and backlog differ by tenant.',cohort)],
            ['Respect Retry-After and reduce per-tenant concurrency; verify backlog recovery.'],
            ['respect_retry_after','reduce_concurrency'],strength=8 if overloaded else 4)

    destination=view.select(lambda r:r.get('stage')=='outbound_delivery' and r.get('status',0)>=500)
    ingress=view.select(lambda r:r.get('stage')=='provider_ingress' and r.get('status')==200)
    if destination and ingress:
        backlog=view.select(lambda r:r.get('queue_depth',0)>0)
        add('customer_endpoint_failure','Events reach ingress but the customer destination rejects delivery.',
            [('ingress_received','The provider event reached ingress.',ingress),
             ('destination_failure','Outbound delivery receives endpoint errors.',destination),
             ('backlog','Undelivered events accumulate.',backlog)],
            ['Restore the destination endpoint, verify successful delivery, then replay with duplicate handling.'],
            ['restore_customer_endpoint','replay_after_recovery'])

    signature=view.select(lambda r:r.get('sender_key_id') and r.get('receiver_key_id') and r['sender_key_id']!=r['receiver_key_id'] and r.get('status')==401)
    if signature:
        change=view.select(lambda r:r.get('sender_key_id') and r.get('receiver_config_updated') is False)
        controlled=view.select(lambda r:'receiver_key_id' in r and 'sender_key_id' not in r and r.get('status') in (200,401))
        control=controlled if {r['status'] for _,r in controlled}>={200,401} else []
        add('webhook_secret_mismatch','Webhook sender and receiver use different signing keys.',
            [('signature_mismatch','The handler rejects a request signed with a different key.',signature),
             ('rotation_mismatch','The sender rotated without a receiver configuration update.',change),
             ('secret_control','The correct receiver key succeeds in the controlled test.',control)],
            ['Synchronize signing-secret configuration and verify a signed delivery before replay.'],
            ['synchronize_signing_secret','replay_after_recovery'],missing=[] if control else ['controlled signing-key comparison'])

    refresh=view.select(lambda r:r.get('refresh_status',0)>=500 and r.get('credential_cache')=='expired')
    if refresh:
        degraded=view.select(lambda r:r.get('service')=='credential-store' and r.get('error_rate',0)>0.2)
        dependency=view.select(lambda r:'credential-store' in r.get('depends_on',[]))
        add('credential_store_unavailable','Credential-store degradation prevents expired credentials from refreshing.',
            [('refresh_failure','Active connections have failed refreshes and expired cached credentials.',refresh),
             ('credential_store_degraded','The credential store reports errors and high latency.',degraded),
             ('auth_dependency','Authentication depends on the credential store.',dependency)],
            ['Restore the credential store; retry refresh after recovery and verify the affected tool.'],
            ['restore_credential_store','retry_refresh_after_recovery'],strength=8 if degraded and dependency else 4)

    pool=view.select(lambda r:r.get('pool_capacity',0)>0 and r.get('pool_in_use',0)>=r['pool_capacity'])
    if pool:
        waiting=view.select(lambda r:r.get('wait_for_pool_ms',0)>r.get('query_ms',float('inf'))*10)
        changes=view.select(lambda r:r.get('config_key')=='pool_capacity')
        add('connection_pool_exhaustion','Connection-pool saturation dominates catalog lookup latency.',
            [('pool_wait_dominates','Waiting for a pool slot dominates query execution.',waiting),
             ('pool_saturated','All configured pool slots are in use.',pool),
             ('pool_config_change','A pool capacity change is recorded.',changes)],
            ['Restore an appropriate pool capacity after checking database headroom; verify latency and saturation.'],
            ['restore_pool_capacity','verify_db_capacity'],strength=8 if waiting else 4)

    mismatch=view.select(lambda r:r.get('request_project') and r.get('connection_project') and r['request_project']!=r['connection_project'] and r.get('connection_exists') is True)
    if mismatch:
        cohort=view.select(lambda r:'failures' in r and 'requests' in r)
        migrations=view.select(lambda r:'project' in str(r.get('change','')).lower())
        add('project_boundary_mismatch','The request project differs from the existing connection owner project.',
            [('project_mismatch','The connection exists under another project.',mismatch),
             ('tenant_isolation','The error is isolated to the affected tenant.',cohort),
             ('project_migration','A project migration is recorded.',migrations)],
            ['Use the correctly scoped connection or project; do not bypass ownership boundaries.'],
            ['use_correct_project_connection'])

    disabled=view.select(lambda r:r.get('trigger_id') and r.get('enabled') is False)
    healthy=view.select(lambda r:r.get('connection_status')=='ACTIVE' and r.get('send_status')==200)
    different=[(e,r) for e,r in disabled if any(h.get('connection_id')!=r.get('connection_id') for _,h in healthy)]
    if different:
        reconnect=view.select(lambda r:r.get('old_connection') and r.get('new_connection') and r['old_connection']!=r['new_connection'])
        add('trigger_old_connection','The trigger remains on an old disabled connection while a different connection can send.',
            [('new_connection_healthy','The current connection can execute a send.',healthy),
             ('trigger_old_disabled_connection','The trigger points to the old disabled connection.',different),
             ('reconnect_identity_change','Reconnection created a different connection identity.',reconnect)],
            ['Create or enable a trigger on the intended current connection, then verify a new event.'],
            ['create_trigger_for_new_connection'])

    accepted=view.select(lambda r:r.get('client_status')=='timeout' and r.get('provider_status')==200 and r.get('provider_message_id'))
    duplicates=[]
    for e,r in accepted:
        others=view.select(lambda x:x.get('operation_id')==r.get('operation_id') and x.get('request_id')!=r.get('request_id')
                           and x.get('provider_status')==200 and x.get('provider_message_id') and x['provider_message_id']!=r['provider_message_id'])
        if others:
            duplicates.extend([(e,r)]+others)
    if duplicates:
        latency=view.select(lambda r:r.get('client_timeout_ms',float('inf'))<r.get('attachment_send_p95_ms',0))
        add('unsafe_send_retry','A retry produced a second accepted message after the original request timed out.',
            [('accepted_before_timeout','Provider acceptance coexists with a client timeout.',accepted),
             ('duplicate_retry','Distinct requests for the same operation produced distinct messages.',duplicates),
             ('timeout_below_latency','Client timeout is below observed attachment latency.',latency)],
            ['Verify send status before retrying, disable blind retries, and account for attachment latency.'],
            ['verify_send_before_retry','disable_blind_send_retries'])

    def alternative(code,description,counter,assumption):
        if any(c.code==code for c in candidates):
            return
        add(code,description,[],[],[],contradictions=counter,strength=0)
        candidates[-1].hypothesis.assumptions=[assumption]
    if bad:
        alternative('missing_grant','Missing permissions could explain a failed send, but recorded send grants contradict that explanation.',
                    grants,'No current missing-scope observation supports this alternative.')
        alternative('provider_failure','An upstream failure is an alternative, but validation stopped before provider execution.',
                    bad,'No provider request or provider failure was observed for these validation errors.')
    if upstream:
        alternative('recipient_mapping_regression','An executor mapping regression is possible, but upstream responses show execution reached the provider.',
                    upstream,'A controlled mapping failure has not been observed.')
    if destination:
        alternative('webhook_secret_mismatch','A signing-key mismatch is possible, but the observed destination returned server errors.',
                    destination,'There is no observed signature rejection supporting this alternative.')
    if signature:
        alternative('customer_endpoint_failure','An unavailable endpoint is an alternative, but the handler responded with a specific signature rejection.',
                    signature,'There is no observed network or server failure supporting this alternative.')

    from .extended_diagnostics import extend
    extend(view,add,background)

    # Keep an explicitly weak competing explanation; temporal correlation is not proof.
    changes=view.select(lambda r:'change' in r)
    if changes:
        add('unconfirmed_change','A nearby deployment or configuration change may be related, but timing alone does not establish causality.',
            [],['Collect a controlled comparison before changing deployment state.'],[],strength=1)
        candidates[-1].hypothesis.supporting_evidence=sorted({e for e,r in changes})
        candidates[-1].hypothesis.assumptions=['This alternative is based on temporal correlation only.']
        if candidates[:-1]:
            candidates[-1].hypothesis.contradicting_evidence=candidates[0].hypothesis.supporting_evidence

    gateway=view.select(lambda r:r.get('status')==502)
    history=view.select(lambda r:'symptom' in r and 'cause' in r)
    if gateway:
        background.append(view.finding('observed_gateway_failure','Gateway failures were observed, without enough causal telemetry.',gateway))
    if gateway and len({r.get('cause') for _,r in history})>1:
        background.append(view.finding('competing_history','Similar past symptoms have different documented causes.',history))
    candidates.sort(key=lambda c:c.strength,reverse=True)
    findings={f.code:f for c in candidates for f in c.findings}
    findings.update({f.code:f for f in background})
    return candidates,list(findings.values())


async def simulated_policy(task,state,tools):
    if task.role=='orchestrator':
        return AgentResult(followups=[
            Task(id='observe',role='observability',question='Establish symptoms, timing, and affected cohorts.'),
            Task(id='dependencies',role='dependency',question='Collect deployments and service relationships.'),
            Task(id='reason-0',role='reasoning',question='Compare explanations against current evidence.',dependencies=['observe','dependencies']),
            Task(id='critic-0',role='critic',question='Challenge missing evidence and causal claims.',dependencies=['reason-0'])])
    if task.role in ('observability','dependency'):
        names=['logs','metrics','connections','refresh_history'] if task.role=='observability' else (['reproduce'] if task.id.startswith('verify-') else ['deployments','dependencies'])
        await asyncio.gather(*(tools.query(Query(tool=name)) for name in names))
        return AgentResult(notes=['Collected observations through bounded tool calls.'])
    if task.role=='reasoning':
        extra=[]
        if task.id=='reason-0':
            extra=await asyncio.gather(*(tools.query(Query(tool=name)) for name in ['history','knowledge']))
        candidates,findings=analyze(state.evidence+extra)
        return AgentResult(candidates=candidates,findings=findings,
                           notes=['Applied explicit deterministic diagnostic rules to observed records; no LLM inference.'])
    if task.role=='critic':
        primary=state.candidates[0] if state.candidates else None
        if primary and primary.missing_checks and state.followup_rounds<1:
            number=state.followup_rounds+1
            verify=f'verify-{number}'
            reason=f'reason-{number}'
            return AgentResult(objections=[f'Missing verification: {check}' for check in primary.missing_checks],followups=[
                Task(id=verify,role='dependency',question='Collect controlled reproduction evidence.'),
                Task(id=reason,role='reasoning',question='Reassess hypotheses using the new control evidence.',dependencies=[verify]),
                Task(id=f'critic-{number}',role='critic',question='Check whether the missing evidence was obtained.',dependencies=[reason])])
        objections=[]
        if primary and primary.missing_checks:
            objections=[f'Unresolved: {check}' for check in primary.missing_checks]
        if not primary or primary.strength<6:
            objections.append('No explanation has sufficient current evidence; report an inconclusive outcome.')
        return AgentResult(objections=objections,followups=[Task(id='report',role='reporting',question='Produce a bounded, evidence-backed investigation report.')])
    if task.role=='reporting':
        primary=state.candidates[0] if state.candidates else None
        telemetry_conflict=any(f.code=='telemetry_conflict' for f in state.findings)
        probable=bool(primary and primary.strength>=6 and not primary.missing_checks and not telemetry_conflict)
        limitations=['Deterministic simulation: rules and orchestration are being tested, not model reasoning. No corrective action was executed.']
        unavailable={e.query.tool for e in state.evidence if e.status=='error'}-{e.query.tool for e in state.evidence if e.status!='error'}
        limitations += [f'{name} remained unavailable after bounded retries.' for name in sorted(unavailable)]
        limitations += [f'{e.query.tool} returned incomplete results; absence cannot establish a fact.' for e in state.evidence if e.status=='partial']
        if primary:
            limitations += [f'Unresolved verification: {check}.' for check in primary.missing_checks]
        actions=primary.actions if probable else ['Collect missing telemetry, request identifiers and timestamps, and obtain a controlled reproduction before confirming a cause.']
        if telemetry_conflict:
            actions=['Align source clocks and observation windows, then collect matching request telemetry before confirming a cause.']
        return AgentResult(report=InvestigationReport(incident_id=state.incident.id,
            outcome='probable_cause' if probable else 'inconclusive',hypotheses=[c.hypothesis for c in state.candidates],
            recommended_actions=actions,limitations=list(dict.fromkeys(limitations))))
    raise ValueError('Unsupported investigation role')


async def run_simulation(simulation, output:Path, *, event_sink=None, limits=None):
    started=monotonic()
    roles=['orchestrator','observability','dependency','reasoning','critic','reporting']
    engine=Engine(simulation.incident,simulation.query,{role:simulated_policy for role in roles},
                  limits=limits or Limits(),mode='deterministic_simulation',event_sink=event_sink)
    output.mkdir(parents=True,exist_ok=True)
    state=await engine.run([Task(id='plan',role='orchestrator',question='Scope and coordinate the synthetic investigation.')],output/'traces/workflow.json')
    report=state.report or InvestigationReport(incident_id=simulation.incident.id,outcome='inconclusive',hypotheses=[],recommended_actions=['Review execution failures and collect missing evidence.'],limitations=state.limitations)
    candidates=state.candidates if state.report else []
    actions=candidates[0].action_codes if report.outcome=='probable_cause' and candidates else (['align_telemetry_windows','collect_missing_telemetry'] if any(f.code=='telemetry_conflict' for f in state.findings) else ['collect_missing_telemetry','request_reproduction'])
    result=Submission(incident_id=simulation.incident.id,approach='simulation',run_status='completed' if state.report else 'failed',
        report=report,ranked_cause_codes=[c.code for c in candidates],findings=state.findings,action_codes=actions,
        trace=state.evidence,latency_seconds=monotonic()-started,input_tokens=None,output_tokens=None)
    (output/f'{simulation.incident.id}.json').write_text(result.model_dump_json(indent=2)+'\n')
    return result,state
