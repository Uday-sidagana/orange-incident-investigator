import asyncio
import json
from pathlib import Path
import pytest
from orange_incident.investigation import run_simulation
from orange_incident.tools import Simulation
from orange_incident.presentation import linear_description,slack_blocks,slack_fallback

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('case_id',['oauth-013','race-016','body-029','payload-031'])
def test_expanded_causes_require_control_evidence(case_id,tmp_path):
    sim=Simulation(ROOT/f'data/incidents/{case_id}.json')
    sim.incident.id='unrecognized-id'
    sim.incident.title='Customer complaint'
    sim.data['sources']['reproduce']=[]
    result,_=asyncio.run(run_simulation(sim,tmp_path))
    assert result.report.outcome=='inconclusive'


def test_expansion_has_disjoint_complete_partitions():
    metadata=json.loads((ROOT/'evaluation/dataset.json').read_text())
    split=json.loads((ROOT/'evaluation/splits.json').read_text())
    assert len(metadata['added_incidents'])==len(set(metadata['added_incidents']))==20
    assert not set(split['development']) & set(split['held_out'])
    assert len([key for ids in split.values() for key in ids])==len(set().union(*(set(ids) for ids in split.values())))
    assert set().union(*(set(ids) for ids in split.values()))=={p.stem for p in (ROOT/'data/incidents').glob('*.json')}


def test_presentation_preserves_uncertainty_and_bounds_untrusted_text():
    ticket={'id':'internal-id','status':'needs_review','complaint':{'title':'Title '*200,'company':'<!channel> <@U123>','description':'Impact '*200},
            'result':{'approach':'simulation','report':{'outcome':'inconclusive','hypotheses':[{'description':'Unverified guess','confidence':'low'}],
            'recommended_actions':['Collect request IDs '*100],'limitations':['Missing logs']},'findings':[],'trace':[]}}
    blocks=slack_blocks(ticket,'report',{'url':'https://linear.app/demo/issue/D-1','identifier':'D-1'})
    encoded=json.dumps(blocks)
    assert '<!channel>' not in encoded and '<@U123>' not in encoded
    assert 'Likely cause' not in encoded and 'Cause not confirmed' in encoded
    assert len(blocks)<15
    for block in blocks:
        if isinstance(block.get('text'),dict):
            assert len(block['text']['text'])<=3000
    rendered=linear_description(ticket)
    assert 'Likely cause' not in rendered and 'Cause not confirmed' in rendered
    assert '+++ Evidence & alternatives' in rendered
    assert 'internal-id' not in slack_fallback(ticket,'report')
