"""通知用のダイジェストを組み立てる。

Push は文字数が限られるので一行、メールは一覧、カレンダーは日程付きのものだけ、
と出力先ごとに形を変える。
"""

from datetime import date, timedelta

CATEGORY_LABELS = {
    "revival": "リバイバル上映",
    "screening_event": "上映イベント",
    "exhibition": "展示・コラボ",
    "concert": "ライブ・コンサート",
}

STATUS_LABELS = {"new": "NEW", "updated": "日程判明"}


def _sort_key(item: dict):
    """日程が決まっているものを先に、近い順。未定は後ろへ。"""
    event = item.get("event") or {}
    start = event.get("start")
    return (0, start) if start else (1, "9999-99-99")


def _format_period(item: dict) -> str:
    event = item.get("event") or {}
    start, end = event.get("start"), event.get("end")
    if not start:
        return "日程未定"
    if end and end != start:
        return f"{_jp(start)}〜{_jp(end)}"
    return _jp(start)


def _jp(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(m)}/{int(d)}"


def _labels(item: dict) -> str:
    cats = "・".join(CATEGORY_LABELS.get(c, c) for c in item.get("categories", []))
    hits = "／".join(m["label"] for m in item.get("matches", []))
    return f"[{cats}]" + (f" {hits}" if hits else "")


def push_line(items: list[dict]) -> str:
    """スマホ通知の一行。200 文字に収める。"""
    if not items:
        return ""
    head = sorted(items, key=_sort_key)[0]
    rest = len(items) - 1
    tail = f" ほか{rest}件" if rest > 0 else ""
    line = f"{_format_period(head)} {head['title']}{tail}"
    return line[:197] + "…" if len(line) > 200 else line


def email_subject(items: list[dict], today: date) -> str:
    watched = sum(1 for i in items if i.get("watched"))
    return f"[アニメ情報] {today:%m/%d} 新着{len(items)}件（ウォッチ対象{watched}件）"


def email_body(items: list[dict], today: date) -> str:
    """プレーンテキストの本文。件名だけ見て判断できるよう日程を先頭に置く。"""
    if not items:
        return "新着はありませんでした。"

    lines = [f"{today:%Y年%-m月%-d日} 時点の新着イベント情報です。", ""]
    for item in sorted(items, key=_sort_key):
        status = STATUS_LABELS.get(item.get("status", "new"), "")
        lines.append(f"■ {_format_period(item)}  {item['title']}  {status}".rstrip())
        lines.append(f"   {_labels(item)}")
        if item.get("summary"):
            lines.append(f"   {item['summary'][:120]}")
        if item.get("url"):
            lines.append(f"   {item['url']}")
        lines.append("")

    undated = [i for i in items if not (i.get("event") or {}).get("start")]
    if undated:
        lines.append(
            f"※ うち{len(undated)}件は日程が未確定です。判明した時点で再通知します。"
        )
    return "\n".join(lines)


def calendar_events(items: list[dict]) -> list[dict]:
    """カレンダー登録すべきものだけを抜き出す。日程不明のものは登録しない。

    end_date_exclusive も一緒に出す。Google カレンダーの終日予定は
    終了日が排他的（登録したい最終日の翌日を渡す）で、呼び出し側で
    毎回間違えるくらいならここで計算しておく。
    """
    events = []
    for item in items:
        event = item.get("event") or {}
        if not event.get("start"):
            continue
        last_day = event.get("end") or event["start"]
        exclusive = (date.fromisoformat(last_day) + timedelta(days=1)).isoformat()
        events.append(
            {
                "summary": f"{_labels(item)} {item['title']}"[:200],
                "start_date": event["start"],
                "end_date": last_day,
                "end_date_exclusive": exclusive,
                "description": "\n".join(
                    filter(None, [item.get("summary", ""), item.get("url", "")])
                ),
            }
        )
    return events
