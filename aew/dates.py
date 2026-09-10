"""日本語のテキストから開催日・上映日を拾う。

「2026年9月18日(金)より1週間限定」「9月18日～24日」「2026/10/23公開」など、
ニュース見出しと本文冒頭に出てくる書き方をひととおり拾えれば十分とする。
カレンダー登録に使うので、取り違えるより拾わない方が安全（拾えなければ None）。
"""

import re
import unicodedata
from datetime import date, timedelta

# 「2026年9月18日」「9月18日」「2026/9/18」「9/18」をまとめて受ける。
_FULL = re.compile(
    r"(?:(?P<y>\d{4})\s*[年/／.]\s*)?"
    r"(?P<m>\d{1,2})\s*[月/／.]\s*"
    r"(?P<d>\d{1,2})\s*日?"
)
# 範囲の右側が「24日」のように日だけのケース
_DAY_ONLY = re.compile(r"^\s*(?P<d>\d{1,2})\s*日")
_RANGE_SEP = re.compile(r"^\s*(?:[~〜～\-‐‑‒–—―]|から|より)\s*")
# 「(金)」のような曜日注記は日付の一部として読み飛ばす
_WEEKDAY = re.compile(r"^\s*[（(][日月火水木金土][）)]")

# 「1週間限定」「3日間限定」— 終了日の推定に使う
_DURATION = re.compile(r"(?P<n>\d{1,2})\s*(?P<unit>週間|日間|ヶ月|か月|カ月)")


def _infer_year(month: int, day: int, ref: date) -> int:
    """年の指定がないとき、基準日から見て最も自然な年を選ぶ。

    直近 60 日前までは「今年の過去日」として許容し、それより古くなるなら翌年扱い。
    上映情報は基本これから先の話なので、未来側に倒す。
    """
    for year in (ref.year, ref.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate >= ref - timedelta(days=60):
            return year
    return ref.year


def _read_date(text: str, pos: int, ref: date):
    """text[pos:] の先頭から日付を1つ読む。(date, 次の位置) か (None, pos)。"""
    m = _FULL.match(text, pos)
    if not m:
        return None, pos
    month, day = int(m.group("m")), int(m.group("d"))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None, pos
    year = int(m.group("y")) if m.group("y") else _infer_year(month, day, ref)
    try:
        value = date(year, month, day)
    except ValueError:
        return None, pos
    end = m.end()
    wd = _WEEKDAY.match(text, end)
    if wd:
        end = wd.end()
    return value, end


def _read_end_day(text: str, pos: int, start: date):
    """範囲の右側。「9月24日」でも「24日」でも受ける。"""
    value, end = _read_date(text, pos, start)
    if value is not None:
        return value, end
    m = _DAY_ONLY.match(text[pos:])
    if not m:
        return None, pos
    day = int(m.group("d"))
    try:
        value = date(start.year, start.month, day)
    except ValueError:
        return None, pos
    return value, pos + m.end()


def extract_ranges(text: str, ref: date | None = None) -> list[dict]:
    """テキスト中の日付・日付範囲をすべて返す。

    返り値は {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD" or None, "raw": str}。
    end は範囲が明示されているか期間が書かれている場合のみ埋まる。
    """
    if not text:
        return []
    ref = ref or date.today()
    text = unicodedata.normalize("NFKC", text)

    found: list[dict] = []
    pos = 0
    while pos < len(text):
        start, after = _read_date(text, pos, ref)
        if start is None:
            pos += 1
            continue
        raw_start = pos
        end_date = None
        sep = _RANGE_SEP.match(text[after:])
        if sep:
            candidate, after_end = _read_end_day(text, after + sep.end(), start)
            if candidate is not None and candidate >= start:
                end_date = candidate
                after = after_end
        if end_date is None:
            end_date = _duration_end(text, after, start)
        found.append(
            {
                "start": start.isoformat(),
                "end": end_date.isoformat() if end_date else None,
                "raw": text[raw_start:after].strip(),
            }
        )
        pos = after
    return found


def _duration_end(text: str, pos: int, start: date):
    """「より1週間限定」のように直後に期間が書かれていれば終了日を割り出す。"""
    tail = text[pos : pos + 20]
    m = _DURATION.search(tail)
    if not m:
        return None
    n, unit = int(m.group("n")), m.group("unit")
    if unit == "週間":
        return start + timedelta(days=7 * n - 1)
    if unit == "日間":
        return start + timedelta(days=n - 1)
    return start + timedelta(days=30 * n - 1)


def primary_range(text: str, ref: date | None = None) -> dict | None:
    """最も手前に出てくる日付を「その記事の日程」として1つ返す。"""
    ranges = extract_ranges(text, ref)
    return ranges[0] if ranges else None


_PUBLISHED_FORMATS = (
    "%a, %d %b %Y %H:%M:%S %z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d",
    "%Y/%m/%d",
)


def parse_published(value: str):
    """RSS や検索結果が持つ公開日時を date にする。読めなければ None。"""
    if not value:
        return None
    from datetime import datetime

    text = value.strip()
    for fmt in _PUBLISHED_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # 「2026年8月26日」形式や、URL 由来の日付も拾えるようにしておく
    found = extract_ranges(text, date(2000, 1, 1))
    return date.fromisoformat(found[0]["start"]) if found else None
