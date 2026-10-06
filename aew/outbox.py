"""配信待ちのメール文面を、DB の `outbox` に置く形に整える。

巡回の Routine は毎回まっさらなセッションで動くので、Gmail コネクタが
渡らない（組織の設定で `connectors` を指定できない）。巡回自身がメールを
送ることはできない。そこで文面だけを DB の `outbox` に積んでおき、毎朝
9:00 の配信 Routine（こちらは Gmail に繋がっている）がまとめて 1 通で送る。

    python3 -m aew.ingest ... --out /tmp/digest.json --commit
    python3 -m aew.confirm --digest /tmp/digest.json --out /tmp/digest.json
    python3 -m aew.outbox --digest /tmp/digest.json --out /tmp/outbox.json
    write_db (set outbox/<表示された doc_id>, file_path=/tmp/outbox.json)

文面を巡回側に書き写させず、ここで digest からそのまま運ぶのが肝。
書き写させると要約し直され、出典に無い年や曜日が混ざる。

新着が無い回は何も書かない（`skip` と表示して終わる）。空の行を積むと、
翌朝「新着 0 件」のメールが届く。
"""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))


def doc_id(now: datetime) -> str:
    """JST の分までを並べた ID。同じ分に 2 度積むことはない。"""
    return now.astimezone(JST).strftime("%Y%m%d%H%M")


def build_row(digest: dict, now: datetime, kind: str = "full") -> dict:
    """digest.json から、配信が読む 1 行を作る。文面は加工しない。"""
    try:
        count = int(digest.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    return {
        "at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": kind,
        "count": count,
        "subject": digest.get("email_subject") or "",
        "body": digest.get("email_body") or "",
        "bullets": digest.get("push_bullets") or "",
    }


def should_send(row: dict) -> bool:
    """積むに値するか。件数も本文も無い行は配信の邪魔になるだけ。"""
    return row["count"] > 0 and bool(row["body"].strip())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--kind", default="full", choices=["full", "diff"],
                        help="どちらの巡回が積んだか（配信では使わない控え）")
    args = parser.parse_args(argv)

    digest = json.loads(Path(args.digest).read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    row = build_row(digest, now, args.kind)

    if not should_send(row):
        print("skip: 新着が無いので outbox には積みません")
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"doc_id: {doc_id(now)}")
    print(f"{row['count']} 件の文面を {out} に用意しました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
