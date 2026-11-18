# Splash shown while Marketing Bot is cold-starting (frontend build + backend boot).
# Closes itself as soon as /health answers. Safe to delete; run.bat recreates nothing.
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Marketing Bot'
$form.FormBorderStyle = 'None'
$form.StartPosition = 'CenterScreen'
$form.Size = New-Object System.Drawing.Size(440, 230)
$form.BackColor = [System.Drawing.Color]::FromArgb(13, 13, 13)
$form.TopMost = $true
$form.ShowInTaskbar = $true

$title = New-Object System.Windows.Forms.Label
$title.Text = 'Marketing Bot'
$title.Font = New-Object System.Drawing.Font('Segoe UI', 18, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::FromArgb(245, 245, 245)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(28, 26)
$form.Controls.Add($title)

$status = New-Object System.Windows.Forms.Label
$status.Text = 'Starting the backend and building the dashboard'
$status.AutoSize = $false
$status.Size = New-Object System.Drawing.Size(384, 20)
$status.Location = New-Object System.Drawing.Point(28, 66)
$status.ForeColor = [System.Drawing.Color]::FromArgb(163, 163, 163)
$status.Font = New-Object System.Drawing.Font('Segoe UI', 9.5)
$form.Controls.Add($status)

$dots = New-Object System.Windows.Forms.Label
$dots.Text = '...'
$dots.AutoSize = $false
$dots.Size = New-Object System.Drawing.Size(384, 20)
$dots.Location = New-Object System.Drawing.Point(28, 88)
$dots.ForeColor = [System.Drawing.Color]::FromArgb(99, 102, 241)
$dots.Font = New-Object System.Drawing.Font('Segoe UI', 12, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($dots)

$hint = New-Object System.Windows.Forms.Label
$hint.Text = 'First run of the day can take a minute. The dashboard opens by itself when it is ready.'
$hint.AutoSize = $false
$hint.Size = New-Object System.Drawing.Size(384, 40)
$hint.Location = New-Object System.Drawing.Point(28, 126)
$hint.ForeColor = [System.Drawing.Color]::FromArgb(115, 115, 115)
$hint.Font = New-Object System.Drawing.Font('Segoe UI', 8.5)
$form.Controls.Add($hint)

$close = New-Object System.Windows.Forms.Button
$close.Text = 'Close'
$close.FlatStyle = 'Flat'
$close.FlatAppearance.BorderSize = 1
$close.FlatAppearance.BorderColor = [System.Drawing.Color]::FromArgb(42, 42, 42)
$close.ForeColor = [System.Drawing.Color]::FromArgb(163, 163, 163)
$close.BackColor = [System.Drawing.Color]::FromArgb(22, 22, 22)
$close.Size = New-Object System.Drawing.Size(64, 24)
$close.Location = New-Object System.Drawing.Point(348, 182)
$close.Add_Click({ $form.Close() })
$form.Controls.Add($close)

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$frame = 0

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 400
$timer.Add_Tick({
    $frame += 1
    $dots.Text = '.' * (($frame % 3) + 1)
    try {
        $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 1
        if ($r.status -eq 'ok') {
            $timer.Stop()
            $form.Close()
            return
        }
    } catch {
        # Server not up yet.
    }
    if ($sw.Elapsed.TotalSeconds -gt 240) {
        $status.Text = 'Still starting - if this does not resolve, check run.log'
        $status.ForeColor = [System.Drawing.Color]::FromArgb(251, 191, 36)
    }
})
$timer.Start()
[System.Windows.Forms.Application]::Run($form)
