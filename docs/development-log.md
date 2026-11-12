# Development observations

These are development checks on `gmail-001`, not held-out evaluation results or a training transcript. Failed runs remain in ignored local `runs/codex-development/` directories.

1. The local API key was configured, but one small API request returned `credit_balance_exhausted` / `insufficient_quota`. Further API requests were suspended.
2. Codex CLI was installed and authenticated using ChatGPT. A minimal non-interactive request completed successfully.
3. An unsupported CLI feature flag prevented startup. The adapter was corrected to use installed feature names.
4. An evidence-collecting run reached report validation, but its report did not pass evidence/vocabulary/consistency checks. It was retained as failed, rather than accepted as a diagnosis. Rejected drafts are now saved in execution traces for inspection.
5. An overly broad CLI event classifier treated a runtime notice as evidence-tool access. The classifier now distinguishes reasoning/planning/notices from direct execution/search/MCP/file actions. Tests cover both acceptance and rejection.
6. Another run exhausted its tool budget. Trace review showed semantic questions being sent to a literal substring search and time filters applied to untimestamped sources. Query descriptions and shared instructions now explicitly explain these semantics. The host also reports the remaining tool budget to the model and attempts a bounded final report after collection budget exhaustion.
7. Runtime failures are explicitly marked `run_status=failed` so they cannot earn abstention credit on insufficient-evidence cases.

Changes above address generic transport, interface, and reliability behavior; no expected cause was inserted into runtime code. Development results may inform prompts/playbooks, but do not train model weights automatically. Preserve the held-out split for later assessment, and pin the runtime/model before a final architecture comparison.

## First accepted development report

After interface corrections, Codex completed `gmail-001` with eight tool calls and selected the expected recipient-mapping regression as the leading cause. The scorer measured valid citations (1.0), finding recall 0.5, and finding precision 0.4; grounded top-1 did not pass. Controlled reproduction was not obtained. This is a single tuned development case, not evidence of held-out accuracy or multi-agent superiority.

Trace review also identified that the original reproduction records have no timestamps. Shared instructions were clarified to start reproduction queries without time filters. This is a general tool-interface correction; the accepted report remains scored as originally generated. The missing evidence is a concrete target for the forthcoming Critic agent's follow-up behavior.
