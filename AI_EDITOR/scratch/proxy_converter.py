
import os
import subprocess
import json

ffmpeg_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\ffmpeg-bin\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe'
ffprobe_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\ffmpeg-bin\ffmpeg-master-latest-win64-gpl\bin\ffprobe.exe'

def get_media_info(file_path):
    cmd = [ffprobe_path, '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)

def convert_audio():
    src = r'C:\Users\L.Thirumala Teja\Downloads\fragment - slowed - slxughter.mp3'
    dst = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\fragment_proxy.wav'
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst): os.remove(dst)
    print('Converting audio...')
    subprocess.run([ffmpeg_path, '-i', src, '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', dst], check=True)
    print(f'Audio converted to: {dst}')
    
def convert_video():
    src = r'C:\Users\L.Thirumala Teja\Downloads\Naruto Vs Sasuke-2x-RIFE-RIFE4.0-120fps.mp4'
    dst = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\Naruto_Sasuke_proxy.mp4'
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst): os.remove(dst)
    print('Converting video...')
    # Standard H.264, 60fps, scale to 2160x3840 if needed, or keep original if already that or just force it for standardness
    # The prompt says: 2160x3840 if practical, 60 FPS, standard MP4, standard pixel format (yuv420p).
    # Since the original is an AMV, scaling it to 2160x3840 (vertical 4K) might stretch it. I'll use -vf scale=2160:3840:force_original_aspect_ratio=decrease,pad=2160:3840:(ow-iw)/2:(oh-ih)/2
    subprocess.run([ffmpeg_path, '-i', src, '-r', '60', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', dst], check=True)
    print(f'Video converted to: {dst}')

if __name__ == '__main__':
    convert_audio()
    convert_video()
    print('Proxy creation complete.')

