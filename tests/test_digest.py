"""通知の文面を組み立てる部分。"""

import unittest

from aew.digest import push_bullets


class TestPushBullets(unittest.TestCase):
    """端末への通知の文面。

    利用者の指示は「新着があったときだけ、箇条書きで。長いエラーを
    通知に出すな」。文面をここで決め切ることで、巡回側が経過や失敗の
    顛末を混ぜ込む余地をなくす。
    """

    def _item(self, title, start=None, end=None, cats=("exhibition",), note=""):
        return {"title": title, "categories": list(cats), "matches": [],
                "date_note": note,
                "event": {"start": start, "end": end} if start else None}

    def test_新着が無ければ空(self):
        self.assertEqual("", push_bullets([]))

    def test_件数と箇条書きを返す(self):
        out = push_bullets([
            self._item("ボトムズ総合模型演習2026", "2026-10-09", "2026-11-08"),
            self._item("中原岬 POP UP SHOP", "2026-10-17", "2026-10-29",
                       cats=("goods",)),
        ])
        lines = out.split("\n")
        self.assertEqual("新着2件", lines[0])
        self.assertTrue(lines[1].startswith("- 10/9〜11/8 [展示・コラボ] "))
        self.assertTrue(lines[2].startswith("- 10/17〜10/29 [グッズ・商品] "))

    def test_日程の近い順に並ぶ(self):
        out = push_bullets([
            self._item("あと", "2026-12-01"),
            self._item("さき", "2026-10-01"),
        ])
        self.assertIn("さき", out.split("\n")[1])

    def test_日程未確認は後ろで理由つき(self):
        out = push_bullets([
            self._item("日付あり", "2026-10-01"),
            self._item("日付なし", note="出典に年の記載がない"),
        ])
        self.assertIn("- 日程未確認 ", out.split("\n")[2])

    def test_多いときは丸める(self):
        items = [self._item(f"催し{i}", f"2026-11-{i:02d}") for i in range(1, 11)]
        lines = push_bullets(items).split("\n")
        self.assertEqual("新着10件", lines[0])
        self.assertEqual(7, len(lines) - 1)
        self.assertEqual("- ほか4件", lines[-1])

    def test_長い題名は詰める(self):
        out = push_bullets([self._item("あ" * 120, "2026-10-01")])
        self.assertIn("…", out)
        self.assertLess(len(out.split("\n")[1]), 70)
