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
time.sleep(2)

print("AI STATUS: RUNNING")
service.start()

print()
print("The blue edge should now be visible.")
print("The center of the screen should remain transparent.")
print("The stop button should be visible at bottom-right.")
print()
print("Click the STOP button to test it.")
print()

while True:
    root.update()
    time.sleep(0.02)

    if service.controller.is_stop_requested():
        print("STOP REQUEST RECEIVED")
        break

service.stop()

root.update()
time.sleep(2)

ui.close()
root.destroy()

print("AI EDGE TEST COMPLETE")