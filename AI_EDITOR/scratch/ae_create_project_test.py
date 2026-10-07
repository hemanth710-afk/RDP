
from dotenv import load_dotenv
from pathlib import Path
from ae_automation import AEAutomationCommands

load_dotenv('.env')

def main():
    print('Starting minimal create_project test...')
    
    # Ensure test directory exists
    test_dir = Path('scratch/human_editor_test/ae_debug')
    test_dir.mkdir(parents=True, exist_ok=True)
    
    commands = AEAutomationCommands()
    try:
        commands.create_project()
        print('SUCCESS - create_project returned without error.')
    except Exception as e:
        print(f'FAILURE - {type(e).__name__}: {e}')

if __name__ == '__main__':
    main()

