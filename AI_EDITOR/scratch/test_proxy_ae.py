
from dotenv import load_dotenv
load_dotenv('.env')
from ae_automation import AEAutomationCommands

def test_proxies():
    commands = AEAutomationCommands()
    
    print('1. Creating project...')
    res = commands.create_project()
    print(res)
    
    print('2. Importing WAV proxy...')
    wav_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\fragment_proxy.wav'
    wav_res = commands.layers.import_footage(wav_path)
    print('WAV imported:', wav_res['footage']['name'])
    
    print('3. Importing MP4 proxy...')
    mp4_path = r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\human_editor_test\media\Naruto_Sasuke_proxy.mp4'
    mp4_res = commands.layers.import_footage(mp4_path)
    print('MP4 imported:', mp4_res['footage']['name'])
    
    print('4. Creating composition...')
    comp_res = commands.layers.create_composition('Test Comp', 1920, 1080, 60.0, 10.0)
    print('Comp created:', comp_res['comp']['name'])
    
    print('5. Adding imported media...')
    commands.layers.add_layer('Test Comp', 'footage', source_name=wav_res['footage']['name'])
    commands.layers.add_layer('Test Comp', 'footage', source_name=mp4_res['footage']['name'])
    print('Layers added successfully.')

if __name__ == '__main__':
    test_proxies()

