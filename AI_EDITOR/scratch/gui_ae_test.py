import subprocess
import time
from pywinauto.application import Application

print('Killing existing AE instances...')
subprocess.run(['taskkill', '/F', '/IM', 'AfterFX.exe'], capture_output=True)
time.sleep(2)

print('Starting After Effects normally...')
try:
    Application(backend='uia').start(r'C:\Program Files\Adobe\Adobe After Effects 2022\Support Files\AfterFX.exe')
except Exception as e:
    print('Start error:', e)

print('Waiting 20 seconds for AE to boot...')
time.sleep(20)

print('Writing test JSX...')
with open('scratch/test.jsx', 'w') as f:
    f.write('$.writeln("Test from GUI!");\n')
    f.write('var file = new File("C:\\\\Users\\\\L.Thirumala Teja\\\\AI_EDITOR\\\\scratch\\\\test_out.txt");\n')
    f.write('file.open("w"); file.write("GUI instance worked."); file.close();\n')

print('Running AfterFX.exe -r test.jsx...')
res = subprocess.run([r'C:\Program Files\Adobe\Adobe After Effects 2022\Support Files\AfterFX.exe', '-r', r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\test.jsx'], capture_output=True, text=True)
print('STDOUT:', res.stdout)
print('STDERR:', res.stderr)

import os
if os.path.exists('scratch/test_out.txt'):
    print('Output found! Script executed successfully.')
else:
    print('Output NOT found!')

print('Checking running AfterFX instances...')
res = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq AfterFX.exe'], capture_output=True, text=True)
print(res.stdout)
