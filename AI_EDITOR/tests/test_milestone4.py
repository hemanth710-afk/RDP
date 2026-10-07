import os
import json
import pytest
import time
import subprocess
import socket
from pywinauto.application import Application

from brain.plan_parser import EditingPlanParser, PlanParserError
from ae_automation.cep_runner import AECepRunner, AECepError

def test_parser_save_project():
    parser = EditingPlanParser()
    payload = {
        "title": "Test Save",
        "duration": 10.0,
        "actions": [
            {
                "action": "save_project",
                "parameters": {
                    "project_path": "C:/test.aep"
                }
            }
        ]
    }
    plan = parser.parse(payload)
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "save_project"
    assert plan.actions[0].parameters["project_path"] == "C:/test.aep"

def test_parser_export_video():
    parser = EditingPlanParser()
    payload = {
        "title": "Test Export",
        "duration": 10.0,
        "actions": [
            {
                "action": "export_video",
                "parameters": {
                    "output_path": "C:/test.mp4",
                    "format": "mp4"
                }
            }
        ]
    }
    plan = parser.parse(payload)
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "export_video"
    assert plan.actions[0].parameters["output_path"] == "C:/test.mp4"
    assert plan.actions[0].parameters["format"] == "mp4"

def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

@pytest.mark.skipif(not os.environ.get("RUN_CEP_TESTS"), reason="Requires active AE GUI")
def test_milestone4_integration():
    # Restart AE to ensure clean state and reload extension
    subprocess.run(['taskkill', '/F', '/IM', 'AfterFX.exe'], capture_output=True)
    time.sleep(3)
    
    try:
        Application(backend='uia').start(r'C:\Program Files\Adobe\Adobe After Effects 2022\Support Files\AfterFX.exe')
    except Exception as e:
        pytest.fail(f"Failed to start AE: {e}")
        
    start_time = time.time()
    server_up = False
    while time.time() - start_time < 60:
        if check_port(8090):
            server_up = True
            break
        time.sleep(2)
        
    assert server_up, "CEP server did not start on port 8090"
    
    runner = AECepRunner(port=8090)
    
    # Missing parameters tests
    with pytest.raises(Exception):
        runner.execute("save_project", {})
        
    with pytest.raises(Exception):
        runner.execute("export_video", {})
        
    with pytest.raises(Exception):
        runner.execute("export_video", {"output_path": "C:/test.mov", "format": "mov"})
    
    # 0. create project
    runner.execute('create_project', {})
    
    # 1. create_composition (Milestone 4 Test Comp)
    runner.execute('create_composition', {
        'name': 'Milestone 4 Test Comp',
        'width': 1920,
        'height': 1080,
        'duration': 5.0,
        'frame_rate': 30.0
    })
    
    # 2. Add layer (MP4 Proxy)
    runner.execute('import_footage', {
        'filepath': r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\Naruto_Sasuke_proxy.mp4'
    })
    
    runner.execute('add_layer', {
        'composition_name': 'Milestone 4 Test Comp',
        'layer_name': 'Naruto Clip',
        'layer_type': 'footage',
        'footage_name': 'Naruto_Sasuke_proxy.mp4'
    })
    
    # 3. Save project
    aep_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\outputs\milestone4_test.aep'
    if os.path.exists(aep_path):
        os.remove(aep_path)
        
    save_res = runner.execute('save_project', {'project_path': aep_path})
    assert save_res['success'] is True
    assert save_res['operation'] == 'save_project'
    assert os.path.exists(aep_path)
    assert os.path.getsize(aep_path) > 0
    
    # 4. Export video
    mp4_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\outputs\milestone4_test.mp4'
    mov_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\outputs\milestone4_test.mov'
    avi_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\outputs\milestone4_test.avi'
    for p in [mp4_path, mov_path, avi_path]:
        if os.path.exists(p):
            os.remove(p)
    
    export_res = runner.execute('export_video', {'output_path': mp4_path, 'format': 'mp4'})
    assert export_res['success'] is True
    assert export_res['operation'] == 'export_video'
    
    # Wait for export to actually write to disk (AE render queue might be slightly async or lock the file)
    time.sleep(2)
    assert os.path.exists(mp4_path)
    assert os.path.getsize(mp4_path) > 0
