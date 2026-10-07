
import time
import sys

sys.path.insert(0, r'C:\Users\L.Thirumala Teja\AI_EDITOR')
from ae_automation.cep_runner import AECepRunner, AECepError

def test_connection():
    print('Waiting for CEP Bridge to come online on port 8090...')
    runner = AECepRunner(port=8090)
    
    timeout = 300  # 5 minutes
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            print('Attempting to connect...')
            response = runner.execute('create_project', {})
            print('========================================')
            print('SUCCESS! Connection established.')
            print('Response from ExtendScript:')
            print(response)
            print('========================================')
            return
        except AECepError as e:
            time.sleep(2)
        except Exception as e:
            print(f'Unexpected error: {e}')
            time.sleep(2)
            
    print('TIMEOUT: Could not connect to CEP Bridge within 300 seconds.')

if __name__ == '__main__':
    test_connection()

