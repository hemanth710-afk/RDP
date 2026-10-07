
from dotenv import load_dotenv
load_dotenv('.env')
from ae_automation import AEAutomationCommands

def test_imports():
    commands = AEAutomationCommands()
    print('Creating project...')
    commands.create_project()
    
    print('Testing MP3 import...')
    try:
        mp3 = r'C:\Users\L.Thirumala Teja\Downloads\fragment - slowed - slxughter.mp3'
        res = commands.layers.import_footage(mp3)
        print(f'MP3 Success: {res}')
    except Exception as e:
        print(f'MP3 Failure: {e}')

    print('Testing MP4 import...')
    try:
        mp4 = r'C:\Users\L.Thirumala Teja\Downloads\Naruto Vs Sasuke-2x-RIFE-RIFE4.0-120fps.mp4'
        res = commands.layers.import_footage(mp4)
        print(f'MP4 Success: {res}')
    except Exception as e:
        print(f'MP4 Failure: {type(e).__name__} - {e}')

if __name__ == '__main__':
    test_imports()

