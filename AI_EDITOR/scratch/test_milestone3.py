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

def test_milestone3():
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
        print('ERROR: CEP server did not start on port 8090.')
        return
        
    print('Port 8090 is open! Node.js server is running.')
    runner = AECepRunner(port=8090)
    
    # 0. Clean Project
    print('\n--- CREATE PROJECT ---')
    print(json.dumps(runner.execute('create_project', {}), indent=2))
    
    # 1. Import Footage
    print('\n--- IMPORT FOOTAGE ---')
    print(json.dumps(runner.execute('import_footage', {
        'filepath': r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\Naruto_Sasuke_proxy.mp4'
    }), indent=2))
    
    # 2. Create Composition
    print('\n--- CREATE COMPOSITION ---')
    print(json.dumps(runner.execute('create_composition', {
        'name': 'Milestone 3 Test Comp',
        'width': 1920,
        'height': 1080,
        'duration': 10.0,
        'frame_rate': 30.0
    }), indent=2))
    
    # 3. Add Layer (Null)
    print('\n--- ADD NULL LAYER ---')
    print(json.dumps(runner.execute('add_layer', {
        'composition_name': 'Milestone 3 Test Comp',
        'layer_name': 'Controller Null',
        'layer_type': 'null'
    }), indent=2))
    
    # 4. Add Layer (Footage)
    print('\n--- ADD FOOTAGE LAYER ---')
    print(json.dumps(runner.execute('add_layer', {
        'composition_name': 'Milestone 3 Test Comp',
        'layer_name': 'Naruto Clip',
        'layer_type': 'footage',
        'footage_name': 'Naruto_Sasuke_proxy.mp4'
    }), indent=2))
    
    # 5. Set Parent
    print('\n--- SET PARENT ---')
    print(json.dumps(runner.execute('set_parent', {
        'composition_name': 'Milestone 3 Test Comp',
        'child_layer_name': 'Naruto Clip',
        'parent_layer_name': 'Controller Null'
    }), indent=2))
    
    # 6. Set Keyframe (Transform -> Scale)
    print('\n--- SET KEYFRAME ---')
    print(json.dumps(runner.execute('set_keyframe', {
        'composition_name': 'Milestone 3 Test Comp',
        'layer_name': 'Controller Null',
        'property_name': 'transform/Scale',
        'time': 1.0,
        'value': [150.0, 150.0, 100.0]
    }), indent=2))

if __name__ == '__main__':
    test_milestone3()
