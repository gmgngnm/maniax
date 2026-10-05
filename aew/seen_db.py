"""通知済みの記録を、アーティファクトの DB と手元のファイルの間で渡す。

Routine のセッションにはこのリポジトリへの push 権限が無いので、記録を
git で持ち回れない。代わりに DB の `control/seen` に置き、巡回のたびに
読み出してファイルに落とし、終わったら書き戻す。

    read_db  (get control/seen, out_dir=/tmp/db)
    python3 -m aew.seen_db pull --dir /tmp/db/control --out /tmp/seen.json
    python3 -m aew.ingest --state /tmp/seen.json ... --commit
    write_db (set control/seen, file_path=/tmp/seen.json)

ドキュメントがまだ無い初回でも落ちないこと（空の記録として始める）が
この橋渡しの肝。落ちると巡回全体が止まる。
"""

import argparse
import json
from pathlib import Path


def load(directory: Path) -> dict:
    """DB から落とした `control/seen` を読む。無ければ空の記録。"""
    path = Path(directory) / "seen.json"
    if not path.exists():
        return {"entries": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {"entries": {}}
    entries = raw.get("entries")
    return {"entries": entries if isinstance(entries, dict) else {}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    pull = sub.add_parser("pull", help="DB から落とした doc を state ファイルにする")
    pull.add_argument("--dir", required=True,
                      help="read_db の out_dir 配下（例 /tmp/db/control）")
    pull.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    if args.cmd == "pull":
        state = load(Path(args.dir))
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"{len(state['entries'])} 件の記録を {out} に用意しました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
