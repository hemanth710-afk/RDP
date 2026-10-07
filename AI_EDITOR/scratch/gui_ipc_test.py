import os
import subprocess
import time

print('Creating test script...')
with open('scratch/test2.jsx', 'w') as f:
    f.write('$.writeln("IPC Test");\n')
    f.write('var file = new File("C:\\\\Users\\\\L.Thirumala Teja\\\\AI_EDITOR\\\\scratch\\\\test_out2.txt");\n')
    f.write('file.open("w"); file.write("IPC success"); file.close();\n')
    f.write('app.project.save(new File("C:\\\\Users\\\\L.Thirumala Teja\\\\AI_EDITOR\\\\scratch\\\\ipc_proj.aep"));\n')

print('Running AfterFX.exe -r test2.jsx...')
env = os.environ.copy()
env.pop('AE_DISABLE_GPU_SNIFFER', None)
env.pop('AE_DISABLE_GPU', None)

res = subprocess.run(
    [r'C:\Program Files\Adobe\Adobe After Effects 2022\Support Files\AfterFX.exe', '-r', r'C:\Users\L.Thirumala Teja\AI_EDITOR\scratch\test2.jsx'],
    capture_output=True, text=True, env=env
)
print('STDOUT:', res.stdout)
print('STDERR:', res.stderr)
print('Return code:', res.returncode)
