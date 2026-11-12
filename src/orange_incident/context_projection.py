"""Lossless observation deduplication for bounded model context.

Does not query fixtures or evaluator labels. The full trace remains authoritative.
Repeated rows are represented once; different payloads sharing an ID are retained.
"""
import json


def project(evidence,candidates,findings):
    canonical=[]; query_log=[]; derived=[]; locations={}; aliases={}; original={}
    def fingerprint(row):return json.dumps(row,sort_keys=True,separators=(',',':'))
    for envelope in evidence:
        rows=[]; observed=[]; original[envelope.evidence_id]=envelope
        valid=envelope.status!='error' and envelope.error is None
        for row in envelope.records:
            if not valid:continue
            key=fingerprint(row)
            if row.get('source_kind')=='derived_view':
                if key not in locations:derived.append(row);locations[key]=None
                continue
            if key not in locations:
                locations[key]=envelope.evidence_id;rows.append(row)
            observed.append(locations[key])
        aliases[envelope.evidence_id]=list(dict.fromkeys(observed))
        query_log.append({'evidence_id':envelope.evidence_id,'query':envelope.query.model_dump(exclude_none=True),
                          'status':envelope.status,'complete':envelope.complete,'attempt':envelope.attempt,
                          'returned_record_ids':[r.get('record_id') for r in envelope.records],
                          'error':envelope.error.model_dump() if envelope.error else None,'warning':envelope.warning})
        if rows:
            canonical.append({'evidence_id':envelope.evidence_id,'tool':envelope.query.tool,'query':envelope.query.model_dump(exclude_none=True),'status':envelope.status,
                              'complete':envelope.complete,'records':rows})
    def remap_hypothesis(hypothesis):
        value=hypothesis.model_dump()
        for field in ('supporting_evidence','contradicting_evidence'):
            value[field]=list(dict.fromkeys(mapped for eid in value[field] for mapped in aliases.get(eid,[])))
        return value
    def remap_finding(finding):
        value=finding.model_dump()
        for citation in value['citations']:
            envelope=original.get(citation['evidence_id'])
            row=next((r for r in envelope.records if r.get('record_id')==citation['record_id']),None) if envelope else None
            if row is not None and locations.get(fingerprint(row)):
                citation['evidence_id']=locations[fingerprint(row)]
        return value
    unique_findings=[];seen=set()
    for finding in list(findings)+[f for c in candidates for f in c.findings]:
        value=remap_finding(finding);key=json.dumps(value,sort_keys=True)
        if key not in seen:unique_findings.append(value);seen.add(key)
    candidate_views=[]
    for candidate in candidates:
        value=candidate.model_dump(exclude={'findings','hypothesis'})
        value['hypothesis']=remap_hypothesis(candidate.hypothesis)
        value['finding_codes']=list(dict.fromkeys(f.code for f in candidate.findings))
        candidate_views.append(value)
    return {'evidence':canonical,'query_log':query_log,'derived_views':derived,'candidates':candidate_views,'findings':unique_findings,
            'context_note':'Repeated identical rows and duplicate finding text are represented once. Query log preserves every attempt and its original returned IDs. Different observations, including conflicting payloads, are retained. Cite canonical evidence/record pairs. Derived views are not independent corroboration.'}
