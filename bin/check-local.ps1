# セットアップができているか確かめ、足りないものを具体的に指示する。
#
#   powershell -ExecutionPolicy Bypass -File bin\check-local.ps1

. "$PSScriptRoot\_common.ps1"
Set-Location (Get-RepoRoot)
$problems = 0

function Show-Ok   ($m) { Write-Host "  OK   " -ForegroundColor Green -NoNewline; Write-Host $m }
function Show-Ng   ($m) { Write-Host "  NG   " -ForegroundColor Red   -NoNewline; Write-Host $m
                          $script:problems++ }
function Show-Note ($m) { Write-Host "       $m" -ForegroundColor DarkGray }

Write-Host "`n== 必要なもの =="

$py = Get-PythonCommand
if ($py) {
    Show-Ok "Python ($py / $(& $py -V 2>&1))"
} else {
    Show-Ng "Python 3 が見つからない"
    Show-Note "https://www.python.org/downloads/ から入れる。"
    Show-Note '導入時に "Add python.exe to PATH" に必ずチェックを入れること。'
}

if (Get-Command git -ErrorAction SilentlyContinue) {
    Show-Ok "git ($((git --version) -replace 'git version ',''))"
} else {
    Show-Ng "git が無い"
    Show-Note "winget install Git.Git"
}

Write-Host "`n== GitHub への push =="

git rev-parse --git-dir *> $null
if ($LASTEXITCODE -ne 0) {
    Show-Ng "ここは git リポジトリではない"
    Show-Note "gh repo clone gmgngnm/maniax して、その中で実行してください"
} else {
    Show-Ok "リポジトリの中にいる"
    git ls-remote --exit-code origin *> $null
    if ($LASTEXITCODE -eq 0) {
        Show-Ok "GitHub に接続できる（読み取り）"
        if (Get-Command gh -ErrorAction SilentlyContinue) {
            gh auth status *> $null
            if ($LASTEXITCODE -eq 0) { Show-Ok "gh の認証が通っている" }
            else { Show-Ng "gh にログインしていない"; Show-Note "gh auth login" }
        } else {
            Show-Note "gh が無いが、git の認証が別途通っていれば問題ない"
        }
    } else {
        Show-Ng "GitHub に接続できない"
        Show-Note "private リポジトリなので認証が要ります: gh auth login"
    }
}

Write-Host "`n== X に届くか =="
if ($py) {
    & $py -c @"
import sys
sys.path.insert(0, '.')
from aew.xsearch import available, bearer_token
label = {'api': 'X API v2(要トークン)', 'realtime': 'Yahoo!リアルタイム検索',
         'profile': '公式アカウント購読'}
live = 0
for name, (ok, why) in available().items():
    print(('  OK   ' if ok else '  NG   ') + label[name].ljust(26) + ('' if ok else why[:44]))
    live += ok
print()
if live:
    print('  -> 収集できます。')
else:
    print('  -> どの経路にも届きません。ネットワークを確認してください。')
    if not bearer_token():
        print('     X API を使うなら環境変数 X_BEARER_TOKEN を設定します。')
"@
} else {
    Show-Note "Python が無いので確認できません。"
}

Write-Host ""
if ($problems -eq 0) {
    Write-Host "問題なし。次のコマンドで定期実行を登録できます:" -ForegroundColor Green
    Write-Host "  powershell -ExecutionPolicy Bypass -File bin\install-local.ps1"
} else {
    Write-Host "上の NG を解消してから、もう一度実行してください。" -ForegroundColor Yellow
}
