"""記録の置き場所を DB に移した部分。

以前は state/seen.json を git で持ち回っていたが、Routine のセッションに
push 権限が無く、記録は一度も残らなかった。毎朝その失敗だけが通知されて
いた。DB 経由に移したので、ドキュメントが無い初回でも落ちないことと、
壊れた中身で落ちないことを押さえる。
"""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from aew.seen_db import load
from aew.store import SeenStore


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_ドキュメントが無ければ空の記録(self):
        self.assertEqual({"entries": {}}, load(self.tmp))

    def test_中身を読む(self):
        (self.tmp / "seen.json").write_text(
            json.dumps({"entries": {"abc": {"last_seen": "2026-10-01"}}}),
            encoding="utf-8")
        self.assertEqual({"abc": {"last_seen": "2026-10-01"}},
                         load(self.tmp)["entries"])

    def test_壊れたJSONでも落ちない(self):
        (self.tmp / "seen.json").write_text("{", encoding="utf-8")
        self.assertEqual({"entries": {}}, load(self.tmp))

    def test_entriesが辞書でなければ無視する(self):
        (self.tmp / "seen.json").write_text(
            json.dumps({"entries": ["abc"]}), encoding="utf-8")
        self.assertEqual({"entries": {}}, load(self.tmp))


class TestRoundTrip(unittest.TestCase):
    """DB → ファイル → SeenStore → ファイル → DB で記録が往復すること。"""

    def test_往復しても記録が残る(self):
        tmp = Path(tempfile.mkdtemp())
        doc = tmp / "control"
        doc.mkdir()
        (doc / "seen.json").write_text(
            json.dumps({"entries": {}}), encoding="utf-8")

        state = tmp / "seen.json"
        state.write_text(json.dumps(load(doc)), encoding="utf-8")

        store = SeenStore(state)
        item = {"title": "富野由悠季の原点", "url": "https://example.com/a"}
        self.assertEqual("new", store.status(item, "2026-11-06"))
        store.remember(item, "2026-11-06", date(2026, 10, 5))
        store.save()

        # DB に書き戻したものを次の巡回が読み直す
        (doc / "seen.json").write_text(state.read_text(encoding="utf-8"),
                                       encoding="utf-8")
        again = SeenStore(Path(tempfile.mkdtemp()) / "s.json")
        again.entries = load(doc)["entries"]
        self.assertEqual("known", again.status(item, "2026-11-06"))

    def test_保存した中身がそのままDBのドキュメントになる(self):
        state = Path(tempfile.mkdtemp()) / "seen.json"
        store = SeenStore(state)
        store.remember({"title": "A", "url": "https://a/"}, None, date(2026, 10, 5))
        store.save()
        saved = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(["entries"], list(saved.keys()))


if __name__ == "__main__":
    unittest.main()
