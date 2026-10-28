"""Fail-closed OpenRouter free-only model selection (no network, no credentials).

Use only with independently fetched, current model metadata. This module does
not activate provider access or change Hermes/JCode configuration.
"""
from decimal import Decimal, InvalidOperation

class NoFreeModel(RuntimeError):
    pass

def _zero(value):
    try:
        return not isinstance(value, (bool, list, dict)) and value is not None and Decimal(str(value)).is_finite() and Decimal(str(value)) == 0
    except (InvalidOperation, ValueError, TypeError):
        return False

def eligible(model, *, require_tools=True):
    if not isinstance(model, dict):
        return False
    identifier = model.get('id', '')
    pricing = model.get('pricing')
    if not isinstance(identifier, str) or not identifier.endswith(':free'):
        return False
    if not isinstance(pricing, dict) or not {'prompt','completion'}.issubset(pricing) or not all(k in {'prompt','completion','request','image','web_search','internal_reasoning','input_cache_read','input_cache_write'} and _zero(v) for k,v in pricing.items()):
        return False
    if require_tools and (not isinstance(model.get('supported_parameters'), list) or any(not isinstance(x,str) for x in model['supported_parameters']) or 'tools' not in model['supported_parameters']):
        return False
    return True

def select_free_models(catalog, *, require_tools=True):
    """Return free model IDs in catalog order, or fail closed."""
    if not isinstance(catalog, list):
        raise ValueError('Expected a verified list of current model metadata')
    ids = list(dict.fromkeys(m['id'] for m in catalog if eligible(m, require_tools=require_tools)))
    if not ids:
        raise NoFreeModel('No verified free models available; no paid fallback permitted')
    return ids
