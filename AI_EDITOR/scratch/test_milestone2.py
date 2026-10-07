import time
import subprocess
import socket
from pywinauto.application import Application
import sys
import json

sys.path.insert(0, r'C:\Users\L.Thirumala Teja\AI_EDITOR')
from ae_automation.cep_runner import AECepRunner, AECepError

def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def test_milestone2():
    print('Killing AE to reload extension changes...')
    subprocess.run(['taskkill', '/F', '/IM', 'AfterFX.exe'], capture_output=True)
    time.sleep(3)
    
    print('Starting AE...')
    try:
        Application(backend='uia').start(r'C:\Program Files\Adobe\Adobe After Effects 2022\Support Files\AfterFX.exe')
    except Exception as e:
        print('Error starting AE:', e)
        return
        
    print('Waiting for CEP Extension server on port 8090 (max 60s)...')
    start_time = time.time()
    server_up = False
    while time.time() - start_time < 60:
        if check_port(8090):
            server_up = True
            break
        time.sleep(2)
        
    if not server_up:
        print('ERROR: CEP server did not start on port 8090. Did AutoVisible fail?')
        return
        
    print('Port 8090 is open! Node.js server is running.')
    runner = AECepRunner(port=8090)
    
    print('--- IMPORTING WAV ---')
    try:
        wav_res = runner.execute('import_footage', {
            'filepath': r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\fragment_proxy.wav'
        })
        print('WAV SUCCESS!')
        print(json.dumps(wav_res, indent=2))
    except Exception as e:
        print('WAV FAIL:', e)
        
    print('\n--- IMPORTING MP4 ---')
    try:
        mp4_res = runner.execute('import_footage', {
            'filepath': r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\Naruto_Sasuke_proxy.mp4'
        })
        print('MP4 SUCCESS!')
        print(json.dumps(mp4_res, indent=2))
    except Exception as e:
        print('MP4 FAIL:', e)

if __name__ == '__main__':
    test_milestone2()
