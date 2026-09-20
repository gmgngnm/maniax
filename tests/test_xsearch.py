"""X のキーワード検索。経路が開くまでは動かないが、開いた瞬間に効くこと。"""

import unittest

from aew.xsearch import extract_status_links, parse_api_response


class TestExtractStatusLinks(unittest.TestCase):
    """ページ構造に依存せず、投稿リンクと日付を拾えるか。

    相手の markup を観測できないので、クラス名や階層を決め打ちしない。
    リンクさえ見つかれば ID から日付は厳密に出る。
    """

    HTML = """
    <html><body>
      <div class="whatever-classname-may-change">
        <a href="https://x.com/toho_movie/status/1973160936123838534">見る</a>
        <span>『NANA』リバイバル上映</span>
      </div>
      <article><a href="https://twitter.com/evangelion_co/status/1962440302842794108?s=20">x</a></article>
      <a href="https://x.com/toho_movie/status/1973160936123838534">重複リンク</a>
      <a href="https://example.com/not-a-post">無関係</a>
    </body></html>
    """

    def test_finds_posts_from_both_domains(self):
        found = extract_status_links(self.HTML)
        self.assertEqual(len(found), 2)
        self.assertEqual({f["user"] for f in found}, {"toho_movie", "evangelion_co"})

    def test_dates_come_from_the_id(self):
        by_user = {f["user"]: f for f in extract_status_links(self.HTML)}
        self.assertEqual(by_user["toho_movie"]["posted"], "2025-09-30")
        self.assertEqual(by_user["evangelion_co"]["posted"], "2025-09-01")

    def test_duplicate_links_collapse(self):
        urls = [f["url"] for f in extract_status_links(self.HTML)]
        self.assertEqual(len(urls), len(set(urls)))

    def test_query_string_stripped_from_url(self):
        found = extract_status_links(
            '<a href="https://twitter.com/a/status/1962440302842794108?s=20">x</a>'
        )
        self.assertEqual(found[0]["url"], "https://x.com/a/status/1962440302842794108")

    def test_no_posts_yields_empty(self):
        self.assertEqual(extract_status_links("<p>なにもない</p>"), [])

    def test_text_not_fabricated_for_multiple_posts(self):
        # 投稿ごとに本文を切り分けられないときは空のままにする。
        # それらしい文章を当てはめると、誤った要約が生まれる。
        for found in extract_status_links(self.HTML):
            self.assertEqual(found["text"], "")


class TestApiResponse(unittest.TestCase):
    """X API v2 の応答を候補の形に直す。"""

    PAYLOAD = {
        "data": [
            {"id": "2092160065830527246", "author_id": "1",
             "text": "リバイバル上映決定", "created_at": "2026-08-25T10:00:00.000Z"},
            {"id": "1973160936123838534", "author_id": "2", "text": "上映情報"},
        ],
        "includes": {"users": [{"id": "1", "username": "gundam_info"},
                               {"id": "2", "username": "toho_movie"}]},
    }

    def test_maps_author_ids_to_handles(self):
        got = parse_api_response(self.PAYLOAD)
        self.assertEqual(got[0]["url"],
                         "https://x.com/gundam_info/status/2092160065830527246")

    def test_created_at_becomes_a_date(self):
        self.assertEqual(parse_api_response(self.PAYLOAD)[0]["posted"], "2026-08-25")

    def test_missing_created_at_is_blank_not_guessed(self):
        self.assertEqual(parse_api_response(self.PAYLOAD)[1]["posted"], "")

    def test_text_carried_through(self):
        self.assertEqual(parse_api_response(self.PAYLOAD)[0]["text"], "リバイバル上映決定")

    def test_empty_payload(self):
        self.assertEqual(parse_api_response({}), [])
