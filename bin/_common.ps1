# Windows 用スクリプトの共通部分。

function Get-PythonCommand {
    # Windows の Python は python / python3 / py のどれかで入る。
    foreach ($name in @("python", "python3", "py")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            # Microsoft Store のダミー実行ファイルを掴まない
            $out = & $name -c "import sys; print(sys.version_info[0])" 2>$null
            if ($out -eq "3") { return $name }
        }
    }
    return $null
}

function Get-RepoRoot {
    return (Split-Path -Parent $PSScriptRoot)
}
