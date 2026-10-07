"""AI chat bridge for AI_EDITOR using Google Gemini APIs."""

import os
from typing import Optional
from google import genai
from google.genai import types

from config.model_config import ModelConfig
from .chat import AIChatSession, ChatError


class AIChatProviderError(RuntimeError):
    """Raised when a Gemini chat request cannot be completed."""


class AIChatProvider:
    """Connect an AIChatSession to Google Gemini endpoints."""

    def __init__(
        self,
        config: Optional[ModelConfig] = None,
    ) -> None:
        self.config = config or ModelConfig.from_environment()

        # The user requested to use GOOGLE_API_KEY directly from environment
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            # Fallback to config if GOOGLE_API_KEY is not directly in env, 
            # though requirement says os.environ["GOOGLE_API_KEY"]
            api_key = os.getenv(self.config.api_key_env_var)

        if not api_key:
            raise AIChatProviderError(
                "API key environment variable GOOGLE_API_KEY is not set."
            )

        self.client = genai.Client(api_key=api_key)

        # Detect the strongest model if not explicitly configured
        self.model_name = self.config.model
        if self.model_name in ("detect", "auto", "gemini-auto", ""):
            self.model_name = self._detect_strongest_model()

    def _detect_strongest_model(self) -> str:
        """Detect the strongest available Gemini model."""
        try:
            models = self.client.models.list()
            model_names = [m.name for m in models]
            
            # Look for the strongest pro model available
            for target in [
                "models/gemini-2.5-pro",
                "models/gemini-1.5-pro",
                "models/gemini-2.0-pro-exp",
                "gemini-2.5-pro",
                "gemini-1.5-pro",
                "gemini-pro"
            ]:
                if any(target in name for name in model_names):
                    # Return the exact matching name from the API
                    for name in model_names:
                        if target in name:
                            return name
            
            # Fallback
            return "gemini-1.5-pro"
        except Exception as e:
            # If detection fails, fallback to standard pro
            return "gemini-1.5-pro"

    def send(
        self,
        session: AIChatSession,
        *,
        include_script: bool = True,
    ) -> str:
        """Send the current chat/PDF context to Gemini."""

        if not isinstance(session, AIChatSession):
            raise TypeError("session must be an AIChatSession.")

        context = session.build_context(
            include_script=include_script,
        )

        if not context.strip():
            raise ChatError("There is no chat message or PDF script to send.")

        system_prompt = (
            "You are the AI assistant inside AI_EDITOR. "
            "Understand the user's editing request and "
            "uploaded editing script. Do not directly "
            "control After Effects from this response. "
            "Return useful editing instructions that can "
            "later be converted into a structured editing plan."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=context,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=self.config.temperature,
                    max_output_tokens=self.config.max_tokens,
                    response_mime_type="application/json",
                )
            )
        except Exception as exc:
            raise AIChatProviderError(
                f"AI provider request failed: {exc}"
            ) from exc

        if not response.text:
            raise AIChatProviderError(
                "AI provider returned an empty response string."
            )

        response_text = response.text.strip()
        session.add_assistant_message(response_text)
        return response_text

