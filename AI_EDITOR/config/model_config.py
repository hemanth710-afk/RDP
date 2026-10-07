"""Model configuration for the AI_EDITOR model-provider layer."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


# Load environment variables from the project's .env file.
load_dotenv()


class ModelConfigurationError(ValueError):
    """Raised when model configuration contains an invalid value."""


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """Immutable configuration for the AI_EDITOR model provider."""

    provider: str = "gemini"
    model: str = "gemini-3.5-flash"
    api_key_env_var: str = "GOOGLE_API_KEY"
    base_url_env_var: str = "GOOGLE_BASE_URL"
    request_timeout: float = 120.0
    temperature: float = 0.2
    max_tokens: int = 8192

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ModelConfigurationError(
                "Provider name cannot be empty."
            )

        if not self.model.strip():
            raise ModelConfigurationError(
                "Model name cannot be empty."
            )

        if not self.api_key_env_var.strip():
            raise ModelConfigurationError(
                "API key environment-variable name cannot be empty."
            )

        if not self.base_url_env_var.strip():
            raise ModelConfigurationError(
                "Base URL environment-variable name cannot be empty."
            )

        if self.request_timeout <= 0:
            raise ModelConfigurationError(
                "Request timeout must be greater than zero."
            )

        if not 0.0 <= self.temperature <= 2.0:
            raise ModelConfigurationError(
                "Temperature must be between 0.0 and 2.0."
            )

        if self.max_tokens <= 0:
            raise ModelConfigurationError(
                "Max tokens must be greater than zero."
            )

    @classmethod
    def from_environment(cls) -> "ModelConfig":
        """Create configuration from environment variables."""

        return cls(
            provider=os.getenv(
                "MODEL_PROVIDER",
                "gemini",
            ),
            model=os.getenv(
                "MODEL_NAME",
                "gemini-3.5-flash",
            ),
            api_key_env_var=os.getenv(
                "API_KEY_ENV_VAR",
                "GOOGLE_API_KEY",
            ),
            base_url_env_var=os.getenv(
                "BASE_URL_ENV_VAR",
                "GOOGLE_BASE_URL",
            ),
            request_timeout=_read_float(
                "MODEL_REQUEST_TIMEOUT",
                120.0,
            ),
            temperature=_read_float(
                "MODEL_TEMPERATURE",
                0.2,
            ),
            max_tokens=_read_int(
                "MODEL_MAX_TOKENS",
                2048,
            ),
        )

    def __repr__(self) -> str:
        """Return a representation without secret values."""

        return (
            "ModelConfig("
            f"provider={self.provider!r}, "
            f"model={self.model!r}, "
            f"api_key_env_var={self.api_key_env_var!r}, "
            f"base_url_env_var={self.base_url_env_var!r}, "
            f"request_timeout={self.request_timeout!r}, "
            f"temperature={self.temperature!r}, "
            f"max_tokens={self.max_tokens!r})"
        )


def _read_float(name: str, default: float) -> float:
    """Read a finite floating-point environment value."""

    value = os.getenv(name)

    if value is None:
        return default

    try:
        result = float(value)
    except ValueError as exc:
        raise ModelConfigurationError(
            f"{name} must be a valid number."
        ) from exc

    if result != result or result in (
        float("inf"),
        float("-inf"),
    ):
        raise ModelConfigurationError(
            f"{name} must be finite."
        )

    return result


def _read_int(name: str, default: int) -> int:
    """Read an integer environment value."""

    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ModelConfigurationError(
            f"{name} must be a valid integer."
        ) from exc