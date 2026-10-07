import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app_control.after_effects import (
    AfterEffectsConfigurationError,
    AfterEffectsController,
)
from app_control.chrome import (
    ChromeConfigurationError,
    ChromeController,
)
from app_control.controller import ApplicationController


class TestAfterEffectsController(unittest.TestCase):

    def test_can_be_created_with_explicit_path(self):
        with tempfile.NamedTemporaryFile(delete=False) as file:
            path = file.name

        try:
            controller = AfterEffectsController(path)
            self.assertEqual(controller.executable_path, path)
        finally:
            os.unlink(path)

    def test_reads_environment_variable(self):
        with tempfile.NamedTemporaryFile(delete=False) as file:
            path = file.name

        try:
            with patch.dict(
                os.environ,
                {"AI_EDITOR_AFTER_EFFECTS_2022_PATH": path},
            ):
                controller = AfterEffectsController()

            self.assertEqual(controller.executable_path, path)
        finally:
            os.unlink(path)

    def test_missing_executable_is_rejected(self):
        with self.assertRaises(AfterEffectsConfigurationError):
            AfterEffectsController(
                r"C:\does-not-exist\AfterFX.exe"
            )

    @patch("app_control.after_effects.subprocess.Popen")
    def test_launch_uses_configured_executable(self, mock_popen):
        with tempfile.NamedTemporaryFile(delete=False) as file:
            path = file.name

        try:
            controller = AfterEffectsController(path)
            controller.launch()

            mock_popen.assert_called_once_with([path])
        finally:
            os.unlink(path)

    @patch("app_control.after_effects.subprocess.Popen")
    def test_launch_does_not_use_shell(self, mock_popen):
        with tempfile.NamedTemporaryFile(delete=False) as file:
            path = file.name

        try:
            controller = AfterEffectsController(path)
            controller.launch()

            _, kwargs = mock_popen.call_args
            self.assertNotIn("shell", kwargs)
        finally:
            os.unlink(path)


