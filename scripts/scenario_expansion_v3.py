"""Public-doc-inspired prospective cases. Author/evaluator code, never runtime policy."""
BASE='https://docs.composio.dev/kb/guide/'
# id, public source, complaint, observed fault, corrected control, cause, next action.
CASES=[
('notion-access-033','toolkits-notion','Notion pages disappear for one workspace',
 'Cedar sees page-not-found errors for a newly added Notion page, while existing pages still load. A connector release happened nearby. Please investigate before asking everyone to reconnect.',
 {'toolkit':'notion','status':404,'resource_exists':True,'integration_has_page_access':False,'token_valid':True},
 {'status':200,'integration_has_page_access':True},'notion_resource_not_shared','Share only the intended page with the existing Notion integration and verify access; do not widen unrelated permissions.',
 'Notion resource access is granted to its integration, rather than through conventional OAuth scopes.'),
('notion-event-034','toolkits-notion','Notion edits no longer reach our workflow',
 'Our Notion workflow receives newly created pages but misses edits to existing pages. Work is backing up for Cedar after a trigger configuration change.',
 {'toolkit':'notion','status':200,'observed_event':'page_content_updated','configured_trigger_event':'page_created','matched':False,'connection_active':True},
 {'status':200,'configured_trigger_event':'page_content_updated','matched':True},'trigger_event_kind_mismatch','Select the current trigger for the intended update event and verify a new edit; preserve the existing connection.',
 'Different Notion event families have separate trigger catalog entries.'),
('github-org-035','toolkits-github','GitHub personal repositories work but organization jobs fail',
 'Cedar can read personal repositories but organization requests return 403. Reconnecting has not helped, and organization jobs are accumulating.',
 {'toolkit':'github','status':403,'personal_repository_access':True,'organization_oauth_policy':'restricted','organization_app_approval':'pending','token_valid':True},
 {'status':200,'organization_app_approval':'approved'},'github_organization_approval','Request approval from the GitHub organization owner for the intended OAuth app, then retest the organization resource.',
 'GitHub organizations may require owner approval of an OAuth app.'),
('github-token-036','toolkits-github','Our GitHub relay treats healthy connections as unauthenticated',
 'A new relay cannot find the GitHub access token in connected-account responses. The connection looks active, but relay jobs fail while Composio tool executions work.',
 {'toolkit':'github','status':200,'connected_account_active':True,'provider_token_field':'REDACTED','relay_requires_raw_token':True,'tool_execution_status':200},
 {'status':200,'relay_requires_raw_token':False,'execution_path':'authenticated_proxy','relay_completed':True},'redacted_token_relay_design','Route the provider request through authenticated tool/proxy execution rather than extracting a provider token.',
 'Connected-account responses redact GitHub provider tokens; authenticated execution remains available.'),
('github-setup-037','toolkits-github','GitHub V2 trigger setup stalls before creating a trigger',
 'A migrated GitHub setup job fails on a webhook-endpoint creation call. No trigger instance is created, although our GitHub account is connected.',
 {'toolkit':'github','status':404,'trigger_generation':'v2','attempted_setup_path':'/webhook_endpoints','trigger_created':False,'auth_valid':True},
 {'status':200,'attempted_setup_path':'/trigger_instances/{slug}/upsert','trigger_created':True,'ingress_provisioned':True},'obsolete_trigger_setup_path','Create/upsert the V2 trigger directly through the supported trigger-instance path and verify a new event.',
 'GitHub V2 trigger creation provisions its ingress without a separate endpoint-creation step.'),
('sheets-plane-038','toolkits-googlesheets','Sheets works in Platform but appears disconnected in MCP',
 'Cedar connected Google Sheets in Platform yesterday. The Connect MCP client still asks for authentication and cannot execute spreadsheet jobs.',
 {'toolkit':'googlesheets','status':401,'request_surface':'connect_mcp','connection_surface':'platform','connect_mcp_connection_count':0,'platform_connection_active':True},
 {'status':200,'connection_surface':'connect_mcp','connect_mcp_connection_count':1},'connection_surface_isolation','Connect Sheets through the MCP authentication flow used by this client; do not assume Platform connections are shared.',
 'Platform and consumer Connect MCP maintain separate connection contexts.'),
('sheets-discovery-039','toolkits-googlesheets','A Sheets action is missing after catalog discovery',
 'Our agent sees only twenty Sheets tools and says a required action is unavailable. The same action appears in the current catalog. A provider outage is suspected.',
 {'toolkit':'googlesheets','status':200,'list_limit':20,'returned_tools':20,'has_more':True,'requested_tool_on_later_page':True,'version_contains_tool':True},
 {'status':200,'pagination_completed':True,'requested_tool_found':True},'tool_discovery_truncation','Paginate or raise the discovery limit, then execute the exact returned action slug on the intended version.',
 'Tool discovery can return only its default first page; follow pagination or request a larger limit.'),
('sheets-id-040','toolkits-googlesheets','Sheets lookup fails although the document exists',
 'Cedar asks the MCP agent to read a spreadsheet by its display name. It repeatedly fails to find the sheet, while another job with a copied document ID works.',
 {'toolkit':'googlesheets','status':400,'spreadsheet_identifier':'Quarterly Revenue','identifier_kind':'display_name','operation_requires':'spreadsheet_id','name_lookup_supported':False},
 {'status':200,'identifier_kind':'spreadsheet_id','spreadsheet_identifier':'sheet-demo-040'},'spreadsheet_identifier_kind','Pass the intended spreadsheet ID, then verify the target and requested range before writing.',
 'The Sheets MCP operation expects a spreadsheet identifier rather than a name-search request.'),
('airtable-expiry-041','toolkits-airtable','Airtable authentication links fail for late arrivals',
 'Users who return to an old Airtable connection link see expiry errors. Fresh connections work. Onboarding completion has dropped for Cedar.',
 {'toolkit':'airtable','status':410,'connection_state':'EXPIRED','initiation_age_seconds':950,'completion_window_seconds':600,'token_exchange_attempted':False},
 {'status':200,'initiation_age_seconds':120,'connection_state':'ACTIVE'},'authentication_initiation_expired','Start a fresh authentication initiation and complete it within its valid window; avoid retrying the expired link.',
 'An unfinished connection initiation expires after its allowed ten-minute window.'),
('airtable-batch-042','toolkits-airtable','Large Airtable update jobs fail but small updates pass',
 'Cedar batch updates fail validation after increasing the job size. Ten-record jobs still pass. The queue is growing and a recent executor release is blamed.',
 {'toolkit':'airtable','status':422,'action':'AIRTABLE_UPDATE_MULTIPLE_RECORDS','records_in_request':25,'max_records_per_call':10,'provider_rate_limited':False},
 {'status':200,'records_in_request':10},'provider_batch_record_limit','Split updates into batches of at most ten records, respect provider rate limits, and verify partial completion before retrying.',
 'The Airtable multi-record update action has a ten-record batch bound.'),
('slack-user-043','toolkits-slack','Slack user actions fail despite configured bot permissions',
 'A Cedar user-token Slack workflow returns missing_scope. The auth config lists the expected permission, and bot posting still works.',
 {'toolkit':'slack','status':403,'required_token_kind':'user','auth_config_bot_scopes':['search:read'],'auth_config_user_scopes':[],'error':'missing_scope'},
 {'status':200,'auth_config_user_scopes':['search:read'],'granted_token_kind':'user'},'slack_user_scope_configuration','Configure the needed user_scopes and reconnect the intended user; bot scopes do not authorize user-token actions.',
 'Slack separates user-token permissions from bot permissions in its auth configuration.'),
('slack-plan-044','toolkits-slack','Slack AI search fails while ordinary search remains healthy',
 'Cedar cannot use assistant context search, although other Slack tools work. Adding scopes and reconnecting did not restore the workflow.',
 {'toolkit':'slack','status':403,'action':'assistant.search.context','workspace_plan':'standard','agents_ai_apps_enabled':True,'is_ai_search_enabled':False,'required_plan':'business_plus'},
 {'status':200,'workspace_plan':'business_plus','is_ai_search_enabled':True},'provider_feature_entitlement','Check workspace eligibility and feature enablement; use a supported search alternative or obtain the required plan before retesting.',
 'Slack assistant context search depends on both feature enablement and workspace plan eligibility.'),
('slack-ingress-045','toolkits-slack','Slack triggers stop after an app settings change',
 'Previously healthy Slack triggers stopped delivering channel messages. Our webhook endpoint still passes health checks and queued workflows are idle.',
 {'toolkit':'slack','status':200,'provider_event_created':True,'app_event_webhook_url':'https://other.example.invalid/events','expected_ingress_url':'https://ingress.example.invalid/slack','composio_ingress_received':False},
 {'status':200,'app_event_webhook_url':'https://ingress.example.invalid/slack','composio_ingress_received':True},'provider_event_ingress_misrouting','Restore the intended Slack app event-subscription ingress and verify a newly generated message before considering replay.',
 'Slack app event-subscription destination changes can interrupt trigger ingress.'),
('slack-redirect-046','toolkits-slack','Custom Slack OAuth rejects the redirect URL',
 'Cedar replaced its OAuth app redirect setting with the short link shown during connection. New connects fail, but existing connections remain healthy.',
 {'toolkit':'slack','status':400,'oauth_error':'redirect_uri_mismatch','registered_redirect_uri':'https://backend.composio.dev/api/v3/s/demo','authorization_redirect_uri':'https://backend.composio.dev/api/v1/auth-apps/add','short_connect_url_used_as_redirect':True},
 {'status':200,'registered_redirect_uri':'https://backend.composio.dev/api/v1/auth-apps/add','short_connect_url_used_as_redirect':False},'oauth_redirect_uri_mismatch','Match the OAuth app redirect setting to the auth config callback URI; keep the short per-connection link separate.',
 'A shortened connection link is distinct from the static OAuth callback URI.'),
('gmail-shape-047','toolkits-gmail','Gmail attachment sends fail before reaching Google',
 'Cedar plain-text sends work, but attachment jobs immediately return validation errors. The client passes a signed download URL as the attachment argument.',
 {'toolkit':'gmail','status':400,'attachment_argument_type':'string_signed_url','expected_attachment_type':'uploaded_file_object','provider_called':False,'validation_error':'attachment_object_required'},
 {'status':200,'attachment_argument_type':'uploaded_file_object','provider_called':True},'attachment_reference_shape','Upload the file and pass the supported file object, then validate the serialized attachment argument before sending.',
 'Gmail attachment execution accepts uploaded file objects rather than signed URL strings.'),
('gmail-file-048','toolkits-gmail','Delayed Gmail attachment jobs cannot read uploaded files',
 'Attachment jobs work immediately after upload but fail after sitting in Cedar’s queue. A new upload succeeds with the same Gmail account and message data.',
 {'toolkit':'gmail','status':410,'file_reference_expired':True,'file_lookup_status':410,'provider_called':False,'credential_valid':True},
 {'status':200,'file_reference_expired':False,'file_lookup_status':200,'provider_called':True},'temporary_file_reference_expired','Upload a fresh file shortly before execution and use its current reference; verify send status before any retry.',
 'Temporary uploaded file references are short-lived; avoid using stale references in delayed jobs.'),
('session-policy-049','platform-session-tool-policies','An active connection cannot run a write action',
 'Cedar read tools work, but a write action is absent from discovery and blocked at execution. The OAuth connection already has the provider write scope.',
 {'status':403,'provider_scope_present':True,'session_allowed_tags':['readOnlyHint'],'requested_tool_tags':['writeHint'],'policy_allowed':False,'provider_called':False},
 {'status':200,'session_exact_tool_exception_authorized':True,'policy_allowed':True,'provider_called':True},'session_tool_policy_block','Keep least privilege: use an explicitly authorized narrow tool exception only if the workflow should write, then verify the effective policy.',
 'Session tool restrictions apply independently of provider OAuth grants.'),
('log-gap-050','dashboard-log-storage','Audit errors are visible but request payloads are missing',
 'Cedar reports execution errors but cannot inspect request arguments or response bodies in fresh audit rows. Please identify the incident cause from the available data.',
 {'status':500,'request_id':'req-redacted-demo','audit_row_present':True,'payload_storage_enabled':False,'request_payload':None,'response_payload':None,'underlying_error_code':None},
 None,None,'Collect a fresh permitted reproduction, request IDs and diagnostic metadata; missing stored payloads cannot establish the execution failure cause.',
 'Disabling payload storage preserves audit metadata while omitting new request and response content.'),
('delivery-dedupe-051','platform-triggers','One trigger event causes duplicate downstream records',
 'Cedar sees duplicate workflow records after transient webhook delivery failures. The same event identifier appears on both receipts, and they suspect duplicate ingestion.',
 {'status':200,'provider_ingress_events':1,'delivery_attempts':2,'stable_event_id':'event-demo-051','receipt_event_ids':['event-demo-051','event-demo-051'],'receiver_deduplication':False,'downstream_records':2},
 {'status':200,'receiver_deduplication':True,'downstream_records':1,'delivery_attempts':2},'webhook_receiver_not_idempotent','Deduplicate receiver processing using a stable event/log identifier and verify retry behavior without assuming duplicate provider ingress.',
 'Webhook delivery is at-least-once, so receivers need stable-identifier deduplication.'),
('slack-schedule-052','toolkits-slack','Scheduled Slack messages arrive without their files',
 'Cedar scheduled message text is delivered, but the file never appears. The scheduling request puts an uploaded file descriptor in the attachments field.',
 {'toolkit':'slack','status':200,'message_scheduled':True,'attachment_semantics':'legacy_message_formatting','file_upload_performed':False,'file_link_in_body':False,'delivered_file_count':0},
 {'status':200,'file_upload_performed':True,'file_link_in_body':True,'delivered_file_count':1},'scheduled_attachment_semantics','Upload the file separately and include its supported link in the scheduled message body, then verify the scheduled result.',
 'Scheduled-message formatting attachments are not a file-upload operation.'),
]

