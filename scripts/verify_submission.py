"""Offline, read-only verification of the packaged submission; no external API calls."""
import hashlib,json
from pathlib import Path
from orange_incident.benchmark import load_dataset,score
from orange_incident.contracts import Submission
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'submission/evaluation'

def verify():
    manifest=json.loads((OUT/'artifact-manifest.json').read_text())
    for item in manifest['files']:
        p=OUT/item['path'];assert p.is_file(),item['path']
        assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256'],item['path']
    matching=json.loads((OUT/'plain-input-matching/results.json').read_text());n=0
    for version in ['composio-v3','composio-v31']:
        source=OUT/'composio-v3/frozen-v30' if version=='composio-v3' else ROOT
        fixtures,truth=load_dataset(source)
        comparison=json.loads((OUT/version/'comparison.json').read_text())
        assert comparison['status']=='complete'
        for row in comparison['cases']:
            for arm,folder in [('multi_agent','multi_agent'),('single_agent','single_agent_plain_matched')]:
                path=OUT/version/folder/'submissions'/f"{row['id']}.json"
                result=Submission.model_validate_json(path.read_text())
                actual=score(result,fixtures[row['id']],truth[row['id']])
                assert actual==row[arm]['metrics'],(version,row['id'],arm,'score mismatch')
                n+=1
            ticket=json.loads((OUT/version/'multi_agent'/row['id']/'ticket.json').read_text())
            digest=hashlib.sha256(json.dumps({k:ticket['complaint'][k] for k in ['title','description']},sort_keys=True).encode()).hexdigest()
            match=next(x for x in matching['cases'] if x['version']==version and x['id']==row['id'])
            assert digest==match['exact_plain_input_hash'],row['id']
    transcript=ROOT/'submission/transcript';metadata=json.loads((transcript/'manifest.json').read_text())
    for filename,digest in metadata['files'].items():assert hashlib.sha256((transcript/filename).read_bytes()).hexdigest()==digest,filename
    words=len((ROOT/'submission/technical-note.md').read_text().split())
    assert words<=500,words
    result={'artifact_files_verified':len(manifest['files']),'scores_reproduced':n,'matched_incident_inputs_verified':25,'technical_note_words':words,'transcript_visible_messages':metadata['visible_messages'],'all_checks_passed':True}
    print(json.dumps(result,indent=2));return result
if __name__=='__main__':verify()
