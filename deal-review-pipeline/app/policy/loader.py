from __future__ import annotations
import json
from pathlib import Path
import fitz
from app.models.schemas import Policy

class PolicyValidationError(ValueError): pass

def load_policy(path: str) -> Policy:
    p = Path(path)
    if p.suffix.lower() == '.json':
        data = json.loads(p.read_text(encoding='utf-8'))
    elif p.suffix.lower() == '.docx':
        raise PolicyValidationError(
            "DOCX policy files are not supported in this environment. "
            "Please upload the compliance policy as JSON or PDF."
        )
    elif p.suffix.lower() == '.pdf':
        doc = fitz.open(str(p))
        text = '\n'.join(page.get_text() for page in doc)
        data = normalize_policy_text(text)
    else:
        raise PolicyValidationError(f'Unsupported policy format: {p.suffix}')
    try:
        return Policy.model_validate(data)
    except Exception as exc:
        raise PolicyValidationError(f'Policy schema validation failed: {exc}') from exc

def normalize_policy_text(text: str) -> dict:
    # PDF/DOCX normalization is intentionally conservative. A policy PDF/DOCX can be
    # normalized by the LLM adapter in the workflow; this function handles JSON-like
    # content if present and otherwise raises a useful validation error.
    start, end = text.find('{'), text.rfind('}')
    if start >= 0 and end > start:
        try: return json.loads(text[start:end+1])
        except json.JSONDecodeError: pass
    raise PolicyValidationError('PDF/DOCX policy needs LLM normalization into the standardized JSON policy schema.')
