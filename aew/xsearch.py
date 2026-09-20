"""X のキーワード検索。複数の経路を優先順に試す。

## なぜ必要か

WebSearch をドメインで x.com に絞る方法は動くが、**速報性が無い**。
2026-09-20 に「リバイバル上映 決定 アニメ」で実測したところ、返って
きた投稿は最新でも 41 日前、中央値 120 日前だった。検索エンジンの
索引を経由する以上これは避けられない。チケットの発売告知には間に合わない。

本物の検索には、X 側か、X を実時間で索引している先に直接あたるしかない。
どれもこの環境の egress ポリシーで塞がれているので、許可が下りるまでは
`available()` がすべて False を返し、呼び出し側は WebSearch 経路に留まる。

## 経路

api      X API v2 /2/tweets/search/recent。直近 7 日をキーワード検索できる。
         最も正確で速い。有料枠のトークン（環境変数 X_BEARER_TOKEN）と
         api.x.com への到達が要る。
realtime Yahoo! リアルタイム検索。X を実時間で索引しており、日本語の
         検索に強い。無料。search.yahoo.co.jp への到達が要る。
profile  syndication エンドポイントで特定アカウントの最近の投稿を読む。
         キーワード検索はできないが、公式アカウントを列挙して追える。
         無料。syndication.twitter.com への到達が要る。
"""

import json
import os
import re
import urllib.parse
from datetime import datetime, timezone

from .fetch import FetchError, fetch_bytes, fetch_text, html_to_text
from .xposts import parse_status, posted_at

API_HOST = "https://api.x.com"
REALTIME = "https://search.yahoo.co.jp/realtime/search?p={}"
SYNDICATION = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{}"

BEARER_ENV = "X_BEARER_TOKEN"


def bearer_token() -> str | None:
    token = os.environ.get(BEARER_ENV, "").strip()
    return token or None


# ---------------------------------------------------------------- 共通

_STATUS_LINK = re.compile(
    r"https?://(?:www\.)?(?:x|twitter)\.com/[A-Za-z0-9_]{1,15}/status/\d{10,25}"
)


def extract_status_links(html: str) -> list[dict]:
    """HTML から X の投稿リンクを拾い、周辺のテキストを本文として添える。

    ページの構造に依存しない作りにしてある。相手の markup を観測できない
    環境で、クラス名や階層を決め打ちしたパーサを書くと、動かないものを
    「動く」と言うことになる。リンクと本文の近さだけを頼りにする。

    投稿日時は ID から厳密に復元できるので、抽出が粗くても日付は正確。
    """
    text = html_to_text(html)
    found: dict[str, dict] = {}

    for match in _STATUS_LINK.finditer(html):
        url = match.group(0)
        parsed = parse_status(url)
        if not parsed:
            continue
        user, status_id = parsed
        if str(status_id) in found:
            continue
        when = posted_at(status_id)
        found[str(status_id)] = {
            "url": f"https://x.com/{user}/status/{status_id}",
            "user": user,
            "id": str(status_id),
            "posted": when.date().isoformat() if when else "",
            "text": "",
        }

    # 本文はページ全体のテキストから、投稿ごとに切り出せないことが多い。
    # 取れる範囲で埋め、取れなければ空のままにする（捏造しない）。
    if len(found) == 1:
        only = next(iter(found.values()))
        only["text"] = text[:600]

    return list(found.values())


# ---------------------------------------------------------------- api

def search_api(query: str, limit: int = 25) -> list[dict]:
    """X API v2 の recent search。トークンが無ければ空。

    注意: この環境から api.x.com に到達できないため、実際の応答で
    検証できていない。到達できるようになったら、まず 1 件だけ投げて
    応答の形を確かめること。
    """
    token = bearer_token()
    if not token:
        return []
    params = urllib.parse.urlencode({
        "query": query,
        "max_results": max(10, min(limit, 100)),
        "tweet.fields": "created_at,author_id",
        "expansions": "author_id",
        "user.fields": "username",
    })
    url = f"{API_HOST}/2/tweets/search/recent?{params}"
    raw = fetch_bytes(url, headers={"Authorization": f"Bearer {token}"})
    return parse_api_response(json.loads(raw.decode("utf-8")))


def parse_api_response(payload: dict) -> list[dict]:
    """X API v2 の応答を候補の形に直す。"""
    names = {
        u["id"]: u.get("username", "")
        for u in payload.get("includes", {}).get("users", [])
    }
    out = []
    for post in payload.get("data", []):
        user = names.get(post.get("author_id", ""), "i")
        posted = ""
        created = post.get("created_at", "")
        if created:
            try:
                posted = datetime.fromisoformat(
                    created.replace("Z", "+00:00")
                ).astimezone(timezone.utc).date().isoformat()
            except ValueError:
                posted = ""
        out.append({
            "url": f"https://x.com/{user}/status/{post['id']}",
            "user": user,
            "id": post["id"],
            "posted": posted,
            "text": post.get("text", ""),
        })
    return out


# ---------------------------------------------------------------- realtime

def search_realtime(query: str) -> list[dict]:
    """Yahoo! リアルタイム検索を引く。"""
    return extract_status_links(
        fetch_text_raw(REALTIME.format(urllib.parse.quote(query)))
    )


def fetch_text_raw(url: str) -> str:
    """html_to_text を通す前の生 HTML。リンク抽出に要る。"""
    return fetch_bytes(url).decode("utf-8", "replace")


# ---------------------------------------------------------------- profile

def recent_posts(handle: str) -> list[dict]:
    """公式アカウントの最近の投稿。キーワード検索ではない。"""
    return extract_status_links(fetch_text_raw(SYNDICATION.format(handle.lstrip("@"))))


# ---------------------------------------------------------------- 可否

BACKENDS = [
    ("api", f"{API_HOST}/2/openapi.json"),
    ("realtime", "https://search.yahoo.co.jp/realtime"),
    ("profile", "https://syndication.twitter.com/"),
]


def available() -> dict[str, tuple[bool, str]]:
    """どの経路が使えるか。preflight から呼ぶ。"""
    from .fetch import probe

    result = {}
    for name, url in BACKENDS:
        ok, why = probe(url)
        if name == "api" and ok and not bearer_token():
            ok, why = False, f"到達できるが {BEARER_ENV} が未設定"
        result[name] = (ok, why)
    return result


def search(query: str, limit: int = 25) -> tuple[list[dict], str]:
    """使える経路で検索する。(結果, 使った経路) を返す。

    どれも使えなければ ([], "none")。呼び出し側は WebSearch 経路に戻る。
    """
    if bearer_token():
        try:
            return search_api(query, limit), "api"
        except (FetchError, ValueError, KeyError):
            pass
    try:
        return search_realtime(query), "realtime"
    except (FetchError, ValueError):
        pass
    return [], "none"
