
import time
import subprocess
from pywinauto.application import Application
from pywinauto import Desktop
from pywinauto.keyboard import send_keys

def test_manual_import():
    print('Killing existing After Effects instances...')
    subprocess.run(['taskkill', '/F', '/IM', 'AfterFX.exe'], capture_output=True)
    time.sleep(2)
    
    print('Starting After Effects...')
    app = Application(backend='uia').start(r'C:\Program Files\Adobe\Adobe After Effects 2022\Support Files\AfterFX.exe')
    
    print('Waiting for After Effects main window...')
    # Wait for the main window (could be 'Adobe After Effects 2022 - Untitled Project.aep *')
    main_win = None
    for _ in range(30):
        try:
            # Find any window containing 'Adobe After Effects'
            windows = Desktop(backend='uia').windows(title_re='.*Adobe After Effects.*')
            for w in windows:
                if w.window_text().startswith('Adobe After Effects'):
                    main_win = w
                    break
            if main_win:
                break
        except:
            pass
        time.sleep(1)
        
    if not main_win:
        print('Could not find After Effects window.')
        return
        
    print(f'Found window: {main_win.window_text()}')
    main_win.set_focus()
    time.sleep(2)
    
    print('Sending Ctrl+Alt+N (New Project)...')
    send_keys('^%n')
    time.sleep(2)
    
    print('Sending Ctrl+I (Import File)...')
    send_keys('^i')
    time.sleep(3)
    
    import_dialog = None
    try:
        import_dialog = main_win.child_window(title='Import File', control_type='Window')
        import_dialog.wait('visible', timeout=10)
        print('Import dialog opened.')
    except Exception as e:
        print('Could not find Import File dialog:', e)
        return
        
    print('Entering WAV path...')
    wav_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\fragment_proxy.wav'
    send_keys(wav_path + '{ENTER}')
    
    print('Waiting to see what happens after WAV import...')
    time.sleep(5)
    
    # Check for any error dialogs
    error_dialogs = main_win.children(control_type='Window')
    for d in error_dialogs:
        print(f'Possible dialog found: {d.window_text()}')
        # Print all text in dialog
        for child in d.descendants(control_type='Text'):
            print(f'  Text: {child.window_text()}')
            
    print('Sending Ctrl+I for MP4...')
    send_keys('^i')
    time.sleep(3)
    try:
        import_dialog = main_win.child_window(title='Import File', control_type='Window')
        import_dialog.wait('visible', timeout=10)
    except:
        pass
    print('Entering MP4 path...')
    mp4_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\Naruto_Sasuke_proxy.mp4'
    send_keys(mp4_path + '{ENTER}')
    
    print('Waiting 10 seconds for MP4 import...')
    time.sleep(10)
    
    error_dialogs = main_win.children(control_type='Window')
    for d in error_dialogs:
        print(f'Possible dialog found: {d.window_text()}')
        for child in d.descendants(control_type='Text'):
            print(f'  Text: {child.window_text()}')
            
if __name__ == '__main__':
    test_manual_import()

