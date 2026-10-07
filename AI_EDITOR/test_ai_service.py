import tkinter as tk
import time

from ai_status import AIActivityService, AIStatusUI


service = AIActivityService()

root = tk.Tk()
root.withdraw()

ui = AIStatusUI(
    service.controller,
    root=root,
)

print("AI STATUS: IDLE")
root.update()
time.sleep(1)

print("AI STATUS: RUNNING")
service.start()

end_time = time.time() + 8

while time.time() < end_time:
    root.update()
    time.sleep(0.01)

print("AI STATUS: STOPPING")
service.stop()

root.update()
time.sleep(1)

ui.close()
root.destroy()

print("AI STATUS DEMO COMPLETE")
