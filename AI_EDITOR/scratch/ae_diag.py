import os
from dotenv import load_dotenv
load_dotenv()
from ae_automation.script_runner import AEScriptRunner
runner = AEScriptRunner()
print("app.project typeof:", runner.run('$.writeln(typeof app.project);'))
print("app.project string:", runner.run('$.writeln(app.project);'))
print("app.project bool:", runner.run('$.writeln(app.project ? "yes" : "no");'))
print("app.project.items typeof:", runner.run('$.writeln(app.project ? typeof app.project.items : "null");'))
