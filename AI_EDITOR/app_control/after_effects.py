import os
import subprocess


class AfterEffectsConfigurationError(Exception):
    """Raised when After Effects 2022 configuration is invalid."""


class AfterEffectsController:
    """Controller for launching the configured Adobe After Effects 2022."""

    ENV_VAR = "AI_EDITOR_AFTER_EFFECTS_2022_PATH"

    def __init__(self, executable_path=None):
        self.executable_path = (
            executable_path
            or os.getenv(self.ENV_VAR)
        )

        if not self.executable_path:
            raise AfterEffectsConfigurationError(
                "After Effects 2022 executable path is required."
            )

        if not os.path.isfile(self.executable_path):
            raise AfterEffectsConfigurationError(
                "Configured After Effects 2022 executable does not exist."
            )

    def launch(self):
        """Launch the configured After Effects 2022 executable."""
        return subprocess.Popen([self.executable_path])
