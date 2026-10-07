import re

with open('tests/test_ae_automation.py', 'r') as f:
    text = f.read()

text = text.replace(', mock_read: MagicMock, mock_exists: MagicMock', '')
text = text.replace('@patch("ae_automation.script_runner.Path.exists", return_value=True)\n    @patch("ae_automation.script_runner.Path.read_text", return_value="success=true")\n    ', '')
text = text.replace('@patch("ae_automation.script_runner.Path.exists", return_value=False)\n    ', '')
text = text.replace('@patch("ae_automation.script_runner.Path.exists", return_value=True)\n    @patch("ae_automation.script_runner.Path.read_text", return_value="output_text")\n    ', '')

setup_code = '''    def setUp(self) -> None:
        self.fake_exe = _make_fake_exe()
        self.runner = AEScriptRunner(executable_path=self.fake_exe)
        self.patcher1 = patch('ae_automation.script_runner.Path.exists', return_value=True)
        self.patcher2 = patch('ae_automation.script_runner.Path.read_text', return_value='success=true')
        self.mock_exists = self.patcher1.start()
        self.mock_read = self.patcher2.start()

    def tearDown(self) -> None:
        self.patcher1.stop()
        self.patcher2.stop()
        try:
            os.unlink(self.fake_exe)
        except OSError:
            pass'''

text = re.sub(r'    def setUp.*?except OSError:\s+pass', setup_code, text, flags=re.DOTALL)

text = text.replace('def test_returns_stdout(self, mock_run: MagicMock) -> None:', '''def test_returns_stdout(self, mock_run: MagicMock) -> None:
        self.mock_read.return_value = "output_text"''')

text = text.replace('def test_converts_subprocess_failure_to_ae_script_error(self, mock_run: MagicMock) -> None:', '''def test_converts_subprocess_failure_to_ae_script_error(self, mock_run: MagicMock) -> None:
        self.mock_exists.return_value = False''')

text = text.replace('def test_converts_os_error_to_ae_script_error(self, mock_run: MagicMock) -> None:', '''def test_converts_os_error_to_ae_script_error(self, mock_run: MagicMock) -> None:
        self.mock_exists.return_value = False''')

with open('tests/test_ae_automation.py', 'w') as f:
    f.write(text)

print("Tests patched!")
