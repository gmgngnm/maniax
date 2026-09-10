import json
import tempfile
import unittest
from pathlib import Path

from aew.normalize import fingerprint
from aew.sync import from_db, to_writes


class TestFromDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "watchlist"
        self.dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _doc(self, name, body):
        (self.dir / f"{name}.json").write_text(
            json.dumps(body, ensure_ascii=False), encoding="utf-8"
        )

    def test_splits_works_and_people(self):
        self._doc("w01", {"kind": "work", "label": "伝説巨神イデオン", "aliases": ["イデオン"]})
        self._doc("p01", {"kind": "person", "label": "富野由悠季", "role": "監督", "aliases": []})
        got = from_db(self.dir, None)
        self.assertEqual(got["works"], [{"title": "伝説巨神イデオン", "aliases": ["イデオン"]}])
        self.assertEqual(got["people"][0]["name"], "富野由悠季")
        self.assertEqual(got["people"][0]["role"], "監督")

    def test_missing_kind_defaults_to_work(self):
        self._doc("x", {"label": "海のトリトン"})
        self.assertEqual(len(from_db(self.dir, None)["works"]), 1)

    def test_blank_labels_skipped(self):
        self._doc("blank", {"kind": "work", "label": "   "})
        got = from_db(self.dir, None)
        self.assertEqual(got["works"], [])

    def test_settings_carried_over_from_fallback(self):
        fallback = Path(self.tmp.name) / "watchlist.json"
        fallback.write_text(
            json.dumps({"settings": {"max_queries": 12, "include_unmatched": True}}),
            encoding="utf-8",
        )
        self._doc("w01", {"kind": "work", "label": "ブレンパワード"})
        settings = from_db(self.dir, fallback)["settings"]
        self.assertEqual(settings["max_queries"], 12)
        self.assertTrue(settings["include_unmatched"])
        # 指定のなかった既定値は残る
        self.assertTrue(settings["drop_past_events"])


class TestToWrites(unittest.TestCase):
    def test_doc_id_matches_dedupe_fingerprint(self):
        digest = {
            "items": [
                {
                    "title": "イデオン リバイバル上映",
                    "url": "https://example.com/1",
                    "summary": "s",
                    "source": "テスト",
                    "categories": ["revival"],
                    "matches": [{"label": "伝説巨神イデオン"}],
                    "event": {"start": "2026-10-03", "end": None},
                }
            ]
        }
        writes = to_writes(digest)
        self.assertEqual(len(writes), 1)
        self.assertEqual(
            writes[0]["doc_id"], fingerprint("イデオン リバイバル上映", "https://example.com/1")
        )
        self.assertEqual(writes[0]["collection"], "events")
        self.assertEqual(writes[0]["data"]["start"], "2026-10-03")
        self.assertIsNone(writes[0]["data"]["end"])

    def test_undated_event_writes_nulls(self):
        writes = to_writes({"items": [{"title": "T", "url": "u", "event": None}]})
        self.assertIsNone(writes[0]["data"]["start"])

    def test_empty_digest_yields_no_writes(self):
        self.assertEqual(to_writes({"items": []}), [])


if __name__ == "__main__":
    unittest.main()


class TestQueryCoverage(unittest.TestCase):
    """上限で特定のカテゴリが丸ごと落ちていないか。

    以前は作品ごとに 5 本立てていたため、上限 40 だと展示とライブの
    クエリが 1 本も実行されていなかった。
    """

    def _watchlist(self, n_works):
        return {
            "settings": {"max_queries": 60},
            "people": [{"name": "富野由悠季", "role": "監督"}],
            "works": [{"title": "作品" + str(i)} for i in range(n_works)],
        }

    def test_every_template_reaches_every_work(self):
        from aew.sources import WORK_QUERY_TEMPLATES, queries_for

        watchlist = self._watchlist(18)
        queries = queries_for(watchlist)
        for template in WORK_QUERY_TEMPLATES:
            for work in watchlist["works"]:
                self.assertIn(template.format(term=work["title"]), queries)

    def test_cap_still_applies(self):
        from aew.sources import queries_for

        watchlist = self._watchlist(100)
        self.assertEqual(len(queries_for(watchlist)), 60)

    def test_cap_spreads_across_templates(self):
        # 打ち切りが起きても、先頭のテンプレートだけで埋まらないこと
        from aew.sources import queries_for

        watchlist = self._watchlist(100)
        watchlist["settings"]["max_queries"] = 30
        queries = queries_for(watchlist)
        self.assertTrue(any(q.endswith("リバイバル上映") for q in queries))


class TestPending(unittest.TestCase):
    """GUI から追加した直後のエントリだけを拾えるか。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "watchlist"
        self.dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _doc(self, name, body):
        (self.dir / f"{name}.json").write_text(
            json.dumps(body, ensure_ascii=False), encoding="utf-8"
        )

    def test_only_unsearched_entries_returned(self):
        from aew.sync import from_db

        self._doc("w01", {"kind": "work", "label": "既存作品", "searched": True})
        self._doc("w02", {"kind": "work", "label": "追加したて", "searched": False})
        got = from_db(self.dir, None, pending_only=True)
        self.assertEqual([w["title"] for w in got["works"]], ["追加したて"])

    def test_missing_flag_counts_as_searched(self):
        # 印のない古い行を未検索扱いすると、毎回全件を引き直してしまう
        from aew.sync import from_db

        self._doc("w01", {"kind": "work", "label": "印のない行"})
        self.assertEqual(from_db(self.dir, None, pending_only=True)["works"], [])

    def test_pending_ids_uses_document_id(self):
        from aew.sync import pending_ids

        self._doc("w01", {"kind": "work", "label": "A", "searched": True})
        self._doc("w07", {"kind": "person", "label": "B", "searched": False})
        self.assertEqual(pending_ids(self.dir), ["w07"])

    def test_mark_writes_are_updates_not_replacements(self):
        from aew.sync import mark_writes

        writes = mark_writes(["w07"])
        self.assertEqual(writes[0]["op"], "update")
        self.assertEqual(writes[0]["data"], {"searched": True})
        # set だと label や aliases を消してしまう
        self.assertNotIn("label", writes[0]["data"])

    def test_pending_entries_still_produce_queries(self):
        from aew.sources import queries_for
        from aew.sync import from_db

        self._doc("w02", {"kind": "work", "label": "リーンの翼", "searched": False})
        queries = queries_for(from_db(self.dir, None, pending_only=True))
        self.assertTrue(all("リーンの翼" in q for q in queries))
        self.assertEqual(len(queries), 3)
