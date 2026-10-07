"""巡回が積み、翌朝の配信が読む行。

巡回のセッションには Gmail コネクタが渡らないので、巡回自身はメールを
送れない。文面を DB の `outbox` に積んで配信に渡す。ここで押さえるのは
2 点だけ:

- 文面を digest から**そのまま**運ぶこと（書き写させると年や曜日が混ざる）
- 新着の無い回は何も積まないこと（翌朝「0 件」のメールが届く）
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from aew.outbox import build_row, doc_id, main, should_send

DIGEST = {
    "count": 2,
    "push_bullets": "新着2件\n- 装甲騎兵ボトムズ総合模型演習2026",
    "email_subject": "10/06 新着2件（ウォッチ対象2件）",
    "email_body": "装甲騎兵ボトムズ総合模型演習2026\n2026年10月9日(金)〜11月8日(日)",
}


class TestBuildRow(unittest.TestCase):
    def test_文面をそのまま運ぶ(self):
        row = build_row(DIGEST, datetime(2026, 10, 5, 23, 4, tzinfo=timezone.utc))
        self.assertEqual(DIGEST["email_subject"], row["subject"])
        self.assertEqual(DIGEST["email_body"], row["body"])
        self.assertEqual(DIGEST["push_bullets"], row["bullets"])
        self.assertEqual(2, row["count"])

    def test_実際の時刻を秒まで残す(self):
        row = build_row(DIGEST, datetime(2026, 10, 5, 23, 4, 37, tzinfo=timezone.utc))
        self.assertEqual("2026-10-05T23:04:37Z", row["at"])

    def test_doc_idは日本時間の分まで(self):
        # 23:04 UTC は翌日の 08:04 JST
        self.assertEqual(
            "202610060804",
            doc_id(datetime(2026, 10, 5, 23, 4, tzinfo=timezone.utc)))

    def test_どちらの巡回が積んだかを控える(self):
        row = build_row(DIGEST, datetime(2026, 10, 5, tzinfo=timezone.utc), "diff")
        self.assertEqual("diff", row["kind"])

    def test_countが壊れていても落ちない(self):
        row = build_row({"count": None}, datetime(2026, 10, 5, tzinfo=timezone.utc))
        self.assertEqual(0, row["count"])


class TestShouldSend(unittest.TestCase):
    def test_新着があれば積む(self):
        self.assertTrue(
            should_send(build_row(DIGEST, datetime(2026, 10, 5, tzinfo=timezone.utc))))

    def test_新着0件は積まない(self):
        digest = dict(DIGEST, count=0)
        self.assertFalse(
            should_send(build_row(digest, datetime(2026, 10, 5, tzinfo=timezone.utc))))

    def test_本文が空なら積まない(self):
        digest = dict(DIGEST, email_body="  \n")
        self.assertFalse(
            should_send(build_row(digest, datetime(2026, 10, 5, tzinfo=timezone.utc))))


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.digest = self.tmp / "digest.json"
        self.out = self.tmp / "outbox.json"

    def _run(self, digest: dict, *extra):
        self.digest.write_text(json.dumps(digest, ensure_ascii=False),
                               encoding="utf-8")
        return main(["--digest", str(self.digest), "--out", str(self.out), *extra])

    def test_行を書き出す(self):
        self.assertEqual(0, self._run(DIGEST))
        row = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(DIGEST["email_body"], row["body"])

    def test_新着0件ならファイルを作らない(self):
        self.assertEqual(0, self._run(dict(DIGEST, count=0)))
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
