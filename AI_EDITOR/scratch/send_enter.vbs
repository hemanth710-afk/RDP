Set WshShell = WScript.CreateObject("WScript.Shell")
WScript.Sleep 500
WshShell.AppActivate "After Effects"
WScript.Sleep 500
WshShell.SendKeys "{ENTER}"
WScript.Echo "Sent ENTER to After Effects"
