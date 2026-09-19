"""GUI（Artifact のデータベース）と収集パイプラインをつなぐ変換。

GUI 側が持つウォッチリストを収集側の形に直し、収集結果を GUI に
書き戻すための書き込み一覧に直す。この 2 方向だけを受け持つ。

  # DB から取り出したウォッチリストを watchlist.json の形にする
  python3 -m aew.sync from-db --dir /tmp/db/watchlist --out watchlist.json

  # そのうち、まだ一度も検索していない分だけ
  python3 -m aew.sync from-db --dir /tmp/db/watchlist --out /tmp/new.json --pending-only

  # 検索し終えた分に検索済みの印をつける書き込み一覧
  python3 -m aew.sync mark-searched --dir /tmp/db/watchlist --out /tmp/marks.json

  # ダイジェストを DB への書き込み一覧にする
  python3 -m aew.sync to-writes --digest /tmp/digest.json --out /tmp/writes.json

  # 既存の行とも突き合わせて重複を畳む（to-writes の代わりに使う）
  python3 -m aew.sync merge-existing --existing-dir /tmp/db/events \
      --versions /tmp/versions.json --digest /tmp/digest.json --out /tmp/writes.json
"""

import argparse
import json
from pathlib import Path

from .normalize import fingerprint

# GUI 側に無い設定は既存の watchlist.json から引き継ぐ
DEFAULT_SETTINGS = {
    "categories": ["revival", "screening_event", "exhibition", "concert", "goods"],
    "include_unmatched": False,
    "drop_past_events": True,
    "max_queries": 100,
}


def is_pending(doc: dict) -> bool:
    """まだ一度も検索していないエントリか。

    GUI から足したばかりの項目には searched: false が入る。翌朝の巡回を
    待たずに拾いたいのはこれだけ。フィールドが無い古い行は、取りこぼしを
    避けるため検索済みとみなす（新規追加時は必ず false が入るため）。
    """
    return doc.get("searched") is False


def pending_ids(doc_dir: Path) -> list[str]:
    """未検索エントリのドキュメント ID を、ファイル名から拾う。"""
    out = []
    for path in sorted(Path(doc_dir).glob("*.json")):
        if is_pending(json.loads(path.read_text(encoding="utf-8"))):
            out.append(path.stem)
    return out


def mark_writes(doc_ids: list[str]) -> list[dict]:
    """検索済みの印をつける update 書き込みを組む。"""
    return [
        {"op": "update", "collection": "watchlist", "doc_id": doc_id,
         "data": {"searched": True}}
        for doc_id in doc_ids
    ]


def from_db(doc_dir: Path, fallback: Path | None, pending_only: bool = False) -> dict:
    """read_db --out_dir が吐いた JSON 群を watchlist.json の形に組み直す。

    pending_only を立てると、まだ検索していないエントリだけを拾う。
    追加直後の作品を翌朝まで待たずに検索するために使う。このとき
    劇場側からの探索は外す。追加された作品とは無関係な固定クエリで、
    毎時走らせても同じ結果を引き直すだけだから。
    """
    settings = dict(DEFAULT_SETTINGS)
    if fallback and fallback.exists():
        existing = json.loads(fallback.read_text(encoding="utf-8"))
        settings.update(existing.get("settings", {}))
    if pending_only:
        settings["venue_queries"] = False

    works, people = [], []
    for path in sorted(Path(doc_dir).glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if pending_only and not is_pending(doc):
            continue
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
                    "published": item.get("published", ""),
                    "dateNote": item.get("date_note", ""),
                    "dateHint": item.get("date_hint", ""),
                    "dateConflict": item.get("date_conflict", []),
                    "sources": item.get("sources", []),
                    "unverifiable": bool(item.get("unverifiable")),
                    "firstSeen": item.get("first_seen", ""),
                },
            }
        )
    return writes


def _event_from_db(doc_id: str, data: dict) -> dict:
    """GUI に入っている行を、突き合わせに使える形に戻す。"""
    start = data.get("start")
    return {
        "_doc_id": doc_id,
        "title": data.get("title", ""),
        "url": data.get("url", ""),
        "summary": data.get("summary", ""),
        "source": data.get("source", ""),
        "published": data.get("published", ""),
        "categories": data.get("categories", []),
        "matches": data.get("matches", []),
        "event": {"start": start, "end": data.get("end"),
                  "year_explicit": True} if start else None,
        "date_note": data.get("dateNote", ""),
        "date_hint": data.get("dateHint", ""),
        "date_conflict": data.get("dateConflict", []),
        "sources": data.get("sources", []),
        "unverifiable": bool(data.get("unverifiable")),
        "calendar_event_id": data.get("calendarEventId", ""),
        "status": "known",
    }