def add_cases(write):
    for index,(case_id,source,title,description,fault,corrected,cause,action,guidance) in enumerate(CASES):
        service='trigger-worker' if any(x in case_id for x in ('event-','ingress-','dedupe-','setup-')) else 'tool-executor'
        logs=[{'tenant':'cedar','request_id':f'req-{index+33}',**fault},
              {'tenant':'maple','status':200,'same_provider_available':True,'unrelated_read_succeeds':True}]
        rows={'logs':logs,'metrics':[{'tenant':'cedar','requests':500+index*17,'failures':350+index*5 if fault['status']>=400 else 0,'business_operations_blocked':350+index*5,'queue_depth':90+index*3,'p95_latency_ms':1200+index*40},
                                   {'tenant':'maple','requests':450+index*11,'failures':0,'business_operations_blocked':0,'queue_depth':0,'p95_latency_ms':160}],
              'deployments':[{'service':'support-dashboard','change':'Unrelated inbox display release','version':'dashboard-v23'}],
              'dependencies':[{'service':service,'depends_on':['auth-service','provider-api','session-policy'],'provider_api_reachable':True}],
              'history':[{'symptom':'A similar workflow stopped following a release','cause':'An earlier provider outage','relation':'historical analogy only, not current proof'}],
              'knowledge':[{'url':BASE+source,'kind':'public_reference','summary':guidance}]}
        findings={'mechanism_observation':[('logs',0)],'tenant_impact':[('metrics',0),('metrics',1)]}
        actions=[cause+'_remediation'] if cause else ['collect_missing_telemetry','request_reproduction']
        if corrected is not None:
            rows['reproduce']=[{'tenant':'sandbox','provider_mock':True,'controlled':True,'condition':'original','same_request_except':case_id.split('-')[0]+'_configuration','check_passed':False,**fault},
                               {'tenant':'sandbox','provider_mock':True,'controlled':True,'condition':'corrected','same_request_except':case_id.split('-')[0]+'_configuration','check_passed':True,**fault,**corrected}]
            rows['reproduce'][1].update(CONTROL_CORRECTIONS.get(case_id,{}))
            findings['controlled_comparison']=[('reproduce',0),('reproduce',1)]
        else:
            findings={'telemetry_gap':[('logs',0)]}
        failures={}
        if index%4==0:failures['metrics']={'timeout_attempts':1}
        if index%5==0:failures['history']={'incomplete':True}
        if cause is None:failures.update({'metrics':{'incomplete':True},'reproduce':{'incomplete':True}})
        write(case_id,title,description,service,rows,cause,findings,actions,outcome='probable_cause' if cause else 'inconclusive',failures=failures,
              tags=['prospective_comparison_v3','public_documentation_inspired','llm_only_case'])


def vocabulary_definitions():
    definitions={'mechanism_observation':'A current observed fact identifying the proposed failure mechanism. Cite its exact canonical record.',
                 'controlled_comparison':'A discriminating changed-variable comparison. Cite BOTH original and corrected controlled observations.',
                 'tenant_impact':'Observed scope and severity. Cite metrics for BOTH the affected tenant and comparison tenant.',
                 'telemetry_gap':'An explicit observation establishing missing causal telemetry; do not infer absence from an empty partial query.'}
    for case in CASES:
        if case[6]:
            definitions[case[6]]=case[6].replace('_',' ')
            definitions[case[6]+'_remediation']=case[7]
    return definitions


CONTROL_CORRECTIONS={'sheets-discovery-039': {'has_more': False, 'returned_tools': 75, 'initial_page_count': 20}, 'airtable-expiry-041': {'token_exchange_attempted': True}, 'slack-user-043': {'error': None}, 'slack-redirect-046': {'oauth_error': None}, 'gmail-shape-047': {'validation_error': None}}
