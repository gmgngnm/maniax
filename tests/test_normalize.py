import unittest

from aew import normalize as n


class TestNormalize(unittest.TestCase):
    def test_bracket_and_prefix_variants_collapse(self):
        # 媒体ごとに『』の有無や「劇場版」の付け方が違うが、同じ作品として扱う
        a = n.normalize_loose("『劇場版 少女☆歌劇 レヴュースタァライト』")
        b = n.normalize_loose("少女☆歌劇レヴュスタァライト")
        self.assertEqual(a, b)

    def test_site_suffix_removed(self):
        title = "「ひゃくえむ。」リバイバル上映 - コミックナタリー"
        self.assertEqual(
            n.strip_site_suffix(title), "「ひゃくえむ。」リバイバル上映"
        )

    def test_fullwidth_alnum_normalized(self):
        self.assertEqual(n.normalize("∀ガンダム４Ｋ"), n.normalize("∀ガンダム4K"))

    def test_tracking_params_stripped_from_url(self):
        self.assertEqual(
            n.canonical_url("https://natalie.mu/comic/news/1?utm_source=x&fbclid=y#top"),
            "https://natalie.mu/comic/news/1",
        )

    def test_fingerprint_prefers_url_over_title(self):
        # 同じ記事に別の見出しが付いても、URL が同じなら一件
        first = n.fingerprint("見出しA", "https://example.com/1")
        second = n.fingerprint("見出しB", "https://example.com/1?utm_source=z")
        self.assertEqual(first, second)

    def test_fingerprint_falls_back_to_title(self):
        self.assertEqual(n.fingerprint("同じ見出し", ""), n.fingerprint("同じ見出し", ""))
        self.assertNotEqual(n.fingerprint("見出しA", ""), n.fingerprint("見出しB", ""))


if __name__ == "__main__":
    unittest.main()
