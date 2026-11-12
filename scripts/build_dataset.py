"""Author synthetic benchmark fixtures; never imported by runtime agents.

All telemetry is invented. This authoring script also writes evaluator-only labels.
"""
import json
from pathlib import Path

if __name__ != '__main__':
    raise RuntimeError('Dataset authoring script must not be imported by runtime agents')

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ['logs', 'metrics', 'deployments', 'dependencies', 'history', 'knowledge', 'reproduce']
truth = {}


def write_case(case_id, title, description, service, rows, cause, findings, actions, *, failures=None, outcome='probable_cause', tags=None):
    sources = {key: [] for key in SOURCES}
    for tool, records in rows.items():
        for index, record in enumerate(records):
            sources[tool].append({'record_id': f'{case_id}:{tool}:{index}', 'service': service,
                                  **({'timestamp': '2026-11-12T10:05:00Z'} if tool in ['logs', 'metrics', 'deployments', 'reproduce'] else {}), **record})
    sources['dependencies'] = sources['dependencies'] or [{'record_id': f'{case_id}:dependencies:0', 'service': service, 'depends_on': ['auth-service', 'provider-api']}]
    sources['history'] = sources['history'] or [{'record_id': f'{case_id}:history:0', 'service': service, 'symptom': 'Requests fail after a release', 'cause': 'Earlier unrelated argument mapping defect', 'verified': True}]
    fixture = {'incident': {'id': case_id, 'title': title, 'description': description, 'start': '2026-11-12T09:50:00Z', 'end': '2026-11-12T10:15:00Z', 'services': [service]}, 'sources': sources, 'failures': failures or {}}
    (ROOT / f'data/incidents/{case_id}.json').write_text(json.dumps(fixture, indent=2)+'\n')
    truth[case_id] = {'expected_outcome': outcome, 'cause_code': cause, 'findings': {code: [f'{case_id}:{tool}:{i}' for tool,i in refs] for code, refs in findings.items()}, 'acceptable_action_codes': actions, 'tags': tags or []}


write_case('auth-002', 'Gmail failures isolated to one tenant', 'Atlas reports a send outage after a release; other tenants appear healthy.', 'tool-executor', {
 'logs': [{'tenant':'atlas','status':403,'provider_error':'insufficientPermissions','granted_scopes':['gmail.readonly'],'required_scope':'gmail.send'}, {'tenant':'birch','status':200,'granted_scopes':['gmail.send']}],
 'metrics':[{'tenant':'atlas','requests':100,'failures':100},{'tenant':'birch','requests':100,'failures':0}],
 'deployments':[{'change':'Unrelated dashboard CSS deployment','service':'dashboard'}],
 'reproduce':[{'tenant':'sandbox','status':403,'granted_scopes':['gmail.readonly']},{'tenant':'sandbox','status':200,'granted_scopes':['gmail.send']}]
}, 'missing_grant', {'scope_mismatch':[('logs',0)],'tenant_isolation':[('metrics',0),('metrics',1)],'grant_control':[('reproduce',0),('reproduce',1)]}, ['reconnect_required_scope'], tags=['auth','tenant_impact','misleading_change'])

write_case('provider-003', 'Slack execution error spike', 'Slack requests fail across tenants. An executor rollout is suspected.', 'tool-executor', {
 'logs':[{'tenant':'atlas','version':'old','status':503,'provider_called':True,'provider_status':503},{'tenant':'birch','version':'new','status':503,'provider_called':True,'provider_status':503}],
 'metrics':[{'provider':'slack','requests':1000,'failures':850},{'provider':'gmail','requests':1000,'failures':0}],
 'deployments':[{'version':'new','change':'Executor logging update'}],
 'reproduce':[{'version':'old','provider_mock':False,'status':503},{'version':'new','provider_mock':False,'status':503}]
}, 'provider_failure', {'upstream_errors':[('logs',0),('logs',1)],'provider_isolation':[('metrics',0),('metrics',1)],'cross_version_failure':[('reproduce',0),('reproduce',1)]}, ['backoff_provider','monitor_provider'], failures={'logs':{'timeout_attempts':1}}, tags=['upstream','tool_timeout','conflicting_deployment'])

write_case('quota-004', 'Notion rate-limit spike', 'Notion requests are failing and latency is rising during a bulk import.', 'tool-executor', {
 'logs':[{'tenant':'atlas','status':429,'provider_status':429,'retry_after_seconds':60},{'tenant':'birch','status':200}],
 'metrics':[{'tenant':'atlas','requests_per_minute':900,'provider_limit_per_minute':180,'queue_depth':800,'p95_ms':12000},{'tenant':'birch','requests_per_minute':20,'queue_depth':0,'p95_ms':400}],
 'deployments':[{'service':'tool-router','change':'Bulk import concurrency changed from 2 to 40','tenant':'atlas'}]
}, 'provider_rate_limit', {'rate_limit_response':[('logs',0)],'load_exceeds_quota':[('metrics',0)],'tenant_isolation':[('metrics',0),('metrics',1)]}, ['respect_retry_after','reduce_concurrency'], tags=['rate_limit','latency','tenant_impact'])

