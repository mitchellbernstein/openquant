"""LLM provider configuration for OpenQuant agent.

Supports multiple LLM backends via litellm:
  - OpenAI (OPENAI_API_KEY)
  - Anthropic (ANTHROPIC_API_KEY)
  - OpenRouter (OPENROUTER_API_KEY)
  - Ollama local (OLLAMA_HOST)

Model strings follow litellm convention: "provider/model-name"
e.g. "openai/gpt-4o-mini", "anthropic/claude-sonnet-4"
"""

from __future__ import annotations

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ── Default model selection logic ──────────────────────────────────────────

def get_default_model() -> str:
    """Select the best available model based on env vars.

    Priority:
      1. OPENAI_API_KEY   -> openai/gpt-4o-mini
      2. ANTHROPIC_API_KEY -> anthropic/claude-sonnet-4
      3. OPENROUTER_API_KEY -> openrouter/openai/gpt-4o-mini
      4. OLLAMA_HOST       -> ollama/llama3
      5. fallback           -> openai/gpt-4o-mini (will error without key)
    """
    if os.environ.get("OPENAI_API_KEY"):
        return "openai/gpt-4o-mini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic/claude-sonnet-4"
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter/openai/gpt-4o-mini"
    if os.environ.get("OLLAMA_HOST"):
        return "ollama/llama3"
    return "openai/gpt-4o-mini"


def configure_litellm() -> None:
    """Configure litellm with environment variables.

    Sets up API keys and base URLs from environment.
    """
    try:
        import litellm

        # Suppress litellm's noisy logs
        litellm.suppress_debug_info = True

        # OpenRouter configuration
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if openrouter_key:
            os.environ.setdefault("OPENROUTER_API_KEY", openrouter_key)

        # Ollama configuration
        ollama_host = os.environ.get("OLLAMA_HOST")
        if ollama_host:
            os.environ.setdefault("OLLAMA_API_BASE", ollama_host)

        logger.debug("litellm configured successfully")
    except ImportError:
        logger.warning("litellm not installed — agent features will be limited")


def get_model_info(model: str) -> dict:
    """Get metadata about a model string.

    Returns dict with provider, model_name, supports_tools, supports_vision.
    """
    parts = model.split("/", 1)
    provider = parts[0] if len(parts) > 1 else "unknown"
    model_name = parts[1] if len(parts) > 1 else model

    tool_capable = {
        "openai", "anthropic", "openrouter", "ollama",
    }

    return {
        "provider": provider,
        "model_name": model_name,
        "supports_tools": provider in tool_capable,
        "supports_vision": provider in {"openai", "anthropic", "openrouter"},
    }
