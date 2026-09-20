"""どの情報源に届くかを一覧する。

ネットワークポリシーを変えたあと、何が使えるようになったかを
確かめるための道具。

  python3 -m aew.preflight
"""

import argparse

from .fetch import probe
from .sources import RSS_FEEDS, THEATER_PAGES, YOUTUBE_HANDLES
from .youtube import resolve


def run(check_youtube: bool = True) -> int:
    groups = [("RSS（ニュース）", RSS_FEEDS), ("劇場サイト", THEATER_PAGES)]
    reachable = 0
    total = 0

    for label, entries in groups:
        print(f"\n== {label} ==")
        for entry in entries:
            ok, why = probe(entry["url"])
            total += 1
            reachable += ok
            print(f"  {'OK  ' if ok else 'NG  '}{entry['name']:<22}{'' if ok else why[:58]}")

    print("\n== X のキーワード検索 ==")
    from .xsearch import available as x_available
    for name, (ok, why) in x_available().items():
        total += 1
        reachable += ok
        label = {"api": "X API v2（要トークン）",
                 "realtime": "Yahoo!リアルタイム検索",
                 "profile": "公式アカウント購読"}[name]
        print(f"  {'OK  ' if ok else 'NG  '}{label:<26}{'' if ok else why[:44]}")

    if check_youtube:
        print("\n== YouTube 公式チャンネル ==")
        for entry in YOUTUBE_HANDLES:
            total += 1
            channel_id = resolve(entry["handle"])
            if channel_id:
                reachable += 1
                print(f"  OK  {entry['name']:<22}{channel_id}")
            else:
                print(f"  NG  {entry['name']:<22}解決できず（{entry['handle']}）")

    print(f"\n到達: {reachable}/{total}")
    if reachable == 0:
        print(
            "\nすべて遮断されている。環境のネットワークポリシーが許可制のままか確認する。\n"
            "https://code.claude.com/docs/en/claude-code-on-the-web"
        )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-youtube", action="store_true")
    args = parser.parse_args(argv)
    return run(check_youtube=not args.skip_youtube)


if __name__ == "__main__":
    raise SystemExit(main())
