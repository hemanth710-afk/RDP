import os
from pathlib import Path
from ae_automation.commands import AEAutomationCommands
from ae_automation.script_runner import AEScriptRunner

def run_test():
    from dotenv import load_dotenv
    load_dotenv()
    exe_path = os.environ.get("AI_EDITOR_AFTER_EFFECTS_2022_PATH")
    print(f"AE Path: {exe_path}")
    runner = AEScriptRunner(exe_path)
    cmds = AEAutomationCommands(runner=runner)
    
    test_project = Path("C:/Users/L.Thirumala Teja/AI_EDITOR/scratch/minimal_test.aep")
    if test_project.exists():
        test_project.unlink()
        
    print("Testing create_project...")
    res1 = cmds.project.create_project()
    print(f"create_project result: {res1}")
    print("Testing save_project_as...")
    res2 = cmds.project.save_project_as(str(test_project))
    print(f"save_project_as result: {res2}")
    print(f"Project created? {test_project.exists()}")
    
if __name__ == "__main__":
    run_test()
