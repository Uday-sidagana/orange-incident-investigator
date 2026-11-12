"""Concise human-facing reports; full evidence remains in the saved investigation."""
import html
import re
from urllib.parse import urlparse


def short(value,limit=240):
    text=' '.join(str(value or '').split())
    return text if len(text)<=limit else text[:limit-1].rstrip()+'…'


def md(value,limit=240):
    text=short(value,limit)
    return re.sub(r'([\\`*_\[\]<>])',r'\\\1',text)


def slack(value,limit=240):
    return html.escape(short(value,limit),quote=False)


def parts(ticket):
    result=ticket.get('result') or {}
    report=result.get('report') or {}
    primary=(report.get('hypotheses') or [None])[0]
    probable=report.get('outcome')=='probable_cause' and primary is not None
    return result,report,primary,probable


def review(ticket):
    events_all=ticket.get('events',[])
    latest_start=max((event.get('sequence',0) for event in events_all if event['type']=='investigation_started'),default=-1)
    events=[event['payload'] for event in events_all if event['type']=='review_recorded' and event.get('sequence',0)>latest_start]
    return events[-1] if events else None


def mode(ticket):
    result=ticket.get('result') or {}
    return 'Simulation' if result.get('approach')=='simulation' else 'Single-agent investigation' if result.get('approach')=='single_agent' else 'GPT agent team' if result.get('approach')=='multi_agent' else 'Investigation'


def status(ticket,stage='report'):
    feedback=review(ticket)
    if stage.startswith('review-') and feedback:
        return 'Review accepted' if feedback['verdict']=='accepted' else 'Changes requested'
    if stage=='intake':
        return 'Received'
    if stage=='failure' or ticket.get('status')=='failed':
        return 'Investigation failed'
    if parts(ticket)[1].get('outcome')=='inconclusive':
        return 'More evidence needed'
    return {'reviewed':'Reviewed','changes_requested':'Changes requested','needs_review':'Ready for review'}.get(ticket.get('status'),'Investigation in progress')


def material_limits(report):
    limits=report.get('limitations',[])
    # Runtime provenance belongs in the footer; keep the main uncertainty section actionable.
    return [item for item in limits if not item.startswith('Deterministic simulation:')][:2]


def linear_description(ticket):
    complaint=ticket['complaint']
    result,report,primary,probable=parts(ticket)
    lines=[f"**{md(complaint['company'],150)}** · {status(ticket)} · {mode(ticket)}",'']
    if report:
        summary=primary['description'] if probable else 'Cause not confirmed. Additional evidence is required before recommending a corrective change.'
        lines += [f"> **{'Likely cause' if probable else 'Assessment'}** — {md(summary,320)}",'']
    lines += ['### Reported impact',md(complaint['description'],320),'']
    findings=result.get('findings',[])
    if findings:
        lines += ['### What we found']+[f"- {md(finding['statement'],200)}" for finding in findings[:3]]+['']
    if report:
        lines += ['### Next steps']+[f"- [ ] {md(action,300)}" for action in report.get('recommended_actions',[])[:3]]+['']
        limits=material_limits(report)
        if limits:
            lines += ['### Open questions']+[f'- {md(item,220)}' for item in limits]+['']
    feedback=review(ticket)
    if feedback:
        lines += ['### '+('Assistant validation' if feedback.get('reviewer')=='assistant' else 'Human review'),f"**{status(ticket,'review-latest')}** — {md(feedback.get('notes') or 'No additional notes.',320)}",'']
    workflow=result.get('workflow') or {}
    count=len(result.get('trace',[]))
    confidence=primary.get('confidence','unknown').title() if probable else 'Not established'
    lines += [f"**Confidence:** {confidence} · **Tool calls:** {count}"+ (f" · **Control rounds:** {workflow['followup_rounds']}" if 'followup_rounds' in workflow else ''),
              '_Recommended actions have not been executed. Customer response remains a draft._','',
              '+++ Evidence & alternatives','**Source records**']
    for finding in findings[:8]:
        refs=list(dict.fromkeys(c['record_id'] for c in finding.get('citations',[])))
        lines.append(f"- {md(finding['statement'],140)} — "+', '.join('`'+short(ref,100).replace('`','')+'`' for ref in refs[:4]))
    if not findings:
        lines.append('- No grounded findings yet.')
    alternatives=report.get('hypotheses',[])[1:3]
    if alternatives:
        lines += ['','**Other explanations considered**']
        for hypothesis in alternatives:
            lines.append(f"- {md(hypothesis['description'],200)} ({hypothesis.get('confidence','unknown')} confidence)")
            counter=hypothesis.get('contradicting_evidence',[])
            if counter:
                lines.append('  - Counter-evidence: '+', '.join(f'`{short(ref,60)}`' for ref in counter[:3]))
    lines += ['',f"Plain thread: `{short(ticket.get('plain',{}).get('thread_id') or 'simulated',80)}`",
              f"Run: `{short(ticket['id'],80)}`",'+++']
    return '\n'.join(lines)


