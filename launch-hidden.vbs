Set shell = CreateObject("WScript.Shell")
dq = Chr(34)
root = "C:\Users\PRINT SHOP\Desktop\projects\marketing"

' Build the current frontend, then start the single server that serves
' both the API and the built UI on http://127.0.0.1:8000. main.py opens
' the browser once the server is ready.
shell.Run "cmd /c " & dq & root & "\run.bat" & dq, 0, False
