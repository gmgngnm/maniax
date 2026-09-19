"""同じ催しを報じた複数記事を 1 行にまとめる。

小田原の富野由悠季展が 3 媒体から 3 行になり、しかも日付が
「11/3〜11/30」と「11/6〜12/6」で食い違った（後者が正しい）。
見出しの類似度では判別できなかったので、固有名詞の共有で束ねる。
"""

import unittest

from aew.cluster import (collapse, distinctive_terms, related,
                         same_event, title_similarity)

ODAWARA_A = {
    "title": "富野由悠季の原点に迫る！「機動戦士ガンダム」富野監督の展覧会が小田原城などで11月開催",
    "url": "https://animeanime.jp/a", "source": "アニメ！アニメ！", "published": "",
    "matches": [{"label": "富野由悠季"}], "categories": ["exhibition"],
    "event": {"start": "2026-11-03", "end": "2026-11-30"},
}
ODAWARA_B = {
    "title": "小田原市出身アニメーション映画監督、富野由悠季さん 11月から原点辿る展覧会 小田原城天守閣と三の丸ホールに資料1万点",
    "url": "https://townnews.co.jp/b", "source": "タウンニュース", "published": "2026-09-12",
    "matches": [{"label": "富野由悠季"}], "categories": ["exhibition"],
    "event": {"start": "2026-11-06", "end": "2026-12-06"},
}
ODAWARA_C = {
    "title": "「富野由悠季の原点―小田原から宇宙へ―」キービジュアル公開！ARフォト企画や関連作品上映も実施予定",
    "url": "https://hobby.dengeki.com/c", "source": "電撃ホビー", "published": "",
    "matches": [{"label": "富野由悠季"}], "categories": ["screening_event"], "event": None,
}
REAN = {
    "title": "原作者の富野由悠季も登壇、アニメ「リーンの翼」20周年記念上映会を12月に開催",
    "url": "https://natalie.mu/g", "source": "ナタリー", "published": "",
    "matches": [{"label": "富野由悠季"}], "categories": ["screening_event"], "event": None,
}
TOKYO_D = {
    "title": "「富野由悠季展（仮）」が2029年に東京国立博物館にて開催決定",
    "url": "https://denfami/d", "source": "電ファミ", "published": "",
    "matches": [{"label": "富野由悠季"}], "categories": ["exhibition"], "event": None,
}
TOKYO_E = {
    "title": "「富野由悠季展（仮）」2029年に東京国立博物館で開催決定",
    "url": "https://gundam-official/e", "source": "ガンダム公式", "published": "",
    "matches": [{"label": "富野由悠季"}], "categories": ["exhibition"], "event": None,
}


class TestTermMatching(unittest.TestCase):
    def test_containment_counts_as_related(self):
        self.assertTrue(related("小田原城", "小田原城天守閣"))
        self.assertTrue(related("原点", "原点辿"))

    def test_unrelated_terms(self):
        self.assertFalse(related("小田原城", "東京国立博物館"))

    def test_watchlist_label_excluded_from_terms(self):
        terms = distinctive_terms(ODAWARA_A["title"], {"富野由悠季"})
        self.assertNotIn("富野由悠季", terms)
        self.assertIn("小田原城", terms)


class TestSameEvent(unittest.TestCase):
    def test_same_exhibition_across_outlets(self):
        self.assertTrue(same_event(ODAWARA_A, ODAWARA_B))
        self.assertTrue(same_event(ODAWARA_A, ODAWARA_C))
        self.assertTrue(same_event(ODAWARA_B, ODAWARA_C))

    def test_near_identical_headlines(self):
        self.assertGreater(title_similarity(TOKYO_D["title"], TOKYO_E["title"]), 0.45)
        self.assertTrue(same_event(TOKYO_D, TOKYO_E))

    def test_different_events_stay_apart(self):
        self.assertFalse(same_event(ODAWARA_A, TOKYO_D))
        self.assertFalse(same_event(ODAWARA_B, REAN))
        self.assertFalse(same_event(TOKYO_D, REAN))

    def test_no_shared_watchlist_label_never_merges(self):
        other = dict(ODAWARA_B, matches=[{"label": "伝説巨神イデオン"}])
        self.assertFalse(same_event(ODAWARA_A, other))


class TestCollapse(unittest.TestCase):
    def setUp(self):
        self.groups = collapse([ODAWARA_A, ODAWARA_B, ODAWARA_C, TOKYO_D, TOKYO_E, REAN])

    def test_six_articles_become_three_events(self):
        self.assertEqual(len(self.groups), 3)

    def test_trusted_source_wins_the_date(self):
        # 公開日が分かるタウンニュース側（正しい 11/6）が採られる
        odawara = next(g for g in self.groups if len(g["sources"]) == 3)
        self.assertEqual(odawara["event"]["start"], "2026-11-06")
        self.assertEqual(odawara["event"]["end"], "2026-12-06")

    def test_conflicting_date_is_recorded_not_discarded(self):
        odawara = next(g for g in self.groups if len(g["sources"]) == 3)
        self.assertEqual(len(odawara["date_conflict"]), 1)
        self.assertEqual(odawara["date_conflict"][0]["start"], "2026-11-03")
        self.assertEqual(odawara["date_conflict"][0]["source"], "アニメ！アニメ！")

    def test_all_sources_listed(self):
        odawara = next(g for g in self.groups if len(g["sources"]) == 3)
        names = {s["name"] for s in odawara["sources"]}
        self.assertEqual(names, {"アニメ！アニメ！", "タウンニュース", "電撃ホビー"})

    def test_agreeing_dates_produce_no_conflict(self):
        same = dict(ODAWARA_A, url="https://other/x", source="別媒体",
                    event={"start": "2026-11-06", "end": "2026-12-06"})
        merged = collapse([ODAWARA_B, same])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["date_conflict"], [])

    def test_categories_are_unioned(self):
        odawara = next(g for g in self.groups if len(g["sources"]) == 3)
        self.assertIn("exhibition", odawara["categories"])
        self.assertIn("screening_event", odawara["categories"])

    def test_single_article_still_produces_a_group(self):
        rean = next(g for g in self.groups if len(g["sources"]) == 1)
        self.assertEqual(rean["title"], REAN["title"])


if __name__ == "__main__":
    unittest.main()
