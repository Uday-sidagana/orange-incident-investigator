"""Apply documented control fixes only after the original paired run is complete."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runs/composio-v3'
FIXES={
 'sheets-discovery-039':{'has_more':False,'returned_tools':75,'initial_page_count':20},
 'airtable-expiry-041':{'token_exchange_attempted':True},
 'slack-user-043':{'error':None},
 'slack-redirect-046':{'oauth_error':None},
 'gmail-shape-047':{'validation_error':None},
}

def apply():
    comparison=json.loads((OUT/'comparison.json').read_text())
    assert comparison['status']=='complete' and comparison['completed_pairs']==20,'Finish the frozen original run first'
    manifest=json.loads((OUT/'manifest.json').read_text())
    frozen=OUT/'frozen-v30'
    if not frozen.exists():
        assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in manifest['hashes'].items()),'Original inputs changed before snapshot'
        frozen.mkdir()
        for name in ('src','data','evaluation','config'):
            shutil.copytree(ROOT/name,frozen/name,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(OUT/'comparison.json',OUT/'comparison-original.json')
        shutil.copy2(OUT/'reviews.json',OUT/'reviews-original.json')
        for case in comparison['cases']:
            trace=ROOT/'runs/server'/case['ticket_id']/'traces'
            if trace.exists():shutil.copytree(trace,OUT/'multi_agent'/case['id']/'first-attempt-traces',dirs_exist_ok=True)
    changes=[]
    for case_id,updates in FIXES.items():
        path=ROOT/f'data/incidents/{case_id}.json';fixture=json.loads(path.read_text());row=fixture['sources']['reproduce'][1]
        old={key:row.get(key) for key in updates};row.update(updates)
        path.write_text(json.dumps(fixture,indent=2)+'\n');changes.append({'id':case_id,'record_id':row['record_id'],'before':old,'after':updates})
    author=ROOT/'scripts/scenario_expansion_v3.py';text=author.read_text()
    if 'CONTROL_CORRECTIONS=' not in text:
        text+='\n\nCONTROL_CORRECTIONS='+repr(FIXES)+'\n'
        text=text.replace("            findings['controlled_comparison']=[('reproduce',0),('reproduce',1)]", "            rows['reproduce'][1].update(CONTROL_CORRECTIONS.get(case_id,{}))\n            findings['controlled_comparison']=[('reproduce',0),('reproduce',1)]")
        author.write_text(text)
    metadata=json.loads((ROOT/'evaluation/dataset.json').read_text());metadata.update({'version':'3.1','control_corrections':list(FIXES),'note':'Five corrected control payloads; original frozen v3.0 benchmark and expected labels preserved.'})
    (ROOT/'evaluation/dataset.json').write_text(json.dumps(metadata,indent=2)+'\n')
    target=ROOT/'runs/composio-v31';target.mkdir(exist_ok=True)
    (target/'control-corrections.json').write_text(json.dumps(changes,indent=2)+'\n')
    print(json.dumps(changes,indent=2))

if __name__=='__main__':apply()
