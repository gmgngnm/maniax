# maniax-local.ps1 をタスクスケジューラに登録する。
#
#   powershell -ExecutionPolicy Bypass -File bin\install-local.ps1        # 3時間ごと
#   powershell -ExecutionPolicy Bypass -File bin\install-local.ps1 -Hours 1
#   powershell -ExecutionPolicy Bypass -File bin\install-local.ps1 -Remove

param(
    [int]$Hours = 3,
    [switch]$Remove
)

. "$PSScriptRoot\_common.ps1"
$repo = Get-RepoRoot
$taskName = "maniax-local"
$runner = Join-Path $repo "bin\maniax-local.ps1"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "解除しました。" -ForegroundColor Green
    exit 0
}

if ($Hours -lt 1) { Write-Error "間隔は 1 時間以上で指定してください。"; exit 1 }

# 一度きりの開始時刻 + 繰り返し間隔、という形で登録する。
# 期間を指定しないと既定で終わってしまう環境があるため、明示的に長く取る。
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Hours $Hours) `
    -RepetitionDuration ([TimeSpan]::MaxValue)

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`"" `
    -WorkingDirectory $repo

# ノート PC でも動くように、バッテリー駆動で止めない
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action `
    -Settings $settings -Description "X を検索して maniax に渡す" | Out-Null

Write-Host "登録しました（$Hours 時間ごと）。" -ForegroundColor Green
Write-Host ""
Write-Host "すぐ試す:"
Write-Host "  Start-ScheduledTask -TaskName $taskName"
Write-Host "  Get-Content `"$repo\.local-run.log`" -Tail 20"
Write-Host "解除:"
Write-Host "  powershell -ExecutionPolicy Bypass -File bin\install-local.ps1 -Remove"
