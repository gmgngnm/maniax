"""同じ催しを報じた複数記事を 1 行にまとめる。

小田原の富野由悠季展が 3 媒体から 3 行になり、しかも日付が
「11/3〜11/30」と「11/6〜12/6」で食い違った（後者が正しい）。
見出しの類似度では判別できなかったので、固有名詞の共有で束ねる。
"""

import unittest

from aew.cluster import (collapse, distinctive_terms, group, related,
                         same_event, signal_text, title_similarity)

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


class TestMergeWithExisting(unittest.TestCase):
    """別の日の巡回で同じ催しが 2 行目にならないか。

    小田原の展覧会が、後日 X 経由で 2 行目として入ってしまった。
    collapse は 1 回の巡回の中でしかまとめられないため。
    """

    EXISTING = {
        "title": "小田原市出身アニメーション映画監督、富野由悠季さん 11月から原点辿る展覧会 小田原城天守閣と三の丸ホールに資料1万点",
        "url": "https://www.townnews.co.jp/b", "source": "タウンニュース",
        "published": "2026-09-12", "categories": ["exhibition"],
        "matches": [{"label": "富野由悠季"}],
        "start": "2026-11-06", "end": "2026-12-06",
        "calendarEventId": "cal123",
        "sources": [{"name": "タウンニュース", "url": "https://www.townnews.co.jp/b"}],
    }
    FRESH = {
        "title": "富野由悠季監督の軌跡を辿る展示会「富野由悠季の原点－小田原から宇宙へ－」が小田原市にて11月に開催決定！キービジュアル公開！",
        "url": "https://x.com/gundam_info/status/2092160065830527246",
        "source": "X (@gundam_info)", "published": "2026-08-25",
        "categories": ["exhibition"], "matches": [{"label": "富野由悠季"}],
        "event": None, "date_note": "日付が読み取れない", "sources": [],
    }

    def _merge(self):
        from aew.sync import _event_from_db, merge_existing
        existing = [_event_from_db("doc_old", self.EXISTING)]
        return merge_existing(existing, [self.FRESH], {"doc_old": 4})

    def test_merges_into_the_existing_row(self):
        writes = self._merge()
        sets = [w for w in writes if w["op"] == "set"]
        self.assertEqual(len(sets), 1)
        self.assertEqual(sets[0]["doc_id"], "doc_old")
        self.assertEqual(sets[0]["if_version"], 4)

    def test_no_second_row_created(self):
        self.assertEqual(len([w for w in self._merge() if w["op"] == "set"]), 1)

    def test_confirmed_date_survives_the_merge(self):
        data = [w for w in self._merge() if w["op"] == "set"][0]["data"]
        self.assertEqual(data["start"], "2026-11-06")
        self.assertEqual(data["end"], "2026-12-06")

    def test_calendar_link_is_preserved(self):
        data = [w for w in self._merge() if w["op"] == "set"][0]["data"]
        self.assertEqual(data["calendarEventId"], "cal123")

    def test_untouched_rows_are_not_rewritten(self):
        from aew.sync import _event_from_db, merge_existing
        other = _event_from_db("doc_other", {
            "title": "無関係な催し", "url": "https://x/y",
            "categories": ["concert"], "matches": [{"label": "別作品"}],
        })
        writes = merge_existing([other], [], {"doc_other": 1})
        self.assertEqual(writes, [])

    def test_brand_new_event_gets_a_fingerprint_id(self):
        from aew.sync import merge_existing
        writes = merge_existing([], [dict(self.FRESH)], {})
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]["op"], "set")
        self.assertNotIn("if_version", writes[0])
        self.assertRegex(writes[0]["doc_id"], r"^[0-9a-f]{16}$")


def _x_post(name, handle, summary, labels, categories):
    return {
        "title": f"{name} (@{handle})",
        "summary": summary,
        "url": f"https://x.com/{handle}/status/1",
        "source": name,
        "published": "",
        "matches": [{"label": label} for label in labels],
        "categories": categories,
    }


ODAWARA_POST = _x_post(
    "ガンダム公式", "gundam_info",
    "富野由悠季監督の展示会「富野由悠季の原点－小田原から宇宙へ－」が"
    "小田原市にて11月開催決定し、キービジュアルが公開された。",
    ["富野由悠季"], ["exhibition"],
)


class TestHandleTitles(unittest.TestCase):
    """X の投稿は見出しがアカウント名で、催しの手がかりが要約にしかない。

    小田原の展覧会が X 経由で 2 行目になった。見出しだけを見ていると
    登録済みの行と結び付かない。
    """

    def test_要約まで見て登録済みの催しに束ねる(self):
        self.assertTrue(same_event(ODAWARA_B, ODAWARA_POST))
        self.assertEqual(1, len(group([ODAWARA_B, ODAWARA_POST])))

    def test_見出しに手がかりのある記事は要約を足さない(self):
        # 要約まで見ると語が増えすぎ、別の催しまで束ねてしまう。
        item = {
            "title": "『銀河英雄伝説』POP UP SHOP in コトブキヤ",
            "summary": "あわせてねんどろいどの再販も決定した。",
        }
        self.assertEqual(item["title"], signal_text(item))

    def test_同じ人物を扱う別の催しの投稿は束ねない(self):
        other = _x_post(
            "サンライズ", "sunrise_inc",
            "富野由悠季監督作品『リーンの翼』のアニメ化20周年記念上映会が"
            "新宿ピカデリーで決定しました。",
            ["富野由悠季"], ["screening_event"],
        )
        self.assertFalse(same_event(ODAWARA_POST, other))
