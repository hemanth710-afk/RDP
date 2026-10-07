import os
import zipfile
import json
import subprocess
from pathlib import Path

# Paths
zip_path = r"C:\Users\L.Thirumala Teja\Downloads\Naruto_Sasuke_Fragment_Clips.zip"
song_path = r"C:\Users\L.Thirumala Teja\Downloads\fragment - slowed - slxughter.mp3"
extract_dir = Path(r"C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\real_amv\sources")
inventory_path = Path(r"C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\real_amv\clip_inventory.json")
script_path = Path(r"C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\real_amv\script.json")
ffprobe_path = r"C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\ffmpeg-bin\ffmpeg-master-latest-win64-gpl\bin\ffprobe.exe"

# 1. Create directories and extract ZIP
extract_dir.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(extract_dir)

# Ensure read-only properties
for file in extract_dir.rglob('*'):
    if file.is_file():
        os.chmod(file, 0o444)

# 2. Inventory building
inventory = []
clips_for_script = []

def probe_file(file_path):
    cmd = [
        ffprobe_path,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,r_frame_rate,duration",
        "-of", "json",
        str(file_path)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        if 'streams' in data and len(data['streams']) > 0:
            stream = data['streams'][0]
            fps_str = stream.get('r_frame_rate', '0/1')
            if '/' in fps_str:
                num, den = map(float, fps_str.split('/'))
                fps = num / den if den != 0 else 0
            else:
                fps = float(fps_str)
            return {
                "codec": stream.get("codec_name"),
                "width": stream.get("width"),
                "height": stream.get("height"),
                "fps": round(fps, 3),
                "duration": float(stream.get("duration", 0))
            }
    except Exception as e:
        pass
    return None

def probe_audio(file_path):
    cmd = [
        ffprobe_path,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(file_path)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        return float(data.get('format', {}).get('duration', 0))
    except Exception:
        return 0.0

for file in extract_dir.rglob('*'):
    if file.is_file() and file.suffix.lower() in ('.mp4', '.mov', '.avi', '.mkv'):
        info = probe_file(file)
        if info:
            inv_item = {
                "filename": file.name,
                "absolute_path": str(file.resolve()),
                "duration": info["duration"],
                "resolution": f"{info['width']}x{info['height']}",
                "fps": info["fps"],
                "codec": info["codec"]
            }
            inventory.append(inv_item)
            
            clips_for_script.append({
                "id": file.stem,
                "path": str(file.resolve()),
                "duration": info["duration"],
                "description": f"Extracted clip {file.name}"
            })

# Save inventory
with open(inventory_path, 'w', encoding='utf-8') as f:
    json.dump(inventory, f, indent=2)

# Save script
song_duration = probe_audio(song_path)

script_data = {
    "title": "Naruto vs Sasuke - Fragment",
    "song_path": song_path,
    "target_duration": song_duration,
    "width": 2160,
    "height": 3840,
    "frame_rate": 60.0,
    "mood": "Intense, action-packed, dramatic, slowed phonk, buildup to explosive climax",
    "editing_style": "Fast-paced action cuts with the beat, cinematic slowing for drops, dynamic zooms, vertical aspect ratio crop focusing on action",
    "special_requirements": "Use the strongest impact moments for drops. Sync hits with percussion and bass. Ensure the vertical 2160x3840 format keeps subjects centered.",
    "clips": clips_for_script
}

with open(script_path, 'w', encoding='utf-8') as f:
    json.dump(script_data, f, indent=2)

print(f"Inventory saved: {len(inventory)} clips.")
print(f"Song duration: {song_duration}")
print(f"Script saved to {script_path}")
