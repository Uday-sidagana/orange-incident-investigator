"""Copy preserved, credential-redacted evaluation evidence into the submission."""
import hashlib,json,re,shutil
from pathlib import Path
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]

def package():
    out=ROOT/'submission/evaluation';out.mkdir(parents=True,exist_ok=True)
    secrets=sorted({v for k,v in dotenv_values(ROOT/'.env').items() if v and len(v)>=10 and any(t in k for t in ('KEY','TOKEN','SECRET'))},key=len,reverse=True)
    copied=[]
    for cohort in ['composio-v3','composio-v31','plain-input-matching','context-recovery','custom-intake','submission-demo']:
        source=ROOT/'runs'/cohort
        if not source.exists():continue
        for p in sorted(source.rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts or p.suffix in ('.pyc','.sqlite','.db') or p.name.startswith('.env'):continue
            if p.suffix not in ('.json','.jsonl','.csv','.md','.py','.toml'):continue
            raw=p.read_text()
            for secret in secrets:raw=raw.replace(secret,'[REDACTED CREDENTIAL]')
            raw=re.sub(r'\b(?:sk-[A-Za-z0-9_-]{16,}|xox[baprs]-[A-Za-z0-9-]{12,}|gh[pousr]_[A-Za-z0-9]{20,})','[REDACTED CREDENTIAL]',raw)
            target=out/cohort/p.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(raw)
            copied.append({'path':str(target.relative_to(out)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    (out/'artifact-manifest.json').write_text(json.dumps({'source':'Preserved local run artifacts; copied without selecting best-of retries. Credentials, if present, redacted explicitly. Historical frozen snapshots are evaluation evidence, not the current operational implementation.','files':copied},indent=2)+'\n')
    print(json.dumps({'files':len(copied),'destination':str(out)}))
if __name__=='__main__':package()
