"""手元の PC で X を検索し、巡回に渡す候補を作る。

## なぜこれがあるか

巡回が動くクラウド環境は egress ポリシーで X も Yahoo! リアルタイム検索も
塞がれている。一方、手元の PC にはその制限が無い。**検索だけを手元でやり、
結果をリポジトリ経由で渡せば**、クラウド側の制限を回避せずに速報性が手に入る。

## 使い方（手元の PC で）

    git clone https://github.com/gmgngnm/maniax && cd maniax
    python3 -m aew.collect_x --watchlist watchlist.json --out inbox/$(date +%F).json
    git add inbox && git commit -m "x: $(date +%F) の収集" && git push

次の巡回が `inbox/` を読み、通常の検索結果と一緒に突き合わせる。
取り込んだファイルは巡回側が消すので、置きっぱなしにしてよい。

X API のトークンがあれば `X_BEARER_TOKEN` に入れておくと、そちらが優先される。
無ければ Yahoo! リアルタイム検索を使う。どちらも使えなければ何も出力しない。

## 注意

ログインした状態で X を機械的に読むことはしない。規約違反であり、
アカウントが凍結される。ここで使うのは公開 API と、X を索引している
第三者の検索のみ。
"""

import argparse
import json
from datetime import date
from pathlib import Path

from .sources import x_queries_for
from .xsearch import search


def collect(watchlist: dict, limit_per_query: int = 25) -> tuple[list[dict], dict]:
    """ウォッチリストの各語で X を引き、候補の形にして返す。"""
    candidates: dict[str, dict] = {}
    stats = {"queries": 0, "hits": 0, "backends": {}}

    for query in x_queries_for(watchlist):
        stats["queries"] += 1
        posts, backend = search(query, limit_per_query)
        stats["backends"][backend] = stats["backends"].get(backend, 0) + 1
        for post in posts:
            if post["url"] in candidates:
                continue
            candidates[post["url"]] = {
                "title": post.get("text") or f"@{post['user']} の投稿",
                "url": post["url"],
                # 本文をそのまま渡す。要約は作らない（年の創作を防ぐ）
                "snippet": post.get("text", ""),
                "summary": "",
                "source": f"X (@{post['user']})",
                # 空でよい。ingest が status ID から厳密に復元する。
                "published": post.get("posted", ""),
            }
    stats["hits"] = len(candidates)
    return list(candidates.values()), stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist", default="watchlist.json")
    parser.add_argument("--out", default=f"inbox/{date.today().isoformat()}.json")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    watchlist = json.loads(Path(args.watchlist).read_text(encoding="utf-8"))
    candidates, stats = collect(watchlist, args.limit)

    if not candidates:
        print("候補なし。", end=" ")
        if stats["backends"].get("none"):
            print("X に到達できる経路がありません。"
                  "X_BEARER_TOKEN を設定するか、ネットワークを確認してください。")
        else:
            print("検索はできましたが、該当する投稿がありませんでした。")
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    used = ", ".join(f"{k}×{v}" for k, v in sorted(stats["backends"].items()))
    print(f"{stats['queries']} クエリ / {stats['hits']} 件を {out} に書き出した（経路: {used}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
