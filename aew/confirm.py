"""記事本文を読んで、日付の裏を取る。

スニペットには「1月27日」としか出ていなくても、本文には
「2023年1月27日」と年まで書かれていることが多い。本文が読めるなら、
検証するだけでなく**年を訂正できる**。これが今回の事故に直接効く。

本文が読めない環境（この環境の egress ポリシーは対象ドメインを 403 で
塞いでいる）では何もせず、スニペット段階の判定をそのまま残す。
許可が下りれば自動的に効き始める。
"""

import argparse
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

from .dates import extract_ranges, parse_published
from .fetch import FetchError, fetch_text

# 判定結果
CONFIRMED = "confirmed"      # 本文に同じ月日があり、年まで取れた
CONSISTENT = "consistent"    # 本文に同じ月日はあるが、年は本文にも無い
CONTRADICTED = "contradicted"  # 本文に日付はあるが、その月日は出てこない
INCONCLUSIVE = "inconclusive"  # 本文に日付が見当たらない
UNREACHABLE = "unreachable"    # 本文を取得できない

_MD = re.compile(r"(?P<m>\d{1,2})\s*[月/／]\s*(?P<d>\d{1,2})")


def candidate_month_day(item: dict) -> tuple[int, int] | None:
    """照合の軸になる月日。確定日付があればそこから、無ければヒントから。"""
    event = item.get("event") or {}
    if event.get("start"):
        parts = event["start"].split("-")
        return int(parts[1]), int(parts[2])
    hint = item.get("date_hint")
    if hint:
        m = _MD.search(unicodedata.normalize("NFKC", hint))
        if m:
            return int(m.group("m")), int(m.group("d"))
    return None


def body_month_days(body: str) -> set[tuple[int, int]]:
    """本文に出てくる月日をすべて拾う。

    年が解決できるかどうかとは切り離す。「本文にその月日が出てくるか」
    は年を知らなくても判定でき、矛盾の検出にはこれで足りる。
    """
    found = set()
    for m in _MD.finditer(unicodedata.normalize("NFKC", body)):
        month, day = int(m.group("m")), int(m.group("d"))
        if 1 <= month <= 12 and 1 <= day <= 31:
            found.add((month, day))
    return found


def check(item: dict, body: str) -> tuple[str, dict | None]:
    """本文と突き合わせる。(判定, 訂正後の日付範囲 or None) を返す。"""
    target = candidate_month_day(item)
    if target is None:
        return INCONCLUSIVE, None

    present = body_month_days(body)
    if not present:
        return INCONCLUSIVE, None
    if target not in present:
        return CONTRADICTED, None

    # 年まで取れている記述があればそれを採る。これが訂正になる。
    published = parse_published(item.get("published", ""))
    for candidate in extract_ranges(body, published):
        parts = candidate["start"].split("-")
        if (int(parts[1]), int(parts[2])) == target and candidate.get("year_explicit"):
            return CONFIRMED, candidate
    return CONSISTENT, None


def confirm_item(item: dict, fetcher=fetch_text) -> dict:
    """1 件について本文を読み、item を書き換えて返す。"""
    url = item.get("url", "")
    if not url:
        item["date_confidence"] = INCONCLUSIVE
        return item

    try:
        body = fetcher(url)
    except FetchError as exc:
        item["date_confidence"] = UNREACHABLE
        item.setdefault("date_note", "")
        if exc.kind == "blocked":
            item["body_note"] = "本文を取得できない（ネットワークポリシーで遮断）"
        else:
            item["body_note"] = f"本文を取得できない（{exc.detail}）"
        return item

    verdict, corrected = check(item, body)
    item["date_confidence"] = verdict

    if verdict == CONFIRMED:
        previous = (item.get("event") or {}).get("start")
        item["event"] = {
            "start": corrected["start"],
            "end": corrected.get("end"),
            "raw": corrected["raw"],
            "year_explicit": True,
        }
        item["date_note"] = ""
        item.pop("date_hint", None)
        if previous and previous != corrected["start"]:
            item["body_note"] = f"本文により {previous} から訂正"
        else:
            item["body_note"] = "本文で確認"
    elif verdict == CONTRADICTED:
        # 本文に日付はあるのに、その月日が出てこない。信用できない。
        item["event"] = None
        item["date_note"] = "本文に該当する日付が見当たらない"
        item["body_note"] = "本文と一致しない"
    elif verdict == CONSISTENT:
        item["body_note"] = "本文に同じ月日はあるが、年の記載なし"
    else:
        item["body_note"] = "本文に日付の記載なし"
    return item


def confirm_all(items: list[dict], fetcher=fetch_text) -> list[dict]:
    return [confirm_item(item, fetcher) for item in items]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    digest = json.loads(Path(args.digest).read_text(encoding="utf-8"))
    items = confirm_all(digest.get("items", []))

    # 本文で日付が消えた・変わったものがあるので、通知文面を作り直す
    from . import digest as digest_mod

    today = date.fromisoformat(digest.get("generated_at", date.today().isoformat()))
    digest["items"] = items
    digest["count"] = len(items)
    digest["push"] = digest_mod.push_line(items)
    digest["email_subject"] = digest_mod.email_subject(items, today)
    digest["email_body"] = digest_mod.email_body(items, today)
    digest["calendar_events"] = digest_mod.calendar_events(items)

    Path(args.out).write_text(
        json.dumps(digest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tally: dict[str, int] = {}
    for item in items:
        key = item.get("date_confidence", "?")
        tally[key] = tally.get(key, 0) + 1
    print("本文照合: " + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
