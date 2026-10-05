import unittest

from aew.match import classify, evaluate, is_listing_url, match_watchlist

WATCHLIST = {
    "settings": {
        "categories": ["revival", "screening_event", "exhibition", "concert", "goods"],
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

    def test_disc_release_is_goods(self):
        # 以前は「イベントではない」として捨てていたが、グッズ欄を設けたので拾う
        self.assertIn("goods", classify("Blu-ray BOX発売決定"))

    def test_goods_dropped_when_category_disabled(self):
        self.assertEqual(classify("Blu-ray BOX発売決定", enabled={"revival"}), [])

    def test_streaming_is_still_not_an_event(self):
        self.assertEqual(classify("アニメの配信開始"), [])

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


class TestListingUrls(unittest.TestCase):
    """検索結果・一覧ページは中身が入れ替わる。そこから拾った日付は
    次に見たときには別の商品の日付になっているので、候補にしない。
    アニメイトの animetitle/?aid=... が 1 件の催しとして並んだ。"""

    LISTING = [
        "https://www.animate-onlineshop.jp/animetitle/?aid=1156",
        "https://example.com/search?keyword=%E9%8A%80%E8%8B%B1",
        "https://example.com/tag/gengaten/",
        "https://example.com/category/allnight/",
        # ドリパスの投票ページ。日程はまだ決まっていない（e774 は個別公演）
        "https://www.dreampass.jp/ballot_boxes/9",
    ]
    DETAIL = [
        "https://www.ticketpay.jp/booking/?event_id=57316",
        "https://art.parco.jp/parcomuseum/detail/?id=179",
        "https://natalie.mu/comic/news/649095",
        "https://ccnews.cinemacity.co.jp/aa_38th_yojouhan/",
        "https://gineiden-anime.com/goods/5986",
        "https://www.dreampass.jp/e774",
    ]

    def test_一覧ページと判定する(self):
        for url in self.LISTING:
            with self.subTest(url=url):
                self.assertTrue(is_listing_url(url))

    def test_個別ページは通す(self):
        for url in self.DETAIL:
            with self.subTest(url=url):
                self.assertFalse(is_listing_url(url))

    def test_一覧ページは候補にしない(self):
        watchlist = {"works": [{"title": "銀河英雄伝説"}], "people": [],
                     "settings": {}}
        candidate = {
            "title": "アニメイト「銀河英雄伝説」検索結果・9月下旬発売グッズ",
            "url": "https://www.animate-onlineshop.jp/animetitle/?aid=1156",
            "summary": "2026年9月下旬発売予定の新グッズが予約受付中。",
            "source": "アニメイト", "published": "",
        }
        self.assertIsNone(evaluate(candidate, watchlist))


class TestExhibitionSuffix(unittest.TestCase):
    """「◯◯展」という形を規則で拾う。

    ボトムズのジオラマ展が、語彙表に「ジオラマ展」が無いせいで
    「イベントではない」と判定され、1 か月の展示をまるごと
    見落としかけた。語を足し続けるのではなく形で拾う。
    """

    EXHIBITIONS = [
        "ジオラマ展「装甲騎兵ボトムズ総合模型演習2026」が北千住マルイで開催",
        "いのまたむつみ回顧展、名古屋で開催",
        "よつばと！原画展",
        "模型展を開く",
        "個展のお知らせ",
    ]
    NOT_EXHIBITIONS = [
        "シリーズは大きく発展した",
        "話が進展した",
        "物語が展開する",
        "今後の展望を語った",
    ]

    def test_展で終わる語は展示とみなす(self):
        for text in self.EXHIBITIONS:
            with self.subTest(text=text):
                self.assertIn("exhibition", classify(text))

    def test_普通の熟語は展示にしない(self):
        for text in self.NOT_EXHIBITIONS:
            with self.subTest(text=text):
                self.assertNotIn("exhibition", classify(text))

    def test_種別を絞っていれば足さない(self):
        self.assertEqual([], classify("ジオラマ展が開催", enabled={"goods"}))

    def test_二重に足さない(self):
        hits = classify("よつばと！原画展の開催")
        self.assertEqual(1, hits.count("exhibition"))
