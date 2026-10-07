import json
from collections import Counter

plan_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\real_amv\editing_plan.json'
inv_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\real_amv\clip_inventory.json'

with open(plan_path, 'r', encoding='utf-8') as f:
    plan = json.load(f)

with open(inv_path, 'r', encoding='utf-8') as f:
    inventory = json.load(f)

total_clips_available = len(inventory)
used_clip_paths = set()
used_clip_names = []
cuts = 0
effects = []

for action in plan.get('actions', []):
    if action.get('action') == 'import_footage':
        path = action.get('parameters', {}).get('file_path', '')
        if path.endswith(('.mp4', '.mov', '.avi', '.mkv')):
            used_clip_paths.add(path)
            used_clip_names.append(path.split('\\')[-1])
    elif action.get('action') == 'add_layer':
        pass
    elif action.get('action') == 'cut':
        cuts += 1
    elif action.get('action') == 'add_effect':
        effects.append(action.get('parameters', {}).get('effect_name'))

clips_used_count = len(used_clip_paths)
skipped_clips = total_clips_available - clips_used_count

name_counts = Counter(used_clip_names)
reused = [name for name, count in name_counts.items() if count > 1]

print(f"Total planned duration: {plan.get('duration', 0)}")
print(f"Number of source clips available: {total_clips_available}")
print(f"Number of clips used: {clips_used_count}")
print(f"Number skipped: {skipped_clips}")
print(f"Reused clips: {reused}")
print(f"Number of cuts: {cuts}")
print(f"Effects: {set(effects)}")
print(f"Notes: {plan.get('notes', '')}")
