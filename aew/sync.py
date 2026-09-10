"""GUI（Artifact のデータベース）と収集パイプラインをつなぐ変換。

GUI 側が持つウォッチリストを収集側の形に直し、収集結果を GUI に
書き戻すための書き込み一覧に直す。この 2 方向だけを受け持つ。

  # DB から取り出したウォッチリストを watchlist.json の形にする
  python3 -m aew.sync from-db --dir /tmp/db/watchlist --out watchlist.json

  # ダイジェストを DB への書き込み一覧にする
  python3 -m aew.sync to-writes --digest /tmp/digest.json --out /tmp/writes.json
"""

import argparse
import json
from pathlib import Path

from .normalize import fingerprint

# GUI 側に無い設定は既存の watchlist.json から引き継ぐ
DEFAULT_SETTINGS = {
    "categories": ["revival", "screening_event", "exhibition", "concert"],
    "include_unmatched": False,
    "drop_past_events": True,
    "max_queries": 40,
}


def from_db(doc_dir: Path, fallback: Path | None) -> dict:
    """read_db --out_dir が吐いた JSON 群を watchlist.json の形に組み直す。"""
    settings = dict(DEFAULT_SETTINGS)
    if fallback and fallback.exists():
        existing = json.loads(fallback.read_text(encoding="utf-8"))
        settings.update(existing.get("settings", {}))

    works, people = [], []
    for path in sorted(Path(doc_dir).glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        label = (doc.get("label") or "").strip()
        if not label:
            continue
        aliases = [str(a).strip() for a in doc.get("aliases", []) if str(a).strip()]
        if doc.get("kind") == "person":
            people.append(
                {"name": label, "role": doc.get("role", ""), "aliases": aliases}
            )
        else:
            works.append({"title": label, "aliases": aliases})

    return {"settings": settings, "people": people, "works": works}


def to_writes(digest: dict) -> list[dict]:
    """ダイジェストの各件を、GUI が読む events コレクションへの set にする。

    doc_id は収集側の重複判定と同じ fingerprint なので、同じイベントを
    別の日に拾い直しても行が増えず、上書きになる。
    """
    writes = []
    for item in digest.get("items", []):
        event = item.get("event") or {}
        writes.append(
            {
                "op": "set",
                "collection": "events",
                "doc_id": fingerprint(item.get("title", ""), item.get("url", "")),
                "data": {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "summary": item.get("summary", ""),
                    "source": item.get("source", ""),
                    "categories": item.get("categories", []),
                    "matches": item.get("matches", []),
                    "start": event.get("start"),
                    "end": event.get("end"),
                },
            }
        )
    return writes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    a = sub.add_parser("from-db", help="DB のウォッチリスト -> watchlist.json")
    a.add_argument("--dir", required=True, help="read_db --out_dir が作った watchlist ディレクトリ")
    a.add_argument("--out", required=True)
    a.add_argument("--fallback", default="watchlist.json", help="settings の引き継ぎ元")

    b = sub.add_parser("to-writes", help="ダイジェスト -> DB 書き込み一覧")
    b.add_argument("--digest", required=True)
    b.add_argument("--out", required=True)

    args = parser.parse_args(argv)

    if args.command == "from-db":
        result = from_db(Path(args.dir), Path(args.fallback))
        if not result["works"] and not result["people"]:
            raise SystemExit(
                "DB のウォッチリストが空。GUI 側が消えている恐れがあるので、"
                "リポジトリの watchlist.json をそのまま使うこと。"
            )
        payload = result
    else:
        payload = to_writes(json.loads(Path(args.digest).read_text(encoding="utf-8")))

    Path(args.out).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
