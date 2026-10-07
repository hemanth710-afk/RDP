
import time
import subprocess
import socket
from pywinauto.application import Application
import sys

sys.path.insert(0, r'C:\Users\L.Thirumala Teja\AI_EDITOR')
from ae_automation.cep_runner import AECepRunner, AECepError

def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def test_full():
    print('Starting After Effects...')
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
        # Let's try sending keys to open it manually as a fallback
        print('Attempting to force open the extension via UI...')
        try:
            from pywinauto import Desktop
            from pywinauto.keyboard import send_keys
            main_win = Desktop(backend='uia').window(title_re='.*Adobe After Effects.*')
            main_win.set_focus()
            time.sleep(1)
            send_keys('%w')
            time.sleep(1)
            send_keys('{UP}{UP}{UP}{RIGHT}{ENTER}')
            time.sleep(10)
        except Exception as e:
            print('UI fallback failed:', e)
            return
            
        if not check_port(8090):
            print('ERROR: Still no server on port 8090.')
            return
        
    print('Port 8090 is open! Node.js server is running.')
    print('Sending create_project command...')
    runner = AECepRunner(port=8090)
    try:
        response = runner.execute('create_project', {})
        import json
        print('SUCCESS!')
        print(json.dumps(response, indent=2))
    except Exception as e:
        print('Failed to execute command:', e)

if __name__ == '__main__':
    test_full()