class TestChromeController(unittest.TestCase):

    def _make_chrome_fixtures(self):
        """Create temporary fake Chrome executable and user-data directory."""
        fd, chrome_path = tempfile.mkstemp(suffix=".exe", prefix="fake_chrome_")
        os.close(fd)
        user_data_dir = tempfile.mkdtemp(prefix="chrome_user_data_")
        return chrome_path, user_data_dir

    def test_can_be_created_with_explicit_paths(self):
        chrome_path, user_data_dir = self._make_chrome_fixtures()
        profile = "TestProfile"

        try:
            controller = ChromeController(
                executable_path=chrome_path,
                user_data_directory=user_data_dir,
                profile_directory=profile,
            )

            self.assertEqual(
                controller.executable_path,
                chrome_path,
            )
            self.assertEqual(
                controller.user_data_directory,
                user_data_dir,
            )
            self.assertEqual(
                controller.profile_directory,
                profile,
            )
        finally:
            os.unlink(chrome_path)
            os.rmdir(user_data_dir)

    def test_reads_environment_configuration(self):
        chrome_path, user_data_dir = self._make_chrome_fixtures()
        profile = "TestProfile"

        try:
            with patch.dict(
                os.environ,
                {
                    "AI_EDITOR_CHROME_PATH": chrome_path,
                    "AI_EDITOR_CHROME_USER_DATA": user_data_dir,
                    "AI_EDITOR_CHROME_PROFILE": profile,
                },
            ):
                controller = ChromeController()

            self.assertEqual(
                controller.executable_path,
                chrome_path,
            )
            self.assertEqual(
                controller.user_data_directory,
                user_data_dir,
            )
            self.assertEqual(
                controller.profile_directory,
                profile,
            )
        finally:
            os.unlink(chrome_path)
            os.rmdir(user_data_dir)

    def test_missing_chrome_executable_is_rejected(self):
        user_data_dir = tempfile.mkdtemp(prefix="chrome_user_data_")

        try:
            with self.assertRaises(ChromeConfigurationError):
                ChromeController(
                    executable_path=r"C:\does-not-exist\chrome.exe",
                    user_data_directory=user_data_dir,
                    profile_directory="TestProfile",
                )
        finally:
            os.rmdir(user_data_dir)

    def test_missing_profile_directory_is_rejected(self):
        chrome_path, user_data_dir = self._make_chrome_fixtures()

        try:
            with self.assertRaises(ChromeConfigurationError):
                ChromeController(
                    executable_path=chrome_path,
                    user_data_directory=user_data_dir,
                    profile_directory="",
                )
        finally:
            os.unlink(chrome_path)
            os.rmdir(user_data_dir)

    def test_missing_user_data_directory_is_rejected(self):
        chrome_path, user_data_dir = self._make_chrome_fixtures()

        try:
            with self.assertRaises(ChromeConfigurationError):
                ChromeController(
                    executable_path=chrome_path,
                    user_data_directory="",
                    profile_directory="TestProfile",
                )
        finally:
            os.unlink(chrome_path)
            os.rmdir(user_data_dir)

    def test_nonexistent_user_data_directory_is_rejected(self):
        chrome_path, user_data_dir = self._make_chrome_fixtures()

        try:
            with self.assertRaises(ChromeConfigurationError):
                ChromeController(
                    executable_path=chrome_path,
                    user_data_directory=r"C:\does-not-exist\Chrome User Data",
                    profile_directory="TestProfile",
                )
        finally:
            os.unlink(chrome_path)
            os.rmdir(user_data_dir)

    def test_profile_directory_accepts_name_string(self):
        """ChromeController accepts a profile name such as 'Profile 6'."""
        chrome_path, user_data_dir = self._make_chrome_fixtures()

        try:
            controller = ChromeController(
                executable_path=chrome_path,
                user_data_directory=user_data_dir,
                profile_directory="Profile 6",
            )
            self.assertEqual(controller.profile_directory, "Profile 6")
        finally:
            os.unlink(chrome_path)
            os.rmdir(user_data_dir)

    @patch("app_control.chrome.subprocess.Popen")
    def test_launch_uses_chrome_executable(self, mock_popen):
        chrome_path, user_data_dir = self._make_chrome_fixtures()
        profile = "TestProfile"

        try:
            controller = ChromeController(
                executable_path=chrome_path,
                user_data_directory=user_data_dir,
                profile_directory=profile,
            )

            controller.launch()

            args = mock_popen.call_args.args[0]

            self.assertEqual(args[0], chrome_path)
        finally:
            os.unlink(chrome_path)
            os.rmdir(user_data_dir)

    @patch("app_control.chrome.subprocess.Popen")
    def test_launch_uses_user_data_dir_argument(self, mock_popen):
        chrome_path, user_data_dir = self._make_chrome_fixtures()
        profile = "TestProfile"

        try:
            controller = ChromeController(
                executable_path=chrome_path,
                user_data_directory=user_data_dir,
                profile_directory=profile,
            )

            controller.launch()

            args = mock_popen.call_args.args[0]

            self.assertIn(
                f"--user-data-dir={user_data_dir}",
                args,
            )
        finally:
            os.unlink(chrome_path)
            os.rmdir(user_data_dir)

    @patch("app_control.chrome.subprocess.Popen")
    def test_launch_uses_profile_directory_argument(self, mock_popen):
        chrome_path, user_data_dir = self._make_chrome_fixtures()
        profile = "TestProfile"

        try:
            controller = ChromeController(
                executable_path=chrome_path,
                user_data_directory=user_data_dir,
                profile_directory=profile,
            )

            controller.launch()

            args = mock_popen.call_args.args[0]

            self.assertIn(
                f"--profile-directory={profile}",
                args,
            )
        finally:
            os.unlink(chrome_path)
            os.rmdir(user_data_dir)

    @patch("app_control.chrome.subprocess.Popen")
    def test_launch_command_structure(self, mock_popen):
        """Verify the exact command list structure passed to Popen."""
        chrome_path, user_data_dir = self._make_chrome_fixtures()
        profile = "Profile 6"

        try:
            controller = ChromeController(
                executable_path=chrome_path,
                user_data_directory=user_data_dir,
                profile_directory=profile,
            )

            controller.launch()

            expected = [
                chrome_path,
                f"--user-data-dir={user_data_dir}",
                f"--profile-directory={profile}",
            ]

            mock_popen.assert_called_once_with(expected)
        finally:
            os.unlink(chrome_path)
            os.rmdir(user_data_dir)

    @patch("app_control.chrome.subprocess.Popen")
    def test_chrome_launch_does_not_use_shell(self, mock_popen):
        chrome_path, user_data_dir = self._make_chrome_fixtures()
        profile = "TestProfile"

        try:
            controller = ChromeController(
                executable_path=chrome_path,
                user_data_directory=user_data_dir,
                profile_directory=profile,
            )

            controller.launch()

            _, kwargs = mock_popen.call_args
            self.assertNotIn("shell", kwargs)
        finally:
            os.unlink(chrome_path)
            os.rmdir(user_data_dir)

    @patch("app_control.chrome.subprocess.Popen")
    def test_no_google_credentials_are_passed(self, mock_popen):
        chrome_path, user_data_dir = self._make_chrome_fixtures()
        profile = "TestProfile"

        try:
            controller = ChromeController(
                executable_path=chrome_path,
                user_data_directory=user_data_dir,
                profile_directory=profile,
            )

            controller.launch()

            args = mock_popen.call_args.args[0]
            command = " ".join(args)

            self.assertNotIn("password", command.lower())
            self.assertNotIn("passwd", command.lower())
            self.assertNotIn("token", command.lower())
            self.assertNotIn("credential", command.lower())
            self.assertNotIn("auth", command.lower())
            self.assertNotIn("@gmail", command.lower())
            self.assertNotIn("@google", command.lower())
        finally:
            os.unlink(chrome_path)
            os.rmdir(user_data_dir)


class TestApplicationController(unittest.TestCase):

    def test_can_launch_after_effects(self):
        after_effects = MagicMock()
        controller = ApplicationController(
            after_effects=after_effects
        )

        controller.launch_after_effects()

        after_effects.launch.assert_called_once_with()

    def test_can_launch_chrome(self):
        chrome = MagicMock()
        controller = ApplicationController(
            chrome=chrome
        )

        controller.launch_chrome()

        chrome.launch.assert_called_once_with()

    def test_missing_after_effects_controller_is_rejected(self):
        controller = ApplicationController()

        with self.assertRaises(RuntimeError):
            controller.launch_after_effects()

    def test_missing_chrome_controller_is_rejected(self):
        controller = ApplicationController()

        with self.assertRaises(RuntimeError):
            controller.launch_chrome()


if __name__ == "__main__":
    unittest.main()