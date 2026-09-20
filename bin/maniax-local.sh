#!/usr/bin/env bash
# 手元の PC で X を検索し、結果をリポジトリ経由で巡回に渡す。
#
# クラウド側は egress ポリシーで X も Yahoo! リアルタイム検索も塞がれている。
# 手元にはその制限が無いので、検索だけをここでやる。
#
# 定期実行は bin/install-local.sh が登録する。手で動かしてもよい。

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$REPO/.local-run.log"
cd "$REPO" || exit 1

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG"; }

log "---- 開始 ----"

if ! command -v python3 >/dev/null 2>&1; then
  log "python3 が見つからない。中止。"; exit 1
fi

# 先に最新へ。ウォッチリストが更新されている。
if ! git pull --rebase --autostash --quiet 2>>"$LOG"; then
  log "git pull に失敗。ローカルの状態で続行する。"
fi

OUT="inbox/$(date +%Y-%m-%dT%H%M).json"
if ! python3 -m aew.collect_x --watchlist watchlist.json --out "$OUT" >>"$LOG" 2>&1; then
  log "収集なし、または経路に到達できず。何もせず終了。"
  exit 0
fi

git add inbox
if git diff --cached --quiet; then
  log "新しい候補なし。コミットしない。"
  exit 0
fi

git commit --quiet -m "x: $(date +%Y-%m-%d\ %H:%M) の手元収集" >>"$LOG" 2>&1

for attempt in 1 2 3; do
  if git push --quiet 2>>"$LOG"; then
    log "push 完了: $OUT"
    exit 0
  fi
  log "push 失敗（$attempt 回目）。pull し直して再試行。"
  git pull --rebase --autostash --quiet 2>>"$LOG"
  sleep $((attempt * 5))
done

log "push できなかった。次回にまとめて送られる。"
exit 1
