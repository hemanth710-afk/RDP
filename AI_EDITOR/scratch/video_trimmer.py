import json
import os
from pathlib import Path
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips

def main():
    state_dir = Path("scratch/amv_test_state")
    plan_path = state_dir / "editing_plan.json"
    
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
        
    video_path = plan["source_files"][1]
    if video_path == "sasuke_fight":
        video_path = r"C:\Users\L.Thirumala Teja\Downloads\Naruto Vs Sasuke-2x-RIFE-RIFE4.0-120fps.mp4"
        
    audio_path = r"C:\Users\L.Thirumala Teja\Downloads\fragment - slowed - slxughter.mp3"
    
    print(f"Loading video: {video_path}")
    source_video = VideoFileClip(video_path)
    
    print(f"Loading audio: {audio_path}")
    source_audio = AudioFileClip(audio_path)
    
    clips = []
    
    # Extract cuts from the plan
    # Each cut action looks like:
    # {"action": "cut", "parameters": {"layer_name": "clip_1", "timeline_start": 0.0, "timeline_end": 2.5, "source_start": 0.0}}
    cut_actions = [a for a in plan["actions"] if a["action"] == "cut"]
    
    # Sort cuts by their timeline_start to assemble in order
    cut_actions.sort(key=lambda x: x["parameters"]["timeline_start"])
    
    for action in cut_actions:
        params = action["parameters"]
        t_start = params["timeline_start"]
        t_end = params["timeline_end"]
        s_start = params["source_start"]
        
        duration = t_end - t_start
        s_end = s_start + duration
        
        print(f"Cutting from source {s_start}s to {s_end}s (for timeline {t_start}s to {t_end}s)")
        clip = source_video.subclipped(s_start, s_end)
        clips.append(clip)
        
    print(f"Concatenating {len(clips)} clips...")
    final_video = concatenate_videoclips(clips)
    
    print("Trimming audio and setting to final video...")
    final_audio = source_audio.subclipped(0, final_video.duration)
    final_video = final_video.with_audio(final_audio)
    
    output_path = Path("scratch/trimmed_amv.mp4")
    print(f"Exporting to {output_path}...")
    
    final_video.write_videofile(
        str(output_path),
        fps=60,
        codec="libx264",
        audio_codec="aac",
        logger="bar"
    )
    
    print("Done!")

if __name__ == "__main__":
    main()
