"""YouTube 公式チャンネルを情報源にする。

チャンネル ID さえ分かれば、認証なしで Atom フィードが読める。
新作の予告公開や上映告知が、ニュースサイトより先に出ることがある。

ID を設定に直書きすると間違いが紛れ込むので、ハンドル（@name）から
実行時に解決する。解決できなければそのチャンネルは黙って飛ばす。
推測した ID で誤った情報源を作るくらいなら、使わない方がよい。
"""

import re

from .fetch import FetchError, fetch_bytes

FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
_CHANNEL_ID = re.compile(rb'"(?:channelId|externalId)"\s*:\s*"(UC[\w-]{22})"')


def resolve(handle: str) -> str | None:
    """@handle からチャンネル ID を引く。取得できなければ None。"""
    handle = handle.lstrip("@")
    try:
        page = fetch_bytes(f"https://www.youtube.com/@{handle}")
    except FetchError:
        return None
    m = _CHANNEL_ID.search(page)
    return m.group(1).decode() if m else None


def feed_url(channel_id: str) -> str:
    return FEED.format(channel_id)


def resolve_all(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """[{name, handle}] を [{name, url}] に。(解決できたもの, できなかったもの)。"""
    resolved, failed = [], []
    for entry in entries:
        channel_id = resolve(entry["handle"])
        if channel_id:
            resolved.append({"name": entry["name"], "url": feed_url(channel_id)})
        else:
            failed.append(entry)
    return resolved, failed
