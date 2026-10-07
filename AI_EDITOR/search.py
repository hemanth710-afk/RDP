import os
import re
import json

terms = re.compile(r'Claude|Anthropic|LitAI|AgentRouter|AEScriptRunner', re.IGNORECASE)
results = []
for root, dirs, files in os.walk('.'):
    if '.venv' in dirs: dirs.remove('.venv')
    if '.git' in dirs: dirs.remove('.git')
    for file in files:
        if file.endswith(('.py', '.md', '.txt', '.json')):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        if terms.search(line):
                            results.append({'Path': path, 'LineNumber': i+1, 'Line': line.strip()})
            except Exception:
                pass
print(json.dumps(results, indent=2))
