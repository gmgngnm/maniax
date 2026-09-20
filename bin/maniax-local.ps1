# 手元の PC で X を検索し、結果をリポジトリ経由で巡回に渡す。
# 登録は bin\install-local.ps1 が行う。手で動かしてもよい。

. "$PSScriptRoot\_common.ps1"
$ErrorActionPreference = "Continue"
$repo = Get-RepoRoot
Set-Location $repo
$log = Join-Path $repo ".local-run.log"

function Write-Log($msg) {
    "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg | Add-Content $log
}

Write-Log "---- 開始 ----"

$py = Get-PythonCommand
if (-not $py) { Write-Log "Python 3 が見つからない。中止。"; exit 1 }

# 先に最新へ。ウォッチリストが更新されている。
git pull --rebase --autostash --quiet 2>&1 | Add-Content $log

$out = "inbox/{0}.json" -f (Get-Date -Format "yyyy-MM-ddTHHmm")
& $py -m aew.collect_x --watchlist watchlist.json --out $out 2>&1 | Add-Content $log
if ($LASTEXITCODE -ne 0) {
    Write-Log "収集なし、または経路に到達できず。何もせず終了。"
    exit 0
}

git add inbox
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Log "新しい候補なし。コミットしない。"; exit 0 }

git commit --quiet -m ("x: {0} の手元収集" -f (Get-Date -Format "yyyy-MM-dd HH:mm")) 2>&1 |
    Add-Content $log

foreach ($attempt in 1..3) {
    git push --quiet 2>&1 | Add-Content $log
    if ($LASTEXITCODE -eq 0) { Write-Log "push 完了: $out"; exit 0 }
    Write-Log "push 失敗（$attempt 回目）。pull し直して再試行。"
    git pull --rebase --autostash --quiet 2>&1 | Add-Content $log
    Start-Sleep -Seconds ($attempt * 5)
}

Write-Log "push できなかった。次回にまとめて送られる。"
exit 1
