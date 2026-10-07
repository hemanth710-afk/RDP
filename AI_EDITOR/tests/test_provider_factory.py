import os
import unittest
from unittest.mock import patch

from config.model_config import ModelConfig
from models.provider_factory import (
    ProviderFactoryError,
    create_provider,
)


class TestProviderFactory(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("GOOGLE_API_KEY", None)
        os.environ.pop("CUSTOM_PROVIDER_KEY", None)

    @patch("interface.ai_chat.AIChatProvider")
    def test_gemini_provider_can_be_created(self, mock_provider):
        config = ModelConfig(provider="gemini", model="gemini-3.5-flash", api_key_env_var="GOOGLE_API_KEY")
        os.environ["GOOGLE_API_KEY"] = "test-secret"

        result = create_provider(config)

        self.assertIs(result, mock_provider.return_value)
        mock_provider.assert_called_once_with(config=config)

    @patch("interface.ai_chat.AIChatProvider")
    def test_configured_model_name_is_passed(self, mock_provider):
        os.environ["GOOGLE_API_KEY"] = "test-secret"
        config = ModelConfig(model="custom-model")
        create_provider(config)

        self.assertEqual(
            mock_provider.call_args.kwargs["config"].model,
            "custom-model",
        )

    @patch("interface.ai_chat.AIChatProvider")
    def test_api_key_environment_variable_name_is_resolved(self, mock_provider):
        os.environ["CUSTOM_PROVIDER_KEY"] = "custom-secret"
        config = ModelConfig(api_key_env_var="CUSTOM_PROVIDER_KEY")

        create_provider(config)

        self.assertEqual(
            mock_provider.call_args.kwargs["config"].api_key_env_var,
            "CUSTOM_PROVIDER_KEY",
        )

    def test_unsupported_provider_is_rejected(self):
        with self.assertRaises(ProviderFactoryError) as context:
            create_provider(ModelConfig(provider="unsupported"))

        self.assertIn("Unsupported model provider", str(context.exception))

    @patch("interface.ai_chat.AIChatProvider")
    def test_factory_makes_no_network_request(self, mock_provider):
        os.environ["GOOGLE_API_KEY"] = "test-secret"
        create_provider(ModelConfig())

        mock_provider.assert_called_once()
        self.assertFalse(
            any(
                call[0] and isinstance(call[0][0], str)
                and call[0][0].startswith(("http://", "https://"))
                for call in mock_provider.mock_calls
            )
        )

    @patch("interface.ai_chat.AIChatProvider")
    def test_api_key_is_not_exposed_by_factory_error_or_representation(
        self,
        mock_provider,
    ):
        secret = "super-secret-api-key"
        os.environ["GOOGLE_API_KEY"] = secret

        result = create_provider(ModelConfig())

        self.assertNotIn(secret, str(result))
        self.assertNotIn(secret, repr(result))
        self.assertNotIn(secret, str(ModelConfig()))

    def test_api_key_is_not_exposed_in_missing_key_error(self):
        with self.assertRaises(ProviderFactoryError) as context:
            create_provider(
                ModelConfig(api_key_env_var="CUSTOM_PROVIDER_KEY")
            )

        self.assertNotIn("super-secret-api-key", str(context.exception))


if __name__ == "__main__":
    unittest.main()

