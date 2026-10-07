
import json
from pathlib import Path

plan_path = Path('scratch/human_editor_test/editing_plan.json')
with open(plan_path, 'r', encoding='utf-8') as f:
    plan_data = json.load(f)

for action in plan_data.get('actions', []):
    if action['action'] == 'add_layer':
        lt = action['parameters'].get('layer_type')
        if lt in ('audio', 'video'):
            layer_name = action['parameters'].get('layer_name')
            print(f'Changing layer_type {lt} -> footage for {layer_name}')
            action['parameters']['layer_type'] = 'footage'

with open(plan_path, 'w', encoding='utf-8') as f:
    json.dump(plan_data, f, indent=2)

print('Plan updated successfully.')

