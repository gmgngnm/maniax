"""日本語のテキストから開催日・上映日を拾う。

「2026年9月18日(金)より1週間限定」「9月18日～24日」「2026/10/23公開」など、
ニュース見出しと本文冒頭に出てくる書き方をひととおり拾えれば十分とする。
カレンダー登録に使うので、取り違えるより拾わない方が安全（拾えなければ None）。

**年を勝手に補わないこと。** 以前は「年の指定がなければ未来側に倒す」
実装になっており、2022年の記事にあった「9月30日」を 2026-09-30 と読んで、
終わった上映を未来の予定として通知する事故を起こした。年が書かれていない
日付は、記事の公開日という基準がある場合に限り、その前後の狭い窓の中でだけ
補う。基準が無ければ日付を返さない。
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
# 「(金)」のような曜日注記。読み飛ばすだけでなく、年の検算に使う。
# match(text, pos) 形式で使うのでアンカーを付けない（^ は pos ではなく
# 文字列先頭にしか当たらず、曜日の検算が黙って素通りする）
_WEEKDAY = re.compile(r"\s*[（(](?P<w>[日月火水木金土])[）)]")

# date.weekday() は月曜が 0
WEEKDAY_CHARS = "月火水木金土日"

# 「1週間限定」「3日間限定」— 終了日の推定に使う
_DURATION = re.compile(r"(?P<n>\d{1,2})\s*(?P<unit>週間|日間|ヶ月|か月|カ月)")


# 年を補ってよい範囲。記事の公開日からこれ以上離れる年は採らない。
# 告知は開催の数日〜数ヶ月前後に出るので、これより広げる理由がない。
INFER_MAX_DISTANCE_DAYS = 300


def weekday_matches(value: date, weekday: str | None) -> bool:
    """「(金)」のような曜日注記と実際の曜日が合うか。注記が無ければ真。"""
    if not weekday:
        return True
    return WEEKDAY_CHARS[value.weekday()] == weekday


def _infer_year(month: int, day: int, ref: date | None,
                weekday: str | None = None) -> int | None:
    """年の指定がないときに、記事の公開日から年を割り出す。

    基準が無ければ None を返す（推測しない）。

    **公開日に最も近い年を採る。** 日本語の文章は、同じ年の話なら年を
    省く。2025 年 9 月の投稿にある「5月」は、翌年ではなくその年の 5 月を
    指していることが多い。以前は未来側に倒していたため、これを 2026 年 5 月と
    読んでしまっていた。

    年をまたぐ場合も自然に扱える。12 月の投稿にある「1月5日」は、
    同じ年の 1 月（11 ヶ月前）より翌年の 1 月（半月後）の方が近いので、
    翌年が選ばれる。

    曜日注記があればそれを最優先する。「10/3(金)」は 2025 年なら金曜、
    2026 年なら土曜なので、これだけで年が決まる。合う年が範囲内に
    無ければ、出典と食い違う日付を出すより読み取りを諦める。
    """
    if ref is None:
        return None

    best_key = None
    best_year = None
    best_matches = False
    for year in (ref.year - 1, ref.year, ref.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        distance = abs((candidate - ref).days)
        if distance > INFER_MAX_DISTANCE_DAYS:
            continue
        matches = weekday_matches(candidate, weekday)
        # 曜日一致を最優先、次に公開日への近さ、同点なら同じ年を選ぶ
        key = (0 if matches else 1, distance, 0 if year == ref.year else 1)
        if best_key is None or key < best_key:
            best_key, best_year, best_matches = key, year, matches

    if best_year is None:
        return None
    if weekday and not best_matches:
        return None
    return best_year


def _read_date(text: str, pos: int, ref: date | None):
    """text[pos:] の先頭から日付を1つ読む。(date, 年が明示か, 次の位置)。

    読めなければ (None, False, pos)。
    """
    m = _FULL.match(text, pos)
    if not m:
        return None, False, pos
    month, day = int(m.group("m")), int(m.group("d"))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None, False, pos

    end = m.end()
    wd_match = _WEEKDAY.match(text, end)
    weekday = wd_match.group("w") if wd_match else None
    if wd_match:
        end = wd_match.end()

    explicit = m.group("y") is not None
    year = int(m.group("y")) if explicit else _infer_year(month, day, ref, weekday)
    if year is None:
        return None, False, pos
    try:
        value = date(year, month, day)
    except ValueError:
        return None, False, pos

    # 年が明示されていても、曜日が合わなければ信用しない。
    # 収集側が年を書き足したときにここで露見する。
    if not weekday_matches(value, weekday):
        return None, False, pos

    return value, explicit, end


def _read_end_day(text: str, pos: int, start: date):
    """範囲の右側。「9月24日」でも「24日」でも受ける。

    終了日は開始日を基準に読む。開始日が確定している以上、
    ここで年を補うのは推測ではなく範囲の解釈。
    """
    value, _, end = _read_date(text, pos, start)
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

    返り値は {"start", "end", "raw", "year_explicit"}。
    end は範囲が明示されているか期間が書かれている場合のみ埋まる。
    year_explicit は、出典に 4 桁の年が書かれていたかどうか。呼び出し側が
    この日付をどれだけ信用してよいかの判断に使う。

    ref（記事の公開日）を渡さない場合、年の書かれていない日付は
    読み飛ばす。今日を基準に補うと、古い記事の日付が未来に化ける。
    """
    if not text:
        return []
    text = unicodedata.normalize("NFKC", text)

    found: list[dict] = []
    pos = 0
    while pos < len(text):
        start, explicit, after = _read_date(text, pos, ref)
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
                "year_explicit": explicit,
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


