"""実際に起きた誤情報の回帰テスト。

2026-09-18 に、終わったイベント 2 件が未来の予定として登録された。
同じことを二度と通さないための固定。
"""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from aew.ingest import run
from aew.store import SeenStore
from aew.verify import MAX_SOURCE_AGE_DAYS, assess, is_stale

TODAY = date(2026, 9, 18)

WATCHLIST = {
    "settings": {"categories": ["revival", "screening_event"], "include_unmatched": False},
    "people": [],
    "works": [{"title": "銀河英雄伝説", "aliases": ["銀英伝"]}],
}


class TestRealIncidents(unittest.TestCase):
    """報告された 2 件が、そのままの入力で止まるか。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "seen.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, candidates):
        return run(candidates, WATCHLIST, SeenStore(self.state), TODAY)

    def test_die_neue_these_2022_not_dated_as_2026(self):
        # 実際は 2022年9月30日公開。記事も 2022 年のもの。
        items = self._run([
            {
                "title": "『銀河英雄伝説 Die Neue These 策謀』劇場上映、第一章9/30・第二章10/28公開",
                "url": "https://eigakan.org/theaterpage/schedule.php?t=gineidenanime4th1",
                "summary": "第一章9月30日、第二章10月28日から順次公開される。",
                "published": "2022-09-20",
            }
        ])
        self.assertEqual(items, [], "古い記事は候補ごと落とす")

    def test_ishiguro_ginei_revival_not_dated_as_2027(self):
        # 実際は 2023年1月27日・2月3日。収集側が要約に「2027年」と書いてしまった。
        items = self._run([
            {
                "title": "石黒版『銀河英雄伝説』劇場2作品リバイバル上映！",
                "url": "https://www.crank-in.net/news/114501/1",
                "summary": "2027年1月27日・2月3日にEJアニメシアター新宿でリバイバル上映決定。",
                "published": "2023-01-10",
            }
        ])
        self.assertEqual(items, [], "古い記事は、要約に書かれた年に関わらず落とす")

    def test_fabricated_future_year_rejected_when_article_is_recent(self):
        # 記事は新しいが、そこから 4 年先の日付。年の取り違えを疑う。
        items = self._run([
            {
                "title": "銀英伝 リバイバル上映",
                "url": "https://example.com/lead",
                "summary": "2030年1月27日より上映",
                "published": "2026-09-10",
            }
        ])
        self.assertEqual(len(items), 1, "情報自体は残す")
        self.assertIsNone(items[0]["event"], "日付は出さない")
        self.assertIn("離れすぎ", items[0]["date_note"])

    def test_recent_article_with_bare_date_is_accepted(self):
        # 正常系まで巻き添えにしていないこと
        items = self._run([
            {
                "title": "銀英伝 リバイバル上映決定",
                "url": "https://example.com/ok",
                "summary": "10月3日より上映",
                "published": "2026-09-15",
            }
        ])
        self.assertEqual(items[0]["event"]["start"], "2026-10-03")


class TestStaleness(unittest.TestCase):
    def test_old_article_is_stale(self):
        self.assertTrue(is_stale(date(2022, 9, 20), TODAY))

    def test_recent_article_is_not_stale(self):
        self.assertFalse(is_stale(TODAY - __import__("datetime").timedelta(days=30), TODAY))

    def test_boundary_is_not_stale(self):
        cutoff = TODAY - __import__("datetime").timedelta(days=MAX_SOURCE_AGE_DAYS)
        self.assertFalse(is_stale(cutoff, TODAY))

    def test_unknown_publication_date_is_not_stale(self):
        # 公開日が拾えなかっただけの新しい記事を消さない
        self.assertFalse(is_stale(None, TODAY))


class TestAssess(unittest.TestCase):
    def test_no_date_rejected(self):
        self.assertFalse(assess(None, TODAY, TODAY, False).accepted)

    def test_explicit_year_without_published_accepted(self):
        self.assertTrue(assess(date(2026, 12, 1), None, TODAY, True).accepted)

    def test_inferred_year_without_published_rejected(self):
        verdict = assess(date(2026, 12, 1), None, TODAY, False)
        self.assertFalse(verdict.accepted)
        self.assertIn("公開日が不明", verdict.reason)

    def test_date_before_article_rejected(self):
        verdict = assess(date(2026, 5, 1), date(2026, 9, 1), TODAY, True)
        self.assertFalse(verdict.accepted)
        self.assertIn("前の日付", verdict.reason)

    def test_slightly_before_article_allowed(self):
        # 会期中に出る記事もあるので、少し前は許す
        self.assertTrue(assess(date(2026, 8, 25), date(2026, 9, 1), TODAY, True).accepted)


if __name__ == "__main__":
    unittest.main()


class TestOngoingLongEvents(unittest.TestCase):
    """公開日より前に始まっていても、会期が続いていれば残す。"""

    def test_ongoing_exhibition_kept(self):
        verdict = assess(
            date(2026, 6, 1), date(2026, 9, 10), TODAY, True, end=date(2026, 10, 31)
        )
        self.assertTrue(verdict.accepted)

    def test_finished_event_still_rejected(self):
        verdict = assess(
            date(2026, 6, 1), date(2026, 9, 10), TODAY, True, end=date(2026, 6, 30)
        )
        self.assertFalse(verdict.accepted)
        self.assertIn("前の日付", verdict.reason)

    def test_no_end_date_still_rejected(self):
        verdict = assess(date(2026, 6, 1), date(2026, 9, 10), TODAY, True)
        self.assertFalse(verdict.accepted)


class TestUnverifiable(unittest.TestCase):
    """過去か未来か判定できない項目に印が付くか。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "seen.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, candidate):
        return run([candidate], WATCHLIST, SeenStore(self.state), TODAY)

    def test_no_date_and_no_published_is_unverifiable(self):
        # amass の記事がこれ。記事 ID しか無い URL で、本文の「5月25日」が
        # 何年か分からない。予定として扱うと終わったイベントが居座る。
        items = self._run({
            "title": "『銀河英雄伝説』一挙上映決定",
            "url": "https://amass.jp/182382/",
            "summary": "5月25日に上映",
        })
        self.assertTrue(items[0]["unverifiable"])

    def test_url_date_makes_it_verifiable(self):
        items = self._run({
            "title": "銀河英雄伝説 リバイバル上映決定",
            "url": "https://animeanime.jp/article/2026/09/10/1.html",
            "summary": "10月3日より上映",
        })
        self.assertFalse(items[0]["unverifiable"])
        self.assertEqual(items[0]["published"], "2026-09-10")
        self.assertEqual(items[0]["event"]["start"], "2026-10-03")

    def test_explicit_year_makes_it_verifiable(self):
        items = self._run({
            "title": "銀河英雄伝説 リバイバル上映決定",
            "url": "https://amass.jp/999999/",
            "summary": "2026年10月3日より上映",
        })
        self.assertFalse(items[0]["unverifiable"])


