"""Additional finite diagnostic playbooks over observed fields, never incident IDs."""


def extend(view,add,background):
    def assess(code,description,predicate,finding,statement,action,action_code,variable,control_finding):
        observed=view.select(predicate)
        if not observed:
            return
        controls=view.select(lambda row:row.get('controlled') is True and row.get('control_variable')==variable)
        verified=controls if {row.get('check_passed') for _,row in controls}>={False,True} else []
        add(code,description,
            [(finding,statement,observed),(control_finding,'Changing only the investigated control changes the observed outcome.',verified)],
            [action],[action_code],missing=[] if verified else [f'controlled {variable.replace("_"," ")} comparison'])

    assess('oauth_app_unverified','The custom OAuth app is blocked at consent verification before token exchange.',
           lambda r:r.get('oauth_error')=='unverified_app' and r.get('app_verification_status')=='unverified' and r.get('token_exchange_attempted') is False,
           'unverified_consent','The observed consent rejection identifies an unverified app before token exchange.',
           'Use a suitably verified OAuth app for the requested scopes, then reconnect and verify consent.',
           'verify_custom_oauth_app','oauth_app_verification','verification_control')
    assess('workspace_app_policy','An education workspace administrator policy blocks this OAuth app.',
           lambda r:r.get('oauth_error')=='access_not_configured' and r.get('workspace_edition')=='education' and r.get('admin_app_access')=='blocked',
           'workspace_policy_block','The education tenant reports an administrator-controlled app access rejection.',
           'Ask the workspace administrator to review and authorize the intended app under the organization policy; changing scopes alone does not resolve it.',
           'request_workspace_admin_access','admin_app_access','policy_control')
    assess('oauth_consent_revoked','Revoked consent prevents the expired connection from refreshing.',
           lambda r:r.get('refresh_error')=='invalid_grant' and r.get('consent_state')=='revoked',
           'revoked_consent','Refresh fails with invalid_grant and observed revoked consent.',
           'Reconnect the intended account with renewed consent; verify refresh and the affected action.',
           'reconnect_revoked_consent','consent_reconnection','reconnection_control')
    assess('refresh_rotation_race','Concurrent refreshes reuse an older generation of a rotated refresh token.',
           lambda r:r.get('refresh_error')=='invalid_grant' and r.get('consent_state')=='active' and r.get('refresh_token_rotated') is True and r.get('concurrent_refresh_count',0)>1 and r.get('submitted_generation')!=r.get('current_generation'),
           'refresh_generation_race','Concurrent refresh failures reference an older token generation despite active consent.',
           'Serialize refresh per connection and atomically store rotated credentials; verify parallel executions before rollout.',
           'serialize_connection_refresh','refresh_serialization','refresh_serialization_control')
    assess('wrong_connected_account','The router selects a different connected account from the one the request intended.',
           lambda r:r.get('expected_account_id') and r.get('selected_account_id') and r['expected_account_id']!=r['selected_account_id'] and r.get('result_matches_expected_account') is False,
           'account_selection_mismatch','A successful request uses a different account and returns the wrong account data.',
           'Select the intended connected account explicitly and verify its owner and returned resource.',
           'select_intended_connected_account','account_selection','account_selection_control')
    assess('provider_resource_role','OAuth scopes are present, but the provider account lacks the role required by this resource operation.',
           lambda r:r.get('provider_error')=='role_required' and r.get('required_resource_role') and r.get('granted_resource_role')!=r['required_resource_role'] and r.get('required_scope') in r.get('granted_scopes',[]),
           'resource_role_mismatch','The required scope is granted while the provider role does not satisfy the action.',
           'Use an account authorized for the required resource role, or request the minimum necessary role; retest the action.',
           'use_authorized_resource_role','resource_role','resource_role_control')
    assess('slack_channel_membership','The authenticated Slack bot is not a member of the destination channel.',
           lambda r:r.get('provider_error')=='not_in_channel' and r.get('token_authenticated') is True and r.get('bot_is_channel_member') is False,
           'channel_membership_missing','Slack authenticates the token but rejects posting because channel membership is absent.',
           'Invite the intended bot to the destination channel and retry the known rejected notification once.',
           'invite_bot_to_channel','channel_membership','membership_control')
    assess('sdk_argument_nesting','The client sends a required argument at the wrong path before provider execution.',
           lambda r:r.get('validation_error')=='missing_required_argument' and r.get('expected_argument_path') and r['expected_argument_path'] not in r.get('provided_argument_paths',[]) and r.get('provider_called') is False,
           'argument_path_mismatch','A required argument is present at a different path and validation stops before the provider.',
           'Use the current tool schema and correct nested argument shape; verify the serialized request and a controlled execution.',
           'correct_nested_arguments','argument_nesting','argument_shape_control')
    assess('toolkit_version_pin','The application pins a toolkit version that does not contain the requested action.',
           lambda r:r.get('action_known_in_registry') is True and r.get('tool_available_on_requested_version') is False and r.get('requested_version')==r.get('resolved_version'),
           'unavailable_pinned_tool','The catalog knows the action but the resolved pinned version does not contain it.',
           'Select a tested toolkit version containing the action and verify compatibility before changing the production pin.',
           'update_and_test_toolkit_pin','toolkit_pin','toolkit_pin_control')
    assess('expired_provider_api_key','The integration still uses an expired provider API-key version.',
           lambda r:r.get('auth_method')=='api_key' and r.get('key_expired') is True and r.get('configured_credential_version')!=r.get('active_credential_version'),
           'expired_api_key','The API-key credential is expired and differs from the active provider credential version.',
           'Replace the stored provider API key securely, verify a read-only action, then retest the affected operation.',
           'replace_expired_provider_key','credential_version','credential_version_control')
    assess('provider_region_mismatch','Requests use a provider region different from the connection resource region.',
           lambda r:r.get('connection_region') and r.get('request_region') and r['connection_region']!=r['request_region'] and r.get('resource_exists_in_connection_region') is True,
           'region_mismatch','The resource exists in the connection region, but requests target another region.',
           'Route the connection to its correct regional provider endpoint and verify the same resource.',
           'route_to_connection_region','provider_region','region_control')
    assess('provider_ip_allowlist','The provider rejects the new egress route because it is not allowlisted.',
           lambda r:r.get('provider_error')=='ip_not_allowed' and r.get('ip_allowlisted') is False,
           'egress_not_allowlisted','The provider explicitly rejects an unapproved egress route.',
           'Confirm the expected egress route with the customer and update the provider allowlist or restore an approved route.',
           'approve_expected_egress','egress_route','egress_control')
    assess('webhook_clock_skew','The receiver clock puts an otherwise valid webhook signature outside its timestamp window.',
           lambda r:r.get('signature_valid') is True and abs(r.get('timestamp_skew_seconds',0))>r.get('allowed_skew_seconds',float('inf')),
           'webhook_clock_outside_window','The valid signature is rejected because the timestamp difference exceeds the allowed window.',
           'Synchronize the receiver clock and verify delivery while keeping replay-window validation enabled.',
           'synchronize_webhook_clock','receiver_clock','clock_control')
    assess('webhook_event_subscription','The webhook subscription omits the event type needed for trigger delivery.',
           lambda r:r.get('matching_trigger_event_exists') is True and r.get('required_event_type') and r['required_event_type'] not in r.get('subscription_event_types',[]) and r.get('outbound_attempted') is False,
           'subscription_event_missing','A trigger event exists but its delivery event type is missing from the subscription.',
           'Subscribe the intended destination to the correct delivery event type and verify a new matching event.',
           'subscribe_to_delivery_event','subscription_event_type','subscription_control')
    baseline=view.select(lambda r:r.get('poll_success') is True and r.get('message_predates_baseline') is True and r.get('backfill_enabled') is False and r.get('event_emitted') is False)
    if baseline:
        newer=view.select(lambda r:r.get('poll_success') is True and r.get('message_predates_baseline') is False and r.get('event_emitted') is True)
        add('polling_baseline_expectation','Healthy polling intentionally excludes messages that existed before its baseline.',
            [('polling_baseline_exclusion','Messages before the polling baseline are excluded without backfill.',baseline),
             ('post_baseline_delivery','A new message after the baseline is delivered.',newer)],
            ['Fetch historical messages separately; verify trigger delivery with a message created after the baseline.'],
            ['fetch_historical_messages_separately'],missing=[] if newer else ['delivery of a post-baseline message'])
    assess('expired_history_cursor','The stored history cursor is no longer accepted by the provider.',
           lambda r:r.get('poll_error')=='history_cursor_expired' and r.get('stored_cursor_valid') is False,
           'invalid_history_cursor','Polling rejects an invalid stored cursor while the connection remains active.',
           'Resynchronize the cursor using the provider-supported recovery path, account for the missed interval, and verify a new event.',
           'resynchronize_history_cursor','history_cursor_resync','cursor_resync_control')
    assess('webhook_body_transformation','Signature verification uses transformed JSON bytes rather than the original request body.',
           lambda r:r.get('signature_matches_raw') is True and r.get('signature_matches_reencoded') is False and r.get('raw_body_hash')!=r.get('verified_body_hash'),
           'signature_body_changed','The signature matches the raw body but not the reserialized bytes used by the handler.',
           'Verify the original raw request bytes before parsing or reserializing JSON; keep signature verification enabled.',
           'verify_original_body_bytes','signature_input_bytes','raw_body_control')
    assess('internal_dns_failure','Internal name resolution prevents credential lookup before any provider request.',
           lambda r:r.get('network_error')=='dns_resolution_failed' and r.get('operation')=='credential_lookup' and r.get('provider_called') is False,
           'credential_dns_failure','Credential lookup fails at internal DNS resolution, before the external provider is called.',
           'Restore the intended internal DNS record or resolver configuration and verify resolution and credential lookup.',
           'restore_internal_dns','internal_dns_resolver','dns_control')
    assess('provider_payload_limit','The serialized attachment request exceeds the provider request-size limit.',
           lambda r:r.get('provider_status')==413 and r.get('payload_bytes',0)>r.get('max_request_bytes',float('inf')) and r.get('upload_reference_valid') is True,
           'payload_exceeds_limit','A valid upload reference produces a request larger than the provider accepts.',
           'Reduce the attachment/request size or use a supported upload path; verify the final serialized payload before retrying.',
           'reduce_provider_payload','payload_size','payload_size_control')
    conflict=view.select(lambda r:r.get('telemetry_window_consistent') is False)
    if conflict:
        background.append(view.finding('telemetry_conflict','Telemetry sources disagree and their observation windows are not aligned.',conflict))