def mentions_bare_date(text: str) -> str | None:
    """年の書かれていない日付らしき記述があれば、その文字列を返す。

    年を解決できずに読み飛ばしたとき、「日付が無い」のか「年が無い」のかを
    区別して伝えるために使う。利用者が出典を自分で確かめる手がかりにもなる。
    """
    if not text:
        return None
    for m in _FULL.finditer(unicodedata.normalize("NFKC", text)):
        if m.group("y"):
            continue
        month, day = int(m.group("m")), int(m.group("d"))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return m.group(0).strip()
    return None


# 「2026年9月から発売」のように、月までしか書かれていない告知。
# 日が無いのでカレンダーには入れられないが、「日付が読み取れない」と
# 突き放すより「2026年9月」と伝えた方が、利用者が自分で追える。
_MONTH_ONLY = re.compile(
    r"(?:(?P<y>20\d{2})\s*年\s*)?(?P<m>\d{1,2})\s*月"
    r"(?!\s*\d{1,2}\s*日)"      # 「9月18日」は日付として別で拾う
    r"(?!\s*[/／.]\s*\d)"        # 「9/18」も同様
)


def mentions_month(text: str, ref: date | None = None) -> str | None:
    """月までしか書かれていない時期があれば、読みやすい形で返す。

    年が書かれていなければ記事の公開日から補うが、これは**表示用の
    手がかりに限る**。カレンダーにも予定一覧にも日付としては渡さない。
    """
    if not text:
        return None
    for m in _MONTH_ONLY.finditer(unicodedata.normalize("NFKC", text)):
        month = int(m.group("m"))
        if not 1 <= month <= 12:
            continue
        if m.group("y"):
            return f"{int(m.group('y'))}年{month}月"
        year = _infer_year(month, 1, ref)
        return f"{year}年{month}月" if year else f"{month}月"
    return None


# 記事 URL に埋まった公開日。animeanime.jp/article/2026/08/26/... のような形。
# 前後を数字以外で区切り、記事 ID を日付と読み違えないようにする。
_URL_DATE = re.compile(r"(?<!\d)(20\d{2})[/\-_]?(\d{2})[/\-_]?(\d{2})(?!\d)")


def published_from_path(url: str, today: date | None = None) -> date | None:
    """URL のパスから公開日を拾う。読めなければ None。

    公開日は年の解釈にも古さの判定にも効くのに、収集側が拾い損ねることが
    多い。URL に入っているなら、そこから取れる分は取る。
    """
    if not url:
        return None
    today = today or date.today()
    path = re.sub(r"^https?://[^/]+", "", url)
    for match in _URL_DATE.finditer(path):
        year, month, day = (int(g) for g in match.groups())
        try:
            found = date(year, month, day)
        except ValueError:
            continue
        # 未来の日付は公開日ではない。記事 ID の偶然の一致も落とす。
        if date(2000, 1, 1) <= found <= today:
            return found
    return None
