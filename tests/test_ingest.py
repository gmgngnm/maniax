import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from aew.digest import calendar_events, push_line
from aew.ingest import run
from aew.store import SeenStore

TODAY = date(2026, 9, 10)

WATCHLIST = {
    "settings": {"categories": ["revival", "exhibition"], "include_unmatched": False},
    "people": [],
    "works": [{"title": "伝説巨神イデオン", "aliases": ["イデオン"]}],
}


class TestIngest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "seen.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, candidates):
        store = SeenStore(self.state)
        items = run(candidates, WATCHLIST, store, TODAY)
        store.save()
        return items

    def test_new_item_reported_once(self):
        candidates = [
            {
                "title": "『伝説巨神イデオン』リバイバル上映決定",
                "url": "https://example.com/1",
                "summary": "2026年10月3日より上映",
            }
        ]
        first = self._run(candidates)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["status"], "new")
        self.assertEqual(first[0]["event"]["start"], "2026-10-03")

        # 2 回目は既知なので通知しない
        self.assertEqual(self._run(candidates), [])

    def test_same_event_from_two_outlets_reported_once(self):
        candidates = [
            {"title": "イデオン リバイバル上映決定", "url": "https://a.example/1"},
            {"title": "イデオン リバイバル上映決定", "url": "https://a.example/1?utm_source=x"},
        ]
        self.assertEqual(len(self._run(candidates)), 1)

    def test_date_becoming_known_triggers_renotify(self):
        undated = [{"title": "イデオン原画展 開催決定", "url": "https://example.com/2"}]
        self.assertEqual(self._run(undated)[0]["status"], "new")

        dated = [
            {
                "title": "イデオン原画展 開催決定",
                "url": "https://example.com/2",
                "summary": "会期は11月1日～11月30日",
            }
        ]
        again = self._run(dated)
        self.assertEqual(len(again), 1)
        self.assertEqual(again[0]["status"], "updated")
        self.assertEqual(again[0]["event"]["end"], "2026-11-30")

    def test_state_persists_to_disk(self):
        self._run([{"title": "イデオン リバイバル上映", "url": "https://example.com/3"}])
        saved = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["entries"]), 1)

    def test_prune_drops_ancient_entries(self):
        store = SeenStore(self.state)
        store.entries["old"] = {"last_seen": "2020-01-01"}
        store.entries["fresh"] = {"last_seen": TODAY.isoformat()}
        self.assertEqual(store.prune(TODAY), 1)
        self.assertIn("fresh", store.entries)


class TestDigest(unittest.TestCase):
    def test_calendar_skips_undated_items(self):
        items = [
            {"title": "A", "categories": ["revival"], "matches": [], "event": None},
            {
                "title": "B",
                "categories": ["revival"],
                "matches": [],
                "event": {"start": "2026-10-03", "end": None},
            },
        ]
        events = calendar_events(items)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["start_date"], "2026-10-03")
        self.assertEqual(events[0]["end_date"], "2026-10-03")

    def test_push_line_prefers_soonest_and_stays_short(self):
        items = [
            {"title": "後の予定", "categories": [], "matches": [], "event": {"start": "2026-12-01"}},
            {"title": "近い予定", "categories": [], "matches": [], "event": {"start": "2026-09-20"}},
        ]
        line = push_line(items)
        self.assertIn("近い予定", line)
        self.assertIn("ほか1件", line)
        self.assertLessEqual(len(line), 200)

    def test_push_line_empty_for_no_items(self):
        self.assertEqual(push_line([]), "")


if __name__ == "__main__":
    unittest.main()


class TestPastEvents(unittest.TestCase):
    """検索は過去記事も拾うので、終わったイベントを落とせているか。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "seen.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, candidates, watchlist=WATCHLIST):
        return run(candidates, watchlist, SeenStore(self.state), TODAY)

    def test_finished_event_is_dropped(self):
        candidates = [
            {
                "title": "イデオン リバイバル上映",
                "url": "https://example.com/past",
                "summary": "2026年1月9日から1月15日まで上映",
            }
        ]
        self.assertEqual(self._run(candidates), [])

    def test_ongoing_event_is_kept(self):
        # 会期に入っているが、まだ終わっていないもの
        candidates = [
            {
                "title": "イデオン原画展",
                "url": "https://example.com/now",
                "summary": "2026年9月1日～9月30日開催",
            }
        ]
        self.assertEqual(len(self._run(candidates)), 1)

    def test_undated_event_is_kept(self):
        candidates = [{"title": "イデオン リバイバル上映決定", "url": "https://example.com/tbd"}]
        self.assertEqual(len(self._run(candidates)), 1)

    def test_drop_past_can_be_disabled(self):
        watchlist = dict(
            WATCHLIST, settings={**WATCHLIST["settings"], "drop_past_events": False}
        )
        candidates = [
            {
                "title": "イデオン リバイバル上映",
                "url": "https://example.com/past2",
                "summary": "2026年1月9日から1月15日まで上映",
            }
        ]
        self.assertEqual(len(self._run(candidates, watchlist)), 1)


class TestPublishedAsReference(unittest.TestCase):
    """年の無い日付は、今日ではなく記事公開日を基準に読む。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "seen.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_year_taken_from_article_date(self):
        # 2026-05 の記事にある「6月5日」は 2026 年。今日基準だと 2027 になってしまう。
        candidates = [
            {
                "title": "イデオン 4DXリバイバル上映決定",
                "url": "https://example.com/4dx",
                "summary": "6月5日より全国20館で上映",
                "published": "2026-05-20",
            }
        ]
        watchlist = dict(
            WATCHLIST, settings={**WATCHLIST["settings"], "drop_past_events": False}
        )
        items = run(candidates, watchlist, SeenStore(self.state), TODAY)
        self.assertEqual(items[0]["event"]["start"], "2026-06-05")

    def test_falls_back_to_today_without_published(self):
        candidates = [
            {
                "title": "イデオン リバイバル上映決定",
                "url": "https://example.com/nopub",
                "summary": "10月3日より上映",
            }
        ]
        items = run(candidates, WATCHLIST, SeenStore(self.state), TODAY)
        self.assertEqual(items[0]["event"]["start"], "2026-10-03")


class TestCalendarEndDate(unittest.TestCase):
    """終日予定の終了日が排他的である点をコード側で吸収できているか。"""

    def _event(self, start, end):
        item = {"title": "T", "categories": [], "matches": [], "event": {"start": start, "end": end}}
        return calendar_events([item])[0]

    def test_single_day_exclusive_end_is_next_day(self):
        event = self._event("2026-10-03", None)
        self.assertEqual(event["end_date"], "2026-10-03")
        self.assertEqual(event["end_date_exclusive"], "2026-10-04")

    def test_range_exclusive_end_is_day_after_last(self):
        event = self._event("2026-11-03", "2026-11-30")
        self.assertEqual(event["end_date_exclusive"], "2026-12-01")

    def test_exclusive_end_crosses_month_and_year(self):
        event = self._event("2026-12-31", None)
        self.assertEqual(event["end_date_exclusive"], "2027-01-01")
