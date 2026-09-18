"""候補を受け取って、通知すべきものだけを返す CLI。

  cat candidates.json | python3 -m aew.ingest --watchlist watchlist.json \
      --state state/seen.json --out digest.json

candidates.json は次の形の配列:
  [{"title": "...", "url": "...", "summary": "...", "source": "...",
    "published": "2026-09-10"}]

--commit を付けるまで state は更新しない。まず結果を見て、
納得してから記録する運用ができるようにしてある。
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import digest
from .dates import mentions_bare_date, parse_published, primary_range
from .match import evaluate
from .store import SeenStore
from . import verify


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run(candidates, watchlist, store: SeenStore, today: date) -> list[dict]:
    """候補を評価し、新着（と日程が新たに判明したもの）だけ返す。"""
    results: list[dict] = []
    seen_this_run: set[str] = set()
    drop_past = watchlist.get("settings", {}).get("drop_past_events", True)

    for candidate in candidates:
        item = evaluate(candidate, watchlist)
        if item is None:
            continue

        # 同じ実行の中で複数媒体が同じイベントを報じることがある
        key = store.key(item)
        if key in seen_this_run:
            continue
        seen_this_run.add(key)

        # 年の書かれていない日付は、記事の公開日を基準に解釈する。
        # 今日を基準にすると、古い記事の「9月30日」が来月の予定に化ける。
        # 公開日が分からなければ日付を補わない（primary_range が None を返す）。
        published = parse_published(item.get("published", ""))
        item["published"] = published.isoformat() if published else ""

        # 古い記事はニュースではない。候補ごと落とす。
        if published and verify.is_stale(published, today):
            continue

        text = " ".join(
            filter(None, [item["title"], item.get("snippet", ""), item.get("summary", "")])
        )
        candidate_range = primary_range(text, published)

        # 読み取れた日付を、出してよいかどうか門番に通す
        start_date = (
            date.fromisoformat(candidate_range["start"]) if candidate_range else None
        )
        verdict = verify.assess(
            start_date,
            published,
            today,
            bool(candidate_range and candidate_range.get("year_explicit")),
        )
        if verdict.accepted:
            item["event"] = candidate_range
            item["date_note"] = ""
        else:
            # 日付は出さないが、情報自体は残す。なぜ出さないかも添える。
            item["event"] = None
            item["date_note"] = verdict.reason
            hint = candidate_range["raw"] if candidate_range else mentions_bare_date(text)
            if hint:
                item["date_hint"] = hint
                if candidate_range is None:
                    # 日付は書いてあるが年が無く、基準にする公開日も無い
                    item["date_note"] = "出典に年の記載がなく、記事の公開日も不明"

        if drop_past and _has_ended(item["event"], today):
            continue

        event_date = (item["event"] or {}).get("start")
        item["status"] = store.status(item, event_date)
        if item["status"] != "known":
            results.append(item)
        store.remember(item, event_date, today)

    return results


def _has_ended(event: dict | None, today: date) -> bool:
    """会期が今日より前に終わっているか。日程不明のものは終了扱いにしない。

    検索は過去の記事も拾ってくるので、これを入れないと
    「もう終わった上映」の通知でメールが埋まる。
    """
    if not event or not event.get("start"):
        return False
    last_day = event.get("end") or event["start"]
    return last_day < today.isoformat()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist", default="watchlist.json")
    parser.add_argument("--state", default="state/seen.json")
    parser.add_argument("--candidates", help="省略時は標準入力から読む")
    parser.add_argument("--out", help="ダイジェスト JSON の出力先")
    parser.add_argument(
        "--commit", action="store_true", help="state/seen.json を実際に更新する"
    )
    parser.add_argument("--today", help="基準日 (YYYY-MM-DD)。テスト用。")
    args = parser.parse_args(argv)

    today = date.fromisoformat(args.today) if args.today else date.today()
    watchlist = load_json(args.watchlist)
    candidates = (
        load_json(args.candidates) if args.candidates else json.load(sys.stdin)
    )

    store = SeenStore(Path(args.state))
    items = run(candidates, watchlist, store, today)

    if args.commit:
        store.prune(today)
        store.save()

    payload = {
        "generated_at": today.isoformat(),
        "count": len(items),
        "items": items,
        "push": digest.push_line(items),
        "email_subject": digest.email_subject(items, today),
        "email_body": digest.email_body(items, today),
        "calendar_events": digest.calendar_events(items),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
