import json
with open('C:\\Users\\L.Thirumala Teja\\AI_EDITOR\\scratch\\real_amv\\editing_plan.json', 'r') as f:
    plan = json.load(f)

for action in plan['actions']:
    if action['action'] == 'add_layer':
        print(action)
