"""通知済みイベントの記録。

Routine は毎回まっさらなセッションで動くので、状態はリポジトリの
state/seen.json に置いて git で持ち回る。
"""

import json
from datetime import date, timedelta
from pathlib import Path

from .normalize import fingerprint

# これより古い記録は捨てる。再通知の心配がなくなる程度に長く取る。
RETENTION_DAYS = 400


class SeenStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: dict[str, dict] = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            self.entries = raw.get("entries", {})

    def key(self, item: dict) -> str:
        return fingerprint(item.get("title", ""), item.get("url", ""))

    def status(self, item: dict, event_date: str | None) -> str:
        """new / known / updated のいずれか。

        updated は「前回は日付不明だったが今回わかった」場合。
        チケット確保に直結するので、これは再通知する価値がある。
        """
        record = self.entries.get(self.key(item))
        if record is None:
            return "new"
        if event_date and not record.get("event_date"):
            return "updated"
        return "known"

    def remember(self, item: dict, event_date: str | None, today: date) -> None:
        key = self.key(item)
        record = self.entries.setdefault(
            key, {"first_seen": today.isoformat(), "title": item.get("title", "")}
        )
        record["last_seen"] = today.isoformat()
        record["url"] = item.get("url", "")
        if event_date:
            record["event_date"] = event_date

    def prune(self, today: date) -> int:
        """古すぎる記録を落とす。落とした件数を返す。"""
        cutoff = (today - timedelta(days=RETENTION_DAYS)).isoformat()
        stale = [k for k, v in self.entries.items() if v.get("last_seen", "") < cutoff]
        for k in stale:
            del self.entries[k]
        return len(stale)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "entries": self.entries}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
