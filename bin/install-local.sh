#!/usr/bin/env bash
# maniax-local.sh を定期実行に登録する。macOS と Linux を自動で判別する。
#
#   bash bin/install-local.sh          # 3 時間ごとに実行
#   bash bin/install-local.sh 1        # 1 時間ごと
#   bash bin/install-local.sh --remove # 解除

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$REPO/bin/maniax-local.sh"
LABEL="jp.maniax.local"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

chmod +x "$RUNNER" 2>/dev/null || true

if [ "${1:-}" = "--remove" ]; then
  case "$(uname -s)" in
    Darwin) launchctl unload "$PLIST" 2>/dev/null || true; rm -f "$PLIST"
            echo "解除しました（launchd）。" ;;
    *)      crontab -l 2>/dev/null | grep -v "maniax-local.sh" | crontab -
            echo "解除しました（cron）。" ;;
  esac
  exit 0
fi

HOURS="${1:-3}"
if ! [ "$HOURS" -ge 1 ] 2>/dev/null; then
  echo "間隔は 1 以上の時間数で指定してください。" >&2; exit 1
fi

case "$(uname -s)" in
  Darwin)
    mkdir -p "$HOME/Library/LaunchAgents"
    cat >"$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>$RUNNER</string>
  </array>
  <key>StartInterval</key><integer>$((HOURS * 3600))</integer>
  <key>RunAtLoad</key><true/>
</dict></plist>
PLISTEOF
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    echo "登録しました（launchd, ${HOURS}時間ごと）。"
    ;;
  Linux)
    ENTRY="0 */$HOURS * * * /bin/bash $RUNNER"
    ( crontab -l 2>/dev/null | grep -v "maniax-local.sh"; echo "$ENTRY" ) | crontab -
    echo "登録しました（cron, ${HOURS}時間ごと）。"
    ;;
  *)
    echo "この OS では自動登録できません。README の Windows の項を見てください。" >&2
    exit 1
    ;;
esac

echo
echo "動作確認:"
echo "  bash $RUNNER && tail -20 $REPO/.local-run.log"
echo "解除:"
echo "  bash $REPO/bin/install-local.sh --remove"
