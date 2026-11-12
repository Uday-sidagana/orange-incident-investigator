"""Build a credential-checked source ZIP, excluding local state and environments."""
import hashlib,json,re,zipfile
from pathlib import Path
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
TOP_FILES=['README.md','pyproject.toml','requirements-lock.txt','.env.example','.gitignore']
TOP_DIRS=['src','web','tests','scripts','data','evaluation','docs','config','submission']

def build():
    paths=[ROOT/name for name in TOP_FILES]
    for directory in TOP_DIRS:
        paths += [p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and not any(part.endswith('.egg-info') for part in p.parts) and p.suffix not in ('.pyc','.sqlite','.db')]
    paths=sorted(set(paths));secrets=[v for k,v in dotenv_values(ROOT/'.env').items() if v and len(v)>=10 and any(t in k for t in ('KEY','TOKEN','SECRET'))]
    for path in paths:
        assert path.name=='.env.example' or not path.name.startswith('.env'),path
        data=path.read_bytes()
        for secret in secrets:assert secret.encode() not in data,f'Configured credential found in {path.relative_to(ROOT)}'
        assert not re.search(rb'\b(?:sk-[A-Za-z0-9_-]{24,}|xox[baprs]-[A-Za-z0-9-]{16,}|gh[pousr]_[A-Za-z0-9]{25,})',data),f'Possible API credential in {path.relative_to(ROOT)}'
    destination=ROOT/'runs/submission-release';destination.mkdir(parents=True,exist_ok=True)
    archive=destination/'orange-incident-investigator-submission.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as output:
        for path in paths:output.write(path,Path('orange-incident-investigator')/path.relative_to(ROOT))
    report={'archive':str(archive.relative_to(ROOT)),'files':len(paths),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'credential_scan':'passed for configured credential values and common API credential patterns','excludes':['.env','local authentication','SQLite inbox','runs/','virtual environments','private reasoning'],'note':'Visible dialogue and tool audit are redacted authentic records, not a rewritten transcript. Video recording and reviewer access remain candidate actions.'}
    (destination/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return archive
if __name__=='__main__':build()
