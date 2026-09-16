from __future__ import annotations
import json, os, re, requests
from typing import Any
from dotenv import load_dotenv
load_dotenv()

class LLMError(RuntimeError): pass

class OpenRouterClient:
    def __init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY','').strip()
        self.base_url = os.getenv('OPENROUTER_BASE_URL','https://openrouter.ai/api/v1').rstrip('/')
        self.model = os.getenv('OPENROUTER_MODEL','google/gemma-4-26b-a4b')
        self.temperature = float(os.getenv('OPENROUTER_TEMPERATURE','0'))
        if not self.api_key:
            raise LLMError('OPENROUTER_API_KEY is not configured. Copy .env.example to .env and set it.')

    def generate_json(self, system: str, user: str) -> dict[str, Any]:
        url = f'{self.base_url}/chat/completions'
        payload = {'model': self.model, 'temperature': self.temperature,
                   'messages':[{'role':'system','content':system},{'role':'user','content':user}],
                   'response_format': {'type':'json_object'}}
        headers = {'Authorization':f'Bearer {self.api_key}','Content-Type':'application/json',
                   'HTTP-Referer':'http://localhost:8501','X-Title':'Deal Review Pipeline'}
        r = requests.post(url, headers=headers, json=payload, timeout=120)
        # Some OpenRouter-routed models/providers do not expose response_format.
        # Retry once without it; the parser below still validates JSON strictly.
        if r.status_code >= 400 and 'response_format' in r.text.lower():
            payload.pop('response_format', None)
            r = requests.post(url, headers=headers, json=payload, timeout=120)
        if r.status_code >= 400:
            raise LLMError(f'OpenRouter HTTP {r.status_code}: {r.text[:1000]}')
        try:
            content = r.json()['choices'][0]['message']['content']
        except Exception as exc:
            raise LLMError(f'Unexpected OpenRouter response: {r.text[:1000]}') from exc
        return parse_json(content)

def parse_json(content: str) -> dict[str, Any]:
    content = content.strip()
    content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content, flags=re.I|re.S).strip()
    try: return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', content, flags=re.S)
        if match:
            try: return json.loads(match.group(0))
            except json.JSONDecodeError: pass
    raise LLMError('Malformed LLM JSON output.')
