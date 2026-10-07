
import sys
import json
sys.path.insert(0, r'C:\Users\L.Thirumala Teja\AI_EDITOR')
from ae_automation.cep_runner import AECepRunner, AECepError

def test_direct():
    print('Connecting to CEP Bridge on port 8090...')
    runner = AECepRunner(port=8090)
    
    try:
        response = runner.execute('create_project', {})
        print('========================================')
        print('SUCCESS! Connection established.')
        print('Response from ExtendScript:')
        print(json.dumps(response, indent=2))
        print('========================================')
    except AECepError as e:
        print(f'Test Failed: {e}')
    except Exception as e:
        print(f'Unexpected error: {e}')

if __name__ == '__main__':
    test_direct()