write_case('webhook-005', 'Trigger delivery backlog', 'Events appear in trigger logs but Atlas receives no callbacks.', 'webhook-delivery', {
 'logs':[{'event_id':'evt-1','stage':'provider_ingress','status':200},{'event_id':'evt-1','stage':'outbound_delivery','destination':'atlas.example/webhook','status':503,'attempt':4}],
 'metrics':[{'tenant':'atlas','queue_depth':450,'oldest_event_seconds':600},{'tenant':'birch','queue_depth':0}],
 'deployments':[{'tenant':'atlas','change':'Customer endpoint maintenance began','service':'customer-endpoint'}]
}, 'customer_endpoint_failure', {'ingress_received':[('logs',0)],'destination_failure':[('logs',1)],'backlog':[('metrics',0)]}, ['restore_customer_endpoint','replay_after_recovery'], tags=['webhook','backlog','dependency'])

write_case('signature-006', 'Webhook rejection spike after secret rotation', 'Customer webhook now rejects deliveries, although the trigger is active.', 'webhook-delivery', {
 'logs':[{'event_id':'evt-2','stage':'provider_ingress','status':200},{'event_id':'evt-2','stage':'customer_handler','status':401,'error':'signature mismatch','sender_key_id':'key-2','receiver_key_id':'key-1'}],
 'metrics':[{'tenant':'atlas','requests':200,'failures':200}],
 'deployments':[{'change':'Webhook signing key rotated','sender_key_id':'key-2','receiver_config_updated':False}],
 'reproduce':[{'receiver_key_id':'key-1','status':401},{'receiver_key_id':'key-2','status':200}]
}, 'webhook_secret_mismatch', {'signature_mismatch':[('logs',1)],'rotation_mismatch':[('deployments',0)],'secret_control':[('reproduce',0),('reproduce',1)]}, ['synchronize_signing_secret','replay_after_recovery'], tags=['config','conflicting_active_status'])

write_case('refresh-007', 'Authentication failures across multiple toolkits', 'Previously active connections fail intermittently. Dashboard connection status is still active.', 'auth-service', {
 'logs':[{'connection_status':'ACTIVE','refresh_status':503,'credential_cache':'expired','provider_called':False},{'connection_status':'ACTIVE','refresh_status':503,'credential_cache':'expired','provider_called':False,'tenant':'birch'}],
 'metrics':[{'service':'credential-store','p95_ms':15000,'error_rate':0.8},{'service':'auth-service','refresh_failures':800}],
 'dependencies':[{'depends_on':['credential-store']}],
 'deployments':[{'service':'dashboard','change':'Connection badge display update'}]
}, 'credential_store_unavailable', {'refresh_failure':[('logs',0)],'credential_store_degraded':[('metrics',0)],'auth_dependency':[('dependencies',0)]}, ['restore_credential_store','retry_refresh_after_recovery'], failures={'metrics':{'timeout_attempts':1}}, tags=['dependency','auth','tool_timeout'])

write_case('pool-008', 'Tool discovery latency spike', 'Tool listing is slow across tenants, with few explicit errors.', 'tool-router', {
 'logs':[{'operation':'catalog_lookup','wait_for_pool_ms':8000,'query_ms':15},{'operation':'catalog_lookup','wait_for_pool_ms':7900,'query_ms':12}],
 'metrics':[{'service':'catalog-db','pool_in_use':20,'pool_capacity':20,'cpu_percent':20,'p95_ms':8200}],
 'deployments':[{'change':'Catalog DB connection pool reduced from 100 to 20','config_key':'pool_capacity'}],
 'dependencies':[{'depends_on':['catalog-db']}],
 'history':[{'symptom':'Slow discovery','cause':'Earlier expensive SQL query','verified':True}]
}, 'connection_pool_exhaustion', {'pool_wait_dominates':[('logs',0),('logs',1)],'pool_saturated':[('metrics',0)],'pool_config_change':[('deployments',0)]}, ['restore_pool_capacity','verify_db_capacity'], tags=['latency','config','misleading_history'])

write_case('tenant-009', 'Connected account not found after migration', 'Atlas reports missing connections after moving its consumer app to a new project.', 'auth-service', {
 'logs':[{'tenant':'atlas','request_project':'project-b','connection_project':'project-a','status':404,'connection_exists':True},{'tenant':'birch','request_project':'project-a','connection_project':'project-a','status':200}],
 'metrics':[{'tenant':'atlas','requests':80,'failures':80},{'tenant':'birch','requests':80,'failures':0}],
 'deployments':[{'tenant':'atlas','change':'Application project changed from project-a to project-b'}]
}, 'project_boundary_mismatch', {'project_mismatch':[('logs',0)],'tenant_isolation':[('metrics',0),('metrics',1)],'project_migration':[('deployments',0)]}, ['use_correct_project_connection'], tags=['tenant_impact','identity'])

