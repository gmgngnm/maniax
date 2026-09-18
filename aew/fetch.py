"""記事本文や RSS を取りに行く共通部分。

この環境の外向き通信はポリシー適用のプロキシを通る。許可されていない
ホストは 403 で弾かれるので、**呼び出し側は「取れないのが普通」として
書くこと**。取れなければ日付の裏取りを諦めるだけで、処理は止めない。
"""

import os
import re
import ssl
import urllib.error
import urllib.request
from html import unescape

USER_AGENT = "maniax-anime-event-watch/1.0 (+https://github.com/gmgngnm/maniax)"
TIMEOUT = 20
MAX_BYTES = 2_000_000

# プロキシは TLS を張り直すので、この CA を信用する必要がある
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"

BLOCKED = "blocked"
UNREACHABLE = "unreachable"


class FetchError(Exception):
    """取得できなかった理由を kind で区別する。"""

    def __init__(self, kind: str, detail: str):
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


def _context() -> ssl.SSLContext:
    if os.path.exists(CA_BUNDLE):
        return ssl.create_default_context(cafile=CA_BUNDLE)
    return ssl.create_default_context()


def fetch_bytes(url: str, timeout: int = TIMEOUT) -> bytes:
    """URL を取得する。失敗は FetchError。"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_context()) as r:
            return r.read(MAX_BYTES)
    except urllib.error.HTTPError as exc:
        kind = BLOCKED if exc.code in (403, 407) else UNREACHABLE
        raise FetchError(kind, f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        # プロキシの拒否は CONNECT 段階で落ちるので URLError として来る
        detail = str(exc.reason)
        kind = BLOCKED if "403" in detail or "407" in detail else UNREACHABLE
        raise FetchError(kind, detail) from exc
    except (OSError, ValueError) as exc:
        raise FetchError(UNREACHABLE, str(exc)) from exc


_SCRIPT = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"[ \t　]+")
_BLANK = re.compile(r"\n{3,}")


def html_to_text(html: str) -> str:
    """本文らしきテキストを雑に取り出す。日付を拾うのが目的なので精度は程々でよい。"""
    text = _SCRIPT.sub(" ", html)
    text = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", text, flags=re.I)
    text = _TAG.sub(" ", text)
    text = unescape(text)
    text = _SPACE.sub(" ", text)
    return _BLANK.sub("\n\n", text).strip()


def _decode(raw: bytes) -> str:
    """文字コードを当てる。日本語サイトは UTF-8 か Shift_JIS/EUC が混ざる。"""
    head = raw[:4096].decode("ascii", "ignore").lower()
    for needle, codec in (
        ("shift_jis", "cp932"), ("shift-jis", "cp932"), ("windows-31j", "cp932"),
        ("euc-jp", "euc_jp"), ("iso-2022-jp", "iso2022_jp"),
    ):
        if needle in head:
            return raw.decode(codec, "replace")
    return raw.decode("utf-8", "replace")


def fetch_text(url: str, timeout: int = TIMEOUT) -> str:
    """記事本文をプレーンテキストで返す。失敗は FetchError。"""
    return html_to_text(_decode(fetch_bytes(url, timeout)))


def probe(url: str, timeout: int = 10) -> tuple[bool, str]:
    """到達できるかだけ確かめる。(可否, 理由) を返す。"""
    try:
        fetch_bytes(url, timeout)
        return True, "ok"
    except FetchError as exc:
        return False, f"{exc.kind}: {exc.detail}"
