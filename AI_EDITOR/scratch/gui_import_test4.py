
import time
import subprocess
from pywinauto.application import Application
from pywinauto import Desktop
from pywinauto.keyboard import send_keys

def test_manual_import():
    print('Killing existing AE instances...')
    subprocess.run(['taskkill', '/F', '/IM', 'AfterFX.exe'], capture_output=True)
    time.sleep(2)
    
    print('Starting AE...')
    Application(backend='uia').start(r'C:\Program Files\Adobe\Adobe After Effects 2022\Support Files\AfterFX.exe')
    
    print('Waiting 20 seconds for AE to boot...')
    time.sleep(20)
    
    main_win = None
    try:
        main_win = Desktop(backend='uia').window(title_re='.*Adobe After Effects.*')
        main_win.set_focus()
        print('Focused main window.')
    except:
        print('Could not focus main window.')
        return
        
    time.sleep(1)
    print('Creating New Project...')
    send_keys('^%n')
    time.sleep(2)
    
    print('Opening Import File dialog...')
    send_keys('^i')
    time.sleep(3)
    
    try:
        import_dialog = Desktop(backend='uia').window(title='Import File')
        import_dialog.set_focus()
        print('Import dialog opened for WAV.')
    except:
        print('Could not open first import dialog.')
        return
        
    wav_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\fragment_proxy.wav'
    send_keys(wav_path + '{ENTER}')
    time.sleep(5)
    
    main_win.set_focus()
    print('Opening Import File dialog for MP4...')
    send_keys('^i')
    time.sleep(3)
    
    try:
        import_dialog = Desktop(backend='uia').window(title='Import File')
        import_dialog.set_focus()
        print('Import dialog opened for MP4.')
    except:
        print('Could not open second import dialog.')
        return
        
    mp4_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\Naruto_Sasuke_proxy.mp4'
    send_keys(mp4_path + '{ENTER}')
    time.sleep(5)
    
    print('Done!')

if __name__ == '__main__':
    test_manual_import()

