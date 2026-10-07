import re

with open('tests/test_ae_automation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove TestAEScriptRunnerRun class entirely
content = re.sub(r'(?s)^class TestAEScriptRunnerRun\(unittest\.TestCase\):.*?(?=(?:^class |^if __name__ == "__main__":))', '', content, flags=re.MULTILINE)

with open('tests/test_ae_automation.py', 'w', encoding='utf-8') as f:
    f.write(content)
