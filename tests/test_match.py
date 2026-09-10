import unittest

from aew.match import classify, evaluate, match_watchlist

WATCHLIST = {
    "settings": {
        "categories": ["revival", "screening_event", "exhibition", "concert"],
        "include_unmatched": False,
    },
    "people": [{"name": "富野由悠季", "role": "監督", "aliases": ["富野喜幸", "井荻麟"]}],
    "works": [
        {"title": "機動戦士ガンダム 逆襲のシャア", "aliases": ["逆襲のシャア", "逆シャア"]},
        {"title": "伝説巨神イデオン", "aliases": ["イデオン"]},
    ],
}


class TestClassify(unittest.TestCase):
    def test_revival_detected(self):
        self.assertIn("revival", classify("4Kリマスターでリバイバル上映決定"))

    def test_exhibition_detected(self):
        self.assertIn("exhibition", classify("原画展の開催が決定"))

    def test_concert_detected(self):
        self.assertIn("concert", classify("オーケストラコンサート開催"))

    def test_disc_release_is_not_an_event(self):
        self.assertEqual(classify("Blu-ray BOX発売決定"), [])

    def test_disabled_category_is_ignored(self):
        self.assertEqual(classify("原画展の開催", enabled={"revival"}), [])


class TestWatchlist(unittest.TestCase):
    def test_alias_matches(self):
        hits = match_watchlist("『逆シャア』のリバイバル上映", WATCHLIST)
        self.assertEqual([h["label"] for h in hits], ["機動戦士ガンダム 逆襲のシャア"])

    def test_person_pen_name_matches(self):
        hits = match_watchlist("井荻麟 作詞の主題歌を特集", WATCHLIST)
        self.assertEqual(hits[0]["kind"], "person")

    def test_unrelated_text_does_not_match(self):
        self.assertEqual(match_watchlist("全然関係ない作品の上映", WATCHLIST), [])


class TestEvaluate(unittest.TestCase):
    def _candidate(self, title, summary=""):
        return {"title": title, "url": "https://example.com/x", "summary": summary}

    def test_watched_event_is_kept(self):
        item = evaluate(self._candidate("『逆襲のシャア』4Kリバイバル上映決定"), WATCHLIST)
        self.assertIsNotNone(item)
        self.assertTrue(item["watched"])
        self.assertIn("revival", item["categories"])

    def test_event_outside_watchlist_is_dropped(self):
        self.assertIsNone(evaluate(self._candidate("別作品のリバイバル上映決定"), WATCHLIST))

    def test_watched_work_without_event_is_dropped(self):
        # 作品に触れているだけのニュースは通知しない
        self.assertIsNone(evaluate(self._candidate("逆襲のシャアの新作プラモ発表"), WATCHLIST))

    def test_include_unmatched_keeps_general_events(self):
        watchlist = dict(WATCHLIST, settings={**WATCHLIST["settings"], "include_unmatched": True})
        item = evaluate(self._candidate("別作品のリバイバル上映決定"), watchlist)
        self.assertIsNotNone(item)
        self.assertFalse(item["watched"])

    def test_site_suffix_stripped_in_output(self):
        item = evaluate(
            self._candidate("イデオン リバイバル上映 - コミックナタリー"), WATCHLIST
        )
        self.assertEqual(item["title"], "イデオン リバイバル上映")


if __name__ == "__main__":
    unittest.main()


class TestExhibitionSuffix(unittest.TestCase):
    """固有名＋「展」で書かれた展覧会を取りこぼさないか。"""

    def test_person_exhibition_announcement(self):
        text = "ガンダム50周年プロジェクトが始動、富野由悠季展の開催発表"
        self.assertIn("exhibition", classify(text))

    def test_evaluate_picks_up_person_exhibition(self):
        item = evaluate(
            {
                "title": "ガンダム50周年プロジェクトが始動、富野由悠季展の開催発表",
                "url": "https://natalie.mu/eiga/news/672199",
                "summary": "",
            },
            WATCHLIST,
        )
        self.assertIsNotNone(item)
        self.assertIn("exhibition", item["categories"])

    def test_bare_ten_does_not_false_positive(self):
        # 「展開」「発展」で誤爆しないこと
        self.assertEqual(classify("シリーズの新展開が発表、事業も発展"), [])
