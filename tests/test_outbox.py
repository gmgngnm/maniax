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
from datetime import date, datetime, timezone
from pathlib import Path

from aew.outbox import (build_row, doc_id, main, news_items, rebuild,
                        should_send)

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


class TestNewsItems(unittest.TestCase):
    """畳んだあとの行から、知らせる価値のある行だけを拾う。

    2026-10-09 の事故: 小田原の展覧会（確定済み 11/6〜12/6、カレンダー
    登録済み）を報じた別記事が、三の丸ホールの会期 11/23〜12/6 だけを
    載せていた。merge-existing は既存の日程を保って食い違いを
    `dateConflict` に落としたのに、digest から作った文面はその記事の
    日程を「日程判明」として送ろうとした。
    """

    ODAWARA = {
        "title": "富野由悠季の原点－小田原から宇宙へ－",
        "url": "https://tomino-beginningpoint.jp/",
        "start": "2026-11-06",
        "end": "2026-12-06",
        "categories": ["exhibition"],
        "matches": [{"label": "富野由悠季"}],
        "calendarEventId": "4of70ptunngs",
    }

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "doc_odawara.json").write_text(
            json.dumps(self.ODAWARA, ensure_ascii=False), encoding="utf-8")

    def _write(self, doc_id, data):
        return {"op": "set", "collection": "events", "doc_id": doc_id, "data": data}

    def test_日程が変わらない行は知らせない(self):
        # 別の媒体が同じ催しを報じただけ。日程は畳んだあとも 11/6 のまま
        merged = dict(self.ODAWARA,
                      dateConflict=[{"start": "2026-11-23", "end": "2026-12-06",
                                     "url": "https://press.moviewalker.jp/x"}])
        self.assertEqual([], news_items([self._write("doc_odawara", merged)], self.tmp))

    def test_知らない行は新規として知らせる(self):
        rows = news_items([self._write("doc_new", {
            "title": "装甲騎兵ボトムズ総合模型演習2026",
            "start": "2026-10-09", "end": "2026-11-08",
            "categories": ["exhibition"], "matches": [{"label": "ボトムズ"}],
        })], self.tmp)
        self.assertEqual(1, len(rows))
        self.assertEqual("new", rows[0]["status"])
        self.assertTrue(rows[0]["watched"])

    def test_日程が決まった行は知らせる(self):
        (self.tmp / "doc_pending.json").write_text(
            json.dumps({"title": "富野由悠季展（仮）", "start": None, "end": None},
                       ensure_ascii=False), encoding="utf-8")
        rows = news_items([self._write("doc_pending", {
            "title": "富野由悠季展（仮）", "start": "2029-04-01", "end": None,
        })], self.tmp)
        self.assertEqual(["updated"], [r["status"] for r in rows])

    def test_題名だけ変わった行は知らせない(self):
        merged = dict(self.ODAWARA, title="富野由悠季の原点-小田原から宇宙へ-")
        self.assertEqual([], news_items([self._write("doc_odawara", merged)], self.tmp))

    def test_delete_は無視する(self):
        writes = [{"op": "delete", "collection": "events", "doc_id": "doc_odawara"}]
        self.assertEqual([], news_items(writes, self.tmp))

    def test_既存ディレクトリが無くても落ちない(self):
        rows = news_items([self._write("doc_new", {"title": "A", "start": None})], None)
        self.assertEqual(["new"], [r["status"] for r in rows])


class TestRebuild(unittest.TestCase):
    def test_件数と文面を作り直す(self):
        items = [{"title": "装甲騎兵ボトムズ総合模型演習2026", "status": "new",
                  "watched": True, "categories": ["exhibition"], "matches": [],
                  "event": {"start": "2026-10-09", "end": "2026-11-08"}}]
        rebuilt = rebuild(dict(DIGEST), items, date(2026, 10, 9))
        self.assertEqual(1, rebuilt["count"])
        self.assertIn("新着1件", rebuilt["push_bullets"])
        self.assertIn("新着1件", rebuilt["email_subject"])
        self.assertIn("装甲騎兵ボトムズ総合模型演習2026", rebuilt["email_body"])


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

    def test_畳んだあとの行で作り直す(self):
        """digest が 1 件でも、日程が変わっていなければ何も積まない。"""
        existing = self.tmp / "events"
        existing.mkdir()
        row = {"title": "富野由悠季の原点－小田原から宇宙へ－",
               "start": "2026-11-06", "end": "2026-12-06",
               "categories": ["exhibition"], "matches": []}
        (existing / "doc_odawara.json").write_text(
            json.dumps(row, ensure_ascii=False), encoding="utf-8")
        writes = self.tmp / "writes.json"
        writes.write_text(json.dumps([{
            "op": "set", "collection": "events", "doc_id": "doc_odawara",
            "data": dict(row, dateConflict=[{"start": "2026-11-23"}]),
        }], ensure_ascii=False), encoding="utf-8")

        code = self._run(dict(DIGEST, count=1, generated_at="2026-10-08"),
                         "--writes", str(writes), "--existing-dir", str(existing))
        self.assertEqual(0, code)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
