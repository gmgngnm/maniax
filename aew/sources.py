"""情報源の一覧。

RSS 経路（collect_rss）で読むフィードと、WebSearch 経路で使う検索クエリの
ひな形を、ひとつの場所にまとめておく。
"""

# ネットワーク許可が下りたら collect_rss がここを読む。
# 現状この環境の egress ポリシーではいずれも 403 で塞がっている。
RSS_FEEDS = [
    {"name": "コミックナタリー", "url": "https://natalie.mu/comic/feed/news"},
    {"name": "映画ナタリー", "url": "https://natalie.mu/eiga/feed/news"},
    {"name": "音楽ナタリー", "url": "https://natalie.mu/music/feed/news"},
    {"name": "アニメ！アニメ！", "url": "https://animeanime.jp/rss/index.rdf"},
    {"name": "映画.com", "url": "https://eiga.com/rss/news/"},
    {"name": "アニメイトタイムズ", "url": "https://www.animatetimes.com/rss/"},
    {"name": "リスアニ！", "url": "https://www.lisani.jp/feed/"},
    {"name": "MOVIE WALKER PRESS", "url": "https://moviewalker.jp/rss/news.rdf"},
]

# WebSearch 経路のクエリ。{term} にウォッチリストの作品名・人物名が入る。
#
# 1 作品あたりの本数は意図的に絞ってある。カテゴリごとに 1 本ずつ立てると
# 作品数 × 5 本になり、上限で後ろのカテゴリが丸ごと落ちる。実際に試すと
# 「展示会 原画展 コンサート」のようにまとめても各カテゴリの記事は拾えるので、
# 近いカテゴリは 1 本に統合している。
WORK_QUERY_TEMPLATES = [
    "{term} リバイバル上映",
    "{term} 上映 イベント 決定",
    "{term} 展示会 原画展 コンサート",
]

# 作品を問わず広く拾う用。watchlist.settings.include_unmatched が真のときだけ使う。
BROAD_QUERIES = [
    "アニメ リバイバル上映 決定",
    "劇場アニメ 応援上映 爆音上映 決定",
    "アニメ 原画展 開催 決定",
]


def queries_for(watchlist: dict) -> list[str]:
    """ウォッチリストから検索クエリを組み立てる。

    作品数×テンプレート数をそのまま並べると件数が爆発し、1 回の実行で
    さばけない。テンプレート単位のラウンドロビンにして、全作品が
    「まず 1 本目のクエリ」を得てから 2 本目に進むようにする。
    こうすると上限で打ち切っても、特定の作品だけ完全に無視されることがない。
    """
    settings = watchlist.get("settings", {})
    limit = settings.get("max_queries", 40)

    works = [w["title"] for w in watchlist.get("works", []) if w.get("title")]
    people = [p["name"] for p in watchlist.get("people", []) if p.get("name")]

    rounds: list[list[str]] = []
    # 人物は本数が少ないので先に置き、確実に拾われるようにする
    rounds.append([f"{n} イベント 上映 決定" for n in people])
    for template in WORK_QUERY_TEMPLATES:
        rounds.append([template.format(term=t) for t in works])
    rounds.append([f"{n} 展示会 トークショー 登壇" for n in people])
    if settings.get("include_unmatched"):
        rounds.append(list(BROAD_QUERIES))

    out: list[str] = []
    for group in rounds:
        out.extend(group)
    # 重複を落としつつ順序は保つ
    return list(dict.fromkeys(out))[:limit]


def _main() -> None:
    """watchlist.json から検索クエリを 1 行ずつ出す。

    定期実行のセッションが「今回どれを検索すべきか」を得るための入口。
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(description=_main.__doc__)
    parser.add_argument("--watchlist", default="watchlist.json")
    args = parser.parse_args()

    with open(args.watchlist, encoding="utf-8") as handle:
        queries = queries_for(json.load(handle))
    try:
        for query in queries:
            print(query)
    except BrokenPipeError:
        # `| head` などで受け側が先に閉じただけ。異常ではない。
        pass


if __name__ == "__main__":
    _main()