write_case('cursor-010', 'No events after Gmail trigger reconnect', 'Sending tools work, but new messages are not delivered after an account reconnect.', 'trigger-worker', {
 'logs':[{'connection_id':'ca-new','connection_status':'ACTIVE','send_status':200},{'trigger_id':'ti-old','connection_id':'ca-old','enabled':False,'last_poll':'2026-11-12T09:40:00Z'}],
 'metrics':[{'tenant':'atlas','new_messages':12,'trigger_events':0}],
 'deployments':[{'change':'Account reconnected under a different application user ID','old_connection':'ca-old','new_connection':'ca-new'}]
}, 'trigger_old_connection', {'new_connection_healthy':[('logs',0)],'trigger_old_disabled_connection':[('logs',1)],'reconnect_identity_change':[('deployments',0)]}, ['create_trigger_for_new_connection'], tags=['trigger','conflicting_send_success'])

write_case('duplicate-011', 'Duplicate Gmail sends after attachment timeouts', 'Customers receive duplicate attachment emails despite client timeout errors.', 'tool-executor', {
 'logs':[{'operation_id':'op-1','request_id':'req-1','client_status':'timeout','provider_message_id':'msg-a','provider_status':200},{'operation_id':'op-1','request_id':'req-2','client_status':200,'provider_message_id':'msg-b','provider_status':200,'retry_of':'req-1'}],
 'metrics':[{'client_timeout_ms':1000,'attachment_send_p95_ms':3500,'duplicate_operations':30}],
 'deployments':[{'service':'customer-client','change':'Unconditional retries enabled on execution timeout'}]
}, 'unsafe_send_retry', {'accepted_before_timeout':[('logs',0)],'duplicate_retry':[('logs',0),('logs',1)],'timeout_below_latency':[('metrics',0)]}, ['verify_send_before_retry','disable_blind_send_retries'], tags=['non_idempotent','latency','conflicting_timeout'])

write_case('unknown-012', 'Intermittent execution failures with missing telemetry', 'A customer reports sporadic 502 responses; traces and metrics are unavailable.', 'tool-executor', {
 'logs':[{'tenant':'atlas','status':502,'request_id':'lost-1','upstream_trace_id':None}],
 'metrics':[],
 'deployments':[{'change':'Executor release','version':'new'}],
 'history':[{'symptom':'502 error','cause':'Provider outage','verified':True},{'symptom':'502 error','cause':'Executor regression','verified':True}]
}, None, {'observed_gateway_failure':[('logs',0)],'competing_history':[('history',0),('history',1)]}, ['collect_missing_telemetry','request_reproduction'], outcome='inconclusive', failures={'metrics':{'timeout_attempts':100},'logs':{'incomplete':True},'reproduce':{'incomplete':True}}, tags=['inconclusive','permanent_tool_failure','incomplete_evidence'])

from scenario_expansion import add_cases
add_cases(write_case)
from scenario_expansion_v3 import add_cases as add_v3
add_v3(write_case)

# Preserve the first authored case and give every returned record a stable ID.
p = ROOT/'data/incidents/gmail-001.json'
gmail=json.loads(p.read_text())
for tool, records in gmail['sources'].items():
    for i, record in enumerate(records):
        record['record_id']=f'gmail-001:{tool}:{i}'
p.write_text(json.dumps(gmail,indent=2)+'\n')
truth['gmail-001']={'expected_outcome':'probable_cause','cause_code':'recipient_mapping_regression','findings':{'version_specific_failure':['gmail-001:logs:1','gmail-001:logs:6'],'pre_provider_failure':['gmail-001:logs:1'],'scope_present':['gmail-001:logs:1'],'version_control':['gmail-001:reproduce:0','gmail-001:reproduce:1']},'acceptable_action_codes':['rollback_executor','repair_recipient_mapping'],'tags':['regression','misleading_history','tool_timeout']}
(ROOT/'evaluation/ground_truth.json').write_text(json.dumps(dict(sorted(truth.items())),indent=2)+'\n')
print(f'Wrote {len(truth)} benchmark incidents and isolated evaluator labels.')

# Vocabulary is public; per-incident mapping and required evidence remain private to evaluation.
vocabulary = {
    'cause_codes': sorted({t['cause_code'] for t in truth.values() if t['cause_code']} | {'unconfirmed_change'}),
    'finding_codes': sorted({code for t in truth.values() for code in t['findings']}),
    'action_codes': sorted({code for t in truth.values() for code in t['acceptable_action_codes']}),
    'instructions': 'Use codes only when justified by observed evidence; use an inconclusive outcome when evidence is insufficient (tentative ranked hypotheses may remain). These are benchmark labels, not per-incident answers. Explain each selected code in the report or finding statement.'
}
from scenario_expansion_v3 import vocabulary_definitions
vocabulary['definitions']=vocabulary_definitions()
(ROOT/'data/rubric.json').write_text(json.dumps(vocabulary, indent=2)+'\n')

# Derived connection views preserve their log provenance and are not new ground truth.
import sys
sys.path.insert(0, str(ROOT/'src'))
from orange_incident.connection_views import materialize
for path in (ROOT/'data/incidents').glob('*.json'):
    fixture=json.loads(path.read_text())
    fixture['sources'].update(materialize(fixture['sources']))
    path.write_text(json.dumps(fixture,indent=2)+'\n')
