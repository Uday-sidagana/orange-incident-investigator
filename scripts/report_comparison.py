"""Generate an auditable report from completed first-attempt paired results."""
import csv,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runs/composio-v3'

def generate():
    data=json.loads((OUT/'comparison.json').read_text())
    if data['completed_pairs']!=20 or data['status']!='complete':raise RuntimeError('All 20 paired runs must finish before generating final results')
    reviews=json.loads((OUT/'reviews.json').read_text());sources={c['id']:c for c in json.loads((ROOT/'evaluation/prospective-v3.json').read_text())}
    truth=json.loads((ROOT/'evaluation/ground_truth.json').read_text())
    # Manual review never replaces the independently scored first-attempt outcome.
    for row in data['cases']:
        row['review']=reviews.get(row['id']);row['source_url']=sources[row['id']]['source_url']
        row['expected']={'outcome':truth[row['id']]['expected_outcome'],'cause':truth[row['id']]['cause_code']}
    (OUT/'comparison.json').write_text(json.dumps(data,indent=2)+'\n')
    fields=['case_id','expected_outcome','expected_cause','multi_run_status','multi_outcome','multi_top_cause','multi_correct','multi_grounded','multi_citation_validity','multi_tool_calls','multi_latency_seconds','multi_input_tokens','multi_output_tokens','single_run_status','single_outcome','single_top_cause','single_correct','single_grounded','single_citation_validity','single_tool_calls','single_latency_seconds','single_input_tokens','single_output_tokens','assistant_review','linear_url']
    with (OUT/'comparison.csv').open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        for row in data['cases']:
            item={'case_id':row['id'],'expected_outcome':row['expected']['outcome'],'expected_cause':row['expected']['cause'],'assistant_review':(row.get('review') or {}).get('verdict'),'linear_url':row.get('integrations',{}).get('linear',{}).get('url')}
            for arm,prefix in [('multi_agent','multi'),('single_agent','single')]:
                result=row[arm];m=result.get('metrics',{})
                item.update({prefix+'_run_status':result['run_status'],prefix+'_outcome':result['outcome'],prefix+'_top_cause':result.get('top_cause'),prefix+'_correct':m.get('root_cause_top1',False),prefix+'_grounded':m.get('grounded_top1',False)})
                for key in ('citation_validity','tool_calls','latency_seconds','input_tokens','output_tokens'):item[prefix+'_'+key]=m.get(key)
            writer.writerow(item)
    lines=['# Measured single-agent versus multi-agent comparison','', 'Twenty new public-documentation-inspired synthetic cases, one first attempt per architecture per case. Both use GPT-5.4 with low reasoning effort, identical saved Plain incident text, the same nine evidence tools and failure-injection rules, the same public vocabulary and citation validator, and identical global limits. Multi-agent cases enter through real Plain; queue and outbound time are excluded from the inference latency measurement.','', 'The first-attempt outputs are preserved independently of assistant reviews and any subsequent operational recovery. Wrong abstentions and execution failures count as incorrect.','', '| Metric | Multi-agent team | Single agent |','| --- | ---: | ---: |']
    summary=data['summary']
    def percent(key):return [f"{100*summary[a][key]:.1f}%" for a in ('multi_agent','single_agent')]
    for label,key in [('Root-cause accuracy (includes outcome)','root_cause_accuracy'),('Outcome accuracy','outcome_accuracy'),('Grounded correct reports','grounded_top1'),('Mean citation validity','citation_validity'),('Mean finding precision','finding_precision'),('Mean finding recall','finding_recall'),('Mean annotated action precision','action_precision')]:
        values=percent(key);lines.append(f'| {label} | {values[0]} | {values[1]} |')
    for label,key,fmt in [('Mean tool attempts','mean_tool_calls','.1f'),('Mean inference seconds','mean_latency_seconds','.1f'),('Median inference seconds','median_latency_seconds','.1f'),('Reported input tokens','input_tokens',','),('Reported output tokens','output_tokens',','),('Reported total tokens','total_tokens',',')]:
        values=[format(summary[a][key],fmt) for a in ('multi_agent','single_agent')];lines.append(f'| {label} | {values[0]} | {values[1]} |')
    paired={'both_correct':0,'only_multi_correct':0,'only_single_correct':0,'both_incorrect':0}
    for row in data['cases']:
        m=bool(row['multi_agent'].get('metrics',{}).get('root_cause_top1'));s=bool(row['single_agent'].get('metrics',{}).get('root_cause_top1'))
        paired['both_correct' if m and s else 'only_multi_correct' if m else 'only_single_correct' if s else 'both_incorrect']+=1
    lines+=['','Paired outcomes: '+', '.join(f'{key.replace("_"," ")}: {value}' for key,value in paired.items())+'.','', '## Per-case results','', '| Case | Expected | Multi-agent first attempt | Single-agent first attempt | Assistant review |','| --- | --- | --- | --- | --- |']
    for row in data['cases']:
        descriptions=[]
        for arm in ('multi_agent','single_agent'):
            r=row[arm];correct=r.get('metrics',{}).get('root_cause_top1',False)
            descriptions.append(f"{'Correct' if correct else 'Incorrect'} · {r['outcome']} · {r['run_status']}")
        lines.append(f"| {row['id']} | {row['expected']['cause'] or 'Inconclusive'} | {descriptions[0]} | {descriptions[1]} | {(row.get('review') or {}).get('verdict','Pending')} |")
    lines+=['','## Interpretation and limits','', '- This is an author-visible, closed-vocabulary synthetic cohort, not blind external evaluation. Original held-out cases were not used. Prompts, models, dataset and validators were hash-frozen before execution; the first-attempt score is not improved by selecting retries.',
            '- A grounded correct report requires both correct cause/outcome and all annotated finding requirements. Citation validity checks that referenced observed records exist; neither metric alone proves every sentence or proposed action is correct. Assistant review notes inspect wording, counter-evidence, remediation and uncertainty.',
            '- Controls are precomputed sandbox observations, not live provider experiments. Some flat control records retain initial diagnostic fields; dataset ambiguities are called out in review notes rather than silently changed after seeing model results.',
            '- Latency excludes Plain queue, Slack/Linear delivery and review. Multi-agent and baseline runs shared local/provider resources (original team workers and up to three baseline workers in a later input-matching pass), so these numbers are not a controlled production throughput study.',
            '- Token totals sum provider-reported usage, including reasoning tokens. Failed/cancelled requests without usage may still incur provider charges; these totals are not a billing reconciliation.',
            '- One sample per architecture per case is insufficient for broad statistical superiority claims. Extra critics and tool calls can add useful checks, excessive abstention, cost and additional failure opportunities; measured outcomes decide the comparison.',
            '', '## Review and source records','']
    for row in data['cases']:
        review=row.get('review') or {};lines += [f"### {row['id']}",'',review.get('notes','Review pending.'),'',f"Source: [Composio guide]({row['source_url']}). Ticket: `{row['ticket_id']}`.",'']
    lines += ['Machine-readable results: `runs/composio-v3/comparison.json` and `comparison.csv`. Frozen configuration: `manifest.json`. Original submissions, model calls, task logs and manual review records are retained under the same run directory.']
    report_path=ROOT/'docs/comparison-results.md'
    existing=report_path.read_text() if report_path.exists() else ''
    appendix='\n## Input audit and preserved versions'+existing.split('\n## Input audit and preserved versions',1)[1] if '\n## Input audit and preserved versions' in existing else ''
    report_path.write_text('\n'.join(lines)+'\n'+appendix)
    print(json.dumps({'paired_outcomes':paired,'summary':summary},indent=2))

if __name__=='__main__':generate()
