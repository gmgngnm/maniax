"""手元の PC から渡された候補を取り込む。

`inbox/` に置かれた JSON を読み、通常の候補と結合する。読み終えたファイルは
巡回側が削除する（同じものを何度も取り込まないため。重複判定もあるので
二重に通知されることは無いが、溜め続ける理由も無い）。
"""

import argparse
import json
from pathlib import Path


def load(directory: Path) -> tuple[list[dict], list[Path]]:
    """inbox の中身をすべて読む。(候補, 読んだファイル) を返す。"""
    candidates: list[dict] = []
    read: list[Path] = []
    for path in sorted(Path(directory).glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            # 壊れたファイルで巡回全体を止めない
            continue
        if isinstance(payload, list):
            candidates.extend(c for c in payload if isinstance(c, dict))
            read.append(path)
    return candidates, read


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default="inbox")
    parser.add_argument("--merge-into", help="既存の candidates.json に足す")
    parser.add_argument("--out", required=True)
    parser.add_argument("--consume", action="store_true",
                        help="読み終えたファイルを削除する")
    args = parser.parse_args()

    candidates, read = load(Path(args.dir))
    if args.merge_into and Path(args.merge_into).exists():
        existing = json.loads(Path(args.merge_into).read_text(encoding="utf-8"))
        candidates = list(existing) + candidates

    Path(args.out).write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.consume:
        for path in read:
            path.unlink()
    print(f"inbox から {len(read)} ファイル / 合計 {len(candidates)} 件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