def linear_url(reference):
    value=(reference or {}).get('url','')
    parsed=urlparse(value)
    return value if parsed.scheme=='https' and parsed.hostname=='linear.app' and not any(ch in value for ch in '<>|') else None


def slack_fallback(ticket,stage,linear_reference=None):
    base=stage.removeprefix('summary-')
    result,report,primary,probable=parts(ticket)
    lines=[f"{status(ticket,base)} · {short(ticket['complaint']['title'],180)}",
           f"{short(ticket['complaint']['company'],100)} · {mode(ticket)}"]
    if base!='intake' and report:
        lines.append('Likely cause: '+short(primary['description'],230) if probable else 'Cause not confirmed; further evidence is needed.')
        if report.get('recommended_actions'):
            lines.append('Next: '+short(report['recommended_actions'][0],240))
    feedback=review(ticket)
    if base.startswith('review-') and feedback:
        lines.append('Review: '+short(feedback.get('notes'),240))
    url=linear_url(linear_reference)
    if url:
        lines.append(f"Linear: {linear_reference.get('identifier','Issue')} {url}")
    lines.append('Customer response not sent; no deployed fix is claimed.')
    return '\n'.join(lines)


def slack_blocks(ticket,stage,linear_reference=None):
    summary=stage.startswith('summary-')
    base=stage.removeprefix('summary-')
    result,report,primary,probable=parts(ticket)
    label=status(ticket,base)
    icon='🟠' if base=='intake' else '🔴' if base=='failure' else '🟢' if probable else '🟡'
    blocks=[{'type':'header','text':{'type':'plain_text','text':f'{icon} {label}', 'emoji':True}},
            {'type':'section','text':{'type':'plain_text','text':short(ticket['complaint']['title'],220)}}]
    fields=[{'type':'mrkdwn','text':'*Company*\n'+slack(ticket['complaint']['company'],150)},
            {'type':'mrkdwn','text':'*Status*\n'+label}]
    if base!='intake' and report:
        fields += [{'type':'mrkdwn','text':'*Confidence*\n'+(primary.get('confidence','unknown').title() if probable else 'Not established')},
                   {'type':'mrkdwn','text':f"*Investigation*\n{len(result.get('trace',[]))} tool calls"}]
    blocks.append({'type':'section','fields':fields})
    if base!='intake' and report:
        text='*Likely cause*\n'+slack(primary['description'],300) if probable else '*Assessment*\nCause not confirmed. Collect more evidence before changing production.'
        blocks.append({'type':'section','text':{'type':'mrkdwn','text':text}})
        findings=result.get('findings',[])
        if findings and not summary:
            blocks.append({'type':'section','text':{'type':'mrkdwn','text':'*Evidence*\n'+'\n'.join('• '+slack(f['statement'],170) for f in findings[:3])}})
        actions=report.get('recommended_actions',[])[:1 if summary else 2]
        if actions:
            blocks.append({'type':'section','text':{'type':'mrkdwn','text':'*Next steps*\n'+'\n'.join(f'{i}. '+slack(action,260) for i,action in enumerate(actions,1))}})
        limits=material_limits(report)
        if limits and not summary:
            blocks.append({'type':'section','text':{'type':'mrkdwn','text':'*Open question*\n'+slack(limits[0],240)}})
    if base=='failure':
        blocks.append({'type':'section','text':{'type':'plain_text','text':short(ticket.get('error') or 'Inspect the failed run before retrying.',260)}})
    feedback=review(ticket)
    if base.startswith('review-') and feedback:
        blocks.append({'type':'section','text':{'type':'mrkdwn','text':'*Review notes*\n'+slack(feedback.get('notes') or 'No additional notes.',320)}})
    elements=[]
    url=linear_url(linear_reference)
    if url:
        elements.append({'type':'mrkdwn','text':f'<{url}|Open {slack(linear_reference.get("identifier","Linear issue"),40)} in Linear>'})
    elements.append({'type':'plain_text','text':f'{mode(ticket)} · '+('Details in thread · ' if summary else '')+'Response not sent'})
    blocks.append({'type':'context','elements':elements})
    return blocks
