from orange_incident.context_projection import project
from orange_incident.models import Query,ToolResult,ToolError


def envelope(eid,rows,status='ok',error=None):
    return ToolResult(evidence_id=eid,query=Query(tool='logs'),records=rows,status=status,complete=status=='ok',error=error,attempt=1)


def test_projection_preserves_unique_and_conflicting_observations_and_failures():
    same={'record_id':'row-one','status':400,'input_present':True}
    changed={'record_id':'row-one','status':200,'input_present':True}
    evidence=[envelope('ev_first',[same]),envelope('ev_duplicate',[same]),envelope('ev_conflict',[changed]),
              envelope('ev_timeout',[],status='error',error=ToolError(code='timeout',message='Transient telemetry failure',retryable=True))]
    result=project(evidence,[],[])
    assert [(e['evidence_id'],e['records'][0]['status']) for e in result['evidence']]==[('ev_first',400),('ev_conflict',200)]
    assert len(result['query_log'])==4 and result['query_log'][-1]['error']['retryable']
    assert result['query_log'][1]['returned_record_ids']==['row-one']


def test_projection_keeps_derived_view_separate_without_treating_it_as_independent():
    row={'record_id':'view-one','source_kind':'derived_view','token_state':'expired'}
    result=project([envelope('ev_view',[row])],[],[])
    assert result['evidence']==[] and result['derived_views']==[row]


def test_projection_remaps_duplicate_citations_without_losing_the_observation():
    from orange_incident.contracts import Candidate,Finding,Citation
    from orange_incident.models import Hypothesis
    row={'record_id':'same-row','status':403,'scope_missing':True}
    finding=Finding(code='mechanism_observation',statement='Observed missing permission',citations=[Citation(evidence_id='ev_again',record_id='same-row')])
    candidate=Candidate(code='missing_grant',hypothesis=Hypothesis(description='A missing grant',supporting_evidence=['ev_again'],contradicting_evidence=[],confidence='medium',assumptions=[]),findings=[finding])
    result=project([envelope('ev_first',[row]),envelope('ev_again',[row])],[candidate],[finding])
    assert result['candidates'][0]['hypothesis']['supporting_evidence']==['ev_first']
    assert result['findings'][0]['citations']==[{'evidence_id':'ev_first','record_id':'same-row'}]
    assert len(result['findings'])==1 and result['evidence'][0]['records']==[row]
    assert candidate.hypothesis.supporting_evidence==['ev_again']
