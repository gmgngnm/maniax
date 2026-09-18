"""X（Twitter）の投稿を情報源として扱う。

公式アカウントの告知はニュースサイトより早い。API は有料枠が要り、
未認証の直接取得は遮断されているが、**ドメインを絞った WebSearch なら
投稿本文がそのまま返る**。追加の権限もキーも要らない。

さらに好都合なことに、status URL に含まれる ID は投稿時刻を埋め込んだ
snowflake なので、**ID だけから投稿日時を厳密に復元できる**。
記事の公開日が拾えず日付を出せない、という制約が X では起きない。
"""

import re
from datetime import datetime, timezone

# snowflake の基準時刻（2010-11-04T01:42:54.657Z）。上位ビットがミリ秒。
SNOWFLAKE_EPOCH_MS = 1288834974657
_TIMESTAMP_SHIFT = 22

# 復元結果として受け入れる範囲。2011-01-01 〜 2100-01-01。
_MIN_PLAUSIBLE_MS = 1293840000000
_MAX_PLAUSIBLE_MS = 4102444800000

_STATUS = re.compile(
    r"https?://(?:www\.)?(?:x|twitter|mobile\.twitter|fxtwitter|vxtwitter)\.com"
    r"/(?P<user>[A-Za-z0-9_]{1,15})/status(?:es)?/(?P<id>\d{10,25})"
)


def parse_status(url: str) -> tuple[str, int] | None:
    """status URL から (アカウント名, 投稿 ID) を取り出す。"""
    if not url:
        return None
    m = _STATUS.search(url)
    return (m.group("user"), int(m.group("id"))) if m else None


def is_x_url(url: str) -> bool:
    return parse_status(url) is not None


def posted_at(status_id: int) -> datetime | None:
    """投稿 ID から投稿日時（UTC）を復元する。"""
    ms = (status_id >> _TIMESTAMP_SHIFT) + SNOWFLAKE_EPOCH_MS
    # snowflake 導入（2010-11）直後や遠い未来になるものは、実在の ID ではない。
    # 基準時刻ちょうどに落ちる小さな数を投稿日として通さないための下限。
    if not (_MIN_PLAUSIBLE_MS <= ms <= _MAX_PLAUSIBLE_MS):
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def published_from_url(url: str) -> str | None:
    """X の URL なら投稿日を YYYY-MM-DD で返す。X でなければ None。

    日本のアカウントを追うので日本時間で日付にする。UTC のままだと
    夜の投稿が前日にずれ、年またぎの判定を誤る。
    """
    parsed = parse_status(url)
    if parsed is None:
        return None
    when = posted_at(parsed[1])
    if when is None:
        return None
    jst = when.timestamp() + 9 * 3600
    return datetime.fromtimestamp(jst, tz=timezone.utc).date().isoformat()


# リバイバル上映・特集上映の告知が集まるアカウント。作品を問わず効く。
AGGREGATOR_ACCOUNTS = [
    {"name": "Filmarksリバイバル上映", "handle": "Filmarks_ticket"},
    {"name": "東宝映画情報", "handle": "toho_movie"},
    {"name": "新文芸坐", "handle": "shin_bungeiza"},
    {"name": "塚口サンサン劇場", "handle": "sunsun3_gekijo"},
]

# WebSearch を X に絞って投げるときのドメイン
SEARCH_DOMAINS = ["x.com", "twitter.com"]


def work_queries(titles: list[str]) -> list[str]:
    """作品ごとに X を引くクエリ。"""
    return [f"{t} リバイバル上映 OR 上映決定 OR 舞台挨拶" for t in titles]


def aggregator_queries() -> list[str]:
    """告知が集まるアカウントを直接引く。"""
    return [f"from:{a['handle']} 上映" for a in AGGREGATOR_ACCOUNTS]