class TestSpanSanity(unittest.TestCase):
    """会期の長さが種別に対してありえない範囲なら、日程として採らない。"""

    def test_nine_month_screening_rejected(self):
        # 実例: 福岡市美術館の「上映会」が 2026-06-30〜2027-03-31 として
        # 登録された。上映会が 9 か月続くことはない。
        verdict = assess(
            date(2026, 6, 30), date(2026, 6, 20), TODAY, True,
            end=date(2027, 3, 31), categories=["screening_event"],
        )
        self.assertFalse(verdict.accepted)
        self.assertIn("長すぎる", verdict.reason)

    def test_two_week_screening_accepted(self):
        verdict = assess(
            date(2026, 10, 1), date(2026, 9, 10), TODAY, True,
            end=date(2026, 10, 14), categories=["screening_event"],
        )
        self.assertTrue(verdict.accepted)

    def test_month_long_exhibition_accepted(self):
        verdict = assess(
            date(2026, 11, 6), date(2026, 9, 12), TODAY, True,
            end=date(2026, 12, 6), categories=["exhibition"],
        )
        self.assertTrue(verdict.accepted)

    def test_exhibition_gets_a_longer_allowance_than_screening(self):
        span = (date(2026, 11, 6), date(2027, 3, 1))
        self.assertTrue(assess(span[0], date(2026, 10, 1), TODAY, True,
                               end=span[1], categories=["exhibition"]).accepted)
        self.assertFalse(assess(span[0], date(2026, 10, 1), TODAY, True,
                                end=span[1], categories=["revival"]).accepted)

    def test_mixed_categories_take_the_longest_allowance(self):
        verdict = assess(
            date(2026, 11, 6), date(2026, 10, 1), TODAY, True,
            end=date(2027, 3, 1), categories=["screening_event", "exhibition"],
        )
        self.assertTrue(verdict.accepted)

    def test_single_day_always_fine(self):
        verdict = assess(date(2026, 10, 1), date(2026, 9, 10), TODAY, True,
                         categories=["concert"])
        self.assertTrue(verdict.accepted)
