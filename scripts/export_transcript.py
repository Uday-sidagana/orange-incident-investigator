"""Export visible Codex dialogue faithfully; never export reasoning/system messages."""
import argparse,hashlib,json,re
from pathlib import Path
from collections import Counter
from dotenv import dotenv_values

def scrub(text,secrets):
    for value in secrets:text=text.replace(value,'[REDACTED CREDENTIAL]')
    return re.sub(r'\b(?:sk-[A-Za-z0-9_-]{16,}|xox[baprs]-[A-Za-z0-9-]{12,}|gh[pousr]_[A-Za-z0-9]{20,})','[REDACTED CREDENTIAL]',text)

def export(source,destination,root):
    destination.mkdir(parents=True,exist_ok=True)
    secrets=sorted({v for k,v in dotenv_values(root/'.env').items() if v and len(v)>=10 and any(t in k for t in ('KEY','TOKEN','SECRET'))},key=len,reverse=True)
    records=[];tools=[];counts=Counter();source_bytes=source.read_bytes()
    for line in source_bytes.splitlines():
        row=json.loads(line)
        if row.get('type')!='response_item':continue
        item=row.get('payload',{});kind=item.get('type')
        if kind=='message' and item.get('role') in ('user','assistant'):
            if item.get('phase') in ('analysis','summary') or item.get('channel') in ('analysis','summary'):continue
            chunks=[]
            for c in item.get('content',[]):
                if c.get('type') in ('input_text','output_text','text'):chunks.append(c.get('text',''))
                elif 'image' in c.get('type',''):chunks.append('[Image attachment: binary content not included in text export]')
            body='\n'.join(chunks)
            if item['role']=='user' and body.lstrip().startswith('<environment_context>'):continue
            records.append({'number':len(records)+1,'timestamp':row.get('timestamp'),'role':item['role'],'phase':item.get('phase'),'text':scrub(body,secrets)})
            counts[item['role']]+=1
        elif kind in ('function_call','function_call_output','custom_tool_call','custom_tool_call_output'):
            tools.append(json.loads(scrub(json.dumps({'timestamp':row.get('timestamp'),'item':item},ensure_ascii=False),secrets)))
    (destination/'conversation.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
    (destination/'tool-audit.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in tools))
    intro='''# Coding-assistant conversation — authentic visible-message export

Exported from the locally persisted Codex session. User and assistant wording and ordering are preserved. This is not a reconstructed or professionally rewritten dialogue. Credentials are replaced with explicit redaction markers. Image binaries, system/developer messages, private reasoning and environment-only messages are excluded. Visible tool calls/results are retained separately in tool-audit.jsonl. Historical mistakes and subsequent corrections remain in the record. This snapshot ends at the export boundary shown in manifest.json; later work is not retroactively inserted.

'''
    content=[intro]
    for r in records:content += [f"## Message {r['number']:03d} · {'Uday' if r['role']=='user' else 'Codex'} · {r['timestamp']}",'',r['text'],'']
    (destination/'conversation.md').write_text('\n'.join(content))
    manifest={'source_filename':source.name,'source_sha256':hashlib.sha256(source_bytes).hexdigest(),'source_bytes':len(source_bytes),'visible_messages':len(records),'by_role':dict(counts),'tool_records':len(tools),'last_visible_message_timestamp':records[-1]['timestamp'] if records else None,'coverage':'Persisted original response_item messages only; compaction summaries are not substituted for dialogue. No invented messages. Current active turn may not yet be complete.','exclusions':['system/developer messages','private reasoning','environment-only user messages','image binaries'],'redaction':'Configured credential values and common API-token patterns, without rewriting substantive dialogue.','files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.iterdir() if p.is_file() and p.name!='manifest.json'}}
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'visible_messages':len(records),'by_role':dict(counts),'tool_records':len(tools),'destination':str(destination)}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('--destination',type=Path,default=Path('submission/transcript'));args=parser.parse_args();export(args.source,args.destination,Path.cwd())
