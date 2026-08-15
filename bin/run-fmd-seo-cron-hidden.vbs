' Hidden launcher for the FMD SEO engine's daily brain tick.
' Mirrors ZEIROS run_ingest_hidden.vbs: Task Scheduler with an interactive
' token pops a visible console for wsl.exe, which can kill the run if the
' window is closed. This wrapper runs wsl.exe with window style 0 (no window)
' and waits, so Task Scheduler still tracks the real process and its exit code.
' Extra script arguments are forwarded to bin/fmd-seo-cron.
Set sh = CreateObject("Wscript.Shell")
args = ""
For Each a In Wscript.Arguments
    args = args & " " & a
Next
cmd = "wsl.exe -d Ubuntu-22.04 -u lucascoh -- /home/lucascoh/fmd-seo-engine/.worktrees/fmd-seo-scheduler-state/bin/fmd-seo-cron" & args
rc = sh.Run(cmd, 0, True)
Wscript.Quit rc
