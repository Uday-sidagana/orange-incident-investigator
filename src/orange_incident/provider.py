"""Small OpenAI Responses adapter. Secrets never enter persisted payloads."""
import os
from pathlib import Path
from dotenv import dotenv_values
from openai import AsyncOpenAI
from .contracts import Diagnosis
from .models import Query


class ProviderFailure(RuntimeError):
    pass


def load_config(path: Path = Path('.env')) -> tuple[str, str]:
    config = dotenv_values(path) if path.exists() else {}
    key = os.environ.get('OPENAI_API_KEY') or config.get('OPENAI_API_KEY')
    model = os.environ.get('OPENAI_MODEL') or config.get('OPENAI_MODEL') or 'gpt-4.1-mini'
    if not key:
        raise ProviderFailure('OPENAI_API_KEY is missing; configure the local ignored .env file')
    return key, model


def tool_definition():
    schema = Query.model_json_schema()
    schema['required'] = list(schema['properties'])
    for value in schema['properties'].values():
        value.pop('default', None)
    return {'type':'function', 'name':'query_evidence',
            'description':'Read logs, metrics, deployments, dependencies, history, reference knowledge, or controlled reproduction records. Filters are exact except case-insensitive search. Partial results do not prove absence. Retry transient errors within budget.',
            'parameters':schema, 'strict':True}


class GPTProvider:
    def __init__(self, api_key: str, model: str, client=None):
        self.model = model
        self.client = client or AsyncOpenAI(api_key=api_key, max_retries=0, timeout=30)
        self.calls = []

    async def request(self, *, instructions, messages, final=False, max_output_tokens=2500):
        try:
            common = dict(model=self.model, instructions=instructions, input=messages,
                          max_output_tokens=max_output_tokens, store=False)
            if final:
                response = await self.client.responses.parse(**common, text_format=Diagnosis)
            else:
                response = await self.client.responses.create(**common, tools=[tool_definition()], parallel_tool_calls=True)
        except Exception as exc:
            # No raw provider exception text: upstream diagnostics can include request contents.
            code = getattr(exc, 'code', None)
            safe_codes = {'credit_balance_exhausted','insufficient_quota','invalid_api_key','model_not_found','rate_limit_exceeded'}
            reason = code if code in safe_codes else type(exc).__name__
            self.calls.append({'model':self.model, 'status':'error', 'error':reason, 'usage':None})
            raise ProviderFailure(f'GPT request failed: {reason}') from None
        usage = response.usage.model_dump() if response.usage else None
        self.calls.append({'model':response.model, 'response_id':response.id, 'status':response.status, 'usage':usage})
        if response.status != 'completed':
            raise ProviderFailure(f'GPT response was {response.status}; output was not accepted')
        return response

    async def close(self):
        await self.client.close()
