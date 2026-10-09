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

文面は digest ではなく **merge-existing の結果**（`--writes` と
`--existing-dir`）から組み立てる。digest は突き合わせ前の各記事の見え方
なので、既存の行に畳まれたあとの正しい日程を知らない。2026-10-09 に、
小田原の展覧会（確定済み 11/6〜12/6、カレンダー登録済み）を報じた別記事が
三の丸ホールの会期 11/23〜12/6 だけを載せており、digest から作った文面が
それを「日程判明」として送ろうとした。畳んだあとの行を見れば、日程は
変わっていないと分かる。
"""

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import digest as digest_mod
from .sync import event_from_db

JST = timezone(timedelta(hours=9))

# 行が「知らせる価値のある更新」かを決める欄。題名の言い回しが変わっただけ
# では知らせない（同じ催しの別記事を拾うたびにメールが来てしまう）。
NEWS_FIELDS = ("start", "end")


def doc_id(now: datetime) -> str:
    """JST の分までを並べた ID。同じ分に 2 度積むことはない。"""
    return now.astimezone(JST).strftime("%Y%m%d%H%M")


def changed_fields(before: dict, after: dict) -> list[str]:
    return [k for k in NEWS_FIELDS
            if (before.get(k) or None) != (after.get(k) or None)]


def news_items(writes: list[dict], existing_dir: Path | None) -> list[dict]:
    """merge-existing の書き込み一覧から、知らせる行だけを item の形で返す。

    - 既存の行が無い doc_id → 新規（`new`）
    - 既存の行があって日程が変わった → 日程判明・日程変更（`updated`）
    - 既存の行があって日程が同じ → **知らせない**。同じ催しを別の媒体が
      報じただけで、利用者が既に知っていることを繰り返すだけになる。
    """
    items = []
    for write in writes:
        if write.get("op") != "set" or write.get("collection") != "events":
            continue
        data = write.get("data") or {}
        doc_id = write.get("doc_id", "")

        before = None
        if existing_dir and doc_id:
            path = Path(existing_dir) / f"{doc_id}.json"
            if path.exists():
                try:
                    before = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    before = None

        if before is not None:
            if not changed_fields(before, data):
                continue
            status = "updated"
        else:
            status = "new"

        item = event_from_db(doc_id, data)
        item["status"] = status
        item["watched"] = bool(data.get("matches"))
        items.append(item)
    return items


def rebuild(digest: dict, items: list[dict], today: date) -> dict:
    """知らせる行だけで文面を作り直す。"""
    merged = dict(digest)
    merged["count"] = len(items)
    merged["items"] = items
    merged["push_bullets"] = digest_mod.push_bullets(items)
    merged["email_subject"] = digest_mod.email_subject(items, today)
    merged["email_body"] = digest_mod.email_body(items, today)
    return merged


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
    parser.add_argument("--writes",
                        help="merge-existing の出力。渡すと畳んだあとの行から"
                             "文面を作り直す（日程はこちらが正しい）")
    parser.add_argument("--existing-dir",
                        help="read_db --out_dir が作った events ディレクトリ。"
                             "日程が変わっていない行を落とすのに使う")
    args = parser.parse_args(argv)

    digest = json.loads(Path(args.digest).read_text(encoding="utf-8"))
    if args.writes:
        writes = json.loads(Path(args.writes).read_text(encoding="utf-8"))
        today = date.fromisoformat(
            digest.get("generated_at") or date.today().isoformat())
        items = news_items(
            writes, Path(args.existing_dir) if args.existing_dir else None)
        before = digest.get("count", 0)
        digest = rebuild(digest, items, today)
        if before != len(items):
            print(f"畳んだあとの行で作り直した: {before} 件 -> {len(items)} 件")

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
