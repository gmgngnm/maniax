# Windows 用。PowerShell で実行する。
# 定期実行の登録（3 時間ごと）:
#   $t = New-ScheduledTaskTrigger -Once -At (Get-Date) `
#         -RepetitionInterval (New-TimeSpan -Hours 3)
#   $a = New-ScheduledTaskAction -Execute "powershell.exe" `
#         -Argument "-NoProfile -File `"$PWD\bin\maniax-local.ps1`""
#   Register-ScheduledTask -TaskName "maniax-local" -Trigger $t -Action $a
# 解除:
#   Unregister-ScheduledTask -TaskName "maniax-local" -Confirm:$false

$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$log = Join-Path $repo ".local-run.log"

function Write-Log($msg) {
  "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg | Add-Content $log
}

Write-Log "---- 開始 ----"
git pull --rebase --autostash --quiet 2>&1 | Add-Content $log

$out = "inbox/{0}.json" -f (Get-Date -Format "yyyy-MM-ddTHHmm")
python -m aew.collect_x --watchlist watchlist.json --out $out 2>&1 | Add-Content $log
if ($LASTEXITCODE -ne 0) { Write-Log "収集なし。終了。"; exit 0 }

git add inbox
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Log "新しい候補なし。"; exit 0 }

git commit --quiet -m ("x: {0} の手元収集" -f (Get-Date -Format "yyyy-MM-dd HH:mm"))
git push --quiet 2>&1 | Add-Content $log
Write-Log "push 完了: $out"
