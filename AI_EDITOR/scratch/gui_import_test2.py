
import time
import subprocess
from pywinauto.application import Application
from pywinauto import Desktop
from pywinauto.keyboard import send_keys

def take_screenshot(name):
    import pyscreeze
    pyscreeze.screenshot(name)

def test_manual_import():
    print('Killing existing After Effects instances...')
    subprocess.run(['taskkill', '/F', '/IM', 'AfterFX.exe'], capture_output=True)
    time.sleep(2)
    
    print('Starting After Effects...')
    Application(backend='uia').start(r'C:\Program Files\Adobe\Adobe After Effects 2022\Support Files\AfterFX.exe')
    
    print('Waiting 20 seconds for After Effects to boot completely...')
    time.sleep(20)
    
    print('Finding main window...')
    main_win = None
    try:
        main_win = Desktop(backend='uia').window(title_re='.*Adobe After Effects.*')
        main_win.set_focus()
        print('Focused main window.')
    except Exception as e:
        print('Could not focus main window:', e)
        return
        
    time.sleep(2)
    print('Sending Ctrl+Alt+N (New Project)...')
    send_keys('^%n')
    time.sleep(2)
    
    print('Sending Ctrl+I (Import File)...')
    send_keys('^i')
    time.sleep(4)
    take_screenshot('scratch/dialog_open.png')
    
    try:
        import_dialog = Desktop(backend='uia').window(title='Import File')
        import_dialog.wait('visible', timeout=10)
        import_dialog.set_focus()
        print('Import dialog opened.')
    except Exception as e:
        print('Could not find Import File dialog:', e)
        return
        
    print('Entering WAV path...')
    wav_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\fragment_proxy.wav'
    send_keys(wav_path + '{ENTER}')
    
    print('Waiting 10 seconds to see if error pops up...')
    time.sleep(10)
    take_screenshot('scratch/after_wav_import.png')
    
    print('Sending Ctrl+I for MP4...')
    main_win.set_focus()
    send_keys('^i')
    time.sleep(4)
    
    try:
        import_dialog = Desktop(backend='uia').window(title='Import File')
        import_dialog.wait('visible', timeout=10)
        import_dialog.set_focus()
    except:
        print('Could not open second import dialog.')
        
    print('Entering MP4 path...')
    mp4_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\Naruto_Sasuke_proxy.mp4'
    send_keys(mp4_path + '{ENTER}')
    
    print('Waiting 10 seconds for MP4 import...')
    time.sleep(10)
    take_screenshot('scratch/after_mp4_import.png')
    print('Done.')

if __name__ == '__main__':
    test_manual_import()

