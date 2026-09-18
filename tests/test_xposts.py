"""X の投稿を情報源として扱う部分。"""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from aew.dates import primary_range
from aew.ingest import run
from aew.store import SeenStore
from aew.xposts import is_x_url, parse_status, published_from_url


class TestSnowflake(unittest.TestCase):
    """投稿 ID から投稿日を復元できるか。実在の投稿で検算する。"""

    def test_known_posts(self):
        # 東宝の投稿。本文の「10/3(金)」と、2025-10-03 が金曜である事実が一致する。
        self.assertEqual(
            published_from_url("https://x.com/toho_movie/status/1973160936123838534"),
            "2025-10-01",
        )
        self.assertEqual(
            published_from_url("https://x.com/evangelion_co/status/1962440302842794108"),
            "2025-09-01",
        )

    def test_twitter_com_and_query_string(self):
        self.assertEqual(
            published_from_url("https://twitter.com/a/status/1962440302842794108?s=20"),
            "2025-09-01",
        )

    def test_non_x_url(self):
        self.assertIsNone(published_from_url("https://natalie.mu/comic/news/1"))
        self.assertFalse(is_x_url("https://natalie.mu/comic/news/1"))

    def test_parse_status_extracts_handle(self):
        self.assertEqual(
            parse_status("https://x.com/toho_movie/status/1973160936123838534")[0],
            "toho_movie",
        )

    def test_garbage_id_rejected(self):
        self.assertIsNone(published_from_url("https://x.com/a/status/12345678"))


class TestWeekdayCrossCheck(unittest.TestCase):
    """曜日注記による年の検算。"""

    def test_weekday_picks_the_right_year(self):
        # 2025-10-03 は金曜、2026-10-03 は土曜
        got = primary_range("10/3(金)～リバイバル上映", date(2025, 10, 1))
        self.assertEqual(got["start"], "2025-10-03")

    def test_weekday_mismatch_rejects_inferred_year(self):
        self.assertIsNone(primary_range("10/3(金)～リバイバル上映", date(2026, 9, 20)))

    def test_weekday_mismatch_rejects_explicit_year(self):
        # 収集側が年を書き足した場合、ここで露見する
        self.assertIsNone(primary_range("2026年10月3日(金)より", date(2026, 9, 20)))

    def test_weekday_agreement_accepted(self):
        got = primary_range("2025年10月3日(金)より", date(2025, 9, 20))
        self.assertEqual(got["start"], "2025-10-03")

    def test_no_weekday_annotation_unaffected(self):
        got = primary_range("10月3日より上映", date(2026, 9, 20))
        self.assertEqual(got["start"], "2026-10-03")


class TestIngestWithX(unittest.TestCase):
    WATCHLIST = {
        "settings": {"categories": ["revival"], "include_unmatched": False},
        "people": [],
        "works": [{"title": "エヴァンゲリオン", "aliases": ["エヴァ"]}],
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "seen.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_published_recovered_from_status_id(self):
        # published を渡していないのに、ID から日付の基準が立つ
        items = run(
            [{
                "title": "エヴァンゲリオン公式",
                "url": "https://x.com/evangelion_co/status/2086347175366480134",
                "summary": "エヴァ リバイバル上映決定。9月25日より。",
            }],
            self.WATCHLIST,
            SeenStore(self.state),
            date(2026, 9, 18),
        )
        self.assertEqual(items[0]["published"], "2026-08-09")
        self.assertEqual(items[0]["event"]["start"], "2026-09-25")

    def test_old_post_is_dropped(self):
        items = run(
            [{
                "title": "エヴァ リバイバル上映決定",
                "url": "https://x.com/evangelion_co/status/1962440302842794108",
                "summary": "10月より上映",
            }],
            self.WATCHLIST,
            SeenStore(self.state),
            date(2026, 9, 18),
        )
        self.assertEqual(items, [], "1 年前の投稿は候補ごと落とす")


if __name__ == "__main__":
    unittest.main()
