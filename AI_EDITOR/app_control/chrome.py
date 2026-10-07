import os
import subprocess


class ChromeConfigurationError(Exception):
    """Raised when Chrome configuration is invalid."""


class ChromeController:
    """Controller for launching Chrome with an existing Chrome profile."""

    CHROME_ENV_VAR = "AI_EDITOR_CHROME_PATH"
    USER_DATA_ENV_VAR = "AI_EDITOR_CHROME_USER_DATA"
    PROFILE_ENV_VAR = "AI_EDITOR_CHROME_PROFILE"

    def __init__(
        self,
        executable_path=None,
        user_data_directory=None,
        profile_directory=None,
    ):
        self.executable_path = (
            executable_path
            if executable_path is not None
            else os.getenv(self.CHROME_ENV_VAR)
        )

        self.user_data_directory = (
            user_data_directory
            if user_data_directory is not None
            else os.getenv(self.USER_DATA_ENV_VAR)
        )

        self.profile_directory = (
            profile_directory
            if profile_directory is not None
            else os.getenv(self.PROFILE_ENV_VAR)
        )

        if not self.executable_path:
            raise ChromeConfigurationError(
                "Chrome executable path is required."
            )

        if not os.path.isfile(self.executable_path):
            raise ChromeConfigurationError(
                "Configured Chrome executable does not exist."
            )

        if not self.user_data_directory:
            raise ChromeConfigurationError(
                "Chrome user-data directory is required."
            )

        if not os.path.isdir(self.user_data_directory):
            raise ChromeConfigurationError(
                "Configured Chrome user-data directory does not exist."
            )

        if not self.profile_directory:
            raise ChromeConfigurationError(
                "Chrome profile directory is required."
            )

    def launch(self):
        """Launch Chrome using the configured existing profile."""
        return subprocess.Popen(
            [
                self.executable_path,
                f"--user-data-dir={self.user_data_directory}",
                f"--profile-directory={self.profile_directory}",
            ]
        )