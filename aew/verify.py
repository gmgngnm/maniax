"""日付を出してよいかを判定する門番。

誤った日程を出すことは、何も出さないことより悪い。「終わった上映を
来年の予定として通知する」のが最悪で、実際それが起きた:

  - 『銀河英雄伝説 Die Neue These 策謀』第一章（2022年9月30日公開）が
    2026-09-30 の予定として登録された
  - 石黒版『銀河英雄伝説』リバイバル上映（2023年1月27日）が
    2027-01-27 の予定として登録された

どちらも、古い記事にあった「9月30日」「1月27日」に、出典が書いていない年を
補ってしまったのが原因。ここでは次の 2 つを守る。

  1. 出典に年が書かれていないなら、記事の公開日を基準にした狭い窓の中でしか
     年を補わない。基準が無ければ日付を出さない。
  2. 補った・補わないに関わらず、記事の公開日と照らして不自然な日付は捨てる。
"""

from datetime import date, timedelta

# これより古い記事は「ニュース」ではない。候補ごと落とす。
# 上映やイベントの告知は開催の数週間〜数ヶ月前に出るので、半年あれば足りる。
MAX_SOURCE_AGE_DAYS = 180

# 記事公開から見て、これより先の日付は疑う。
# 「2029年に開催」級の長期告知もあるが、その手の記事は年だけで
# 月日を書かないので、ここには引っかからない。
MAX_LEAD_DAYS = 550

# 記事公開より前の日付は、過去の出来事への言及とみなす。
MAX_BACKDATE_DAYS = 31

# 種別ごとの、ありうる会期の長さ（日）。これを超える範囲は日程ではなく、
# 施設の年度表示やページの掲載期間を拾ってしまった疑いが強い。
# 実例: 福岡市美術館の「上映会」が 2026-06-30〜2027-03-31（9か月）として
# 登録された。上映会が 9 か月続くことはない。
MAX_SPAN_DAYS = {
    "revival": 60,
    "screening_event": 60,
    "concert": 31,
    "goods": 31,
    "exhibition": 210,
}
DEFAULT_MAX_SPAN_DAYS = 210


def max_span_for(categories) -> int:
    """その催しに許す会期の長さ。複数種別なら最も長いものに合わせる。"""
    spans = [MAX_SPAN_DAYS[c] for c in (categories or []) if c in MAX_SPAN_DAYS]
    return max(spans) if spans else DEFAULT_MAX_SPAN_DAYS


class Verdict:
    """判定結果。日付を採るか、採らないか、その理由。"""

    def __init__(self, accepted: bool, reason: str = ""):
        self.accepted = accepted
        self.reason = reason

    def __repr__(self):
        return f"Verdict(accepted={self.accepted}, reason={self.reason!r})"


def is_stale(published: date | None, today: date,
             max_age_days: int = MAX_SOURCE_AGE_DAYS) -> bool:
    """記事自体が古すぎるか。古ければ候補ごと捨てる。

    公開日が分からないものは捨てない（捨てると、公開日を拾えなかった
    だけの新しい記事まで消える）。代わりに日付を採らない扱いにする。
    """
    if published is None:
        return False
    return (today - published).days > max_age_days


def assess(start: date | None, published: date | None, today: date,
           year_was_explicit: bool, end: date | None = None,
           categories=None) -> Verdict:
    """この日付を予定として出してよいかを判定する。"""
    if start is None:
        return Verdict(False, "日付が読み取れない")

    if end is not None:
        span = (end - start).days + 1
        limit = max_span_for(categories)
        if span > limit:
            return Verdict(
                False,
                f"会期が{span}日と長すぎる（この種別の上限{limit}日）。"
                "掲載期間や年度表示を拾った疑い",
            )

    if published is None:
        # 記事の公開日が分からないと、年が正しいか確かめようがない。
        # 出典に年がはっきり書いてある場合だけ通す。
        if year_was_explicit:
            return Verdict(True)
        return Verdict(False, "記事の公開日が不明で、出典にも年の記載がない")

    if (today - published).days > MAX_SOURCE_AGE_DAYS:
        return Verdict(False, f"記事が古い（{(today - published).days}日前）")

    if start < published - timedelta(days=MAX_BACKDATE_DAYS):
        # ただし会期がまだ続いているなら、開催中の長期イベントの記事。
        # 原画展のように数ヶ月続くものは、始まってから記事が出ることもある。
        if not (end and end >= today):
            return Verdict(False, "記事の公開日より前の日付（過去の出来事への言及）")

    if start > published + timedelta(days=MAX_LEAD_DAYS):
        return Verdict(False, "記事の公開日から離れすぎている（年の取り違えの疑い）")

    return Verdict(True)
