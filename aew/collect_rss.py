"""RSS/Atom を直接読んで候補 JSON を作る（ネットワーク許可が要る経路）。

  python3 -m aew.collect_rss --out candidates.json

egress ポリシーで対象ドメインが塞がっている間は、各フィードが失敗として
記録され、空の配列が出る。WebSearch 経路の出力と同じ形なので、
許可が下りたら ingest への入力をこちらに差し替えるだけで移行できる。
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from xml.etree import ElementTree

from .dates import parse_published
from .sources import RSS_FEEDS

USER_AGENT = "maniax-anime-event-watch/1.0 (+https://github.com/gmgngnm/maniax)"
TIMEOUT = 20

# 名前空間つきタグを素朴に扱うため、タグ名だけ見る
def _tag(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _text(parent, *names) -> str:
    for child in parent:
        if _tag(child) in names:
            if child.text:
                return child.text.strip()
            # Atom の <link href="..."/>
            href = child.attrib.get("href")
            if href:
                return href.strip()
    return ""


def parse_feed(xml_bytes: bytes, source_name: str) -> list[dict]:
    """RSS 2.0 / RDF (RSS 1.0) / Atom のいずれからも項目を取り出す。"""
    root = ElementTree.fromstring(xml_bytes)
    items = [e for e in root.iter() if _tag(e) in ("item", "entry")]
    out = []
    for element in items:
        title = _text(element, "title")
        if not title:
            continue
        out.append(
            {
                "title": title,
                "url": _text(element, "link", "id"),
                "summary": _text(element, "description", "summary", "content")[:400],
                "source": source_name,
                "published": _text(element, "pubDate", "date", "published", "updated"),
            }
        )
    return out


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def collect(feeds=None) -> tuple[list[dict], list[dict]]:
    """(候補, 失敗したフィード) を返す。1本落ちても全体は止めない。"""
    candidates: list[dict] = []
    failures: list[dict] = []
    for feed in feeds or RSS_FEEDS:
        try:
            candidates.extend(parse_feed(fetch(feed["url"]), feed["name"]))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            failures.append({"name": feed["name"], "url": feed["url"], "error": str(exc)})
        except ElementTree.ParseError as exc:
            failures.append(
                {"name": feed["name"], "url": feed["url"], "error": f"parse: {exc}"}
            )
    return candidates, failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="候補 JSON の出力先（省略時は標準出力）")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=14,
        help="これより古い記事は捨てる。日付が読めないものは残す。",
    )
    args = parser.parse_args(argv)

    candidates, failures = collect()
    if args.max_age_days:
        candidates = _drop_old(candidates, args.max_age_days)

    text = json.dumps(candidates, ensure_ascii=False, indent=2)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text + "\n")
    else:
        print(text)

    for failure in failures:
        print(f"[warn] {failure['name']}: {failure['error']}", file=sys.stderr)
    if failures and not candidates:
        print(
            "[error] 全フィードの取得に失敗した。egress ポリシーで "
            "対象ドメインが許可されているか確認すること。",
            file=sys.stderr,
        )
        return 1
    return 0


def _drop_old(candidates: list[dict], max_age_days: int) -> list[dict]:
    cutoff = date.today() - timedelta(days=max_age_days)
    kept = []
    for candidate in candidates:
        published = parse_published(candidate.get("published", ""))
        if published is None or published >= cutoff:
            kept.append(candidate)
    return kept


if __name__ == "__main__":
    raise SystemExit(main())
