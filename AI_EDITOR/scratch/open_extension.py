
import time
import sys
from pywinauto import Desktop
from pywinauto.keyboard import send_keys

def open_ext():
    print('Finding AE window...')
    try:
        main_win = Desktop(backend='uia').window(title_re='.*Adobe After Effects.*')
        main_win.set_focus()
        print('Focused AE main window.')
    except Exception as e:
        print('Could not focus AE:', e)
        return
        
    time.sleep(1)
    print('Sending Alt+W...')
    send_keys('%w')
    time.sleep(1)
    
    print('Navigating to Extensions...')
    # Depending on AE version, typing 'Extensions' might not work directly if it's not a standard menu item,
    # but let's try standard menu navigation.
    send_keys('ext{RIGHT}')
    time.sleep(1)
    
    print('Selecting AI_EDITOR Bridge...')
    send_keys('ai{ENTER}')
    print('Keys sent.')

if __name__ == '__main__':
    open_ext()

