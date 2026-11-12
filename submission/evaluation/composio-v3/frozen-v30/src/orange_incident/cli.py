import argparse
import asyncio
import json
from pathlib import Path
from .models import Query
from .tools import Simulation


async def collect(fixture: Path, output: Path):
    simulation = Simulation(fixture)
    await asyncio.gather(*(simulation.query_with_retry(Query(tool=tool)) for tool in
                           ['logs', 'metrics', 'deployments', 'dependencies', 'history', 'knowledge']))
    output.mkdir(parents=True, exist_ok=True)
    payload = {'mode': 'offline_tool_demonstration', 'agent_investigation': False,
               'incident': simulation.incident.model_dump(),
               'tool_calls': len(simulation.trace),
               'trace': [result.model_dump() for result in simulation.trace]}
    target = output / 'trace.json'
    target.write_text(json.dumps(payload, indent=2) + '\n')
    print(f'Collected {len(simulation.trace)} tool calls. Trace: {target}')
    print('Offline demonstration only: no LLM diagnosis or evaluation score was generated.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['collect', 'workflow-demo', 'validate-dataset', 'score', 'investigate', 'serve', 'plain-check', 'simulate', 'simulate-suite', 'integrations-check', 'agents','single-agent'])
    parser.add_argument('--fixture', type=Path, default=Path('data/incidents/gmail-001.json'))
    parser.add_argument('--output', type=Path, default=Path('runs/offline'))
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--submissions', type=Path, default=Path('runs/submissions'))
    parser.add_argument('--split', choices=['all', 'development', 'held_out','prospective_comparison'], default='all')
    parser.add_argument('--provider', choices=['openai', 'codex'], default='openai')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--team-name')
    parser.add_argument('--channel-name')
    args = parser.parse_args()
    if args.command == 'single-agent':
        from .single_agent import run_single_agent
        async def single():
            result=await run_single_agent(Simulation(args.fixture),args.output,root=args.root)
            print(json.dumps({'incident':result.incident_id,'approach':result.approach,'outcome':result.report.outcome,'run_status':result.run_status,'tool_calls':len(result.trace),'input_tokens':result.input_tokens,'output_tokens':result.output_tokens},indent=2))
        asyncio.run(single())
        return
    if args.command == 'agents':
        from .llm_agents import run_live_agents
        async def agents():
            result,state=await run_live_agents(Simulation(args.fixture),args.output,root=args.root)
            print(json.dumps({'incident':result.incident_id,'approach':result.approach,'outcome':result.report.outcome,
                              'run_status':result.run_status,'causes':result.ranked_cause_codes,'tasks':len(state.tasks),
                              'tool_calls':len(result.trace),'input_tokens':result.input_tokens,'output_tokens':result.output_tokens,
                              'limitations':result.report.limitations},indent=2))
        asyncio.run(agents())
        return
    if args.command == 'integrations-check':
        import os
        from dotenv import dotenv_values,set_key
        from .channels import DeliveryFailure,LinearClient,SlackClient
        settings=dotenv_values(args.root/'.env')
        def setting(name):
            return os.environ.get(name) or settings.get(name) or ''
        async def check_connections():
            result={}
            if setting('LINEAR_API_KEY'):
                client=LinearClient(setting('LINEAR_API_KEY'),setting('LINEAR_TEAM_ID'))
                try:
                    result['linear']=await client.verify()
                    if args.team_name:
                        matches=[team for team in result['linear']['teams'] if args.team_name.casefold() in (team['name'].casefold(),team['key'].casefold())]
                        if len(matches)!=1:
                            raise DeliveryFailure('Linear team name/key must identify exactly one accessible team.')
                        set_key(str(args.root/'.env'),'LINEAR_TEAM_ID',matches[0]['id'])
                        result['linear']['selected_team']=matches[0]
                except DeliveryFailure as exc:
                    result['linear']={'verified':False,'error':str(exc)}
                finally:
                    await client.close()
            else:
                result['linear']={'verified':False,'needs':'LINEAR_API_KEY'}
            if setting('SLACK_BOT_TOKEN'):
                client=SlackClient(setting('SLACK_BOT_TOKEN'),setting('SLACK_CHANNEL_ID'))
                try:
                    if args.channel_name:
                        client.channel_id=await client.find_channel(args.channel_name)
                    result['slack']=await client.verify()
                    if client.channel_id:
                        result['slack']['channel_id']=client.channel_id
                        if args.channel_name:
                            set_key(str(args.root/'.env'),'SLACK_CHANNEL_ID',client.channel_id)
                except DeliveryFailure as exc:
                    result['slack']={'verified':False,'error':str(exc)}
                finally:
                    await client.close()
            else:
                result['slack']={'verified':False,'needs':'SLACK_BOT_TOKEN'}
            print(json.dumps(result,indent=2))
            print('Read-only verification: no issues or messages created. Integration enable flags were not changed.')
        asyncio.run(check_connections())
        return
    if args.command in ('simulate','simulate-suite'):
        from .investigation import run_simulation
        async def simulate_all():
            fixtures=[args.fixture] if args.command=='simulate' else sorted((args.root/'data/incidents').glob('*.json'))
            for fixture in fixtures:
                simulation=Simulation(fixture)
                target=args.output / simulation.incident.id
                result,state=await run_simulation(simulation,target)
                if args.command=='simulate-suite':
                    submissions=args.output/'submissions'
                    submissions.mkdir(parents=True,exist_ok=True)
                    (submissions/f'{result.incident_id}.json').write_text(result.model_dump_json(indent=2)+'\n')
                print(json.dumps({'incident':result.incident_id,'mode':state.mode,'outcome':result.report.outcome,
                    'run_status':result.run_status,'leading_hypothesis':result.ranked_cause_codes[:1],
                    'tasks':len(state.tasks),'tool_calls':len(result.trace),'followup_rounds':state.followup_rounds}))
        asyncio.run(simulate_all())
        return
    if args.command == 'plain-check':
        import os
        from dotenv import dotenv_values
        from .plain import PlainClient, PlainFailure
        config=dotenv_values(args.root / '.env')
        key=os.environ.get('PLAIN_API_KEY') or config.get('PLAIN_API_KEY')
        if not key:
            parser.error('Save PLAIN_API_KEY in the local ignored .env first')
        async def verify_plain():
            client=PlainClient(key)
            try:
                await client.verify()
                print('Plain machine-user authentication verified. No tickets or messages were created.')
            except PlainFailure as exc:
                print(str(exc))
            finally:
                await client.close()
        asyncio.run(verify_plain())
        return
    if args.command == 'serve':
        import uvicorn
        from .server import create_app
        uvicorn.run(create_app(args.root), host='127.0.0.1', port=args.port)
        return
    if args.command == 'validate-dataset':
        from .benchmark import validate_dataset
        print(json.dumps(validate_dataset(args.root), indent=2))
        return
    if args.command == 'score':
        from .benchmark import score_directory
        if not args.submissions.is_dir():
            parser.error('Submissions directory does not exist')
        result = score_directory(args.root, args.submissions, args.output / 'scores.json', args.split)
        print(json.dumps(result['summary'], indent=2))
        return
    if args.command == 'investigate':
        from .provider import GPTProvider, load_config
        from .baseline import investigate
        async def live():
            if args.provider == 'codex':
                from .codex_provider import CodexProvider
                provider = CodexProvider()
            else:
                key, model = load_config(args.root / '.env')
                provider = GPTProvider(key, model)
            try:
                result = await investigate(Simulation(args.fixture), provider,
                    json.loads((args.root / 'data/rubric.json').read_text()), args.output,
                    timeout_seconds=300 if args.provider == 'codex' else 180)
                print(json.dumps({'incident':result.incident_id,'outcome':result.report.outcome,'run_status':result.run_status,
                    'tool_calls':len(result.trace),'input_tokens':result.input_tokens,'output_tokens':result.output_tokens,
                    'limitations':result.report.limitations}, indent=2))
            finally:
                await provider.close()
        asyncio.run(live())
        return
    if args.command == 'collect':
        asyncio.run(collect(args.fixture, args.output))
    else:
        from .demo import workflow_demo
        target = args.output / 'workflow.json'
        state = asyncio.run(workflow_demo(args.fixture, target))
        print(f'Scripted workflow: {len(state.tasks)} tasks, {state.tool_calls} calls; {target}')
        print('No live agents or root-cause diagnosis. Outcome:', state.status)


if __name__ == '__main__':
    main()
