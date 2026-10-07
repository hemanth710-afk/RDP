import os
import unittest
from unittest.mock import patch

from config.model_config import ModelConfig, ModelConfigurationError


class TestModelConfig(unittest.TestCase):
    def tearDown(self):
        for name in (
            "MODEL_PROVIDER",
            "MODEL_NAME",
            "API_KEY_ENV_VAR",
            "BASE_URL_ENV_VAR",
            "MODEL_REQUEST_TIMEOUT",
            "MODEL_TEMPERATURE",
            "MODEL_MAX_TOKENS",
        ):
            os.environ.pop(name, None)

    def test_default_configuration(self):
        config = ModelConfig()
        self.assertEqual(config.provider, "gemini")
        self.assertEqual(config.model, "gemini-3.5-flash")
        self.assertEqual(config.api_key_env_var, "GOOGLE_API_KEY")
        self.assertEqual(config.base_url_env_var, "GOOGLE_BASE_URL")
        self.assertEqual(config.request_timeout, 120.0)
        self.assertEqual(config.temperature, 0.2)
        self.assertEqual(config.max_tokens, 8192)

    def test_custom_provider(self):
        self.assertEqual(ModelConfig(provider="custom").provider, "custom")

    def test_custom_model(self):
        self.assertEqual(ModelConfig(model="custom-model").model, "custom-model")

    def test_custom_timeout(self):
        config = ModelConfig()
        self.assertEqual(config.provider, "gemini")
        self.assertEqual(config.model, "gemini-3.5-flash")
        self.assertEqual(config.api_key_env_var, "GOOGLE_API_KEY")
        self.assertEqual(config.base_url_env_var, "GOOGLE_BASE_URL")
        self.assertEqual(config.request_timeout, 120.0)
        self.assertEqual(config.temperature, 0.2)
        self.assertEqual(config.max_tokens, 8192)

    @patch.dict(
        os.environ,
        {
            "MODEL_PROVIDER": "gemini",
            "MODEL_NAME": "gemini-4-pro",
            "API_KEY_ENV_VAR": "TEST_API_KEY",
            "BASE_URL_ENV_VAR": "TEST_BASE_URL",
            "MODEL_REQUEST_TIMEOUT": "60.5",
            "MODEL_TEMPERATURE": "0.7",
            "MODEL_MAX_TOKENS": "1000",
        },
        clear=True,
    )
    def test_from_environment(self) -> None:
        """Test configuration creation from environment variables."""
        config = ModelConfig.from_environment()

        self.assertEqual(config.provider, "gemini")
        self.assertEqual(config.model, "gemini-4-pro")
        self.assertEqual(config.api_key_env_var, "TEST_API_KEY")
        self.assertEqual(config.base_url_env_var, "TEST_BASE_URL")
        self.assertEqual(config.request_timeout, 60.5)
        self.assertEqual(config.temperature, 0.7)
        self.assertEqual(config.max_tokens, 1000)

    def test_repr_does_not_contain_secrets(self) -> None:
        """Test representation explicitly to ensure no key values leak."""
        config = ModelConfig(api_key_env_var="GOOGLE_API_KEY")
        text = repr(config)
        self.assertIn("ModelConfig", text)
        self.assertIn("GOOGLE_API_KEY", text)

    def test_invalid_timeout_handling(self):
        with self.assertRaises(ModelConfigurationError):
            ModelConfig(request_timeout=0)

    def test_invalid_temperature_handling(self):
        with self.assertRaises(ModelConfigurationError):
            ModelConfig(temperature=2.1)

    def test_invalid_max_token_handling(self):
        with self.assertRaises(ModelConfigurationError):
            ModelConfig(max_tokens=0)

    def test_api_key_value_is_not_exposed_by_string_representation(self):
        secret = "super-secret-api-key"
        config = ModelConfig(api_key_env_var="ANTHROPIC_AUTH_TOKEN")
        text = str(config)
        self.assertNotIn(secret, text)
        self.assertIn("ANTHROPIC_AUTH_TOKEN", text)


if __name__ == "__main__":
    unittest.main()
