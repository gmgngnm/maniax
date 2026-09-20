#!/usr/bin/env bash
# セットアップができているか確かめ、足りないものを具体的に指示する。
#
#   bash bin/check-local.sh

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

ok()   { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()   { printf '  \033[31mNG\033[0m   %s\n' "$1"; PROBLEMS=$((PROBLEMS+1)); }
note() { printf '       %s\n' "$1"; }
PROBLEMS=0

echo "== 必要なもの =="

if command -v python3 >/dev/null 2>&1; then
  ok "python3 ($(python3 -V 2>&1 | cut -d' ' -f2))"
else
  ng "python3 が無い"
  note "macOS: brew install python3   /   Ubuntu: sudo apt install python3"
fi

if command -v git >/dev/null 2>&1; then
  ok "git ($(git --version | cut -d' ' -f3))"
else
  ng "git が無い"
  note "macOS: xcode-select --install   /   Ubuntu: sudo apt install git"
fi

echo
echo "== GitHub への push =="

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  ng "ここは git リポジトリではない"
  note "git clone https://github.com/gmgngnm/maniax して、その中で実行してください"
else
  ok "リポジトリの中にいる"
  if git ls-remote --exit-code origin >/dev/null 2>&1; then
    ok "GitHub に接続できる（読み取り）"
    # 書き込みは実際に試さないと分からないが、認証の有無は見える
    if git config --get credential.helper >/dev/null 2>&1 \
       || [ -n "$(git config --get remote.origin.url | grep -E '^git@')" ] \
       || command -v gh >/dev/null 2>&1; then
      ok "push の認証が設定されていそう"
      note "確実に確かめるには: bash bin/maniax-local.sh を一度実行"
    else
      ng "push の認証が未設定の可能性"
      note "いちばん簡単: gh auth login   （GitHub CLI を入れて指示に従う）"
      note "macOS: brew install gh   /   Ubuntu: sudo apt install gh"
    fi
  else
    ng "GitHub に接続できない"
    note "private リポジトリなので認証が要ります。gh auth login が簡単です"
  fi
fi

echo
echo "== X に届くか =="
python3 - <<'PY'
import sys
sys.path.insert(0, ".")
try:
    from aew.xsearch import available, bearer_token
except Exception as exc:  # noqa: BLE001
    print(f"  NG   モジュールを読めない: {exc}")
    sys.exit(0)

label = {"api": "X API v2（要トークン）",
         "realtime": "Yahoo!リアルタイム検索",
         "profile": "公式アカウント購読"}
live = 0
for name, (ok_, why) in available().items():
    mark = "\033[32mOK\033[0m  " if ok_ else "\033[31mNG\033[0m  "
    print(f"  {mark} {label[name]:<26}{'' if ok_ else why[:44]}")
    live += ok_
if live:
    print("\n  → 収集できます。")
else:
    print("\n  → どの経路にも届きません。このPCのネットワークを確認してください。")
    if not bearer_token():
        print("     X API を使うなら X_BEARER_TOKEN を環境変数に設定します。")
PY

echo
if [ "$PROBLEMS" -eq 0 ]; then
  echo "問題なし。次のコマンドで定期実行を登録できます:"
  echo "  bash bin/install-local.sh"
else
  echo "上の NG を解消してから、もう一度このスクリプトを実行してください。"
fi
