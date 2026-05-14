"""Shared LLM provider utilities.

Common helpers used by both ``llm_client.py`` (summarization) and
``llm_extraction.py`` (structured extraction) to avoid duplicated logic.
"""

import os
from typing import Optional


def clean_json_response(content: str) -> str:
    """Remove markdown code block markers from an LLM JSON response.

    Uses slicing (start/end checks) rather than ``.replace()`` so that
    backtick characters inside the actual JSON payload are preserved.
    """
    if not content:
        return content

    content = content.strip()

    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]

    if content.endswith("```"):
        content = content[:-3]

    return content.strip()


def resolve_api_key(
    provider: str,
    explicit_key: Optional[str] = None,
) -> Optional[str]:
    """Resolve an API key for a provider.

    Resolution order:
    1. Explicitly provided key
    2. ConfigManager (supports claude_desktop_config.json keys)
    3. Environment variable (OPENAI_API_KEY / ANTHROPIC_API_KEY / AZURE_OPENAI_API_KEY)

    Returns ``None`` if no key is configured.
    """
    if explicit_key:
        return explicit_key

    try:
        from ..config import get_config_manager
        key = get_config_manager().get_api_key(provider)
        if key:
            return key
    except Exception:
        pass

    env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "aoai": "AZURE_OPENAI_API_KEY",
    }
    env_var = env_map.get(provider)
    if env_var:
        return os.environ.get(env_var)
    return None


def resolve_base_url(
    provider: str,
    explicit_url: Optional[str] = None,
    *,
    ollama_default: str = "http://localhost:11434",
) -> Optional[str]:
    """Resolve a base URL for a provider from an explicit URL or environment.

    For Ollama, falls back to a configurable default.
    """
    if explicit_url:
        return explicit_url
    if provider == "aoai":
        return os.environ.get("AZURE_OPENAI_ENDPOINT")
    if provider == "ollama":
        return ollama_default
    return None
