import unittest
from datetime import date

from aew.dates import extract_ranges, primary_range, published_from_path

REF = date(2026, 9, 10)


class TestDates(unittest.TestCase):
    def test_duration_expands_to_end_date(self):
        got = primary_range("9月18日から1週間限定で上映", REF)
        self.assertEqual(got["start"], "2026-09-18")
        self.assertEqual(got["end"], "2026-09-24")

    def test_explicit_range_with_wave_dash(self):
        got = primary_range("会期は9月18日～9月24日", REF)
        self.assertEqual((got["start"], got["end"]), ("2026-09-18", "2026-09-24"))

    def test_range_with_day_only_right_side(self):
        got = primary_range("9月18日〜24日まで開催", REF)
        self.assertEqual((got["start"], got["end"]), ("2026-09-18", "2026-09-24"))

    def test_weekday_annotation_is_skipped(self):
        got = primary_range("2026年9月9日（水）よりリバイバル上映", REF)
        self.assertEqual(got["start"], "2026-09-09")

    def test_slash_notation(self):
        self.assertEqual(primary_range("2026/10/23 公開", REF)["start"], "2026-10-23")

    def test_year_inferred_forward_for_next_year(self):
        # 基準日より 60 日以上前になる日付は翌年と解釈する
        got = primary_range("1月5日より上映", REF)
        self.assertEqual(got["start"], "2027-01-05")

    def test_recent_past_keeps_current_year(self):
        got = primary_range("8月20日より上映", REF)
        self.assertEqual(got["start"], "2026-08-20")

    def test_no_date_returns_none(self):
        self.assertIsNone(primary_range("日程は後日発表", REF))

    def test_invalid_date_rejected(self):
        self.assertEqual(extract_ranges("13月45日", REF), [])

    def test_multiple_dates_returns_first_as_primary(self):
        text = "2026年9月18日より上映、2026年10月23日には新作も公開"
        ranges = extract_ranges(text, REF)
        self.assertEqual(len(ranges), 2)
        self.assertEqual(ranges[0]["start"], "2026-09-18")


if __name__ == "__main__":
    unittest.main()


class TestNearestYear(unittest.TestCase):
    """年の書かれていない日付は、公開日に最も近い年として読む。

    日本語の文章は同じ年の話なら年を省く。2025 年の投稿にある「5月」は
    その年の 5 月を指すのが自然で、翌年ではない。
    """

    def test_same_year_preferred_for_earlier_month(self):
        got = primary_range("5月10日に開催", date(2025, 9, 1))
        self.assertEqual(got["start"], "2025-05-10")

    def test_year_rollover_forward(self):
        # 12 月の投稿の「1月5日」は翌年の方が近い
        got = primary_range("1月5日より上映", date(2025, 12, 20))
        self.assertEqual(got["start"], "2026-01-05")

    def test_year_rollover_backward(self):
        # 1 月の投稿の「12月24日」は前年の方が近い
        got = primary_range("12月24日に実施", date(2026, 1, 15))
        self.assertEqual(got["start"], "2025-12-24")

    def test_far_month_beyond_window_rejected(self):
        # どの年に置いても公開日から離れすぎるケースは無い（最大でも半年）が、
        # 境界の扱いが壊れていないことだけ確かめる
        got = primary_range("3月1日より", date(2026, 9, 1))
        self.assertIsNotNone(got)
        self.assertIn(got["start"], ("2026-03-01", "2027-03-01"))

    def test_weekday_overrides_proximity(self):
        # 近さでは 2026 年だが、曜日が合うのは 2025 年
        got = primary_range("10/3(金)より", date(2026, 1, 10))
        self.assertEqual(got["start"], "2025-10-03")


class TestPublishedFromPath(unittest.TestCase):
    """URL に埋まった公開日を拾う。収集側が拾い損ねたときの保険。"""

    TODAY = date(2026, 9, 19)

    def test_slash_separated_path(self):
        self.assertEqual(
            published_from_path("https://animeanime.jp/article/2026/08/26/102377.html", self.TODAY),
            date(2026, 8, 26),
        )

    def test_compact_date_in_path(self):
        self.assertEqual(
            published_from_path("https://example.com/news/20260215-abc", self.TODAY),
            date(2026, 2, 15),
        )

    def test_article_id_is_not_a_date(self):
        self.assertIsNone(published_from_path("https://amass.jp/182382/", self.TODAY))
        self.assertIsNone(published_from_path("https://natalie.mu/comic/news/684330", self.TODAY))

    def test_invalid_date_rejected(self):
        self.assertIsNone(published_from_path("https://example.com/id/20261234", self.TODAY))

    def test_future_date_rejected(self):
        # 公開日が未来になることはない。記事 ID の偶然の一致を落とす。
        self.assertIsNone(published_from_path("https://example.com/a/2030/01/01/x", self.TODAY))

    def test_host_digits_ignored(self):
        self.assertIsNone(published_from_path("https://20260101.example.com/x", self.TODAY))
