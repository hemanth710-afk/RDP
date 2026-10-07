import time
import subprocess
from pywinauto.application import Application
from pywinauto import Desktop
from pywinauto.keyboard import send_keys
import sys

# Import our new AECepRunner
sys.path.insert(0, r"C:\Users\L.Thirumala Teja\AI_EDITOR")
from ae_automation.cep_runner import AECepRunner, AECepError

def run_milestone1():
    print("Killing existing AE instances...")
    subprocess.run(['taskkill', '/F', '/IM', 'AfterFX.exe'], capture_output=True)
    time.sleep(2)
    
    print("Starting AE normally...")
    Application(backend='uia').start(r'C:\Program Files\Adobe\Adobe After Effects 2022\Support Files\AfterFX.exe')
    
    print("Waiting 20 seconds for AE to boot...")
    time.sleep(20)
    
    try:
        main_win = Desktop(backend='uia').window(title_re='.*Adobe After Effects.*')
        main_win.set_focus()
        print("Focused AE main window.")
    except Exception as e:
        print(f"Could not focus main window: {e}")
        return

    # To open an extension via keyboard in AE:
    # Alt+W (Window), down arrow to Extensions, right arrow, then enter.
    # But this is brittle. A better way in AE is often to use the search help, or since it's a test,
    # let's try the keyboard navigation: Alt+W -> up arrow (usually brings you to bottom where Extensions is)
    print("Attempting to open AI_EDITOR Bridge panel via UI automation...")
    send_keys('%w')  # Alt+W for Window menu
    time.sleep(1)
    send_keys('{UP}{UP}{UP}{RIGHT}{ENTER}') # Navigate to Extensions and hit Enter
    # Depending on installed extensions, it might need specific targeting.
    
    print("Waiting 10 seconds for the CEP panel and Node.js server to start...")
    time.sleep(10)
    
    print("Sending create_project command to localhost:8090...")
    runner = AECepRunner()
    try:
        response = runner.execute("create_project", {})
        print("Success!")
        print("Response received:")
        print(response)
    except AECepError as e:
        print(f"Test Failed: {e}")

if __name__ == "__main__":
    run_milestone1()