def merge_existing(existing: list[dict], fresh: list[dict],
                   versions: dict[str, int]) -> list[dict]:
    """新着を既存の行と突き合わせ、DB への書き込み一覧を作る。

    `collapse` は 1 回の巡回の中でしか同じ催しをまとめられない。別の日に
    別の媒体が同じ催しを報じると、GUI に 2 行目ができてしまう。実際、
    小田原の展覧会が X 経由で 2 行目になった。ここでは既存の行も一緒に
    束ね、同じ催しなら 1 行に畳む。

    既存の行しか含まないまとまりには触れない（無用な書き換えを避ける）。
    """
    from .cluster import group, resolve

    writes: list[dict] = []
    for members in group(existing + fresh):
        known = [m for m in members if m.get("_doc_id")]
        if len(members) == len(known):
            continue  # 新着なし。触らない。

        merged = resolve(members)

        # 既にカレンダーに入れてあるなら、その紐づけを失わない
        for m in members:
            if m.get("calendar_event_id"):
                merged["calendar_event_id"] = m["calendar_event_id"]
                break

        # 既存の行があればその ID を引き継ぐ。カレンダー登録済みを優先。
        if known:
            known.sort(key=lambda m: (0 if m.get("calendar_event_id") else 1,
                                      m["_doc_id"]))
            doc_id = known[0]["_doc_id"]
        else:
            doc_id = fingerprint(merged.get("title", ""), merged.get("url", ""))

        data = _event_payload(merged)
        write = {"op": "set", "collection": "events", "doc_id": doc_id, "data": data}
        if doc_id in versions:
            write["if_version"] = versions[doc_id]
        writes.append(write)

        # 同じ催しに畳まれた他の行は消す
        for m in known[1:]:
            drop = {"op": "delete", "collection": "events", "doc_id": m["_doc_id"]}
            if m["_doc_id"] in versions:
                drop["if_version"] = versions[m["_doc_id"]]
            writes.append(drop)

    return writes


def _event_payload(item: dict) -> dict:
    event = item.get("event") or {}
    payload = {
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "summary": item.get("summary", ""),
        "source": item.get("source", ""),
        "categories": item.get("categories", []),
        "matches": item.get("matches", []),
        "start": event.get("start"),
        "end": event.get("end"),
        "published": item.get("published", ""),
        "dateNote": item.get("date_note", ""),
        "dateHint": item.get("date_hint", ""),
        "dateConflict": item.get("date_conflict", []),
        "sources": item.get("sources", []),
        "unverifiable": bool(item.get("unverifiable")),
    }
    if item.get("calendar_event_id"):
        payload["calendarEventId"] = item["calendar_event_id"]
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    a = sub.add_parser("from-db", help="DB のウォッチリスト -> watchlist.json")
    a.add_argument("--dir", required=True, help="read_db --out_dir が作った watchlist ディレクトリ")
    a.add_argument("--out", required=True)
    a.add_argument("--fallback", default="watchlist.json", help="settings の引き継ぎ元")
    a.add_argument("--pending-only", action="store_true",
                   help="まだ検索していないエントリだけを出す")

    b = sub.add_parser("to-writes", help="ダイジェスト -> DB 書き込み一覧")
    b.add_argument("--digest", required=True)
    b.add_argument("--out", required=True)

    d = sub.add_parser("merge-existing",
                       help="新着を既存の行と突き合わせ、重複を畳んで書き込み一覧にする")
    d.add_argument("--existing-dir", required=True,
                   help="read_db --out_dir が作った events ディレクトリ")
    d.add_argument("--versions", required=True,
                   help='{"doc_id": version} の JSON。list の出力から作る')
    d.add_argument("--digest", required=True)
    d.add_argument("--out", required=True)

    c = sub.add_parser("mark-searched", help="未検索エントリに検索済みの印をつける")
    c.add_argument("--dir", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--all", action="store_true",
                   help="未検索に限らず全エントリを対象にする（日次の全件巡回向け）")

    args = parser.parse_args(argv)

    if args.command == "from-db":
        result = from_db(Path(args.dir), Path(args.fallback), args.pending_only)
        if not result["works"] and not result["people"]:
            if args.pending_only:
                # 追加分がないのは平常。呼び出し側が終了コードで判断する。
                print("no pending entries")
                return 2
            raise SystemExit(
                "DB のウォッチリストが空。GUI 側が消えている恐れがあるので、"
                "リポジトリの watchlist.json をそのまま使うこと。"
            )
        payload = result
    elif args.command == "merge-existing":
        existing = [
            _event_from_db(path.stem, json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(Path(args.existing_dir).glob("*.json"))
        ]
        digest = json.loads(Path(args.digest).read_text(encoding="utf-8"))
        versions = json.loads(Path(args.versions).read_text(encoding="utf-8"))
        payload = merge_existing(existing, digest.get("items", []), versions)
    elif args.command == "mark-searched":
        directory = Path(args.dir)
        ids = (
            [p.stem for p in sorted(directory.glob("*.json"))]
            if args.all
            else pending_ids(directory)
        )
        payload = mark_writes(ids)
    else:
        payload = to_writes(json.loads(Path(args.digest).read_text(encoding="utf-8")))

    Path(args.out).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
