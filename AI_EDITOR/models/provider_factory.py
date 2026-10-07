"""Factory for creating configured model providers."""

from __future__ import annotations

import os
from typing import Any

from config.model_config import ModelConfig, ModelConfigurationError


class ProviderFactoryError(ModelConfigurationError):
    """Raised when a configured model provider cannot be created."""


def create_provider(config: ModelConfig) -> Any:
    """Create the concrete provider selected by *config*.

    The factory resolves the configured API-key environment variable at
    creation time and passes the resulting secret directly to the provider.
    No API requests are performed here.
    """
    provider_name = config.provider.strip().lower()

    if provider_name in ("gemini", "google-genai"):
        api_key = os.getenv(config.api_key_env_var) or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ProviderFactoryError(
                f"API key environment variable {config.api_key_env_var!r} "
                "is not set."
            )
        from interface.ai_chat import AIChatProvider
        return AIChatProvider(config=config)

    raise ProviderFactoryError(
        f"Unsupported model provider: {config.provider!r}."
    )
