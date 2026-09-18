"""本文照合。スニペットに無い年を本文から取れるか。"""

import unittest

from aew.confirm import (CONFIRMED, CONSISTENT, CONTRADICTED, INCONCLUSIVE,
                         UNREACHABLE, check, confirm_item)
from aew.fetch import FetchError


class TestCheck(unittest.TestCase):
    def _item(self, start=None, hint=None, published="2023-01-10"):
        item = {"url": "https://example.com/a", "published": published}
        if start:
            item["event"] = {"start": start, "end": None}
        if hint:
            item["date_hint"] = hint
        return item

    def test_body_supplies_missing_year(self):
        # 今回の事故そのもの: スニペットは「1月27日」、本文に「2023年1月27日」
        item = self._item(hint="1月27日")
        verdict, corrected = check(item, "EJアニメシアター新宿にて2023年1月27日より上映")
        self.assertEqual(verdict, CONFIRMED)
        self.assertEqual(corrected["start"], "2023-01-27")

    def test_body_corrects_a_wrong_year(self):
        item = self._item(start="2027-01-27")
        verdict, corrected = check(item, "2023年1月27日より上映")
        self.assertEqual(verdict, CONFIRMED)
        self.assertEqual(corrected["start"], "2023-01-27")

    def test_body_without_matching_day_contradicts(self):
        item = self._item(start="2026-01-27")
        verdict, corrected = check(item, "2026年3月5日より上映")
        self.assertEqual(verdict, CONTRADICTED)
        self.assertIsNone(corrected)

    def test_body_with_same_day_but_no_year(self):
        item = self._item(start="2026-01-27", published=None)
        verdict, _ = check(item, "1月27日より上映")
        self.assertEqual(verdict, CONSISTENT)

    def test_body_without_dates_is_inconclusive(self):
        item = self._item(start="2026-01-27")
        self.assertEqual(check(item, "日程は後日発表")[0], INCONCLUSIVE)

    def test_no_candidate_day_is_inconclusive(self):
        self.assertEqual(check({"url": "u"}, "2026年1月27日")[0], INCONCLUSIVE)


class TestConfirmItem(unittest.TestCase):
    def test_correction_is_recorded(self):
        item = {"url": "https://example.com/a", "published": "2023-01-10",
                "event": {"start": "2027-01-27", "end": None}}
        confirm_item(item, fetcher=lambda url: "2023年1月27日より上映")
        self.assertEqual(item["event"]["start"], "2023-01-27")
        self.assertIn("訂正", item["body_note"])

    def test_contradiction_drops_the_date(self):
        item = {"url": "https://example.com/a", "published": "2026-09-01",
                "event": {"start": "2026-10-01", "end": None}}
        confirm_item(item, fetcher=lambda url: "2026年12月24日より上映")
        self.assertIsNone(item["event"])
        self.assertIn("一致しない", item["body_note"])

    def test_blocked_network_leaves_item_untouched(self):
        # 本文が読めない環境で、スニペット段階の判定を壊さないこと
        item = {"url": "https://example.com/a", "published": "2026-09-01",
                "event": {"start": "2026-10-01", "end": None}}

        def blocked(url):
            raise FetchError("blocked", "403")

        confirm_item(item, fetcher=blocked)
        self.assertEqual(item["date_confidence"], UNREACHABLE)
        self.assertEqual(item["event"]["start"], "2026-10-01")
        self.assertIn("遮断", item["body_note"])

    def test_missing_url_is_inconclusive(self):
        item = {"event": {"start": "2026-10-01"}}
        confirm_item(item, fetcher=lambda url: "unused")
        self.assertEqual(item["date_confidence"], INCONCLUSIVE)


if __name__ == "__main__":
    unittest.main()
