import unittest
from datetime import date

from aew.dates import extract_ranges, primary_range

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
